"""Append one auditable operation entry to a voice-production project log."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path


def clean(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split()) or "无"


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a voice-project operation log entry.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--files", required=True)
    parser.add_argument("--status", required=True, choices=("完成", "进行中", "失败", "已取消"))
    parser.add_argument("--previous-task-id", default="未适用")
    parser.add_argument("--notes", default="无")
    args = parser.parse_args()

    path = Path(args.project_root) / "0日志信息" / "任务操作日志.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# 配音任务操作日志\n", encoding="utf-8")

    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    entry = (
        f"\n## {timestamp} | {clean(args.task)}\n\n"
        f"- 状态：{args.status}\n"
        f"- 上一任务ID：{clean(args.previous_task_id)}\n"
        f"- 操作：{clean(args.action)}\n"
        f"- 文件：{clean(args.files)}\n"
        f"- 评价/复生/备注：{clean(args.notes)}\n"
    )
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(entry)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
