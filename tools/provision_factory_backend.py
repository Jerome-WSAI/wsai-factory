"""Create Render service wsai-factory-backend if missing; set secrets from env.

Never prints secret values. Uses RENDER_API_KEY + WSAI_FACTORY_WEBHOOK_KEY + GROQ_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from typing import Mapping


OWNER_ID = "tea-d9h562m7r5hc73cumvbg"
SERVICE_NAME = "wsai-factory-backend"
REPO = "https://github.com/Jerome-WSAI/wsai-factory"


class ProvisionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not isinstance(value, str) or value.strip() == "":
        raise ProvisionError("missing_env", f"env {name} must be non-empty")
    return value.strip()


def http_json(
    method: str,
    url: str,
    body: dict[str, object] | None,
    headers: Mapping[str, str],
) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        status = int(exc.code)
    except urllib.error.URLError as exc:
        raise ProvisionError("unreachable", f"{url} unreachable: {exc}") from exc
    if raw.strip() == "":
        return status, None
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        preview = raw[:120].replace("\n", " ")
        return status, {"ok": False, "non_json_preview": preview}


def auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def find_backend(api_key: str) -> dict[str, object] | None:
    status, payload = http_json(
        "GET",
        "https://api.render.com/v1/services?limit=50",
        None,
        auth_headers(api_key),
    )
    if status != 200 or not isinstance(payload, list):
        raise ProvisionError("list_failed", f"list services status={status}")
    for item in payload:
        if not isinstance(item, dict):
            continue
        service = item.get("service")
        if not isinstance(service, dict):
            service = item
        if service.get("name") == SERVICE_NAME:
            return service
    return None


def create_backend(api_key: str) -> dict[str, object]:
    body: dict[str, object] = {
        "type": "web_service",
        "name": SERVICE_NAME,
        "ownerId": OWNER_ID,
        "repo": REPO,
        "branch": "main",
        "autoDeploy": "yes",
        "serviceDetails": {
            "runtime": "python",
            "plan": "pro_ultra",
            "region": "frankfurt",
            "healthCheckPath": "/health",
            "envSpecificDetails": {
                "buildCommand": "pip install -r factory_backend/requirements.txt",
                "startCommand": "python factory_backend/server.py",
            },
        },
        "envVars": [
            {"key": "PYTHON_VERSION", "value": "3.12.8"},
            {"key": "FACTORY_CORS_ORIGIN", "value": "https://wsai-factory-chatbot.vercel.app"},
            {"key": "FACTORY_INBOX_POLL_SEC", "value": "5"},
            {"key": "WSAI_FACTORY_WEBHOOK_KEY", "value": require_env("WSAI_FACTORY_WEBHOOK_KEY")},
            {"key": "GROQ_API_KEY", "value": require_env("GROQ_API_KEY")},
        ],
    }
    status, payload = http_json(
        "POST",
        "https://api.render.com/v1/services",
        body,
        auth_headers(api_key),
    )
    if status not in (200, 201):
        raise ProvisionError(
            "create_failed",
            f"POST /services status={status} body={payload}",
        )
    if not isinstance(payload, dict):
        raise ProvisionError("create_bad_shape", "create response not object")
    service = payload.get("service")
    if isinstance(service, dict):
        return service
    return payload


def service_url(service: Mapping[str, object]) -> str | None:
    details = service.get("serviceDetails")
    if isinstance(details, dict):
        url = details.get("url")
        if isinstance(url, str) and url.strip() != "":
            return url.strip()
    return None


def wait_health(url: str, attempts: int, sleep_sec: float) -> dict[str, object]:
    last: dict[str, object] = {"http_status": 0, "ok": False}
    for _ in range(attempts):
        status, payload = http_json("GET", f"{url.rstrip('/')}/health", None, {})
        ok = status == 200 and isinstance(payload, dict) and payload.get("ok") is True
        last = {
            "http_status": status,
            "ok": ok,
            "service": payload.get("service") if isinstance(payload, dict) else None,
        }
        if ok:
            return last
        time.sleep(sleep_sec)
    return last


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-attempts", required=True, type=int)
    parser.add_argument("--wait-sleep-sec", required=True, type=float)
    args = parser.parse_args()
    if args.wait_attempts < 1:
        raise ProvisionError("bad_attempts", "wait-attempts must be >= 1")
    api_key = require_env("RENDER_API_KEY")
    require_env("WSAI_FACTORY_WEBHOOK_KEY")
    require_env("GROQ_API_KEY")
    existing = find_backend(api_key)
    created = False
    if existing is None:
        service = create_backend(api_key)
        created = True
    else:
        service = existing
    url = service_url(service)
    result: dict[str, object] = {
        "ok": False,
        "created": created,
        "service_id": service.get("id"),
        "name": service.get("name"),
        "url": url,
    }
    if url is None:
        result["error"] = {
            "code": "url_missing",
            "message": "service exists but URL missing yet — retry status shortly",
        }
        print(json.dumps(result, ensure_ascii=True, indent=2))
        raise SystemExit(1)
    health = wait_health(url, args.wait_attempts, args.wait_sleep_sec)
    result["health"] = health
    result["ok"] = health.get("ok") is True
    if result["ok"] is not True:
        result["error"] = {
            "code": "health_pending_or_failed",
            "message": (
                f"service URL {url} not healthy yet after "
                f"{args.wait_attempts} attempts — check Render deploy logs / secrets"
            ),
        }
        print(json.dumps(result, ensure_ascii=True, indent=2))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    try:
        main()
    except ProvisionError as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": exc.code, "message": exc.message}},
                ensure_ascii=True,
            )
        )
        raise SystemExit(1) from exc
