#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures as cf
import difflib
import http.client
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from manage_api_pool import (
    BalanceExhaustedError,
    ensure_not_paused,
    is_balance_error,
    raise_if_balance_error,
    signal_balance_exhausted,
)

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
REQUIRED_KEYS = ("剧本名字", "task_ID", "角色名字", "台词", "时长", "提示词")
TASK_FILE_RE = re.compile(r"^(.+)\+([1-9]\d*)个任务$")
INVALID_FOLDER_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
STATE_LOCK = threading.Lock()


@dataclass(frozen=True)
class Item:
    task_name: str
    source: str
    item_id: str
    script_name: str
    input_task_id: str
    role: str
    line: str
    seconds: str
    prompt: str

    @property
    def key(self) -> str:
        return f"{self.task_name}/{self.input_task_id}"


@dataclass(frozen=True)
class Reference:
    script_name: str
    role: str
    folder: Path
    videos: tuple[Path, ...]
    audios: tuple[Path, ...]


def reference_key(script_name: str, role: str) -> str:
    return f"{script_name}\u241f{role}"


def safe_name(text: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text).strip(" .")
    return text[:100] or "item"


def enforce_dialogue_whitelist(prompt: str, line: str) -> str:
    # Keep the full target line exactly once in the final prompt. Repeating the
    # complete line in performance notes can make a generative model repeat it.
    prompt_without_line = prompt.replace(line, "目标台词")
    rule = (
        f"【最高优先级台词白名单——覆盖前文任何可能冲突的描述】成片中唯一允许人物发声的内容是："
        f"“{line}”。人物必须从头到尾只完整说这句话一次，字词与顺序必须完全一致。"
        "参考音视频只用于复刻音色和自然说话习惯，不得复述、继承或生成参考素材中的原台词、口头禅、旁白、第二人声及背景声音。"
        "目标句之前、之后和中间都不得说任何其他可辨识的字、词或声音内容；严禁添加开场白、"
        "称呼、回应、解释、语气词、口头禅、旁白、重复、改写、漏词、续写和第二句话。"
        "不要朗读提示词或表演说明。即使场景上下文暗示人物还会继续对话，也必须在目标句结束后保持静音。"
        "若无法严格遵守，宁可保持静音，也绝不能补充目标句之外的内容。"
    )
    return prompt_without_line.rstrip() + "\n\n" + rule


def duration_text(value: Any) -> str:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*秒?\s*", str(value))
    number = float(match.group(1)) if match else 4.0
    return str(int(number)) if number.is_integer() else str(number)


def parse_voice_task_json(path: Path) -> list[Item]:
    filename = TASK_FILE_RE.fullmatch(path.stem)
    if not filename:
        raise ValueError(f"任务文件名不符合 task_id+N个任务.json：{path.name}")
    task_name = path.stem
    file_task_id = filename.group(1)
    declared_count = int(filename.group(2))
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list) or not data:
        raise ValueError(f"{path.name}: JSON 根节点必须是非空数组；单任务也要使用 [{{...}}]")
    if len(data) != declared_count:
        raise ValueError(f"{path.name}: 文件名标注 {declared_count} 个任务，实际为 {len(data)} 个")
    width = max(3, len(str(len(data))))
    result: list[Item] = []
    expected = set(REQUIRED_KEYS)
    for index, raw in enumerate(data, 1):
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError(f"{path.name}: 第 {index} 项必须且只能包含：{'、'.join(REQUIRED_KEYS)}")
        values: dict[str, str] = {}
        for key in REQUIRED_KEYS:
            value = raw[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{path.name}: 第 {index} 项的“{key}”必须是非空字符串")
            values[key] = value.strip()
        if not re.fullmatch(r"[1-9]\d*秒", values["时长"]):
            raise ValueError(f"{path.name}: 第 {index} 项的“时长”必须类似“4秒”")
        for key in ("剧本名字", "角色名字"):
            if values[key] in {".", ".."} or INVALID_FOLDER_NAME.search(values[key]):
                raise ValueError(f"{path.name}: 第 {index} 项的“{key}”必须是安全的单层目录名")
        expected_item_task_id = f"{file_task_id}_{index}"
        if values["task_ID"] != expected_item_task_id:
            raise ValueError(
                f"{path.name}: 第 {index} 项的“task_ID”必须为“{expected_item_task_id}”"
            )
        if values["台词"] not in values["提示词"]:
            raise ValueError(f"{path.name}: 第 {index} 项的提示词未包含完整原台词")
        result.append(Item(
            task_name, path.name, f"{index:0{width}d}", values["剧本名字"], values["task_ID"], values["角色名字"],
            values["台词"], duration_text(values["时长"]), values["提示词"],
        ))
    if len({item.script_name for item in result}) != 1:
        raise ValueError(f"{path.name}: 同一个 JSON 文件内的“剧本名字”必须一致")
    return result


def discover_items(root: Path, task_ids: set[str] | None = None,
                   input_task_ids: set[str] | None = None) -> tuple[list[Item], list[str]]:
    source_root = root / "文字素材"
    if not source_root.is_dir():
        raise ValueError(f"文字素材目录不存在：{source_root}")
    task_files = sorted((p for p in source_root.glob("*.json")
                         if TASK_FILE_RE.fullmatch(p.stem)
                         and (not task_ids or TASK_FILE_RE.fullmatch(p.stem).group(1) in task_ids)),
                        key=lambda p: p.name)
    if not task_files:
        selected = "、".join(sorted(task_ids)) if task_ids else "task_id+N个任务.json"
        raise ValueError(f"未找到任务 JSON：{source_root}\\{selected}")
    items: list[Item] = []
    warnings: list[str] = []
    seen_task_ids: dict[str, str] = {}
    for task_file in task_files:
        parsed = parse_voice_task_json(task_file)
        for item in parsed:
            previous = seen_task_ids.get(item.input_task_id)
            if previous:
                raise ValueError(
                    f"重复 task_ID：{item.input_task_id} 同时出现在 {previous} 和 {task_file.name}"
                )
            seen_task_ids[item.input_task_id] = task_file.name
        items.extend(item for item in parsed
                     if not input_task_ids or item.input_task_id in input_task_ids)
    if input_task_ids:
        found = {item.input_task_id for item in items}
        missing = input_task_ids - found
        if missing:
            raise ValueError(f"未找到 input task_ID：{'、'.join(sorted(missing))}")
    return items, warnings


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def selected_files(folder: Path, manifest: dict[str, Any], singular: str,
                   plural: str, extensions: set[str]) -> tuple[Path, ...]:
    raw = manifest.get(plural)
    if raw is None and manifest.get(singular):
        raw = [manifest[singular]]
    if raw is None:
        return tuple(sorted(
            (path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in extensions),
            key=lambda path: path.name,
        ))
    if not isinstance(raw, list) or not raw or not all(isinstance(name, str) and name.strip() for name in raw):
        raise ValueError(f"{folder / 'reference.json'}: {plural} 必须是非空文件名数组")
    files = tuple(folder / name for name in raw)
    for path in files:
        if not path.resolve().is_relative_to(folder.resolve()):
            raise ValueError(f"指定参考素材必须位于角色目录内：{path}")
        if not path.is_file() or path.suffix.lower() not in extensions:
            raise ValueError(f"指定参考素材不存在或格式不支持：{path}")
    return files


def resolve_references(root: Path, items: list[Item]) -> tuple[dict[str, Reference], list[str]]:
    base = root / "角色音色素材"
    result: dict[str, Reference] = {}
    errors = []
    pairs = sorted({(item.script_name, item.role) for item in items})
    for script_name, role in pairs:
        script_folder = base / script_name
        aliases_path = script_folder / "角色映射.json"
        aliases = read_json(aliases_path) if aliases_path.exists() else {}
        mapped_role = str(aliases.get(role, role)) if isinstance(aliases, dict) else role
        folder = script_folder / mapped_role
        if not folder.is_dir():
            errors.append(f"剧本 {script_name} / 角色 {role}: 找不到素材目录 {folder}")
            continue
        manifest_path = folder / "reference.json"
        manifest = read_json(manifest_path) if manifest_path.exists() else {}
        if not isinstance(manifest, dict):
            errors.append(f"{manifest_path}: 根节点必须是对象")
            continue
        try:
            videos = selected_files(folder, manifest, "video", "videos", VIDEO_EXTS)
            audios = selected_files(folder, manifest, "audio", "audios", AUDIO_EXTS)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not videos:
            errors.append(f"剧本 {script_name} / 角色 {role}: 缺少参考视频；每个请求必须上传一个视频")
            continue
        key = reference_key(script_name, role)
        result[key] = Reference(script_name, role, folder, videos, audios)
    return result, errors


def override_reference_audio(refs: dict[str, Reference], values: list[str]) -> None:
    """Replace one role's audio bundle for this run without changing its manifest."""
    for value in values:
        if "=" not in value:
            raise ValueError("--reference-audio 格式应为 角色=绝对音频路径")
        role, raw_path = value.split("=", 1)
        role = role.strip()
        path = Path(raw_path.strip())
        matches = [key for key, ref in refs.items() if ref.role == role]
        if len(matches) != 1:
            raise ValueError(f"--reference-audio 无法唯一匹配角色：{role}")
        if not path.is_absolute() or not path.is_file() or path.suffix.lower() not in AUDIO_EXTS:
            raise ValueError(f"指定参考音频不存在或格式不支持：{path}")
        key = matches[0]
        ref = refs[key]
        refs[key] = Reference(ref.script_name, ref.role, ref.folder, ref.videos, (path,))


def ffmpeg_exe() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("未找到 FFmpeg；请安装 ffmpeg 或 imageio-ffmpeg") from exc


def run_ffmpeg(args: list[str]) -> None:
    process = subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args],
                             capture_output=True, text=True)
    if process.returncode:
        raise RuntimeError(process.stderr.strip() or "FFmpeg 处理失败")


def spoken_text(text: str) -> str:
    return "".join(character for character in text.strip()
                   if not character.isspace() and not unicodedata.category(character).startswith("P"))


def recognize_wav(wav_path: Path, target: str = "") -> list[dict[str, Any]]:
    script = Path(__file__).with_name("transcribe_windows.ps1")
    command = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
        "-InputWav", str(wav_path),
    ]
    if target:
        command.extend(["-TargetText", target])
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if process.returncode:
        raise RuntimeError(process.stderr.strip() or "Windows 中文语音识别失败")
    try:
        return json.loads(process.stdout.strip())["results"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError(f"无法解析语音识别结果：{process.stdout[-500:]}") from exc


def extract_mp3(video: Path, destination: Path, start: float = 0.0,
                end: float | None = None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".part.mp3")
    args = ["-i", str(video), "-vn"]
    if start > 0 or end is not None:
        filters = [f"atrim=start={max(0.0, start):.3f}"]
        if end is not None:
            filters[0] += f":end={max(start + 0.02, end):.3f}"
        filters.append("asetpts=PTS-STARTPTS")
        args.extend(["-af", ",".join(filters)])
    args.extend(["-codec:a", "libmp3lame", "-q:a", "2", str(temp)])
    run_ffmpeg(args)
    os.replace(temp, destination)


def align_target_speech(wav_path: Path, target_line: str,
                        dictation: list[dict[str, Any]]) -> dict[str, Any]:
    target = spoken_text(target_line)
    exact = recognize_wav(wav_path, target)
    viable = [result for result in exact if float(result.get("confidence") or 0.0) >= 0.15]
    if viable:
        chosen = max(viable, key=lambda result: float(result.get("confidence") or 0.0))
        return {
            "start": float(chosen["start"]), "end": float(chosen["end"]),
            "confidence": float(chosen["confidence"]), "method": "exact",
        }

    chunks = [spoken_text(part) for part in re.split(r"[，。！？；、,.!?;:：]+", target_line)]
    chunks = [chunk for chunk in chunks if chunk]
    if len(chunks) == 1 and len(chunks[0]) >= 5:
        midpoint = len(chunks[0]) // 2
        chunks = [chunks[0][:midpoint], chunks[0][midpoint:]]
    def align_chunk(chunk: str, minimum_start: float) -> list[dict[str, Any]]:
        results = recognize_wav(wav_path, chunk)
        candidates = [result for result in results
                      if float(result.get("confidence") or 0.0) >= 0.10
                      and float(result["start"]) >= minimum_start - 0.25]
        if candidates:
            return [max(candidates, key=lambda result: float(result.get("confidence") or 0.0))]
        if len(chunk) >= 4:
            midpoint = len(chunk) // 2
            left = align_chunk(chunk[:midpoint], minimum_start)
            right = align_chunk(chunk[midpoint:], float(left[-1]["end"]))
            return left + right
        raise RuntimeError(f"未识别到目标台词片段“{chunk}”：{target_line}")

    aligned = []
    previous_end = -1.0
    chunk_failed = False
    for chunk in chunks:
        try:
            chunk_results = align_chunk(chunk, previous_end)
        except RuntimeError:
            chunk_failed = True
            break
        aligned.extend(chunk_results)
        previous_end = float(chunk_results[-1]["end"])
    if not chunk_failed and aligned:
        return {
            "start": float(aligned[0]["start"]), "end": float(aligned[-1]["end"]),
            "confidence": min(float(result["confidence"]) for result in aligned),
            "method": "chunks", "chunks": chunks,
        }

    speech = [result for result in dictation
              if result.get("start") is not None and result.get("end") is not None]
    recognized = spoken_text("".join(str(result.get("text") or "") for result in speech))
    similarity = difflib.SequenceMatcher(None, target, recognized).ratio() if recognized else 0.0
    length_ratio = len(recognized) / len(target) if target else 0.0
    if speech and similarity >= 0.40 and 0.60 <= length_ratio <= 1.40:
        return {
            "start": min(float(result["start"]) for result in speech),
            "end": max(float(result["end"]) for result in speech),
            "confidence": similarity, "method": "fuzzy_whole",
            "recognized": recognized,
        }
    raise RuntimeError(f"未能可靠对齐目标台词：{target_line}；识别为：{recognized or '空'}")


def semantic_trim_to_mp3(video: Path, destination: Path, target_line: str) -> dict[str, Any]:
    target = spoken_text(target_line)
    if not target:
        raise ValueError("目标台词为空，无法语义裁剪")
    with tempfile.TemporaryDirectory() as temp_dir:
        wav_path = Path(temp_dir) / "audio.wav"
        run_ffmpeg(["-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(wav_path)])
        with wave.open(str(wav_path), "rb") as wav_file:
            duration = wav_file.getnframes() / wav_file.getframerate()
        dictation = recognize_wav(wav_path)
        try:
            alignment = align_target_speech(wav_path, target_line, dictation)
        except RuntimeError as exc:
            # Recognition is advisory. If it cannot reliably prove where the
            # target sentence is, preserve the complete audio instead of
            # risking a clipped line.
            extract_mp3(video, destination)
            return {
                "target": target_line, "confidence": 0.0,
                "method": "unrecognized_preserve_full",
                "recognition_note": str(exc),
                "target_start": None, "target_end": None,
                "extra_before": False, "extra_after": False,
                "output_start": 0.0, "output_end": duration,
                "source_duration": duration,
            }
        confidence = float(alignment["confidence"])
        target_start = float(alignment["start"])
        target_end = float(alignment["end"])
        speech = [result for result in dictation
                  if result.get("start") is not None and result.get("end") is not None]
        tolerance = 0.22
        extra_before = any(float(result["start"]) < target_start - tolerance for result in speech)
        extra_after = any(float(result["end"]) > target_end + tolerance for result in speech)
        cut_start = max(0.0, target_start - 0.08) if extra_before else 0.0
        cut_end = min(duration, target_end + 0.08) if extra_after else duration
        extract_mp3(video, destination, cut_start, cut_end)
        return {
            "target": target_line, "confidence": confidence, "method": alignment["method"],
            "target_start": target_start, "target_end": target_end,
            "extra_before": extra_before, "extra_after": extra_after,
            "output_start": cut_start, "output_end": cut_end, "source_duration": duration,
        }


def extract_reference_audio(video: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-i", str(video), "-vn", "-ac", "1", "-ar", "44100", str(destination)])
    return destination


def multipart_upload(url: str, api_key: str, file_path: Path, fields: dict[str, str]) -> dict[str, Any]:
    boundary = "----Codex" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    prefix = b"".join(parts) + (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{file_path.name}\"\r\n"
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")
    suffix = f"\r\n--{boundary}--\r\n".encode()
    parsed = urllib.parse.urlsplit(url)
    connection_class = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_class(parsed.hostname, parsed.port, timeout=180)
    path = urllib.parse.urlunsplit(("", "", parsed.path, parsed.query, ""))
    connection.putrequest("POST", path)
    connection.putheader("Authorization", f"Bearer {api_key}")
    connection.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
    connection.putheader("Content-Length", str(len(prefix) + file_path.stat().st_size + len(suffix)))
    connection.endheaders()
    connection.send(prefix)
    with file_path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            connection.send(chunk)
    connection.send(suffix)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    if response.status >= 400:
        message = f"上传失败 HTTP {response.status}: {body[:500].decode('utf-8', 'replace')}"
        raise_if_balance_error(message, response.status)
        raise RuntimeError(message)
    return json.loads(body.decode("utf-8"))


def json_request(method: str, url: str, api_key: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {api_key}")
    if data is not None:
        request.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read(1000).decode("utf-8", "replace")
        message = f"HTTP {exc.code}: {body}"
        raise_if_balance_error(message, exc.code)
        raise RuntimeError(message) from exc


def download(url: str, api_key: str, destination: Path) -> None:
    request = urllib.request.Request(url, method="GET", headers={"Authorization": f"Bearer {api_key}"})
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=300) as response, temp.open("wb") as output:
            shutil.copyfileobj(response, output, 1024 * 1024)
    except urllib.error.HTTPError as exc:
        body = exc.read(1000).decode("utf-8", "replace")
        message = f"下载失败 HTTP {exc.code}: {body}"
        raise_if_balance_error(message, exc.code)
        raise RuntimeError(message) from exc
    os.replace(temp, destination)


def state_path(root: Path, task_name: str) -> Path:
    return root / "已生成视频" / task_name / ".seedance-state.json"


def load_states(root: Path, task_names: set[str]) -> dict[str, dict[str, Any]]:
    combined = {}
    for task_name in task_names:
        path = state_path(root, task_name)
        if path.exists():
            combined.update(read_json(path).get("jobs", {}))
    return combined


def save_states(root: Path, states: dict[str, dict[str, Any]]) -> None:
    with STATE_LOCK:
        grouped: dict[str, dict[str, Any]] = {}
        for key, value in states.items():
            grouped.setdefault(value["task_name"], {})[key] = value
        for task_name, jobs in grouped.items():
            path = state_path(root, task_name)
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
            temp.write_text(json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2), encoding="utf-8")
            for attempt in range(10):
                try:
                    os.replace(temp, path)
                    break
                except PermissionError:
                    if attempt == 9:
                        raise
                    time.sleep(0.1 * (attempt + 1))


def append_failure(root: Path, job: dict[str, Any], issue: str) -> None:
    path = root / "问题与改进log" / "问题建议.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    block = (
        f"\n## {datetime.now().astimezone().isoformat(timespec='seconds')} | {job['task_name']} | {job['input_task_id']} | v{job['variant']:02d}\n\n"
        f"- 剧本分类：{job['script_name']}\n- 输入 task_ID：{job['input_task_id']}\n"
        f"- 角色：{job['role']}\n- 台词：{job.get('line') or '未填写'}\n- 问题类型：接口失败\n"
        f"- 问题描述：{issue}\n- 改进建议：检查错误后只重做该版本\n"
        f"- 远端任务 ID：{job.get('api_id') or '未创建'}\n- 原视频：{job.get('output') or '未生成'}\n- 处理状态：待返工\n"
    )
    with STATE_LOCK, path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(block)


def output_name(item: Item, variant: int) -> str:
    line_label = safe_name(item.line)[:40]
    return f"{safe_name(item.input_task_id)}_{safe_name(item.role)}_{line_label}_v{variant:02d}.mp4"


def upload_all_references(root: Path, refs: dict[str, Reference], config: dict[str, Any],
                          workers: int) -> dict[str, dict[str, list[str]]]:
    api_key = config["api_key"]
    # Keep reference uploads in the same environment as generation so
    # environment-scoped API keys work for both chat.q1.com and chat-test.
    parsed_base = urllib.parse.urlsplit(str(config["base_url"]))
    host = urllib.parse.urlunsplit((parsed_base.scheme, parsed_base.netloc, "", "", "")).rstrip("/")
    temp_dir = root / "已生成视频" / ".reference-audio-cache"

    def one(key: str, ref: Reference) -> tuple[str, dict[str, list[str]]]:
        audios = list(ref.audios)
        if not audios:
            for index, video in enumerate(ref.videos, 1):
                destination = temp_dir / safe_name(ref.script_name) / f"{safe_name(ref.role)}_{index:02d}.wav"
                audios.append(extract_reference_audio(video, destination))
        video_urls = []
        for index, video in enumerate(ref.videos, 1):
            try:
                # Preserve the user's complete reference upload, then use a compact clip
                # for generation because q1 rejects long reference-video durations.
                multipart_upload(
                    host + "/api/upload/video", api_key, video, {"convert": "false"}
                )
                clip = temp_dir / safe_name(ref.script_name) / f"{safe_name(ref.role)}_{index:02d}_reference-clip.mp4"
                clip.parent.mkdir(parents=True, exist_ok=True)
                run_ffmpeg(["-i", str(video), "-t", "10", "-c", "copy", str(clip)])
                video_urls.append(multipart_upload(
                    host + "/api/upload/video", api_key, clip, {"convert": "false"}
                )["filename"])
            except Exception as exc:
                raise RuntimeError(f"上传视频失败 {video}: {exc}") from exc
        audio_urls = []
        for audio in audios:
            try:
                audio_urls.append(multipart_upload(
                    host + "/api/upload/audio", api_key, audio,
                    {"convert": "false", "compress": "false"}
                )["filename"])
            except Exception as exc:
                raise RuntimeError(f"上传音频失败 {audio}: {exc}") from exc
        return key, {"videos": video_urls, "audios": audio_urls}

    uploaded: dict[str, dict[str, list[str]]] = {}
    # q1 upload storage can race on temporary files; upload role bundles serially.
    with cf.ThreadPoolExecutor(max_workers=1) as pool:
        for key, value in pool.map(lambda pair: one(*pair), refs.items()):
            uploaded[key] = value
    return uploaded


def run_generation(root: Path, items: list[Item], refs: dict[str, Reference], workers: int,
                   poll_seconds: int, force_regenerate: bool = False,
                   output_folder: str | None = None,
                   resume_only: bool = False,
                   submit_only: bool = False,
                   direct_mp3: bool = False,
                   poll_once: bool = False,
                   only_variants: set[tuple[str, int]] | None = None,
                   variants_per_line: int = 4,
                   config_file: str | None = None) -> None:
    config_candidates = [
        Path(config_file) if config_file else root / "apis" / "doubao_api_config.json",
        *( [] if config_file else [root / "doubao_api_config.json"] ),
    ]
    config_path = next((path for path in config_candidates if path.exists()), None)
    if config_path is None:
        raise ValueError("缺少配置文件：" + " 或 ".join(str(path) for path in config_candidates))
    config = read_json(config_path)
    for field in ("api_key", "base_url", "model"):
        if not config.get(field):
            raise ValueError(f"配置缺少字段：{field}")
    ffmpeg_exe()
    uploaded = {} if resume_only else upload_all_references(root, refs, config, workers)
    api_key = config["api_key"]
    base_url = str(config["base_url"]).rstrip("/")
    if not base_url.endswith("/v1"):
        base_url += "/v1"
    destination_tasks = ({output_folder} if output_folder else
                         {item.task_name for item in items})
    # A caller that supplies an explicit output folder expects a fully
    # isolated batch.  Do not merge an older source-task state here: matching
    # task IDs could otherwise be mistaken for outputs in the new folder.
    # Preserve the legacy recovery behavior only for the default layout.
    state_sources = set(destination_tasks) if output_folder else (
        set(destination_tasks) | {items[0].task_name}
    )
    states = load_states(root, state_sources)
    jobs: dict[str, dict[str, Any]] = {}
    for item in items:
        destination_task = output_folder or item.task_name
        for variant in range(1, variants_per_line + 1):
            if only_variants and (item.input_task_id, variant) not in only_variants:
                continue
            key = f"{item.key}/v{variant:02d}"
            output = root / "已生成视频" / destination_task / output_name(item, variant)
            default_job = {
                "task_name": destination_task, "source_task_name": item.task_name,
                "source": item.source, "item_id": item.item_id,
                "script_name": item.script_name, "input_task_id": item.input_task_id,
                "role": item.role, "line": item.line, "seconds": item.seconds, "variant": variant,
                "status": "new", "api_id": "", "output": str(output),
            }
            job = states.get(key, default_job)
            if force_regenerate and (not job.get("force_pending") or job.get("status") == "failed"):
                job = dict(default_job)
                job["force_pending"] = True
            job["script_name"] = item.script_name
            job["input_task_id"] = item.input_task_id
            job["task_name"] = destination_task
            job["source_task_name"] = item.task_name
            job["output"] = str(output)
            job["original_prompt"] = item.prompt
            prompt = enforce_dialogue_whitelist(item.prompt, item.line)
            if force_regenerate:
                prompt += ("\n【返工稳定性要求】只输出清晰的单人近距离人声与目标台词；"
                           "不生成复杂画面、多人互动、动作或额外叙事。")
            job["prompt"] = prompt
            jobs[key] = job
    states.update(jobs)
    save_states(root, states)
    if resume_only:
        missing_ids = [key for key, job in jobs.items() if not job.get("api_id")]
        if missing_ids:
            raise ValueError("--resume-only 发现尚未提交的任务，不能跳过素材上传：" +
                             ", ".join(missing_ids[:8]))

    balance_stop = threading.Event()

    def submit(pair: tuple[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        key, job = pair
        if balance_stop.is_set():
            job.update(status="balance_paused", error="其他并发任务检测到余额不足")
            return key, job
        if Path(job["output"]).exists() and not job.get("force_pending"):
            if job.get("status") != "downloaded":
                job["status"] = "completed"
            return key, job
        if job.get("api_id"):
            return key, job
        reference_urls = uploaded[reference_key(job["script_name"], job["role"])]
        reference_index = job["variant"] - 1
        payload = {
            "model": config["model"], "prompt": job["prompt"], "n": 1,
            "size": "480x854", "seconds": job["seconds"], "aspect_ratio": "9:16",
            "quality": "480p", "generate_audio": True,
            "reference_video": reference_urls["videos"][reference_index % len(reference_urls["videos"])],
            "reference_audio": reference_urls["audios"][reference_index % len(reference_urls["audios"])],
        }
        try:
            result = json_request("POST", base_url + "/videos", api_key, payload)
            job.update(api_id=result["id"], status=result.get("status", "queued"))
        except BalanceExhaustedError as exc:
            balance_stop.set()
            job.update(status="balance_blocked", error=str(exc))
            raise
        except Exception as exc:
            job.update(status="submit_failed", error=str(exc))
            append_failure(root, job, str(exc))
        return key, job

    balance_error: BalanceExhaustedError | None = None
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(submit, pair): pair[0] for pair in jobs.items()}
        for future in cf.as_completed(futures):
            try:
                key, job = future.result()
                states[key] = job
                save_states(root, states)
            except BalanceExhaustedError as exc:
                balance_stop.set()
                balance_error = balance_error or exc
                key = futures[future]
                states[key] = jobs[key]
                save_states(root, states)
    if balance_error:
        raise balance_error

    if submit_only:
        counts: dict[str, int] = {}
        for job in jobs.values():
            counts[job["status"]] = counts.get(job["status"], 0) + 1
        print("已提交并记录：" + ", ".join(
            f"{key}={value}" for key, value in sorted(counts.items())
        ), flush=True)
        return

    while True:
        pending = [(key, job) for key, job in jobs.items()
                   if job.get("api_id") and job.get("status") not in {"completed", "failed", "downloaded"}]
        if not pending:
            break
        if not poll_once:
            time.sleep(poll_seconds)

        def poll(pair: tuple[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
            key, job = pair
            try:
                result = json_request("GET", f"{base_url}/videos/{job['api_id']}", api_key)
                job["status"] = result.get("status", job["status"])
                if job["status"] == "failed":
                    job["error"] = str(result.get("error") or "Seedance 返回 failed")
                    append_failure(root, job, job["error"])
            except BalanceExhaustedError:
                raise
            except Exception as exc:
                job["last_poll_error"] = str(exc)
            return key, job

        with cf.ThreadPoolExecutor(max_workers=workers) as pool:
            for key, job in pool.map(poll, pending):
                states[key] = jobs[key] = job
        save_states(root, states)
        counts: dict[str, int] = {}
        for job in jobs.values():
            counts[job["status"]] = counts.get(job["status"], 0) + 1
        print("状态：" + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())), flush=True)
        if poll_once:
            break

    # A download or MP3 extraction can be interrupted after the remote task
    # has completed. Retry that local step with the saved API ID instead of
    # creating a second billable generation request.
    completed = [(key, job) for key, job in jobs.items()
                 if job.get("status") in {"completed", "postprocess_failed"}]

    def finish(pair: tuple[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        key, job = pair
        video = Path(job["output"])
        try:
            if job.get("force_pending") or not video.exists():
                download(f"{base_url}/videos/{job['api_id']}/content", api_key, video)
            mp3 = root / "已转mp3" / job["task_name"] / (video.stem + ".mp3")
            if direct_mp3:
                extract_mp3(video, mp3)
                job["semantic_trim"] = {"method": "direct_full_track", "trimmed": False}
            else:
                job["semantic_trim"] = semantic_trim_to_mp3(video, mp3, job["line"])
            job["status"] = "downloaded"
            job["mp3"] = str(mp3)
            job["force_pending"] = False
        except BalanceExhaustedError:
            raise
        except Exception as exc:
            job["status"] = "postprocess_failed"
            job["error"] = str(exc)
            append_failure(root, job, str(exc))
        return key, job

    # Windows System.Speech recognizers share native state and must run serially.
    with cf.ThreadPoolExecutor(max_workers=1) as pool:
        for key, job in pool.map(finish, completed):
            states[key] = jobs[key] = job
    save_states(root, states)


def extract_existing(root: Path, workers: int, task_ids: set[str] | None = None) -> None:
    items, _ = discover_items(root, task_ids)
    video_root = root / "已生成视频"
    task_dirs = sorted((path for path in video_root.iterdir() if path.is_dir()
                        and TASK_FILE_RE.fullmatch(path.name)
                        and (not task_ids or TASK_FILE_RE.fullmatch(path.name).group(1) in task_ids)),
                       key=lambda path: path.name)
    videos = sorted(video for task_dir in task_dirs for video in task_dir.glob("*.mp4"))
    if not videos:
        selected = "、".join(sorted(task_ids)) if task_ids else "全部任务"
        raise ValueError(f"没有找到可提取的 MP4：{selected}")

    def one(video: Path) -> tuple[Path, dict[str, Any]]:
        matches = [item for item in items if item.task_name == video.parent.name and video.name.startswith(
            f"{safe_name(item.input_task_id)}_{safe_name(item.role)}_"
        )]
        if len(matches) != 1:
            raise RuntimeError(f"无法为视频唯一匹配 JSON 台词：{video}")
        destination = root / "已转mp3" / video.parent.name / (video.stem + ".mp3")
        metadata = semantic_trim_to_mp3(video, destination, matches[0].line)
        return destination, metadata

    failures = []
    with cf.ThreadPoolExecutor(max_workers=1) as pool:
        future_to_video = {pool.submit(one, video): video for video in videos}
        for future in cf.as_completed(future_to_video):
            video = future_to_video[future]
            try:
                destination, metadata = future.result()
                print(json.dumps({"path": str(destination), **metadata}, ensure_ascii=False))
            except Exception as exc:
                failures.append((video, str(exc)))
                print(f"语义裁剪失败：{video}：{exc}", file=sys.stderr)
    if failures:
        raise RuntimeError(f"{len(failures)} 个视频语义裁剪失败；失败文件未覆盖")


def print_plan(items: list[Item], refs: dict[str, Reference], warnings: list[str], errors: list[str], variants_per_line: int) -> None:
    by_task: dict[str, list[Item]] = {}
    for item in items:
        by_task.setdefault(item.task_name, []).append(item)
    for task, task_items in by_task.items():
        print(f"{task}: {len(task_items)} 条台词，生成 {len(task_items) * variants_per_line} 个视频")
        for item in task_items:
            print(f"  {item.input_task_id} | {item.script_name}/{item.role} | {item.seconds}s | {item.line}")
    print(f"总计：{len(items)} 条台词，{len(items) * variants_per_line} 个视频，角色 {len(refs)} 个")
    for reference in refs.values():
        print(f"参考素材：{reference.script_name}/{reference.role}")
        for video in reference.videos:
            print(f"  视频：{video}")
        if reference.audios:
            for audio in reference.audios:
                print(f"  音频：{audio}")
        else:
            print("  音频：将从参考视频提取")
    for warning in warnings:
        print("警告：" + warning)
    for error in errors:
        print("错误：" + error)


def self_test() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        source = root / "文字素材"
        role = root / "角色音色素材" / "测试剧本" / "月儿"
        source.mkdir(parents=True)
        role.mkdir(parents=True)
        (source / "task_id_demo+1个任务.json").write_text(json.dumps([{
            "剧本名字": "测试剧本", "task_ID": "task_id_demo_1",
            "角色名字": "月儿", "台词": "不到十分钟。", "时长": "4秒",
            "提示词": "只用普通话自然说一次：不到十分钟。",
        }], ensure_ascii=False), encoding="utf-8")
        (role / "ref1.mp4").write_bytes(b"test")
        (role / "ref2.mp4").write_bytes(b"test")
        (role / "ref.mp3").write_bytes(b"test")
        items, warnings = discover_items(root)
        refs, errors = resolve_references(root, items)
        assert len(items) == 1 and items[0].seconds == "4" and items[0].item_id == "001"
        assert items[0].script_name == "测试剧本" and items[0].input_task_id == "task_id_demo_1"
        assert items[0].task_name == "task_id_demo+1个任务" and len(refs) == 1 and not warnings and not errors
        assert len(next(iter(refs.values())).videos) == 2 and len(next(iter(refs.values())).audios) == 1
        assert output_name(items[0], 4) == "task_id_demo_1_月儿_不到十分钟。_v04.mp4"
        forced_prompt = enforce_dialogue_whitelist("基础提示。", "不到十分钟。")
        assert "最高优先级台词白名单" in forced_prompt
        assert "只完整说这句话一次" in forced_prompt and "不得说任何其他" in forced_prompt
        assert forced_prompt.count("不到十分钟。") == 1
        assert is_balance_error("HTTP 402: payment required", 402)
        assert is_balance_error("余额不足，请充值", 403)
        assert not is_balance_error("HTTP 403: permission denied", 403)
        video = root / "sample.mp4"
        mp3 = root / "sample.mp3"
        run_ffmpeg([
            "-f", "lavfi", "-i", "color=c=black:s=160x284:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(video),
        ])
        extract_mp3(video, mp3)
        assert mp3.stat().st_size > 0
    print("self-test: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch q1 Seedance cloned-voice video pipeline.")
    parser.add_argument("--project-root", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true", help="Perform paid generation.")
    mode.add_argument("--submit-only", action="store_true",
                      help="Submit paid jobs, persist API IDs, then exit without polling or downloading.")
    mode.add_argument("--dry-run", action="store_true", help="Validate and print the plan (default).")
    mode.add_argument("--extract-only", action="store_true")
    mode.add_argument("--self-test", action="store_true")
    parser.add_argument("--max-workers", type=int, default=16)
    parser.add_argument("--poll-seconds", type=int, default=12)
    parser.add_argument("--task-id", action="append", default=[],
                        help="Only process this file task ID; repeat for multiple IDs.")
    parser.add_argument("--input-task-id", action="append", default=[],
                        help="Only process this JSON task_ID; repeat for multiple IDs.")
    parser.add_argument("--force-regenerate", action="store_true",
                        help="Submit new generation jobs even when outputs already exist.")
    parser.add_argument("--only-task", help="Only process one file task_id or full JSON stem.")
    parser.add_argument("--output-folder",
                        help="Write video, MP3, and resumable state to this separate output folder.")
    parser.add_argument("--resume-only", action="store_true",
                        help="Only poll saved API IDs and download results; skip reference uploads.")
    parser.add_argument("--direct-mp3", action="store_true",
                        help="Extract the complete video audio track to MP3 without semantic trimming.")
    parser.add_argument("--poll-once", action="store_true",
                        help="Query saved task IDs once, download completed jobs, then exit.")
    parser.add_argument("--variant", action="append", default=[],
                        help="Only process one task_ID/variant, e.g. 0720005_1/v02; repeat as needed.")
    parser.add_argument("--variants-per-line", type=int, default=4,
                        help="Number of independently generated versions per dialogue (default: 4).")
    parser.add_argument("--config-file",
                        help="Use this API configuration JSON instead of the default doubao_api_config.json.")
    parser.add_argument("--source-chat", default=os.environ.get("CODEX_CHAT_ROLE", "生成"),
                        choices=("理解文本与任务", "提示词", "生成", "监控", "拉回", "记录"),
                        help="Chat role used for emergency balance notifications.")
    parser.add_argument("--reference-audio", action="append", default=[],
                        help="Override one role's reference audio for this run: 角色=绝对音频路径.")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    root = Path(args.project_root)
    if args.max_workers < 1:
        raise ValueError("--max-workers 必须大于 0")
    if not 1 <= args.variants_per_line <= 8:
        raise ValueError("--variants-per-line 必须在 1 到 8 之间")
    if args.extract_only:
        extract_existing(root, args.max_workers, set(args.task_id) or None)
        return 0
    items, warnings = discover_items(root, set(args.task_id) or None,
                                     set(args.input_task_id) or None)
    if args.only_task:
        items = [item for item in items if item.task_name == args.only_task or
                 TASK_FILE_RE.fullmatch(item.task_name).group(1) == args.only_task]
        if not items:
            raise ValueError(f"未找到指定任务：{args.only_task}")
    refs, errors = resolve_references(root, items)
    override_reference_audio(refs, args.reference_audio)
    print_plan(items, refs, warnings, errors, args.variants_per_line)
    if warnings or errors:
        return 2
    # --resume-only is itself an execution mode: it must poll persisted API
    # jobs and download completed work without requiring --run as well.
    if args.run or args.resume_only or args.submit_only:
        ensure_not_paused(root)
        selected_variants = set()
        for value in args.variant:
            match = re.fullmatch(r"(.+)/v(0[1-8]|[1-8])", value.strip())
            if not match:
                raise ValueError(f"--variant 格式应为 task_ID/v01：{value}")
            selected_variants.add((match.group(1), int(match.group(2))))
        try:
            run_generation(root, items, refs, args.max_workers, args.poll_seconds,
                           args.force_regenerate, args.output_folder, args.resume_only,
                           args.submit_only, args.direct_mp3, args.poll_once,
                           selected_variants or None, args.variants_per_line, args.config_file)
        except BalanceExhaustedError as exc:
            file_task_ids = sorted({TASK_FILE_RE.fullmatch(item.task_name).group(1) for item in items})
            result = signal_balance_exhausted(
                root, args.source_chat, file_task_ids, str(exc)
            )
            print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
            return 42
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("已中断；任务 ID 已保存，下次使用 --run 继续。", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)
