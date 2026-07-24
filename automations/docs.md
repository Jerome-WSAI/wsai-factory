# Automation: resolve official docs

## Trigger
Webhook or git push after local stage `stripped` (`tools/advance_stage.py --to-stage docs`).

## Input
- `pipeline/jobs/<job_id>/inventory.json`
- `pipeline/jobs/<job_id>/01-stripped/` (code + manifests kept)

## Hard rules
1. For every real dependency in `inventory.json` (ignore names starting with `__manifest__:` — expand those manifests first), resolve **official** documentation URL + version-pinned instructions.
2. Write `pipeline/jobs/<job_id>/02-docs/official_docs/<ecosystem>/<name>/` with:
   - `meta.json`: `{name, ecosystem, version, url, fetched_at, source}`
   - `instructions.md`: technical excerpts only (no marketing prose)
3. Write `docs_manifest.json` listing each dep with `doc_status`: `resolved` | `unresolved`.
4. If any dep cannot be resolved officially → set that entry `unresolved`, set job error, **do not invent**. Fail loud.
5. Do not modify application code in this stage.
6. Launch **2** read-only control checks (coverage of inventory vs manifest; no fabricated URLs). Controllers do not write code.

## Output
- `02-docs/official_docs/**`
- `02-docs/docs_manifest.json`
- Update `state.json`: `stage=docs`, `status=ok` or `failed`

## Stack
Prefer vendor docs / Context7-style official sources. Date every fetch (`fetched_at` ISO-8601).
