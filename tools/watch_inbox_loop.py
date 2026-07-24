"""Poll pipeline/inbox forever using watch_inbox_once.scan_once."""

from __future__ import annotations

import argparse
import json
import time

from watch_inbox_once import scan_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Loop scan of pipeline/inbox")
    parser.add_argument("--polls", required=True, type=int)
    parser.add_argument("--interval-sec", required=True, type=float)
    parser.add_argument("--loop-sleep-sec", required=True, type=float)
    args = parser.parse_args()
    while True:
        results = scan_once(args.polls, args.interval_sec)
        if len(results) > 0:
            print(json.dumps({"ok": True, "processed": results}, ensure_ascii=False))
        time.sleep(args.loop_sleep_sec)


if __name__ == "__main__":
    main()
