---
name: requirements-impact-refiner
description: Use when the automatic bootstrap has selected a concrete behavior change needing impact refinement, or the user explicitly requests it, before planning; with Superpowers, after approved brainstorming; excludes ideation, explanation, debugging, code review, status, and an already impact-refined requirement or plan
license: MIT
compatibility: Agent Skills clients; repository access and tests improve evidence.
metadata:
  version: "0.3.1"
---

# Requirements Impact Refiner

Use for concrete pre-planning changes; not ideation, debugging, code review, or generic PRDs.

## Resource paths

Resolve every `references/`, `assets/`, and `scripts/` path from the directory that contains this `SKILL.md`. Set `SKILL_DIR` to it; read `SKILL_DIR/references/evidence-model.md`, `SKILL_DIR/references/impact-taxonomy.md`, `SKILL_DIR/references/refinement-loop.md`, `SKILL_DIR/assets/impact-report-template.md`, templates, and validator from it, not the plugin root or workspace root. Byte-identical plugin-root mirrors are fallback only if a client loses or misinfers `SKILL_DIR`; they never replace it as canonical.

1. Locate the latest v0.3 predecessor; record `REQ-###`, inspect evidence, and preserve current behavior as `INV-###`.
2. First report: `RPT-###`, Revision 1, predecessor `none`, and all impacts `new`. Later, preserve IDs, increment once, and hash exact predecessor bytes; never invent lineage.
3. Before a choice, use only the [pre-decision template](assets/impact-report-pre-decision-template.md): ledger, one focused question, and two or three options. Never emit `DEC-###` or **Decisions and Accepted Risks**; use **Decision Needed** and “the pending decision.”
4. After an explicit choice, use only the [post-decision template](assets/impact-report-post-decision-template.md), link its `DEC-###`, and recalculate every impact.
5. Compute **Impact Delta** with `resolved`, `mitigated`, `unchanged`, `accepted`, `deferred`, `blocked`, `superseded`, `reopened`, and `new`. List each current or predecessor `IMP-###` once. Stable states, including `blocked`→`blocked`, are `unchanged`; terminal-to-active is `reopened`.
6. `accepted` needs a decision; `resolved` needs evidence. List only `deferred`/`blocked` impacts as unresolved. Stop at a report-only planning handoff.

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
- Validate a first report with `scripts/validate-impact-report.py REPORT.md`; validate a revision with `scripts/validate-impact-report.py --previous PREVIOUS.md REPORT.md`. If unavailable, compare conceptually and disclose the gap. Delta coverage must match lifecycle transitions.
- Before choice, include only the request and supplied constraints/invariants; keep option mechanics in **Decision Needed**. `AC-###` entries are future targets, not verified behavior.

## Output shape

No preamble. The first non-empty line exactly `# Requirements Impact Report`; then return the complete canonical current report inline. Do not return only a summary, a temporary-file link, or a saved-file path. A saved file is supplementary only. Every lineage turn returns the complete revised report inline, including its Report State, ledger, Impact Delta, and Planning Handoff.
