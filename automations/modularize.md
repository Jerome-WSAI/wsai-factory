# Automation: extract reuse units (modularize)

## Trigger
Webhook/git after align OK (`tools/advance_stage.py --to-stage modularized`).

## Preconditions
- Local script already produced `module_plan.json` via:
  `python tools/ast_module_plan.py --job-id <id> --code-subdir 03-aligned`
- Plan units must have `evidence` in {`existing_directory`,`single_root_no_subdirs`}

## Hard rules
1. Apply **only** the plan: copy/move listed `source_paths` into `04-modules/Projet/<module_name>/`.
2. Forbidden: invent new modules, rename for “cleanliness”, add glue features.
3. If plan empty or evidence missing → fail.
4. Two read-only controllers verify every output file maps to a plan path.

## Output
- `pipeline/jobs/<job_id>/04-modules/Projet/<module>/...`
- Then human/script may promote to `pipeline/stock/<module_name>/`
- `state.json`: `stage=modularized`, `status=ok|failed`
