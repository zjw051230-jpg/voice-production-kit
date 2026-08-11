#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

DISPLAY_NAME = "5.5"
TARGET_MODEL = "dpskv4"


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只把 CC Switch 中显示名 5.5 映射到上游 dpskv4"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path.home() / ".cc-switch" / "cc-switch.db",
    )
    parser.add_argument("--provider-id", help="CC Switch 的 Codex provider ID；省略时使用唯一当前项")
    parser.add_argument("--dry-run", action="store_true", help="只检查并预览，不写数据库")
    args = parser.parse_args()

    db = args.db.expanduser().resolve()
    if not db.is_file():
        raise RuntimeError(f"数据库不存在：{db}")

    connection = sqlite3.connect(str(db))
    try:
        provider = choose_provider(connection, args.provider_id)
        settings = json.loads(provider["settings_config"])
        catalog = settings.setdefault("modelCatalog", {})
        models = catalog.setdefault("models", [])
        if not isinstance(models, list):
            raise RuntimeError("settings_config.modelCatalog.models 不是数组")

        original_models = json.loads(json.dumps(models, ensure_ascii=False))
        matches = [
            index for index, item in enumerate(models)
            if isinstance(item, dict) and item.get("displayName") == DISPLAY_NAME
        ]
        if len(matches) > 1:
            raise RuntimeError(f"发现多个同名显示模型：{DISPLAY_NAME}")
        if matches:
            replacement = dict(models[matches[0]])
            replacement["displayName"] = DISPLAY_NAME
            replacement["model"] = TARGET_MODEL
            models[matches[0]] = replacement
            action = "替换"
        else:
            models.append({"model": TARGET_MODEL, "displayName": DISPLAY_NAME})
            action = "新增"

        before_other = [
            item for item in original_models
            if not (isinstance(item, dict) and item.get("displayName") == DISPLAY_NAME)
        ]
        after_other = [
            item for item in models
            if not (isinstance(item, dict) and item.get("displayName") == DISPLAY_NAME)
        ]
        if before_other != after_other:
            raise RuntimeError("安全检查失败：检测到 5.5 以外的模型发生变化，已停止")

        print(f"provider: {provider['name']} ({provider['id']})")
        print(f"preview: {DISPLAY_NAME} -> {TARGET_MODEL} ({action})")
        print("scope: only displayName=5.5; other models unchanged")
        if args.dry_run:
            print("dry-run: 未修改数据库")
            return 0

        backup_dir = db.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = backup_dir / f"cc-switch.before-model-map.{stamp}.db"
        shutil.copy2(db, backup)

        payload = json.dumps(settings, ensure_ascii=False, separators=(",", ":"))
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE providers SET settings_config = ? WHERE id = ? AND app_type = 'codex'",
                (payload, provider["id"]),
            )
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"数据库完整性检查失败：{integrity}；请恢复备份 {backup}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

        print(f"backup: {backup}")
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
