# Requirements Impact Report

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Speckit clarify is complete; refine impacts before planning. | Supplied `INT-spec-kit` evaluation request |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Enter after `speckit.clarify`, preserve its resulting requirement and Planning Handoff as the baseline, refine repository impacts using evidence, and return the canonical impact report before `speckit.plan`. Do not repeat general specification or invoke `speckit.plan` automatically. | the pending decision | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `speckit.clarify` is complete and its resulting requirement is the input baseline. | `verified` | Supplied `INT-spec-kit` evidence: “speckit.clarify is complete.” |
| `INV-002` | `speckit.plan` has not started. | `verified` | Supplied `INT-spec-kit` evidence: “speckit.plan has not started.” |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | Spec Kit clarification remains the authoritative pre-refinement baseline. |
| `INV-002` | `REQ-001` | `IMP-002` | The report must stop before the downstream planning boundary. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Workflow / Regression | high | `resolved` | `verified` | The Spec Kit adapter consumes completed clarification and explicitly prohibits repeating general clarification. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | Workflow / Operations | high | `resolved` | `verified` | The adapter exits before `speckit.plan` and explicitly prohibits invoking it automatically. | `INV-002` | the pending decision | `AC-002` |

## Decisions and Accepted Risks

No user or stakeholder policy choice is required for this integration handoff. The supplied workflow state fixes the entry and exit boundaries; no concrete `DEC-###` is recorded. Any later product or implementation choice belongs to the owning Spec Kit workflow and must be recorded there before accepting a risk.

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Added the post-clarify entry, pre-plan exit, canonical report-only output, and no-repeat/no-auto-invocation constraints. | the pending decision | none | `IMP-001` and `IMP-002` resolved by the adapter boundary. |

## Focused Decision

No decision is needed for this workflow integration case. The pending decision is any later product or implementation policy that emerges from the refined requirement; it is not selected by the supplied phase-status evidence.

## Whole-Set Recalculation

The complete known impact set remains `IMP-001` and `IMP-002`. Both are resolved by the Spec Kit integration contract. No impact is accepted, deferred, blocked, or superseded.

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
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | The report consumes the completed `speckit.clarify` requirement and its Planning Handoff without reopening general specification. | Inspect this report against `integration-spec-kit.md` Ownership and Entry rules; no second specification phase is created. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | The output is the canonical impact report and stops before `speckit.plan`; no planning tasks are written and no external workflow is invoked automatically. | Inspect the report’s Stop Check and Planning Handoff; supplied evidence keeps `speckit.plan` unstarted. |

## Unresolved, Deferred, and Blocked Items

None. Feature-specific impacts require the actual clarified requirement and repository evidence in the owning Spec Kit workflow; that limitation does not block this integration-boundary evaluation.

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Spec Kit integration boundary only; no feature requirement artifact or product repository was supplied. | Supplied `INT-spec-kit` phase-state facts and `integration-spec-kit.md`. | Entry/exit and ownership conclusions are `verified`; feature-specific code, data, interface, and regression impacts remain outside this evaluation. |

## Stop Check

All material integration impacts have terminal `resolved` states with direct adapter evidence. This is a report-only handoff; it does not invoke `speckit.plan` or create implementation tasks.

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: consume completed `speckit.clarify`, refine impacts, and hand off before `speckit.plan` without repeating specification. | `REQ-001`, `INV-001`–`INV-002`, `IMP-001`–`IMP-002` | Feature-specific risks depend on the clarified requirement and repository evidence supplied to the downstream workflow. | `AC-001`–`AC-002` | Spec Kit; hand off to `speckit.plan` only after this report is consumed by the owning workflow. |
