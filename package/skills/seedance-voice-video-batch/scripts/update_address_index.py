"""Build and validate a bidirectional provenance index for one voice project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path


TASK_ITEM = re.compile(r"(?<!\d)(\d{7}(?:重制\d*)?_\d+)(?!\d)")
TASK_BATCH = re.compile(r"(?<!\d)(\d{7})(?!\d)")
LEGACY_ITEM = re.compile(r"(?<!\d)(\d{7}重制\d*_\d+)(?!\d)")


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def norm(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def infer_task_id(path: Path, root: Path) -> str:
    try:
        relative = str(path.relative_to(root))
    except ValueError:
        relative = str(path)
    for pattern in (LEGACY_ITEM, TASK_ITEM):
        match = pattern.search(relative)
        if match:
            return match.group(1)
    match = TASK_BATCH.search(relative)
    return match.group(1) if match else "未识别"


def record_id(original_path: str) -> str:
    digest = hashlib.sha256(norm(original_path).encode("utf-8")).hexdigest()[:16]
    return f"rec_{digest}"


def load_index(index_path: Path) -> dict:
    if not index_path.exists():
        return {}
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if "按任务ID" in data and "按路径" in data else {}


def old_records(data: dict) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for task_records in data.get("按任务ID", {}).values():
        records.update(task_records)
    return records


def files_without_reparse_roots(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name for name in directories
            if not (current_path / name).is_symlink()
            and not getattr(current_path / name, "is_junction", lambda: False)()
        ]
        files.extend(current_path / name for name in filenames)
    return files


def build(root: Path, index_path: Path, external_roots: list[Path] | None = None) -> dict:
    timestamp = now()
    previous = load_index(index_path)
    previous_records = old_records(previous)
    by_current = {norm(rec.get("当前路径", "")): rec for rec in previous_records.values()}
    records: dict[str, dict] = {}

    candidates = files_without_reparse_roots(root)
    for external_root in external_roots or []:
        if external_root.exists():
            candidates.extend(files_without_reparse_roots(external_root))

    trash_root = norm((root / "垃圾桶").resolve())

    for path in candidates:
        if not path.is_file() or norm(path) == norm(index_path):
            continue
        absolute = str(path.resolve())
        existing = by_current.get(norm(absolute))
        if existing:
            rec = dict(existing)
            rec["文件名"] = path.name
            rec["类型"] = path.suffix.lower() or "无扩展名"
            rec["当前路径"] = absolute
            rec["状态"] = "垃圾桶" if norm(path.resolve()).startswith(trash_root) else "现存"
            rec["大小字节"] = path.stat().st_size
            rec["最后核验时间"] = timestamp
        else:
            task_id = infer_task_id(path, root)
            rid = record_id(absolute)
            rec = {
                "record_id": rid,
                "task_ID": task_id,
                "文件名": path.name,
                "类型": path.suffix.lower() or "无扩展名",
                "原始路径": absolute,
                "当前路径": absolute,
                "状态": "垃圾桶" if norm(path.resolve()).startswith(trash_root) else "现存",
                "大小字节": path.stat().st_size,
                "历史路径": [absolute],
                "操作历史": [{"时间": timestamp, "操作": "首次纳入索引", "路径": absolute}],
                "最后核验时间": timestamp,
            }
        records[rec["record_id"]] = rec

    # Preserve records whose files are currently missing so historical paths remain traceable.
    for rid, rec in previous_records.items():
        if rid not in records:
            preserved = dict(rec)
            current = preserved.get("当前路径", "")
            # Records may intentionally point to a network share outside the scanned root.
            preserved["状态"] = preserved.get("状态", "现存") if current and Path(current).exists() else "路径失效待核查"
            preserved["最后核验时间"] = timestamp
            records[rid] = preserved

    by_task: dict[str, dict] = {}
    by_path: dict[str, dict] = {}
    for rid, rec in records.items():
        task_id = rec.get("task_ID") or "未识别"
        by_task.setdefault(task_id, {})[rid] = rec
        history = list(dict.fromkeys(rec.get("历史路径", []) + [rec.get("原始路径"), rec.get("当前路径")]))
        rec["历史路径"] = [p for p in history if p]
        for path in rec["历史路径"]:
            by_path[path] = {
                "record_id": rid,
                "task_ID": task_id,
                "路径状态": "当前" if norm(path) == norm(rec.get("当前路径", "")) else "历史",
                "当前路径": rec.get("当前路径"),
            }

    return {
        "schema_version": 1,
        "根目录": str(root.resolve()),
        "更新时间": timestamp,
        "说明": "双向溯源：按任务ID查文件；按任意当前或历史绝对路径反查任务与record_id。",
        "按任务ID": by_task,
        "按路径": by_path,
    }


def validate(data: dict) -> tuple[int, int]:
    by_task = data["按任务ID"]
    by_path = data["按路径"]
    record_count = 0
    for task_id, records in by_task.items():
        for rid, rec in records.items():
            record_count += 1
            if rid != rec["record_id"] or task_id != rec["task_ID"]:
                raise ValueError(f"record mismatch: {rid}")
            for path in rec["历史路径"]:
                reverse = by_path.get(path)
                if not reverse or reverse["record_id"] != rid or reverse["task_ID"] != task_id:
                    raise ValueError(f"missing reverse path: {path}")
    for path, reverse in by_path.items():
        if reverse["record_id"] not in by_task[reverse["task_ID"]]:
            raise ValueError(f"orphan reverse path: {path}")
    return record_count, len(by_path)


def atomic_write(index_path: Path, data: dict) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = index_path.with_suffix(index_path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    check = json.loads(temporary.read_text(encoding="utf-8"))
    validate(check)
    os.replace(temporary, index_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--index")
    parser.add_argument("--external-root", action="append", default=[])
    args = parser.parse_args()
    root = Path(args.root)
    index_path = Path(args.index) if args.index else root / "0日志信息" / "地址索引.json"
    data = build(root, index_path, [Path(item) for item in args.external_root])
    records, paths = validate(data)
    atomic_write(index_path, data)
    print(json.dumps({"index": str(index_path), "records": records, "paths": paths}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
