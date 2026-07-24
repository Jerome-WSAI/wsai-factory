## Learned User Preferences

- Prefer plain language with no jargon: restate messy requests cleanly, say concretely what the finished project will enable, and propose an evolution — do not parrot the user.
- Flag instructions that look unhealthy or were written by an agent that followed blindly without reflection.
- Documentation must be technical only (not prose); a workspace project truth source is temporary until realized, then delete it and keep one up-to-date file that shows how things work (feature name, path, folder + pseudocode/names, official stack URL).
- Dislikes Cursor plugins for this system: not enough control and painful to maintain.
- Specialized control/validation subagents should keep the main agent honest (no lying/hallucination patterns); they must not do the main work themselves.
- Do not invent new agents in-chat; send creation through MCP tied to Cursor Automations, and grow the hook/agent system over time as work proceeds.
- Prefer continuous tools that stream discussion context to a central “brain” over local fiches; the system must build only what was said — no unplanned invention.
- Adopted global.rules / global.instructions in `rules.mdc` (strict typing, no default params, no silent fallbacks, 2+ subagents or none, commit only on request, etc.).

## Learned Workspace Facts

- WSAI-Factory is the workspace for a Cursor orchestration system: turn disjoint iterative user messages into a dynamic project understanding, then a validated objective fiche, then gate/control agents (one gate per objective).
- Planned companion public repo `WSAI-agents`: generic agents with no coupling to private projects, driven by a dynamic brief from context.
- Intended hook layer detects phases where the main agent is unsupervised and forces creation/invocation of a specialized follow-up agent via Automations/MCP.
- Runtime ingest pipeline (local folders + scripts + Automations bridge): `pipeline/HOW.md` — inbox → inventory+strip → official docs → align → extract units → stock; no cloud folder-watch; inventaire before strip; unresolved docs fail closed.
