"""Safe handoff probes — no secrets printed; wrong/missing auth only.

Fails loud if health is not 200 or auth probes do not return 401.
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
    parser = argparse.ArgumentParser(description="Probe handoff auth without secrets")
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    health_status, health = http_json("GET", f"{base}/health", None, {})
    if health_status != 200 or health.get("ok") is not True:
        raise ProbeError(
            "health_failed",
            f"GET /health expected 200 ok, got {health_status} {health}",
        )
    empty_status, empty = http_json(
        "POST",
        f"{base}/handoff",
        b"{}",
        {"Content-Type": "application/json"},
    )
    if empty_status != 401:
        raise ProbeError(
            "empty_auth_expected_401",
            f"POST /handoff without Authorization expected 401, got {empty_status} {empty}",
        )
    wrong_status, wrong = http_json(
        "POST",
        f"{base}/handoff",
        b'{"to_stage":"docs","job_id":"probe","slug":"probe","from_stage":"stripped","inventory_path":"x","repo":"Jerome-WSAI/wsai-factory"}',
        {
            "Content-Type": "application/json",
            "Authorization": "Bearer intentionally-wrong",
        },
    )
    if wrong_status != 401:
        raise ProbeError(
            "wrong_auth_expected_401",
            f"POST /handoff wrong Bearer expected 401, got {wrong_status} {wrong}",
        )
    demand_status, demand = http_json(
        "POST",
        f"{base}/demand",
        b'{"x":1}',
        {"Content-Type": "application/json"},
    )
    print(
        json.dumps(
            {
                "ok": True,
                "base_url": base,
                "health": health_status,
                "handoff_no_auth": empty_status,
                "handoff_wrong_auth": wrong_status,
                "demand_status": demand_status,
                "demand_code": demand.get("code"),
                "note": "demand_status 410=local demand_moved; 404=prod older handler",
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except ProbeError as exc:
        print(json.dumps({"ok": False, "error": {"code": exc.code, "message": exc.message}}))
        raise SystemExit(1) from exc
