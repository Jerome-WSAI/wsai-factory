"""Always-on Factory handoff: webhook metadata → Cursor Cloud Agent run.

Signal only (no project zip). Fail loud. Stdlib only.
Binds 0.0.0.0:$PORT for Render.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping


CURSOR_API_BASE = "https://api.cursor.com/v1"

STAGE_TO_ENV: Mapping[str, str] = {
    "docs": "FACTORY_AGENT_DOCS",
    "aligned": "FACTORY_AGENT_ALIGN",
    "modularized": "FACTORY_AGENT_MODULARIZE",
    "stripped": "FACTORY_AGENT_INBOX",
}


class HandoffError(Exception):
    def __init__(self, code: str, message: str, http_status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not isinstance(value, str) or value.strip() == "":
        raise HandoffError(
            "missing_env",
            f"required env {name} is missing or empty",
            500,
        )
    return value.strip()


def require_port() -> int:
    raw = os.environ.get("PORT")
    if not isinstance(raw, str) or raw.strip() == "":
        raise HandoffError("missing_port", "env PORT is required", 500)
    try:
        port = int(raw)
    except ValueError as exc:
        raise HandoffError("bad_port", f"PORT must be int, got {raw!r}", 500) from exc
    if port < 1 or port > 65535:
        raise HandoffError("bad_port", f"PORT out of range: {port}", 500)
    return port


def parse_json_object(raw: bytes) -> dict[str, object]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HandoffError("bad_body_encoding", "body must be UTF-8 JSON", 400) from exc
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HandoffError("bad_json", f"invalid JSON: {exc}", 400) from exc
    if not isinstance(parsed, dict):
        raise HandoffError("bad_json_root", "JSON root must be object", 400)
    return parsed


def require_string_field(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or value.strip() == "":
        raise HandoffError(
            "missing_field",
            f"payload.{key} must be a non-empty string",
            400,
        )
    return value.strip()


def agent_id_for_stage(to_stage: str) -> str:
    env_name = STAGE_TO_ENV.get(to_stage)
    if env_name is None:
        raise HandoffError(
            "unsupported_to_stage",
            f"to_stage {to_stage!r} has no Factory agent mapping "
            f"(supported: {sorted(STAGE_TO_ENV)})",
            400,
        )
    return require_env(env_name)


def cursor_auth_header(api_key: str) -> str:
    token = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def create_agent_run(
    api_key: str,
    agent_id: str,
    prompt_text: str,
) -> dict[str, object]:
    url = f"{CURSOR_API_BASE}/agents/{agent_id}/runs"
    body = json.dumps({"prompt": {"text": prompt_text}}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": cursor_auth_header(api_key),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "wsai-factory-handoff/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = response.getcode()
            raw = response.read().decode("utf-8")
            if status < 200 or status >= 300:
                raise HandoffError(
                    "cursor_bad_status",
                    f"Cursor run create HTTP {status}: {raw[:500]}",
                    502,
                )
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise HandoffError(
            "cursor_http_error",
            f"Cursor run create HTTP {exc.code}: {err_body[:800]}",
            502,
        ) from exc
    except urllib.error.URLError as exc:
        raise HandoffError(
            "cursor_network",
            f"Cursor API network failure: {exc}",
            502,
        ) from exc
    if raw.strip() == "":
        raise HandoffError("cursor_empty", "Cursor run create returned empty body", 502)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise HandoffError("cursor_bad_shape", "Cursor run response must be object", 502)
    return parsed


def build_prompt(payload: Mapping[str, object]) -> str:
    job_id = require_string_field(payload, "job_id")
    slug = require_string_field(payload, "slug")
    from_stage = require_string_field(payload, "from_stage")
    to_stage = require_string_field(payload, "to_stage")
    inventory_path = require_string_field(payload, "inventory_path")
    repo = require_string_field(payload, "repo")
    return (
        "WSAI-Factory stage handoff (metadata only; code is already in git).\n"
        f"repo={repo}\n"
        f"job_id={job_id}\n"
        f"slug={slug}\n"
        f"from_stage={from_stage}\n"
        f"to_stage={to_stage}\n"
        f"inventory_path={inventory_path}\n"
        "Execute the matching automations/*.md contract for this to_stage. "
        "Fail loud. Do not invent code or docs."
    )


def handle_handoff(payload: Mapping[str, object], webhook_key: str, auth_header: str) -> dict[str, object]:
    expected = f"Bearer {webhook_key}"
    if auth_header != expected:
        raise HandoffError("unauthorized", "Authorization Bearer token mismatch", 401)
    to_stage = require_string_field(payload, "to_stage")
    if to_stage == "stock":
        return {
            "ok": True,
            "action": "noop",
            "reason": "stock stage has no Cursor agent; local/stock scripts own this step",
            "to_stage": to_stage,
        }
    agent_id = agent_id_for_stage(to_stage)
    cursor_key = require_env("CURSOR_API_KEY")
    prompt = build_prompt(payload)
    run = create_agent_run(cursor_key, agent_id, prompt)
    run_id = run.get("id")
    if not isinstance(run_id, str) or run_id == "":
        # some responses nest under "run"
        nested = run.get("run")
        if isinstance(nested, dict):
            run_id = nested.get("id")
        if not isinstance(run_id, str) or run_id == "":
            raise HandoffError(
                "cursor_missing_run_id",
                f"run id missing in response keys={list(run.keys())}",
                502,
            )
    return {
        "ok": True,
        "action": "agent_run",
        "agent_id": agent_id,
        "run_id": run_id,
        "to_stage": to_stage,
        "url": f"https://cursor.com/agents/{agent_id}",
    }


class HandoffHandler(BaseHTTPRequestHandler):
    server_version = "WSAIFactoryHandoff/1.0"

    def log_message(self, format: str, *args: object) -> None:
        print(f"handoff {self.address_string()} {format % args}")

    def _send_json(self, status: int, body: dict[str, object]) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path in ("/health", "/healthz"):
            self._send_json(200, {"ok": True, "service": "wsai-factory-handoff"})
            return
        self._send_json(404, {"ok": False, "code": "not_found", "message": "GET only /health"})

    def do_POST(self) -> None:
        if self.path != "/handoff":
            self._send_json(404, {"ok": False, "code": "not_found", "message": "POST only /handoff"})
            return
        try:
            length_raw = self.headers.get("Content-Length")
            if length_raw is None:
                raise HandoffError("missing_length", "Content-Length required", 400)
            try:
                length = int(length_raw)
            except ValueError as exc:
                raise HandoffError("bad_length", "Content-Length must be int", 400) from exc
            if length < 0 or length > 1_000_000:
                raise HandoffError("bad_length", "Content-Length out of allowed range", 400)
            raw = self.rfile.read(length)
            payload = parse_json_object(raw)
            auth = self.headers.get("Authorization")
            if not isinstance(auth, str):
                raise HandoffError("unauthorized", "Authorization header required", 401)
            webhook_key = require_env("WSAI_FACTORY_WEBHOOK_KEY")
            result = handle_handoff(payload, webhook_key, auth)
            self._send_json(200, result)
        except HandoffError as exc:
            self._send_json(
                exc.http_status,
                {"ok": False, "code": exc.code, "message": exc.message},
            )


def main() -> None:
    port = require_port()
    # Fail fast on missing secrets at boot (not only on first request).
    require_env("WSAI_FACTORY_WEBHOOK_KEY")
    require_env("CURSOR_API_KEY")
    for env_name in STAGE_TO_ENV.values():
        require_env(env_name)
    server = ThreadingHTTPServer(("0.0.0.0", port), HandoffHandler)
    print(f"wsai-factory-handoff listening on 0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
