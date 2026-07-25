"""Sync pipeline stock into chatbot/stock and deploy Vercel production.

Fails loud. Does not print secret values.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHATBOT = ROOT / "chatbot"


class DeployError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def run(cmd: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise DeployError(
            "command_failed",
            f"cmd={cmd!r} exit={proc.returncode} stderr={proc.stderr.strip()} stdout={proc.stdout.strip()}",
        )
    return proc.stdout


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
        print(json.dumps({"ok": True, "deployed": False, "sync": json.loads(sync_out)}))
        return
    deploy_out = run(
        ["vercel", "deploy", "--prod", "--yes"],
        CHATBOT,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "deployed": True,
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
