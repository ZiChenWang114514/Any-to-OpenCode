#!/usr/bin/env python3
"""Start an isolated local OpenCode server and invoke a session safely."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULTS_PATH = SKILL_DIR / "references" / "defaults.json"


class OpenCodeAssistantError(RuntimeError):
    """A structured assistant-side error returned by OpenCode."""

    def __init__(self, details: dict[str, Any]) -> None:
        self.details = details
        super().__init__(str(details.get("message") or "OpenCode assistant returned an error"))


def load_defaults() -> dict[str, Any]:
    with DEFAULTS_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data.get("model"), str) or "/" not in data["model"]:
        raise ValueError(f"Invalid model in {DEFAULTS_PATH}: expected provider/model")
    return data


def find_opencode() -> str:
    names = ["opencode.cmd", "opencode.exe", "opencode"] if os.name == "nt" else ["opencode"]
    for name in names:
        if resolved := shutil.which(name):
            return resolved
    raise FileNotFoundError("OpenCode CLI was not found on PATH")


def run_cli(executable: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [executable, *args], capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, check=False,
    )


def choose_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def add_no_proxy(environment: dict[str, str]) -> None:
    raw = environment.get("NO_PROXY", environment.get("no_proxy", ""))
    entries = [item.strip() for item in raw.split(",") if item.strip()]
    for item in ("127.0.0.1", "localhost", "::1"):
        if item not in entries:
            entries.append(item)
    environment["NO_PROXY"] = environment["no_proxy"] = ",".join(entries)


def basic_auth(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("ascii")).decode("ascii")
    return f"Basic {token}"


def http_json(
    base_url: str, auth_header: str, method: str, path: str,
    body: dict[str, Any] | None = None, timeout: int = 30,
) -> Any:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{base_url}{path}", data=data, method=method,
        headers={
            "Authorization": auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        payload = response.read()
        return json.loads(payload.decode("utf-8")) if payload else None


def start_server(
    executable: str, workdir: Path, host: str, port: int,
    permission: Any, log_dir: Path,
) -> tuple[subprocess.Popen[Any], str, str]:
    username = "codex-opencode"
    password = secrets.token_urlsafe(32)
    environment = os.environ.copy()
    environment["OPENCODE_SERVER_USERNAME"] = username
    environment["OPENCODE_SERVER_PASSWORD"] = password
    environment["OPENCODE_PERMISSION"] = json.dumps(permission, separators=(",", ":"))
    add_no_proxy(environment)
    stdout_handle = (log_dir / "server.stdout.log").open("wb")
    stderr_handle = (log_dir / "server.stderr.log").open("wb")
    try:
        process = subprocess.Popen(
            [executable, "serve", "--hostname", host, "--port", str(port)],
            cwd=str(workdir), env=environment, stdin=subprocess.DEVNULL,
            stdout=stdout_handle, stderr=stderr_handle,
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
            start_new_session=(os.name != "nt"),
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()
    return process, username, password


def stop_owned_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    else:
        try:
            os.killpg(process.pid, 15)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def wait_for_health(
    base_url: str, auth_header: str, process: subprocess.Popen[Any], timeout: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"OpenCode server exited with code {process.returncode}")
        try:
            health = http_json(base_url, auth_header, "GET", "/global/health", timeout=3)
            if isinstance(health, dict) and health.get("healthy"):
                return health
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise TimeoutError(f"OpenCode server was not healthy within {timeout}s: {last_error}")


def split_model(model: str) -> tuple[str, str]:
    provider, model_id = model.split("/", 1)
    if not provider or not model_id:
        raise ValueError("Model must use provider/model format")
    return provider, model_id


def read_tail(path: Path, max_chars: int = 4000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-max_chars:]


def parse_assistant_response(
    response: dict[str, Any], session_id: str, requested_model_id: str,
) -> tuple[str, str | None]:
    info = response.get("info")
    info = info if isinstance(info, dict) else {}
    error = info.get("error")
    if isinstance(error, dict):
        data = error.get("data")
        data = data if isinstance(data, dict) else {}
        raise OpenCodeAssistantError({
            "session_id": session_id,
            "name": error.get("name") or "AssistantError",
            "message": data.get("message") or error.get("message") or "OpenCode assistant returned an error",
            "status_code": data.get("statusCode"),
            "retryable": data.get("isRetryable"),
        })

    parts = response.get("parts")
    parts = parts if isinstance(parts, list) else []
    reply = "\n".join(
        part.get("text", "") for part in parts
        if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
    )
    actual_model = info.get("modelID")
    if actual_model and actual_model != requested_model_id:
        raise RuntimeError(f"Requested model {requested_model_id}, received {actual_model}")
    if not reply.strip():
        raise OpenCodeAssistantError({
            "session_id": session_id,
            "name": "EmptyAssistantReply",
            "message": "OpenCode assistant returned no text reply",
            "status_code": None,
            "retryable": None,
        })
    return reply, actual_model


def invoke(args: argparse.Namespace, smoke_test: bool = False) -> dict[str, Any]:
    defaults = load_defaults()
    executable = find_opencode()
    workdir = Path(args.dir).expanduser().resolve()
    if not workdir.is_dir():
        raise NotADirectoryError(f"Work directory does not exist: {workdir}")
    model = args.model or defaults["model"]
    provider, model_id = split_model(model)
    agent = args.agent or defaults.get("agent", "build")
    host = defaults.get("host", "127.0.0.1")
    if host != "127.0.0.1":
        raise ValueError("This helper only permits host 127.0.0.1")
    timeout = int(args.timeout or defaults.get("request_timeout_seconds", 600))
    port = choose_port(host)
    base_url = f"http://{host}:{port}"
    log_dir = Path(tempfile.mkdtemp(prefix="codex-opencode-"))
    process: subprocess.Popen[Any] | None = None
    session_id = getattr(args, "session_id", None)
    created_session = False
    try:
        process, username, password = start_server(
            executable, workdir, host, port,
            defaults.get("permission", {"*": "allow"}), log_dir,
        )
        auth_header = basic_auth(username, password)
        health = wait_for_health(base_url, auth_header, process, min(timeout, 30))
        if not session_id:
            session = http_json(
                base_url, auth_header, "POST", "/session", {"title": args.title}, timeout=30,
            )
            session_id = session["id"]
            created_session = True

        prompt = getattr(args, "prompt", None)
        prompt_file = getattr(args, "prompt_file", None)
        if prompt_file:
            prompt = Path(prompt_file).read_text(encoding="utf-8")
        if smoke_test:
            prompt = "Reply with exactly OPENCODE_SESSION_OK. Do not use tools."
        if not prompt or not prompt.strip():
            raise ValueError("A non-empty --prompt or --prompt-file is required")

        response = http_json(
            base_url, auth_header, "POST", f"/session/{session_id}/message",
            {
                "model": {"providerID": provider, "modelID": model_id},
                "agent": agent,
                "parts": [{"type": "text", "text": prompt}],
            },
            timeout=timeout,
        )
        if not isinstance(response, dict):
            raise RuntimeError("OpenCode returned an unexpected response")
        reply, actual_model = parse_assistant_response(response, session_id, model_id)
        if smoke_test and reply.strip() != "OPENCODE_SESSION_OK":
            raise RuntimeError(f"Unexpected smoke-test reply: {reply!r}")
        result = {
            "ok": True, "session_id": session_id, "created_session": created_session,
            "workdir": str(workdir), "requested_model": model,
            "actual_model": actual_model, "agent": agent, "reply": reply,
            "server_version": health.get("version"),
        }
        if smoke_test:
            http_json(base_url, auth_header, "DELETE", f"/session/{session_id}", timeout=30)
            result["test_session_deleted"] = True
        return result
    except Exception as exc:
        details: dict[str, Any] = {"error": str(exc), "log_dir": str(log_dir)}
        if isinstance(exc, OpenCodeAssistantError):
            details["assistant_error"] = exc.details
        for name in ("server.stdout.log", "server.stderr.log"):
            if text := read_tail(log_dir / name):
                details[f"{name}_tail"] = text
        raise RuntimeError(json.dumps(details, ensure_ascii=False)) from exc
    finally:
        if process is not None:
            stop_owned_process(process)
        if smoke_test:
            shutil.rmtree(log_dir, ignore_errors=True)


def status() -> dict[str, Any]:
    defaults = load_defaults()
    executable = find_opencode()
    version_result = run_cli(executable, "--version")
    provider, model_id = split_model(defaults["model"])
    models_result = run_cli(executable, "models", provider, timeout=60)
    db_result = run_cli(executable, "db", "path")
    models = [line.strip() for line in models_result.stdout.splitlines() if line.strip()]
    return {
        "ok": version_result.returncode == 0 and models_result.returncode == 0,
        "executable": executable, "version": version_result.stdout.strip(),
        "default_model": defaults["model"],
        "default_model_available": defaults["model"] in models,
        "provider": provider, "model_id": model_id,
        "db_path": db_result.stdout.strip(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    status_parser = subparsers.add_parser("status", help="Read-only OpenCode diagnostics")
    status_parser.add_argument("--json", action="store_true")
    for name, help_text in (
        ("invoke", "Create or continue a real OpenCode session"),
        ("smoke-test", "Run a temporary model and API test"),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument("--dir", required=True)
        command_parser.add_argument("--title", default=f"codex-opencode-{name}")
        command_parser.add_argument("--model", help="Temporary provider/model override")
        command_parser.add_argument("--agent", choices=("build", "plan"))
        command_parser.add_argument("--timeout", type=int)
        command_parser.add_argument("--json", action="store_true")
        if name == "invoke":
            prompt_group = command_parser.add_mutually_exclusive_group(required=True)
            prompt_group.add_argument("--prompt")
            prompt_group.add_argument("--prompt-file")
            command_parser.add_argument("--session-id")
    return parser


def print_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = status() if args.command == "status" else invoke(args, args.command == "smoke-test")
        print_result(result, args.json)
        return 0 if result.get("ok") else 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
