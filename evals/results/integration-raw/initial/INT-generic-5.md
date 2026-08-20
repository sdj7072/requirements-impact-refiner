# Requirements Impact Report

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Refine this approved requirement before I plan it with my own workflow. | Supplied request; supplied evidence says the requirement is approved. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Produce a canonical, report-only impact refinement for the approved requirement; preserve current behavior and invariants, identify evidence-backed impacts and acceptance criteria, and hand the report to the user’s planning method. Do not invoke an external framework or write implementation tasks. | No recorded decision; the supplied request provides the boundary. | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The requirement is already approved and is being refined before planning. | `verified` | Supplied evidence: “the requirement is approved.” |
| `INV-002` | No named orchestration framework is active. | `verified` | Supplied evidence: “no named orchestration framework is active.” |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | Supplied request places refinement before the user’s planning workflow. |
| `INV-002` | `REQ-001` | `IMP-002` | No orchestration framework was selected in the supplied evidence. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Operations / compatibility | High | `resolved` | `verified` | The request explicitly places refinement before planning; the refined requirement fixes the report-to-planning handoff. | `INV-001` | — | `AC-001` |
| `IMP-002` | `REQ-001` | Operations | High | `resolved` | `verified` | No named orchestration framework is active; the refined requirement prohibits automatic external-framework invocation. | `INV-001`, `INV-002` | — | `AC-002` |
| `IMP-003` | `REQ-001` | Regression / operations | High | `resolved` | `verified` | The refined requirement is explicitly report-only and prohibits implementation-task creation. | `INV-001` | — | `AC-003` |

## Decisions and Accepted Risks

No focused policy decision is required: the supplied request already selects a generic handoff (“my own workflow”) and supplies the no-framework constraint. Therefore no concrete `DEC-###` or accepted impact is recorded.

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Added report-only output, explicit generic handoff, and prohibitions on framework invocation and implementation tasks. | No recorded decision; supplied boundary. | None | `IMP-001`–`IMP-003` are resolved by the explicit boundary. |

## Whole-Set Recalculation and Delta

The complete known set was recalculated after the revision:

- resolved: `IMP-001`, `IMP-002`, `IMP-003`
- mitigated: none
- unchanged: none
- accepted: none
- deferred: none
- blocked: none
- new: none

The delta categories are mutually exclusive and contain every known impact exactly once.

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | The output ends at a canonical impact report and `Planning Handoff` that names the user’s planning method as the next owner; it does not start that method. | Supplied request; direct output inspection. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | The report does not name, activate, or invoke a framework that the user did not select. | Supplied “no named orchestration framework” evidence; output inspection. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-001` | The report contains no implementation work breakdown, coding tasks, or plan; it contains only refinement findings, risks, and criteria. | Supplied request; output inspection. |

## Unresolved, Deferred, and Blocked Items

None. No external repository or framework evidence was required for this generic routing refinement; implementation-level impacts remain the responsibility of the later planning workflow.

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Generic integration boundary only; no repository behavior was supplied. | Supplied requirement-approved and no-framework-active statements. | Routing conclusions are `verified` for this request, while any future code/data impacts must be assessed during planning. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `INV-001`, `INV-002`, `IMP-001`, `IMP-002`, `IMP-003` | Future implementation planning may uncover repository impacts not in the supplied evidence. | `AC-001`, `AC-002`, `AC-003` | The user’s own planning method; the generic adapter does not invoke it automatically. |

## Stop Check

All known impacts have a terminal `resolved` state supported by the explicit refined boundary. This is a report-only planning handoff, not an implementation plan.
