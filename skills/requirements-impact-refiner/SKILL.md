---
name: requirements-impact-refiner
description: Use when the automatic bootstrap has selected a concrete behavior change needing impact refinement, or the user explicitly requests it, before planning; with Superpowers, after approved brainstorming; excludes ideation, explanation, debugging, code review, status, and an already impact-refined requirement or plan
license: MIT
compatibility: Agent Skills clients; repository access and tests improve evidence.
metadata:
  version: "0.3.2"
---

# Requirements Impact Refiner

Use for concrete pre-planning changes; not ideation, debugging, code review, or generic PRDs.

## Resource paths

Resolve every `references/`, `assets/`, `schemas/`, and `scripts/` path from the directory that contains this `SKILL.md`. Set `SKILL_DIR` to it, not the plugin root or workspace root. Byte-identical plugin-root mirrors are fallback only if a client loses or misinfers `SKILL_DIR`.

1. Run `scripts/resolve-settings.py` with the repository root and explicit request overrides. Invalid configuration is disclosed; use `balanced` and `compact`.
2. Select the phase and one workflow adapter. Determine whether a predecessor exists, evidence is ambiguous, or multiple impact domains apply. Run `scripts/resource_route.py` with those flags and read only the returned paths.
3. Inspect repository evidence. Author one complete state JSON using the compact contract. Do not omit an impact to shorten output. Preserve current behavior as `INV-###`; future `AC-###` entries are not current evidence.
4. Run `scripts/publish-impact-report.py`. Correct exit-1 validation errors. On exit 2 with `full-inline`, render Markdown and disclose that persistence/fast revisions are unavailable.
5. For published `compact`, return only `render-impact-report.py --format compact`. For `full`, return canonical Markdown inline. Never rewrite the renderer's facts or begin planning.

## Workflow integration

Read exactly one adapter after the orchestrator is known; apply its Entry before analysis. If more than one orchestrator is active, ask the user to choose one. Never invoke their external workflow.

| Selected mode | Read only |
| --- | --- |
| `generic` | [Generic](references/integration-generic.md) |
| `superpowers` | [Superpowers](references/integration-superpowers.md) |
| `claude-feature-dev` | [Claude feature-dev](references/integration-claude-feature-dev.md) |
| `spec-kit` | [Spec Kit](references/integration-spec-kit.md) |

## Stop conditions

Before selection, state one question with two or three options and no `DEC-###`. `accepted` needs a decision; `resolved` needs evidence; only `blocked`/`deferred` are unresolved. Stop at the validated Planning Handoff. Compact output links the append-only JSON and Markdown; full output preserves the complete canonical report.
