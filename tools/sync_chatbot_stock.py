"""Copy pipeline/stock into chatbot/stock for the Vercel UI. Fail if source empty of modules."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from pipeline_lib import PipelineError


def sync_chatbot_stock(source: Path, destination: Path) -> dict[str, str | int]:
    if not source.is_dir():
        raise PipelineError(
            "stock_missing",
            f"stock source missing: {source}",
            "chatbot",
        )
    module_files = [
        p
        for p in source.rglob("*")
        if p.is_file() and p.name not in {".gitkeep", "index.json"}
    ]
    if len(module_files) == 0:
        raise PipelineError(
            "stock_empty",
            f"no module files under {source}; refuse empty chatbot stock sync",
            "chatbot",
        )
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return {
        "source": str(source.resolve()).replace("\\", "/"),
        "destination": str(destination.resolve()).replace("\\", "/"),
        "file_count": len(module_files),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync pipeline/stock -> chatbot/stock")
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    out = sync_chatbot_stock(Path(args.source), Path(args.destination))
    print(json.dumps({"ok": True, **out}, ensure_ascii=False))


if __name__ == "__main__":
    main()
