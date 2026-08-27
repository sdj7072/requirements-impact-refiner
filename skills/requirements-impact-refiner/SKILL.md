---
name: requirements-impact-refiner
description: Use when the automatic bootstrap has selected a concrete behavior change needing impact refinement, or the user explicitly requests it, before planning; with Superpowers, after approved brainstorming; excludes ideation, explanation, debugging, code review, status, and an already impact-refined requirement or plan.
license: MIT
compatibility: Agent Skills clients.
metadata:
  version: "0.6.1-dev"
---

# Requirements Impact Refiner

Use after bootstrap; not ideation, debugging, code review, or generic PRDs. `flow` defaults to `report`.

## Default bootstrap

1. Read [Previous report](references/previous-report.md); call `rir_previous` with supplied evidence.
2. `fresh`: return report. `ambiguous`: ask candidates. Stop.
3. `stale`: return its report, then scan with exact hints. `none`: scan normally.
4. `needs_input`: relay and stop. Ask flow: return scan `display_text` and stop. Report flow: hide scan `display_text` and continue.

## Detailed refinement

After yes (ask) or immediately (report), follow the reference; read [Controller](references/controller-workflow.md) and exactly one adapter: [generic](references/integration-generic.md), [superpowers](references/integration-superpowers.md), [claude-feature-dev](references/integration-claude-feature-dev.md), or [spec-kit](references/integration-spec-kit.md). Return the canonical report inline. Resolve links from this `SKILL.md` directory.

## Fallbacks

CLI: `scripts/rir-controller.py previous` before `scan`; [Fast Scan](references/fast-scan.md) governs ask. If unavailable, disclose; never invent `full-inline`.
