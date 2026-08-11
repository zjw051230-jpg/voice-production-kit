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

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(r"D:\配音工具总结\安装包\v2.1")
TEST_ROOT = Path(r"D:\配音工具总结\test\v2.1")
API_SCRIPTS = PACKAGE / "skills" / "seedance-voice-video-batch" / "scripts"
PROJECT_SCRIPTS = PACKAGE / "skills" / "manage-voice-production" / "scripts"
DASHBOARD_SCRIPTS = PACKAGE / "skills" / "voice-production-dashboard" / "scripts"
sys.path[:0] = [str(API_SCRIPTS), str(PROJECT_SCRIPTS), str(DASHBOARD_SCRIPTS)]

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
from run_pipeline import require_terminal_for_pullback, terminal_summary
from voice_dashboard import STAGE_ORDER, derive_status, resolve_completed, scan_workspace, status_details


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
    chat_path = pool_paths(project)["chats"]
    leased_chats = read_json(chat_path)
    leased_chats["chats"]["生成"].update({
        "status": 1,
        "active_task": {
            "lease_id": "balance-test-lease", "task_ID": "fixture-task",
            "summary": "余额中断租约", "from_chat": "理解文本与任务",
        },
    })
    leased_chats["chats"]["理解文本与任务"]["waiting_for_feedback"] = {
        "from_chat": "生成", "lease_id": "balance-test-lease",
    }
    chat_path.write_text(json.dumps(leased_chats, ensure_ascii=False, indent=2), encoding="utf-8")
    first_event = signal_balance_exhausted(project, "生成", ["fixture-task"], "余额不足")
    assert first_event["next_config_id"]
    state = read_json(pool_paths(project)["state"])
    chats = read_json(pool_paths(project)["chats"])
    assert state["workflow_paused"] is True
    assert chats["chats"]["理解文本与任务"]["status"] == 1
    assert all(chat["status"] == 0 for name, chat in chats["chats"].items() if name != "理解文本与任务")
    assert all(chat.get("active_task") is None for chat in chats["chats"].values())
    assert all(chat.get("waiting_for_feedback") is None for chat in chats["chats"].values())
    assert chats["chats"]["生成"]["last_interrupted_task"]["lease_id"] == "balance-test-lease"
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
    original_config = (
        'model_provider = "custom"\nmodel = "gpt-5.6-sol"\n\n'
        '[model_providers.custom]\nname = "custom"\nbase_url = "https://example.invalid/v1"\n'
    )
    original = {
        "auth": {"OPENAI_API_KEY": "fixture-only-secret"},
        "config": original_config,
        "unrelated": {"keep": True},
    }
    other = {"config": 'model = "unchanged"\n', "unrelated": {"keep": "other"}}
    original_meta = {
        "apiFormat": "openai_responses",
        "endpointAutoSelect": True,
        "localProxyRequestOverrides": {
            "headers": {"X-Keep": "yes"},
            "body": {"temperature": 0.2},
            "modelRoutes": {"existing-model": "existing-upstream"},
        },
    }
    other_meta = {"apiFormat": "openai_chat", "keep": "other"}
    live_config = fixture / "config.toml"
    live_original = original_config + '\n[desktop]\nfollowUpQueueMode = "queue"\n'
    live_config.write_text(live_original, encoding="utf-8")
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE providers (id TEXT PRIMARY KEY, name TEXT, settings_config TEXT, meta TEXT, app_type TEXT, is_current INTEGER)")
        connection.execute("INSERT INTO providers VALUES (?,?,?,?,?,?)", ("p1", "Current", json.dumps(original), json.dumps(original_meta), "codex", 1))
        connection.execute("INSERT INTO providers VALUES (?,?,?,?,?,?)", ("p2", "Other", json.dumps(other), json.dumps(other_meta), "codex", 0))
        connection.execute("INSERT INTO providers VALUES (?,?,?,?,?,?)", ("p3", "Empty Meta", json.dumps(other), "{}", "codex", 0))
    connection.close()

    script = PACKAGE / "scripts" / "configure_ccswitch_model.py"
    child_env = dict(os.environ, PYTHONIOENCODING="utf-8")
    dry = subprocess.run(
        [sys.executable, str(script), "--db", str(db), "--skip-binary-check", "--dry-run"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=child_env,
    )
    assert dry.returncode == 0 and "preview: gpt-5.5 -> deepseek-v4-pro" in dry.stdout
    with sqlite3.connect(db) as connection:
        assert json.loads(connection.execute("SELECT settings_config FROM providers WHERE id='p1'").fetchone()[0]) == original
        assert json.loads(connection.execute("SELECT meta FROM providers WHERE id='p1'").fetchone()[0]) == original_meta
    connection.close()
    applied = subprocess.run(
        [sys.executable, str(script), "--db", str(db), "--skip-binary-check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=child_env,
    )
    assert applied.returncode == 0 and "integrity_check: ok" in applied.stdout
    with sqlite3.connect(db) as connection:
        current = json.loads(connection.execute("SELECT settings_config FROM providers WHERE id='p1'").fetchone()[0])
        current_meta = json.loads(connection.execute("SELECT meta FROM providers WHERE id='p1'").fetchone()[0])
        untouched = json.loads(connection.execute("SELECT settings_config FROM providers WHERE id='p2'").fetchone()[0])
        untouched_meta = json.loads(connection.execute("SELECT meta FROM providers WHERE id='p2'").fetchone()[0])
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    connection.close()
    routes = current_meta["localProxyRequestOverrides"]["modelRoutes"]
    assert routes["gpt-5.5"] == "deepseek-v4-pro"
    assert routes["existing-model"] == "existing-upstream"
    assert current_meta["localProxyRequestOverrides"]["headers"] == {"X-Keep": "yes"}
    assert current_meta["localProxyRequestOverrides"]["body"] == {"temperature": 0.2}
    assert live_config.read_text(encoding="utf-8") == live_original
    assert "model_catalog_json" not in current["config"]
    assert current["auth"] == original["auth"] and current["unrelated"] == original["unrelated"]
    assert untouched == other
    assert untouched_meta == other_meta
    assert list((fixture / "backups").glob("cc-switch.before-local-route.*.db"))

    def route(model: str) -> str:
        return routes.get(model, model)

    assert route("gpt-5.5") == "deepseek-v4-pro"
    for model in ("gpt-5.5-mini", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "other"):
        assert route(model) == model

    empty_meta = subprocess.run(
        [sys.executable, str(script), "--db", str(db), "--skip-binary-check", "--provider-id", "p3"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=child_env,
    )
    assert empty_meta.returncode == 0 and "integrity_check: ok" in empty_meta.stdout
    with sqlite3.connect(db) as connection:
        p3_meta = json.loads(connection.execute("SELECT meta FROM providers WHERE id='p3'").fetchone()[0])
    assert p3_meta == {
        "localProxyRequestOverrides": {"modelRoutes": {"gpt-5.5": "deepseek-v4-pro"}}
    }
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
        )

    def verify_access(chat: str) -> dict:
        return run("verify-access", "--chat", chat)

    initial = run("bootstrap-status", expected=4)
    assert initial["bootstrap_required"] is True
    assert set(initial["missing_threads"]) == {"理解文本与任务", "提示词", "生成", "监控", "拉回", "记录"}
    assert set(initial["chat_creation_contracts"]) == set(models)
    assert all(
        contract["initial_message"] == "这个对话开启完全访问，不需要问我要任何的批准。"
        and contract["access_verification"]["must_run_in_target_chat"] is True
        for contract in initial["chat_creation_contracts"].values()
    )
    self_report = subprocess.run(
        [sys.executable, str(script), "--project-root", str(project), "register",
         "--chat", "理解文本与任务", "--thread-id", "thread-owner",
         "--actual-model", "gpt-5.6-sol", "--actual-reasoning-effort", "medium",
         "--full-access-verified", "true"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    assert self_report.returncode != 0

    wrong_model = subprocess.run(
        [sys.executable, str(script), "--project-root", str(project), "register",
         "--chat", "理解文本与任务", "--thread-id", "thread-owner",
         "--actual-model", "gpt-5.6-terra", "--actual-reasoning-effort", "medium",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    assert wrong_model.returncode != 0 and "模型不匹配" in wrong_model.stderr
    wrong_effort = subprocess.run(
        [sys.executable, str(script), "--project-root", str(project), "register",
         "--chat", "理解文本与任务", "--thread-id", "thread-owner",
         "--actual-model", "gpt-5.6-sol", "--actual-reasoning-effort", "low",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    assert wrong_effort.returncode != 0 and "思考程度不匹配" in wrong_effort.stderr

    register("理解文本与任务", "thread-owner")
    access_blocked = run("bootstrap-status", expected=4)
    assert "理解文本与任务" in access_blocked["unverified_full_access"]
    owner_access = verify_access("理解文本与任务")
    assert owner_access["full_access_verified"] is True
    assert not list((project / ".codex").glob(".full-access-probe-*.tmp"))

    verify_access("提示词")
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
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    assert duplicate.returncode != 0 and "thread_id已登记给其他Chat" in duplicate.stderr

    for chat, thread in (
        ("生成", "thread-generate"), ("监控", "thread-monitor"),
        ("拉回", "thread-download"), ("记录", "thread-record"),
    ):
        verify_access(chat)
        register(chat, thread)
    bootstrapped = run("bootstrap-status")
    assert bootstrapped["ready"] is True and bootstrapped["duplicate_thread_ids"] == []
    assert bootstrapped["record_policy_errors"] == []

    table_path = project / ".codex" / "03_codexchat对应表.json"
    tampered = read_json(table_path)
    tampered["chats"]["记录"]["feedback_required"] = True
    table_path.write_text(json.dumps(tampered, ensure_ascii=False, indent=2), encoding="utf-8")
    record_policy_block = run("bootstrap-status", expected=4)
    assert "记录.feedback_required必须为false" in record_policy_block["record_policy_errors"]
    tampered["chats"]["记录"]["feedback_required"] = False
    table_path.write_text(json.dumps(tampered, ensure_ascii=False, indent=2), encoding="utf-8")

    ready = run("prepare-handoff", "--from-chat", "理解文本与任务", "--to-chat", "提示词", "--task-id", "T001", "--summary", "测试交接")
    assert ready["ready"] is True and ready["thread_id"] == "thread-prompt"
    lease_id = ready["active_task"]["lease_id"]
    assert ready["dispatch_contract"] == {
        "thread_id": "thread-prompt", "host_id": "local",
        "model": "gpt-5.6-sol", "reasoning_effort": "medium",
        "prompt_file": ready["prompt_file"], "defaults_forbidden": True,
        "lease_id": lease_id,
    }
    assert ready["must_stop_and_wait"] is True
    table = run("show")
    assert table["chats"]["提示词"]["active_task"]["lease_id"] == lease_id
    assert table["chats"]["理解文本与任务"]["waiting_for_feedback"]["lease_id"] == lease_id

    source_waiting = run(
        "prepare-handoff", "--from-chat", "理解文本与任务", "--to-chat", "生成",
        "--task-id", "T002", "--summary", "主对话等待时禁止派发", expected=2,
    )
    assert source_waiting["source_waiting"] is True

    busy = run(
        "prepare-handoff", "--from-chat", "生成", "--to-chat", "提示词",
        "--task-id", "T003", "--summary", "目标忙碌定时重试", expected=2,
    )
    assert busy["ready"] is False and busy["retry_minutes"] == 5
    assert busy["timer_required"] is True
    assert busy["retry_contract"]["schedule"]["kind"] == "once"
    assert busy["retry_contract"]["arguments"]["task_ID"] == "T003"
    assert busy["retry_contract"]["automation_id"].startswith("voice-chat-retry-2-")
    assert len(busy["retry_contract"]["dedupe_key"]) == 12
    assert busy["active_task"]["lease_id"] == lease_id
    busy_table = run("show")
    assert busy["retry_contract"]["automation_id"] in busy_table["pending_retries"]

    manual_clear = subprocess.run(
        [sys.executable, str(script), "--project-root", str(project),
         "set-status", "--chat", "提示词", "--status", "0"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    assert manual_clear.returncode != 0 and "活动任务" in manual_clear.stderr
    wrong_lease = subprocess.run(
        [sys.executable, str(script), "--project-root", str(project),
         "complete", "--chat", "提示词", "--lease-id", "wrong-lease"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    assert wrong_lease.returncode != 0 and "lease-id不匹配" in wrong_lease.stderr

    completed = run("complete", "--chat", "提示词", "--lease-id", lease_id)
    assert completed["status"] == 0
    assert completed["feedback_contract"]["acknowledgement_required"] is True
    still_waiting = run(
        "prepare-handoff", "--from-chat", "理解文本与任务", "--to-chat", "生成",
        "--task-id", "T002", "--summary", "反馈未确认仍禁止派发", expected=2,
    )
    assert still_waiting["source_waiting"] is True
    acknowledged = run(
        "ack-feedback", "--chat", "理解文本与任务", "--from-chat", "提示词",
        "--lease-id", lease_id,
    )
    assert acknowledged["resumed"] is True and acknowledged["waiting_for_feedback"] is None

    record_handoff = run(
        "prepare-handoff", "--from-chat", "理解文本与任务", "--to-chat", "记录",
        "--task-id", "R001", "--summary", "单向写入记录",
    )
    record_lease = record_handoff["active_task"]["lease_id"]
    assert record_handoff["one_way_terminal"] is True
    assert record_handoff["report_to_owner"] is False
    assert record_handoff["must_stop_and_wait"] is False
    assert run("show")["chats"]["理解文本与任务"]["waiting_for_feedback"] is None
    record_completed = run("complete", "--chat", "记录", "--lease-id", record_lease)
    assert record_completed["one_way_terminal"] is True
    assert record_completed["report_to_owner"] is False
    assert record_completed["feedback_contract"] is None
    forbidden_record_report = subprocess.run(
        [sys.executable, str(script), "--project-root", str(project), "prepare-handoff",
         "--from-chat", "记录", "--to-chat", "理解文本与任务",
         "--task-id", "R001", "--summary", "禁止汇报"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    assert forbidden_record_report.returncode != 0 and "单向终止阶段" in forbidden_record_report.stderr

    remote_state = project / "已生成视频" / "T006+1个任务" / ".seedance-state.json"
    remote_state.parent.mkdir(parents=True, exist_ok=True)
    remote_jobs = {
        "T006/v01": {"status": "completed"}, "T006/v02": {"status": "completed"},
        "T006/v03": {"status": "failed"}, "T006/v04": {"status": "processing"},
    }
    remote_state.write_text(json.dumps({"jobs": remote_jobs}, ensure_ascii=False), encoding="utf-8")
    gated = run(
        "prepare-handoff", "--from-chat", "监控", "--to-chat", "拉回",
        "--task-id", "T006", "--summary", "整批终态后拉回",
        "--remote-state-file", str(remote_state), expected=2,
    )
    assert gated["terminal_gate"] == {
        "state_file": str(remote_state.resolve()), "total": 4, "success": 2,
        "failed": 1, "running": 1, "downloaded": 0, "terminal": False,
    }
    assert run("show")["chats"]["拉回"]["active_task"] is None
    remote_jobs["T006/v04"]["status"] = "failed"
    remote_state.write_text(json.dumps({"jobs": remote_jobs}, ensure_ascii=False), encoding="utf-8")
    allowed = run(
        "prepare-handoff", "--from-chat", "监控", "--to-chat", "拉回",
        "--task-id", "T006", "--summary", "整批终态后拉回",
        "--remote-state-file", str(remote_state),
    )
    assert allowed["terminal_gate"]["terminal"] is True
    assert allowed["terminal_gate"]["success"] + allowed["terminal_gate"]["failed"] == 4
    assert allowed["active_task"]["remote_state_file"] == str(remote_state.resolve())
    run("complete", "--chat", "拉回", "--lease-id", allowed["active_task"]["lease_id"])

    state_path = project / ".codex" / "04_API池状态.json"
    state = read_json(state_path)
    state.update({"workflow_paused": True, "pause_reason": "Seedance API 余额不足"})
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    blocked = run("prepare-handoff", "--from-chat", "理解文本与任务", "--to-chat", "提示词", "--summary", "暂停门禁", expected=2)
    assert blocked["paused"] is True and blocked["required_target"] == "理解文本与任务"
    emergency = run("prepare-handoff", "--from-chat", "生成", "--to-chat", "理解文本与任务", "--summary", "余额不足")
    assert emergency["emergency"] is True and emergency["thread_id"] == "thread-owner"
    return {
        "chat_workflow": "OK", "bootstrap_gate": "OK", "model_contract": "OK",
        "full_access_probe": "OK", "single_task_lease": "OK",
        "owner_waits_for_feedback": "OK", "record_one_way_terminal": "OK",
        "remote_terminal_gate": "OK", "busy_retry_minutes": 5, "pause_gate": "OK",
    }


def test_terminal_and_dashboard(root: Path) -> dict:
    partial = {
        "v01": {"status": "completed"}, "v02": {"status": "completed"},
        "v03": {"status": "failed"}, "v04": {"status": "processing"},
    }
    summary = terminal_summary(partial)
    assert summary == {"total": 4, "success": 2, "failed": 1, "running": 1,
                       "downloaded": 0, "terminal": False}
    try:
        require_terminal_for_pullback(partial)
    except RuntimeError as error:
        assert "禁止拉回" in str(error)
    else:
        raise AssertionError("partial-terminal batch bypassed pullback gate")
    partial["v04"]["status"] = "failed"
    assert require_terminal_for_pullback(partial)["terminal"] is True
    task = {"提示词": "fixture"}
    partial["v04"]["status"] = "processing"
    status, dashboard = derive_status(task, list(partial.values()), "已选中")
    assert status == "生成中" and dashboard["running"] == 1 and not dashboard["terminal"]
    partial["v04"]["status"] = "failed"
    status, dashboard = derive_status(task, list(partial.values()), "已选中")
    assert status == "可拉回" and dashboard["terminal"] and not dashboard["deliverables_ready"]
    status, dashboard = derive_status(task, [{"status": "failed"}, {"status": "cancelled"}], "已选中")
    assert status == "已结束（全部失败）" and dashboard["terminal"] and not dashboard["deliverables_ready"]
    status, dashboard = derive_status(task, [], "未知")
    assert status == "素材未登记"
    assert status_details(status, dashboard, "未知")["next_action"] == "登记角色素材"
    missing = root / "missing.mp4"
    status, dashboard = derive_status(task, [{"status": "downloaded", "output": str(missing),
                                               "mp3": str(root / "missing.mp3")}], "缺失")
    assert status == "成品缺失", "远端任务存在后，素材缺失不能覆盖真实成品状态"
    assert dashboard["missing_deliverables"] == 1
    status, dashboard = derive_status(task, [{"status": "completed"}], "缺失")
    assert status == "可拉回", "远端任务存在后必须优先显示真实生产状态"
    assert STAGE_ORDER == ["准备中", "生产中", "待拉回", "需处理", "已交付"]

    workspace = root / "dashboard-terminal"
    project = workspace / "项目"
    task_root = project / "文字素材"
    state_root = project / "已生成视频" / "TDB+1个任务"
    mp3_root = project / "已转mp3" / "TDB+1个任务"
    for path in (task_root, state_root, mp3_root):
        path.mkdir(parents=True, exist_ok=True)
    (workspace / "项目注册表.json").write_text(json.dumps({
        "projects": {"项目": {"project_root": str(project), "active": True}}
    }, ensure_ascii=False), encoding="utf-8")
    (task_root / "TDB+1个任务.json").write_text(json.dumps([{
        "剧本名字": "测试剧", "task_ID": "TDB_1", "角色名字": "角色",
        "台词": "测试。", "时长": "4秒", "提示词": "fixture",
    }], ensure_ascii=False), encoding="utf-8")
    video = state_root / "TDB_1_角色_测试_v01.mp4"
    mp3 = mp3_root / "TDB_1_角色_测试_v01.mp3"
    video.write_bytes(b"video"); mp3.write_bytes(b"audio")
    jobs = {
        "TDB/v01": {"input_task_id": "TDB_1", "status": "downloaded", "output": str(video), "mp3": str(mp3)},
        "TDB/v02": {"input_task_id": "TDB_1", "status": "failed"},
    }
    state_root.joinpath(".seedance-state.json").write_text(json.dumps({"jobs": jobs}, ensure_ascii=False), encoding="utf-8")
    row, files = resolve_completed(workspace, "项目::TDB_1")
    assert row["status"] == "已结束（含失败）" and row["complete"] is True
    assert row["stage"] == "已交付" and row["requires_attention"] is True
    assert row["next_action"] == "检查失败版本或打开成品"
    assert row["duration"] == "4秒" and row["source_name"] == "TDB+1个任务.json"
    assert row["updated_at"] and scan_workspace(workspace)[0]["source"]
    assert set(files) == {video.resolve(), mp3.resolve()}
    return {"pullback_terminal_gate": "OK", "dashboard_terminal_counts": "OK",
            "dashboard_smart_states": "OK"}


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
        "announcement": PACKAGE / "v2.1更新公告.md",
        "quick": Path(r"D:\配音工具总结\文档\v2.1\配音工作流使用说明.md"),
        "published_manual": Path(r"D:\配音工具总结\文档\v2.1\配音工具详细使用手册.md"),
        "published_announcement": Path(r"D:\配音工具总结\文档\v2.1\v2.1更新公告.md"),
    }
    for path in docs.values():
        assert path.is_file() and path.stat().st_size > 300
        text = path.read_text(encoding="utf-8-sig")
        assert "v2.1" in text and "v1.0.9" not in text
    combined = "\n".join(path.read_text(encoding="utf-8-sig") for path in docs.values())
    for required in ("创建项目", "Seedance API配置工具", "立即写", "余额不足", "5.5", "deepseek-v4-pro", "D:\\codex-board"):
        assert required in combined, f"documentation missing: {required}"
    assert docs["manual"].read_bytes() == docs["published_manual"].read_bytes()
    assert docs["announcement"].read_bytes() == docs["published_announcement"].read_bytes()
    assert docs["quick"].stat().st_size < docs["manual"].stat().st_size
    announcement = docs["announcement"].read_text(encoding="utf-8-sig")
    for required in (
        "voice-production-toolkit4bingchuan", "develop/v2.1", "pull --ff-only",
        "install.ps1 -Force", "configure_ccswitch_model.py --dry-run",
        "不得调用 Seedance", "不得向服务器", "integrity_check: ok",
    ):
        assert required in announcement, f"update announcement missing: {required}"
    assert announcement.count("```text") == 1
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8-sig")
    assert "docs/v2.1更新公告.md" in readme
    manual = docs["manual"].read_text(encoding="utf-8-sig")
    assert len(manual.encode("utf-8")) > 18000
    for section in ("第一次使用", "日常生产", "故障处理", "状态说明", "交付检查清单", "参考资料"):
        assert section in manual, f"detailed manual missing section: {section}"
    for link in (
        "https://developers.openai.com/codex/permissions",
        "https://developers.openai.com/codex/build-skills",
        "https://developers.openai.com/codex/learn/best-practices",
        "https://developers.openai.com/codex/automations",
        "https://github.com/freestylefly/CodexGuide",
    ):
        assert link in manual, f"detailed manual missing reference: {link}"
    return {"documents": "OK", "manuals_identical": True}


def main() -> None:
    base = TEST_ROOT / ".test-artifacts"
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="workflow-fixture-", dir=base))
    try:
        result = {}
        result.update(test_api_gui_and_failover(root))
        result.update(test_ccswitch_mapping(root))
        result.update(test_ccswitch_api_import(root))
        result.update(test_chat_workflow(root))
        result.update(test_terminal_and_dashboard(root))
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
