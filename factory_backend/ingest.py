"""Dynamic ingest: unpack upload → strip→docs→align→stock using tools/."""

from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

from errors import FactoryError

_REPO = Path(__file__).resolve().parents[1]
_TOOLS = _REPO / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from pipeline_automate import run_slug  # noqa: E402
from pipeline_lib import INBOX_ROOT, assert_slug  # noqa: E402


def ingest_zip_bytes(slug: str, zip_bytes: bytes, polls: int, interval_sec: float) -> dict[str, object]:
    assert_slug(slug)
    if len(zip_bytes) < 22:
        raise FactoryError("empty_zip", "zip payload too small", 400)
    target = INBOX_ROOT / slug
    if target.exists():
        raise FactoryError(
            "slug_exists",
            f"inbox slug already present: {slug}",
            409,
        )
    staging = INBOX_ROOT / f".staging-{slug}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=False)
    zip_path = staging / "upload.zip"
    zip_path.write_bytes(zip_bytes)
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(staging)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise FactoryError("bad_zip", f"invalid zip: {exc}", 400) from exc
    zip_path.unlink(missing_ok=True)
    # If zip contained a single top folder, flatten into slug dir
    children = [p for p in staging.iterdir()]
    if len(children) == 1 and children[0].is_dir():
        children[0].rename(target)
        shutil.rmtree(staging, ignore_errors=True)
    else:
        staging.rename(target)
    try:
        result = run_slug(slug, polls, interval_sec)
    except Exception as exc:
        raise FactoryError(
            "ingest_failed",
            f"pipeline failed for slug={slug}: {exc}",
            500,
        ) from exc
    return {"ok": True, **result}
