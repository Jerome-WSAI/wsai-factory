"""Run local automated pipeline for one inbox slug: strip→docs→align→modules→stock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from apply_modules_stock import apply_and_stock
from pipeline_lib import INBOX_ROOT, PIPELINE_ROOT, PipelineError, REPO_ROOT, assert_slug
from stage_align_local import run_align
from stage_docs_local import run_docs
from sync_chatbot_stock import sync_chatbot_stock
from watch_inbox_once import process_inbox_entry


def run_slug(slug: str, polls: int, interval_sec: float) -> dict[str, str | int]:
    assert_slug(slug)
    slug_dir = INBOX_ROOT / slug
    if not slug_dir.is_dir():
        raise PipelineError(
            "missing_inbox_slug",
            f"inbox slug missing: {slug_dir}",
            "inbox",
        )
    result = process_inbox_entry(slug_dir, polls, interval_sec)
    job_dir = Path(result["job_dir"])
    job_id = job_dir.name
    run_docs(job_id)
    run_align(job_id)
    apply_and_stock(job_id)
    chatbot_stock = REPO_ROOT / "chatbot" / "stock"
    sync_info = sync_chatbot_stock(PIPELINE_ROOT / "stock", chatbot_stock)
    return {
        "job_id": job_id,
        "slug": slug,
        "job_dir": str(job_dir),
        "stage": "stock",
        "chatbot_stock_files": int(sync_info["file_count"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Local E2E pipeline automation")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--polls", required=True, type=int)
    parser.add_argument("--interval-sec", required=True, type=float)
    args = parser.parse_args()
    out = run_slug(args.slug, args.polls, args.interval_sec)
    print(json.dumps({"ok": True, **out}, ensure_ascii=False))


if __name__ == "__main__":
    main()
