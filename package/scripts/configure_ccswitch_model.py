#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SOURCE_MODEL = "gpt-5.5"
TARGET_MODEL = "deepseek-v4-pro"
FEATURE_MARKER = b"cc-switch-local-proxy-exact-model-routes-v1"


def choose_provider(connection: sqlite3.Connection, provider_id: str | None) -> sqlite3.Row:
    connection.row_factory = sqlite3.Row
    if provider_id:
        row = connection.execute(
            "SELECT * FROM providers WHERE id = ? AND app_type = 'codex'",
            (provider_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"未找到 Codex provider：{provider_id}")
        return row

    rows = connection.execute(
        "SELECT * FROM providers WHERE app_type = 'codex' AND is_current = 1"
    ).fetchall()
    if len(rows) != 1:
        raise RuntimeError("无法唯一确定当前 Codex provider，请使用 --provider-id 明确指定")
    return rows[0]


def parse_object(raw: str | None, label: str) -> dict:
    value = json.loads(raw) if raw else {}
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} 不是 JSON 对象")
    return value


def updated_meta(meta: dict) -> tuple[dict, str]:
    result = json.loads(json.dumps(meta, ensure_ascii=False))
    overrides = result.get("localProxyRequestOverrides")
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise RuntimeError("localProxyRequestOverrides 不是 JSON 对象")
    routes = overrides.get("modelRoutes")
    if routes is None:
        routes = {}
    if not isinstance(routes, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in routes.items()
    ):
        raise RuntimeError("modelRoutes 必须是字符串到字符串的映射")

    previous = routes.get(SOURCE_MODEL)
    new_routes = dict(routes)
    new_routes[SOURCE_MODEL] = TARGET_MODEL
    new_overrides = dict(overrides)
    new_overrides["modelRoutes"] = new_routes
    result["localProxyRequestOverrides"] = new_overrides
    action = "保持" if previous == TARGET_MODEL else ("替换" if previous else "新增")
    return result, action


def cc_switch_running() -> bool:
    if sys.platform != "win32":
        return False
    completed = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq cc-switch.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return "cc-switch.exe" in completed.stdout.lower()


def verify_binary(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"CC Switch 程序不存在：{path}")
    with path.open("rb") as stream:
        if FEATURE_MARKER not in stream.read():
            raise RuntimeError(
                "当前 CC Switch 不支持精确本地模型路由；请先安装工具包内置版本，"
                "禁止退回 model_catalog_json 或无条件 body 覆盖"
            )


def snapshot_rows(connection: sqlite3.Connection) -> dict[tuple[str, str], tuple]:
    columns = [row[1] for row in connection.execute("PRAGMA table_info(providers)")]
    return {
        (row[columns.index("id")], row[columns.index("app_type")]): tuple(row)
        for row in connection.execute(f"SELECT {','.join(columns)} FROM providers")
    }


def main() -> int:
    home = Path.home()
    default_db = home / ".cc-switch" / "cc-switch.db"
    default_exe = home / "AppData" / "Local" / "Programs" / "CC Switch" / "cc-switch.exe"
    parser = argparse.ArgumentParser(
        description=(
            "只在 CC Switch 内部本地代理中精确路由 "
            f"{SOURCE_MODEL} -> {TARGET_MODEL}"
        )
    )
    parser.add_argument("--db", type=Path, default=default_db)
    parser.add_argument("--cc-switch-exe", type=Path, default=default_exe)
    parser.add_argument("--provider-id", help="Codex provider ID；省略时使用唯一当前项")
    parser.add_argument("--dry-run", action="store_true", help="只检查并预览，不写数据库")
    parser.add_argument(
        "--skip-binary-check",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    db = args.db.expanduser().resolve()
    exe = args.cc_switch_exe.expanduser().resolve()
    if not db.is_file():
        raise RuntimeError(f"数据库不存在：{db}")
    if not args.skip_binary_check:
        verify_binary(exe)

    connection = sqlite3.connect(str(db))
    connection.row_factory = sqlite3.Row
    try:
        integrity_before = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity_before != "ok":
            raise RuntimeError(f"数据库完整性检查失败：{integrity_before}")

        provider = choose_provider(connection, args.provider_id)
        meta_original = parse_object(provider["meta"], "provider meta")
        meta_next, action = updated_meta(meta_original)
        changed = meta_next != meta_original
        rows_before = snapshot_rows(connection)
        settings_before = provider["settings_config"]

        print(f"provider: {provider['name']} ({provider['id']})")
        print(f"preview: {SOURCE_MODEL} -> {TARGET_MODEL} ({action})")
        print("storage: CC Switch provider.meta.localProxyRequestOverrides.modelRoutes")
        print("scope: exact source-model match only; other routes, providers, API key and base_url unchanged")
        print("forbidden: no model_catalog_json, no Codex model catalog, no external proxy")
        if args.dry_run:
            print("dry-run: 未修改数据库或任何 Codex 配置文件")
            return 0

        running = db == default_db.resolve() and cc_switch_running()
        if running:
            print("runtime: CC Switch 正在运行；使用 SQLite 单事务在线更新，不停止当前 Codex 连接")

        backup_dir = db.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = backup_dir / f"cc-switch.before-local-route.{stamp}.db"
        shutil.copy2(db, backup)

        try:
            connection.execute("BEGIN IMMEDIATE")
            if changed:
                connection.execute(
                    "UPDATE providers SET meta = ? WHERE id = ? AND app_type = 'codex'",
                    (
                        json.dumps(meta_next, ensure_ascii=False, separators=(",", ":")),
                        provider["id"],
                    ),
                )
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"数据库完整性检查失败：{integrity}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

        rows_after = snapshot_rows(connection)
        if set(rows_before) != set(rows_after):
            raise RuntimeError("安全检查失败：provider 集合发生变化")
        target_key = (provider["id"], "codex")
        changed_keys = [key for key in rows_before if rows_before[key] != rows_after[key]]
        expected_keys = [target_key] if changed else []
        if changed_keys != expected_keys:
            raise RuntimeError(f"安全检查失败：provider 变化范围异常：{changed_keys}")

        saved = choose_provider(connection, provider["id"])
        if saved["settings_config"] != settings_before:
            raise RuntimeError("安全检查失败：API Key、base_url 或 provider config 发生变化")
        saved_meta = parse_object(saved["meta"], "保存后的 provider meta")
        expected_without_route = json.loads(json.dumps(meta_original, ensure_ascii=False))
        actual_without_route = json.loads(json.dumps(saved_meta, ensure_ascii=False))
        for document in (expected_without_route, actual_without_route):
            overrides = document.get("localProxyRequestOverrides")
            if isinstance(overrides, dict):
                overrides.pop("modelRoutes", None)
                if not overrides:
                    document.pop("localProxyRequestOverrides", None)
        if expected_without_route != actual_without_route:
            raise RuntimeError("安全检查失败：5.5 精确路由以外的 provider meta 发生变化")
        routes = saved_meta["localProxyRequestOverrides"]["modelRoutes"]
        if routes.get(SOURCE_MODEL) != TARGET_MODEL:
            raise RuntimeError("保存后校验失败：精确路由不存在")

        print(f"backup database: {backup}")
        print("verified: only exact gpt-5.5 local route changed")
        print("verified unchanged: gpt-5.5-mini, all 5.6 models, other routes/providers, API key, base_url")
        print("integrity_check: ok")
        if running:
            print("activation: 若刚替换 CC Switch 程序，请在当前工作结束后重启一次 CC Switch")
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
