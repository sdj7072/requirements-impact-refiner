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

Resolve every `references/`, `assets/`, and `scripts/` path from the directory that contains this `SKILL.md`. Set `SKILL_DIR` to it; read `SKILL_DIR/references/evidence-model.md`, the taxonomy, refinement loop, [presentation modes](references/presentation-modes.md), template chooser, selected template, and validator from it, not the plugin root or workspace root. Byte-identical plugin-root mirrors are fallback only if a client loses or misinfers `SKILL_DIR`.

1. Resolve presentation settings with `scripts/resolve-settings.py`; current-request override beats repository config, then default `balanced`. Disclose invalid config and use `balanced`.
2. Locate the latest v0.3 predecessor; record `REQ-###`, inspect evidence, and preserve current behavior as `INV-###`.
3. First report: `RPT-###`, Revision 1, predecessor `none`, all impacts `new`. Later, preserve IDs, increment once, and hash exact predecessor bytes.
4. Before a choice, use only the pre-decision template: one question and two or three options; never emit `DEC-###`. After an explicit choice, use only the post-decision template, link `DEC-###`, and recalculate every impact.
5. Compute **Impact Delta** across all nine categories in the template. List each current or predecessor `IMP-###` once. Stable states are `unchanged`; terminal-to-active is `reopened`.
6. `accepted` needs a decision; `resolved` needs evidence. Only `deferred`/`blocked` impacts are unresolved. Stop at report-only handoff.

## Workflow integration

Read exactly one adapter after the orchestrator is known; apply its Entry before step 1. If more than one orchestrator is active, ask the user to choose one. Never invoke their external workflow.

| Selected mode | Read only |
| --- | --- |
| `generic` | [Generic](references/integration-generic.md) |
| `superpowers` | [Superpowers](references/integration-superpowers.md) |
| `claude-feature-dev` | [Claude feature-dev](references/integration-claude-feature-dev.md) |
| `spec-kit` | [Spec Kit](references/integration-spec-kit.md) |

## Before output

- Match `Report State` to one stage template. A concrete `DEC-###` needs an explicit selection; constraints and recommendations do not select mechanics.
- Validate with `scripts/validate-impact-report.py --require-summary REPORT.md`; add `--previous PREVIOUS.md` for a revision. If unavailable, compare conceptually and disclose the gap.
- Before choice, include only the request and supplied constraints/invariants; keep option mechanics in **Decision Needed**. `AC-###` entries are future targets, not verified behavior.

## Output shape

No preamble; the first non-empty line exactly `# Requirements Impact Report`. After `Report State`, include one `Change Impact Summary` row per ledger impact, worded for the resolved audience mode and fact-bound to that `IMP-###`. Then return the complete canonical current report inline. A saved file is supplementary only. Every lineage turn returns the complete revised report inline.
