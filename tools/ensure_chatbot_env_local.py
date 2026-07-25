"""Ensure chatbot/.env.local has backend wiring for local E2E. Never prints secrets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    text = path.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        clean_key = key.strip().lstrip("\ufeff")
        if clean_key == "":
            continue
        out[clean_key] = value.strip().strip('"').strip("'")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--chatbot-secret", required=True)
    args = parser.parse_args()
    root_env = load_dotenv(ROOT / ".env")
    webhook = root_env.get("WSAI_FACTORY_WEBHOOK_KEY", "")
    if webhook.strip() == "":
        raise SystemExit("WSAI_FACTORY_WEBHOOK_KEY missing in .env")
    target = ROOT / "chatbot" / ".env.local"
    existing = load_dotenv(target)
    existing["FACTORY_BACKEND_URL"] = args.backend_url.strip()
    existing["WSAI_FACTORY_WEBHOOK_KEY"] = webhook
    existing["CHATBOT_API_SECRET"] = args.chatbot_secret.strip()
    target.write_text(
        "".join(f"{key}={value}\n" for key, value in sorted(existing.items())),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "path": str(target.relative_to(ROOT)).replace("\\", "/"),
                "keys": sorted(existing.keys()),
                "backend_url": args.backend_url.strip(),
                "has_webhook": True,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
