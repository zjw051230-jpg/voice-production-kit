#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_PROJECT_DIRS = {
    "01_输入资料", "02_生产成品", "03_交付与版本", "04_管理与记录",
}
LEGACY_MAPPING = {
    "角色音色素材": "01_输入资料/01_角色音色参考",
    "剧情总览": "01_输入资料/02_剧情与剧本",
    "文字素材": "01_输入资料/03_配音任务",
    "素材": "01_输入资料/04_临时素材",
    "已生成视频": "02_生产成品/01_生成视频",
    "已转mp3": "02_生产成品/02_MP3音频",
    "1提交资料": "03_交付与版本/01_待提交资料",
    "2版本": "03_交付与版本/02_工作版本",
    "8版本": "03_交付与版本/03_历史版本",
    "apis": "04_管理与记录/01_API配置",
    "0日志信息": "04_管理与记录/02_操作日志与索引",
    "问题与改进log": "04_管理与记录/03_问题与改进",
    "垃圾桶": "04_管理与记录/04_回收归档",
}
SUSPICIOUS_SECRET = re.compile(r'(?i)(api[_-]?key|token|secret)\s*[=:]\s*["\'](?!请|your|<|\$)[A-Za-z0-9_\-]{16,}')


def fail(message: str) -> None:
    raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="离线验证可移植配音工作流")
    parser.add_argument("--package-root", required=True, type=Path)
    parser.add_argument("--workspace-root", required=True, type=Path)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--codex-home", required=True, type=Path)
    args = parser.parse_args()

    package = args.package_root.resolve()
    if any(path.is_dir() and path.name == "__pycache__" for path in package.rglob("__pycache__")):
        fail("安装包包含不应发布的 __pycache__")
    if any("update_codex_board" in path.name for path in package.rglob("*")):
        fail("安装包包含已废弃的 codex-board 工具")
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8-sig"))
    for required in (
        "START-HERE.md",
        "INSTALL.md",
        "API与CCSwitch配置.md",
        "详细使用手册.md",
        "配置Seedance API.ps1",
        "install-ccswitch.ps1",
        "scripts/configure_ccswitch_model.py",
    ):
        if not (package / required).is_file():
            fail(f"安装包缺少配置教学或工具：{required}")
    registry = json.loads((args.workspace_root / "项目注册表.json").read_text(encoding="utf-8-sig"))
    project_entry = registry.get("projects", {}).get(args.project_name)
    if not project_entry:
        fail(f"项目未注册：{args.project_name}")
    project = Path(project_entry["project_root"])
    missing_dirs = sorted(REQUIRED_PROJECT_DIRS - {item.name for item in project.iterdir() if item.is_dir()})
    if missing_dirs:
        fail("项目目录缺失：" + "、".join(missing_dirs))

    for rel in ("0日志信息/任务操作日志.md", "0日志信息/地址索引.json", "问题与改进log/问题建议.md"):
        if not (project / rel).exists():
            fail(f"项目基础文件缺失：{rel}")
    json.loads((project / "0日志信息" / "地址索引.json").read_text(encoding="utf-8-sig"))

    mapping_path = project / "04_管理与记录" / "02_操作日志与索引" / "目录兼容映射.json"
    json.loads(mapping_path.read_text(encoding="utf-8-sig"))
    for legacy_name, target_relative in LEGACY_MAPPING.items():
        legacy = project / legacy_name
        target = project / target_relative
        if not target.is_dir():
            fail(f"人类可读目录缺失：{target_relative}")
        if sys.platform == "win32" and not getattr(legacy, "is_junction", lambda: False)():
            fail(f"旧工具路径不是目录联接：{legacy_name}")
        if legacy.resolve() != target.resolve():
            fail(f"旧工具路径映射错误：{legacy_name} -> {target_relative}")

    metadata = project / ".codex"
    if not metadata.is_dir():
        fail("项目缺少 .codex 隐藏管理目录")
    if sys.platform == "win32" and not (metadata.stat().st_file_attributes & 2):
        fail(".codex 未设置 Windows 隐藏属性")
    assets = json.loads((metadata / "01_素材状态与选用.json").read_text(encoding="utf-8-sig"))
    dialogue = json.loads((metadata / "02_台词ID位置索引.json").read_text(encoding="utf-8-sig"))
    if not isinstance(assets.get("角色素材"), dict):
        fail("素材状态文件缺少角色素材映射")
    if not isinstance(dialogue.get("台词"), dict):
        fail("台词位置索引缺少台词映射")
    if not (metadata / "任务清单").is_dir():
        fail(".codex 缺少任务清单目录")
    chat_table = json.loads((metadata / "03_codexchat对应表.json").read_text(encoding="utf-8-sig"))
    expected_chats = {"理解文本与任务", "提示词", "生成", "监控", "拉回", "记录"}
    if set(chat_table.get("chats", {})) != expected_chats:
        fail("codexchat对应表缺少固定的六个Chat")
    if not isinstance(chat_table.get("pending_retries"), dict):
        fail("codexchat对应表缺少定时重试登记表")
    for name, chat in chat_table["chats"].items():
        if chat.get("status") not in (0, 1):
            fail(f"Chat status必须是0或1：{name}")
        if not chat.get("model") or not chat.get("reasoning_effort") or not chat.get("prompt"):
            fail(f"Chat缺少模型、推理强度或提示词：{name}")
        if chat.get("full_access_required") is not True or not isinstance(chat.get("skills"), list):
            fail(f"Chat缺少完全访问或技能索引要求：{name}")
        if chat.get("initial_message") != "这个对话开启完全访问，不需要问我要任何的批准。":
            fail(f"Chat缺少固定完全访问初始化消息：{name}")
        if "verify-access" not in chat.get("prompt", ""):
            fail(f"Chat缺少实际权限探测要求：{name}")
        for field in ("active_task", "waiting_for_feedback"):
            if field not in chat:
                fail(f"Chat缺少租约或等待字段：{name}/{field}")
        if "lease_id" not in chat.get("prompt", ""):
            fail(f"Chat缺少任务租约要求：{name}")
    record_chat = chat_table["chats"]["记录"]
    if (
        record_chat.get("feedback_required") is not False
        or record_chat.get("feedback_to") is not None
        or record_chat.get("next_chat") is not None
        or chat_table.get("record_is_one_way") is not True
        or chat_table.get("record_reports_to_owner") is not False
    ):
        fail("记录Chat必须是无反馈的单向终止阶段")
    if "禁止调用prepare-handoff" not in record_chat.get("prompt", ""):
        fail("记录Chat提示词缺少禁止汇报硬约束")
        if "04_API池状态.json" not in chat.get("prompt", ""):
            fail(f"Chat缺少API余额暂停协议：{name}")
    api_state_path = metadata / "04_API池状态.json"
    api_document = metadata / "04_API池与余额切换.md"
    api_index_path = project / "apis" / "api_pool" / "index.json"
    if not api_state_path.is_file() or not api_document.is_file() or not api_index_path.is_file():
        fail("项目缺少API池状态、隐藏说明或索引")
    api_state = json.loads(api_state_path.read_text(encoding="utf-8-sig"))
    api_index = json.loads(api_index_path.read_text(encoding="utf-8-sig"))
    if not isinstance(api_state.get("workflow_paused"), bool):
        fail("API池状态缺少workflow_paused布尔值")
    if not isinstance(api_index.get("configs"), list):
        fail("API池索引缺少configs数组")
    for task_id, entry in dialogue["台词"].items():
        if not isinstance(entry, dict):
            fail(f"台词位置条目格式错误：{task_id}")
        info_path = Path(entry.get("资料索引", ""))
        change_path = Path(entry.get("改动记录", ""))
        if not info_path.is_file() or not change_path.is_file():
            fail(f"台词任务清单文件缺失：{task_id}")
        info = json.loads(info_path.read_text(encoding="utf-8-sig"))
        if info.get("task_ID") != task_id or info.get("台词") != entry.get("台词"):
            fail(f"台词索引与资料索引不一致：{task_id}")

    for skill in manifest["skills"]:
        installed = args.codex_home / "skills" / skill
        if not (installed / "SKILL.md").exists():
            fail(f"技能未安装：{skill}")

    package_exe = package / "program" / "配音任务看板.exe"
    if not package_exe.is_file() or package_exe.stat().st_size < 1_000_000:
        fail("安装包缺少有效的配音任务看板.exe")
    api_tool_package = package / "program" / "Seedance API配置工具.exe"
    if not api_tool_package.is_file() or api_tool_package.stat().st_size < 1_000_000:
        fail("安装包缺少有效的 Seedance API配置工具.exe")
    cc_switch_exe = package / "program" / "cc-switch" / "cc-switch.exe"
    if not cc_switch_exe.is_file() or cc_switch_exe.stat().st_size < 10_000_000:
        fail("安装包缺少有效的 CC Switch 程序本体")
    if b"cc-switch-local-proxy-exact-model-routes-v1" not in cc_switch_exe.read_bytes():
        fail("CC Switch 程序不支持内部精确模型路由")
    if not (package / "program" / "cc-switch" / "LICENSE").is_file():
        fail("安装包缺少 CC Switch MIT 许可文件")
    if any(path.suffix.lower() in {".db", ".db-wal", ".db-shm"} for path in package.rglob("*")):
        fail("安装包包含 CC Switch 或其他实时数据库")
    dashboard_app = args.workspace_root / ".codex-dashboard" / "app"
    dashboard_exe = dashboard_app / "配音任务看板.exe"
    if not dashboard_exe.is_file():
        fail("工作区缺少配音任务看板.exe")
    dashboard_config = dashboard_app / "dashboard-config.json"
    if not dashboard_config.is_file():
        fail("工作区缺少看板配置")
    dashboard = json.loads(dashboard_config.read_text(encoding="utf-8-sig"))
    if dashboard.get("app_mode") != "desktop-exe" or dashboard.get("copy_mode") != "copy-only-no-overwrite":
        fail("看板程序模式或复制策略不符合要求")
    if Path(dashboard.get("workspace_root", "")).resolve() != args.workspace_root.resolve():
        fail("看板工作区路径不一致")
    api_automation = args.workspace_root / ".codex-tools" / "配置Seedance API.ps1"
    if not api_automation.is_file():
        fail("工作区缺少 Seedance API 自动配置程序")
    api_tool = args.workspace_root / ".codex-tools" / "Seedance API配置工具.exe"
    api_tool_config = args.workspace_root / ".codex-tools" / "api-tool-config.json"
    if not api_tool.is_file() or api_tool.stat().st_size < 1_000_000:
        fail("工作区缺少 Seedance API 配置工具 EXE")
    if not api_tool_config.is_file():
        fail("工作区缺少 Seedance API 配置工具工作区配置")
    api_gui_config = json.loads(api_tool_config.read_text(encoding="utf-8-sig"))
    if Path(api_gui_config.get("workspace_root", "")).resolve() != args.workspace_root.resolve():
        fail("Seedance API 配置工具工作区路径不一致")
    project_api_tool = project / "apis" / "Seedance API配置工具.exe"
    project_api_config = project / "apis" / "api-tool-config.json"
    if not project_api_tool.is_file() or project_api_tool.stat().st_size < 1_000_000:
        fail("项目 04_管理与记录/01_API配置 缺少 Seedance API配置工具.exe")
    if not project_api_config.is_file():
        fail("项目 API 配置目录缺少 api-tool-config.json")
    project_api_gui_config = json.loads(project_api_config.read_text(encoding="utf-8-sig"))
    if Path(project_api_gui_config.get("workspace_root", "")).resolve() != args.workspace_root.resolve():
        fail("项目内 API 配置工具工作区路径不一致")

    for path in package.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".pyc", ".png", ".jpg", ".mp3", ".mp4", ".exe"}:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        if SUSPICIOUS_SECRET.search(text):
            fail(f"疑似真实密钥：{path}")

    print(json.dumps({
        "status": "OK",
        "version": manifest["version"],
        "project_root": str(project.resolve()),
        "skills": manifest["skills"],
        "api_called": False,
        "codex_board_created": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
