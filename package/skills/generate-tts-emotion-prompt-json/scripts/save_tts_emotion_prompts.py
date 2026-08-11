#!/usr/bin/env python3
"""Validate emotion-only TTS task JSON and save with deterministic naming."""

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
INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
VALID_DURATION = re.compile(r"^[1-9]\d*秒$")
FORBIDDEN_PROMPT_TERMS = (
    "参考音频", "参考视频", "参考音色", "参考素材", "上传", "复刻", "克隆",
    "模仿音色", "声纹", "音色还原", "声线", "年龄感", "音高", "共鸣",
    "口音", "画面", "镜头", "分辨率", "竖屏", "音乐", "音效", "环境噪声",
)
CONTEXT_GROUPS = {
    "场景触发": ("此刻", "刚", "发现", "听到", "得知", "意识到", "面对", "回忆", "判断"),
    "对象和目的": ("对", "说", "目的是", "想让", "希望", "提醒", "回答", "报告", "命令", "承认"),
    "情绪": ("情绪", "担心", "焦急", "警觉", "羞愧", "希望", "神秘", "得意", "热络", "克制", "愤怒", "难过", "关切"),
    "节奏": ("语速", "放慢", "加快", "停顿", "短停", "衔接"),
    "重音和收句": ("重读", "加重", "句尾", "收住", "下落", "上扬"),
}
BOUNDARY_MARKERS = ("只说输入台词", "不添加", "不重复", "续说")


def fail(message: str) -> None:
    raise ValueError(message)


def validate(task_id: str, data: object) -> list[dict[str, str]]:
    if not task_id or task_id.strip() != task_id:
        fail("task_id 不能为空，也不能包含首尾空格")
    if task_id in {".", ".."} or INVALID_FILENAME.search(task_id):
        fail("task_id 含 Windows 文件名不允许的字符")
    if not isinstance(data, list) or not data:
        fail("JSON 根节点必须是非空数组")

    expected_keys = set(REQUIRED_KEYS)
    result: list[dict[str, str]] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict) or set(item) != expected_keys:
            fail(f"第 {index} 项必须且只能包含：{'、'.join(REQUIRED_KEYS)}")
        normalized: dict[str, str] = {}
        for key in REQUIRED_KEYS:
            value = item[key]
            if not isinstance(value, str) or not value.strip():
                fail(f"第 {index} 项的“{key}”必须是非空字符串")
            normalized[key] = value.strip()
        expected_item_id = f"{task_id}_{index}"
        if normalized["task_ID"] != expected_item_id:
            fail(f"第 {index} 项 task_ID 必须为“{expected_item_id}”；同批任务必须共用一个 task_id")
        if not VALID_DURATION.fullmatch(normalized["时长"]):
            fail(f"第 {index} 项的“时长”必须类似“7秒”")

        prompt = normalized["提示词"]
        forbidden = [term for term in FORBIDDEN_PROMPT_TERMS if term in prompt]
        if forbidden:
            fail(f"第 {index} 项提示词含禁止的音色或视听指令：{'、'.join(forbidden)}")
        if normalized["台词"] in prompt:
            fail(f"第 {index} 项提示词不得复述台词；TTS input 单独传入台词")
        missing = [label for label, markers in CONTEXT_GROUPS.items() if not any(m in prompt for m in markers)]
        if missing:
            fail(f"第 {index} 项提示词缺少：{'、'.join(missing)}")
        if not all(marker in prompt for marker in BOUNDARY_MARKERS):
            fail(f"第 {index} 项提示词必须要求只说输入台词且不添加、不重复、不续说")
        result.append(normalized)

    if len({item["剧本名字"] for item in result}) != 1:
        fail("同一批 JSON 内的“剧本名字”必须一致")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    try:
        with args.input.open("r", encoding="utf-8-sig") as handle:
            tasks = validate(args.task_id, json.load(handle))
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
