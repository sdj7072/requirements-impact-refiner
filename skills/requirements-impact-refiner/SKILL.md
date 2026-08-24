---
name: requirements-impact-refiner
description: Use when the automatic bootstrap has selected a concrete behavior change needing impact refinement, or the user explicitly requests it, before planning; with Superpowers, after approved brainstorming; excludes ideation, explanation, debugging, code review, status, and an already impact-refined requirement or plan.
license: MIT
compatibility: Agent Skills clients; repository access and tests improve evidence.
metadata:
  version: "0.4.0"
---

# Requirements Impact Refiner

Use after bootstrap for concrete pre-planning changes; not ideation, debugging, code review, or generic PRDs.

## Default Fast Scan

1. Call `rir_scan` once with the change and supplied evidence.
2. Return `display_text` verbatim.
3. Ask whether the user wants detailed refinement.
4. Stop; do not promote, plan, or implement without the answer.

Do not invent paths, rerun providers, or hide frontiers. Resolve links from this `SKILL.md` directory. Read [Fast Scan](references/fast-scan.md) only for fallback or technical detail.

## Detailed refinement

After yes, read [Controller workflow](references/controller-workflow.md) and exactly one adapter: [generic](references/integration-generic.md), [superpowers](references/integration-superpowers.md), [claude-feature-dev](references/integration-claude-feature-dev.md), or [spec-kit](references/integration-spec-kit.md). Promoted scans skip trace.

## Fallbacks

CLI fallback uses `scripts/rir-controller.py`. `full-inline` must disclose unavailable persistence and promotion.
