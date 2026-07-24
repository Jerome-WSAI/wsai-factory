# WSAI-Factory pipeline

## Goal

Ingest a full project → code-only + official docs → align → modules → stock.

## Best cloud ingress (chosen)

**Option A — put the project in GitHub under `pipeline/inbox/<slug>/` then push.**

- Cursor Cloud Automations clone the repo; they cannot see `E:\`.
- Trigger: **Push to branch** on `pipeline/inbox/**` (see `automations/inbox.md`).
- Helper: `python tools/push_inbox.py --slug <slug> --commit yes --push yes`

Rejected:
- **B webhook+zip**: invents transport; webhook is a signal, not a filesystem.
- **C GitHub Release**: no Automations Release trigger in Cursor.

Webhook remains for **stage handoff metadata** after files are already in git (`tools/advance_stage.py`).

## Runtime

| Layer | Role |
|-------|------|
| Local worker | `python tools/worker_start.py --worker inbox_loop --polls 2 --interval-sec 1 --loop-sleep-sec 5` |
| Local E2E | `python tools/pipeline_automate.py --slug <slug> --polls 2 --interval-sec 0.5` |
| Cloud ingest | commit inbox → push → Automation `automations/inbox.md` |
| Cloud stages | `automations/docs.md`, `align.md`, `modularize.md` |

## Stages

| stage | path | actor |
|-------|------|-------|
| inbox | `pipeline/inbox/<slug>/` (**tracked in git**) | human + `push_inbox.py` |
| strip | `pipeline/jobs/<job_id>/01-stripped/` | local watch / cloud inbox automation |
| docs | `.../02-docs/` | `stage_docs_local.py` or Automation docs |
| align | `.../03-aligned/` | `stage_align_local.py` or Automation align |
| stock | `pipeline/stock/<job_id>/<module>/` | `apply_modules_stock.py` |

## Stack URLs

- Cursor Automations: https://cursor.com/docs/cloud-agent/automations
- npm registry: https://docs.npmjs.com/about-the-public-npm-registry
- GitHub webhooks: https://docs.github.com/en/webhooks
