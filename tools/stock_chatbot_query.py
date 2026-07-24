"""CLI: query factory stock. Prints on-disk module contents only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline_lib import PipelineError
from stock_chatbot import query_stock


def main() -> None:
    parser = argparse.ArgumentParser(description="Query pipeline/stock; never invent code")
    parser.add_argument("--query", required=True)
    parser.add_argument("--stock-root", required=True)
    args = parser.parse_args()
    try:
        result = query_stock(args.query, Path(args.stock_root))
    except PipelineError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "at_stage": exc.at_stage,
                    },
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(1) from exc
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
