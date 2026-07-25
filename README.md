# WSAI Factory

Runtime: **factory_backend** on Render (agents + pipeline dynamique). Chatbot = Groq → backend → ZIP.

## Cas d'usage

1. Déposer un projet dans `pipeline/inbox/<slug>/` (scan auto si `FACTORY_INBOX_POLL_SEC>0`, ou `POST /inbox/scan`)
2. Chatbot prod discute le besoin → `POST /chat` backend → assemblage modules+frontend → ZIP
3. Téléchargement ZIP via chatbot `/api/download/<order_id>`
4. Preuve: `python tools/proof_factory_x10.py --count 10 --seed 42`

## Local

```text
# Backend
$env:PORT=8787
$env:WSAI_FACTORY_WEBHOOK_KEY=...
$env:GROQ_API_KEY=...
$env:FACTORY_INBOX_POLL_SEC=5
python factory_backend/server.py

# Chatbot
# chatbot/.env.local: FACTORY_BACKEND_URL, WSAI_FACTORY_WEBHOOK_KEY, GROQ via backend
cd chatbot
npm run sync-stock
npm run dev
```

## Render

`render.yaml` defines:
- `wsai-factory-backend` — ingest/chat/assemble/ZIP (`factory_backend/server.py`)
- `wsai-factory-handoff` — legacy stage webhook (`handoff/server.py`)

Secrets (backend): `WSAI_FACTORY_WEBHOOK_KEY`, `GROQ_API_KEY`.  
Live backend: https://wsai-factory-backend.onrender.com/health  
Provision helper: `python tools/provision_factory_backend.py --wait-attempts 36 --wait-sleep-sec 10`

## Commands

| Command | Role |
|---------|------|
| `python tools/proof_factory_x10.py --count 10 --seed 42` | Assemble 10 random stock tools → unzip smoke |
| `python tools/backend_probe.py --base-url https://wsai-factory-backend.onrender.com` | Live health + 401 auth probes (no secrets) |
| `python tools/render_backend_status.py --require-backend yes` | Render API: service exists + healthy |
| `python tools/provision_factory_backend.py --wait-attempts 36 --wait-sleep-sec 10` | Create backend service if missing |
| `python tools/download_token_probe.py --backend-url URL --chatbot-url NONE --job-id JOB --module src` | Order + zip (+ optional chatbot token gate) |
| `python tools/proof_prod_order.py` | Live Render catalog → chat → zip → unzip smoke |
| `python tools/ensure_chatbot_env_local.py --backend-url URL --chatbot-secret SECRET` | Write chatbot/.env.local (no secret prints) |
| `python tools/handoff_probe.py --base-url https://wsai-factory-handoff.onrender.com` | Legacy handoff health + 401 |
| `python tools/deploy_chatbot.py --prod yes` | Sync stock + Vercel prod (WSAI team CLI or `VERCEL_TOKEN`) |

Vercel Production env required: `FACTORY_BACKEND_URL=https://wsai-factory-backend.onrender.com`, `WSAI_FACTORY_WEBHOOK_KEY`, `CHATBOT_API_SECRET`.

## Repo

https://github.com/Jerome-WSAI/wsai-factory
