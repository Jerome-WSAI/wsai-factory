"""Resolve official docs for inventory dependencies (local stage). Fail if unresolved."""

from __future__ import annotations

import argparse
import json
import re
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


GITHUB_REPO_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/#?]+)(?:\.git)?(?:/[^#?]*)?(?:[?#].*)?$",
    re.IGNORECASE,
)


def http_get_text(url: str, accept: str) -> tuple[int, str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "wsai-factory-docs/1.0",
        },
        method="GET",
    )
    attempts = 3
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.getcode()
                content_type = response.headers.get_content_type()
                if content_type is None:
                    content_type = ""
                raw = response.read()
                try:
                    body = raw.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise PipelineError(
                        "http_not_utf8",
                        f"GET {url} body is not UTF-8",
                        "docs",
                    ) from exc
                return status, body, content_type
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                body = raw.decode("utf-8")
            except UnicodeDecodeError as decode_exc:
                raise PipelineError(
                    "http_not_utf8",
                    f"GET {url} error body is not UTF-8 (HTTP {exc.code})",
                    "docs",
                ) from decode_exc
            content_type = exc.headers.get_content_type() if exc.headers else ""
            if content_type is None:
                content_type = ""
            # Non-2xx is a completed response (e.g. 404 README candidate).
            return exc.code, body, content_type
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
    raise PipelineError(
        "http_failed",
        f"GET {url} failed after {attempts} attempts: {last_error}",
        "docs",
    )


def fetch_json(url: str) -> dict[str, object]:
    status, body, _content_type = http_get_text(url, "application/json")
    if status < 200 or status >= 300:
        raise PipelineError(
            "http_bad_status",
            f"GET {url} returned HTTP {status}",
            "docs",
        )
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise PipelineError(
            "http_bad_json",
            f"GET {url} returned non-JSON body: {exc}",
            "docs",
        ) from exc
    if not isinstance(data, dict):
        raise PipelineError(
            "http_not_object",
            f"GET {url} did not return a JSON object",
            "docs",
        )
    return cast(dict[str, object], data)


def github_raw_readme_candidates(official_url: str) -> list[str]:
    match = GITHUB_REPO_RE.match(official_url.strip())
    if match is None:
        return []
    owner = match.group("owner")
    repo = match.group("repo")
    bases = [
        f"https://raw.githubusercontent.com/{owner}/{repo}/main",
        f"https://raw.githubusercontent.com/{owner}/{repo}/master",
    ]
    names = ["README.md", "readme.md", "Readme.md", "README.markdown"]
    out: list[str] = []
    for base in bases:
        for name in names:
            out.append(f"{base}/{name}")
    return out


def fetch_official_instructions(name: str, official_url: str) -> tuple[str, str]:
    """Return (instructions_markdown, content_source_url). Fail loud — never invent body."""
    candidates = github_raw_readme_candidates(official_url)
    if len(candidates) == 0:
        raise PipelineError(
            "docs_not_fetchable",
            f"package {name!r} official_url is not a github.com repo "
            f"(cannot fetch README without inventing): {official_url}",
            "docs",
        )
    last_detail = ""
    for candidate in candidates:
        try:
            status, body, content_type = http_get_text(candidate, "text/plain")
        except PipelineError as exc:
            last_detail = exc.message
            continue
        if status < 200 or status >= 300:
            last_detail = f"HTTP {status} for {candidate}"
            continue
        text = body.strip()
        if len(text) < 80:
            last_detail = f"too short body ({len(text)} chars) at {candidate}"
            continue
        if "text/html" in content_type.lower():
            last_detail = f"HTML content-type at {candidate}"
            continue
        header = (
            f"# {name}\n\n"
            f"<!-- wsai-factory: fetched official excerpt; do not invent -->\n"
            f"- official_url: {official_url}\n"
            f"- content_source: {candidate}\n"
            f"- content_type: {content_type or 'unknown'}\n"
            f"- fetched_at: {utc_now_iso()}\n\n"
            f"---\n\n"
        )
        return header + text, candidate
    raise PipelineError(
        "docs_fetch_failed",
        f"could not fetch official README for {name!r} from {official_url}; "
        f"last={last_detail}",
        "docs",
    )


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
            instructions, content_source = fetch_official_instructions(name, meta["url"])
            meta = {**meta, "content_source": content_source}
            dep_dir = official_root / "npm" / name.replace("/", "__")
            dep_dir.mkdir(parents=True, exist_ok=True)
            write_json(dep_dir / "meta.json", meta)
            (dep_dir / "instructions.md").write_text(instructions, encoding="utf-8")
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
