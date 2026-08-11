#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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
    complete.add_argument("--lease-id", required=True)

    acknowledge = sub.add_parser("ack-feedback")
    acknowledge.add_argument("--chat", required=True)
    acknowledge.add_argument("--from-chat", required=True)
    acknowledge.add_argument("--lease-id", required=True)

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
            if args.status == 1:
                raise ValueError("不得手动占用Chat；必须使用prepare-handoff创建任务租约")
            if chat.get("active_task"):
                raise ValueError("Chat仍有活动任务；必须使用带正确lease-id的complete结束")
            chat["status"] = args.status
            return {"chat": args.chat, "status": args.status}
        print(json.dumps(mutate(path, action), ensure_ascii=False))
        return 0

    if args.command == "complete":
        def action(data: dict[str, Any]) -> dict[str, Any]:
            chat = get_chat(data, args.chat)
            active = chat.get("active_task")
            if not isinstance(active, dict):
                raise ValueError(f"Chat没有可完成的活动任务：{args.chat}")
            if active.get("lease_id") != args.lease_id:
                raise ValueError("lease-id不匹配；拒绝结束或清空其他任务")
            chat["status"] = 0
            completed = {**active, "completed_at": now()}
            chat["last_completed_task"] = completed
            chat["active_task"] = None
            feedback_target_name = chat.get("feedback_to")
            feedback_contract = None
            if chat.get("feedback_required") and feedback_target_name:
                feedback_target = get_chat(data, feedback_target_name)
                waiting = feedback_target.get("waiting_for_feedback")
                acknowledgement_required = bool(
                    isinstance(waiting, dict)
                    and waiting.get("lease_id") == args.lease_id
                    and waiting.get("from_chat") == args.chat
                )
                feedback_contract = {
                    "to_chat": feedback_target_name,
                    "thread_id": feedback_target.get("thread_id"),
                    "host_id": feedback_target.get("host_id", "local"),
                    "lease_id": args.lease_id,
                    "task_ID": active.get("task_ID"),
                    "acknowledgement_required": acknowledgement_required,
                    "acknowledge_command": {
                        "command": "ack-feedback",
                        "chat": feedback_target_name,
                        "from_chat": args.chat,
                        "lease_id": args.lease_id,
                    } if acknowledgement_required else None,
                }
            return {
                "chat": args.chat,
                "status": 0,
                "completed_task": completed,
                "feedback_contract": feedback_contract,
            }
        print(json.dumps(mutate(path, action), ensure_ascii=False))
        return 0

    if args.command == "ack-feedback":
        def action(data: dict[str, Any]) -> dict[str, Any]:
            chat = get_chat(data, args.chat)
            waiting = chat.get("waiting_for_feedback")
            if not isinstance(waiting, dict):
                raise ValueError(f"Chat当前没有等待中的反馈：{args.chat}")
            if waiting.get("from_chat") != args.from_chat or waiting.get("lease_id") != args.lease_id:
                raise ValueError("反馈来源或lease-id不匹配；拒绝恢复主对话")
            source = get_chat(data, args.from_chat)
            completed = source.get("last_completed_task")
            if not isinstance(completed, dict) or completed.get("lease_id") != args.lease_id:
                raise ValueError("下属Chat尚未以该lease-id完成任务，不能确认反馈")
            chat["last_acknowledged_feedback"] = {
                **waiting,
                "acknowledged_at": now(),
            }
            chat["waiting_for_feedback"] = None
            return {
                "chat": args.chat,
                "waiting_for_feedback": None,
                "resumed": True,
                "completed_task": completed,
            }
        print(json.dumps(mutate(path, action), ensure_ascii=False))
        return 0

    if args.command == "prepare-handoff":
        def action(data: dict[str, Any]) -> dict[str, Any]:
            if args.from_chat == args.to_chat:
                raise ValueError("禁止Chat向自己交接任务")
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
            owner_name = data.get("workflow_owner", "理解文本与任务")
            waiting = source.get("waiting_for_feedback")
            if args.from_chat == owner_name and isinstance(waiting, dict):
                return {
                    "ready": False,
                    "source_waiting": True,
                    "from_chat": args.from_chat,
                    "waiting_for_feedback": waiting,
                    "required_action": "停止继续处理；使用Codex任务等待工具等待指定thread反馈",
                }
            retry_key = hashlib.sha256(
                f"{args.from_chat}\0{args.to_chat}\0{args.task_id}\0{args.summary}".encode("utf-8")
            ).hexdigest()[:12]
            retry_automation_id = f"voice-chat-retry-{target.get('order', 0)}-{retry_key}"
            if target.get("status") == 1 or target.get("active_task"):
                retry = int(data.get("busy_retry_minutes", 5))
                retry_after = (datetime.now().astimezone() + timedelta(minutes=retry)).isoformat(timespec="seconds")
                retry_contract = {
                    "automation_id": retry_automation_id,
                    "dedupe_key": retry_key,
                    "schedule": {"kind": "once", "run_at": retry_after},
                    "action": "重新执行同一prepare-handoff；若仍忙碌则按新合同再设5分钟定时器",
                    "arguments": {
                        "from_chat": args.from_chat,
                        "to_chat": args.to_chat,
                        "task_ID": args.task_id or None,
                        "summary": args.summary,
                    },
                }
                data.setdefault("pending_retries", {})[retry_automation_id] = {
                    **retry_contract,
                    "requested_at": now(),
                }
                return {
                    "ready": False,
                    "to_chat": args.to_chat,
                    "retry_minutes": retry,
                    "retry_after": retry_after,
                    "timer_required": True,
                    "retry_contract": retry_contract,
                    "active_task": target.get("active_task"),
                }
            if not target.get("thread_id"):
                raise ValueError(f"目标Chat尚未登记thread_id：{args.to_chat}")
            if target.get("full_access_required") and not target.get("full_access_verified"):
                raise ValueError(f"目标Chat尚未验证完全访问权限：{args.to_chat}")
            if not target.get("model_verified"):
                raise ValueError(f"目标Chat尚未验证实际模型和思考程度：{args.to_chat}")
            lease_id = os.urandom(16).hex()
            active_task = {
                "lease_id": lease_id,
                "task_ID": args.task_id or None,
                "summary": args.summary,
                "from_chat": args.from_chat,
                "assigned_at": now(),
            }
            target["status"] = 1
            target["active_task"] = active_task
            data.setdefault("pending_retries", {}).pop(retry_automation_id, None)
            must_wait = bool(args.from_chat == owner_name and target.get("feedback_required"))
            if must_wait:
                source["waiting_for_feedback"] = {
                    "from_chat": args.to_chat,
                    "thread_id": target["thread_id"],
                    "host_id": target.get("host_id", "local"),
                    "lease_id": lease_id,
                    "task_ID": args.task_id or None,
                    "started_at": now(),
                }
            event = {
                "time": now(), "from": args.from_chat, "to": args.to_chat,
                "task_ID": args.task_id or None, "summary": args.summary, "lease_id": lease_id,
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
                    "lease_id": lease_id,
                },
                "active_task": active_task,
                "must_stop_and_wait": must_wait,
                "post_send_action": {
                    "action": "stop_and_wait_for_feedback",
                    "thread_id": target["thread_id"],
                    "host_id": target.get("host_id", "local"),
                    "lease_id": lease_id,
                    "instruction": "消息发出后立即停止本轮继续处理，调用Codex任务等待工具；收到反馈后运行ack-feedback",
                } if must_wait else None,
                "message_requirement": (
                    "消息中必须附带lease-id，并提醒接收者完成后使用同一lease-id运行complete；"
                    "主对话发送后立即停止并等待反馈"
                ),
            }
        result = mutate(path, action)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ready") else 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
