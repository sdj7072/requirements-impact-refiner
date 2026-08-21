---
name: requirements-impact-refiner
description: Use when the automatic bootstrap has selected a concrete software behavior change for impact refinement, or the user explicitly requests it, before planning; with Superpowers, after approved brainstorming; excludes ideation, explanation, debugging, code review, status, and execution of an already impact-refined requirement or plan
license: MIT
compatibility: Works with Agent Skills clients that can inspect supplied files; repository access, search, and tests improve evidence quality but are not required.
metadata:
  version: "0.3.0"
---

# Requirements Impact Refiner

Use for concrete pre-planning changes; not ideation, debugging, code review, or generic PRDs.

1. Locate the latest v0.3 predecessor; record the change as `REQ-###`, inspect evidence, and preserve current behavior as `INV-###`.
2. Create stable IDs. First report: allocate `RPT-###`, Revision 1, predecessor `none`; all impacts are `new`. Later: preserve report/impact IDs, increment once, and hash exact predecessor bytes. Never invent unavailable lineage.
3. Set report phase explicitly. Before a choice, use only the [pre-decision template](assets/impact-report-pre-decision-template.md): show the ledger, one focused question, and two or three options. After an explicit choice, use only the [post-decision template](assets/impact-report-post-decision-template.md).
4. In `pre-decision`, never output a concrete `DEC-###` or **Decisions and Accepted Risks**. Use **Decision Needed** and “the pending decision.” Constraints, invariants, and recommendations never select policy.
5. In `post-decision`, record the selected choice as `DEC-###`, link it, and recalculate every impact. Never accept without that decision link.
6. Compute **Impact Delta** from predecessor transitions. Include `resolved`, `mitigated`, `unchanged`, `accepted`, `deferred`, `blocked`, `superseded`, `reopened`, and `new`; list each current or predecessor `IMP-###` once. Stable states, including `blocked`→`blocked`, are `unchanged`; terminal-to-active is `reopened`.
7. Keep `accepted` separate from `resolved`: accepted needs a decision; resolved needs evidence. Reject unsupported resolution or acceptance. List only `deferred`/`blocked` impacts in the unresolved-items table. Stop at a report-only planning handoff.

Read [evidence](references/evidence-model.md), [taxonomy](references/impact-taxonomy.md), [loop](references/refinement-loop.md), and the [template chooser](assets/impact-report-template.md).

## Workflow integration

Read exactly one adapter after the orchestrator is known; apply its Entry before step 1. If more than one orchestrator is active, ask the user to choose one. Never invoke their external workflow.

| Selected mode | Read only |
| --- | --- |
| `generic` | [Generic](references/integration-generic.md) |
| `superpowers` | [Superpowers](references/integration-superpowers.md) |
| `claude-feature-dev` | [Claude feature-dev](references/integration-claude-feature-dev.md) |
| `spec-kit` | [Spec Kit](references/integration-spec-kit.md) |

## Before output

- Match `Report State` to exactly one stage template. For concrete `DEC-###`, point to an explicit selection; a constraint or deprecation window does not select mechanics.
- Validate first reports with `scripts/validate-impact-report.py REPORT.md`; validate revisions with `scripts/validate-impact-report.py --previous PREVIOUS.md REPORT.md`. If deterministic validation cannot run, compare conceptually and disclose that gap. The delta must cover all known impacts exactly once and agree with lifecycle transitions.
- Before choice, revision contains only the request and supplied constraints/invariants; pending-option mechanics stay in **Decision needed**. Compare revision/options; remove distinctive option mechanics unless a selection quote exists.
- `AC-###` entries are future targets, not verified current behavior; cite their supporting evidence or gap separately.
