"""Start local factory workers (inbox watcher loop). Explicit start only."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from pipeline_lib import REPO_ROOT


def start_inbox_loop(polls: int, interval_sec: float, loop_sleep_sec: float) -> dict[str, object]:
    script = REPO_ROOT / "tools" / "watch_inbox_loop.py"
    if not script.is_file():
        raise FileNotFoundError(f"missing worker script: {script}")
    proc = subprocess.Popen(
        [
            sys.executable,
            str(script),
            "--polls",
            str(polls),
            "--interval-sec",
            str(interval_sec),
            "--loop-sleep-sec",
            str(loop_sleep_sec),
        ],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return {
        "worker": "inbox_loop",
        "pid": proc.pid,
        "command": [
            sys.executable,
            str(script),
            "--polls",
            str(polls),
            "--interval-sec",
            str(interval_sec),
            "--loop-sleep-sec",
            str(loop_sleep_sec),
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Start WSAI-Factory local workers")
    parser.add_argument(
        "--worker",
        required=True,
        choices=["inbox_loop"],
        help="Which worker to start",
    )
    parser.add_argument("--polls", required=True, type=int)
    parser.add_argument("--interval-sec", required=True, type=float)
    parser.add_argument("--loop-sleep-sec", required=True, type=float)
    args = parser.parse_args()
    if args.worker == "inbox_loop":
        out = start_inbox_loop(args.polls, args.interval_sec, args.loop_sleep_sec)
        print(json.dumps({"ok": True, **out}, ensure_ascii=False))
        return
    raise SystemExit(2)


if __name__ == "__main__":
    main()
