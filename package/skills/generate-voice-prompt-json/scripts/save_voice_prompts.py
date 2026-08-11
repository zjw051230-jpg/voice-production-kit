#!/usr/bin/env python3
"""Validate per-line voice prompt JSON and save it with deterministic naming."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


REQUIRED_KEYS = ("剧本名字", "task_ID", "角色名字", "台词", "时长", "提示词")
INVALID_TASK_ID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
VALID_DURATION = re.compile(r"^[1-9]\d*秒$")
REQUIRED_PROMPT_MARKERS = (
    "参考音视频只用于复刻音色和自然说话习惯",
    "成片唯一允许出现的人声内容是",
    "必须逐字、完整、只说一次",
    "不得改词、漏词、加词、重复、续说",
    "除目标台词外宁可保持静音",
)
VOICE_TEMPLATE_MARKER_SETS = (
    ("严格复刻参考音视频的原始声音", "不得自行调整声线"),
    ("声纹质感", "音高走势", "共鸣位置", "气息力度", "语尾处理", "自然停连"),
)
CONTEXT_MARKER_GROUPS = {
    "当前触发或认知": ("此刻", "刚", "看到", "听到", "发现", "得知", "面对", "正在", "知道", "判断"),
    "对话对象或目的": ("对", "向", "想让", "希望", "为了", "提醒", "询问", "安抚", "制止", "确认", "命令", "回答", "报告"),
    "内在心理或克制": ("担心", "害怕", "不安", "警觉", "焦急", "心疼", "犹豫", "压住", "克制", "隐藏", "试探", "放松", "释然"),
}


def fail(message: str) -> None:
    raise ValueError(message)


def validate(task_id: str, data: object) -> list[dict[str, str]]:
    if not task_id or task_id.strip() != task_id:
        fail("task_id 不能为空，也不能包含首尾空格")
    if task_id in {".", ".."} or INVALID_TASK_ID.search(task_id):
        fail("task_id 含 Windows 文件名不允许的字符")
    if not isinstance(data, list) or not data:
        fail("JSON 根节点必须是非空数组")

    validated: list[dict[str, str]] = []
    expected = set(REQUIRED_KEYS)
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            fail(f"第 {index} 项必须是对象")
        if set(item) != expected:
            fail(f"第 {index} 项必须且只能包含：{'、'.join(REQUIRED_KEYS)}")
        normalized: dict[str, str] = {}
        for key in REQUIRED_KEYS:
            value = item[key]
            if not isinstance(value, str) or not value.strip():
                fail(f"第 {index} 项的“{key}”必须是非空字符串")
            normalized[key] = value.strip()
        if not VALID_DURATION.fullmatch(normalized["时长"]):
            fail(f"第 {index} 项的“时长”必须类似“4秒”")
        expected_item_id = f"{task_id}_{index}"
        if normalized["task_ID"] != expected_item_id:
            fail(f"第 {index} 项的“task_ID”必须为“{expected_item_id}”")
        line_occurrences = normalized["提示词"].count(normalized["台词"])
        if line_occurrences != 1:
            fail(f"第 {index} 项的提示词必须且只能完整包含一次原台词，当前为 {line_occurrences} 次")
        missing_markers = [marker for marker in REQUIRED_PROMPT_MARKERS if marker not in normalized["提示词"]]
        if missing_markers:
            fail(f"第 {index} 项的提示词缺少严格单句约束：{'；'.join(missing_markers)}")
        if not any(all(marker in normalized["提示词"] for marker in markers)
                   for markers in VOICE_TEMPLATE_MARKER_SETS):
            fail(f"第 {index} 项的提示词缺少合格的音色锁定：需要详细音色维度，或明确严格复刻参考音视频且不得自行调整声线")
        missing_context = [
            label for label, markers in CONTEXT_MARKER_GROUPS.items()
            if not any(marker in normalized["提示词"] for marker in markers)
        ]
        if missing_context:
            fail(f"第 {index} 项的提示词缺少剧情到表演的上下文：{'、'.join(missing_context)}")
        validated.append(normalized)
    script_names = {item["剧本名字"] for item in validated}
    if len(script_names) != 1:
        fail("同一个 JSON 文件内的“剧本名字”必须一致")
    script_name = next(iter(script_names))
    if script_name in {".", ".."} or INVALID_TASK_ID.search(script_name):
        fail("“剧本名字”必须是角色音色素材下的单层目录名，不能包含 Windows 非法文件名字符")
    return validated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    try:
        with args.input.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        tasks = validate(args.task_id, data)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        destination = args.output_dir / f"{args.task_id}+{len(tasks)}个任务.json"
        if destination.exists() and not args.overwrite:
            fail(f"目标文件已存在：{destination}；确认替换后再使用 --overwrite")
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(tasks, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(destination)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"path": str(destination), "task_count": len(tasks)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
