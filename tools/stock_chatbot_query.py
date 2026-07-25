"""CLI: query factory stock. Prints on-disk module contents only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline_lib import PipelineError
from stock_chatbot import query_stock


def emit(payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Query pipeline/stock; never invent code")
    parser.add_argument("--query", required=True)
    parser.add_argument("--stock-root", required=True)
    args = parser.parse_args()
    try:
        result = query_stock(args.query, Path(args.stock_root))
    except PipelineError as exc:
        emit(
            {
                "ok": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "at_stage": exc.at_stage,
                },
            }
        )
        raise SystemExit(1) from exc
    emit({"ok": True, "result": result})


if __name__ == "__main__":
    main()
