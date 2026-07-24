# Automation: reuse stock modules (DEFERRED — not enabled)

## Status
Deferred until `pipeline/stock/` contains real modules and issue contract is agreed.
Do not run this automation yet.

## Intended trigger (Cursor Automations)
GitHub **Issue label changed** (supported). Not "issue opened" alone.

## Intended rules (when enabled)
1. Issue must name existing `pipeline/stock/<module>/` ids.
2. Assemble only named modules. No invention.
3. Missing module → fail.
