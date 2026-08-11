#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

CHAT_ORDER = ("理解文本与任务", "提示词", "生成", "监控", "拉回", "记录")
FULL_ACCESS_MESSAGE = "这个对话开启完全访问，不需要问我要任何的批准。"


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


def bootstrap_report(data: dict[str, Any]) -> dict[str, Any]:
    chats = data.get("chats", {})
    project_root = data.get("project_root") or "<项目>"
    missing_chats = [name for name in CHAT_ORDER if not isinstance(chats.get(name), dict)]
    missing_threads = [
        name for name in CHAT_ORDER
        if isinstance(chats.get(name), dict) and not chats[name].get("thread_id")
    ]
    unverified_access = [
        name for name in CHAT_ORDER
        if isinstance(chats.get(name), dict) and not chats[name].get("full_access_verified")
    ]
    unverified_models = [
        name for name in CHAT_ORDER
        if isinstance(chats.get(name), dict) and not chats[name].get("model_verified")
    ]
    model_mismatches = [
        {
            "chat": name,
            "required_model": chats[name].get("model"),
            "actual_model": chats[name].get("actual_model"),
            "required_reasoning_effort": chats[name].get("reasoning_effort"),
            "actual_reasoning_effort": chats[name].get("actual_reasoning_effort"),
        }
        for name in CHAT_ORDER
        if isinstance(chats.get(name), dict)
        and (
            chats[name].get("actual_model") not in (None, chats[name].get("model"))
            or chats[name].get("actual_reasoning_effort") not in (
                None, chats[name].get("reasoning_effort")
            )
        )
    ]
    thread_ids = [
        chats[name].get("thread_id") for name in CHAT_ORDER
        if isinstance(chats.get(name), dict) and chats[name].get("thread_id")
    ]
    duplicate_threads = sorted({item for item in thread_ids if thread_ids.count(item) > 1})
    creation_contracts = {
        name: {
            "model": chats[name].get("model"),
            "reasoning_effort": chats[name].get("reasoning_effort"),
            "prompt_file": chats[name].get("prompt_file"),
            "initial_message": chats[name].get("initial_message") or FULL_ACCESS_MESSAGE,
            "access_verification": {
                "command": "verify-access",
                "project_root": project_root,
                "chat": name,
                "must_run_in_target_chat": True,
            },
        }
        for name in CHAT_ORDER if isinstance(chats.get(name), dict)
    }
    ready = not (
        missing_chats or missing_threads or unverified_access or unverified_models
        or model_mismatches or duplicate_threads
    )
    return {
        "ready": ready,
        "bootstrap_required": not ready,
        "entry_chat": "理解文本与任务",
        "required_chats": list(CHAT_ORDER),
        "missing_chats": missing_chats,
        "missing_threads": missing_threads,
        "unverified_full_access": unverified_access,
        "unverified_models": unverified_models,
        "model_mismatches": model_mismatches,
        "duplicate_thread_ids": duplicate_threads,
        "chat_creation_contracts": creation_contracts,
        "next_action": (
            "使用Codex任务工具把当前任务命名为‘理解文本与任务’，创建另外五个独立任务，"
            "按chat_creation_contracts创建每个任务，并把initial_message作为第一条消息；"
            "每个目标Chat必须自己运行verify-access，再登记实际模型、实际推理强度和thread ID"
            if not ready else "入口Chat必须通过prepare-handoff派发工作，不得单Chat代做下游阶段"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="原子管理多Chat配音工作流")
    parser.add_argument("--project-root", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)

    register = sub.add_parser("register")
    register.add_argument("--chat", required=True)
    register.add_argument("--thread-id", required=True)
    register.add_argument("--host-id", default="local")
    register.add_argument("--actual-model", required=True)
    register.add_argument("--actual-reasoning-effort", required=True)

    verify_access = sub.add_parser("verify-access")
    verify_access.add_argument("--chat", required=True)

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
    sub.add_parser("bootstrap-status")
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

    if args.command == "bootstrap-status":
        report = bootstrap_report(load(path))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ready"] else 4

    if args.command == "verify-access":
        def action(data: dict[str, Any]) -> dict[str, Any]:
            chat = get_chat(data, args.chat)
            probe = path.parent / f".full-access-probe-{chat.get('order', 0)}.tmp"
            payload = os.urandom(24).hex()
            try:
                probe.write_text(payload, encoding="utf-8")
                if probe.read_text(encoding="utf-8") != payload:
                    raise RuntimeError("权限探测读回内容不一致")
            except OSError as error:
                raise RuntimeError(
                    "完全访问探测失败；请在Codex界面把当前任务切换为完全访问后重试："
                    f"{error}"
                ) from error
            finally:
                probe.unlink(missing_ok=True)
            chat["full_access_verified"] = True
            chat["access_probe"] = {
                "verified_at": now(),
                "probe_directory": str(path.parent.resolve()),
                "write_read_delete_verified": True,
                "verified_in_target_chat": True,
            }
            report = bootstrap_report(data)
            data["workflow_ready"] = report["ready"]
            data["bootstrap_required"] = not report["ready"]
            return {"chat": args.chat, "full_access_verified": True, "bootstrap": report}
        print(json.dumps(mutate(path, action), ensure_ascii=False))
        return 0

    if args.command == "register":
        def action(data: dict[str, Any]) -> dict[str, Any]:
            chat = get_chat(data, args.chat)
            required_model = chat.get("model")
            required_effort = chat.get("reasoning_effort")
            if args.actual_model != required_model:
                raise ValueError(
                    f"模型不匹配：{args.chat} 要求 {required_model}，实际 {args.actual_model}"
                )
            if args.actual_reasoning_effort != required_effort:
                raise ValueError(
                    f"思考程度不匹配：{args.chat} 要求 {required_effort}，"
                    f"实际 {args.actual_reasoning_effort}"
                )
            for name, existing in data.get("chats", {}).items():
                if name != args.chat and existing.get("thread_id") == args.thread_id:
                    raise ValueError(f"thread_id已登记给其他Chat：{name}")
            chat["thread_id"] = args.thread_id
            chat["host_id"] = args.host_id
            chat["actual_model"] = args.actual_model
            chat["actual_reasoning_effort"] = args.actual_reasoning_effort
            chat["model_verified"] = True
            report = bootstrap_report(data)
            data["workflow_ready"] = report["ready"]
            data["bootstrap_required"] = not report["ready"]
            return {"chat": chat, "bootstrap": report}
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
                    "prompt_file": target["prompt_file"],
                    "dispatch_contract": {
                        "thread_id": target["thread_id"],
                        "host_id": target.get("host_id", "local"),
                        "model": target["model"],
                        "reasoning_effort": target["reasoning_effort"],
                        "prompt_file": target["prompt_file"],
                        "defaults_forbidden": True,
                    },
                    "message_requirement": "余额不足紧急消息；完成恢复前不得派发其他Chat",
                }
            bootstrap = bootstrap_report(data)
            if not bootstrap["ready"]:
                data["workflow_ready"] = False
                data["bootstrap_required"] = True
                return bootstrap
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
            if not target.get("model_verified"):
                raise ValueError(f"目标Chat尚未验证实际模型和思考程度：{args.to_chat}")
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
                "prompt_file": target["prompt_file"],
                "dispatch_contract": {
                    "thread_id": target["thread_id"],
                    "host_id": target.get("host_id", "local"),
                    "model": target["model"],
                    "reasoning_effort": target["reasoning_effort"],
                    "prompt_file": target["prompt_file"],
                    "defaults_forbidden": True,
                },
                "message_requirement": "消息中提醒：完成后运行complete把自己的status改回0",
            }
        result = mutate(path, action)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ready") else 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
