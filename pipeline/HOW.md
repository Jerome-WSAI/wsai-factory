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
| Chatbot UI (Vercel) | `chatbot/` — sync stock puis deploy; query `POST /api/query` lit `chatbot/stock` verbatim |
| Cloud agents (API) | `python tools/create_cloud_agent.py --stage all --repo-url <url> --starting-ref main --model-id grok-4.5 --auto-create-pr no` |
| Handoff (Render) | `POST https://wsai-factory-handoff.onrender.com/handoff` — Bearer `WSAI_FACTORY_WEBHOOK_KEY` → Cursor agent run |

## Handoff (Render)

| item | value |
|------|-------|
| Service | `wsai-factory-handoff` (workspace WSAI2, plan `pro_ultra`, region frankfurt) |
| Dashboard | https://dashboard.render.com/web/srv-d9hv3lg4n6ts73bjkgbg |
| Health | `GET /health` |
| Handoff | `POST /handoff` JSON = `advance_stage` payload |
| Code | `handoff/server.py` (stdlib only) |
| Blueprint | `render.yaml` |
| Wire local | `python tools/advance_stage.py --job-id <id> --to-stage docs --webhook-url https://wsai-factory-handoff.onrender.com/handoff --git-commit no --git-push no` |

Env on Render (secrets): `WSAI_FACTORY_WEBHOOK_KEY`, `CURSOR_API_KEY`, `FACTORY_AGENT_*`.

## Chatbot (Vercel)

| item | path / command |
|------|----------------|
| Production UI | https://wsai-factory-chatbot.vercel.app |
| UI + API | `chatbot/app/page.tsx`, `chatbot/app/api/query/route.ts` |
| Stock sync | `python tools/sync_chatbot_stock.py --source pipeline/stock --destination chatbot/stock` |
| Local | `cd chatbot && npm run sync-stock && npm run dev` |
| Deploy | Vercel project `wsai-factory-chatbot` (team WSAI), root = `chatbot` |

Rule: responses contain only files present under stock; no generated code.

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
- Next.js App Router (chatbot pin next@16.2.11, published 2026-07-21): https://nextjs.org/docs/app
- React (chatbot pin react@19.2.4): https://react.dev/
- Vercel deployments: https://vercel.com/docs/deployments
- Python pathlib: https://docs.python.org/3/library/pathlib.html
- Python urllib.request: https://docs.python.org/3/library/urllib.request.html
- Python argparse: https://docs.python.org/3/library/argparse.html
- Python json: https://docs.python.org/3/library/json.html
- Python ast: https://docs.python.org/3/library/ast.html
- Python http.server (local stock serve): https://docs.python.org/3/library/http.server.html
- Production chatbot UI: https://wsai-factory-chatbot.vercel.app
- Cloud Agents API: https://cursor.com/docs/cloud-agent/api/endpoints
- Cursor API keys: https://cursor.com/dashboard/api
- Render web services: https://render.com/docs/web-services
- Handoff production: https://wsai-factory-handoff.onrender.com/health
