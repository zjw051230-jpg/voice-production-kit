#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Append one Seedance rework record.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--item", required=True)
    parser.add_argument("--script-name", default="")
    parser.add_argument("--input-task-id", default="")
    parser.add_argument("--variant", type=int)
    parser.add_argument("--role", default="")
    parser.add_argument("--line", default="")
    parser.add_argument("--issue-type", required=True)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--suggestion", required=True)
    parser.add_argument("--task-id", default="")
    parser.add_argument("--video", default="")
    parser.add_argument("--status", default="待返工")
    args = parser.parse_args()

    path = Path(args.project_root) / "问题与改进log" / "问题建议.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    variant = f"v{args.variant:02d}" if args.variant else "未指定"
    block = (
        f"\n## {datetime.now().astimezone().isoformat(timespec='seconds')} | {args.task} | {args.item} | {variant}\n\n"
        f"- 剧本分类：{args.script_name or '未填写'}\n"
        f"- 输入 task_ID：{args.input_task_id or '未填写'}\n"
        f"- 角色：{args.role or '未填写'}\n"
        f"- 台词：{args.line or '未填写'}\n"
        f"- 问题类型：{args.issue_type}\n"
        f"- 问题描述：{args.issue}\n"
        f"- 改进建议：{args.suggestion}\n"
        f"- 远端任务 ID：{args.task_id or '未填写'}\n"
        f"- 原视频：{args.video or '未填写'}\n"
        f"- 处理状态：{args.status}\n"
    )
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(block)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
