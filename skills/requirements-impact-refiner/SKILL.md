---
name: requirements-impact-refiner
description: Use when the automatic bootstrap has selected a concrete behavior change needing impact refinement, or the user explicitly requests it, before planning; with Superpowers, after approved brainstorming; excludes ideation, explanation, debugging, code review, status, and an already impact-refined requirement or plan.
license: MIT
compatibility: Agent Skills clients; repository access and tests improve evidence.
metadata:
  version: "0.5.0"
---

# Requirements Impact Refiner

Use after bootstrap for pre-planning changes; not ideation, debugging, code review, or generic PRDs. `flow` (`resolve-settings.py`) defaults to `report`.

## Default Fast Scan

1. Call `rir_scan` once with the change and supplied evidence.
2. `needs_input`: relay its question verbatim and stop.
3. Report flow: hide `display_text`, continue below. Ask flow: Return `display_text` verbatim. Stop; the renderer-owned question already asks whether to refine ([Fast Scan](references/fast-scan.md)).

## Detailed refinement

After yes (ask) or immediately (report), read [Controller workflow](references/controller-workflow.md) and exactly one adapter: [generic](references/integration-generic.md), [superpowers](references/integration-superpowers.md), [claude-feature-dev](references/integration-claude-feature-dev.md), [spec-kit](references/integration-spec-kit.md). Promoted scans skip trace; return the full canonical report inline. Resolve links from this `SKILL.md` directory.

## Fallbacks

CLI fallback uses `scripts/rir-controller.py`; `full-inline` must disclose unavailable persistence and promotion.
