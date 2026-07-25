"""Assemble stock modules + frontend template into a downloadable zip."""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from errors import FactoryError

_REPO = Path(__file__).resolve().parents[1]
_TOOLS = _REPO / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from pipeline_lib import PIPELINE_ROOT, STOCK_ROOT  # noqa: E402


class ModuleRef(TypedDict):
    job_id: str
    module: str


DELIVERIES = PIPELINE_ROOT / "deliveries"
TEMPLATE = PIPELINE_ROOT / "templates" / "frontend"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _copy_module(job_id: str, module: str, dest_root: Path) -> str:
    source = STOCK_ROOT / job_id / module
    if not source.is_dir():
        # module may be nested path like "src"
        alt = STOCK_ROOT / job_id
        if not alt.is_dir():
            raise FactoryError(
                "module_missing",
                f"stock module missing: job_id={job_id} module={module}",
                400,
            )
        # find module folder under job
        candidate = alt / module
        if not candidate.exists():
            raise FactoryError(
                "module_missing",
                f"stock path missing: {candidate}",
                400,
            )
        source = candidate
    safe_name = f"{job_id}__{module.replace('/', '_')}"
    dest = dest_root / "modules" / safe_name
    if source.is_dir():
        shutil.copytree(source, dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    return f"modules/{safe_name}"


def assemble_order(
    order_id: str,
    tool_name: str,
    brief: str,
    modules: list[ModuleRef],
) -> dict[str, object]:
    if not TEMPLATE.is_dir():
        raise FactoryError(
            "template_missing",
            f"frontend template missing: {TEMPLATE}",
            500,
        )
    if len(modules) == 0:
        raise FactoryError("no_modules", "modules list empty", 400)
    out_dir = PIPELINE_ROOT / "assembled" / order_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(TEMPLATE, out_dir)
    module_entries: list[dict[str, str]] = []
    for ref in modules:
        path = _copy_module(ref["job_id"], ref["module"], out_dir)
        module_entries.append(
            {
                "job_id": ref["job_id"],
                "module": ref["module"],
                "path": path,
            }
        )
    # rewrite template placeholders
    index = out_dir / "index.html"
    if index.is_file():
        index.write_text(
            index.read_text(encoding="utf-8").replace("{{TOOL_NAME}}", tool_name),
            encoding="utf-8",
        )
    manifest = {
        "order_id": order_id,
        "tool_name": tool_name,
        "brief": brief,
        "modules": module_entries,
        "assembled_at": _utc_now(),
    }
    (out_dir / "assembly_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "BRIEF.md").write_text(brief + "\n", encoding="utf-8")
    # smoke: require index + manifest + at least one module file
    module_files = list((out_dir / "modules").rglob("*"))
    if len([p for p in module_files if p.is_file()]) == 0:
        raise FactoryError(
            "assemble_empty_modules",
            "assembled tree has no module files",
            500,
        )
    DELIVERIES.mkdir(parents=True, exist_ok=True)
    zip_path = DELIVERIES / f"{order_id}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in out_dir.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(out_dir).as_posix())
    return {
        "ok": True,
        "order_id": order_id,
        "tool_name": tool_name,
        "zip_path": str(zip_path),
        "zip_name": zip_path.name,
        "assembled_dir": str(out_dir),
        "module_count": len(module_entries),
        "manifest": manifest,
    }
