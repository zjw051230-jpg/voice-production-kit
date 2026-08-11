#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

DISPLAY_NAME = "5.5"
CATALOG_DISPLAY_NAME = "gpt-5.5"
TARGET_MODEL = "deepseek-v4-pro"
CATALOG_FILENAME = "cc-switch-model-catalog.json"
POINTER_LINE = f'model_catalog_json = "{CATALOG_FILENAME}"'
POINTER_PATTERN = re.compile(r"(?m)^[ \t]*model_catalog_json[ \t]*=.*(?:\r?\n)?")


def choose_provider(connection: sqlite3.Connection, provider_id: str | None) -> sqlite3.Row:
    connection.row_factory = sqlite3.Row
    if provider_id:
        row = connection.execute(
            "SELECT id, name, settings_config FROM providers WHERE id = ? AND app_type = 'codex'",
            (provider_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"未找到 Codex provider：{provider_id}")
        return row

    rows = connection.execute(
        "SELECT id, name, settings_config FROM providers "
        "WHERE app_type = 'codex' AND is_current = 1"
    ).fetchall()
    if len(rows) != 1:
        raise RuntimeError("无法唯一确定当前 Codex provider，请使用 --provider-id 明确指定")
    return rows[0]


def set_catalog_pointer(config: str) -> tuple[str, str]:
    matches = list(POINTER_PATTERN.finditer(config))
    if len(matches) > 1:
        raise RuntimeError("provider config 中存在多个 model_catalog_json，已停止")
    if matches:
        current = matches[0].group(0).rstrip("\r\n")
        updated = POINTER_PATTERN.sub(POINTER_LINE + "\n", config, count=1)
        return updated, "保持" if current.strip() == POINTER_LINE else "替换"
    return POINTER_LINE + "\n" + config, "新增"


def without_pointer(config: str) -> str:
    return POINTER_PATTERN.sub("", config)


def target_catalog_entry() -> dict:
    return {
        "additional_speed_tiers": [],
        "availability_nux": None,
        "base_instructions": "You are Codex, a coding agent. You and the user share the same workspace and collaborate to achieve the user's goals.",
        "context_window": 12800,
        "default_reasoning_level": "high",
        "default_reasoning_summary": "none",
        "description": CATALOG_DISPLAY_NAME,
        "display_name": CATALOG_DISPLAY_NAME,
        "effective_context_window_percent": 95,
        "experimental_supported_tools": [],
        "input_modalities": ["text"],
        "max_context_window": 12800,
        "priority": 1000,
        "service_tiers": [],
        "shell_type": "shell_command",
        "slug": TARGET_MODEL,
        "support_verbosity": False,
        "supported_in_api": True,
        "supported_reasoning_levels": [
            {"description": "Disable Thinking", "effort": "none"},
            {"description": "Enabled Thinking", "effort": "high"},
        ],
        "supports_image_detail_original": False,
        "supports_parallel_tool_calls": False,
        "supports_reasoning_summaries": True,
        "supports_search_tool": False,
        "truncation_policy": {"limit": 10000, "mode": "bytes"},
        "upgrade": None,
        "visibility": "list",
    }


def update_catalog(document: object) -> tuple[dict, str]:
    if not isinstance(document, dict):
        raise RuntimeError("模型目录必须是 JSON 对象")
    models = document.get("models")
    if not isinstance(models, list):
        raise RuntimeError("模型目录 models 不是数组")
    original = json.loads(json.dumps(models, ensure_ascii=False))
    matches = [
        index for index, item in enumerate(models)
        if isinstance(item, dict) and item.get("display_name") in {DISPLAY_NAME, CATALOG_DISPLAY_NAME}
    ]
    if len(matches) > 1:
        raise RuntimeError("模型目录中发现多个 5.5 条目，已停止")
    if matches:
        replacement = dict(models[matches[0]])
        old_slug = replacement.get("slug")
        replacement["slug"] = TARGET_MODEL
        models[matches[0]] = replacement
        action = "保持" if old_slug == TARGET_MODEL else "替换"
    else:
        models.append(target_catalog_entry())
        action = "新增"

    before_other = [
        item for item in original
        if not (isinstance(item, dict) and item.get("display_name") in {DISPLAY_NAME, CATALOG_DISPLAY_NAME})
    ]
    after_other = [
        item for item in models
        if not (isinstance(item, dict) and item.get("display_name") in {DISPLAY_NAME, CATALOG_DISPLAY_NAME})
    ]
    if before_other != after_other:
        raise RuntimeError("安全检查失败：检测到 5.5 以外的模型发生变化")
    return document, action


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def cc_switch_running() -> bool:
    if sys.platform != "win32":
        return False
    completed = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq cc-switch.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return "cc-switch.exe" in completed.stdout.lower()


def main() -> int:
    home = Path.home()
    default_db = home / ".cc-switch" / "cc-switch.db"
    default_catalog = home / ".codex" / CATALOG_FILENAME
    default_live = home / ".codex" / "config.toml"
    parser = argparse.ArgumentParser(
        description=f"只把 CC Switch 中显示名 {DISPLAY_NAME} 映射到上游 {TARGET_MODEL}"
    )
    parser.add_argument("--db", type=Path, default=default_db)
    parser.add_argument("--catalog", type=Path, default=default_catalog)
    parser.add_argument("--live-config", type=Path, default=default_live)
    parser.add_argument("--provider-id", help="Codex provider ID；省略时使用唯一当前项")
    parser.add_argument("--dry-run", action="store_true", help="只检查并预览，不写文件")
    args = parser.parse_args()

    db = args.db.expanduser().resolve()
    catalog_path = args.catalog.expanduser().resolve()
    live_path = args.live_config.expanduser().resolve()
    if not db.is_file():
        raise RuntimeError(f"数据库不存在：{db}")
    if db != default_db.resolve() and (
        catalog_path == default_catalog.resolve() or live_path == default_live.resolve()
    ):
        raise RuntimeError("使用测试数据库时必须同时显式传入 --catalog 和 --live-config")
    if not live_path.is_file():
        raise RuntimeError(f"Codex 实时配置不存在：{live_path}")

    catalog_original = (
        json.loads(catalog_path.read_text(encoding="utf-8-sig"))
        if catalog_path.is_file() else {"models": []}
    )
    catalog_updated, catalog_action = update_catalog(
        json.loads(json.dumps(catalog_original, ensure_ascii=False))
    )
    live_original = live_path.read_text(encoding="utf-8-sig")
    live_updated, live_action = set_catalog_pointer(live_original)
    if without_pointer(live_original) != without_pointer(live_updated):
        raise RuntimeError("安全检查失败：实时配置除 model_catalog_json 外发生变化")

    connection = sqlite3.connect(str(db))
    connection.row_factory = sqlite3.Row
    try:
        provider = choose_provider(connection, args.provider_id)
        all_before = {
            row["id"]: row["settings_config"] for row in connection.execute(
                "SELECT id, settings_config FROM providers WHERE app_type = 'codex'"
            )
        }
        settings = json.loads(provider["settings_config"])
        if not isinstance(settings, dict) or not isinstance(settings.get("config"), str):
            raise RuntimeError("当前 provider 的 settings_config.config 不是 TOML 文本")
        provider_config_original = settings["config"]
        provider_config_updated, provider_action = set_catalog_pointer(provider_config_original)
        if without_pointer(provider_config_original) != without_pointer(provider_config_updated):
            raise RuntimeError("安全检查失败：provider config 除 model_catalog_json 外发生变化")
        updated_settings = dict(settings)
        updated_settings["config"] = provider_config_updated
        provider_changed = provider_config_updated != provider_config_original

        print(f"provider: {provider['name']} ({provider['id']})")
        print(f"preview: {DISPLAY_NAME} -> {TARGET_MODEL} ({catalog_action})")
        print(f"provider pointer: {provider_action}; live pointer: {live_action}")
        print(f"catalog: {catalog_path}")
        print("scope: only 5.5 catalog slug and model_catalog_json pointer; other models and providers unchanged")
        if args.dry_run:
            print("dry-run: 未修改数据库或配置文件")
            return 0
        if db == default_db.resolve() and cc_switch_running():
            raise RuntimeError("CC Switch 仍在运行；请完全退出（包括托盘）后再执行")

        backup_dir = db.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        db_backup = backup_dir / f"cc-switch.before-model-map.{stamp}.db"
        catalog_backup = backup_dir / f"cc-switch.before-model-map.{stamp}.catalog.json"
        live_backup = backup_dir / f"cc-switch.before-model-map.{stamp}.config.toml"
        shutil.copy2(db, db_backup)
        if catalog_path.is_file():
            shutil.copy2(catalog_path, catalog_backup)
        shutil.copy2(live_path, live_backup)

        catalog_text = json.dumps(catalog_updated, ensure_ascii=False, indent=2) + "\n"
        try:
            atomic_text(catalog_path, catalog_text)
            atomic_text(live_path, live_updated)
            payload = json.dumps(updated_settings, ensure_ascii=False, separators=(",", ":"))
            connection.execute("BEGIN IMMEDIATE")
            if provider_changed:
                connection.execute(
                    "UPDATE providers SET settings_config = ? WHERE id = ? AND app_type = 'codex'",
                    (payload, provider["id"]),
                )
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"数据库完整性检查失败：{integrity}")
            connection.commit()
        except Exception:
            connection.rollback()
            if catalog_backup.is_file():
                shutil.copy2(catalog_backup, catalog_path)
            elif catalog_path.exists():
                catalog_path.unlink()
            shutil.copy2(live_backup, live_path)
            raise

        all_after = {
            row["id"]: row["settings_config"] for row in connection.execute(
                "SELECT id, settings_config FROM providers WHERE app_type = 'codex'"
            )
        }
        changed_provider_ids = [
            provider_id for provider_id in all_before if all_before[provider_id] != all_after[provider_id]
        ]
        expected_provider_ids = [provider["id"]] if provider_changed else []
        if changed_provider_ids != expected_provider_ids:
            raise RuntimeError(f"安全检查失败：provider 变化范围异常：{changed_provider_ids}")
        saved = json.loads(all_after[provider["id"]])
        saved_without_config = dict(saved)
        original_without_config = dict(settings)
        saved_without_config.pop("config", None)
        original_without_config.pop("config", None)
        if saved_without_config != original_without_config:
            raise RuntimeError("安全检查失败：当前 provider 的非 config 字段发生变化")
        if without_pointer(saved["config"]) != without_pointer(provider_config_original):
            raise RuntimeError("安全检查失败：当前 provider 的其他 config 内容发生变化")

        print(f"backup database: {db_backup}")
        print(f"backup catalog: {catalog_backup if catalog_backup.is_file() else '原目录不存在'}")
        print(f"backup live config: {live_backup}")
        print("verified: only 5.5 mapping changed; all other models/providers/config fields unchanged")
        print("integrity_check: ok")
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
