"""Sync pipeline stock into chatbot/stock and deploy Vercel production.

Fails loud. Does not print secret values.
Preflight: CLI must be authorized for the orgId in chatbot/.vercel/project.json
(WSAI team), not a personal fallback team.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
CHATBOT = ROOT / "chatbot"
VERCEL_PROJECT = CHATBOT / ".vercel" / "project.json"

REQUIRED_PRODUCTION_ENV = (
    "FACTORY_BACKEND_URL",
    "WSAI_FACTORY_WEBHOOK_KEY",
    "CHATBOT_API_SECRET",
)


class DeployError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_vercel() -> str:
    found = shutil.which("vercel")
    if found is None:
        raise DeployError(
            "vercel_missing",
            "vercel CLI not on PATH — install and ensure `vercel` resolves (Windows: vercel.cmd)",
        )
    return found


def vercel_token_args() -> list[str]:
    token = os.environ.get("VERCEL_TOKEN")
    if isinstance(token, str) and token.strip() != "":
        return ["--token", token.strip()]
    return []


def run(cmd: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if proc.returncode != 0:
        raise DeployError(
            "command_failed",
            f"cmd={cmd!r} exit={proc.returncode} stderr={proc.stderr.strip()} stdout={proc.stdout.strip()}",
        )
    return proc.stdout


def load_expected_org() -> str:
    if not VERCEL_PROJECT.is_file():
        raise DeployError(
            "missing_vercel_project",
            f"missing {VERCEL_PROJECT} — link chatbot to WSAI Vercel project first",
        )
    raw = json.loads(VERCEL_PROJECT.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise DeployError("bad_vercel_project", "project.json root must be object")
    org_id = raw.get("orgId")
    if not isinstance(org_id, str) or org_id.strip() == "":
        raise DeployError("missing_org_id", "project.json.orgId must be non-empty string")
    return org_id.strip()


def assert_vercel_org_access(expected_org_id: str) -> Mapping[str, object]:
    vercel = resolve_vercel()
    token_args = vercel_token_args()
    teams = subprocess.run(
        [vercel, "teams", "ls", *token_args],
        cwd=CHATBOT,
        capture_output=True,
        text=True,
        check=False,
    )
    teams_text = f"{teams.stdout}\n{teams.stderr}"
    if "Not authorized" in teams_text and expected_org_id not in teams_text:
        raise DeployError(
            "vercel_not_authorized",
            "vercel CLI not authorized for the WSAI org in "
            f"chatbot/.vercel/project.json (orgId={expected_org_id}). "
            "Personal team whytcard-dev is not enough — vercel login / switch into WSAI, "
            "or set env VERCEL_TOKEN for a token that can access that team, then set "
            f"Production env {', '.join(REQUIRED_PRODUCTION_ENV)} "
            "(FACTORY_BACKEND_URL=https://wsai-factory-backend.onrender.com).",
        )
    probe = subprocess.run(
        [vercel, "project", "ls", f"--scope={expected_org_id}", *token_args],
        cwd=CHATBOT,
        capture_output=True,
        text=True,
        check=False,
    )
    probe_text = f"{probe.stdout}\n{probe.stderr}"
    if (
        probe.returncode != 0
        or "Not authorized" in probe_text
        or "scope does not exist" in probe_text
    ):
        token_hint = (
            "VERCEL_TOKEN is set but still unauthorized for this org"
            if token_args
            else "VERCEL_TOKEN unset; interactive login is personal whytcard-dev only"
        )
        raise DeployError(
            "wrong_vercel_team",
            "vercel CLI cannot list projects for "
            f"orgId={expected_org_id} from chatbot/.vercel/project.json. "
            "Switch into the WSAI team (not personal whytcard-dev), "
            f"set Production env {', '.join(REQUIRED_PRODUCTION_ENV)} "
            "(FACTORY_BACKEND_URL=https://wsai-factory-backend.onrender.com), "
            f"then retry. {token_hint} "
            f"(teams_ls_exit={teams.returncode} project_ls_exit={probe.returncode}).",
        )
    return {
        "ok": True,
        "orgId": expected_org_id,
        "vercel": vercel,
        "token_mode": bool(token_args),
        "required_production_env": list(REQUIRED_PRODUCTION_ENV),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync stock and deploy chatbot")
    parser.add_argument("--prod", choices=("yes", "no"), required=True)
    args = parser.parse_args()
    sync_out = run(
        [
            sys.executable,
            str(ROOT / "tools" / "sync_chatbot_stock.py"),
            "--source",
            str(ROOT / "pipeline" / "stock"),
            "--destination",
            str(CHATBOT / "stock"),
        ],
        ROOT,
    )
    if args.prod != "yes":
        print(
            json.dumps(
                {
                    "ok": True,
                    "deployed": False,
                    "sync": json.loads(sync_out),
                }
            )
        )
        return
    expected_org = load_expected_org()
    preflight = assert_vercel_org_access(expected_org)
    deploy_out = run(
        [
            resolve_vercel(),
            "deploy",
            "--prod",
            "--yes",
            f"--scope={expected_org}",
            *vercel_token_args(),
        ],
        CHATBOT,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "deployed": True,
                "preflight": preflight,
                "sync": json.loads(sync_out),
                "vercel_stdout": deploy_out.strip().splitlines()[-5:],
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except DeployError as exc:
        print(json.dumps({"ok": False, "error": {"code": exc.code, "message": exc.message}}))
        raise SystemExit(1) from exc
