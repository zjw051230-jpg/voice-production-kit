#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CATEGORY_LAYOUT = {
    "01_输入资料": {
        "角色音色素材": "01_角色音色参考",
        "剧情总览": "02_剧情与剧本",
        "文字素材": "03_配音任务",
        "素材": "04_临时素材",
    },
    "02_生产成品": {
        "已生成视频": "01_生成视频",
        "已转mp3": "02_MP3音频",
    },
    "03_交付与版本": {
        "1提交资料": "01_待提交资料",
        "2版本": "02_工作版本",
        "8版本": "03_历史版本",
    },
    "04_管理与记录": {
        "apis": "01_API配置",
        "0日志信息": "02_操作日志与索引",
        "问题与改进log": "03_问题与改进",
        "垃圾桶": "04_回收归档",
    },
}
INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    os.replace(temporary, path)


def ensure_text(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def load_registry(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "projects": {}}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("projects"), dict):
        raise ValueError(f"项目注册表格式错误：{path}")
    return data


def create_layout(root: Path) -> None:
    junction_script = Path(__file__).with_name("create_compatibility_junction.ps1")
    mapping: dict[str, dict[str, str]] = {}
    for category, entries in CATEGORY_LAYOUT.items():
        mapping[category] = {}
        for legacy_name, readable_name in entries.items():
            target = root / category / readable_name
            target.mkdir(parents=True, exist_ok=True)
            mapping[category][readable_name] = legacy_name
            if os.name == "nt":
                completed = subprocess.run(
                    [
                        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", str(junction_script), "-LinkPath", str(root / legacy_name),
                        "-TargetPath", str(target),
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if completed.returncode != 0:
                    raise RuntimeError(
                        f"创建旧工具路径兼容映射失败：{legacy_name}：{completed.stderr.strip()}"
                    )
    management = root / "04_管理与记录" / "02_操作日志与索引"
    write_json(management / "目录兼容映射.json", mapping)
    ensure_text(
        root / "目录说明.md",
        "# 项目目录说明\n\n"
        "请按四个编号分类目录整理文件。工具仍可通过隐藏的旧目录名访问同一批文件。\n\n"
        "不要删除项目根目录中的隐藏兼容映射，否则旧版工具路径会失效。\n",
    )


def create_codex_metadata(root: Path) -> None:
    metadata = root / ".codex"
    checklist = metadata / "任务清单"
    checklist.mkdir(parents=True, exist_ok=True)
    assets = metadata / "01_素材状态与选用.json"
    dialogue_index = metadata / "02_台词ID位置索引.json"
    if not assets.exists():
        write_json(assets, {
            "schema_version": 1,
            "说明": "记录每个剧本角色的素材缺失状态、可用版本和最终选用版本",
            "状态选项": ["缺失", "已有待选择", "已选中", "待确认"],
            "角色素材": {},
            "updated_at": None,
        })
    if not dialogue_index.exists():
        write_json(dialogue_index, {
            "schema_version": 1,
            "说明": "task_ID 到来源任务、台词资料目录和成品位置的映射",
            "台词": {},
            "updated_at": None,
        })
    api_state = metadata / "04_API池状态.json"
    if not api_state.exists():
        write_json(api_state, {
            "schema_version": 1,
            "workflow_paused": False,
            "pause_reason": None,
            "notify_chat": "理解文本与任务",
            "source_chat": None,
            "affected_task_ids": [],
            "resubmit_required": False,
            "next_api_activated": False,
            "active_config_id": None,
            "event_history": [],
            "updated_at": None,
        })
    api_index = root / "apis" / "api_pool" / "index.json"
    if not api_index.exists():
        write_json(api_index, {
            "schema_version": 1,
            "environment": None,
            "active_id": None,
            "configs": [],
            "updated_at": None,
        })
    ensure_text(
        metadata / "04_API池与余额切换.md",
        "# API 池与余额切换\n\n"
        "本文件由自动化程序维护，不包含 API Key。\n\n"
        "任何 Chat 发现明确余额不足时必须停止所有流程，只通知“理解文本与任务”。\n"
        "有下一份 API 时自动切换；恢复后只重新提交没有远端 ID 的版本，禁止 force-regenerate。\n",
    )
    create_chat_workflow(metadata, root)
    if os.name == "nt":
        hidden_script = Path(__file__).with_name("set_hidden_directory.ps1")
        completed = subprocess.run(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(hidden_script), "-Path", str(metadata),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            raise RuntimeError(f"设置 .codex 隐藏目录失败：{completed.stderr.strip()}")


def create_chat_workflow(metadata: Path, root: Path) -> None:
    table_path = metadata / "03_codexchat对应表.json"
    prompt_dir = metadata / "Chat提示词"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    record_path = root / "04_管理与记录" / "03_问题与改进"
    common = (
        f"项目根目录固定为：{root.resolve()}。开始前读取 .codex\\03_codexchat对应表.json 和本角色技能。"
        "本项目要求完全访问权限；若当前 Chat 不是完全访问权限，停止执行并让用户切换。"
        "接到任务时自己的 status 应已由上游设为1。完成后必须运行 manage_chat_workflow.py complete 把自己改回0。"
        "向下游发送前先运行 prepare-handoff；若目标 status=1，不得发送，创建5分钟心跳后重新检查并循环。"
        "交接消息必须包含来源Chat、task_ID、文件绝对路径、具体动作、不可违反的约束，并提醒下游完成后把自己的status改为0。"
        "每次开始和交接前读取 .codex\\04_API池状态.json；workflow_paused=true 时立即停止常规流程。"
        "任何Chat发现明确余额不足时，必须运行 seedance-voice-video-batch/scripts/manage_api_pool.py 的 balance-exhausted，"
        "打断全部流程并把紧急消息发送给‘理解文本与任务’Chat，不得继续提交、查询或拉回。"
    )
    definitions = {
        "理解文本与任务": {
            "model": "gpt-5.6-sol", "reasoning_effort": "medium",
            "skills": ["manage-voice-production", "generate-voice-prompt-json", "seedance-voice-video-batch"],
            "next": "提示词", "feedback": True,
            "prompt": common + "你是总入口和流程负责人。首次进入项目必须先运行bootstrap-status；未就绪时立即把当前任务命名为‘理解文本与任务’，使用Codex任务工具创建提示词、生成、监控、拉回、记录五个独立任务，逐个设置映射表指定的模型、推理强度、提示词和完全访问权限并register。六个任务全部就绪前禁止开始生产。你只负责理解用户文本、补问缺失资料、拆解任务、维护项目元数据和派发；禁止自己代做提示词编写、Seedance提交、监控、拉回或记录。所有派发必须先运行prepare-handoff并使用返回的thread ID。所有需要反馈的阶段都回到你这里，由你向用户做最终确认。收到余额不足紧急消息时，先确认程序已切换下一份API；没有则让用户在CC Switch配置新API并重新导入。然后运行resume-after-balance，使用原任务参数且不加force只重提没有远端ID的版本。",
        },
        "提示词": {
            "model": "gpt-5.6-sol", "reasoning_effort": "medium",
            "skills": ["generate-voice-prompt-json", "generate-tts-emotion-prompt-json", "manage-voice-production"],
            "next": "生成", "feedback": True,
            "prompt": common + "你只负责根据已确认文本生成或修改Seedance配音提示词和六字段任务JSON，同步.codex任务清单，校验素材状态。完成后反馈理解文本与任务Chat，并把可执行任务交给生成Chat。",
        },
        "生成": {
            "model": "gpt-5.6-terra", "reasoning_effort": "medium",
            "skills": ["seedance-voice-video-batch", "manage-voice-production"],
            "next": "监控", "feedback": True,
            "prompt": common + "你只负责生成预检、参考素材上传和Seedance提交。只有素材已选中且上游明确授权实际生成时才提交。拿到远端ID后保存状态，反馈理解文本与任务Chat，并交给监控Chat；不得自行长期轮询。",
        },
        "监控": {
            "model": "gpt-5.6-terra", "reasoning_effort": "low",
            "skills": ["seedance-voice-video-batch"],
            "next": "拉回", "feedback": True,
            "prompt": common + "你只查询已保存的远端任务ID和状态，不重新提交、不重新上传、不使用force-regenerate。完成时反馈理解文本与任务Chat，并把已完成任务交给拉回Chat。",
        },
        "拉回": {
            "model": "gpt-5.6-terra", "reasoning_effort": "low",
            "skills": ["seedance-voice-video-batch", "manage-voice-production"],
            "next": "记录", "feedback": True,
            "prompt": common + "你只拉取已完成视频并按任务要求提取MP3，不重新提交。核对文件存在并同步逐句资料索引后反馈理解文本与任务Chat，再把结果交给记录Chat。",
        },
        "记录": {
            "model": "gpt-5.6-terra", "reasoning_effort": "low",
            "skills": ["manage-voice-production", "repair-voice-generation"],
            "next": None, "feedback": False,
            "prompt": common + f"你只负责把本轮结果、问题和改进记录到：{record_path.resolve()}，并维护对应台词改动记录。该环节单向写入，不向其他Chat发送反馈；写完把自己的status改回0，本轮由理解文本与任务Chat结束。",
        },
    }
    chats = {}
    for order, (name, definition) in enumerate(definitions.items(), 1):
        prompt_file = prompt_dir / f"{order:02d}_{name}.md"
        ensure_text(prompt_file, f"# {name}\n\n{definition['prompt']}\n")
        chats[name] = {
            "order": order,
            "thread_id": None,
            "host_id": "local",
            "status": 0,
            "model": definition["model"],
            "reasoning_effort": definition["reasoning_effort"],
            "full_access_required": True,
            "full_access_verified": False,
            "prompt": definition["prompt"],
            "prompt_file": str(prompt_file.resolve()),
            "skills": definition["skills"],
            "next_chat": definition["next"],
            "feedback_to": "理解文本与任务" if definition["feedback"] and name != "理解文本与任务" else None,
            "feedback_required": definition["feedback"],
        }
    if not table_path.exists():
        write_json(table_path, {
            "schema_version": 2,
            "project_root": str(root.resolve()),
            "workflow_owner": "理解文本与任务",
            "entry_chat": "理解文本与任务",
            "bootstrap_required": True,
            "workflow_ready": False,
            "required_chats": list(definitions),
            "single_chat_execution_forbidden": True,
            "status_values": {"0": "空闲", "1": "处理中或已占用"},
            "busy_retry_minutes": 5,
            "record_output": str(record_path.resolve()),
            "record_is_one_way": True,
            "cycle_ends_at": "理解文本与任务",
            "chats": chats,
            "handoff_history": [],
            "updated_at": None,
        })


def create_project(workspace: Path, name: str, project_root: Path | None) -> Path:
    if not name.strip() or name in {".", ".."} or INVALID_NAME.search(name):
        raise ValueError("项目名为空或包含 Windows 文件名非法字符")
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    root = (project_root or (workspace / name)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    create_layout(root)
    create_codex_metadata(root)
    ensure_text(root / "0日志信息" / "任务操作日志.md", "# 任务操作日志\n\n")
    ensure_text(root / "问题与改进log" / "问题建议.md", "# 问题与改进\n\n")
    index = root / "0日志信息" / "地址索引.json"
    if not index.exists():
        write_json(index, {"schema_version": 1, "按任务ID": {}, "按路径": {}, "未识别": {}})
    api_example = root / "apis" / "doubao_api_config.example.json"
    if not api_example.exists():
        write_json(api_example, {
            "base_url": "https://chat.q1.com/v1",
            "api_key": "请在本机填写，不要提交或分享",
            "model": "doubao-seedance-2.0"
        })
    tools_root = workspace / ".codex-tools"
    api_tool_source = tools_root / "Seedance API配置工具.exe"
    api_tool_config_source = tools_root / "api-tool-config.json"
    if api_tool_source.is_file():
        shutil.copy2(api_tool_source, root / "apis" / api_tool_source.name)
    if api_tool_config_source.is_file():
        shutil.copy2(api_tool_config_source, root / "apis" / api_tool_config_source.name)
    registry_path = workspace / "项目注册表.json"
    registry = load_registry(registry_path)
    existing = registry["projects"].get(name)
    if existing and Path(existing["project_root"]).resolve() != root:
        raise ValueError(f"项目名已注册到其他路径：{existing['project_root']}")
    registry["projects"][name] = {
        "project_root": str(root),
        "created_at": existing.get("created_at") if existing else datetime.now(timezone.utc).isoformat(),
        "active": True,
    }
    write_json(registry_path, registry)
    return root


def main() -> int:
    parser = argparse.ArgumentParser(description="创建或查询多项目配音工作区")
    parser.add_argument("--workspace-root", required=True, type=Path)
    parser.add_argument("--project-name")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    registry_path = args.workspace_root.resolve() / "项目注册表.json"
    if args.list:
        print(json.dumps(load_registry(registry_path), ensure_ascii=False, indent=2))
        return 0
    if not args.project_name:
        parser.error("创建项目时必须提供 --project-name")
    root = create_project(args.workspace_root, args.project_name, args.project_root)
    print(json.dumps({"project_name": args.project_name, "project_root": str(root)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
