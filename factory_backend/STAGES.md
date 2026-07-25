# Factory dynamic stages (single registry)

Stages run in order by `tools/pipeline_automate.run_slug` + `factory_backend` assemble.

| id | role |
|----|------|
| inbox | wait stable + strip |
| docs | official docs |
| align | align to docs |
| modularize | modules → stock |
| assemble | template + stock → zip (orders) |

No Cursor Automations. Runtime = `factory_backend/server.py`.
