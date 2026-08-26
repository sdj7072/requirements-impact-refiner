---
name: requirements-impact-refiner
description: Use when the automatic bootstrap has selected a concrete behavior change needing impact refinement, or the user explicitly requests it, before planning; with Superpowers, after approved brainstorming; excludes ideation, explanation, debugging, code review, status, and an already impact-refined requirement or plan.
license: MIT
compatibility: Agent Skills clients; repository access and tests improve evidence.
metadata:
  version: "0.5.0"
---

# Requirements Impact Refiner

Use for concrete pre-planning changes; not ideation, debugging, code review, or generic PRDs.

## Default bootstrap

1. Call `rir_previous` once with the change and ordered evidence.
2. Return its renderer result and follow [Previous-report bootstrap](references/previous-report.md).
3. Allow `rir_scan` only for `stale` or `none`, then stop.

Never invent confirmation. Resolve links from this `SKILL.md` directory; ordered evidence means supplied evidence. Read [Fast Scan](references/fast-scan.md) only for fallback.

## Detailed refinement

After yes to the scan's rendered question, read [Controller workflow](references/controller-workflow.md) and exactly one adapter: [generic](references/integration-generic.md), [superpowers](references/integration-superpowers.md), [claude-feature-dev](references/integration-claude-feature-dev.md), or [spec-kit](references/integration-spec-kit.md). Promoted scans skip trace.

## Fallbacks

Use `scripts/rir-controller.py previous` before CLI `scan`. If neither surface exists, disclose and stop; never invent a previous body or `full-inline` replacement.
