"""Deprecated entrypoint. Use watch_inbox_once.py or watch_inbox_loop.py."""

from __future__ import annotations

import sys

if __name__ == "__main__":
    print(
        "use tools/watch_inbox_once.py or tools/watch_inbox_loop.py (mode flag forbidden)",
        file=sys.stderr,
    )
    raise SystemExit(2)
