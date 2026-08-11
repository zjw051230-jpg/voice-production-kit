#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def table_path(project: Path) -> Path:
    return project.resolve() / ".codex" / "03_codexchat对应表.json"


def api_state_path(project: Path) -> Path:
    return project.resolve() / ".codex" / "04_API池状态.json"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    os.replace(temporary, path)


def mutate(path: Path, action: Callable[[dict[str, Any]], Any]) -> Any:
    lock = path.with_suffix(path.suffix + ".lock")
    deadline = time.monotonic() + 15
    descriptor = None
    while descriptor is None:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"工作流映射被其他Chat占用：{lock}")
            time.sleep(0.2)
    try:
        data = load(path)
        result = action(data)
        data["updated_at"] = now()
        write(path, data)
        return result
    finally:
        os.close(descriptor)
        lock.unlink(missing_ok=True)


def get_chat(data: dict[str, Any], name: str) -> dict[str, Any]:
    chat = data.get("chats", {}).get(name)
    if not isinstance(chat, dict):
        raise ValueError(f"未知Chat：{name}")
    return chat


def main() -> int:
    parser = argparse.ArgumentParser(description="原子管理多Chat配音工作流")
    parser.add_argument("--project-root", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)

    register = sub.add_parser("register")
    register.add_argument("--chat", required=True)
    register.add_argument("--thread-id", required=True)
    register.add_argument("--host-id", default="local")
    register.add_argument("--full-access-verified", choices=("true", "false"), default="false")

    status = sub.add_parser("set-status")
    status.add_argument("--chat", required=True)
    status.add_argument("--status", required=True, type=int, choices=(0, 1))

    handoff = sub.add_parser("prepare-handoff")
    handoff.add_argument("--from-chat", required=True)
    handoff.add_argument("--to-chat", required=True)
    handoff.add_argument("--task-id", default="")
    handoff.add_argument("--summary", required=True)

    complete = sub.add_parser("complete")
    complete.add_argument("--chat", required=True)

    sub.add_parser("show")
    sub.add_parser("check-pause")
    args = parser.parse_args()
    path = table_path(args.project_root)

    if args.command == "show":
        print(json.dumps(load(path), ensure_ascii=False, indent=2))
        return 0

    if args.command == "check-pause":
        state_path = api_state_path(args.project_root)
        state = load(state_path) if state_path.exists() else {"workflow_paused": False}
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 3 if state.get("workflow_paused") else 0

    if args.command == "register":
        def action(data: dict[str, Any]) -> dict[str, Any]:
            chat = get_chat(data, args.chat)
            chat["thread_id"] = args.thread_id
            chat["host_id"] = args.host_id
            chat["full_access_verified"] = args.full_access_verified == "true"
            return chat
        result = mutate(path, action)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "set-status":
        def action(data: dict[str, Any]) -> dict[str, Any]:
            chat = get_chat(data, args.chat)
            chat["status"] = args.status
            return {"chat": args.chat, "status": args.status}
        print(json.dumps(mutate(path, action), ensure_ascii=False))
        return 0

    if args.command == "complete":
        def action(data: dict[str, Any]) -> dict[str, Any]:
            chat = get_chat(data, args.chat)
            chat["status"] = 0
            return {"chat": args.chat, "status": 0}
        print(json.dumps(mutate(path, action), ensure_ascii=False))
        return 0

    if args.command == "prepare-handoff":
        def action(data: dict[str, Any]) -> dict[str, Any]:
            source = get_chat(data, args.from_chat)
            target = get_chat(data, args.to_chat)
            state_path = api_state_path(args.project_root)
            api_state = load(state_path) if state_path.exists() else {"workflow_paused": False}
            if api_state.get("workflow_paused"):
                if args.to_chat != "理解文本与任务":
                    return {
                        "ready": False,
                        "paused": True,
                        "reason": api_state.get("pause_reason") or "API工作流已暂停",
                        "required_target": "理解文本与任务",
                    }
                if not target.get("thread_id"):
                    raise ValueError("理解文本与任务Chat尚未登记thread_id")
                return {
                    "ready": True,
                    "emergency": True,
                    "thread_id": target["thread_id"],
                    "host_id": target.get("host_id", "local"),
                    "model": target["model"],
                    "reasoning_effort": target["reasoning_effort"],
                    "message_requirement": "余额不足紧急消息；完成恢复前不得派发其他Chat",
                }
            if target.get("status") == 1:
                retry = int(data.get("busy_retry_minutes", 5))
                return {
                    "ready": False,
                    "to_chat": args.to_chat,
                    "retry_minutes": retry,
                    "retry_after": (datetime.now().astimezone() + timedelta(minutes=retry)).isoformat(timespec="seconds"),
                }
            if not target.get("thread_id"):
                raise ValueError(f"目标Chat尚未登记thread_id：{args.to_chat}")
            if target.get("full_access_required") and not target.get("full_access_verified"):
                raise ValueError(f"目标Chat尚未验证完全访问权限：{args.to_chat}")
            target["status"] = 1
            event = {
                "time": now(), "from": args.from_chat, "to": args.to_chat,
                "task_ID": args.task_id or None, "summary": args.summary,
            }
            data.setdefault("handoff_history", []).append(event)
            return {
                "ready": True,
                "thread_id": target["thread_id"],
                "host_id": target.get("host_id", "local"),
                "model": target["model"],
                "reasoning_effort": target["reasoning_effort"],
                "message_requirement": "消息中提醒：完成后运行complete把自己的status改回0",
            }
        result = mutate(path, action)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ready") else 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
