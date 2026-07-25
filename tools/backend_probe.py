"""Safe factory_backend probes — health + auth without printing secrets.

Fails loud if health is not 200 or protected routes do not return 401.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from typing import Mapping


class ProbeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def http_json(
    method: str,
    url: str,
    body: bytes | None,
    headers: Mapping[str, str],
) -> tuple[int, Mapping[str, object]]:
    request = urllib.request.Request(
        url,
        data=body,
        headers=dict(headers),
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        status = int(exc.code)
    except urllib.error.URLError as exc:
        raise ProbeError("unreachable", f"{url} unreachable: {exc}") from exc
    if raw.strip() == "":
        return status, {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        preview = raw[:120].replace("\n", " ")
        raise ProbeError(
            "non_json_body",
            f"{url} status={status} body is not JSON: {preview!r}",
        ) from exc
    if not isinstance(payload, dict):
        raise ProbeError("bad_shape", f"{url} body root must be object")
    return status, payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe factory_backend without secrets")
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    health_status, health = http_json("GET", f"{base}/health", None, {})
    if health_status != 200 or health.get("ok") is not True:
        raise ProbeError(
            "health_failed",
            f"GET /health expected 200 ok, got {health_status} {health}",
        )
    if health.get("service") != "wsai-factory-backend":
        raise ProbeError(
            "wrong_service",
            f"GET /health service expected wsai-factory-backend, got {health.get('service')!r}",
        )
    catalog_status, catalog = http_json("GET", f"{base}/catalog", None, {})
    if catalog_status != 401:
        raise ProbeError(
            "catalog_expected_401",
            f"GET /catalog without Authorization expected 401, got {catalog_status} {catalog}",
        )
    chat_status, chat = http_json(
        "POST",
        f"{base}/chat",
        b'{"message":"probe","history":[]}',
        {"Content-Type": "application/json"},
    )
    if chat_status != 401:
        raise ProbeError(
            "chat_expected_401",
            f"POST /chat without Authorization expected 401, got {chat_status} {chat}",
        )
    wrong_status, wrong = http_json(
        "POST",
        f"{base}/inbox/scan",
        b"{}",
        {
            "Content-Type": "application/json",
            "Authorization": "Bearer intentionally-wrong",
        },
    )
    if wrong_status != 401:
        raise ProbeError(
            "wrong_auth_expected_401",
            f"POST /inbox/scan wrong Bearer expected 401, got {wrong_status} {wrong}",
        )
    print(
        json.dumps(
            {
                "ok": True,
                "base_url": base,
                "health": health_status,
                "service": health.get("service"),
                "catalog_size": health.get("catalog_size"),
                "catalog_no_auth": catalog_status,
                "chat_no_auth": chat_status,
                "inbox_wrong_auth": wrong_status,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except ProbeError as exc:
        print(json.dumps({"ok": False, "error": {"code": exc.code, "message": exc.message}}))
        raise SystemExit(1) from exc
