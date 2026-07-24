"""Local align stage: copy stripped→aligned, structural checks vs docs_manifest. No invention."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import cast

from pipeline_lib import (
    PipelineError,
    read_json_object,
    require_string,
    state_path_for_job,
    utc_now_iso,
    validate_state,
    with_failed,
    with_stage,
    write_json,
)


def run_align(job_id: str) -> None:
    state = validate_state(read_json_object(state_path_for_job(job_id), "align"))
    if state["stage"] != "docs" or state["status"] != "ok":
        raise PipelineError(
            "docs_not_ok",
            "align requires stage=docs status=ok",
            state["stage"],
        )
    manifest = read_json_object(Path(state["docs_manifest_path"]), "align")
    deps_raw = manifest.get("dependencies")
    if not isinstance(deps_raw, list):
        raise PipelineError(
            "bad_docs_manifest",
            "docs_manifest.dependencies must be a list",
            "align",
        )
    rules: list[dict[str, str]] = []
    try:
        for item in deps_raw:
            if not isinstance(item, dict):
                raise PipelineError(
                    "bad_docs_item",
                    "dependency entry must be object",
                    "align",
                )
            dep = cast(dict[str, object], item)
            doc_status = require_string(dep, "doc_status", "align")
            name = require_string(dep, "name", "align")
            if doc_status == "unresolved":
                raise PipelineError(
                    "unresolved_docs",
                    f"cannot align with unresolved doc for {name}",
                    "align",
                )
            if doc_status != "resolved":
                raise PipelineError(
                    "docs_incomplete",
                    f"doc_status must be resolved for {name}, got {doc_status!r}",
                    "align",
                )
            url = require_string(dep, "url", "align")
            rules.append(
                {
                    "id": f"doc-present:{name}",
                    "status": "pass",
                    "evidence": url,
                }
            )
        stripped = Path(state["paths"]["stripped"])
        aligned = Path(state["paths"]["aligned"])
        if aligned.exists():
            shutil.rmtree(aligned)
        shutil.copytree(stripped, aligned)
        report = {
            "job_id": job_id,
            "created_at": utc_now_iso(),
            "mode": "local_structural",
            "rules": rules,
            "note": "Local align copies code and verifies resolved official doc URLs exist in manifest; deep semantic conform is Automation align.md",
        }
        write_json(Path(state["align_report_path"]), report)
        new_state = with_stage(state, "aligned", "ok")
        write_json(state_path_for_job(job_id), new_state)
    except PipelineError as exc:
        failed = with_failed(state, exc.code, exc.message, exc.at_stage)
        write_json(state_path_for_job(job_id), failed)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Local structural align stage")
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    run_align(args.job_id)
    print(json.dumps({"ok": True, "job_id": args.job_id, "stage": "aligned"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
