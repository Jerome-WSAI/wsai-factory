"""Create Cursor Cloud Agents via API (https://api.cursor.com/v1/agents).

Auth: Basic with CURSOR_API_KEY (empty password) or Bearer.
Docs: https://cursor.com/docs/cloud-agent/api/endpoints
Does not print the API key. Fail loud on HTTP errors.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import TypedDict

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from pipeline_lib import PipelineError, REPO_ROOT


API_BASE = "https://api.cursor.com/v1"
AUTOMATIONS_DIR = REPO_ROOT / "automations"

STAGE_SPECS: dict[str, str] = {
    "inbox": "inbox.md",
    "docs": "docs.md",
    "align": "align.md",
    "modularize": "modularize.md",
}


class CreateResult(TypedDict):
    stage: str
    agent_id: str
    run_id: str
    name: str
    url: str


def require_api_key() -> str:
    key = os.environ.get("CURSOR_API_KEY")
    if not isinstance(key, str) or key.strip() == "":
        raise PipelineError(
            "missing_cursor_api_key",
            "set env CURSOR_API_KEY (Cursor Dashboard → API Keys)",
            "cloud_agent",
        )
    return key.strip()


def auth_header(api_key: str) -> str:
    token = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def api_request(
    method: str,
    path: str,
    api_key: str,
    body: dict[str, object] | None,
) -> dict[str, object]:
    url = f"{API_BASE}{path}"
    data: bytes | None = None
    headers = {
        "Authorization": auth_header(api_key),
        "Accept": "application/json",
        "User-Agent": "wsai-factory-cloud-agent/1.0",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = response.getcode()
            raw = response.read().decode("utf-8")
            if status < 200 or status >= 300:
                raise PipelineError(
                    "cursor_api_bad_status",
                    f"{method} {path} HTTP {status}: {raw[:500]}",
                    "cloud_agent",
                )
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise PipelineError(
            "cursor_api_http_error",
            f"{method} {path} HTTP {exc.code}: {err_body[:800]}",
            "cloud_agent",
        ) from exc
    except urllib.error.URLError as exc:
        raise PipelineError(
            "cursor_api_network",
            f"{method} {path} failed: {exc}",
            "cloud_agent",
        ) from exc
    if raw.strip() == "":
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise PipelineError(
            "cursor_api_not_object",
            f"{method} {path} response root must be object",
            "cloud_agent",
        )
    return parsed


def read_stage_prompt(stage: str) -> str:
    if stage not in STAGE_SPECS:
        raise PipelineError(
            "bad_stage",
            f"stage must be one of {sorted(STAGE_SPECS)}",
            "cloud_agent",
        )
    path = AUTOMATIONS_DIR / STAGE_SPECS[stage]
    if not path.is_file():
        raise PipelineError(
            "missing_prompt",
            f"missing prompt file: {path}",
            "cloud_agent",
        )
    text = path.read_text(encoding="utf-8").strip()
    if text == "":
        raise PipelineError(
            "empty_prompt",
            f"prompt file empty: {path}",
            "cloud_agent",
        )
    return (
        f"You are the WSAI-Factory cloud agent for stage={stage}.\n"
        f"Follow the contract below exactly. Fail loud. Do not invent code or docs.\n"
        f"Repo layout: pipeline/inbox, pipeline/jobs, pipeline/stock, tools/.\n\n"
        f"{text}"
    )


def create_agent(
    api_key: str,
    stage: str,
    repo_url: str,
    starting_ref: str,
    model_id: str,
    auto_create_pr: bool,
) -> CreateResult:
    prompt = read_stage_prompt(stage)
    name = f"WSAI Factory - {stage}"
    body: dict[str, object] = {
        "name": name,
        "prompt": {"text": prompt},
        "model": {
            "id": model_id,
            "params": [
                {"id": "effort", "value": "high"},
                {"id": "fast", "value": "true"},
            ],
        },
        "repos": [{"url": repo_url, "startingRef": starting_ref}],
        "autoCreatePR": auto_create_pr,
        "workOnCurrentBranch": False,
    }
    if model_id == "default":
        body.pop("model")
    response = api_request("POST", "/agents", api_key, body)
    agent = response.get("agent")
    run = response.get("run")
    if not isinstance(agent, dict) or not isinstance(run, dict):
        raise PipelineError(
            "cursor_api_bad_shape",
            f"create response missing agent/run objects: keys={list(response.keys())}",
            "cloud_agent",
        )
    agent_id = agent.get("id")
    run_id = run.get("id")
    if not isinstance(agent_id, str) or agent_id == "":
        raise PipelineError(
            "cursor_api_missing_agent_id",
            "create response agent.id missing",
            "cloud_agent",
        )
    if not isinstance(run_id, str) or run_id == "":
        raise PipelineError(
            "cursor_api_missing_run_id",
            "create response run.id missing",
            "cloud_agent",
        )
    return {
        "stage": stage,
        "agent_id": agent_id,
        "run_id": run_id,
        "name": name,
        "url": f"https://cursor.com/agents/{agent_id}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create WSAI-Factory Cursor Cloud Agents via API"
    )
    parser.add_argument(
        "--stage",
        required=True,
        choices=["inbox", "docs", "align", "modularize", "all"],
    )
    parser.add_argument("--repo-url", required=True)
    parser.add_argument("--starting-ref", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--auto-create-pr", required=True, choices=["yes", "no"])
    args = parser.parse_args()
    api_key = require_api_key()
    stages = (
        list(STAGE_SPECS.keys())
        if args.stage == "all"
        else [args.stage]
    )
    results: list[CreateResult] = []
    for stage in stages:
        results.append(
            create_agent(
                api_key,
                stage,
                args.repo_url,
                args.starting_ref,
                args.model_id,
                args.auto_create_pr == "yes",
            )
        )
    print(json.dumps({"ok": True, "created": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
