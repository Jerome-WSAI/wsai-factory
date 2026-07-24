"""Shared types and IO for WSAI-Factory pipeline. Fail loud. No silent recovery."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Mapping, TypedDict, cast


REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ROOT = REPO_ROOT / "pipeline"
INBOX_ROOT = PIPELINE_ROOT / "inbox"
JOBS_ROOT = PIPELINE_ROOT / "jobs"
STOCK_ROOT = PIPELINE_ROOT / "stock"
FAILED_ROOT = PIPELINE_ROOT / "_failed"

StageName = Literal[
    "inbox",
    "stripped",
    "docs",
    "aligned",
    "modularized",
    "stock",
    "failed",
]
StatusName = Literal["pending", "running", "ok", "failed"]

VALID_STAGES: frozenset[str] = frozenset(
    {
        "inbox",
        "stripped",
        "docs",
        "aligned",
        "modularized",
        "stock",
        "failed",
    }
)
VALID_STATUSES: frozenset[str] = frozenset({"pending", "running", "ok", "failed"})

SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,120}$")


class PipelineError(Exception):
    def __init__(self, code: str, message: str, at_stage: str) -> None:
        self.code = code
        self.message = message
        self.at_stage = at_stage
        super().__init__(f"[{code}@{at_stage}] {message}")


class ErrorBlock(TypedDict):
    code: str
    message: str
    at_stage: str


class PathsBlock(TypedDict):
    inbox: str
    stripped: str
    docs: str
    aligned: str
    modules: str
    stock: str
    failed: str


class JobState(TypedDict):
    job_id: str
    slug: str
    stage: StageName
    status: StatusName
    created_at: str
    updated_at: str
    paths: PathsBlock
    inventory_path: str
    docs_manifest_path: str
    align_report_path: str
    module_plan_path: str
    webhook_last_stage: str
    git_commit: str
    error: ErrorBlock


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_job_id(slug: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    return f"{stamp}-{slug}-{short}"


def assert_slug(slug: str) -> None:
    if not SLUG_RE.match(slug):
        raise PipelineError(
            "invalid_slug",
            f"slug must match {SLUG_RE.pattern}, got {slug!r}",
            "inbox",
        )


def read_json_object(path: Path, at_stage: str) -> dict[str, object]:
    if not path.is_file():
        raise PipelineError(
            "missing_json",
            f"required json missing: {path}",
            at_stage,
        )
    raw = path.read_text(encoding="utf-8-sig")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise PipelineError(
            "invalid_json_root",
            f"json root must be object: {path}",
            at_stage,
        )
    return cast(dict[str, object], data)


def write_json(path: Path, data: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(data), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def require_string(data: Mapping[str, object], key: str, at_stage: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or value == "":
        raise PipelineError(
            "missing_field",
            f"field {key!r} must be non-empty string",
            at_stage,
        )
    return value


def validate_state(data: Mapping[str, object]) -> JobState:
    stage_raw = require_string(data, "stage", "state")
    status_raw = require_string(data, "status", "state")
    if stage_raw not in VALID_STAGES:
        raise PipelineError(
            "invalid_stage",
            f"stage {stage_raw!r} not in {sorted(VALID_STAGES)}",
            "state",
        )
    if status_raw not in VALID_STATUSES:
        raise PipelineError(
            "invalid_status",
            f"status {status_raw!r} not in {sorted(VALID_STATUSES)}",
            "state",
        )
    job_id = require_string(data, "job_id", "state")
    slug = require_string(data, "slug", "state")
    paths_obj = data.get("paths")
    if not isinstance(paths_obj, dict):
        raise PipelineError("missing_paths", "paths must be object", "state")
    paths_map = cast(dict[str, object], paths_obj)
    paths: PathsBlock = {
        "inbox": require_string(paths_map, "inbox", "state"),
        "stripped": require_string(paths_map, "stripped", "state"),
        "docs": require_string(paths_map, "docs", "state"),
        "aligned": require_string(paths_map, "aligned", "state"),
        "modules": require_string(paths_map, "modules", "state"),
        "stock": require_string(paths_map, "stock", "state"),
        "failed": require_string(paths_map, "failed", "state"),
    }
    error_obj = data.get("error")
    if not isinstance(error_obj, dict):
        raise PipelineError("missing_error", "error must be object", "state")
    error_map = cast(dict[str, object], error_obj)
    error: ErrorBlock = {
        "code": str(error_map.get("code") if isinstance(error_map.get("code"), str) else ""),
        "message": str(
            error_map.get("message") if isinstance(error_map.get("message"), str) else ""
        ),
        "at_stage": str(
            error_map.get("at_stage") if isinstance(error_map.get("at_stage"), str) else ""
        ),
    }
    return {
        "job_id": job_id,
        "slug": slug,
        "stage": cast(StageName, stage_raw),
        "status": cast(StatusName, status_raw),
        "created_at": require_string(data, "created_at", "state"),
        "updated_at": require_string(data, "updated_at", "state"),
        "paths": paths,
        "inventory_path": require_string(data, "inventory_path", "state"),
        "docs_manifest_path": require_string(data, "docs_manifest_path", "state"),
        "align_report_path": require_string(data, "align_report_path", "state"),
        "module_plan_path": require_string(data, "module_plan_path", "state"),
        "webhook_last_stage": (
            data["webhook_last_stage"]
            if isinstance(data.get("webhook_last_stage"), str)
            else ""
        ),
        "git_commit": (
            data["git_commit"] if isinstance(data.get("git_commit"), str) else ""
        ),
        "error": error,
    }


def create_initial_state(job_id: str, slug: str) -> JobState:
    now = utc_now_iso()
    job_dir = JOBS_ROOT / job_id
    return {
        "job_id": job_id,
        "slug": slug,
        "stage": "inbox",
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "paths": {
            "inbox": str(INBOX_ROOT / slug).replace("\\", "/"),
            "stripped": str(job_dir / "01-stripped").replace("\\", "/"),
            "docs": str(job_dir / "02-docs").replace("\\", "/"),
            "aligned": str(job_dir / "03-aligned").replace("\\", "/"),
            "modules": str(job_dir / "04-modules").replace("\\", "/"),
            "stock": str(STOCK_ROOT).replace("\\", "/"),
            "failed": str(FAILED_ROOT / job_id).replace("\\", "/"),
        },
        "inventory_path": str(job_dir / "inventory.json").replace("\\", "/"),
        "docs_manifest_path": str(job_dir / "02-docs" / "docs_manifest.json").replace(
            "\\", "/"
        ),
        "align_report_path": str(
            job_dir / "03-aligned" / "align_report.json"
        ).replace("\\", "/"),
        "module_plan_path": str(job_dir / "module_plan.json").replace("\\", "/"),
        "webhook_last_stage": "",
        "git_commit": "",
        "error": {"code": "", "message": "", "at_stage": ""},
    }


def state_path_for_job(job_id: str) -> Path:
    return JOBS_ROOT / job_id / "state.json"


def with_failed(state: JobState, code: str, message: str, at_stage: str) -> JobState:
    return {
        **state,
        "stage": "failed",
        "status": "failed",
        "updated_at": utc_now_iso(),
        "error": {"code": code, "message": message, "at_stage": at_stage},
    }


def with_stage(state: JobState, stage: StageName, status: StatusName) -> JobState:
    return {
        **state,
        "stage": stage,
        "status": status,
        "updated_at": utc_now_iso(),
        "error": {"code": "", "message": "", "at_stage": ""},
    }
