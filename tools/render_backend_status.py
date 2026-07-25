"""List Render services and probe wsai-factory-backend health.

Uses RENDER_API_KEY from env. Never prints the key.
Fails loud if the backend service is missing or unhealthy.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from typing import Mapping


class StatusError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def require_api_key() -> str:
    value = os.environ.get("RENDER_API_KEY")
    if not isinstance(value, str) or value.strip() == "":
        raise StatusError(
            "missing_render_api_key",
            "env RENDER_API_KEY must be a non-empty string",
        )
    return value.strip()


def http_json(
    method: str,
    url: str,
    headers: Mapping[str, str],
) -> tuple[int, object]:
    request = urllib.request.Request(url, data=None, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        status = int(exc.code)
    except urllib.error.URLError as exc:
        raise StatusError("unreachable", f"{url} unreachable: {exc}") from exc
    if raw.strip() == "":
        return status, None
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        preview = raw[:120].replace("\n", " ")
        return status, {"ok": False, "non_json_preview": preview}


def list_services(api_key: str) -> list[dict[str, object]]:
    status, payload = http_json(
        "GET",
        "https://api.render.com/v1/services?limit=50",
        {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    if status != 200:
        raise StatusError(
            "render_list_failed",
            f"GET /v1/services expected 200, got {status} {payload}",
        )
    if not isinstance(payload, list):
        raise StatusError("bad_services_shape", "services response must be a list")
    services: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        service = item.get("service")
        if isinstance(service, dict):
            services.append(service)
        else:
            services.append(item)
    return services


def service_summary(service: Mapping[str, object]) -> dict[str, object]:
    service_details = service.get("serviceDetails")
    url = None
    if isinstance(service_details, dict):
        raw_url = service_details.get("url")
        if isinstance(raw_url, str):
            url = raw_url
    return {
        "id": service.get("id"),
        "name": service.get("name"),
        "type": service.get("type"),
        "suspended": service.get("suspended"),
        "url": url,
    }


def probe_health(base_url: str) -> dict[str, object]:
    status, payload = http_json("GET", f"{base_url.rstrip('/')}/health", {})
    ok = status == 200 and isinstance(payload, dict) and payload.get("ok") is True
    service = None
    if isinstance(payload, dict):
        service = payload.get("service")
    return {
        "http_status": status,
        "ok": ok,
        "service": service,
        "body": payload if isinstance(payload, dict) else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Render backend status (no secrets printed)")
    parser.add_argument("--require-backend", choices=("yes", "no"), required=True)
    args = parser.parse_args()
    api_key = require_api_key()
    services = [service_summary(item) for item in list_services(api_key)]
    names = [str(item.get("name")) for item in services]
    backend = next((item for item in services if item.get("name") == "wsai-factory-backend"), None)
    handoff = next((item for item in services if item.get("name") == "wsai-factory-handoff"), None)
    result: dict[str, object] = {
        "ok": True,
        "service_count": len(services),
        "names": names,
        "backend": backend,
        "handoff": handoff,
    }
    if backend is None:
        result["ok"] = False
        result["error"] = {
            "code": "backend_service_missing",
            "message": (
                "Render has no service named wsai-factory-backend. "
                "Sync the blueprint from render.yaml (dashboard Blueprint) "
                "or create the web service, set WSAI_FACTORY_WEBHOOK_KEY + GROQ_API_KEY, deploy."
            ),
        }
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if args.require_backend == "yes":
            raise SystemExit(1)
        return
    url = backend.get("url")
    if not isinstance(url, str) or url.strip() == "":
        result["ok"] = False
        result["error"] = {
            "code": "backend_url_missing",
            "message": "wsai-factory-backend exists but serviceDetails.url is empty",
        }
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if args.require_backend == "yes":
            raise SystemExit(1)
        return
    health = probe_health(url)
    result["health"] = health
    if health.get("ok") is not True:
        result["ok"] = False
        result["error"] = {
            "code": "backend_unhealthy",
            "message": f"GET {url}/health failed: {health}",
        }
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if args.require_backend == "yes":
            raise SystemExit(1)
        return
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    try:
        main()
    except StatusError as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": exc.code, "message": exc.message}},
                ensure_ascii=True,
            )
        )
        raise SystemExit(1) from exc
