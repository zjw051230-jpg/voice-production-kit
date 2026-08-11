#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def backup(path: Path) -> Path:
    target = path.with_name(f"{path.name}.{stamp()}.bak")
    shutil.copy2(path, target)
    return target


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(temp.read_text(encoding="utf-8"))
    os.replace(temp, path)


def replace_values(value, old: str, new: str):
    if isinstance(value, str):
        return new + value[len(old):] if value.lower().startswith(old.lower()) else value
    if isinstance(value, list):
        return [replace_values(x, old, new) for x in value]
    if isinstance(value, dict):
        return {k: replace_values(v, old, new) for k, v in value.items()}
    return value


def discover_projects(workspace: Path) -> dict:
    projects = {}
    for child in workspace.iterdir() if workspace.exists() else []:
        if child.is_dir() and (child / ".codex").is_dir():
            projects[child.name] = {"project_root": str(child.resolve()), "active": True, "recovered_at": datetime.now().astimezone().isoformat()}
    return projects


def registry_projects(workspace: Path) -> tuple[Path, dict]:
    path = workspace / "项目注册表.json"
    if not path.exists():
        return path, {}
    data = read_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("projects"), dict):
        raise ValueError("项目注册表格式错误")
    return path, data["projects"]


def check_writable(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    probe = path / f".dashboard-write-test-{os.getpid()}"
    try:
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
        return True
    except OSError:
        return False


def compatibility_issues(project: Path) -> list[tuple[Path, Path]]:
    mapping_path = project / "04_管理与记录" / "02_操作日志与索引" / "目录兼容映射.json"
    if not mapping_path.exists():
        return []
    mapping = read_json(mapping_path)
    issues = []
    for category, names in mapping.items():
        if not isinstance(names, dict):
            continue
        for readable, legacy in names.items():
            target = project / category / readable
            link = project / legacy
            if target.is_dir() and not link.exists():
                issues.append((link, target))
    return issues


def create_junction(link: Path, target: Path) -> None:
    if os.name != "nt":
        link.symlink_to(target, target_is_directory=True)
        return
    completed = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
    if completed.returncode:
        raise OSError(completed.stderr.strip() or completed.stdout.strip())
    subprocess.run(["attrib", "+h", str(link)], capture_output=True)


def append_reports(projects: dict, lines: list[str]) -> None:
    body = f"\n## {datetime.now().astimezone().isoformat()}\n\n" + "\n".join(f"- {x}" for x in lines) + "\n"
    for entry in projects.values():
        root = Path(entry["project_root"])
        report = root / "04_管理与记录" / "03_问题与改进" / "看板修复记录.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        if not report.exists():
            report.write_text("# 看板修复记录\n", encoding="utf-8")
        with report.open("a", encoding="utf-8") as stream:
            stream.write(body)


def desktop_path() -> Path:
    override = os.environ.get("VOICE_DASHBOARD_DESKTOP", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "[Console]::Write([Environment]::GetFolderPath('Desktop'))"],
        capture_output=True, text=True,
    )
    return Path(completed.stdout.strip()) if completed.returncode == 0 and completed.stdout.strip() else Path.home() / "Desktop"


def shortcut_target(shortcut: Path) -> Path | None:
    env = os.environ.copy()
    env["VOICE_DASHBOARD_LINK"] = str(shortcut)
    command = "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:VOICE_DASHBOARD_LINK);[Console]::Write($s.TargetPath)"
    completed = subprocess.run(["powershell", "-NoProfile", "-Command", command], env=env,
                               capture_output=True, text=True)
    return Path(completed.stdout.strip()) if completed.returncode == 0 and completed.stdout.strip() else None


def create_shortcut(executable: Path, app_dir: Path) -> Path:
    desktop = desktop_path()
    shortcut = desktop / "配音任务看板.lnk"
    env = os.environ.copy()
    env.update({"VOICE_DASHBOARD_EXE": str(executable), "VOICE_DASHBOARD_DIR": str(app_dir),
                "VOICE_DASHBOARD_LINK": str(shortcut)})
    command = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:VOICE_DASHBOARD_LINK);"
        "$s.TargetPath=$env:VOICE_DASHBOARD_EXE;"
        "$s.WorkingDirectory=$env:VOICE_DASHBOARD_DIR;"
        "$s.Description='多项目配音任务看板';$s.Save()"
    )
    completed = subprocess.run(["powershell", "-NoProfile", "-Command", command], env=env,
                               capture_output=True, text=True)
    if completed.returncode:
        raise OSError(completed.stderr.strip() or "创建桌面快捷方式失败")
    return shortcut


def rebuild_exe(source: Path, output_dir: Path) -> Path:
    if subprocess.run([sys.executable, "-m", "PyInstaller", "--version"], capture_output=True).returncode:
        raise RuntimeError("缺少 PyInstaller，无法自动重建 EXE；请重新运行安装包")
    build_root = Path(tempfile.mkdtemp(prefix="voice-dashboard-build-"))
    try:
        completed = subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
            "--name", "配音任务看板", "--distpath", str(output_dir), "--workpath", str(build_root / "work"),
            "--specpath", str(build_root), str(source),
        ], capture_output=True, text=True)
        if completed.returncode:
            raise RuntimeError(completed.stderr[-2000:] or "PyInstaller 构建失败")
    finally:
        shutil.rmtree(build_root, ignore_errors=True)
    return output_dir / "配音任务看板.exe"


def main() -> int:
    parser = argparse.ArgumentParser(description="检查并修复配音任务看板")
    parser.add_argument("--workspace-root", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--repair", action="store_true")
    parser.add_argument("--old-prefix")
    parser.add_argument("--new-prefix")
    args = parser.parse_args()
    if bool(args.old_prefix) != bool(args.new_prefix):
        parser.error("--old-prefix 与 --new-prefix 必须同时提供")

    workspace = args.workspace_root.resolve()
    findings: list[str] = []
    actions: list[str] = []
    registry_path = workspace / "项目注册表.json"
    try:
        _, projects = registry_projects(workspace)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        findings.append(f"项目注册表不可用：{exc}")
        projects = {}

    if not projects:
        recovered = discover_projects(workspace)
        findings.append(f"项目注册表缺失或无项目，可发现 {len(recovered)} 个项目")
        if args.repair and recovered:
            if registry_path.exists():
                backup(registry_path)
            write_json(registry_path, {"schema_version": 1, "projects": recovered})
            projects = recovered
            actions.append("已重建项目注册表")

    metadata_files = [registry_path] if registry_path.exists() else []
    for entry in projects.values():
        root = Path(entry.get("project_root", ""))
        if not root.exists():
            findings.append(f"项目路径不存在：{root}")
        else:
            if not check_writable(root):
                findings.append(f"项目目录不可写：{root}")
            metadata_files.extend((root / ".codex").rglob("*.json") if (root / ".codex").exists() else [])
            for link, target in compatibility_issues(root):
                findings.append(f"兼容目录联接缺失：{link} -> {target}")
                if args.repair:
                    create_junction(link, target)
                    actions.append(f"已重建联接：{link.name}")

    if args.old_prefix and args.new_prefix:
        for path in metadata_files:
            try:
                data = read_json(path)
                replaced = replace_values(data, args.old_prefix, args.new_prefix)
                if replaced != data:
                    if args.repair:
                        backup(path)
                        write_json(path, replaced)
                        actions.append(f"已修复路径：{path}")
                    else:
                        findings.append(f"包含待替换旧路径：{path}")
            except (OSError, json.JSONDecodeError) as exc:
                findings.append(f"JSON 无法读取：{path}：{exc}")

    hidden = workspace / ".codex-dashboard"
    app = hidden / "app"
    config = app / "dashboard-config.json"
    executable = app / "配音任务看板.exe"
    installed_source = app / "voice_dashboard.py"
    dashboard_script = Path(__file__).resolve().parents[2] / "voice-production-dashboard" / "scripts" / "voice_dashboard.py"
    if not dashboard_script.exists():
        findings.append("看板 skill 源程序缺失，请从安装包重新安装")
    if not executable.exists():
        findings.append("配音任务看板.exe 缺失")
        if args.repair and dashboard_script.exists():
            app.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dashboard_script, installed_source)
            rebuild_exe(installed_source, app)
            actions.append("已重建配音任务看板.exe")
    if not config.exists():
        findings.append("看板配置缺失")
        if args.repair:
            app.mkdir(parents=True, exist_ok=True)
            write_json(config, {"schema_version": 2, "workspace_root": str(workspace),
                                "app_mode": "desktop-exe", "copy_mode": "copy-only-no-overwrite",
                                "updated_at": datetime.now().astimezone().isoformat()})
            actions.append("已初始化看板配置")
    else:
        try:
            cfg = read_json(config)
            if (Path(cfg.get("workspace_root", "")).resolve() != workspace
                    or cfg.get("app_mode") != "desktop-exe"
                    or cfg.get("copy_mode") != "copy-only-no-overwrite"):
                findings.append("看板配置中的工作区或程序模式不正确")
                if args.repair:
                    backup(config)
                    cfg.update({"schema_version": 2, "workspace_root": str(workspace),
                                "app_mode": "desktop-exe", "copy_mode": "copy-only-no-overwrite",
                                "updated_at": datetime.now().astimezone().isoformat()})
                    write_json(config, cfg)
                    actions.append("已更新看板配置")
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            findings.append(f"看板配置损坏：{exc}")
            if args.repair:
                backup(config)
                write_json(config, {"schema_version": 2, "workspace_root": str(workspace),
                                    "app_mode": "desktop-exe", "copy_mode": "copy-only-no-overwrite",
                                    "updated_at": datetime.now().astimezone().isoformat()})
                actions.append("已重建看板配置")

    shortcut = desktop_path() / "配音任务看板.lnk"
    current_target = shortcut_target(shortcut) if shortcut.exists() else None
    if not shortcut.exists() or not current_target or current_target.resolve() != executable.resolve():
        findings.append("桌面快捷方式缺失或目标错误")
        if args.repair and executable.exists():
            create_shortcut(executable, app)
            actions.append("已重建或修正桌面快捷方式")

    result_lines = findings + (actions if actions else ["未执行配置修改"])
    if args.repair and projects:
        append_reports(projects, result_lines)
    unresolved_prefixes = ("项目路径不存在", "项目目录不可写", "JSON 无法读取", "看板 skill 源程序缺失")
    unresolved = [item for item in findings if item.startswith(unresolved_prefixes)]
    if args.repair and not projects:
        unresolved.append("没有可用项目")
    ok = not findings if args.check else not unresolved
    print(json.dumps({"ok": ok, "mode": "repair" if args.repair else "check", "findings": findings,
                      "actions": actions, "unresolved": unresolved}, ensure_ascii=False, indent=2))
    return 0 if not findings or args.repair else 1


if __name__ == "__main__":
    raise SystemExit(main())
