"""Propose module boundaries from filesystem/import layout. No invention of new features.

Output: module_plan.json with units derived only from existing directories/files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline_lib import (
    PipelineError,
    read_json_object,
    require_string,
    state_path_for_job,
    utc_now_iso,
    validate_state,
    write_json,
)


SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "dist",
        "build",
        "target",
        ".venv",
        "venv",
        "__pycache__",
        "official_docs",
    }
)


def top_level_units(code_root: Path) -> list[dict[str, object]]:
    units: list[dict[str, object]] = []
    if not code_root.is_dir():
        raise PipelineError(
            "missing_code_root",
            f"code root missing: {code_root}",
            "modularize",
        )
    children = [p for p in sorted(code_root.iterdir()) if p.name not in SKIP_DIRS]
    dirs = [p for p in children if p.is_dir()]
    files = [p for p in children if p.is_file()]
    if len(dirs) == 0 and len(files) == 0:
        raise PipelineError(
            "empty_code_root",
            f"no files to unitize under {code_root}",
            "modularize",
        )
    if len(dirs) == 0:
        file_list = [p.name for p in files]
        root_name = code_root.name
        if root_name == "":
            raise PipelineError(
                "empty_root_name",
                f"code root has empty name: {code_root}",
                "modularize",
            )
        units.append(
            {
                "module_name": root_name,
                "source_paths": file_list,
                "evidence": "single_root_no_subdirs",
            }
        )
        return units
    for directory in dirs:
        nested = [
            p.relative_to(code_root).as_posix()
            for p in directory.rglob("*")
            if p.is_file() and not any(part in SKIP_DIRS for part in p.parts)
        ]
        if len(nested) == 0:
            continue
        units.append(
            {
                "module_name": directory.name,
                "source_paths": nested,
                "evidence": "existing_directory",
            }
        )
    if len(units) == 0:
        raise PipelineError(
            "no_units",
            "directories exist but contain no files; cannot plan modules",
            "modularize",
        )
    return units


def main() -> None:
    parser = argparse.ArgumentParser(description="AST/FS module plan (no invention)")
    parser.add_argument("--job-id", required=True)
    parser.add_argument(
        "--code-subdir",
        required=True,
        help="Subpath under job to scan, e.g. 03-aligned or 01-stripped",
    )
    args = parser.parse_args()
    state = validate_state(read_json_object(state_path_for_job(args.job_id), "modularize"))
    job_id = state["job_id"]
    job_root = state_path_for_job(job_id).parent
    code_root = job_root / args.code_subdir
    units = top_level_units(code_root)
    plan = {
        "job_id": job_id,
        "created_at": utc_now_iso(),
        "code_root": str(code_root).replace("\\", "/"),
        "units": units,
        "rule": "units_only_from_existing_directories_or_single_root",
    }
    out = Path(state["module_plan_path"])
    write_json(out, plan)
    print(json.dumps({"ok": True, "module_plan_path": str(out), "unit_count": len(units)}))


if __name__ == "__main__":
    main()
