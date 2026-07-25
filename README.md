# wsai-factory

Private orchestration factory: ingest projects → strip → official docs → align → modules → stock.

## How it works

See `pipeline/HOW.md`.

## First 5 minutes

```text
# 1) Create a NEW inbox slug (do not reuse a processed one)
mkdir pipeline\inbox\my-slug\src
# put package.json + source under pipeline/inbox/my-slug/

# 2) Local full pipeline → stock
python tools/pipeline_automate.py --slug my-slug --polls 2 --interval-sec 0.5

# 3) Chatbot UI (server actions read chatbot/stock; no API secret needed in browser)
cd chatbot
npm run sync-stock
npm run dev
# open http://localhost:3000 — try query: duration
```

## Quick local

```text
# 1) Local full pipeline
python tools/pipeline_automate.py --slug <slug> --polls 2 --interval-sec 0.5

# 2) Local inbox worker (loop)
python tools/worker_start.py --worker inbox_loop --polls 2 --interval-sec 1 --loop-sleep-sec 5

# 3) Cloud ingress: put project in pipeline/inbox/<slug>/ then
python tools/push_inbox.py --slug <slug> --commit yes --push yes
# → triggers Cursor Automation on Push (see automations/inbox.md)

# 4) Sync + deploy chatbot (stock + production)
python tools/deploy_chatbot.py --prod yes
```

### processed_collision recovery

If `pipeline_automate` fails with `[processed_collision@inbox] already processed slug exists`, the slug already lives under `pipeline/inbox/_processed/<slug>/`. Recovery:

1. Use a **new** slug directory under `pipeline/inbox/<new-slug>/`, or
2. Move/remove `pipeline/inbox/_processed/<slug>/` only if you intentionally want to re-ingest that slug, then put sources back under `pipeline/inbox/<slug>/`.

Do not re-run the same slug while it remains in `_processed/`.

### Edge matrix (expected exits / HTTP)

| Case | Expected |
|------|----------|
| `pipeline_automate` with `--polls 1` | exit `1`, `bad_debounce` (`polls must be >= 2`) |
| `pipeline_automate` on processed slug | exit `1`, `processed_collision` |
| `stock_chatbot_query.py` without `--query` | exit `2` |
| `POST /api/query` `{"query":""}` with valid secret | HTTP `404` `empty_query` |
| `POST /api/query` without `x-chatbot-secret` | HTTP `401` `unauthorized` or `secret_not_configured` |
| `POST /api/query` `{"query":"duration"}` with secret | HTTP `200`, JSON must not contain `absolute_path` |

## Chatbot API auth

- Browser UI uses **server actions** (no secret in the client).
- External `GET /api/modules` and `POST /api/query` require header `x-chatbot-secret: $CHATBOT_API_SECRET`.
- Set `CHATBOT_API_SECRET` in Vercel project env (Production) before deploy.

## Commands

| Command | Path | Role |
|---------|------|------|
| `/verify-loop` | `.cursor/commands/verify-loop.md` | Boucle docs + anti-fake + essais réels |
| `/factory-push-inbox` | `.cursor/commands/factory-push-inbox.md` | Commit/push inbox vers GitHub pour Automations |
| smoke | `python tools/chatbot_smoke.py` | Auth + path-leak + local stock probes |
| deploy | `python tools/deploy_chatbot.py --prod yes` | sync stock → vercel prod |

## Repo

https://github.com/Jerome-WSAI/wsai-factory
