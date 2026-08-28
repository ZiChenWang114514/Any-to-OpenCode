#!/usr/bin/env python3
"""Discover model pools and run isolated local OpenCode sessions safely."""

from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
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
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


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
) -> tuple[str, str | None, str | None]:
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
    actual_variant = info.get("variant")
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
    return reply, actual_model, actual_variant


def parse_verbose_models(output: str, provider: str) -> list[dict[str, Any]]:
    """Parse `opencode models --verbose` records for one provider."""
    clean = ANSI_ESCAPE.sub("", output)
    decoder = json.JSONDecoder()
    pattern = re.compile(rf"(?m)^{re.escape(provider)}/[^\r\n]+\r?\n")
    records: list[dict[str, Any]] = []
    for match in pattern.finditer(clean):
        payload = clean[match.end():].lstrip()
        try:
            record, _ = decoder.raw_decode(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("providerID") == provider:
            records.append(record)
    return records


def is_zero_cost_model(record: dict[str, Any]) -> bool:
    """Return true for active models whose advertised token costs are all zero."""
    if record.get("status") != "active":
        return False
    cost = record.get("cost")
    if not isinstance(cost, dict):
        return False
    cache = cost.get("cache")
    cache = cache if isinstance(cache, dict) else {}
    values = (cost.get("input"), cost.get("output"), cache.get("read"), cache.get("write"))
    return all(isinstance(value, (int, float)) and value == 0 for value in values)


def discover_free_models(executable: str, provider: str, refresh: bool) -> list[str]:
    arguments = ["models", provider, "--verbose"]
    if refresh:
        arguments.append("--refresh")
    result = run_cli(executable, *arguments, timeout=90)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "OpenCode model discovery failed")
    records = parse_verbose_models(result.stdout, provider)
    models = [f"{provider}/{record['id']}" for record in records if is_zero_cost_model(record)]
    return sorted(set(models))


def invoke(args: argparse.Namespace, smoke_test: bool = False) -> dict[str, Any]:
    defaults = load_defaults()
    executable = find_opencode()
    workdir = Path(args.dir).expanduser().resolve()
    if not workdir.is_dir():
        raise NotADirectoryError(f"Work directory does not exist: {workdir}")
    model = args.model or defaults["model"]
    provider, model_id = split_model(model)
    agent = args.agent or defaults.get("agent", "build")
    variant = getattr(args, "variant", None) or defaults.get("variant")
    host = defaults.get("host", "127.0.0.1")
    if host != "127.0.0.1":
        raise ValueError("This helper only permits host 127.0.0.1")
    timeout = int(args.timeout or defaults.get("request_timeout_seconds", 600))
    port = choose_port(host)
    base_url = f"http://{host}:{port}"
    log_dir = Path(tempfile.mkdtemp(prefix="codex-opencode-"))
    process: subprocess.Popen[Any] | None = None
    auth_header: str | None = None
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

        message_payload = {
            "model": {"providerID": provider, "modelID": model_id},
            "agent": agent,
            "parts": [{"type": "text", "text": prompt}],
        }
        if variant:
            message_payload["variant"] = variant
        response = http_json(
            base_url, auth_header, "POST", f"/session/{session_id}/message",
            message_payload,
            timeout=timeout,
        )
        if not isinstance(response, dict):
            raise RuntimeError("OpenCode returned an unexpected response")
        reply, actual_model, actual_variant = parse_assistant_response(
            response, session_id, model_id
        )
        if smoke_test and reply.strip() != "OPENCODE_SESSION_OK":
            raise RuntimeError(f"Unexpected smoke-test reply: {reply!r}")
        result = {
            "ok": True, "session_id": session_id, "created_session": created_session,
            "workdir": str(workdir), "requested_model": model,
            "actual_model": actual_model, "requested_variant": variant,
            "actual_variant": actual_variant, "agent": agent, "reply": reply,
            "server_version": health.get("version"),
        }
        if smoke_test:
            http_json(base_url, auth_header, "DELETE", f"/session/{session_id}", timeout=30)
            result["test_session_deleted"] = True
        return result
    except Exception as exc:
        details: dict[str, Any] = {"error": str(exc), "log_dir": str(log_dir)}
        if smoke_test and created_session and session_id and auth_header:
            try:
                http_json(base_url, auth_header, "DELETE", f"/session/{session_id}", timeout=30)
                details["test_session_deleted"] = True
            except Exception as cleanup_exc:
                details["test_session_delete_error"] = type(cleanup_exc).__name__
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


def summarize_failure(exc: Exception) -> dict[str, Any]:
    try:
        details = json.loads(str(exc))
    except (json.JSONDecodeError, TypeError):
        return {"error": str(exc)}
    if not isinstance(details, dict):
        return {"error": str(exc)}
    summary: dict[str, Any] = {"error": details.get("error", type(exc).__name__)}
    if "assistant_error" in details:
        summary["assistant_error"] = details["assistant_error"]
    if "test_session_deleted" in details:
        summary["test_session_deleted"] = details["test_session_deleted"]
    if "test_session_delete_error" in details:
        summary["test_session_delete_error"] = details["test_session_delete_error"]
    return summary


def free_pool(args: argparse.Namespace) -> dict[str, Any]:
    executable = find_opencode()
    models = discover_free_models(executable, args.provider, args.refresh)
    if not models:
        raise RuntimeError(f"No active zero-cost models found for provider {args.provider}")
    attempts_per_model = int(args.retries) + 1
    run_id = secrets.token_hex(4)

    def smoke_model(model: str) -> dict[str, Any]:
        failures: list[dict[str, Any]] = []
        for attempt in range(1, attempts_per_model + 1):
            model_id = model.split("/", 1)[1]
            title = f"codex-free-pool-{run_id}-{model_id}-a{attempt}"
            invoke_args = argparse.Namespace(
                dir=args.dir, title=title, model=model, variant=None,
                agent="plan", timeout=args.timeout, json=True,
                prompt=None, prompt_file=None, session_id=None,
            )
            try:
                result = invoke(invoke_args, smoke_test=True)
                return {
                    "model": model, "ok": True, "attempts": attempt,
                    "actual_model": result.get("actual_model"),
                    "reply": result.get("reply"),
                    "server_version": result.get("server_version"),
                    "test_session_deleted": result.get("test_session_deleted"),
                }
            except Exception as exc:
                failures.append({"attempt": attempt, **summarize_failure(exc)})
        return {"model": model, "ok": False, "attempts": attempts_per_model, "failures": failures}

    results: list[dict[str, Any]] = []
    workers = min(max(1, int(args.parallel)), len(models))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(smoke_model, model): model for model in models}
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: item["model"])
    passed = sum(1 for item in results if item["ok"])
    return {
        "ok": passed == len(results),
        "provider": args.provider,
        "discovered": len(models),
        "passed": passed,
        "failed": len(results) - passed,
        "parallel": workers,
        "results": results,
    }


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
    pool_parser = subparsers.add_parser(
        "free-pool", help="Discover and concurrently smoke-test active zero-cost models"
    )
    pool_parser.add_argument("--dir", "--workdir", dest="dir", required=True)
    pool_parser.add_argument("--provider", default="opencode")
    pool_parser.add_argument("--parallel", type=int, choices=range(1, 9), default=3)
    pool_parser.add_argument("--timeout", type=int, default=300)
    pool_parser.add_argument("--retries", type=int, choices=range(0, 4), default=0)
    pool_parser.add_argument("--no-refresh", dest="refresh", action="store_false")
    pool_parser.add_argument("--json", action="store_true")
    for name, help_text in (
        ("invoke", "Create or continue a real OpenCode session"),
        ("smoke-test", "Run a temporary model and API test"),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument("--dir", "--workdir", dest="dir", required=True)
        command_parser.add_argument("--title", default=f"codex-opencode-{name}")
        command_parser.add_argument("--model", help="Temporary provider/model override")
        command_parser.add_argument(
            "--variant", help="Provider-specific model variant, for example xhigh"
        )
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


def any_to_payload(result: dict[str, Any], command: str) -> dict[str, Any]:
    """Add the shared Any-to fields without removing adapter-specific detail."""
    payload = dict(result)
    payload.setdefault("schema_version", 1)
    payload.setdefault("target", "opencode")
    payload.setdefault("command", command)
    payload.setdefault("provider", payload.get("provider") or "opencode")
    payload.setdefault("workdir", payload.get("directory"))
    payload.setdefault("session_id", payload.get("session_id"))
    payload.setdefault("requested_model", payload.get("requested_model") or payload.get("default_model"))
    payload.setdefault("actual_model", payload.get("actual_model"))
    payload.setdefault("result", payload.get("response"))
    payload.setdefault("warnings", [])
    payload.setdefault("error", None)
    return payload


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "status":
            result = status()
        elif args.command == "free-pool":
            result = free_pool(args)
        else:
            result = invoke(args, args.command == "smoke-test")
        if args.json:
            result = any_to_payload(result, args.command)
        print_result(result, args.json)
        return 0 if result.get("ok") else 1
    except Exception as exc:
        if getattr(args, "json", False):
            print_result(any_to_payload({"ok": False, "error": str(exc)}, args.command), True)
        else:
            print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
