---
name: requirements-impact-refiner
description: Use when the automatic bootstrap has selected a concrete behavior change needing impact refinement, or the user explicitly requests it, before planning; with Superpowers, after approved brainstorming; excludes ideation, explanation, debugging, code review, status, and an already impact-refined requirement or plan
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

Perform exactly these actions:

1. Select one adapter from the table below.
2. Call `rir_begin` with the repository root, request, supplied evidence, adapter, and any explicit presentation overrides.
3. Inspect only the evidence needed to fill the returned analysis contract. Supplied evidence is valid input even when the workspace is empty. A needed clarification belongs in a complete pre-decision analysis; never emit a standalone question.
4. Call `rir_finalize` with the returned draft ID and normalized analysis. Correct validation errors without changing the draft ID.
5. On success, return `display_text` verbatim and stop before planning or implementation.

## Workflow integration

Read exactly one adapter and [Controller workflow](references/controller-workflow.md); apply its Entry before analysis. If more than one orchestrator is active, ask the user to choose one. Never invoke their external workflow.

| Selected mode | Read only |
| --- | --- |
| `generic` | [Generic](references/integration-generic.md) |
| `superpowers` | [Superpowers](references/integration-superpowers.md) |
| `claude-feature-dev` | [Claude feature-dev](references/integration-claude-feature-dev.md) |
| `spec-kit` | [Spec Kit](references/integration-spec-kit.md) |

## Fallbacks

CLI fallback uses the same controller via `scripts/rir-controller.py`; its successful finalize stdout is the response. Use `full-inline` only when neither MCP nor CLI is available, disclose that persistence and fast revisions are unavailable, and follow the controller workflow reference. Never rewrite renderer-owned facts.
