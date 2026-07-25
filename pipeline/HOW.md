# Factory backend pipeline

Render service `factory_backend/server.py` owns ingest + assemble.

- Inbox drop → `/inbox/scan` or poll `FACTORY_INBOX_POLL_SEC`
- Chat/order → assemble template + stock → `pipeline/deliveries/<order_id>.zip`
- Auth: Bearer `WSAI_FACTORY_WEBHOOK_KEY` on all mutating/catalog routes; `/health` public
- Proof: `python tools/proof_factory_x10.py --count 10 --seed 42`
- Probe: `python tools/backend_probe.py --base-url http://127.0.0.1:8787`

Live backend: https://wsai-factory-backend.onrender.com/health  
Legacy handoff: https://wsai-factory-handoff.onrender.com/health  
Provision: `python tools/provision_factory_backend.py --wait-attempts 36 --wait-sleep-sec 10`
