#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import threading
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None
    Image = ImageDraw = None

BG = "#f4f6f7"
PANEL = "#ffffff"
TEXT = "#172027"
MUTED = "#66737c"
BORDER = "#d8dee2"
BLUE = "#225ea8"
GREEN = "#177454"
RED = "#b33a32"
AMBER = "#9a6300"
TASK_FIELDS = {"剧本名字", "task_ID", "角色名字", "台词", "时长", "提示词"}
REMOTE_FAILED = {"failed", "error", "cancelled", "canceled", "submit_failed"}
REMOTE_RUNNING = {"queued", "processing", "running", "in_progress"}
REMOTE_SUBMITTED = {"pending", "submitted", "created"}
REMOTE_READY = {"succeeded", "completed", "success", "done"}
PULLBACK_FAILED = {"postprocess_failed", "download_blocked"}
MEDIA_SUFFIXES = {".mp3", ".mp4", ".wav", ".m4a"}
STAGE_ORDER = ["准备中", "生产中", "待拉回", "需处理", "已交付"]


def app_dir() -> Path:
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


def config_path() -> Path:
    return app_dir() / "dashboard-config.json"


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="dashboard-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def task_records(document) -> list[dict]:
    if isinstance(document, list):
        return [item for item in document if isinstance(item, dict)]
    if isinstance(document, dict):
        if TASK_FIELDS.intersection(document):
            return [document]
        for key in ("tasks", "任务", "items", "data"):
            value = document.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def load_projects(workspace: Path) -> list[tuple[str, Path]]:
    registry = read_json(workspace / "项目注册表.json", {}) or {}
    projects = registry.get("projects", {}) if isinstance(registry, dict) else {}
    result = []
    for name, entry in projects.items():
        if isinstance(entry, dict) and entry.get("active") is False:
            continue
        raw = entry.get("project_root") if isinstance(entry, dict) else entry
        if isinstance(raw, str) and raw.strip():
            result.append((str(name), Path(raw)))
    return result


def find_named(root: Path, *names: str) -> Path | None:
    for name in names:
        path = root / Path(name)
        if path.exists():
            return path
    return None


def material_status(root: Path, role: str) -> str:
    data = read_json(root / ".codex" / "01_素材状态与选用.json", {}) or {}
    roles = data.get("角色素材", {}) if isinstance(data, dict) else {}
    item = roles.get(role, {}) if isinstance(roles, dict) else {}
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("状态") or item.get("status") or "未知")
    return "未知"


def collect_jobs(video_root: Path | None) -> dict[str, list[dict]]:
    by_task: dict[str, list[dict]] = {}
    if not video_root or not video_root.exists():
        return by_task
    for state_path in video_root.rglob(".seedance-state.json"):
        data = read_json(state_path, {}) or {}
        jobs = data.get("jobs", {}) if isinstance(data, dict) else {}
        values = jobs.values() if isinstance(jobs, dict) else jobs if isinstance(jobs, list) else []
        for job in values:
            if not isinstance(job, dict):
                continue
            task_id = str(job.get("input_task_id") or job.get("task_ID") or "").strip()
            if task_id:
                value = dict(job)
                value["_state_path"] = str(state_path)
                by_task.setdefault(task_id, []).append(value)
    return by_task


def files_exist(job: dict) -> bool:
    output, mp3 = job.get("output"), job.get("mp3")
    return bool(output and mp3 and Path(str(output)).is_file() and Path(str(mp3)).is_file())


def job_summary(jobs: list[dict]) -> dict:
    total = len(jobs)
    statuses = [str(job.get("status", "new")).strip().lower() for job in jobs]
    success = sum(status in REMOTE_READY | {"downloaded"} | PULLBACK_FAILED for status in statuses)
    failed = sum(status in REMOTE_FAILED for status in statuses)
    downloaded = sum(status == "downloaded" and files_exist(job)
                     for status, job in zip(statuses, jobs))
    submitted = sum(status in REMOTE_SUBMITTED for status in statuses)
    generating = sum(status in REMOTE_RUNNING for status in statuses)
    missing_deliverables = sum(status == "downloaded" and not files_exist(job)
                               for status, job in zip(statuses, jobs))
    running = total - success - failed
    terminal = total > 0 and success + failed == total
    deliverables_ready = terminal and success > 0 and downloaded == success
    return {
        "total": total, "success": success, "failed": failed, "running": running,
        "downloaded": downloaded, "terminal_count": success + failed,
        "terminal": terminal, "deliverables_ready": deliverables_ready,
        "pullback_failed": sum(status in PULLBACK_FAILED for status in statuses),
        "submitted": submitted, "generating": generating,
        "nonterminal": running, "missing_deliverables": missing_deliverables,
        "local_failures": sum(status in PULLBACK_FAILED for status in statuses) + missing_deliverables,
        "statuses": set(statuses),
    }


def derive_status(task: dict, jobs: list[dict], material: str) -> tuple[str, dict]:
    summary = job_summary(jobs)
    statuses = summary["statuses"]
    if not jobs:
        if material == "缺失":
            return "素材缺失", summary
        if material in {"已有待选择", "待确认"}:
            return "素材待选择", summary
        if material in {"", "未知", "未登记"}:
            return "素材未登记", summary
    if summary["running"] > 0:
        if statuses & (REMOTE_RUNNING | REMOTE_READY | REMOTE_FAILED | PULLBACK_FAILED | {"downloaded"}):
            return "生成中", summary
        if statuses & REMOTE_SUBMITTED or any(job.get("api_id") for job in jobs):
            return "已提交", summary
    if summary["terminal"]:
        if summary["pullback_failed"]:
            return "拉回失败", summary
        if summary["missing_deliverables"]:
            return "成品缺失", summary
        if summary["success"] == 0:
            return "已结束（全部失败）", summary
        if not summary["deliverables_ready"]:
            return "可拉回", summary
        if summary["failed"]:
            return "已结束（含失败）", summary
        return "已完成", summary
    if statuses & REMOTE_SUBMITTED or any(job.get("api_id") for job in jobs):
        return "已提交", summary
    if str(task.get("提示词", "")).strip():
        return "提示词就绪", summary
    return "待准备", summary


def status_details(status: str, summary: dict, material: str) -> dict:
    mapping = {
        "素材未登记": ("准备中", "登记角色素材", True),
        "素材缺失": ("准备中", "补充角色素材", True),
        "素材待选择": ("准备中", "确认参考音色", True),
        "待准备": ("准备中", "补齐台词与提示词", False),
        "提示词就绪": ("准备中", "提交生成", False),
        "已提交": ("生产中", "等待远端开始", False),
        "生成中": ("生产中", "等待远端全部结束", False),
        "可拉回": ("待拉回", "拉回全部成功版本", False),
        "成品缺失": ("需处理", "检查或重新拉回成品", True),
        "拉回失败": ("需处理", "重试拉回", True),
        "已结束（全部失败）": ("需处理", "重做失败版本", True),
        "已结束（含失败）": ("已交付", "检查失败版本或打开成品", True),
        "已完成": ("已交付", "打开或复制成品", False),
    }
    stage, next_action, attention = mapping.get(status, ("需处理", "检查任务状态", True))
    return {"stage": stage, "next_action": next_action, "requires_attention": attention}


def latest_update(source: Path, jobs: list[dict]) -> str:
    timestamps = []
    try:
        timestamps.append(source.stat().st_mtime)
    except OSError:
        pass
    for job in jobs:
        state_path = job.get("_state_path")
        if state_path:
            try:
                timestamps.append(Path(str(state_path)).stat().st_mtime)
            except OSError:
                pass
    if not timestamps:
        return ""
    return datetime.fromtimestamp(max(timestamps)).astimezone().strftime("%Y-%m-%d %H:%M")


def scan_workspace(workspace: Path) -> list[dict]:
    rows = []
    for project_name, root in load_projects(workspace):
        task_root = find_named(root, "文字素材", "01_输入资料/03_配音任务")
        video_root = find_named(root, "已生成视频", "02_生产成品/01_生成视频")
        jobs_by_task = collect_jobs(video_root)
        seen = set()
        for source in list(task_root.rglob("*.json")) if task_root and task_root.exists() else []:
            for task in task_records(read_json(source, [])):
                task_id = str(task.get("task_ID") or "").strip()
                if not task_id or task_id in seen:
                    continue
                seen.add(task_id)
                material = material_status(root, str(task.get("角色名字") or ""))
                jobs = jobs_by_task.get(task_id, [])
                status, summary = derive_status(task, jobs, material)
                details = status_details(status, summary, material)
                rows.append({
                    "key": f"{project_name}::{task_id}", "project": project_name,
                    "task_id": task_id, "script": str(task.get("剧本名字") or ""),
                    "role": str(task.get("角色名字") or ""), "line": str(task.get("台词") or ""),
                    "duration": str(task.get("时长") or "未填写"),
                    "material": "素材未登记" if material in {"", "未知", "未登记"} else material,
                    "status": status, **details,
                    "done": summary["terminal_count"], "total": summary["total"],
                    "success": summary["success"], "failed": summary["failed"],
                    "running": summary["running"], "downloaded": summary["downloaded"],
                    "terminal": summary["terminal"],
                    "complete": summary["deliverables_ready"], "source": str(source),
                    "source_name": source.name, "updated_at": latest_update(source, jobs),
                })
    return sorted(rows, key=lambda item: (item["project"], item["task_id"]))


def resolve_completed(workspace: Path, key: str) -> tuple[dict, list[Path]]:
    matches = [row for row in scan_workspace(workspace) if row["key"] == key]
    if len(matches) != 1 or not matches[0]["complete"]:
        raise ValueError("整批任务尚未终态，或成功版本尚未全部拉回，不能执行成品操作")
    project_name, task_id = key.split("::", 1)
    projects = dict(load_projects(workspace))
    root = projects[project_name]
    jobs = collect_jobs(find_named(root, "已生成视频", "02_生产成品/01_生成视频")).get(task_id, [])
    files = []
    for job in jobs:
        if str(job.get("status") or "").lower() != "downloaded" or not files_exist(job):
            continue
        for field in ("output", "mp3"):
            path = Path(str(job.get(field) or "")).resolve()
            if path.suffix.lower() in MEDIA_SUFFIXES and path.is_file() and path not in files:
                files.append(path)
    if not files:
        raise ValueError("未找到登记的成品文件")
    return matches[0], files


def validate_destination(raw: str) -> Path:
    if '"' in raw:
        raise ValueError("地址不能包含双引号")
    value = raw.strip()
    if not value:
        raise ValueError("请输入目标地址")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("必须输入绝对本地路径或 UNC 路径")
    if not path.exists() or not path.is_dir():
        raise ValueError("目标地址不存在或不是文件夹")
    return path.resolve()


def copy_completed(workspace: Path, key: str, raw_destination: str) -> tuple[Path, int]:
    row, files = resolve_completed(workspace, key)
    destination = validate_destination(raw_destination)
    name = re.sub(r'[<>:"/\\|?*]', "_", f"{row['project']}_{row['task_id']}")
    target = destination / name
    if target.exists():
        raise FileExistsError(f"目标任务文件夹已存在，未复制：{target}")
    staging = destination / f".{name}.copying-{os.getpid()}-{secrets.token_hex(4)}"
    staging.mkdir()
    try:
        for source in files:
            copy_path = staging / source.name
            if copy_path.exists():
                raise FileExistsError(f"目标文件已存在，未覆盖：{copy_path}")
            shutil.copy2(source, copy_path)
        os.replace(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return target, len(files)


class VoiceDashboard:
    def __init__(self, root: tk.Tk, workspace: Path) -> None:
        self.root = root
        self.workspace = workspace
        self.rows: list[dict] = []
        self.filtered: list[dict] = []
        self.last_signature = None
        self.tray_icon = None
        self.topmost = tk.BooleanVar(value=False)
        self.project_filter = tk.StringVar(value="全部项目")
        self.status_filter = tk.StringVar(value="全部状态")
        self.search_value = tk.StringVar()
        self.summary = tk.StringVar(value="正在读取任务")
        root.title("配音任务看板")
        root.geometry("980x760")
        root.minsize(720, 520)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.configure_styles()
        self.build_ui()
        self.start_tray()
        self.refresh()

    def configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Voice.Horizontal.TProgressbar", troughcolor="#e8edf1", background=BLUE,
                        bordercolor="#e8edf1", lightcolor=BLUE, darkcolor=BLUE, thickness=7)
        style.configure("Voice.TCombobox", padding=5)

    def build_ui(self) -> None:
        header = tk.Frame(self.root, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x")
        title_row = tk.Frame(header, bg=PANEL)
        title_row.pack(fill="x", padx=18, pady=(13, 8))
        tk.Label(title_row, text="配音任务看板", bg=PANEL, fg=TEXT,
                 font=("Microsoft YaHei UI", 14, "bold")).pack(side="left")
        tk.Label(title_row, textvariable=self.summary, bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(16, 0))
        tk.Checkbutton(title_row, text="置顶", variable=self.topmost, command=self.toggle_topmost,
                       bg=PANEL, activebackground=PANEL, fg=MUTED, selectcolor=PANEL,
                       font=("Microsoft YaHei UI", 9)).pack(side="right")
        tk.Button(title_row, text="工作区", command=self.choose_workspace, bg="#e8edf1", fg=TEXT,
                  activebackground="#dbe2e7", relief="flat", cursor="hand2", padx=11, pady=4,
                  font=("Microsoft YaHei UI", 9)).pack(side="right", padx=(0, 10))

        filter_row = tk.Frame(header, bg=PANEL)
        filter_row.pack(fill="x", padx=18, pady=(0, 13))
        self.project_box = ttk.Combobox(filter_row, textvariable=self.project_filter, state="readonly",
                                        width=15, style="Voice.TCombobox")
        self.project_box.pack(side="left")
        self.project_box.bind("<<ComboboxSelected>>", lambda _event: self.render())
        self.status_box = ttk.Combobox(filter_row, textvariable=self.status_filter, state="readonly",
                                       width=13, style="Voice.TCombobox")
        self.status_box.pack(side="left", padx=(8, 0))
        self.status_box.bind("<<ComboboxSelected>>", lambda _event: self.render())
        search = tk.Entry(filter_row, textvariable=self.search_value, bg="#f8fafb", fg=TEXT,
                          insertbackground=TEXT, relief="solid", bd=1, font=("Microsoft YaHei UI", 9))
        search.pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=6)
        search.insert(0, "")
        self.search_value.trace_add("write", lambda *_args: self.render())
        tk.Button(filter_row, text="刷新", command=lambda: self.refresh(force=True), bg=BLUE, fg="white",
                  activebackground="#1c5595", activeforeground="white", relief="flat", cursor="hand2",
                  padx=14, pady=5, font=("Microsoft YaHei UI", 9, "bold")).pack(side="left", padx=(8, 0))

        content = tk.Frame(self.root, bg=BG, highlightbackground="#cfd6dc", highlightthickness=1)
        content.pack(fill="both", expand=True, padx=16, pady=(14, 0))
        self.canvas = tk.Canvas(content, bg=BG, bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(content, orient="vertical", command=self.canvas.yview)
        self.list_frame = tk.Frame(self.canvas, bg=BG)
        self.window_id = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.list_frame.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.window_id, width=event.width))
        self.canvas.bind("<MouseWheel>", self.scroll)
        self.footer = tk.StringVar(value=f"工作区：{self.workspace}")
        tk.Label(self.root, textvariable=self.footer, bg=BG, fg=MUTED, anchor="w",
                 font=("Microsoft YaHei UI", 8)).pack(fill="x", padx=20, pady=(7, 10))

    def toggle_topmost(self) -> None:
        self.root.attributes("-topmost", self.topmost.get())

    def choose_workspace(self) -> None:
        selected = filedialog.askdirectory(title="选择包含项目注册表.json的工作区", initialdir=str(self.workspace))
        if not selected:
            return
        workspace = Path(selected)
        if not (workspace / "项目注册表.json").is_file():
            messagebox.showerror("工作区无效", "所选目录中没有项目注册表.json。", parent=self.root)
            return
        self.workspace = workspace.resolve()
        config = read_json(config_path(), {}) or {}
        config.update({"schema_version": 2, "workspace_root": str(self.workspace), "app_mode": "desktop-exe",
                       "copy_mode": "copy-only-no-overwrite", "updated_at": datetime.now(timezone.utc).isoformat()})
        atomic_json(config_path(), config)
        self.last_signature = None
        self.refresh(force=True)

    def refresh(self, force=False) -> None:
        try:
            rows = scan_workspace(self.workspace)
            signature = json.dumps(rows, ensure_ascii=False, sort_keys=True)
            if force or signature != self.last_signature:
                self.rows = rows
                self.last_signature = signature
                projects = ["全部项目"] + sorted({row["project"] for row in rows})
                statuses = ["全部状态"] + [stage for stage in STAGE_ORDER if any(
                    row["stage"] == stage for row in rows)]
                self.project_box.configure(values=projects)
                self.status_box.configure(values=statuses)
                if self.project_filter.get() not in projects:
                    self.project_filter.set("全部项目")
                if self.status_filter.get() not in statuses:
                    self.status_filter.set("全部状态")
                producing = sum(row["stage"] == "生产中" for row in rows)
                pullback = sum(row["stage"] == "待拉回" for row in rows)
                delivered = sum(row["stage"] == "已交付" for row in rows)
                issues = sum(row["requires_attention"] for row in rows)
                self.summary.set(f"全部 {len(rows)}  ·  生产中 {producing}  ·  待拉回 {pullback}  ·  已交付 {delivered}  ·  需处理 {issues}")
                self.footer.set(f"每2秒自动刷新  ·  工作区：{self.workspace}")
                self.render()
        except Exception as error:
            self.footer.set(f"读取失败：{error}")
        self.root.after(2000, self.refresh)

    def render(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()
        project, status, search = self.project_filter.get(), self.status_filter.get(), self.search_value.get().strip().lower()
        self.filtered = [row for row in self.rows
                         if (project == "全部项目" or row["project"] == project)
                         and (status == "全部状态" or row["stage"] == status)
                         and (not search or any(search in str(row[field]).lower() for field in (
                             "task_id", "role", "line", "script", "status", "stage", "next_action", "source_name")))]
        if not self.filtered:
            tk.Label(self.list_frame, text="没有符合条件的配音任务", bg=BG, fg=MUTED,
                     font=("Microsoft YaHei UI", 10), pady=50).pack(fill="x")
            return
        for row in self.filtered:
            self.render_task(row)
        self.bind_wheel(self.list_frame)

    def render_task(self, task: dict) -> None:
        card = tk.Frame(self.list_frame, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", padx=7, pady=(7, 0))
        top = tk.Frame(card, bg=PANEL)
        top.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(top, text=task["task_id"], bg=PANEL, fg=TEXT, width=17, anchor="w",
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        tk.Label(top, text=f"{task['project']} / {task['script']}", bg=PANEL, fg=MUTED, anchor="w",
                 font=("Microsoft YaHei UI", 8)).pack(side="left", fill="x", expand=True)
        status_color = {"已完成": GREEN, "已结束（含失败）": AMBER,
                        "已结束（全部失败）": RED, "拉回失败": RED, "素材缺失": RED,
                        "素材待选择": AMBER}.get(task["status"], BLUE if task["status"] in {"已提交", "生成中", "可拉回"} else MUTED)
        tk.Label(top, text=f"{task['stage']} · {task['status']}", bg=PANEL, fg=status_color, anchor="e",
                 font=("Microsoft YaHei UI", 9, "bold")).pack(side="right")

        meta = tk.Frame(card, bg=PANEL)
        meta.pack(fill="x", padx=12, pady=(0, 4))
        tk.Label(meta, text=f"角色：{task['role']}  ·  时长：{task['duration']}  ·  素材：{task['material']}",
                 bg=PANEL, fg=MUTED, anchor="w", font=("Microsoft YaHei UI", 8)).pack(fill="x")
        tk.Label(card, text=f"更新：{task['updated_at'] or '暂无'}  ·  来源：{task['source_name']}",
                 bg=PANEL, fg=MUTED, anchor="w", font=("Microsoft YaHei UI", 8)).pack(
                     fill="x", padx=12, pady=(0, 4))

        tk.Label(card, text=task["line"] or "（未填写台词）", bg=PANEL, fg="#3c4853", anchor="w",
                 justify="left", wraplength=620, font=("Microsoft YaHei UI", 9)).pack(
                     fill="x", padx=12, pady=(0, 7))

        progress = tk.Frame(card, bg=PANEL)
        progress.pack(fill="x", padx=12, pady=(0, 6))
        total, done = task["total"], task["done"]
        percent = round(done / total * 100) if total else 0
        ttk.Progressbar(progress, style="Voice.Horizontal.TProgressbar", maximum=100, value=percent,
                        length=180).pack(side="left", fill="x", expand=True)
        counts = (f"终态 {done}/{total}  成功 {task['success']}  失败 {task['failed']}  "
                  f"运行 {task['running']}  已下载 {task['downloaded']}") if total else "—"
        tk.Label(progress, text=counts, bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 8)).pack(side="left", padx=(10, 0))

        bottom = tk.Frame(card, bg=PANEL)
        bottom.pack(fill="x", padx=12, pady=(0, 10))
        action_color = RED if task["requires_attention"] else BLUE
        tk.Label(bottom, text=f"下一步：{task['next_action']}", bg=PANEL, fg=action_color,
                 anchor="w", font=("Microsoft YaHei UI", 8, "bold")).pack(side="left", fill="x", expand=True)
        if task["complete"]:
            tk.Button(bottom, text="成品链接", command=lambda key=task["key"]: self.open_output(key),
                      bg="#e8edf1", fg=TEXT, activebackground="#dbe2e7", relief="flat", cursor="hand2",
                      padx=10, pady=3, font=("Microsoft YaHei UI", 8)).pack(side="left", padx=(0, 6))
            tk.Button(bottom, text="复制到地址", command=lambda key=task["key"]: self.copy_dialog(key),
                      bg=GREEN, fg="white", activebackground="#115d42", activeforeground="white",
                      relief="flat", cursor="hand2", padx=10, pady=3,
                      font=("Microsoft YaHei UI", 8, "bold")).pack(side="left")

    def open_output(self, key: str) -> None:
        try:
            _, files = resolve_completed(self.workspace, key)
            folder = next((path.parent for path in files if path.suffix.lower() == ".mp3"), files[0].parent)
            os.startfile(folder)
        except Exception as error:
            messagebox.showerror("打开失败", str(error), parent=self.root)

    def copy_dialog(self, key: str) -> None:
        row = next(item for item in self.rows if item["key"] == key)
        dialog = tk.Toplevel(self.root)
        dialog.title("复制成品到地址")
        dialog.geometry("530x245")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=PANEL)
        tk.Label(dialog, text="复制成品到地址", bg=PANEL, fg=TEXT,
                 font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", padx=20, pady=(18, 5))
        tk.Label(dialog, text=f"{row['project']} · {row['task_id']} · {row['role']}", bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=20)
        value = tk.StringVar()
        error_text = tk.StringVar()
        entry = tk.Entry(dialog, textvariable=value, bg="#f8fafb", fg=TEXT, insertbackground=TEXT,
                         relief="solid", bd=1, font=("Microsoft YaHei UI", 10))
        entry.pack(fill="x", padx=20, pady=(16, 5), ipady=7)

        def strip_quotes(*_args) -> None:
            current = value.get()
            if '"' in current:
                value.set(current.replace('"', ""))
                error_text.set("地址不能包含双引号")

        value.trace_add("write", strip_quotes)
        tk.Label(dialog, textvariable=error_text, bg=PANEL, fg=RED, anchor="w",
                 font=("Microsoft YaHei UI", 8)).pack(fill="x", padx=20)
        tk.Label(dialog, text="只复制，不移动、不删除；目标任务文件夹已存在时不会覆盖。", bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", padx=20)
        actions = tk.Frame(dialog, bg=PANEL)
        actions.pack(side="bottom", fill="x", padx=20, pady=17)

        def submit() -> None:
            try:
                target, count = copy_completed(self.workspace, key, value.get())
                dialog.destroy()
                messagebox.showinfo("复制完成", f"已复制 {count} 个文件到：\n{target}", parent=self.root)
            except Exception as error:
                error_text.set(str(error))

        tk.Button(actions, text="取消", command=dialog.destroy, bg="#e8edf1", fg=TEXT,
                  relief="flat", cursor="hand2", padx=14, pady=5).pack(side="right")
        tk.Button(actions, text="提交并复制", command=submit, bg=GREEN, fg="white", activebackground="#115d42",
                  activeforeground="white", relief="flat", cursor="hand2", padx=14, pady=5,
                  font=("Microsoft YaHei UI", 9, "bold")).pack(side="right", padx=(0, 8))
        entry.bind("<Return>", lambda _event: submit())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        entry.focus_set()

    def scroll(self, event) -> str:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def bind_wheel(self, widget) -> None:
        widget.bind("<MouseWheel>", self.scroll)
        for child in widget.winfo_children():
            self.bind_wheel(child)

    def start_tray(self) -> None:
        if pystray is None:
            return
        image = Image.new("RGBA", (64, 64), (34, 94, 168, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((13, 10, 51, 54), radius=5, fill="white")
        for y, width in ((21, 25), (31, 30), (41, 20)):
            draw.rounded_rectangle((20, y, 20 + width, y + 4), radius=2, fill=(34, 94, 168, 255))
        menu = pystray.Menu(
            pystray.MenuItem("显示看板", lambda _icon, _item: self.root.after(0, self.show_window), default=True),
            pystray.MenuItem("退出", lambda _icon, _item: self.root.after(0, self.quit_app)),
        )
        self.tray_icon = pystray.Icon("voice-dashboard", image, "配音任务看板", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_to_tray(self) -> None:
        if self.tray_icon:
            self.root.withdraw()
        else:
            self.quit_app()

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()

    def quit_app(self) -> None:
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()


def resolve_workspace(cli_workspace: Path | None) -> Path:
    if cli_workspace:
        return cli_workspace.resolve()
    config = read_json(config_path(), {}) or {}
    raw = config.get("workspace_root") if isinstance(config, dict) else None
    if raw:
        return Path(str(raw)).resolve()
    raise ValueError("看板尚未配置工作区，请重新运行安装包或传入 --workspace-root")


def main() -> int:
    parser = argparse.ArgumentParser(description="多项目配音任务桌面看板")
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--scan-json", action="store_true", help="输出扫描结果后退出，用于验收")
    args = parser.parse_args()
    try:
        workspace = resolve_workspace(args.workspace_root)
    except ValueError as error:
        if args.scan_json:
            print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
            return 2
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("看板未配置", str(error), parent=root)
        root.destroy()
        return 2
    if args.scan_json:
        print(json.dumps({"ok": True, "workspace": str(workspace), "tasks": scan_workspace(workspace)}, ensure_ascii=False, indent=2))
        return 0
    root = tk.Tk()
    VoiceDashboard(root, workspace)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
