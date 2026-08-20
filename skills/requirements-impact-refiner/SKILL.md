---
name: requirements-impact-refiner
description: Use when a proposed software change may affect existing behavior, contracts, data, permissions, compatibility, or regression risk and repository evidence can refine the requirement before implementation planning.
license: MIT
compatibility: Works with Agent Skills clients that can inspect supplied files; repository access, search, and tests improve evidence quality but are not required.
metadata:
  version: "0.1.0"
---

# Requirements Impact Refiner

Use after a change is concrete and before implementation planning. Do not activate for ideation, debugging, code review, or generic PRD writing. If the impact review or specification is already approved and coding tasks or an implementation plan are requested, exit this skill immediately: emit no `REQ-###`, `INV-###`, `IMP-###`, `DEC-###`, or `AC-###` artifacts and continue or route to the active planning workflow. Ordinary planning output after this exit is allowed.

1. Record the proposed change as `REQ-###`; inspect supplied and repository evidence. Preserve current behavior as `INV-###` entries before refining the change.
2. Create stable `REQ-###`, `INV-###`, `IMP-###`, `DEC-###`, and `AC-###` identifiers. Classify every impact as `verified`, `inferred`, or `unknown`; cite evidence instead of implying confidence.
3. Show the impact ledger before asking one focused question. Offer two or three concrete refinement options only when a decision is needed.
4. Create `DEC-###` only after an explicit user/stakeholder selection or a decision explicitly supplied by the request. Before then, use plain **Decision needed** with no `DEC` ID; a compatibility invariant is not a selected wire or cache policy. Never mark an impact `accepted` without that recorded choice.
5. After a decision, update the requirement and recalculate the complete impact set. Even without a decision, show an explicit complete delta with every category and `new: none` when applicable.
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

Read [the evidence model](references/evidence-model.md) for IDs, evidence, states, and uncertainty; [the taxonomy](references/impact-taxonomy.md) for inspection targets; and [the refinement loop](references/refinement-loop.md) for decisions and stopping. Load only the integration reference selected for the current workflow when one is available; never load every integration reference by default.

## Common mistakes

- Presenting payment idempotency advice without tying it to the supplied request evidence.
- Listing impacts without evidence levels, stable IDs, a decision, or whole-set delta.
- Treating a user’s silence as resolution or acceptance.
- Replacing an approved planning workflow with an implementation plan.
