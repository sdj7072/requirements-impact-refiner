# Requirements Impact Report — Claude feature-dev integration

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Feature-dev clarification is complete; analyze change impact. | Supplied request; supplied evidence says feature-dev Phase 3 is complete and Phase 4 architecture has not started. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Analyze the clarified feature requirement against available repository evidence, preserve the Phase 3 clarification as the baseline, and return a canonical report-only impact analysis before Claude feature-dev Phase 4 architecture design. Do not repeat general clarification, invoke Phase 4 automatically, or create an implementation plan. | No recorded decision; the supplied workflow boundary is explicit. | none |

The supplied Phase 3 result is consumed as the requirement baseline. It does not select an architecture, migration, API transition, retry, rollout, or other implementation mechanic.

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Feature-dev clarification (Phase 3) is complete and its clarified requirement is the current baseline. | `verified` | Supplied evidence: “feature-dev Phase 3 is complete.” |
| `INV-002` | Claude feature-dev Phase 4 architecture design has not started. | `verified` | Supplied evidence: “Phase 4 architecture has not started.” |
| `INV-003` | The impact-refinement pass owns the interval after clarification and before architecture design. | `verified` | `skills/requirements-impact-refiner/references/integration-claude-feature-dev.md — Entry/Exit`; supplied phase boundary. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003` | Supplied Phase 3 completion fact. |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-003` | Supplied Phase 4 not-started fact. |
| `INV-003` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | Claude feature-dev adapter Entry, Ownership, Output, and Exit. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Compatibility / Operations | High | `resolved` | `verified` | The adapter enters after Phase 3 clarification and consumes that clarified requirement; the supplied context confirms Phase 3 is complete. | `INV-001`, `INV-003` | — | `AC-001` |
| `IMP-002` | `REQ-001` | Operations / Workflow ownership | High | `resolved` | `verified` | The adapter exits before Phase 4 architecture design; the supplied context confirms Phase 4 has not started. | `INV-002`, `INV-003` | — | `AC-002` |
| `IMP-003` | `REQ-001` | Regression / Scope | High | `resolved` | `verified` | The adapter says not to repeat general clarification, not to automatically invoke the external workflow, and to return a report rather than an implementation plan or architecture design. | `INV-001`, `INV-002`, `INV-003` | — | `AC-003` |

## One Focused Decision

No focused policy decision is required. The supplied facts explicitly establish the workflow boundary and do not select architecture or implementation mechanics. No concrete `DEC-###` is recorded.

## Recorded Decision

No recorded decision; the supplied Phase 3/Phase 4 boundary governs this report. No impact is accepted, deferred, or blocked by silence.

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Preserved the completed Phase 3 clarification, constrained impact analysis to the pre-Phase 4 boundary, and made the handoff report-only. | No recorded decision; supplied workflow facts are explicit constraints. | none | `IMP-001`–`IMP-003` are resolved by the explicit entry/exit boundary. |

## Whole-Set Recalculation

The complete known set was recalculated after the boundary was made explicit. No impact is superseded and no new product impact can be inferred from the supplied workflow facts.

## Delta

- resolved: `IMP-001`, `IMP-002`, `IMP-003`
- mitigated: none
- unchanged: none
- accepted: none
- deferred: none
- blocked: none
- new: none

The categories are mutually exclusive and contain every known `IMP-###` exactly once.

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | The report uses the completed Phase 3 clarification as its requirement baseline and does not repeat broad clarification. | Supplied Phase 3 completion; adapter Entry/Ownership; output inspection. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | The report ends before Phase 4 architecture design and does not invoke or perform architecture design. | Supplied Phase 4-not-started fact; adapter Exit; output inspection. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | The output is a canonical impact report with `Planning Handoff`, not an implementation plan, architecture design, or automatic external-workflow invocation. | Adapter Output/Exit; direct output inspection. |

## Unresolved, Deferred, and Blocked Items

None for this integration boundary. Product-specific functionality, data, interface, authorization, state, operations, compatibility, policy, and regression impacts require the clarified feature requirement and repository evidence; they are not claimed from the two supplied phase facts.

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Claude feature-dev integration boundary only | Supplied Phase 3/Phase 4 facts and `integration-claude-feature-dev.md` | Workflow-entry and exit conclusions are `verified`. |
| Product behavior and repository implementation | No product source, tests, contracts, schemas, policies, or deployment evidence supplied | No product-specific impact is asserted; those impacts remain outside this boundary report. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: analyze the completed Phase 3 feature requirement against repository evidence and hand off the report before Phase 4 architecture design. | `INV-001`–`INV-003`, `IMP-001`–`IMP-003` | Product-specific impacts cannot be assessed beyond the supplied workflow facts; architecture and implementation decisions remain for the later feature-dev phase. | `AC-001`–`AC-003` | Claude feature-dev Phase 4 architecture design is the next owner, but is not invoked by this report. |

## Stop Check

All known integration-boundary impacts have a terminal `resolved` state supported by explicit supplied facts or the selected adapter. This is a report-only handoff before Phase 4, not an architecture design or implementation plan.
