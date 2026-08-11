"""Attach an explicit source relationship to an indexed derived file."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--action", required=True)
    args = parser.parse_args()
    index = Path(args.index)
    data = json.loads(index.read_text(encoding="utf-8"))
    source = data["按路径"].get(args.source)
    output = data["按路径"].get(args.output)
    if not source or not output:
        raise SystemExit("source or output path is absent from index")
    task_records = data["按任务ID"][output["task_ID"]]
    record = task_records[output["record_id"]]
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    record["来源record_id"] = source["record_id"]
    record["来源路径"] = args.source
    record.setdefault("操作历史", []).append(
        {"时间": timestamp, "操作": args.action, "来源路径": args.source, "结果路径": args.output}
    )
    data["更新时间"] = timestamp
    temporary = index.with_suffix(index.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    os.replace(temporary, index)
    print(output["record_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
