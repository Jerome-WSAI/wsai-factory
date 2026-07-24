"""Resolve official docs for inventory dependencies (local stage). Fail if unresolved."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
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


def fetch_json(url: str) -> dict[str, object]:
    # Official urllib: https://docs.python.org/3/library/urllib.request.html
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "wsai-factory-docs/1.0"},
        method="GET",
    )
    attempts = 3
    last_error: BaseException | None = None
    body = ""
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.getcode()
                if status < 200 or status >= 300:
                    raise PipelineError(
                        "http_bad_status",
                        f"GET {url} returned HTTP {status}",
                        "docs",
                    )
                body = response.read().decode("utf-8")
            last_error = None
            break
        except urllib.error.URLError as exc:
            last_error = exc
            print(
                json.dumps(
                    {
                        "level": "warning",
                        "event": "http_retry",
                        "url": url,
                        "attempt": attempt,
                        "attempts": attempts,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    if last_error is not None:
        raise PipelineError(
            "http_failed",
            f"GET {url} failed after {attempts} attempts: {last_error}",
            "docs",
        ) from last_error
    data = json.loads(body)
    if not isinstance(data, dict):
        raise PipelineError(
            "http_not_object",
            f"GET {url} did not return a JSON object",
            "docs",
        )
    return cast(dict[str, object], data)


def resolve_npm(name: str, version: str) -> dict[str, str]:
    # Official npm registry API: https://docs.npmjs.com/about-the-public-npm-registry
    url = f"https://registry.npmjs.org/{urllib.parse.quote(name)}"
    data = fetch_json(url)
    homepage = data.get("homepage")
    repository = data.get("repository")
    official = ""
    if isinstance(homepage, str) and homepage.startswith("http"):
        official = homepage
    elif isinstance(repository, dict):
        repo_url = repository.get("url")
        if isinstance(repo_url, str) and repo_url != "":
            official = repo_url.replace("git+", "").replace("ssh://git@", "https://")
            if official.startswith("git@"):
                official = official.replace(":", "/").replace("git@", "https://")
            if official.endswith(".git"):
                official = official[: -len(".git")]
    if official == "":
        raise PipelineError(
            "npm_no_official_url",
            f"npm package {name!r} has no homepage/repository URL in registry metadata",
            "docs",
        )
    fetched_at = utc_now_iso()
    return {
        "name": name,
        "ecosystem": "npm",
        "version": version,
        "url": official,
        "registry_url": url,
        "fetched_at": fetched_at,
        "source": "registry.npmjs.org",
        "doc_status": "resolved",
    }


def run_docs(job_id: str) -> None:
    state = validate_state(read_json_object(state_path_for_job(job_id), "docs"))
    if state["stage"] not in {"stripped", "docs"}:
        raise PipelineError(
            "bad_stage_for_docs",
            f"docs requires stage stripped|docs, got {state['stage']!r}",
            state["stage"],
        )
    inventory = read_json_object(Path(state["inventory_path"]), "docs")
    deps_raw = inventory.get("dependencies")
    if not isinstance(deps_raw, list):
        raise PipelineError(
            "bad_inventory_deps",
            "inventory.dependencies must be a list",
            "docs",
        )
    docs_root = Path(state["paths"]["docs"])
    official_root = docs_root / "official_docs"
    official_root.mkdir(parents=True, exist_ok=True)
    resolved: list[dict[str, str]] = []
    try:
        for item in deps_raw:
            if not isinstance(item, dict):
                raise PipelineError(
                    "bad_dep_item",
                    "dependency entry must be object",
                    "docs",
                )
            dep = cast(dict[str, object], item)
            name = require_string(dep, "name", "docs")
            ecosystem = require_string(dep, "ecosystem", "docs")
            version = require_string(dep, "version", "docs")
            if name.startswith("__manifest__:"):
                # Expand later; mark unresolved so align cannot silently proceed
                entry = {
                    "name": name,
                    "ecosystem": ecosystem,
                    "version": version,
                    "url": "",
                    "registry_url": "",
                    "fetched_at": utc_now_iso(),
                    "source": "manifest-pointer",
                    "doc_status": "unresolved",
                }
                resolved.append(entry)
                continue
            if ecosystem != "npm":
                raise PipelineError(
                    "unsupported_ecosystem",
                    f"local docs resolver supports npm only for now; got {ecosystem!r} for {name}",
                    "docs",
                )
            meta = resolve_npm(name, version)
            dep_dir = official_root / "npm" / name.replace("/", "__")
            dep_dir.mkdir(parents=True, exist_ok=True)
            write_json(dep_dir / "meta.json", meta)
            (dep_dir / "instructions.md").write_text(
                f"# {name}\n\n"
                f"- ecosystem: npm\n"
                f"- version_range: {version}\n"
                f"- official_url: {meta['url']}\n"
                f"- registry: {meta['registry_url']}\n"
                f"- fetched_at: {meta['fetched_at']}\n"
                f"- source: {meta['source']}\n",
                encoding="utf-8",
            )
            resolved.append(meta)
        unresolved = [d for d in resolved if d["doc_status"] != "resolved"]
        manifest = {
            "job_id": job_id,
            "created_at": utc_now_iso(),
            "dependencies": resolved,
        }
        write_json(Path(state["docs_manifest_path"]), manifest)
        if len(unresolved) > 0:
            names = ", ".join(d["name"] for d in unresolved)
            raise PipelineError(
                "unresolved_docs",
                f"unresolved official docs for: {names}",
                "docs",
            )
        new_state = with_stage(state, "docs", "ok")
        write_json(state_path_for_job(job_id), new_state)
    except PipelineError as exc:
        failed = with_failed(state, exc.code, exc.message, exc.at_stage)
        write_json(state_path_for_job(job_id), failed)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Local official docs resolver")
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    run_docs(args.job_id)
    print(json.dumps({"ok": True, "job_id": args.job_id, "stage": "docs"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
