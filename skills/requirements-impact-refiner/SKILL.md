---
name: requirements-impact-refiner
description: Use when the automatic bootstrap has selected a concrete software behavior change for impact refinement, or the user explicitly requests it, before planning; with Superpowers, after approved brainstorming; excludes ideation, explanation, debugging, code review, status, and execution of an already impact-refined requirement or plan
license: MIT
compatibility: Works with Agent Skills clients that can inspect supplied files; repository access, search, and tests improve evidence quality but are not required.
metadata:
  version: "0.1.1"
---

# Requirements Impact Refiner

Use for concrete pre-planning changes; not ideation, debugging, code review, or generic PRDs. For explanation, status, or executing an already impact-refined requirement or plan, exit without IDs to the active workflow.

1. Record the change as `REQ-###`; inspect supplied and repository evidence. Preserve current behavior as `INV-###` before refining.
2. Create stable `REQ-###`, `INV-###`, `IMP-###`, `DEC-###`, and `AC-###` identifiers. Give each impact one of `verified`, `inferred`, or `unknown`; split compound findings with different levels. Cite evidence.
3. Show the impact ledger before asking one focused question. Offer two or three concrete refinement options only when a decision is needed.
4. Create concrete `DEC-###` only after explicit selection; otherwise use **Decision needed** and “the pending decision.” Generic “no decision ID is recorded” is allowed. Constraints, invariants, and recommendations never select policy; never accept without a recorded choice.
5. After a decision, recalculate the complete set. Always show every delta category and `new: none`; categorise every known `IMP-###` once only, placing initial `detected` or `refining` impacts under `unchanged`.
6. Keep `accepted` separate from `resolved`: accepted needs its decision link; resolved needs evidence. Stop at a report-only planning handoff (refined requirement, evidence, open risks, `AC-###`), not a work breakdown or plan.

States: `detected`, `refining`, `mitigated`, `resolved`, `accepted`, `deferred`, `blocked`, `superseded`. Evidence: `verified` means direct inspected support; `inferred` means indirect repository support; `unknown` means insufficient or conflicting support.

Read [evidence](references/evidence-model.md), [taxonomy](references/impact-taxonomy.md), and [loop](references/refinement-loop.md).

## Workflow integration

Read exactly one adapter after the orchestrator is known; apply its Entry before step 1. If more than one orchestrator is active, ask the user to choose one before continuing. Never load multiple adapters or invoke their external workflow.

| Selected mode | Read only |
| --- | --- |
| `generic` | [Generic](references/integration-generic.md) |
| `superpowers` | [Superpowers](references/integration-superpowers.md) |
| `claude-feature-dev` | [Claude feature-dev](references/integration-claude-feature-dev.md) |
| `spec-kit` | [Spec Kit](references/integration-spec-kit.md) |

## Common mistakes

- Ungrounded idempotency claims, missing evidence/IDs/delta, silent acceptance, or replacing approved planning.

## Before output

- For concrete `DEC-###`, quote or point to an explicit user/stakeholder selection. Without one: no concrete ID or Recorded decision section; a constraint or deprecation window does not select mechanics.
- Validate delta: category-ID union equals all known `IMP-###`; intersections are empty. A ledger `blocked` impact goes only under `blocked`.
- Before choice, revision contains only the request and supplied constraints/invariants; pending-option mechanics stay in **Decision needed**. Compare revision/options; remove distinctive option mechanics unless a selection quote exists.
- `AC-###` entries are future targets, not verified current behavior; cite their supporting evidence or gap separately.
