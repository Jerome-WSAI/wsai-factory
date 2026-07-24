"""Stage (and optionally commit/push) pipeline/inbox/<slug>/ for Cursor Cloud Automations.

Cloud agents only see git-tracked files. Supported ingress = files in git under inbox.
Does not commit or push unless explicitly requested via flags.
"""

from __future__ import annotations

import argparse
import json
import subprocess

from pipeline_lib import INBOX_ROOT, PipelineError, REPO_ROOT, assert_slug


def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
    )


def require_ok(result: subprocess.CompletedProcess[str], code: str) -> None:
    if result.returncode != 0:
        raise PipelineError(
            code,
            f"git failed ({code}): {result.stderr.strip() or result.stdout.strip()}",
            "inbox",
        )


def push_inbox(slug: str, do_commit: bool, do_push: bool) -> dict[str, str]:
    if do_push and not do_commit:
        raise PipelineError(
            "push_requires_commit",
            "push=yes requires commit=yes",
            "inbox",
        )
    assert_slug(slug)
    slug_dir = INBOX_ROOT / slug
    if not slug_dir.is_dir():
        raise PipelineError(
            "missing_inbox_slug",
            f"inbox slug missing: {slug_dir}",
            "inbox",
        )
    files = [p for p in slug_dir.rglob("*") if p.is_file()]
    if len(files) == 0:
        raise PipelineError(
            "empty_inbox_slug",
            f"inbox slug has no files: {slug_dir}",
            "inbox",
        )
    rel = f"pipeline/inbox/{slug}"
    ignore = run_git(["check-ignore", "-q", f"{rel}/src"])
    # exit 0 = ignored; exit 1 = not ignored; other = error
    if ignore.returncode == 0:
        # check a real file
        sample = files[0]
        rel_sample = sample.relative_to(REPO_ROOT).as_posix()
        ign2 = run_git(["check-ignore", "-q", rel_sample])
        if ign2.returncode == 0:
            raise PipelineError(
                "inbox_still_ignored",
                f"path still gitignored: {rel_sample}",
                "inbox",
            )
    require_ok(run_git(["add", "-A", "--", rel]), "git_add_failed")
    status = run_git(["status", "--porcelain", "--", rel])
    require_ok(status, "git_status_failed")
    if not do_commit:
        return {
            "slug": slug,
            "rel": rel,
            "staged": "yes" if status.stdout.strip() != "" else "no",
            "commit": "none",
            "pushed": "no",
        }
    if status.stdout.strip() == "":
        cached = run_git(["ls-files", "--", rel])
        require_ok(cached, "git_ls_files_failed")
        if cached.stdout.strip() == "":
            raise PipelineError(
                "nothing_to_commit",
                f"path {rel} not staged and not tracked",
                "inbox",
            )
        return {
            "slug": slug,
            "rel": rel,
            "staged": "no",
            "commit": "unchanged",
            "pushed": "no",
        }
    msg = f"factory(inbox): drop {slug}"
    require_ok(run_git(["commit", "-m", msg]), "git_commit_failed")
    head = run_git(["rev-parse", "HEAD"])
    require_ok(head, "git_rev_parse_failed")
    sha = head.stdout.strip()
    pushed = "no"
    if do_push:
        require_ok(run_git(["push", "-u", "origin", "HEAD"]), "git_push_failed")
        pushed = "yes"
    return {
        "slug": slug,
        "rel": rel,
        "staged": "yes",
        "commit": sha,
        "pushed": pushed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage/commit/push pipeline/inbox/<slug> for GitHub Automations"
    )
    parser.add_argument("--slug", required=True)
    parser.add_argument("--commit", required=True, choices=["yes", "no"])
    parser.add_argument("--push", required=True, choices=["yes", "no"])
    args = parser.parse_args()
    out = push_inbox(args.slug, args.commit == "yes", args.push == "yes")
    print(json.dumps({"ok": True, **out}, ensure_ascii=False))


if __name__ == "__main__":
    main()
