#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

ENVIRONMENT_HOSTS = {
    "test": "chat-test.q1.com",
    "production": "chat.q1.com",
}
ENVIRONMENT_LABELS = {"test": "test版", "production": "正式版"}
BALANCE_MARKERS = (
    "余额不足", "额度不足", "余额已用完", "insufficient balance",
    "insufficient credit", "quota exhausted", "credit exhausted",
    "billing quota", "out of credits", "no balance",
)


class BalanceExhaustedError(RuntimeError):
    pass


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    os.replace(temporary, path)


def pool_paths(project: Path) -> dict[str, Path]:
    root = project.resolve()
    return {
        "pool": root / "apis" / "api_pool",
        "index": root / "apis" / "api_pool" / "index.json",
        "active": root / "apis" / "doubao_api_config.json",
        "state": root / ".codex" / "04_API池状态.json",
        "document": root / ".codex" / "04_API池与余额切换.md",
        "chats": root / ".codex" / "03_codexchat对应表.json",
    }


def environment_from_url(url: str) -> str | None:
    lowered = url.lower()
    if ENVIRONMENT_HOSTS["test"] in lowered:
        return "test"
    if ENVIRONMENT_HOSTS["production"] in lowered:
        return "production"
    return None


def normalize_base_url(url: str, environment: str) -> str:
    expected = ENVIRONMENT_HOSTS[environment]
    match = re.fullmatch(r"https?://([^/]+)(?:/v1)?/?", url.strip(), re.IGNORECASE)
    if not match or match.group(1).lower() != expected:
        raise ValueError(f"线路与地址不匹配：{environment} / {url}")
    return f"https://{expected}/v1"


def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return value[:40] or "provider"


def sanitize_error(value: str) -> str:
    value = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._-]+", "Bearer <REDACTED>", value)
    value = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "<REDACTED>", value)
    return value[:500]


def is_balance_error(value: str, status: int | None = None) -> bool:
    lowered = value.lower()
    return status == 402 or any(marker in lowered for marker in BALANCE_MARKERS)


def raise_if_balance_error(value: str, status: int | None = None) -> None:
    if is_balance_error(value, status):
        raise BalanceExhaustedError(sanitize_error(value))


def discover_ccswitch(db: Path, environment: str) -> list[dict[str, str]]:
    connection = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT p.id, p.name, p.settings_config, p.is_current, e.url "
            "FROM providers p LEFT JOIN provider_endpoints e "
            "ON e.provider_id = p.id AND e.app_type = p.app_type "
            "WHERE p.app_type = 'codex' ORDER BY p.is_current DESC, p.sort_index, p.name"
        ).fetchall()
    finally:
        connection.close()

    discovered: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        try:
            settings = json.loads(row["settings_config"])
        except (TypeError, json.JSONDecodeError):
            continue
        api_key = str(settings.get("auth", {}).get("OPENAI_API_KEY") or "").strip()
        endpoint = str(row["url"] or "").strip()
        if not api_key or environment_from_url(endpoint) != environment:
            continue
        base_url = normalize_base_url(endpoint, environment)
        fingerprint = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
        identity = (base_url, fingerprint)
        if identity in seen:
            continue
        seen.add(identity)
        discovered.append({
            "provider_id": str(row["id"]),
            "provider_name": str(row["name"]),
            "api_key": api_key,
            "base_url": base_url,
            "fingerprint": fingerprint,
            "is_current": bool(row["is_current"]),
        })
    return discovered


def default_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "workflow_paused": False,
        "pause_reason": None,
        "notify_chat": "理解文本与任务",
        "source_chat": None,
        "affected_task_ids": [],
        "resubmit_required": False,
        "next_api_activated": False,
        "active_config_id": None,
        "event_history": [],
        "updated_at": None,
    }


def render_hidden_document(project: Path, index: dict[str, Any], state: dict[str, Any]) -> None:
    paths = pool_paths(project)
    configs = index.get("configs", [])
    lines = [
        "# API 池与余额切换",
        "",
        "本文件由自动化程序维护，不包含 API Key。不要手工修改机器状态 JSON。",
        "",
        f"- 当前线路：{ENVIRONMENT_LABELS.get(index.get('environment'), '未配置')}",
        f"- 配置总数：{len(configs)}",
        f"- 当前配置：{index.get('active_id') or '无'}",
        f"- 工作流暂停：{'是' if state.get('workflow_paused') else '否'}",
        f"- 暂停原因：{state.get('pause_reason') or '无'}",
        f"- 需要重新提交：{'是' if state.get('resubmit_required') else '否'}",
        f"- 待通知Chat：{(state.get('pending_notification') or {}).get('chat') or '无'}",
        f"- 待通知thread ID：{(state.get('pending_notification') or {}).get('thread_id') or '无'}",
        "",
        "## 配置索引",
        "",
    ]
    for item in configs:
        lines.append(
            f"- {item['id']} | {item['provider_name']} | {item['status']} | {item['base_url']}"
        )
    lines.extend([
        "",
        "## 余额不足协议",
        "",
        "任何 Chat 发现明确余额不足时必须立即停止，不得继续提交；运行 balance-exhausted，",
        "把所有 Chat 状态清零，只唤醒“理解文本与任务”。有下一份 API 时程序自动切换，",
        "由“理解文本与任务”执行 resume-after-balance 后，使用原任务参数且不加 force 重新提交。",
        "已有远端 ID 的版本不得重复提交。",
        "",
    ])
    paths["document"].write_text("\n".join(lines), encoding="utf-8")


def initialize_project_state(project: Path) -> None:
    paths = pool_paths(project)
    if not paths["state"].exists():
        write_json(paths["state"], default_state())
    if not paths["index"].exists():
        write_json(paths["index"], {
            "schema_version": 1, "environment": None, "active_id": None,
            "configs": [], "updated_at": None,
        })
    protocol = (
        "【API余额协议】每次操作前读取 .codex\\04_API池状态.json。"
        "发现明确余额不足时立即运行 manage_api_pool.py balance-exhausted，停止全部常规流程，"
        "并把程序返回的紧急消息发送给‘理解文本与任务’Chat；恢复前不得继续。"
    )
    if paths["chats"].exists():
        chats = read_json(paths["chats"], {})
        changed = False
        for chat in chats.get("chats", {}).values():
            prompt = str(chat.get("prompt") or "")
            if "【API余额协议】" not in prompt:
                chat["prompt"] = prompt + protocol
                changed = True
            prompt_file = Path(str(chat.get("prompt_file") or ""))
            if prompt_file.is_file():
                content = prompt_file.read_text(encoding="utf-8-sig")
                if "【API余额协议】" not in content:
                    prompt_file.write_text(content.rstrip() + "\n\n" + protocol + "\n", encoding="utf-8")
        if changed:
            chats["updated_at"] = now()
            write_json(paths["chats"], chats)
    render_hidden_document(project, read_json(paths["index"], {}), read_json(paths["state"], default_state()))


def activate_config(project: Path, index: dict[str, Any], config_id: str) -> dict[str, Any]:
    paths = pool_paths(project)
    entry = next((item for item in index.get("configs", []) if item.get("id") == config_id), None)
    if not entry:
        raise ValueError(f"API 配置不存在：{config_id}")
    source = Path(entry["config_path"])
    config = read_json(source)
    if not config or not all(config.get(key) for key in ("api_key", "base_url", "model")):
        raise ValueError(f"API 配置无效：{source}")
    shutil.copy2(source, paths["active"])
    index["active_id"] = config_id
    index["updated_at"] = now()
    write_json(paths["index"], index)
    return entry


def import_pool(project: Path, db: Path, environment: str) -> dict[str, Any]:
    initialize_project_state(project)
    paths = pool_paths(project)
    found = discover_ccswitch(db, environment)
    if not found:
        raise RuntimeError(f"CC Switch 中没有可用的{ENVIRONMENT_LABELS[environment]} Codex provider")
    old_index = read_json(paths["index"], {}) or {}
    old_status = {
        (item.get("provider_id"), item.get("fingerprint")): item.get("status", "available")
        for item in old_index.get("configs", [])
    }
    environment_dir = paths["pool"] / environment
    environment_dir.mkdir(parents=True, exist_ok=True)
    existing_files = set(environment_dir.glob("*.json"))
    generated_files: set[Path] = set()
    configs: list[dict[str, Any]] = []
    for number, item in enumerate(found, 1):
        config_id = f"{environment}-{number:02d}-{item['fingerprint']}"
        destination = environment_dir / f"{number:02d}_{safe_name(item['provider_name'])}_{item['provider_id'][:8]}.json"
        write_json(destination, {
            "api_key": item["api_key"], "base_url": item["base_url"],
            "model": "doubao-seedance-2.0",
        })
        generated_files.add(destination)
        configs.append({
            "id": config_id,
            "provider_id": item["provider_id"],
            "provider_name": item["provider_name"],
            "base_url": item["base_url"],
            "fingerprint": item["fingerprint"],
            "config_path": str(destination.resolve()),
            "status": old_status.get((item["provider_id"], item["fingerprint"]), "available"),
            "is_current_provider": item["is_current"],
        })
    stale_files = sorted(existing_files - generated_files, key=lambda path: path.name)
    if stale_files:
        archive = paths["pool"] / "_archive" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        archive.mkdir(parents=True, exist_ok=True)
        for stale in stale_files:
            shutil.move(str(stale), archive / stale.name)
    index = {
        "schema_version": 1,
        "environment": environment,
        "source": "CC Switch providers database",
        "active_id": None,
        "configs": configs,
        "updated_at": now(),
    }
    available = [item for item in configs if item["status"] == "available"]
    if not available:
        write_json(paths["index"], index)
        raise RuntimeError(
            f"{ENVIRONMENT_LABELS[environment]}中的API都已标记为余额不足；"
            "请先在CC Switch新增或更换API，再重新导入"
        )
    preferred = next((item for item in available if item["is_current_provider"]), available[0])
    activate_config(project, index, preferred["id"])
    state = read_json(paths["state"], default_state())
    if state.get("workflow_paused") and state.get("resubmit_required"):
        state.update({
            "next_api_activated": True,
            "active_config_id": preferred["id"], "updated_at": now(),
        })
    else:
        state.update({
            "workflow_paused": False, "pause_reason": None,
            "resubmit_required": False, "next_api_activated": False,
            "active_config_id": preferred["id"], "updated_at": now(),
        })
    write_json(paths["state"], state)
    render_hidden_document(project, index, state)
    return {
        "environment": environment,
        "environment_label": ENVIRONMENT_LABELS[environment],
        "config_count": len(configs),
        "active_id": preferred["id"],
        "active_provider": preferred["provider_name"],
        "active_config": str(paths["active"]),
        "api_keys_printed": False,
    }


def save_manual_keys(
    project: Path,
    environment: str,
    api_keys: list[str],
    active_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Replace one environment's pool from locally entered keys without exposing secrets."""
    if environment not in ENVIRONMENT_HOSTS:
        raise ValueError(f"未知 API 线路：{environment}")
    initialize_project_state(project)
    paths = pool_paths(project)
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_key in api_keys:
        api_key = str(raw_key).strip()
        if not api_key:
            continue
        fingerprint = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append((api_key, fingerprint))
    if not unique:
        raise ValueError("至少添加一份 API Key")

    old_index = read_json(paths["index"], {}) or {}
    old_status = {
        item.get("fingerprint"): item.get("status", "available")
        for item in old_index.get("configs", [])
        if item.get("fingerprint")
    }
    environment_dir = paths["pool"] / environment
    environment_dir.mkdir(parents=True, exist_ok=True)
    existing_files = set(environment_dir.glob("*.json"))
    generated_files: set[Path] = set()
    configs: list[dict[str, Any]] = []
    base_url = f"https://{ENVIRONMENT_HOSTS[environment]}/v1"
    for number, (api_key, fingerprint) in enumerate(unique, 1):
        config_id = f"{environment}-{number:02d}-{fingerprint}"
        destination = environment_dir / f"{number:02d}_manual_{fingerprint[-4:]}.json"
        write_json(destination, {
            "api_key": api_key,
            "base_url": base_url,
            "model": "doubao-seedance-2.0",
        })
        generated_files.add(destination)
        configs.append({
            "id": config_id,
            "provider_id": f"manual-{fingerprint}",
            "provider_name": f"手动 API {number:02d}",
            "base_url": base_url,
            "fingerprint": fingerprint,
            "config_path": str(destination.resolve()),
            "status": old_status.get(fingerprint, "available"),
            "is_current_provider": fingerprint == active_fingerprint,
        })

    stale_files = sorted(existing_files - generated_files, key=lambda path: path.name)
    if stale_files:
        archive = paths["pool"] / "_archive" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        archive.mkdir(parents=True, exist_ok=True)
        for stale in stale_files:
            shutil.move(str(stale), archive / stale.name)

    index = {
        "schema_version": 1,
        "environment": environment,
        "source": "local API configuration tool",
        "active_id": None,
        "configs": configs,
        "updated_at": now(),
    }
    available = [item for item in configs if item["status"] == "available"]
    if not available:
        write_json(paths["index"], index)
        raise RuntimeError("所有 API 都已标记为余额不足，请添加新的 API")
    preferred = next(
        (item for item in available if item["fingerprint"] == active_fingerprint),
        available[0],
    )
    activate_config(project, index, preferred["id"])
    state = read_json(paths["state"], default_state())
    if state.get("workflow_paused") and state.get("resubmit_required"):
        state.update({
            "next_api_activated": True,
            "active_config_id": preferred["id"],
            "updated_at": now(),
        })
    else:
        state.update({
            "workflow_paused": False,
            "pause_reason": None,
            "resubmit_required": False,
            "next_api_activated": False,
            "active_config_id": preferred["id"],
            "updated_at": now(),
        })
    write_json(paths["state"], state)
    render_hidden_document(project, index, state)
    return {
        "environment": environment,
        "environment_label": ENVIRONMENT_LABELS[environment],
        "config_count": len(configs),
        "active_id": preferred["id"],
        "active_fingerprint": preferred["fingerprint"],
        "active_config": str(paths["active"]),
        "api_keys_printed": False,
    }


def ensure_not_paused(project: Path) -> None:
    state = read_json(pool_paths(project)["state"], default_state())
    if state.get("workflow_paused"):
        raise RuntimeError(
            "API 工作流已暂停：" + str(state.get("pause_reason") or "未知原因") +
            "；只能交给“理解文本与任务”处理"
        )


def signal_balance_exhausted(project: Path, source_chat: str, task_ids: list[str], error: str) -> dict[str, Any]:
    initialize_project_state(project)
    paths = pool_paths(project)
    index = read_json(paths["index"], {})
    state = read_json(paths["state"], default_state())
    active_id = index.get("active_id")
    for item in index.get("configs", []):
        if item.get("id") == active_id:
            item["status"] = "exhausted"
            item["exhausted_at"] = now()
    next_entry = next((item for item in index.get("configs", []) if item.get("status") == "available"), None)
    if next_entry:
        activate_config(project, index, next_entry["id"])
        index = read_json(paths["index"], index)
    else:
        index["updated_at"] = now()
        write_json(paths["index"], index)

    event = {
        "time": now(), "type": "balance_exhausted", "source_chat": source_chat,
        "task_ids": sorted(set(task_ids)), "old_config_id": active_id,
        "next_config_id": next_entry["id"] if next_entry else None,
        "error": sanitize_error(error),
    }
    state.update({
        "workflow_paused": True,
        "pause_reason": "Seedance API 余额不足",
        "source_chat": source_chat,
        "affected_task_ids": sorted(set(task_ids)),
        "resubmit_required": True,
        "next_api_activated": bool(next_entry),
        "active_config_id": next_entry["id"] if next_entry else None,
        "updated_at": now(),
    })
    state.setdefault("event_history", []).append(event)
    write_json(paths["state"], state)

    notify_thread_id = None
    if paths["chats"].exists():
        chats = read_json(paths["chats"], {})
        for name, chat in chats.get("chats", {}).items():
            chat["status"] = 1 if name == "理解文本与任务" else 0
        owner = chats.get("chats", {}).get("理解文本与任务", {})
        notify_thread_id = owner.get("thread_id")
        chats.setdefault("handoff_history", []).append({
            "time": now(), "from": source_chat, "to": "理解文本与任务",
            "task_ID": ",".join(sorted(set(task_ids))) or None,
            "summary": "检测到 Seedance API 余额不足，已暂停所有流程并尝试切换下一份 API",
            "emergency": True,
        })
        chats["updated_at"] = now()
        write_json(paths["chats"], chats)

    message = (
        "检测到 Seedance API 余额不足，所有配音 Chat 流程已暂停。"
        + (f"已自动切换到 {next_entry['id']}。" if next_entry else "API 池没有下一份可用配置，请先导入新 API。")
        + "请由“理解文本与任务”恢复流程，只重新提交没有远端 ID 的版本，禁止 force-regenerate。"
    )
    state["pending_notification"] = {
        "chat": "理解文本与任务",
        "thread_id": notify_thread_id,
        "message": message,
        "created_at": now(),
    }
    write_json(paths["state"], state)
    render_hidden_document(project, index, state)
    return {
        "paused": True,
        "notify_chat": "理解文本与任务",
        "notify_thread_id": notify_thread_id,
        "message": message,
        "next_api_activated": bool(next_entry),
        "next_config_id": next_entry["id"] if next_entry else None,
        "affected_task_ids": sorted(set(task_ids)),
    }


def resume_after_balance(project: Path) -> dict[str, Any]:
    paths = pool_paths(project)
    index = read_json(paths["index"], {})
    state = read_json(paths["state"], default_state())
    active = next((item for item in index.get("configs", []) if item.get("id") == index.get("active_id")), None)
    if not active or active.get("status") != "available":
        raise RuntimeError("没有可用的新 API；先重新运行 import 导入或整理 API")
    task_ids = list(state.get("affected_task_ids") or [])
    state.update({
        "workflow_paused": False, "pause_reason": None,
        "resubmit_required": False, "next_api_activated": True,
        "active_config_id": active["id"], "updated_at": now(),
        "pending_notification": None,
    })
    state.setdefault("event_history", []).append({
        "time": now(), "type": "resume_after_balance",
        "active_config_id": active["id"], "task_ids": task_ids,
    })
    write_json(paths["state"], state)
    render_hidden_document(project, index, state)
    return {
        "resumed": True, "active_config_id": active["id"],
        "affected_task_ids": task_ids,
        "instruction": "使用原任务参数重新运行提交；不得使用 --force-regenerate，已有远端 ID 会自动跳过",
    }


def choose_environment() -> str:
    print("请选择 Seedance API 线路：")
    print("1. test版（https://chat-test.q1.com/v1）")
    print("2. 正式版（https://chat.q1.com/v1）")
    choice = input("输入 1 或 2：").strip()
    if choice == "1":
        return "test"
    if choice == "2":
        return "production"
    raise ValueError("只能输入 1 或 2")


def main() -> int:
    parser = argparse.ArgumentParser(description="管理 Seedance API 池、线路选择和余额不足切换")
    parser.add_argument("--project-root", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)

    import_cmd = sub.add_parser("import")
    import_cmd.add_argument("--environment", choices=("test", "production"))
    import_cmd.add_argument("--ccswitch-db", type=Path, default=Path.home() / ".cc-switch" / "cc-switch.db")

    balance = sub.add_parser("balance-exhausted")
    balance.add_argument("--source-chat", required=True)
    balance.add_argument("--task-id", action="append", default=[])
    balance.add_argument("--error", required=True)

    sub.add_parser("resume-after-balance")
    sub.add_parser("show")
    args = parser.parse_args()
    project = args.project_root.resolve()

    if args.command == "import":
        environment = args.environment or choose_environment()
        result = import_pool(project, args.ccswitch_db, environment)
    elif args.command == "balance-exhausted":
        result = signal_balance_exhausted(project, args.source_chat, args.task_id, args.error)
    elif args.command == "resume-after-balance":
        result = resume_after_balance(project)
    else:
        paths = pool_paths(project)
        result = {
            "index": read_json(paths["index"], {}),
            "state": read_json(paths["state"], default_state()),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
