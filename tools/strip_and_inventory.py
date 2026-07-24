"""Inventory manifests/imports, then strip project prose docs and noise comments.

Order is mandatory: inventory first, then delete docs by path globs (no content read),
then comment strip with allowlist. Fail loud if no code or no parseable inventory.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Iterable

from pipeline_lib import (
    JOBS_ROOT,
    PipelineError,
    assert_slug,
    create_initial_state,
    new_job_id,
    state_path_for_job,
    utc_now_iso,
    with_failed,
    with_stage,
    write_json,
)


MANIFEST_NAMES = frozenset(
    {
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "requirements.txt",
        "pyproject.toml",
        "Pipfile",
        "Pipfile.lock",
        "Cargo.toml",
        "Cargo.lock",
        "go.mod",
        "go.sum",
        "composer.json",
        "Gemfile",
        "Gemfile.lock",
    }
)

CODE_SUFFIXES = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".rs",
        ".go",
        ".java",
        ".kt",
        ".cs",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
        ".rb",
        ".php",
        ".swift",
    }
)

DOC_SUFFIXES = frozenset({".md", ".mdx", ".rst", ".adoc", ".txt"})
DOC_DIR_NAMES = frozenset({"docs", "doc", "documentation", "wiki"})

SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        "node_modules",
        "dist",
        "build",
        "target",
        ".venv",
        "venv",
        "__pycache__",
        ".turbo",
        ".next",
    }
)

PRESERVE_COMMENT_RE = re.compile(
    r"(?i)(spdx-|copyright|license|#!/|coding[:=]|pragma|"
    r"noqa|type:\s*ignore|eslint-disable|prettier-ignore|"
    r"@ts-nocheck|@ts-ignore|fmt\.Skip)"
)

LINE_COMMENT_RE = {
    ".py": re.compile(r"^(\s*)#(?!!)(.*)"),
    ".js": re.compile(r"^(\s*)//(.*)"),
    ".jsx": re.compile(r"^(\s*)//(.*)"),
    ".ts": re.compile(r"^(\s*)//(.*)"),
    ".tsx": re.compile(r"^(\s*)//(.*)"),
    ".mjs": re.compile(r"^(\s*)//(.*)"),
    ".cjs": re.compile(r"^(\s*)//(.*)"),
    ".rs": re.compile(r"^(\s*)//(.*)"),
    ".go": re.compile(r"^(\s*)//(.*)"),
    ".java": re.compile(r"^(\s*)//(.*)"),
    ".cs": re.compile(r"^(\s*)//(.*)"),
    ".c": re.compile(r"^(\s*)//(.*)"),
    ".cpp": re.compile(r"^(\s*)//(.*)"),
    ".h": re.compile(r"^(\s*)//(.*)"),
    ".hpp": re.compile(r"^(\s*)//(.*)"),
}


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        yield path


def collect_inventory(root: Path) -> dict[str, object]:
    manifests: list[str] = []
    code_files: list[str] = []
    dependencies: list[dict[str, str]] = []
    languages: set[str] = set()

    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        if path.name in MANIFEST_NAMES:
            manifests.append(rel)
            dependencies.extend(parse_manifest_deps(path))
        suffix = path.suffix.lower()
        if suffix in CODE_SUFFIXES:
            code_files.append(rel)
            languages.add(suffix.lstrip("."))

    if len(code_files) == 0:
        raise PipelineError(
            "no_code",
            f"no code files under {root}",
            "inventory",
        )
    if len(manifests) == 0 and len(dependencies) == 0:
        raise PipelineError(
            "no_inventory",
            "no manifests/locks/parseable deps; cannot resolve official docs later",
            "inventory",
        )

    return {
        "languages": sorted(languages),
        "manifests": sorted(manifests),
        "dependencies": dependencies,
        "code_files": sorted(code_files),
    }


def parse_manifest_deps(path: Path) -> list[dict[str, str]]:
    name = path.name
    out: list[dict[str, str]] = []
    if name == "package.json":
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise PipelineError(
                "bad_package_json",
                f"package.json JSON decode failed at {path}: {exc}",
                "inventory",
            ) from exc
        if not isinstance(data, dict):
            raise PipelineError(
                "bad_package_json",
                f"package.json root must be object: {path}",
                "inventory",
            )
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            block = data.get(section)
            if block is None:
                continue
            if not isinstance(block, dict):
                raise PipelineError(
                    "bad_package_json_section",
                    f"package.json section {section!r} must be object at {path}",
                    "inventory",
                )
            for dep_name, version in block.items():
                if not isinstance(dep_name, str) or dep_name == "":
                    raise PipelineError(
                        "bad_dep_name",
                        f"dependency name must be non-empty string in {section} at {path}",
                        "inventory",
                    )
                if not isinstance(version, str) or version == "":
                    raise PipelineError(
                        "bad_dep_version",
                        f"dependency {dep_name!r} version must be non-empty string at {path}",
                        "inventory",
                    )
                out.append(
                    {
                        "name": dep_name,
                        "ecosystem": "npm",
                        "version": version,
                        "source": "manifest",
                        "doc_status": "pending",
                    }
                )
        return out
    if name in {"requirements.txt", "pyproject.toml", "Pipfile"}:
        out.append(
            {
                "name": f"__manifest__:{path.name}",
                "ecosystem": "pypi",
                "version": "manifest-only",
                "source": "manifest",
                "doc_status": "pending",
            }
        )
        return out
    if name == "Cargo.toml":
        out.append(
            {
                "name": f"__manifest__:{path.name}",
                "ecosystem": "crates",
                "version": "manifest-only",
                "source": "manifest",
                "doc_status": "pending",
            }
        )
        return out
    if name == "go.mod":
        out.append(
            {
                "name": f"__manifest__:{path.name}",
                "ecosystem": "go",
                "version": "manifest-only",
                "source": "manifest",
                "doc_status": "pending",
            }
        )
        return out
    return out


def should_delete_doc(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    if any(part.lower() in DOC_DIR_NAMES for part in rel_parts[:-1]):
        return True
    if path.name.upper() in {"README.MD", "README.MDX", "CHANGELOG.MD", "HISTORY.MD"}:
        return True
    if path.name.lower() in {"readme", "changelog", "license", "licence"}:
        # Keep LICENSE text files (legal). Delete README-like without suffix handled above.
        if path.name.lower() in {"license", "licence"}:
            return False
    if path.suffix.lower() in DOC_SUFFIXES:
        if path.name.upper().startswith("LICENSE"):
            return False
        if path.name in MANIFEST_NAMES:
            return False
        return True
    return False


def strip_line_comments(text: str, suffix: str) -> tuple[str, list[str]]:
    pattern = LINE_COMMENT_RE.get(suffix)
    if pattern is None:
        return text, []
    preserved: list[str] = []
    lines_out: list[str] = []
    for line in text.splitlines(keepends=True):
        newline = ""
        body = line
        if line.endswith("\r\n"):
            newline = "\r\n"
            body = line[:-2]
        elif line.endswith("\n"):
            newline = "\n"
            body = line[:-1]
        match = pattern.match(body)
        if match is None:
            lines_out.append(line)
            continue
        full_comment = match.group(0)
        if PRESERVE_COMMENT_RE.search(full_comment):
            preserved.append(full_comment.strip())
            lines_out.append(line)
            continue
        # Drop pure comment lines; keep code if comment is trailing by not matching ^ only.
        # This pattern is start-of-line only → full-line comments removed.
        continue
    return "".join(lines_out), preserved


def delete_docs_and_strip_comments(root: Path) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    preserved_markers: list[str] = []
    for path in list(iter_files(root)):
        if should_delete_doc(path, root):
            removed.append(path.relative_to(root).as_posix())
            path.unlink()
            continue
        suffix = path.suffix.lower()
        if suffix not in LINE_COMMENT_RE:
            continue
        original = path.read_text(encoding="utf-8", errors="strict")
        stripped, preserved = strip_line_comments(original, suffix)
        preserved_markers.extend(preserved)
        if stripped != original:
            path.write_text(stripped, encoding="utf-8")
    # Remove empty doc dirs
    for dirpath in sorted(root.rglob("*"), reverse=True):
        if not dirpath.is_dir():
            continue
        if dirpath.name.lower() in DOC_DIR_NAMES:
            try:
                next(dirpath.iterdir())
            except StopIteration:
                dirpath.rmdir()
                removed.append(dirpath.relative_to(root).as_posix() + "/")
    return removed, preserved_markers


def run_strip_job(source_dir: Path, slug: str) -> Path:
    assert_slug(slug)
    if not source_dir.is_dir():
        raise PipelineError(
            "missing_source",
            f"source directory missing: {source_dir}",
            "inbox",
        )
    job_id = new_job_id(slug)
    state = create_initial_state(job_id, slug)
    job_dir = JOBS_ROOT / job_id
    stripped = job_dir / "01-stripped"
    job_dir.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source_dir, stripped)
    state = with_stage(state, "inbox", "running")
    write_json(state_path_for_job(job_id), state)

    try:
        inv_core = collect_inventory(stripped)
        removed, preserved = delete_docs_and_strip_comments(stripped)
        inventory = {
            "job_id": job_id,
            "created_at": utc_now_iso(),
            "root": str(stripped).replace("\\", "/"),
            "languages": inv_core["languages"],
            "manifests": inv_core["manifests"],
            "dependencies": inv_core["dependencies"],
            "code_files": inv_core["code_files"],
            "removed_paths": removed,
            "preserved_comment_markers": sorted(set(preserved)),
        }
        write_json(job_dir / "inventory.json", inventory)
        state = with_stage(state, "stripped", "ok")
        write_json(state_path_for_job(job_id), state)
        return job_dir
    except PipelineError as exc:
        failed_state = with_failed(state, exc.code, exc.message, exc.at_stage)
        write_json(state_path_for_job(job_id), failed_state)
        failed_dir = Path(failed_state["paths"]["failed"])
        if job_dir.exists() and not failed_dir.exists():
            shutil.move(str(job_dir), str(failed_dir))
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory then strip a project folder")
    parser.add_argument("--source", required=True, help="Absolute path to project folder")
    parser.add_argument("--slug", required=True, help="Job slug (folder name)")
    args = parser.parse_args()
    source = Path(args.source)
    job_dir = run_strip_job(source, args.slug)
    print(json.dumps({"ok": True, "job_dir": str(job_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
