"""Chatbot smoke: path-leak regression + auth gate expectations.

Fails loud. No network secrets printed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]


class SmokeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def run_local_query(query: str) -> Mapping[str, object]:
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "stock_chatbot_query.py"),
            "--query",
            query,
            "--stock-root",
            str(ROOT / "pipeline" / "stock"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise SmokeError(
            "local_query_failed",
            f"exit={proc.returncode} stderr={(proc.stderr or '').strip()}",
        )
    if proc.stdout is None:
        raise SmokeError("local_query_empty", "stdout missing after local query")
    payload = json.loads(proc.stdout)
    if not isinstance(payload, dict):
        raise SmokeError("local_query_shape", "stdout root must be object")
    return payload


def assert_no_absolute_path(payload: Mapping[str, object], label: str) -> None:
    raw = json.dumps(payload)
    if "absolute_path" in raw:
        raise SmokeError("absolute_path_leak", f"{label} JSON contains absolute_path")
    result = payload.get("result")
    if isinstance(result, dict):
        stock_root = result.get("stock_root")
        if isinstance(stock_root, str) and (
            stock_root.startswith("/") or ":\\" in stock_root or ":/" in stock_root
        ):
            raise SmokeError(
                "stock_root_filesystem",
                f"{label} stock_root looks like a filesystem path: {stock_root!r}",
            )


def http_json(
    method: str,
    url: str,
    body: bytes | None,
    headers: Mapping[str, str],
) -> tuple[int, Mapping[str, object]]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        status = int(exc.code)
    payload = json.loads(raw) if raw.strip() else {}
    if not isinstance(payload, dict):
        raise SmokeError("http_shape", f"{url} body root must be object")
    return status, payload


def probe_base(base_url: str, secret: str) -> None:
    modules_url = f"{base_url.rstrip('/')}/api/modules"
    query_url = f"{base_url.rstrip('/')}/api/query"
    status, payload = http_json("GET", modules_url, None, {})
    if status != 401:
        raise SmokeError(
            "unauth_modules",
            f"GET /api/modules without secret expected 401 got {status} body={payload}",
        )
    status, payload = http_json(
        "POST",
        query_url,
        b'{"query":"duration"}',
        {"Content-Type": "application/json"},
    )
    if status != 401:
        raise SmokeError(
            "unauth_query",
            f"POST /api/query without secret expected 401 got {status} body={payload}",
        )
    if secret.strip() == "":
        return
    auth = {"Content-Type": "application/json", "x-chatbot-secret": secret}
    status, payload = http_json("GET", modules_url, None, {"x-chatbot-secret": secret})
    if status != 200:
        raise SmokeError("auth_modules", f"GET /api/modules with secret got {status}")
    assert_no_absolute_path(payload, "modules")
    status, payload = http_json("POST", query_url, b'{"query":"duration"}', auth)
    if status != 200:
        raise SmokeError("auth_query", f"POST duration with secret got {status} {payload}")
    assert_no_absolute_path(payload, "query-duration")
    status, payload = http_json("POST", query_url, b'{"query":"timer"}', auth)
    if status != 200:
        raise SmokeError("auth_timer", f"POST timer with secret got {status} {payload}")
    assert_no_absolute_path(payload, "query-timer")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chatbot smoke probes")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--secret", required=True)
    parser.add_argument("--skip-local", choices=("yes", "no"), required=True)
    args = parser.parse_args()
    if args.skip_local == "no":
        local = run_local_query("duration")
        assert_no_absolute_path(local, "local-cli")
    probe_base(args.base_url, args.secret)
    print(
        json.dumps(
            {
                "ok": True,
                "base_url": args.base_url,
                "local_checked": args.skip_local == "no",
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except SmokeError as exc:
        print(json.dumps({"ok": False, "error": {"code": exc.code, "message": exc.message}}))
        raise SystemExit(1) from exc
