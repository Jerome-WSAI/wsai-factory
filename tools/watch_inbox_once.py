"""Scan pipeline/inbox once: stable dirs → strip → archive to inbox/_processed."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from pipeline_lib import INBOX_ROOT, PipelineError, assert_slug
from strip_and_inventory import run_strip_job


def dir_signature(path: Path) -> tuple[int, int]:
    file_count = 0
    total_size = 0
    for file_path in path.rglob("*"):
        if file_path.is_file():
            file_count += 1
            total_size += file_path.stat().st_size
    return file_count, total_size


def wait_stable(path: Path, polls: int, interval_sec: float) -> None:
    if polls < 2:
        raise PipelineError(
            "bad_debounce",
            "polls must be >= 2",
            "inbox",
        )
    previous = dir_signature(path)
    for _ in range(polls - 1):
        time.sleep(interval_sec)
        current = dir_signature(path)
        if current != previous:
            previous = current
            continue
        if current[0] == 0:
            raise PipelineError(
                "empty_inbox_dir",
                f"inbox folder empty: {path}",
                "inbox",
            )
        return
    raise PipelineError(
        "unstable_inbox",
        f"directory still changing after debounce: {path}",
        "inbox",
    )


def process_inbox_entry(slug_dir: Path, polls: int, interval_sec: float) -> dict[str, str]:
    slug = slug_dir.name
    assert_slug(slug)
    wait_stable(slug_dir, polls, interval_sec)
    job_dir = run_strip_job(slug_dir, slug)
    processed = INBOX_ROOT / "_processed"
    processed.mkdir(parents=True, exist_ok=True)
    destination = processed / slug
    if destination.exists():
        raise PipelineError(
            "processed_collision",
            f"already processed slug exists: {destination}",
            "inbox",
        )
    shutil.move(str(slug_dir), str(destination))
    return {"slug": slug, "job_dir": str(job_dir), "archived_inbox": str(destination)}


def scan_once(polls: int, interval_sec: float) -> list[dict[str, str]]:
    INBOX_ROOT.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, str]] = []
    for entry in sorted(INBOX_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("_"):
            continue
        if entry.name.startswith("."):
            continue
        results.append(process_inbox_entry(entry, polls, interval_sec))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Single scan of pipeline/inbox")
    parser.add_argument("--polls", required=True, type=int)
    parser.add_argument("--interval-sec", required=True, type=float)
    args = parser.parse_args()
    results = scan_once(args.polls, args.interval_sec)
    print(json.dumps({"ok": True, "processed": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
