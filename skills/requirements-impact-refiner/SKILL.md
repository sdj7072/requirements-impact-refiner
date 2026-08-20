---
name: requirements-impact-refiner
description: Use when a proposed software change may affect existing behavior, contracts, data, permissions, compatibility, or regression risk and repository evidence can refine the requirement before implementation planning.
license: MIT
compatibility: Works with Agent Skills clients that can inspect supplied files; repository access, search, and tests improve evidence quality but are not required.
metadata:
  version: "0.1.0"
---

# Requirements Impact Refiner

Use for a concrete change before implementation planning; not ideation, debugging, code review, or generic PRD writing. If the impact review or specification is already approved and coding tasks or an implementation plan are requested, exit this skill immediately: emit no `REQ-###`, `INV-###`, `IMP-###`, `DEC-###`, or `AC-###` artifacts and continue or route to the active planning workflow. Ordinary planning output after this exit is allowed.

1. Record the proposed change as `REQ-###`; inspect supplied and repository evidence. Preserve current behavior as `INV-###` entries before refining the change.
2. Create stable `REQ-###`, `INV-###`, `IMP-###`, `DEC-###`, and `AC-###` identifiers. Classify every impact as `verified`, `inferred`, or `unknown`; cite evidence instead of implying confidence.
3. Show the impact ledger before asking one focused question. Offer two or three concrete refinement options only when a decision is needed.
4. Create `DEC-###` only after an explicit user/stakeholder selection or a decision explicitly supplied by the request. Never allocate, mention, link, or forward-reference `DEC-###` before it is recorded; use only **Decision needed** and “the pending decision.” A constraint, invariant, recommendation, or policy implied by evidence is never a selected wire, cache, transition, or retry policy. Never mark an impact `accepted` without that recorded choice.
5. After a decision, update the requirement and recalculate the complete impact set. Even without a decision, show every delta category and `new: none` when applicable; list every known `IMP-###` exactly once, placing initial `detected` or `refining` impacts under `unchanged`.
6. Keep `accepted` separate from `resolved`: accepted needs its decision link; resolved needs evidence. Stop at a report-only planning handoff (refined requirement, linked evidence, open risks, and `AC-###`), not an imperative work breakdown or implementation plan.

| State | Use |
| --- | --- |
| `detected`, `refining`, `mitigated` | Found, under refinement, or reduced |
| `resolved`, `accepted`, `deferred`, `blocked`, `superseded` | Eliminated with evidence; retained by decision; postponed; information-limited; or replaced |

| Evidence level | Meaning |
| --- | --- |
| `verified` | Direct inspected support |
| `inferred` | Indirect repository support |
| `unknown` | Insufficient or conflicting support |

Read [the evidence model](references/evidence-model.md), [taxonomy](references/impact-taxonomy.md), and [refinement loop](references/refinement-loop.md). Load only the selected integration reference when available; never load every integration reference by default.

## Common mistakes

- Giving idempotency advice without supplied evidence.
- Omitting evidence levels, IDs, a decision, or the whole-set delta.
- Treating silence as resolution or acceptance.
- Replacing approved planning with an implementation plan.
