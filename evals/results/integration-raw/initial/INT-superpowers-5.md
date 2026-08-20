# Requirements Impact Report — Superpowers Integration (Task 4)

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Brainstorming approved the design; refine repository impacts next. | `evals/cases.json — INT-superpowers` |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Consume the approved brainstorming design, inspect repository-backed impacts, preserve existing behavior and contracts, ask only evidence-gap or impact-resolution questions, and return the canonical impact report with its Planning Handoff. The report must stop at the boundary before Superpowers `writing-plans`; it must not repeat brainstorming or invoke `writing-plans`. | the pending decision | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The design approval from Superpowers brainstorming is already complete when this case enters impact refinement. | `verified` | `evals/cases.json — INT-superpowers`; `integration-superpowers.md — Entry` |
| `INV-002` | Superpowers `writing-plans` has not started when this case enters impact refinement. | `verified` | `evals/cases.json — INT-superpowers`; `integration-superpowers.md — Exit` |
| `INV-003` | The canonical output is a report-only Planning Handoff; this adapter does not automatically invoke the external workflow. | `verified` | `integration-superpowers.md — Output, Exit`; `docs/superpowers/specs/2026-08-20-requirements-impact-refiner-design.md — §8.3` |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002` | Approved design is consumed rather than reopened. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-003` | Planning remains a later Superpowers phase. |
| `INV-003` | `REQ-001` | `IMP-002`, `IMP-003` | Report-only handoff is the adapter output. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Compatibility / workflow boundary | high | `refining` | `verified` | `task4-baseline-scoring.md — INT-superpowers` records that the baseline entered after brainstorming but used only a generic planning exit; `integration-superpowers.md — Entry/Exit` defines the exact phase boundary. | `INV-001`, `INV-002` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | Regression / ownership | high | `refining` | `verified` | `integration-superpowers.md — Ownership` requires no repeated clarification, only evidence-gap or impact-resolution questions, no automatic external invocation, and a choose-one gate for multiple orchestrators. | `INV-001`, `INV-003` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | Operations / workflow handoff | high | `detected` | `inferred` | The approved design requires the refiner to hand planning inputs forward without writing an implementation plan; a generic planning handoff can leave ownership ambiguous even when no prohibited action occurred in the baseline transcript. | `INV-002`, `INV-003` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | Orchestrator selection | medium | `blocked` | `unknown` | The supplied case names Superpowers, but no independent runtime evidence establishes whether another orchestrator is active in the surrounding task context. | `INV-001`, `INV-003` | the pending decision | `AC-004` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| — | Decision needed: should the Superpowers adapter enforce the exact exit `before writing-plans` as an explicit ownership boundary? Options: (A) enforce the exact boundary and report-only handoff; (B) allow a generic planning handoff; (C) block until the active orchestrator is confirmed. | `REQ-001` | — | No stakeholder selection was supplied; no concrete decision ID is recorded. |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Baseline approved design refined with the observed Superpowers phase boundary and report-only ownership. | the pending decision | — | `IMP-001` and `IMP-002` remain refining; `IMP-003` remains detected; `IMP-004` remains blocked by missing context. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001`, `INV-002` | The run states entry after approved brainstorming and exits explicitly before `writing-plans`. | `evals/cases.json — INT-superpowers`; `integration-superpowers.md — Entry/Exit` |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | The run does not repeat brainstorming, invoke `writing-plans`, or automatically invoke any external workflow; it asks only impact/evidence questions. | `integration-superpowers.md — Ownership`; Task 4 integration adapter tests |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-002`, `INV-003` | Output contains the canonical impact report and Planning Handoff, with no implementation task breakdown. | `integration-superpowers.md — Output`; `skills/requirements-impact-refiner/SKILL.md — Stop conditions` |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-001`, `INV-003` | If more than one orchestrator is active, the run asks the user to choose one before continuing. | `integration-superpowers.md — Ownership`; active-task context required |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-004` | `blocked` | The surrounding task context does not independently establish whether a second orchestrator is active. | the pending decision | User / workflow controller |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Superpowers integration contract and approved design | `integration-superpowers.md`; `docs/superpowers/specs/2026-08-20-requirements-impact-refiner-design.md` | Direct contract claims are verified. |
| Task 4 baseline routing result | `task4-baseline-scoring.md`; `task4-baseline/INT-superpowers.md` | The generic-exit defect is verified for the supplied baseline; it does not prove behavior in every client/version. |
| Active orchestrator state | No independent runtime/session evidence supplied | Multi-orchestrator impact remains unknown and blocked. |
| Production repository behavior | This integration case supplies workflow evidence, not an application repository | No application-level data, authorization, interface, or runtime claims are made. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: refine repository impacts after approved brainstorming and hand off a report-only result exactly before `writing-plans`, without repeating ideation or invoking planning automatically. | `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `AC-001`, `AC-002`, `AC-003`, `AC-004` | `IMP-001`–`IMP-003` await the boundary choice; `IMP-004` is blocked pending orchestrator confirmation. | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Superpowers, with handoff before `writing-plans`; exact ownership choice is pending. |

## Whole-Set Recalculation and Delta

No explicit stakeholder decision was supplied, so the report remains at the pre-decision refinement state. Every known impact is categorized once:

- resolved: none
- mitigated: none
- unchanged: `IMP-001`, `IMP-002`, `IMP-003`
- accepted: none
- deferred: none
- blocked: `IMP-004`
- new: none

Stop check: the report is ready for the single boundary/orchestrator decision, but refinement is not complete. Do not invoke `writing-plans` or author an implementation plan from this handoff until that pending decision is recorded.
