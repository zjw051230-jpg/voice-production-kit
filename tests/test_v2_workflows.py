from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path

PACKAGE = Path(r"D:\配音工具总结\安装包\v2.1")
TEST_ROOT = Path(r"D:\配音工具总结\test\v2.1")
API_SCRIPTS = PACKAGE / "skills" / "seedance-voice-video-batch" / "scripts"
PROJECT_SCRIPTS = PACKAGE / "skills" / "manage-voice-production" / "scripts"
sys.path[:0] = [str(API_SCRIPTS), str(PROJECT_SCRIPTS)]

from api_config_gui import ApiConfigApp, load_environment_keys
from create_voice_project import create_project
from manage_api_pool import (
    import_pool,
    pool_paths,
    read_json,
    resume_after_balance,
    save_manual_keys,
    signal_balance_exhausted,
)


def assert_no_secret(path: Path, secrets: list[str]) -> None:
    text = path.read_text(encoding="utf-8-sig")
    assert all(secret not in text for secret in secrets), f"secret leaked into {path}"


def test_api_gui_and_failover(root: Path) -> dict:
    workspace = root / "workspace"
    tools = workspace / ".codex-tools"
    tools.mkdir(parents=True)
    shutil.copy2(PACKAGE / "program" / "Seedance API配置工具.exe", tools / "Seedance API配置工具.exe")
    (tools / "api-tool-config.json").write_text(json.dumps({
        "schema_version": 1, "workspace_root": str(workspace), "installed_version": "2.0"
    }, ensure_ascii=False), encoding="utf-8")
    project = create_project(workspace, "API界面测试项目", None)
    assert (project / "apis" / "Seedance API配置工具.exe").is_file()
    assert read_json(project / "apis" / "api-tool-config.json")["installed_version"] == "2.0"

    window = tk.Tk()
    window.withdraw()
    app = ApiConfigApp(window, workspace)
    key_a = "fixture-v2-alpha-000000000001"
    key_b = "fixture-v2-beta-000000000002"
    key_c = "fixture-v2-production-00000003"
    key_d = "fixture-v2-spare-000000000004"
    key_e = "fixture-v2-recovery-0000000005"

    app.key_value.set(key_a)
    app.add_key()
    assert read_json(project / "apis" / "doubao_api_config.json")["api_key"] == key_a
    app.key_value.set(key_a)
    app.add_key()
    assert len(load_environment_keys(project, "test")) == 1
    app.key_value.set(key_b)
    app.add_key()
    assert len(load_environment_keys(project, "test")) == 2

    second = app.keys[1]["fingerprint"]
    app.table.selection_set(second)
    app.set_active()
    assert read_json(project / "apis" / "doubao_api_config.json")["api_key"] == key_b
    first = app.keys[0]["fingerprint"]
    app.table.selection_set(first)
    app.remove_selected()
    assert len(load_environment_keys(project, "test")) == 1
    assert list((project / "apis" / "api_pool" / "_archive").rglob("*.json"))

    app.environment.set("production")
    app.reload_keys()
    app.key_value.set(key_c)
    app.add_key()
    assert read_json(project / "apis" / "doubao_api_config.json")["base_url"] == "https://chat.q1.com/v1"

    window.geometry("700x620+30000+30000")
    window.deiconify()
    window.update_idletasks()
    assert app.save_button.winfo_rooty() + app.save_button.winfo_height() <= window.winfo_rooty() + window.winfo_height()
    window.destroy()

    save_manual_keys(project, "test", [key_b, key_d], None)
    first_event = signal_balance_exhausted(project, "生成", ["fixture-task"], "余额不足")
    assert first_event["next_config_id"]
    state = read_json(pool_paths(project)["state"])
    chats = read_json(pool_paths(project)["chats"])
    assert state["workflow_paused"] is True
    assert chats["chats"]["理解文本与任务"]["status"] == 1
    assert all(chat["status"] == 0 for name, chat in chats["chats"].items() if name != "理解文本与任务")
    second_event = signal_balance_exhausted(project, "生成", ["fixture-task"], "insufficient balance")
    assert second_event["next_config_id"] is None
    save_manual_keys(project, "test", [key_b, key_d, key_e], None)
    assert read_json(pool_paths(project)["state"])["next_api_activated"] is True
    resumed = resume_after_balance(project)
    assert resumed["resumed"] is True
    assert read_json(pool_paths(project)["state"])["workflow_paused"] is False

    secrets = [key_a, key_b, key_c, key_d, key_e]
    assert_no_secret(project / "apis" / "api_pool" / "index.json", secrets)
    assert_no_secret(project / ".codex" / "04_API池与余额切换.md", secrets)
    return {"api_gui": "OK", "balance_failover": "OK", "network_called": False}


def test_ccswitch_mapping(root: Path) -> dict:
    fixture = root / "ccswitch"
    fixture.mkdir()
    db = fixture / "cc-switch.db"
    original = {
        "auth": {"OPENAI_API_KEY": "fixture-only-secret"},
        "base_url": "https://example.invalid/v1",
        "modelCatalog": {"models": [
            {"model": "old-upstream", "displayName": "5.5", "extra": "keep"},
            {"model": "gpt-5.6-sol", "displayName": "5.6-sol"},
            {"model": "other-model", "displayName": "其他"},
        ]},
        "unrelated": {"keep": True},
    }
    other = {"modelCatalog": {"models": [{"model": "unchanged", "displayName": "5.5"}]}}
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE providers (id TEXT PRIMARY KEY, name TEXT, settings_config TEXT, app_type TEXT, is_current INTEGER)")
        connection.execute("INSERT INTO providers VALUES (?,?,?,?,?)", ("p1", "Current", json.dumps(original), "codex", 1))
        connection.execute("INSERT INTO providers VALUES (?,?,?,?,?)", ("p2", "Other", json.dumps(other), "codex", 0))
    connection.close()

    script = PACKAGE / "scripts" / "configure_ccswitch_model.py"
    child_env = dict(os.environ, PYTHONIOENCODING="utf-8")
    dry = subprocess.run(
        [sys.executable, str(script), "--db", str(db), "--dry-run"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=child_env,
    )
    assert dry.returncode == 0 and "preview: 5.5 -> dpskv4" in dry.stdout
    with sqlite3.connect(db) as connection:
        assert json.loads(connection.execute("SELECT settings_config FROM providers WHERE id='p1'").fetchone()[0]) == original
    connection.close()
    applied = subprocess.run(
        [sys.executable, str(script), "--db", str(db)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=child_env,
    )
    assert applied.returncode == 0 and "integrity_check: ok" in applied.stdout
    with sqlite3.connect(db) as connection:
        current = json.loads(connection.execute("SELECT settings_config FROM providers WHERE id='p1'").fetchone()[0])
        untouched = json.loads(connection.execute("SELECT settings_config FROM providers WHERE id='p2'").fetchone()[0])
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    connection.close()
    models = current["modelCatalog"]["models"]
    assert next(item for item in models if item["displayName"] == "5.5")["model"] == "dpskv4"
    assert [item for item in models if item["displayName"] != "5.5"] == [item for item in original["modelCatalog"]["models"] if item["displayName"] != "5.5"]
    assert current["auth"] == original["auth"] and current["base_url"] == original["base_url"] and current["unrelated"] == original["unrelated"]
    assert untouched == other
    assert list((fixture / "backups").glob("cc-switch.before-model-map.*.db"))
    return {"ccswitch_mapping": "OK", "only_5_5_changed": True}


def test_ccswitch_api_import(root: Path) -> dict:
    fixture = root / "ccswitch-import"
    fixture.mkdir()
    db = fixture / "cc-switch.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE providers (id TEXT PRIMARY KEY, name TEXT, settings_config TEXT, app_type TEXT, is_current INTEGER, sort_index INTEGER)")
        connection.execute("CREATE TABLE provider_endpoints (provider_id TEXT, app_type TEXT, url TEXT)")
        rows = [
            ("t1", "Test Current", "fixture-import-test-0001", 1, 1, "https://chat-test.q1.com/v1"),
            ("t2", "Test Backup", "fixture-import-test-0002", 0, 2, "https://chat-test.q1.com/v1"),
            ("td", "Test Duplicate", "fixture-import-test-0002", 0, 3, "https://chat-test.q1.com/v1"),
            ("p1", "Production", "fixture-import-prod-0001", 0, 4, "https://chat.q1.com/v1"),
        ]
        for provider_id, name, key, current, order, url in rows:
            settings = json.dumps({"auth": {"OPENAI_API_KEY": key}})
            connection.execute("INSERT INTO providers VALUES (?,?,?,?,?,?)", (provider_id, name, settings, "codex", current, order))
            connection.execute("INSERT INTO provider_endpoints VALUES (?,?,?)", (provider_id, "codex", url))
    connection.close()
    project = create_project(root / "import-workspace", "导入测试项目", None)
    test_result = import_pool(project, db, "test")
    assert test_result["config_count"] == 2 and test_result["active_provider"] == "Test Current"
    assert read_json(project / "apis" / "doubao_api_config.json")["base_url"] == "https://chat-test.q1.com/v1"
    production_result = import_pool(project, db, "production")
    assert production_result["config_count"] == 1
    assert read_json(project / "apis" / "doubao_api_config.json")["base_url"] == "https://chat.q1.com/v1"
    return {"ccswitch_api_import": "OK", "test_deduplicated_count": 2, "production_count": 1}


def test_chat_workflow(root: Path) -> dict:
    workspace = root / "chat-workspace"
    project = create_project(workspace, "Chat测试项目", None)
    script = PACKAGE / "skills" / "manage-voice-production" / "scripts" / "manage_chat_workflow.py"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")

    def run(*args: str, expected: int = 0) -> dict:
        completed = subprocess.run(
            [sys.executable, str(script), "--project-root", str(project), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
        )
        assert completed.returncode == expected, completed.stdout + completed.stderr
        return json.loads(completed.stdout)

    models = {
        "理解文本与任务": ("gpt-5.6-sol", "medium"),
        "提示词": ("gpt-5.6-sol", "medium"),
        "生成": ("gpt-5.6-terra", "medium"),
        "监控": ("gpt-5.6-terra", "low"),
        "拉回": ("gpt-5.6-terra", "low"),
        "记录": ("gpt-5.6-terra", "low"),
    }

    def register(chat: str, thread: str) -> dict:
        model, effort = models[chat]
        return run(
            "register", "--chat", chat, "--thread-id", thread,
            "--actual-model", model, "--actual-reasoning-effort", effort,
            "--full-access-verified", "true",
        )

    initial = run("bootstrap-status", expected=4)
    assert initial["bootstrap_required"] is True
    assert set(initial["missing_threads"]) == {"理解文本与任务", "提示词", "生成", "监控", "拉回", "记录"}

    wrong_model = subprocess.run(
        [sys.executable, str(script), "--project-root", str(project), "register",
         "--chat", "理解文本与任务", "--thread-id", "thread-owner",
         "--actual-model", "gpt-5.6-terra", "--actual-reasoning-effort", "medium",
         "--full-access-verified", "true"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    assert wrong_model.returncode != 0 and "模型不匹配" in wrong_model.stderr
    wrong_effort = subprocess.run(
        [sys.executable, str(script), "--project-root", str(project), "register",
         "--chat", "理解文本与任务", "--thread-id", "thread-owner",
         "--actual-model", "gpt-5.6-sol", "--actual-reasoning-effort", "low",
         "--full-access-verified", "true"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    assert wrong_effort.returncode != 0 and "思考程度不匹配" in wrong_effort.stderr

    register("理解文本与任务", "thread-owner")
    register("提示词", "thread-prompt")
    blocked_bootstrap = run(
        "prepare-handoff", "--from-chat", "理解文本与任务", "--to-chat", "提示词",
        "--summary", "初始化未完成", expected=2,
    )
    assert blocked_bootstrap["bootstrap_required"] is True
    assert "生成" in blocked_bootstrap["missing_threads"]

    duplicate = subprocess.run(
        [sys.executable, str(script), "--project-root", str(project), "register",
         "--chat", "生成", "--thread-id", "thread-prompt",
         "--actual-model", "gpt-5.6-terra", "--actual-reasoning-effort", "medium",
         "--full-access-verified", "true"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    assert duplicate.returncode != 0 and "thread_id已登记给其他Chat" in duplicate.stderr

    for chat, thread in (
        ("生成", "thread-generate"), ("监控", "thread-monitor"),
        ("拉回", "thread-download"), ("记录", "thread-record"),
    ):
        register(chat, thread)
    bootstrapped = run("bootstrap-status")
    assert bootstrapped["ready"] is True and bootstrapped["duplicate_thread_ids"] == []

    ready = run("prepare-handoff", "--from-chat", "理解文本与任务", "--to-chat", "提示词", "--task-id", "T001", "--summary", "测试交接")
    assert ready["ready"] is True and ready["thread_id"] == "thread-prompt"
    assert ready["dispatch_contract"] == {
        "thread_id": "thread-prompt", "host_id": "local",
        "model": "gpt-5.6-sol", "reasoning_effort": "medium",
        "prompt_file": ready["prompt_file"], "defaults_forbidden": True,
    }
    busy = run("prepare-handoff", "--from-chat", "理解文本与任务", "--to-chat", "提示词", "--summary", "重复交接", expected=2)
    assert busy["ready"] is False and busy["retry_minutes"] == 5
    assert run("complete", "--chat", "提示词")["status"] == 0

    state_path = project / ".codex" / "04_API池状态.json"
    state = read_json(state_path)
    state.update({"workflow_paused": True, "pause_reason": "Seedance API 余额不足"})
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    blocked = run("prepare-handoff", "--from-chat", "理解文本与任务", "--to-chat", "提示词", "--summary", "暂停门禁", expected=2)
    assert blocked["paused"] is True and blocked["required_target"] == "理解文本与任务"
    emergency = run("prepare-handoff", "--from-chat", "生成", "--to-chat", "理解文本与任务", "--summary", "余额不足")
    assert emergency["emergency"] is True and emergency["thread_id"] == "thread-owner"
    return {"chat_workflow": "OK", "bootstrap_gate": "OK", "model_contract": "OK", "busy_retry_minutes": 5, "pause_gate": "OK"}


def test_prompt_manifest_and_provenance(root: Path) -> dict:
    workspace = root / "content-workspace"
    project = create_project(workspace, "内容工具测试项目", None)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")

    def run(script: Path, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [sys.executable, str(script), *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env,
        )
        assert completed.returncode == expected, completed.stdout + completed.stderr
        return completed

    task_id = "0729001"
    line = "不到十分钟。"
    voice_prompt = (
        "参考音视频只用于复刻音色和自然说话习惯。严格复刻参考音视频的原始声音，不得自行调整声线。"
        "此刻刚听到消息，月儿对姐姐回答，内心担心但克制。"
        f"成片唯一允许出现的人声内容是“{line}”，必须逐字、完整、只说一次，"
        "不得改词、漏词、加词、重复、续说，除目标台词外宁可保持静音。"
    )
    voice_tasks = [{
        "剧本名字": "测试剧", "task_ID": f"{task_id}_1", "角色名字": "月儿",
        "台词": line, "时长": "4秒", "提示词": voice_prompt,
    }]
    input_path = root / "voice-input.json"
    input_path.write_text(json.dumps(voice_tasks, ensure_ascii=False), encoding="utf-8")
    voice_saver = PACKAGE / "skills" / "generate-voice-prompt-json" / "scripts" / "save_voice_prompts.py"
    run(voice_saver, "--task-id", task_id, "--input", str(input_path), "--output-dir", str(project / "文字素材"))
    saved_task = project / "文字素材" / f"{task_id}+1个任务.json"
    assert saved_task.is_file()
    run(voice_saver, "--task-id", task_id, "--input", str(input_path), "--output-dir", str(project / "文字素材"), expected=1)

    tts_tasks = [{
        "剧本名字": "测试剧", "task_ID": "0729002_1", "角色名字": "系统",
        "台词": "任务完成。", "时长": "4秒",
        "提示词": "此刻刚得知结果，对同伴报告，情绪释然但克制。语速稍快，中间短停，重点重读结果，句尾下落收住。只说输入台词，不添加任何字，不重复，不得续说。",
    }]
    tts_input = root / "tts-input.json"
    tts_input.write_text(json.dumps(tts_tasks, ensure_ascii=False), encoding="utf-8")
    tts_saver = PACKAGE / "skills" / "generate-tts-emotion-prompt-json" / "scripts" / "save_tts_emotion_prompts.py"
    tts_out = root / "tts-output"
    run(tts_saver, "--task-id", "0729002", "--input", str(tts_input), "--output-dir", str(tts_out))
    assert (tts_out / "0729002+1个任务.json").is_file()

    role_dir = project / "角色音色素材" / "测试剧" / "月儿"
    role_dir.mkdir(parents=True)
    (role_dir / "月儿音色.mp4").write_bytes(b"fixture")
    sync = PACKAGE / "skills" / "manage-voice-production" / "scripts" / "sync_task_manifest.py"
    run(sync, "--project-root", str(project), "--task-json", str(saved_task))
    info = read_json(project / ".codex" / "任务清单" / f"{task_id}_1" / "资料索引.json")
    assert info["参考素材"]["素材状态"] == "已选中"

    source_file = project / "已转mp3" / f"{task_id}_1_月儿_不到十分钟_v01.mp3"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(b"source")
    derived_file = project / "已转mp3" / f"{task_id}_1_月儿_不到十分钟_v02.mp3"
    derived_file.write_bytes(b"derived")
    index_script = PACKAGE / "skills" / "seedance-voice-video-batch" / "scripts" / "update_address_index.py"
    index_path = project / "0日志信息" / "地址索引.json"
    run(index_script, "--root", str(project), "--index", str(index_path))
    index = read_json(index_path)
    assert str(source_file.resolve()) in index["按路径"] and str(derived_file.resolve()) in index["按路径"]

    linker = PACKAGE / "skills" / "seedance-voice-video-batch" / "scripts" / "link_derived_file.py"
    run(linker, "--index", str(index_path), "--source", str(source_file.resolve()), "--output", str(derived_file.resolve()), "--action", "测试派生")
    linked = read_json(index_path)
    reverse = linked["按路径"][str(derived_file.resolve())]
    record = linked["按任务ID"][reverse["task_ID"]][reverse["record_id"]]
    assert record["来源路径"] == str(source_file.resolve())

    resolver = PACKAGE / "skills" / "repair-voice-generation" / "scripts" / "resolve_repair_source.py"
    resolved = run(resolver, "--project-root", str(project), "--file", str(source_file.resolve()))
    repaired = json.loads(resolved.stdout)
    assert repaired["原task_ID"] == f"{task_id}_1" and repaired["台词"] == line

    logger = PACKAGE / "skills" / "seedance-voice-video-batch" / "scripts" / "append_task_log.py"
    run(logger, "--project-root", str(project), "--task", task_id, "--action", "离线验收", "--files", str(source_file), "--status", "完成")
    assert "离线验收" in (project / "0日志信息" / "任务操作日志.md").read_text(encoding="utf-8-sig")
    feedback = PACKAGE / "skills" / "seedance-voice-video-batch" / "scripts" / "append_feedback.py"
    run(feedback, "--project-root", str(project), "--task", task_id, "--item", "1", "--issue-type", "测试", "--issue", "测试问题", "--suggestion", "测试建议")
    assert "测试建议" in (project / "问题与改进log" / "问题建议.md").read_text(encoding="utf-8-sig")
    return {"voice_prompt_saver": "OK", "tts_prompt_saver": "OK", "task_manifest": "OK", "provenance_and_repair": "OK", "logs_and_feedback": "OK"}


def test_documents() -> dict:
    docs = {
        "start": PACKAGE / "START-HERE.md",
        "install": PACKAGE / "INSTALL.md",
        "api": PACKAGE / "API与CCSwitch配置.md",
        "manual": PACKAGE / "详细使用手册.md",
        "quick": Path(r"D:\配音工具总结\文档\v2.1\配音工作流使用说明.md"),
        "published_manual": Path(r"D:\配音工具总结\文档\v2.1\配音工具详细使用手册.md"),
    }
    for path in docs.values():
        assert path.is_file() and path.stat().st_size > 300
        text = path.read_text(encoding="utf-8-sig")
        assert "v2.0" in text and "v1.0.9" not in text
    combined = "\n".join(path.read_text(encoding="utf-8-sig") for path in docs.values())
    for required in ("创建项目", "Seedance API配置工具", "立即写", "余额不足", "5.5", "dpskv4", "D:\\codex-board"):
        assert required in combined, f"documentation missing: {required}"
    assert docs["manual"].read_bytes() == docs["published_manual"].read_bytes()
    assert docs["quick"].stat().st_size < docs["manual"].stat().st_size
    return {"documents": "OK", "manuals_identical": True}


def main() -> None:
    base = TEST_ROOT / ".test-artifacts"
    root = Path(tempfile.mkdtemp(prefix="workflow-fixture-", dir=base))
    try:
        result = {}
        result.update(test_api_gui_and_failover(root))
        result.update(test_ccswitch_mapping(root))
        result.update(test_ccswitch_api_import(root))
        result.update(test_chat_workflow(root))
        result.update(test_prompt_manifest_and_provenance(root))
        result.update(test_documents())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        for _attempt in range(5):
            try:
                shutil.rmtree(root)
                break
            except PermissionError:
                time.sleep(0.2)


if __name__ == "__main__":
    main()
