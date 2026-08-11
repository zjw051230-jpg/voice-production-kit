#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from manage_api_pool import ENVIRONMENT_HOSTS, pool_paths, read_json, save_manual_keys

BG = "#f3f5f6"
PANEL = "#ffffff"
TEXT = "#172027"
MUTED = "#66737c"
BORDER = "#d6dde1"
BLUE = "#225ea8"


def app_dir() -> Path:
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


def load_tool_config() -> dict:
    path = app_dir() / "api-tool-config.json"
    return read_json(path, {}) or {}


def load_projects(workspace: Path) -> list[tuple[str, Path]]:
    registry = read_json(workspace / "项目注册表.json", {}) or {}
    result: list[tuple[str, Path]] = []
    for name, entry in registry.get("projects", {}).items():
        if isinstance(entry, dict) and entry.get("active") is False:
            continue
        raw = entry.get("project_root") if isinstance(entry, dict) else entry
        if raw:
            result.append((str(name), Path(str(raw)).resolve()))
    return sorted(result, key=lambda item: item[0])


def load_environment_keys(project: Path, environment: str) -> list[dict]:
    paths = pool_paths(project)
    index = read_json(paths["index"], {}) or {}
    indexed = {
        item.get("fingerprint"): item
        for item in index.get("configs", [])
        if item.get("fingerprint")
    }
    result: list[dict] = []
    for config_path in sorted((paths["pool"] / environment).glob("*.json")):
        config = read_json(config_path, {}) or {}
        key = str(config.get("api_key") or "").strip()
        if not key:
            continue
        import hashlib
        fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        meta = indexed.get(fingerprint, {})
        result.append({
            "api_key": key,
            "fingerprint": fingerprint,
            "status": meta.get("status", "available"),
            "active": index.get("environment") == environment and index.get("active_id") == meta.get("id"),
        })
    return result


class ApiConfigApp:
    def __init__(self, root: tk.Tk, workspace: Path) -> None:
        self.root = root
        self.workspace = workspace
        self.projects: dict[str, Path] = {}
        self.keys: list[dict] = []
        self.project_name = tk.StringVar()
        self.environment = tk.StringVar(value="test")
        self.key_value = tk.StringVar()
        self.show_key = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="请选择项目并添加 API Key")
        root.title("Seedance API 配置工具")
        root.geometry("700x620")
        root.minsize(620, 560)
        root.configure(bg=BG)
        self._styles()
        self._build()
        self.refresh_projects()

    def _styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Tool.TCombobox", padding=6)

    def _build(self) -> None:
        header = tk.Frame(self.root, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x")
        tk.Label(header, text="Seedance API 配置工具", bg=PANEL, fg=TEXT,
                 font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w", padx=20, pady=(16, 3))
        tk.Label(header, text="本机录入，自动去重、整理并生成项目活动配置", bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=20, pady=(0, 15))

        form = tk.Frame(self.root, bg=BG)
        form.pack(fill="x", padx=22, pady=(18, 10))
        tk.Label(form, text="项目", bg=BG, fg=TEXT, font=("Microsoft YaHei UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        self.project_box = ttk.Combobox(form, textvariable=self.project_name, state="readonly", style="Tool.TCombobox")
        self.project_box.grid(row=1, column=0, sticky="ew", pady=(5, 14))
        self.project_box.bind("<<ComboboxSelected>>", lambda _e: self.reload_keys())
        tk.Button(form, text="刷新", command=self.refresh_projects, bg="#e4e9ec", fg=TEXT,
                  relief="flat", padx=14, pady=5).grid(row=1, column=1, padx=(8, 0), pady=(5, 14))

        tk.Label(form, text="线路", bg=BG, fg=TEXT, font=("Microsoft YaHei UI", 9, "bold")).grid(row=2, column=0, sticky="w")
        mode = tk.Frame(form, bg=BG)
        mode.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 14))
        for label, value in (("test版", "test"), ("正式版", "production")):
            tk.Radiobutton(mode, text=label, variable=self.environment, value=value, command=self.reload_keys,
                           bg=BG, activebackground=BG, selectcolor=BG, fg=TEXT,
                           font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(0, 20))

        tk.Label(form, text="API Key", bg=BG, fg=TEXT, font=("Microsoft YaHei UI", 9, "bold")).grid(row=4, column=0, sticky="w")
        entry_row = tk.Frame(form, bg=BG)
        entry_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(5, 5))
        entry_row.columnconfigure(0, weight=1)
        self.key_entry = tk.Entry(entry_row, textvariable=self.key_value, show="*", bg=PANEL, fg=TEXT,
                                  insertbackground=TEXT, relief="solid", bd=1, font=("Consolas", 10))
        self.key_entry.grid(row=0, column=0, sticky="ew", ipady=7)
        tk.Button(entry_row, text="添加 API", command=self.add_key, bg=BLUE, fg="white",
                  activebackground="#1c5595", activeforeground="white", relief="flat",
                  padx=16, pady=7).grid(row=0, column=1, padx=(8, 0))
        tk.Checkbutton(form, text="显示输入内容", variable=self.show_key, command=self.toggle_key,
                       bg=BG, activebackground=BG, selectcolor=BG, fg=MUTED,
                       font=("Microsoft YaHei UI", 8)).grid(row=6, column=0, sticky="w")
        form.columnconfigure(0, weight=1)

        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(side="bottom", fill="x", padx=22, pady=(2, 12))
        actions = tk.Frame(bottom, bg=BG)
        actions.pack(fill="x")
        tk.Button(actions, text="删除选中", command=self.remove_selected, bg="#e9edef", fg=TEXT,
                  relief="flat", padx=13, pady=6).pack(side="left")
        tk.Button(actions, text="设为当前", command=self.set_active, bg="#e9edef", fg=TEXT,
                  relief="flat", padx=13, pady=6).pack(side="left", padx=(8, 0))
        self.save_button = tk.Button(
            actions, text="保存并生成配置", command=lambda: self.save(show_success=True), bg=BLUE, fg="white",
            activebackground="#1c5595", activeforeground="white", relief="flat",
            padx=18, pady=7, font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.save_button.pack(side="right")
        tk.Label(bottom, textvariable=self.status, bg=BG, fg=MUTED, anchor="w",
                 font=("Microsoft YaHei UI", 8)).pack(fill="x", pady=(8, 0))

        table_frame = tk.Frame(self.root, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        table_frame.pack(fill="both", expand=True, padx=22, pady=(4, 10))
        self.table = ttk.Treeview(table_frame, columns=("label", "tail", "status"), show="headings", height=4)
        self.table.heading("label", text="本地编号")
        self.table.heading("tail", text="密钥标识")
        self.table.heading("status", text="状态")
        self.table.column("label", width=150, anchor="w")
        self.table.column("tail", width=210, anchor="w")
        self.table.column("status", width=140, anchor="center")
        self.table.pack(fill="both", expand=True, padx=10, pady=(10, 5))

    def current_project(self) -> Path | None:
        return self.projects.get(self.project_name.get())

    def refresh_projects(self) -> None:
        previous = self.project_name.get()
        self.projects = dict(load_projects(self.workspace))
        names = list(self.projects)
        self.project_box.configure(values=names)
        self.project_name.set(previous if previous in self.projects else (names[0] if names else ""))
        self.reload_keys()

    def reload_keys(self) -> None:
        project = self.current_project()
        self.keys = load_environment_keys(project, self.environment.get()) if project else []
        self.render_keys()

    def toggle_key(self) -> None:
        self.key_entry.configure(show="" if self.show_key.get() else "*")

    def add_key(self) -> None:
        value = self.key_value.get().strip()
        if not value:
            messagebox.showwarning("未输入 API Key", "请输入 API Key 后再添加。", parent=self.root)
            return
        import hashlib
        fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
        if any(item["fingerprint"] == fingerprint for item in self.keys):
            self.key_value.set("")
            self.status.set("该 API 已存在，未重复添加")
            return
        self.keys.append({"api_key": value, "fingerprint": fingerprint, "status": "available", "active": not self.keys})
        self.key_value.set("")
        self.render_keys()
        self.save(show_success=False)

    def render_keys(self) -> None:
        for row in self.table.get_children():
            self.table.delete(row)
        for number, item in enumerate(self.keys, 1):
            state = "当前" if item.get("active") else ("余额不足" if item.get("status") == "exhausted" else "可用")
            self.table.insert("", "end", iid=item["fingerprint"], values=(f"API {number:02d}", f"********{item['fingerprint'][-4:]}", state))
        project = self.current_project()
        endpoint = f"https://{ENVIRONMENT_HOSTS[self.environment.get()]}/v1"
        self.status.set(f"{len(self.keys)} 份 API | {endpoint}" + (f" | {project}" if project else " | 未找到项目"))

    def remove_selected(self) -> None:
        selected = set(self.table.selection())
        if not selected:
            return
        if len(selected) >= len(self.keys):
            messagebox.showwarning("至少保留一项", "API 池中至少需要保留一份 API。", parent=self.root)
            return
        self.keys = [item for item in self.keys if item["fingerprint"] not in selected]
        if self.keys and not any(item.get("active") for item in self.keys):
            self.keys[0]["active"] = True
        self.render_keys()
        self.save(show_success=False)

    def set_active(self) -> None:
        selected = self.table.selection()
        if len(selected) != 1:
            messagebox.showwarning("请选择一项", "请选择一份 API 设为当前。", parent=self.root)
            return
        for item in self.keys:
            item["active"] = item["fingerprint"] == selected[0]
        self.render_keys()
        self.save(show_success=False)

    def save(self, show_success: bool = True) -> bool:
        project = self.current_project()
        if not project:
            messagebox.showerror("没有项目", "工作区中没有可用项目。", parent=self.root)
            return False
        try:
            active = next((item["fingerprint"] for item in self.keys if item.get("active")), None)
            result = save_manual_keys(project, self.environment.get(), [item["api_key"] for item in self.keys], active)
            self.reload_keys()
            self.status.set(f"保存成功：{result['config_count']} 份配置，已生成 {result['active_config']}")
            if show_success:
                messagebox.showinfo("配置完成", f"已整理 {result['config_count']} 份 API，并生成项目活动配置。", parent=self.root)
            return True
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.root)
            return False


def main() -> int:
    config = load_tool_config()
    workspace = Path(str(config.get("workspace_root") or "")).resolve()
    if not (workspace / "项目注册表.json").is_file():
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("配置缺失", "未找到工作区项目注册表，请重新运行安装器。")
        return 1
    root = tk.Tk()
    ApiConfigApp(root, workspace)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
