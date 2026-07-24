---
description: Boucle qualité temporaire — docs officielles, anti-fake, essais réels, cleanup
argument-hint: [demande à accomplir]
---

Tu exécutes la boucle `/verify-loop` pour accomplir : $ARGUMENTS

Tu n’es PAS en train d’écrire un message à l’utilisateur pendant la boucle. Tu exécutes le protocole ci-dessous jusqu’à validation, puis tu nettoies, puis seulement tu parles à l’utilisateur.

## 0. Interdits absolus

- Composer / modèles interdits si l’utilisateur a dit Grok/auto : pour tout `Task`, modèle `cursor-grok-4.5-high-fast` ou omis (auto). Jamais `composer-2.5-fast`.
- Toujours **2+ subagents en parallèle** ou aucun (règle `rules.mdc`). Jamais exactement 1.
- Aucun placeholder, mock, fake, TODO cosmétique, URL inventée, “doc officielle” de mémoire modèle.
- Les agents de contrôle / preuve **ne font pas** le travail principal ; ils vérifient.
- Ne crée pas d’agents permanents Automations ici : uniquement des artefacts **temporaires** sous `.cursor/loop-runs/<run_id>/`.

## 1. Amorcer le run temporaire

1. Si `$ARGUMENTS` est vide : une question ciblée à l’utilisateur, puis stop (pas de boucle).
2. Sinon lancer :
   `python tools/loop_run.py init --demand "$ARGUMENTS"`
3. Lire le `run_id` et les chemins imprimés (JSON).
4. Installer les hooks temporaires :
   `python tools/loop_run.py install-hooks --run-id <run_id>`
5. Écrire immédiatement dans `.cursor/loop-runs/<run_id>/PLAN.md` (technique, pas roman) :
   - objectif (= demande)
   - plan d’étapes
   - **pourquoi** chaque étape
   - preuves attendues (fichiers, commandes, URLs officielles datées)
   - critères “demande accomplie”

## 2. Boucle obligatoire (répéter jusqu’à PASS)

Chaque itération = **batch parallèle de 2+ Task** (Grok/auto), puis synthèse par toi.

### Batch A — Contrôle (lecture seule, ne codent pas)

Lance **en même temps** au minimum :

1. **docs-official** — Vérifie que chaque dépendance / API / outil touché a une **doc officielle** (URL vendor, version, date). Signale tout trou. Interdit d’inventer une URL.
2. **anti-fake** — Cherche fake/mock/placeholder/stub/`pass`/`NotImplemented`/lorem/TODO trompeur. Exige preuve fichier+ligne. Verdict PASS/FAIL.
3. **charte-qualite** — Confronté à `rules.mdc` + chartes du repo (typage strict, pas de fallback silencieux, erreurs explicites, etc.). Verdict PASS/FAIL avec preuves.

Chacun doit renvoyer exactement :

```text
VERDICT: PASS|FAIL
PREUVES:
- path:line — fait
MANQUES:
- ...
```

### Batch B — Essais réels (pas “lire le code pour dire que ça marche”)

Lance **en même temps** au minimum **2** subagents `shell` ou `generalPurpose` dont l’objectif est :

- **ne pas** valider en relisant le source comme preuve suffisante ;
- **exécuter** l’outil / CLI / serveur / script réellement (install deps si besoin, commandes non interactives) ;
- rapporter stdout/stderr, exit codes, artefacts.

Retour exact :

```text
VERDICT: PASS|FAIL
ESSAIS:
- commande — exit — observation
PREUVE_DEMANDE_ACCOMPLIE: oui|non — justification courte
```

### Synthèse (toi, agent principal)

1. Mets à jour `.cursor/loop-runs/<run_id>/EVIDENCE.md` avec les retours.
2. Si un FAIL : corrige le **minimum** (code/config), incrémente `iteration` via :
   `python tools/loop_run.py bump --run-id <run_id>`
   puis **recommence la boucle** (nouveaux batches 2+).
3. Si tous PASS **et** `PREUVE_DEMANDE_ACCOMPLIE: oui` sur les essais réels :
   - écris `.cursor/loop-runs/<run_id>/validation.json` avec `"status":"pass"`
   - `python tools/loop_run.py finalize --run-id <run_id>`
   - **stop la boucle**

## 3. Cleanup (obligatoire avant de parler)

`python tools/loop_run.py cleanup --run-id <run_id>`

Ça doit :

- retirer les hooks temporaires et restaurer le backup `hooks.json` s’il existait ;
- supprimer `.cursor/loop-runs/<run_id>/` (artefacts temporaires) ;
- ne laisser **aucun** hook/subagent prompt temporaire actif.

Si cleanup échoue : signale l’erreur clairement ; ne prétends pas que c’est propre.

## 4. Après cleanup — parler à l’utilisateur

Réponse courte en français :
- Voici ö

Pas de jargon. Pas de roman. Ne repars pas en boucle sauf nouvelle commande.

## 5. Hook stop (comportement attendu)

Tant que le run est ACTIVE et `validation.json` absent ou non-pass, le hook stop doit te renvoyer en follow-up pour continuer la boucle (ne pas abandonner ni inventer un succès). Dès `finalize` + cleanup, plus de follow-up loop.
