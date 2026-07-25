"""Advance a job stage marker + optional webhook/git. Prefer tools/pipeline_automate.py for local E2E."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast

from pipeline_lib import (
    JobState,
    PipelineError,
    StageName,
    StatusName,
    read_json_object,
    require_string,
    state_path_for_job,
    utc_now_iso,
    validate_state,
    with_failed,
    with_stage,
    write_json,
)


STAGE_ORDER = [
    "stripped",
    "docs",
    "aligned",
    "modularized",
    "stock",
]


def load_state(job_id: str) -> JobState:
    state = validate_state(read_json_object(state_path_for_job(job_id), "advance"))
    if state["job_id"] != job_id:
        raise PipelineError(
            "job_id_mismatch",
            "state.job_id does not match argument",
            "advance",
        )
    return state


def assert_can_advance(state: JobState, target_stage: str) -> None:
    if target_stage not in STAGE_ORDER:
        raise PipelineError(
            "bad_target",
            f"target_stage must be one of {STAGE_ORDER}",
            "advance",
        )
    current = state["stage"]
    status = state["status"]
    if status == "failed":
        raise PipelineError(
            "job_failed",
            "cannot advance a failed job; inspect pipeline/_failed",
            current,
        )
    if current == "inbox":
        raise PipelineError(
            "not_stripped",
            "run strip before advance",
            "inbox",
        )
    if current not in STAGE_ORDER:
        raise PipelineError(
            "bad_current",
            f"cannot advance from stage {current!r}",
            current,
        )
    current_idx = STAGE_ORDER.index(current)
    target_idx = STAGE_ORDER.index(target_stage)
    if current_idx >= len(STAGE_ORDER) - 1:
        raise PipelineError(
            "already_terminal",
            f"job already at terminal stage {current!r}; cannot advance to {target_stage!r}",
            current,
        )
    next_stage = STAGE_ORDER[current_idx + 1]
    if target_idx != current_idx + 1:
        raise PipelineError(
            "skip_forbidden",
            f"must advance {current!r} -> {next_stage!r}, not {target_stage!r}",
            current,
        )
    if target_stage == "docs":
        inv = Path(state["inventory_path"])
        if not inv.is_file():
            raise PipelineError(
                "missing_inventory",
                f"inventory required: {inv}",
                "stripped",
            )
    if target_stage == "aligned":
        docs_manifest = Path(state["docs_manifest_path"])
        if not docs_manifest.is_file():
            raise PipelineError(
                "missing_docs_manifest",
                f"docs_manifest required: {docs_manifest}",
                "docs",
            )
        manifest = read_json_object(docs_manifest, "docs")
        deps = manifest.get("dependencies")
        if not isinstance(deps, list):
            raise PipelineError(
                "bad_docs_manifest",
                "docs_manifest.dependencies must be a list",
                "docs",
            )
        for item in deps:
            if not isinstance(item, dict):
                raise PipelineError(
                    "bad_docs_item",
                    "dependency entry must be object",
                    "docs",
                )
            dep = cast(dict[str, object], item)
            doc_status = require_string(dep, "doc_status", "docs")
            if doc_status == "unresolved":
                raise PipelineError(
                    "unresolved_docs",
                    "cannot align while a dependency is unresolved",
                    "docs",
                )
            if doc_status != "resolved":
                raise PipelineError(
                    "docs_incomplete",
                    f"dependency doc_status must be resolved, got {doc_status!r}",
                    "docs",
                )


def post_webhook(url: str, payload: dict[str, object], api_key: str) -> None:
    headers = {"Content-Type": "application/json"}
    if api_key != "":
        headers["Authorization"] = f"Bearer {api_key}"
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.getcode()
            if status < 200 or status >= 300:
                raise PipelineError(
                    "webhook_bad_status",
                    f"webhook returned HTTP {status}",
                    "advance",
                )
    except urllib.error.URLError as exc:
        raise PipelineError(
            "webhook_failed",
            f"webhook POST failed: {exc}",
            "advance",
        ) from exc


def git_commit_and_optional_push(paths: list[str], message: str, do_push: bool) -> str:
    cwd = str(Path(__file__).resolve().parents[1])
    for relative in paths:
        subprocess.run(
            ["git", "add", "--", relative],
            check=True,
            cwd=cwd,
        )
    result = subprocess.run(
        ["git", "commit", "-m", message],
        check=False,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PipelineError(
            "git_commit_failed",
            f"git commit failed: {result.stderr.strip()}",
            "advance",
        )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    commit = head.stdout.strip()
    if do_push:
        push = subprocess.run(
            ["git", "push"],
            check=False,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if push.returncode != 0:
            raise PipelineError(
                "git_push_failed",
                f"git push failed: {push.stderr.strip()}",
                "advance",
            )
    return commit


def main() -> None:
    parser = argparse.ArgumentParser(description="Advance pipeline job stage marker")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--to-stage", required=True, choices=STAGE_ORDER)
    parser.add_argument("--webhook-url", required=True)
    parser.add_argument("--git-commit", required=True, choices=["yes", "no"])
    parser.add_argument("--git-push", required=True, choices=["yes", "no"])
    args = parser.parse_args()
    state = load_state(args.job_id)
    try:
        assert_can_advance(state, args.to_stage)
        payload: dict[str, object] = {
            "job_id": args.job_id,
            "slug": state["slug"],
            "from_stage": state["stage"],
            "to_stage": args.to_stage,
            "inventory_path": state["inventory_path"],
            "repo": "Jerome-WSAI/wsai-factory",
        }
        updated = state
        if args.webhook_url != "NONE":
            api_key = os.environ.get("WSAI_FACTORY_WEBHOOK_KEY")
            if not isinstance(api_key, str):
                raise PipelineError(
                    "missing_webhook_key",
                    "env WSAI_FACTORY_WEBHOOK_KEY required when webhook-url is not NONE",
                    "advance",
                )
            post_webhook(args.webhook_url, payload, api_key)
            updated = {
                **updated,
                "webhook_last_stage": args.to_stage,
                "updated_at": utc_now_iso(),
            }
        if args.git_commit == "yes":
            job_rel = f"pipeline/jobs/{args.job_id}"
            commit = git_commit_and_optional_push(
                [job_rel],
                f"pipeline({args.job_id}): advance to {args.to_stage}",
                args.git_push == "yes",
            )
            updated = {**updated, "git_commit": commit, "updated_at": utc_now_iso()}
        elif args.git_push == "yes":
            raise PipelineError(
                "push_without_commit",
                "git-push=yes requires git-commit=yes",
                "advance",
            )
        status_value: StatusName = "ok" if args.to_stage == "stock" else "running"
        stage_value: StageName
        if args.to_stage == "stripped":
            stage_value = "stripped"
        elif args.to_stage == "docs":
            stage_value = "docs"
        elif args.to_stage == "aligned":
            stage_value = "aligned"
        elif args.to_stage == "modularized":
            stage_value = "modularized"
        elif args.to_stage == "stock":
            stage_value = "stock"
        else:
            raise PipelineError(
                "bad_target",
                f"unsupported to-stage {args.to_stage!r}",
                "advance",
            )
        final = with_stage(updated, stage_value, status_value)
        write_json(state_path_for_job(args.job_id), final)
        print(json.dumps({"ok": True, "state": final}, ensure_ascii=False))
    except PipelineError as exc:
        failed = with_failed(state, exc.code, exc.message, exc.at_stage)
        write_json(state_path_for_job(args.job_id), failed)
        raise


if __name__ == "__main__":
    main()
