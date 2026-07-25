"""Prove same-origin download token gate without printing secrets.

1) POST /order on local backend with Bearer
2) Mint HMAC token like chatbot
3) GET Next /api/download/<id>?token=... expects zip when Next is up
   OR verify token match + backend /order/<id>/zip with Bearer

Usage:
  python tools/download_token_probe.py --backend-url http://127.0.0.1:8787 --chatbot-url NONE
  python tools/download_token_probe.py --backend-url http://127.0.0.1:8787 --chatbot-url http://127.0.0.1:3000
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from typing import Mapping


class ProbeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def require_key() -> str:
    value = os.environ.get("WSAI_FACTORY_WEBHOOK_KEY")
    if not isinstance(value, str) or value.strip() == "":
        raise ProbeError(
            "missing_webhook_key",
            "env WSAI_FACTORY_WEBHOOK_KEY must be non-empty",
        )
    return value.strip()


def mint_token(order_id: str, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        f"zip:{order_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def http(
    method: str,
    url: str,
    body: bytes | None,
    headers: Mapping[str, str],
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()
    except urllib.error.URLError as exc:
        raise ProbeError("unreachable", f"{url} unreachable: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--chatbot-url", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--module", required=True)
    args = parser.parse_args()
    key = require_key()
    backend = args.backend_url.rstrip("/")
    payload = json.dumps(
        {
            "tool_name": "Pass6TokenProbe",
            "brief": "pass6 download token probe",
            "modules": [{"job_id": args.job_id, "module": args.module}],
        }
    ).encode("utf-8")
    status, raw = http(
        "POST",
        f"{backend}/order",
        payload,
        {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    if status != 200:
        raise ProbeError("order_failed", f"POST /order got {status}: {raw[:200]!r}")
    order = json.loads(raw.decode("utf-8"))
    if not isinstance(order, dict) or order.get("ok") is not True:
        raise ProbeError("order_bad", f"unexpected order body: {order}")
    order_id = order.get("order_id")
    if not isinstance(order_id, str) or order_id.strip() == "":
        raise ProbeError("order_id_missing", "order_id missing")
    token = mint_token(order_id, key)
    zip_status, zip_bytes = http(
        "GET",
        f"{backend}/order/{order_id}/zip",
        None,
        {"Authorization": f"Bearer {key}", "Accept": "application/zip"},
    )
    if zip_status != 200 or len(zip_bytes) < 22:
        raise ProbeError(
            "backend_zip_failed",
            f"backend zip status={zip_status} bytes={len(zip_bytes)}",
        )
    no_token_status = None
    chatbot_status = None
    chatbot_bytes = 0
    if args.chatbot_url != "NONE":
        chat = args.chatbot_url.rstrip("/")
        no_token_status, _ = http(
            "GET",
            f"{chat}/api/download/{order_id}",
            None,
            {},
        )
        if no_token_status != 401:
            raise ProbeError(
                "download_unguarded",
                f"GET download without token expected 401, got {no_token_status}",
            )
        chatbot_status, chat_bytes = http(
            "GET",
            f"{chat}/api/download/{order_id}?token={token}",
            None,
            {},
        )
        chatbot_bytes = len(chat_bytes)
        if chatbot_status != 200 or chatbot_bytes < 22:
            raise ProbeError(
                "chatbot_download_failed",
                f"tokenized download status={chatbot_status} bytes={chatbot_bytes}",
            )
        if chat_bytes[:2] != b"PK":
            raise ProbeError("not_zip", "chatbot download body is not a zip (missing PK)")
    print(
        json.dumps(
            {
                "ok": True,
                "order_id": order_id,
                "backend_zip_bytes": len(zip_bytes),
                "chatbot_url": args.chatbot_url,
                "download_no_token": no_token_status,
                "download_with_token": chatbot_status,
                "download_bytes": chatbot_bytes,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except ProbeError as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": exc.code, "message": exc.message}},
                ensure_ascii=True,
            )
        )
        raise SystemExit(1) from exc
