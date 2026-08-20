# Requirements Impact Report

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Speckit clarify is complete; refine impacts before planning. | Supplied `INT-spec-kit` evaluation request |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Enter after `speckit.clarify`, consume its requirement and current Planning Handoff, perform evidence-based impact refinement, and return the canonical impact report before `speckit.plan`. Do not repeat specification or invoke `speckit.plan` automatically. | the pending decision | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `speckit.clarify` has completed, so its resulting requirement is the baseline for refinement. | `verified` | Supplied `INT-spec-kit` repository evidence: “speckit.clarify is complete.” |
| `INV-002` | `speckit.plan` has not started. | `verified` | Supplied `INT-spec-kit` repository evidence: “speckit.plan has not started.” |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | Completed clarification is the selected Spec Kit entry state. |
| `INV-002` | `REQ-001` | `IMP-002` | Planning has not started and must remain the downstream handoff boundary. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Workflow / Compatibility | high | `resolved` | `verified` | Repeating general specification after clarification would duplicate the completed Spec Kit stage; the adapter explicitly says it “does not repeat general clarification.” | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | Workflow / Regression | high | `resolved` | `verified` | Starting planning from this adapter would cross the required boundary; the adapter exits before `speckit.plan` and says not to invoke it. | `INV-002` | the pending decision | `AC-002` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| None | No user/stakeholder policy choice is required for this integration handoff. | `REQ-001` | None | The supplied workflow state fixes the entry and exit points; any later implementation or planning choices belong to Spec Kit planning. |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Added the Spec Kit entry/exit boundaries and report-only handoff while preserving the completed clarification as baseline. | the pending decision | — | Clarified workflow ownership; no implementation plan created. |

## Focused Decision

No decision is needed for this integration case. The pending decision is any later product or implementation choice that emerges from the refined requirement; it must be recorded by the owning workflow before an impact can be accepted.

## Whole-Set Recalculation

The complete impact set remains `IMP-001` and `IMP-002`. Both are resolved by the supplied Spec Kit adapter contract: clarification is consumed as the baseline, and the report hands off before planning. No impact is accepted, deferred, blocked, or superseded.

## Delta

- resolved: `IMP-001`, `IMP-002`
- mitigated: none
- unchanged: none
- accepted: none
- deferred: none
- blocked: none
- new: none

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | The report consumes the completed `speckit.clarify` requirement and Planning Handoff without reopening general specification questions. | Validate the artifact against the Spec Kit adapter’s ownership rule; no separate clarification artifact is created. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | The task returns the canonical impact report and stops before invoking or writing `speckit.plan` planning tasks. | Validate the artifact’s Planning Handoff; `speckit.plan` remains unstarted. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Integration boundary only; no product repository or clarified feature content was supplied. | `INT-spec-kit` facts and `integration-spec-kit.md`. | Workflow entry/exit behavior is verified; feature-specific impacts must be refined from the selected clarification artifact in the owning Spec Kit workflow. |

## Stop Check and Planning Handoff

All material integration impacts are resolved with direct adapter evidence. This report is a report-only handoff; it does not invoke `speckit.plan` or create planning tasks.

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: consume completed `speckit.clarify`, refine impacts, and hand off before `speckit.plan` without repeating specification. | `REQ-001`, `INV-001`–`INV-002`, `IMP-001`–`IMP-002` | Feature-specific risks depend on the selected clarification artifact and remain for the downstream Spec Kit planning workflow. | `AC-001`–`AC-002` | Spec Kit; hand off to `speckit.plan` only after this report is accepted by the owning workflow. |
