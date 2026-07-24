---
description: Deposer un projet dans pipeline/inbox et le pousser vers GitHub (cloud)
argument-hint: [slug]
---

Tu prepares l'ingress cloud pour le slug `$ARGUMENTS`.

1. Si `$ARGUMENTS` vide : demande le slug, stop.
2. Verifie que `pipeline/inbox/$ARGUMENTS/` existe et contient des fichiers.
3. Execute (stage only, no commit unless user asks):
   `python tools/push_inbox.py --slug $ARGUMENTS --commit no --push no`
4. Montre le JSON. Si `inbox_still_ignored` : corrige `.gitignore`.
5. Demande confirmation explicite avant `--commit yes` puis avant `--push yes`.
6. Rappelle Automation Cursor Push to branch + `automations/inbox.md`.
