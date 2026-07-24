# wsai-factory

Private orchestration factory: ingest projects → strip → official docs → align → modules → stock.

## How it works

See `pipeline/HOW.md`.

## Quick local

```text
# 1) Local full pipeline
python tools/pipeline_automate.py --slug <slug> --polls 2 --interval-sec 0.5

# 2) Local inbox worker (loop)
python tools/worker_start.py --worker inbox_loop --polls 2 --interval-sec 1 --loop-sleep-sec 5

# 3) Cloud ingress: put project in pipeline/inbox/<slug>/ then
python tools/push_inbox.py --slug <slug> --commit yes --push yes
# → triggers Cursor Automation on Push (see automations/inbox.md)

# quality loop: /verify-loop <demande>
```

## Commands

| Command | Path | Role |
|---------|------|------|
| `/verify-loop` | `.cursor/commands/verify-loop.md` | Boucle docs + anti-fake + essais réels |
| `/factory-push-inbox` | `.cursor/commands/factory-push-inbox.md` | Commit/push inbox vers GitHub pour Automations |

## Repo

https://github.com/Jerome-WSwissAI/wsai-factory
