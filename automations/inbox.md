# Automation: cloud inbox ingest (Push to branch)

## Trigger
Cursor Automations: **Push to branch** on `Jerome-WSwissAI/wsai-factory` when paths under `pipeline/inbox/**` change (not `_processed`).

## Goal
Human or `tools/push_inbox.py` commits a full project into `pipeline/inbox/<slug>/`. Cloud agent processes it.

## Hard rules
1. List new/changed directories directly under `pipeline/inbox/` (ignore `_processed`, `.gitkeep`).
2. For each `<slug>`, run the strip path equivalent to local:
   - inventory then strip docs/comments (same contracts as `tools/strip_and_inventory.py`)
   - write `pipeline/jobs/<job_id>/` + `state.json` + `inventory.json`
3. Do not invent modules or docs in this stage.
4. After strip OK, either:
   - call next Automation/webhook for `to_stage=docs`, or
   - run docs stage using official sources only (same rules as `automations/docs.md`)
5. Two read-only controllers: (a) inbox files are tracked in git (b) no code invention.
6. Move/delete handled inbox from `pipeline/inbox/<slug>/` only after job artifacts exist under `pipeline/jobs/<job_id>/01-stripped/` (prefer move note in state; do not destroy history without commit).

## Output
- `pipeline/jobs/<job_id>/**`
- `state.json` stage=`stripped` or further if chain continues
- Commit + push job artifacts

## Local companion
- Drop files: copy project â†’ `pipeline/inbox/<slug>/`
- Publish to GitHub: `python tools/push_inbox.py --slug <slug> --commit yes --push yes`


