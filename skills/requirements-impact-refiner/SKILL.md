---
name: requirements-impact-refiner
description: Use when the automatic bootstrap has selected a concrete behavior change needing impact refinement, or the user explicitly requests it, before planning; with Superpowers, after approved brainstorming; excludes ideation, explanation, debugging, code review, status, and an already impact-refined requirement or plan
license: MIT
compatibility: Agent Skills clients; repository access and tests improve evidence.
metadata:
  version: "0.4.0"
---

# Requirements Impact Refiner

Use for concrete pre-planning changes; not ideation, debugging, code review, or generic PRDs.

## Resource paths

Resolve every `references/`, `assets/`, `schemas/`, and `scripts/` path from the directory that contains this `SKILL.md`. Set `SKILL_DIR` to it, not the plugin root or workspace root. Byte-identical plugin-root mirrors are fallback only if a client loses or misinfers `SKILL_DIR`.

1. Before inspecting workspace availability, run `scripts/resolve-settings.py` with the repository root and request overrides. Invalid configuration uses disclosed `balanced` and `compact` defaults.
2. Select the phase and one adapter. Determine predecessor, evidence-ambiguity, and multi-domain flags. Run `scripts/resource_route.py`; read only returned paths.
3. Supplied `Repository evidence` remains inspectable when the workspace is empty. Never offer implementation or scaffolding; refine it or state the missing entry input. Author complete state JSON without omitting impacts. Preserve behavior as `INV-###`; future `AC-###` is not current evidence.
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
