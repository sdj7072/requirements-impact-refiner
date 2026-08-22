# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-###` | 1 | none | post-decision |

For a later revision, preserve the Report ID, increment Revision by one, and replace `none` with the lowercase SHA-256 of the exact predecessor bytes.

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-###` | Describe the requested behavior change. | User request or supplied specification. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-###` | State the selected mechanics and preserved constraints. | `DEC-###` | `REQ-###` / none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-###` | Describe current observable behavior. | `verified` / `inferred` / `unknown` | Repository path and symbol, inference basis, or named gap. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-###` | `REQ-###` | `IMP-###` | Repository path and symbol, policy, or named gap. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-###` | `REQ-###` | `functionality` / `data` / `interfaces` / `authorization/privacy` / `state/concurrency` / `operations` / `compatibility` / `legal/policy` / `regression` | `critical` / `high` / `medium` / `low` | `detected` / `refining` / `mitigated` / `resolved` / `accepted` / `deferred` / `blocked` / `superseded` | `verified` / `inferred` / `unknown` | Repository path and symbol, inference basis, or named gap. | `INV-###` | `DEC-###` | `AC-###` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-###` | State the selected option. | `REQ-###` | `IMP-###` / none | Explain the trade-off and evidence. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | none |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | `IMP-###` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-###` | Describe this revision. | `DEC-###` | `IMP-###` / none | Summarize the requirement and impact change. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-###` | `REQ-###` | `IMP-###` | `INV-###` | State the observable result. | Future test, inspection method, or named gap. |

## Unresolved, Deferred, and Blocked Items

List only ledger impacts whose state is `deferred` or `blocked`; keep `detected` and `refining` impacts in the ledger only.

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-###` | `deferred` / `blocked` | Name the gap or rationale. | `DEC-###` / none | Name the next owner. |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Name the inspected boundary or limitation. | Repository evidence or named gap. | State how this changes confidence. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-###` | `INV-###`, `IMP-###`, `DEC-###` | Name deferred and accepted impacts, or none. | `AC-###` | Name the selected planning workflow, or Not ready when blocked. |
