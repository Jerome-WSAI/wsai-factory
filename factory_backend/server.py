"""WSAI Factory backend — dynamic pipeline on Render (replaces Cursor Automations).

Bind 0.0.0.0:$PORT. Stdlib HTTP. Fail loud.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from assemble import ModuleRef, assemble_order
from brain import list_stock_catalog, run_brain
from errors import FactoryError, require_env
from ingest import ingest_zip_bytes

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ORIGIN = os.environ.get(
    "FACTORY_CORS_ORIGIN",
    "https://wsai-factory-chatbot.vercel.app",
)
DELIVERIES = REPO_ROOT / "pipeline" / "deliveries"
ORDERS_STATE = REPO_ROOT / "pipeline" / "orders_state"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def require_port() -> int:
    raw = os.environ.get("PORT")
    if not isinstance(raw, str) or raw.strip() == "":
        raise FactoryError("missing_port", "env PORT is required", 500)
    try:
        port = int(raw)
    except ValueError as exc:
        raise FactoryError("bad_port", f"PORT must be int, got {raw!r}", 500) from exc
    if port < 1 or port > 65535:
        raise FactoryError("bad_port", f"PORT out of range: {port}", 500)
    return port


def check_bearer(auth_header: str | None) -> None:
    expected = f"Bearer {require_env('WSAI_FACTORY_WEBHOOK_KEY')}"
    if auth_header != expected:
        raise FactoryError("unauthorized", "Authorization Bearer token mismatch", 401)


def new_order_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def save_order_state(order_id: str, payload: Mapping[str, object]) -> None:
    ORDERS_STATE.mkdir(parents=True, exist_ok=True)
    path = ORDERS_STATE / f"{order_id}.json"
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_order_state(order_id: str) -> dict[str, object]:
    path = ORDERS_STATE / f"{order_id}.json"
    if not path.is_file():
        raise FactoryError("order_not_found", f"unknown order_id={order_id}", 404)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise FactoryError("bad_order_state", "order state must be object", 500)
    return data


def parse_modules(raw: object) -> list[ModuleRef]:
    if not isinstance(raw, list) or len(raw) == 0:
        raise FactoryError("bad_modules", "modules must be non-empty array", 400)
    out: list[ModuleRef] = []
    for item in raw:
        if not isinstance(item, dict):
            raise FactoryError("bad_module_item", "module must be object", 400)
        job_id = item.get("job_id")
        module = item.get("module")
        if not isinstance(job_id, str) or job_id.strip() == "":
            raise FactoryError("bad_job_id", "module.job_id required", 400)
        if not isinstance(module, str) or module.strip() == "":
            raise FactoryError("bad_module", "module.module required", 400)
        out.append({"job_id": job_id.strip(), "module": module.strip()})
    return out


def handle_chat(payload: Mapping[str, object]) -> dict[str, object]:
    message = payload.get("message")
    if not isinstance(message, str) or message.strip() == "":
        raise FactoryError("missing_message", "message required", 400)
    history_raw = payload.get("history")
    history: list[dict[str, str]] = []
    if isinstance(history_raw, list):
        for item in history_raw:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if isinstance(role, str) and isinstance(content, str):
                history.append({"role": role, "content": content})
    catalog = list_stock_catalog()
    decision = run_brain(message.strip(), history, catalog)
    status = decision.get("status")
    reply = decision.get("reply")
    if not isinstance(reply, str):
        reply = ""
    result: dict[str, object] = {
        "ok": True,
        "decision": decision,
        "catalog_size": len(catalog),
        "order": {"queued": False},
    }
    if status != "ready":
        return result
    tool_name = decision.get("tool_name")
    brief = decision.get("brief")
    if not isinstance(tool_name, str) or tool_name.strip() == "":
        raise FactoryError("brain_ready_no_tool", "ready without tool_name", 502)
    if not isinstance(brief, str) or brief.strip() == "":
        raise FactoryError("brain_ready_no_brief", "ready without brief", 502)
    modules = parse_modules(decision.get("modules"))
    order_id = new_order_id()
    assembled = assemble_order(order_id, tool_name.strip(), brief.strip(), modules)
    state = {
        "order_id": order_id,
        "status": "assembled",
        "created_at": utc_now(),
        "tool_name": tool_name.strip(),
        "brief": brief.strip(),
        "modules": modules,
        "zip_name": assembled["zip_name"],
        "download_path": f"/order/{order_id}/zip",
    }
    save_order_state(order_id, state)
    result["order"] = {
        "queued": True,
        "order_id": order_id,
        "download_path": state["download_path"],
        "zip_name": assembled["zip_name"],
        "module_count": assembled["module_count"],
    }
    result["reply"] = reply
    return result


def handle_order_direct(payload: Mapping[str, object]) -> dict[str, object]:
    tool_name = payload.get("tool_name")
    brief = payload.get("brief")
    if not isinstance(tool_name, str) or tool_name.strip() == "":
        raise FactoryError("missing_tool_name", "tool_name required", 400)
    if not isinstance(brief, str) or brief.strip() == "":
        raise FactoryError("missing_brief", "brief required", 400)
    modules = parse_modules(payload.get("modules"))
    order_id = new_order_id()
    assembled = assemble_order(order_id, tool_name.strip(), brief.strip(), modules)
    state = {
        "order_id": order_id,
        "status": "assembled",
        "created_at": utc_now(),
        "tool_name": tool_name.strip(),
        "brief": brief.strip(),
        "modules": modules,
        "zip_name": assembled["zip_name"],
        "download_path": f"/order/{order_id}/zip",
    }
    save_order_state(order_id, state)
    return {"ok": True, **state, "module_count": assembled["module_count"]}


def handle_ingest(payload: Mapping[str, object]) -> dict[str, object]:
    slug = payload.get("slug")
    zip_b64 = payload.get("zip_base64")
    if not isinstance(slug, str) or slug.strip() == "":
        raise FactoryError("missing_slug", "slug required", 400)
    if not isinstance(zip_b64, str) or zip_b64.strip() == "":
        raise FactoryError("missing_zip", "zip_base64 required", 400)
    import base64

    try:
        zip_bytes = base64.b64decode(zip_b64, validate=True)
    except Exception as exc:
        raise FactoryError("bad_base64", f"zip_base64 invalid: {exc}", 400) from exc
    polls = payload.get("polls")
    interval = payload.get("interval_sec")
    polls_i = int(polls) if isinstance(polls, (int, float)) else 2
    interval_f = float(interval) if isinstance(interval, (int, float)) else 0.5
    return ingest_zip_bytes(slug.strip(), zip_bytes, polls_i, interval_f)


def scan_local_inbox() -> dict[str, object]:
    """Process every stable folder under pipeline/inbox/ via full pipeline."""
    import sys

    tools = str(REPO_ROOT / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from pipeline_automate import run_slug
    from pipeline_lib import INBOX_ROOT

    INBOX_ROOT.mkdir(parents=True, exist_ok=True)
    done: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for entry in sorted(INBOX_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("_") or entry.name.startswith("."):
            continue
        try:
            out = run_slug(entry.name, 2, 0.5)
            done.append(dict(out))
        except Exception as exc:
            errors.append({"slug": entry.name, "error": str(exc)})
    return {"ok": True, "processed": done, "errors": errors}


class FactoryHandler(BaseHTTPRequestHandler):
    server_version = "WSAIFactoryBackend/1.0"

    def log_message(self, format: str, *args: object) -> None:
        print(f"factory {self.address_string()} {format % args}", flush=True)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization",
        )

    def _send_json(self, status: int, body: dict[str, object]) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self._cors()
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict[str, object]:
        length_raw = self.headers.get("Content-Length")
        if length_raw is None:
            raise FactoryError("missing_length", "Content-Length required", 400)
        try:
            length = int(length_raw)
        except ValueError as exc:
            raise FactoryError("bad_length", "Content-Length must be int", 400) from exc
        if length < 0 or length > 80_000_000:
            raise FactoryError("bad_length", "Content-Length out of range", 400)
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FactoryError("bad_json", f"invalid JSON: {exc}", 400) from exc
        if not isinstance(parsed, dict):
            raise FactoryError("bad_json_root", "JSON root must be object", 400)
        return parsed

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if path in ("/health", "/healthz"):
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "service": "wsai-factory-backend",
                        "catalog_size": len(list_stock_catalog()),
                    },
                )
                return
            if path == "/catalog":
                check_bearer(self.headers.get("Authorization"))
                catalog = list_stock_catalog()
                self._send_json(200, {"ok": True, "modules": catalog})
                return
            if path.startswith("/order/") and path.endswith("/status"):
                check_bearer(self.headers.get("Authorization"))
                order_id = path[len("/order/") : -len("/status")]
                self._send_json(200, {"ok": True, **load_order_state(order_id)})
                return
            if path.startswith("/order/") and path.endswith("/zip"):
                check_bearer(self.headers.get("Authorization"))
                order_id = path[len("/order/") : -len("/zip")]
                state = load_order_state(order_id)
                zip_name = state.get("zip_name")
                if not isinstance(zip_name, str):
                    raise FactoryError("missing_zip_name", "order has no zip", 500)
                zip_path = DELIVERIES / zip_name
                if not zip_path.is_file():
                    raise FactoryError(
                        "zip_missing",
                        f"zip file missing: {zip_path}",
                        404,
                    )
                data = zip_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{zip_name}"',
                )
                self.send_header("Content-Length", str(len(data)))
                self._cors()
                self.end_headers()
                self.wfile.write(data)
                return
            self._send_json(
                404,
                {"ok": False, "code": "not_found", "message": f"GET {path}"},
            )
        except FactoryError as exc:
            self._send_json(
                exc.http_status,
                {"ok": False, "code": exc.code, "message": exc.message},
            )

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            check_bearer(self.headers.get("Authorization"))
            if path == "/chat":
                self._send_json(200, handle_chat(self._read_json()))
                return
            if path == "/order":
                self._send_json(200, handle_order_direct(self._read_json()))
                return
            if path == "/ingest":
                self._send_json(200, handle_ingest(self._read_json()))
                return
            if path == "/inbox/scan":
                self._send_json(200, scan_local_inbox())
                return
            self._send_json(
                404,
                {"ok": False, "code": "not_found", "message": f"POST {path}"},
            )
        except FactoryError as exc:
            self._send_json(
                exc.http_status,
                {"ok": False, "code": exc.code, "message": exc.message},
            )


def inbox_poll_loop(interval_sec: float) -> None:
    while True:
        try:
            result = scan_local_inbox()
            processed = result.get("processed")
            if isinstance(processed, list) and len(processed) > 0:
                print(
                    json.dumps(
                        {"event": "inbox_scan", "processed": len(processed)},
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
        except Exception as exc:
            print(
                json.dumps(
                    {"event": "inbox_scan_error", "error": str(exc)},
                    ensure_ascii=False,
                ),
                flush=True,
            )
        time.sleep(interval_sec)


def main() -> None:
    # Fail boot if secrets missing for chat path
    require_env("WSAI_FACTORY_WEBHOOK_KEY")
    require_env("GROQ_API_KEY")
    port = require_port()
    poll_raw = os.environ.get("FACTORY_INBOX_POLL_SEC", "0").strip()
    try:
        poll_sec = float(poll_raw)
    except ValueError as exc:
        raise FactoryError(
            "bad_poll",
            f"FACTORY_INBOX_POLL_SEC must be float, got {poll_raw!r}",
            500,
        ) from exc
    if poll_sec > 0:
        thread = threading.Thread(
            target=inbox_poll_loop,
            args=(poll_sec,),
            daemon=True,
            name="inbox-poll",
        )
        thread.start()
        print(
            json.dumps({"event": "inbox_poll_started", "interval_sec": poll_sec}),
            flush=True,
        )
    server = ThreadingHTTPServer(("0.0.0.0", port), FactoryHandler)
    print(
        json.dumps(
            {
                "event": "listen",
                "host": "0.0.0.0",
                "port": port,
                "service": "wsai-factory-backend",
            }
        ),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
