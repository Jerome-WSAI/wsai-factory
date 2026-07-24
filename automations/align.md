# Automation: align code to resolved official docs

## Trigger
Webhook/git after docs stage OK (`tools/advance_stage.py --to-stage aligned`).

## Preconditions
- `docs_manifest.json` exists
- **Zero** `doc_status=unresolved` (otherwise refuse and fail)

## Hard rules
1. Change code only to conform to resolved official instructions for listed deps.
2. Do not add features not present in `01-stripped` / aligned inputs.
3. Do not delete SPDX/license/pragma/`noqa`/`type: ignore` markers.
4. Write `03-aligned/align_report.json`: per-rule `{id, status: pass|fail, evidence}`.
5. Any fail → job `status=failed`, no silent skip.
6. Launch **2** read-only controllers (honesty / invention check; docs coverage check). They do not implement.

## Output
- `pipeline/jobs/<job_id>/03-aligned/` (full tree)
- `align_report.json`
- `state.json` updated
