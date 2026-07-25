"""Proof: assemble 10 random stock tools → unzip → smoke open checks.

Usage:
  python tools/proof_factory_x10.py --count 10 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "factory_backend"))
sys.path.insert(0, str(REPO / "tools"))

from assemble import assemble_order  # noqa: E402
from brain import list_stock_catalog  # noqa: E402
from pipeline_lib import PIPELINE_ROOT  # noqa: E402


def _remove_tree(path: Path) -> None:
    """Remove a directory tree; retry on Windows file locks."""
    if not path.exists():
        return
    last_error: Exception | None = None
    for _attempt in range(8):
        try:
            shutil.rmtree(path)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.15)
    raise RuntimeError(
        f"cannot remove proof dir {path}: {last_error}"
    ) from last_error


def smoke_open(zip_path: Path, extract_dir: Path) -> dict[str, object]:
    _remove_tree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(extract_dir)
    index = extract_dir / "index.html"
    manifest = extract_dir / "assembly_manifest.json"
    modules_dir = extract_dir / "modules"
    if not index.is_file():
        raise RuntimeError(f"missing index.html in {extract_dir}")
    if not manifest.is_file():
        raise RuntimeError(f"missing assembly_manifest.json in {extract_dir}")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    html = index.read_text(encoding="utf-8")
    if "{{TOOL_NAME}}" in html:
        raise RuntimeError("template placeholder not replaced")
    module_files = [p for p in modules_dir.rglob("*") if p.is_file()]
    if len(module_files) == 0:
        raise RuntimeError("no module files after unzip")
    return {
        "index_bytes": index.stat().st_size,
        "module_files": len(module_files),
        "tool_name": data.get("tool_name"),
        "order_id": data.get("order_id"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", required=True, type=int)
    parser.add_argument("--seed", required=True, type=int)
    args = parser.parse_args()
    if args.count < 1:
        raise SystemExit("count must be >= 1")
    catalog = list_stock_catalog()
    if len(catalog) == 0:
        raise SystemExit("stock catalog empty — ingest projects first")
    rng = random.Random(args.seed)
    picks = [catalog[rng.randrange(0, len(catalog))] for _ in range(args.count)]
    proof_root = PIPELINE_ROOT / "proof_x10" / f"seed-{args.seed}"
    _remove_tree(proof_root)
    proof_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    for index, ref in enumerate(picks, start=1):
        order_id = f"proof-{args.seed}-{index:02d}"
        tool_name = f"ProofTool-{index}-{ref['module']}"
        brief = f"auto proof {index}/{args.count} using {ref['job_id']}/{ref['module']}"
        assembled = assemble_order(
            order_id,
            tool_name,
            brief,
            [{"job_id": ref["job_id"], "module": ref["module"]}],
        )
        zip_path = Path(str(assembled["zip_path"]))
        smoke = smoke_open(zip_path, proof_root / order_id)
        results.append(
            {
                "n": index,
                "job_id": ref["job_id"],
                "module": ref["module"],
                "zip": zip_path.name,
                "smoke": smoke,
                "ok": True,
            }
        )
        print(json.dumps({"event": "proof_ok", **results[-1]}, ensure_ascii=False))
    summary = {
        "ok": True,
        "count": len(results),
        "seed": args.seed,
        "all_passed": all(r["ok"] is True for r in results),
        "results": results,
    }
    (proof_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["all_passed"] is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
