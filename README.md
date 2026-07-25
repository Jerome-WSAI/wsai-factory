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
Until Render creates `wsai-factory-backend`, local `PORT=8787` is the proof path.

## Commands

| Command | Role |
|---------|------|
| `python tools/proof_factory_x10.py --count 10 --seed 42` | Assemble 10 random stock tools → unzip smoke |
| `python tools/backend_probe.py --base-url http://127.0.0.1:8787` | Health + 401 auth probes (no secrets) |
| `python tools/handoff_probe.py --base-url https://wsai-factory-handoff.onrender.com` | Legacy handoff health + 401 |
| `python tools/deploy_chatbot.py --prod yes` | Sync stock + Vercel prod (needs WSAI team CLI) |

## Repo

https://github.com/Jerome-WSAI/wsai-factory
