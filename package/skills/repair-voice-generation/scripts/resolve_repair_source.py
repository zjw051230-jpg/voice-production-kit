#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import ntpath
import re
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
ADDRESS_INDEX = ROOT / "0日志信息" / "地址索引.json"
DIALOGUE_INDEX = ROOT / "0日志信息" / "0724及之前_台词角色对应序号表.json"
TEXT_DIR = ROOT / "文字素材"
ITEM_ID = re.compile(r"^(?P<batch>\d{7}(?:重制\d*)?)_(?P<item>\d+)$")


def norm_windows(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(value.strip().strip('"')))


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def find_reverse(address: dict[str, Any], supplied: str) -> tuple[str, dict[str, Any]]:
    wanted = norm_windows(supplied)
    matches = [(path, ref) for path, ref in address["按路径"].items() if norm_windows(path) == wanted]
    if len(matches) != 1:
        raise RuntimeError(f"地址索引精确匹配数量应为1，实际为{len(matches)}：{supplied}")
    return matches[0]


def full_record(address: dict[str, Any], reverse: dict[str, Any]) -> dict[str, Any]:
    task_id = reverse["task_ID"]
    record_id = reverse["record_id"]
    records = address["按任务ID"].get(task_id, {})
    record = records.get(record_id)
    if not record:
        raise RuntimeError(f"按路径能命中，但按任务ID无法回到记录：{task_id}/{record_id}")
    return record


def find_source_items(task_id: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for path in sorted(TEXT_DIR.glob("*+*个任务.json")):
        try:
            items = load(path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("task_ID") == task_id:
                found.append({"json": str(path), "item": item})
    return found


def dialogue_matches(index: dict[str, Any], task_id: str) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for role, lines in index.items():
        if not isinstance(lines, dict):
            continue
        for line, task_ids in lines.items():
            if isinstance(task_ids, list) and task_id in task_ids:
                matches.append({"角色": role, "台词": line})
    return matches


def main() -> int:
    global ROOT, ADDRESS_INDEX, DIALOGUE_INDEX, TEXT_DIR
    parser = argparse.ArgumentParser(description="Resolve a repair source file to its exact original JSON item.")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--dialogue-index", type=Path,
                        help="Optional legacy dialogue-role index; defaults inside project 0日志信息")
    parser.add_argument("--file", required=True, help="Absolute current or historical file path supplied by the user")
    args = parser.parse_args()

    ROOT = args.project_root.resolve()
    ADDRESS_INDEX = ROOT / "0日志信息" / "地址索引.json"
    DIALOGUE_INDEX = args.dialogue_index or (ROOT / "0日志信息" / "0724及之前_台词角色对应序号表.json")
    TEXT_DIR = ROOT / "文字素材"

    address = load(ADDRESS_INDEX)
    dialogue = load(DIALOGUE_INDEX) if DIALOGUE_INDEX.exists() else {}
    matched_path, reverse = find_reverse(address, args.file)
    record = full_record(address, reverse)
    task_id = str(reverse["task_ID"])
    if task_id == "未识别" or not ITEM_ID.fullmatch(task_id):
        raise RuntimeError(f"该文件未解析到可用的条目 task_ID：{task_id}")

    source_items = find_source_items(task_id)
    if len(source_items) != 1:
        raise RuntimeError(f"原始文字素材中 task_ID={task_id} 的精确条目应为1个，实际为{len(source_items)}个")
    source = source_items[0]
    cross = dialogue_matches(dialogue, task_id)
    item = source["item"]
    consistent = not dialogue or any(
        x["角色"] == item.get("角色名字") and x["台词"] == item.get("台词") for x in cross
    )
    if not consistent:
        raise RuntimeError(
            "台词角色索引与原JSON不一致："
            + json.dumps({"index": cross, "json_role": item.get("角色名字"), "json_line": item.get("台词")}, ensure_ascii=False)
        )

    output = {
        "用户路径": args.file,
        "索引命中路径": matched_path,
        "路径状态": reverse.get("路径状态"),
        "record_id": record.get("record_id"),
        "记录状态": record.get("状态"),
        "当前路径": record.get("当前路径"),
        "历史路径": record.get("历史路径", []),
        "原task_ID": task_id,
        "源JSON": source["json"],
        "剧本名字": item.get("剧本名字"),
        "角色名字": item.get("角色名字"),
        "台词": item.get("台词"),
        "时长": item.get("时长"),
        "原提示词": item.get("提示词"),
        "台词角色索引交叉验证": cross,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
