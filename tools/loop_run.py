"""Temporary verify-loop run lifecycle: init, hooks install, bump, finalize, cleanup."""

from __future__ import annotations

import argparse
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
CURSOR_DIR = REPO_ROOT / ".cursor"
LOOP_ROOT = CURSOR_DIR / "loop-runs"
HOOKS_JSON = CURSOR_DIR / "hooks.json"
HOOKS_BACKUP = CURSOR_DIR / "hooks.json.verify-loop.bak"
HOOKS_DIR = CURSOR_DIR / "hooks"
ACTIVE_FILE = LOOP_ROOT / "ACTIVE"


class LoopError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(data), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise LoopError("missing_json", f"missing file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise LoopError("bad_json", f"root must be object: {path}")
    return data


def run_dir(run_id: str) -> Path:
    return LOOP_ROOT / run_id


def require_run(run_id: str) -> Path:
    path = run_dir(run_id)
    if not path.is_dir():
        raise LoopError("missing_run", f"run directory missing: {path}")
    return path


def cmd_init(demand: str) -> None:
    if demand.strip() == "":
        raise LoopError("empty_demand", "demand must be non-empty")
    LOOP_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    path = run_dir(run_id)
    path.mkdir(parents=True, exist_ok=False)
    meta = {
        "run_id": run_id,
        "demand": demand,
        "created_at": utc_now_iso(),
        "iteration": 1,
        "status": "active",
    }
    write_json(path / "meta.json", meta)
    (path / "PLAN.md").write_text(
        f"# PLAN\n\n## Objectif\n\n{demand}\n\n"
        "## Etapes\n\n(sections a completer par l agent verify-loop)\n\n"
        "## Pourquoi\n\n(sections a completer par l agent verify-loop)\n\n"
        "## Preuves attendues\n\n(sections a completer par l agent verify-loop)\n\n"
        "## Criteres demande accomplie\n\n(sections a completer par l agent verify-loop)\n",
        encoding="utf-8",
    )
    (path / "EVIDENCE.md").write_text("# EVIDENCE\n\n", encoding="utf-8")
    (path / "prompts").mkdir(parents=True, exist_ok=True)
    for name, body in {
        "docs-official.md": (
            "Controle lecture seule. Verifie docs OFFICIELLES (URL vendor, version, date). "
            "Interdit inventer. Retour: VERDICT/PREUVES/MANQUES."
        ),
        "anti-fake.md": (
            "Controle lecture seule. Cherche fake/mock/placeholder/stub/TODO trompeur. "
            "Preuves path:line. Retour: VERDICT/PREUVES/MANQUES."
        ),
        "charte-qualite.md": (
            "Controle lecture seule vs rules.mdc et chartes repo. "
            "Retour: VERDICT/PREUVES/MANQUES."
        ),
        "essai-reel-a.md": (
            "N'utilise pas la relecture du code comme preuve. Execute vraiment l'outil. "
            "Retour: VERDICT/ESSAIS/PREUVE_DEMANDE_ACCOMPLIE."
        ),
        "essai-reel-b.md": (
            "Second essai independent. Execute vraiment (autre angle/commande). "
            "Retour: VERDICT/ESSAIS/PREUVE_DEMANDE_ACCOMPLIE."
        ),
    }.items():
        (path / "prompts" / name).write_text(body + "\n", encoding="utf-8")
    ACTIVE_FILE.write_text(run_id + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "run_id": run_id,
                "run_dir": str(path),
                "active_file": str(ACTIVE_FILE),
            },
            ensure_ascii=False,
        )
    )


def stop_hook_script() -> str:
    return """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
active = repo / ".cursor" / "loop-runs" / "ACTIVE"
if not active.is_file():
    print("{}")
    sys.exit(0)
run_id = active.read_text(encoding="utf-8").strip()
if run_id == "":
    print("{}")
    sys.exit(0)
validation = repo / ".cursor" / "loop-runs" / run_id / "validation.json"
if validation.is_file():
    data = json.loads(validation.read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("status") == "pass":
        print("{}")
        sys.exit(0)
msg = (
    f"verify-loop ACTIVE run_id={run_id}. validation PASS manquant. "
    "Reprendre la boucle: Batch A (docs-official + anti-fake + charte-qualite) "
    "et Batch B (2 essais reels) en parallele (2+ subagents, modele grok/auto). "
    "Interdit fake/placeholder. Quand PASS: finalize puis cleanup, puis parler a l'utilisateur."
)
print(json.dumps({"followup_message": msg}))
"""


def cmd_install_hooks(run_id: str) -> None:
    require_run(run_id)
    if not ACTIVE_FILE.is_file() or ACTIVE_FILE.read_text(encoding="utf-8").strip() != run_id:
        raise LoopError("active_mismatch", "ACTIVE run_id does not match")
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    hook_path = HOOKS_DIR / f"verify-loop-stop-{run_id}.py"
    hook_path.write_text(stop_hook_script(), encoding="utf-8")
    existing: dict[str, Any]
    if HOOKS_JSON.is_file():
        if not HOOKS_BACKUP.is_file():
            shutil.copy2(HOOKS_JSON, HOOKS_BACKUP)
        existing = read_json(HOOKS_JSON)
    else:
        existing = {"version": 1, "hooks": {}}
    if "version" not in existing:
        existing["version"] = 1
    hooks = existing.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        existing["hooks"] = hooks
    stop_list = hooks.get("stop")
    if not isinstance(stop_list, list):
        stop_list = []
        hooks["stop"] = stop_list
    entry = {
        "command": f"python .cursor/hooks/verify-loop-stop-{run_id}.py",
        "loop_limit": 8,
    }
    # avoid duplicate for same run
    stop_list[:] = [
        item
        for item in stop_list
        if not (
            isinstance(item, dict)
            and str(item.get("command", "")).endswith(f"verify-loop-stop-{run_id}.py")
        )
    ]
    stop_list.append(entry)
    write_json(HOOKS_JSON, existing)
    print(
        json.dumps(
            {
                "ok": True,
                "hooks_json": str(HOOKS_JSON),
                "hook_script": str(hook_path),
                "backup": str(HOOKS_BACKUP) if HOOKS_BACKUP.is_file() else "",
            },
            ensure_ascii=False,
        )
    )


def cmd_bump(run_id: str) -> None:
    path = require_run(run_id)
    meta = read_json(path / "meta.json")
    iteration = meta.get("iteration")
    if not isinstance(iteration, int):
        raise LoopError("bad_iteration", "meta.iteration must be int")
    meta["iteration"] = iteration + 1
    meta["updated_at"] = utc_now_iso()
    write_json(path / "meta.json", meta)
    print(json.dumps({"ok": True, "iteration": meta["iteration"]}, ensure_ascii=False))


def cmd_finalize(run_id: str) -> None:
    path = require_run(run_id)
    validation = {
        "status": "pass",
        "run_id": run_id,
        "finalized_at": utc_now_iso(),
    }
    write_json(path / "validation.json", validation)
    meta = read_json(path / "meta.json")
    meta["status"] = "passed"
    meta["updated_at"] = utc_now_iso()
    write_json(path / "meta.json", meta)
    print(json.dumps({"ok": True, "validation": validation}, ensure_ascii=False))


def cmd_cleanup(run_id: str) -> None:
    path = run_dir(run_id)
    # remove hook script
    hook_path = HOOKS_DIR / f"verify-loop-stop-{run_id}.py"
    if hook_path.is_file():
        hook_path.unlink()
    # restore or rewrite hooks.json without this entry
    if HOOKS_BACKUP.is_file():
        shutil.copy2(HOOKS_BACKUP, HOOKS_JSON)
        HOOKS_BACKUP.unlink()
    elif HOOKS_JSON.is_file():
        data = read_json(HOOKS_JSON)
        hooks = data.get("hooks")
        if isinstance(hooks, dict):
            stop_list = hooks.get("stop")
            if isinstance(stop_list, list):
                hooks["stop"] = [
                    item
                    for item in stop_list
                    if not (
                        isinstance(item, dict)
                        and str(item.get("command", "")).endswith(
                            f"verify-loop-stop-{run_id}.py"
                        )
                    )
                ]
                if len(hooks["stop"]) == 0:
                    del hooks["stop"]
        write_json(HOOKS_JSON, data)
        # if hooks empty except version, remove file to avoid empty permanent hooks
        hooks_obj = data.get("hooks")
        if isinstance(hooks_obj, dict) and len(hooks_obj) == 0:
            HOOKS_JSON.unlink()
    if ACTIVE_FILE.is_file() and ACTIVE_FILE.read_text(encoding="utf-8").strip() == run_id:
        ACTIVE_FILE.unlink()
    if path.is_dir():
        shutil.rmtree(path)
    print(json.dumps({"ok": True, "cleaned_run_id": run_id}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="verify-loop temporary run manager")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--demand", required=True)

    p_hooks = sub.add_parser("install-hooks")
    p_hooks.add_argument("--run-id", required=True)

    p_bump = sub.add_parser("bump")
    p_bump.add_argument("--run-id", required=True)

    p_fin = sub.add_parser("finalize")
    p_fin.add_argument("--run-id", required=True)

    p_clean = sub.add_parser("cleanup")
    p_clean.add_argument("--run-id", required=True)

    args = parser.parse_args()
    if args.command == "init":
        cmd_init(args.demand)
        return
    if args.command == "install-hooks":
        cmd_install_hooks(args.run_id)
        return
    if args.command == "bump":
        cmd_bump(args.run_id)
        return
    if args.command == "finalize":
        cmd_finalize(args.run_id)
        return
    if args.command == "cleanup":
        cmd_cleanup(args.run_id)
        return
    raise LoopError("unknown_command", f"unknown command {args.command!r}")


if __name__ == "__main__":
    main()
