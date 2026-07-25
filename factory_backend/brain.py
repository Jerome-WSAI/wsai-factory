"""Groq brain for factory orders — negotiation only, modules from live stock."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import TypedDict

from errors import FactoryError, require_env

GROQ_API_BASE = "https://api.groq.com/openai/v1"


class ModuleRef(TypedDict):
    job_id: str
    module: str


def list_stock_catalog() -> list[ModuleRef]:
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    tools = repo / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from pipeline_lib import STOCK_ROOT

    catalog: list[ModuleRef] = []
    if not STOCK_ROOT.is_dir():
        return catalog
    for job_dir in sorted(STOCK_ROOT.iterdir()):
        if not job_dir.is_dir() or job_dir.name.startswith("."):
            continue
        for child in sorted(job_dir.iterdir()):
            if child.name in {".gitkeep", "index.json"}:
                continue
            catalog.append({"job_id": job_dir.name, "module": child.name})
    return catalog


def run_brain(
    message: str,
    history: list[dict[str, str]],
    catalog: list[ModuleRef],
) -> dict[str, object]:
    api_key = require_env("GROQ_API_KEY")
    lines = [f"- job_id={m['job_id']} module={m['module']}" for m in catalog]
    system = "\n".join(
        [
            "Tu es le cerveau WSAI Factory sur Render.",
            "Tu parles français, naturellement, pour comprendre le besoin utilisateur.",
            "Tu choisis UNIQUEMENT des modules du catalogue stock fourni.",
            "Tu ne génères pas de code source.",
            "Réponds UNIQUEMENT JSON:",
            '{"status":"need_info"|"ready"|"impossible","reply":"...",',
            '"question":"...?", "tool_name":"...", "brief":"...",',
            '"modules":[{"job_id":"...","module":"..."}]}',
            "Catalogue:",
            *lines,
        ]
    )
    body = json.dumps(
        {
            "model": "llama-3.3-70b-versatile",
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                *[
                    {"role": h["role"], "content": h["content"]}
                    for h in history
                    if h.get("role") in {"user", "assistant"}
                    and isinstance(h.get("content"), str)
                ],
                {"role": "user", "content": message},
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{GROQ_API_BASE}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "wsai-factory-backend/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read().decode("utf-8")
            status = response.getcode()
            if status < 200 or status >= 300:
                raise FactoryError(
                    "groq_bad_status",
                    f"Groq HTTP {status}: {raw[:500]}",
                    502,
                )
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise FactoryError(
            "groq_http_error",
            f"Groq HTTP {exc.code}: {err[:800]}",
            502,
        ) from exc
    except urllib.error.URLError as exc:
        raise FactoryError("groq_network", f"Groq network: {exc}", 502) from exc
    parsed = json.loads(raw)
    choices = parsed.get("choices")
    if not isinstance(choices, list) or len(choices) == 0:
        raise FactoryError("groq_no_choices", "Groq missing choices", 502)
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str) or content.strip() == "":
        raise FactoryError("groq_empty", "Groq empty content", 502)
    decision = json.loads(content)
    if not isinstance(decision, dict):
        raise FactoryError("groq_bad_decision", "decision must be object", 502)
    return decision
