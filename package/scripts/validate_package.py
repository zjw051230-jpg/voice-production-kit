#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REQUIRED_PACKAGE = (
    "START-HERE.md", "INSTALL.md", "manifest.json", "install.ps1",
    "program/配音任务看板.exe",
)
FORBIDDEN_NAMES = {
    "cc-switch.exe", "cc-switch.db", "Seedance API配置工具.exe",
    "配置Seedance API.ps1", "credentials.json", "doubao_api_config.json",
    ".env", "providers.json", "provider.json", "task-log.jsonl",
}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm"}
FORBIDDEN_MATERIAL_PARTS = {"角色音色素材", "文字素材", "已生成视频", "已转mp3", "1.projects", "2.submission", "6.snapshot"}
SECRET_PATTERNS = (
    re.compile(r'"(?:api[_-]?key|token|secret)"\s*:\s*"(?!YOUR_API_KEY|你的API_KEY|请在本机填写|<[^>]+>|\*+|\$\{|self\.)[^"]{10,}"', re.I),
    re.compile(r"\b(?:sk|gh[opsu])[-_][A-Za-z0-9_-]{20,}\b"),
)


def validate_package(package: Path) -> tuple[list[str], dict]:
    errors: list[str] = []
    for relative in REQUIRED_PACKAGE:
        if not (package / relative).is_file():
            errors.append(f"missing package file: {relative}")
    try:
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid manifest: {exc}"], {}
    if manifest.get("version") != "2.2":
        errors.append("manifest version must be 2.2")
    if manifest.get("environment_dependency") != "env4BC":
        errors.append("environment dependency must be env4BC")
    if set(manifest.get("bundled_programs", {})) != {"voice_dashboard"}:
        errors.append("voice package may bundle only the voice dashboard")
    for skill in manifest.get("skills", []):
        if not (package / "skills" / skill / "SKILL.md").is_file():
            errors.append(f"missing skill: {skill}")

    for path in package.rglob("*"):
        rel = path.relative_to(package)
        lowered = {part.lower() for part in rel.parts}
        if "__pycache__" in lowered or path.suffix.lower() == ".pyc":
            errors.append(f"cache file: {rel}")
        if any(part.lower() in lowered for part in FORBIDDEN_MATERIAL_PARTS):
            errors.append(f"material/runtime directory: {rel}")
        if not path.is_file():
            continue
        if path.name.lower() in {item.lower() for item in FORBIDDEN_NAMES}:
            errors.append(f"environment/private file: {rel}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"database file: {rel}")
        if path.suffix.lower() in {".md", ".json", ".py", ".pyw", ".ps1", ".txt"}:
            content = path.read_text(encoding="utf-8-sig", errors="ignore")
            if any(pattern.search(content) for pattern in SECRET_PATTERNS):
                errors.append(f"possible secret: {rel}")
    return errors, manifest


def validate_install(workspace: Path, project_name: str, codex_home: Path, manifest: dict) -> list[str]:
    errors: list[str] = []
    registry_path = workspace / "项目注册表.json"
    if not registry_path.is_file():
        return ["workspace project registry is missing"]
    registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    entry = registry.get("projects", {}).get(project_name)
    if not entry:
        return [f"project is not registered: {project_name}"]
    project = Path(entry["project_root"])
    for dirname in ("01_输入资料", "02_生产成品", "03_交付与版本", "04_管理与记录", ".codex"):
        if not (project / dirname).is_dir():
            errors.append(f"project directory missing: {dirname}")
    for skill in manifest.get("skills", []):
        if not (codex_home / "skills" / skill / "SKILL.md").is_file():
            errors.append(f"installed skill missing: {skill}")
    dashboard = workspace / ".codex-dashboard" / "app" / "配音任务看板.exe"
    config = dashboard.parent / "dashboard-config.json"
    if not dashboard.is_file() or not config.is_file():
        errors.append("installed voice dashboard is incomplete")
    if (workspace / ".codex-tools").exists():
        errors.append("voice installer must not create environment tool directory")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", required=True, type=Path)
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--project-name")
    parser.add_argument("--codex-home", type=Path)
    args = parser.parse_args()
    errors, manifest = validate_package(args.package_root.resolve())
    if args.workspace_root and args.project_name and args.codex_home:
        errors.extend(validate_install(args.workspace_root.resolve(), args.project_name, args.codex_home.resolve(), manifest))
    if errors:
        print("VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(json.dumps({"status": "OK", "version": manifest["version"], "environment_dependency": "env4BC", "materials_touched": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
