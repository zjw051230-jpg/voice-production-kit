#!/usr/bin/env python3
"""Loopback-only companion for the BaaS voice dashboard.

It exposes read-only workspace scanning and a guarded "open output" action.
Generation, API configuration, file deletion and arbitrary command execution
are intentionally outside this agent.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def load_dashboard_module(script: Path):
    spec = importlib.util.spec_from_file_location("voice_dashboard_for_agent", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载看板扫描器：{script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Agent:
    def __init__(self, workspace: Path, dashboard_script: Path):
        self.workspace = workspace.resolve()
        self.dashboard = load_dashboard_module(dashboard_script)

    def scan(self) -> list[dict]:
        return self.dashboard.scan_workspace(self.workspace)

    def open_output(self, key: str) -> dict:
        rows = [row for row in self.scan() if row.get("key") == key]
        if len(rows) != 1 or not rows[0].get("complete"):
            raise ValueError("任务尚未完成，不能打开成品")
        project_name = str(rows[0].get("project") or "")
        task_id = str(rows[0].get("task_id") or "")
        projects = dict(self.dashboard.load_projects(self.workspace))
        root = projects.get(project_name)
        if not root:
            raise ValueError("任务所属项目不存在")
        output_root = self.dashboard.find_named(root, "已生成视频", "02_生产成品/01_生成视频")
        if output_root is None:
            raise ValueError("未找到生成视频目录")
        candidates = [p for p in output_root.rglob("*") if p.is_file() and task_id in p.name]
        target = (candidates[0].parent if candidates else output_root).resolve()
        if not self._inside_workspace(target):
            raise ValueError("拒绝打开工作区之外的路径")
        if os.name == "nt":
            os.startfile(str(target))  # type: ignore[attr-defined]
        else:
            raise RuntimeError("打开成品目录仅支持 Windows")
        return {"opened": str(target)}

    def _inside_workspace(self, path: Path) -> bool:
        try:
            path.relative_to(self.workspace)
            return True
        except ValueError:
            return False


class Handler(BaseHTTPRequestHandler):
    server_version = "VoiceLocalAgent/0.1"

    def _send(self, status: int, payload: object, content_type: str = "application/json") -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") if content_type == "application/json" else str(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, "", "text/plain")

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        try:
            if route == "/api/health":
                self._send(200, {"ok": True, "agent": "voice-local-agent", "workspace": str(self.server.agent.workspace)})
            elif route == "/api/scan":
                self._send(200, {"ok": True, "tasks": self.server.agent.scan()})
            else:
                self._send(404, {"ok": False, "error": "not_found"})
        except Exception as exc:
            self._send(500, {"ok": False, "error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if route != "/api/open-output":
                self._send(404, {"ok": False, "error": "not_found"})
                return
            key = str(body.get("key") or "")
            if not key or len(key) > 300:
                raise ValueError("缺少合法任务标识")
            self._send(200, {"ok": True, **self.server.agent.open_output(key)})
        except Exception as exc:
            self._send(400, {"ok": False, "error": str(exc)})


def main() -> int:
    parser = argparse.ArgumentParser(description="配音 BaaS 看板本地工作代理")
    parser.add_argument("--workspace-root", required=True, type=Path)
    parser.add_argument("--dashboard-script", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("本地代理只允许绑定回环地址")
    workspace = args.workspace_root.resolve()
    if not workspace.is_dir():
        parser.error(f"工作区不存在：{workspace}")
    script = args.dashboard_script
    if script is None:
        bundled = Path(__file__).resolve().with_name("voice_dashboard.py")
        script = bundled if bundled.is_file() else Path(__file__).resolve().parents[1] / "skills" / "voice-production-dashboard" / "scripts" / "voice_dashboard.py"
    if not script.is_file():
        parser.error(f"找不到看板扫描器：{script}")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.agent = Agent(workspace, script)  # type: ignore[attr-defined]
    print(f"Voice local agent listening on http://{args.host}:{args.port}")
    print(f"Workspace: {workspace}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
