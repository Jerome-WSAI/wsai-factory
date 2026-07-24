"""HTTP UI for stock chatbot. Serves query form + /api/query over pipeline/stock."""

from __future__ import annotations

import argparse
from pathlib import Path

from stock_chatbot import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve stock chatbot UI")
    parser.add_argument("--stock-root", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    serve(Path(args.stock_root), args.host, args.port)


if __name__ == "__main__":
    main()
