"""Apply module_plan.json into 04-modules/Projet/<module>/ then promote to pipeline/stock."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import cast

from pipeline_lib import (
    PipelineError,
    STOCK_ROOT,
    read_json_object,
    require_string,
    state_path_for_job,
    utc_now_iso,
    validate_state,
    with_failed,
    with_stage,
    write_json,
)
from ast_module_plan import top_level_units


def apply_and_stock(job_id: str) -> None:
    state = validate_state(read_json_object(state_path_for_job(job_id), "modularize"))
    if state["stage"] != "aligned" or state["status"] != "ok":
        raise PipelineError(
            "align_not_ok",
            "modularize requires stage=aligned status=ok",
            state["stage"],
        )
    aligned = Path(state["paths"]["aligned"])
    plan_path = Path(state["module_plan_path"])
    try:
        units = top_level_units(aligned)
        plan = {
            "job_id": job_id,
            "created_at": utc_now_iso(),
            "code_root": str(aligned).replace("\\", "/"),
            "units": units,
            "rule": "units_only_from_existing_directories_or_single_root",
        }
        write_json(plan_path, plan)
        modules_root = Path(state["paths"]["modules"]) / "Projet"
        if modules_root.exists():
            shutil.rmtree(modules_root)
        modules_root.mkdir(parents=True, exist_ok=True)
        stocked: list[str] = []
        for unit in units:
            module_name = unit["module_name"]
            if not isinstance(module_name, str) or module_name == "":
                raise PipelineError(
                    "bad_module_name",
                    "module_name must be non-empty string",
                    "modularize",
                )
            evidence = unit["evidence"]
            if evidence not in {"existing_directory", "single_root_no_subdirs"}:
                raise PipelineError(
                    "bad_evidence",
                    f"unsupported evidence {evidence!r}",
                    "modularize",
                )
            source_paths = unit["source_paths"]
            if not isinstance(source_paths, list) or len(source_paths) == 0:
                raise PipelineError(
                    "empty_unit",
                    f"module {module_name} has no source_paths",
                    "modularize",
                )
            dest = modules_root / module_name
            dest.mkdir(parents=True, exist_ok=False)
            for rel in source_paths:
                if not isinstance(rel, str):
                    raise PipelineError(
                        "bad_source_path",
                        "source_paths entries must be strings",
                        "modularize",
                    )
                src = aligned / rel
                if not src.is_file():
                    raise PipelineError(
                        "missing_source_file",
                        f"planned file missing: {src}",
                        "modularize",
                    )
                target = dest / Path(rel).name if evidence == "existing_directory" else dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
            stock_dest = STOCK_ROOT / job_id / module_name
            if stock_dest.exists():
                raise PipelineError(
                    "stock_collision",
                    f"stock module already exists: {stock_dest}",
                    "stock",
                )
            shutil.copytree(dest, stock_dest)
            stocked.append(f"{job_id}/{module_name}")
        index = {
            "job_id": job_id,
            "created_at": utc_now_iso(),
            "modules": stocked,
        }
        write_json(STOCK_ROOT / job_id / "index.json", index)
        new_state = with_stage(state, "stock", "ok")
        write_json(state_path_for_job(job_id), new_state)
    except PipelineError as exc:
        failed = with_failed(state, exc.code, exc.message, exc.at_stage)
        write_json(state_path_for_job(job_id), failed)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply modules and promote to stock")
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    apply_and_stock(args.job_id)
    print(json.dumps({"ok": True, "job_id": args.job_id, "stage": "stock"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
