#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

REQUIRED_KEYS = ("剧本名字", "task_ID", "角色名字", "台词", "时长", "提示词")
MEDIA_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".mp4", ".mov", ".mkv", ".webm"}
REFERENCE_CHANGE_KEYS = ("素材目录", "素材状态", "可用版本", "选中版本", "需要用户选择", "选中原因")
INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    os.replace(temporary, path)


def validate_tasks(data: object) -> list[dict[str, str]]:
    if not isinstance(data, list) or not data:
        raise ValueError("任务 JSON 根节点必须是非空数组")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for number, item in enumerate(data, 1):
        if not isinstance(item, dict) or set(item) != set(REQUIRED_KEYS):
            raise ValueError(f"第 {number} 项必须且只能包含六个标准字段")
        normalized = {}
        for key in REQUIRED_KEYS:
            value = item[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"第 {number} 项的 {key} 必须是非空字符串")
            normalized[key] = value.strip()
        task_id = normalized["task_ID"]
        if task_id in seen or task_id in {".", ".."} or INVALID_FILENAME.search(task_id):
            raise ValueError(f"task_ID 重复或不能作为目录名：{task_id}")
        seen.add(task_id)
        result.append(normalized)
    return result


def asset_record(project: Path, script: str, role: str, previous: dict[str, Any] | None) -> dict[str, Any]:
    directory = project / "角色音色素材" / script / role
    media = sorted(
        str(path.resolve()) for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES
    ) if directory.is_dir() else []
    previous_selected = (previous or {}).get("选中版本")
    selected = previous_selected if previous_selected in media else (media[0] if len(media) == 1 else None)
    if not media:
        status = "缺失"
    elif selected:
        status = "已选中"
    else:
        status = "已有待选择"
    return {
        "剧本名字": script,
        "角色名字": role,
        "素材目录": str(directory.resolve()),
        "素材状态": status,
        "可用版本": media,
        "选中版本": selected,
        "需要用户选择": len(media) > 1 and selected is None,
        "选中原因": (previous or {}).get("选中原因", "单一素材自动选中" if len(media) == 1 else ""),
        "最后核验时间": now(),
    }


def append_change(path: Path, task_id: str, changes: list[str], created: bool) -> None:
    if not path.exists():
        path.write_text(f"# {task_id} 改动记录\n\n", encoding="utf-8")
    action = "建立台词资料" if created else "同步任务资料"
    details = "；".join(changes)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"## {now()} {action}\n\n{details}\n\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="同步任务 JSON 到项目 .codex 任务清单")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--task-json", required=True, type=Path)
    args = parser.parse_args()

    project = args.project_root.resolve()
    source = args.task_json.resolve()
    tasks = validate_tasks(load_json(source))
    metadata = project / ".codex"
    assets_path = metadata / "01_素材状态与选用.json"
    dialogue_path = metadata / "02_台词ID位置索引.json"
    assets = load_json(assets_path)
    dialogue = load_json(dialogue_path)
    stamp = now()

    for task in tasks:
        task_id = task["task_ID"]
        role_key = f"{task['剧本名字']}/{task['角色名字']}"
        role_record = asset_record(project, task["剧本名字"], task["角色名字"], assets["角色素材"].get(role_key))
        assets["角色素材"][role_key] = role_record

        task_dir = metadata / "任务清单" / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        info_path = task_dir / "资料索引.json"
        change_path = task_dir / "改动记录.md"
        previous = load_json(info_path) if info_path.exists() else None
        info = {
            "schema_version": 1,
            **task,
            "来源任务JSON": str(source),
            "任务资料目录": str(task_dir.resolve()),
            "参考素材": role_record,
            "视频输出目录": str((project / "已生成视频").resolve()),
            "MP3输出目录": str((project / "已转mp3").resolve()),
            "远端状态文件": None,
            "生成版本": [],
            "updated_at": stamp,
        }
        changes = []
        if previous:
            for key in (*REQUIRED_KEYS, "来源任务JSON"):
                if previous.get(key) != info.get(key):
                    changes.append(f"{key}：{previous.get(key)!r} -> {info.get(key)!r}")
            previous_reference = previous.get("参考素材", {})
            current_reference = info.get("参考素材", {})
            if any(previous_reference.get(key) != current_reference.get(key) for key in REFERENCE_CHANGE_KEYS):
                changes.append(
                    "参考素材状态或选中版本更新："
                    f"{previous_reference.get('素材状态')!r}/{previous_reference.get('选中版本')!r} -> "
                    f"{current_reference.get('素材状态')!r}/{current_reference.get('选中版本')!r}"
                )
        else:
            changes.append(f"首次建立，来源任务 JSON：{source}")
        write_json(info_path, info)
        if previous is None or changes:
            append_change(change_path, task_id, changes, previous is None)
        dialogue["台词"][task_id] = {
            "剧本名字": task["剧本名字"],
            "角色名字": task["角色名字"],
            "台词": task["台词"],
            "来源任务JSON": str(source),
            "资料索引": str(info_path.resolve()),
            "改动记录": str(change_path.resolve()),
            "视频输出目录": info["视频输出目录"],
            "MP3输出目录": info["MP3输出目录"],
        }

    assets["updated_at"] = stamp
    dialogue["updated_at"] = stamp
    write_json(assets_path, assets)
    write_json(dialogue_path, dialogue)
    print(json.dumps({"task_count": len(tasks), "metadata_root": str(metadata)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
