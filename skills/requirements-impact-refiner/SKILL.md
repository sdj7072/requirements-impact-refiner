---
name: requirements-impact-refiner
description: Use when the automatic bootstrap has selected a concrete behavior change needing impact refinement, or the user explicitly requests it, before planning; with Superpowers, after approved brainstorming; excludes ideation, explanation, debugging, code review, status, and an already impact-refined requirement or plan.
license: MIT
compatibility: Agent Skills clients; repository access and tests improve evidence.
metadata:
  version: "0.4.0"
---

# Requirements Impact Refiner

Use for concrete pre-planning behavior changes; not ideation, debugging, code review, or generic PRDs; exclude status requests too.

## Resource paths

Resolve every `references/`, `assets/`, `schemas/`, and `scripts/` path from the directory that contains this `SKILL.md`. Set `SKILL_DIR` to it, not the plugin root or workspace root. Byte-identical plugin-root mirrors are fallback only if a client loses or misinfers `SKILL_DIR`.

## Normal MCP recipe

Read one selected adapter, [Controller workflow](references/controller-workflow.md), and [transitive graph guidance](references/transitive-impact-graph.md). Then do exactly:

1. `rir_begin`
2. `rir_trace_impact`
3. inspect compact receipt
4. `rir_finalize`
5. return `display_text` verbatim

Inspect only the evidence needed to fill the returned analysis contract; supplied evidence is valid input even when the workspace is empty. Use only the compact receipt for graph evidence. Do not author graph JSON, rerun providers, invent edges, suppress frontiers, begin planning, or rewrite renderer-owned facts; stop before planning or implementation.

## Workflow integration

Read exactly one adapter and apply its Entry before analysis. If more than one orchestrator is active, ask the user to choose one; never invoke its external workflow.

| Selected mode | Read only |
| --- | --- |
| `generic` | [Generic](references/integration-generic.md) |
| `superpowers` | [Superpowers](references/integration-superpowers.md) |
| `claude-feature-dev` | [Claude feature-dev](references/integration-claude-feature-dev.md) |
| `spec-kit` | [Spec Kit](references/integration-spec-kit.md) |

## Fallbacks

CLI fallback uses `scripts/rir-controller.py`; successful finalize stdout is the response. Use `full-inline` only when MCP and CLI are both unavailable, disclose unavailable persistence and fast revisions, and follow Controller workflow.
