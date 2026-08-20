# Requirements Impact Report — INT-generic-2

## Original Requirement

| Requirement ID | Original request | Supplied evidence |
| --- | --- | --- |
| `REQ-001` | “Refine this approved requirement before I plan it with my own workflow.” | `evals/cases.json` — `INT-generic` request |

The request establishes that an approved requirement exists, but its substantive text is not supplied in the available evidence. `REQ-001` therefore remains unchanged pending the approved requirement text and the repository scope it governs. No implementation mechanics, orchestration framework, or work breakdown is added here.

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Preserve the approved requirement as supplied; substantive behavior is pending the authoritative requirement text and repository scope. | No decision recorded; the pending decision remains open. | none |

## Current Behavior

| Invariant ID | Current behavior to preserve | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The approved requirement’s current behavior and compatibility obligations must be preserved while impacts are refined. | `unknown` | The supplied evidence confirms approval but does not include the requirement text, repository paths, contracts, tests, or current behavior. |

`INV-001` is a preservation target, not a claim that any particular behavior has been verified.

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | Approved requirement’s current behavior is not present in supplied evidence; preserve it once the authoritative source is supplied. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Functionality / data / interfaces / authorization-privacy / state-concurrency / operations / compatibility / regression | High | `blocked` | `unknown` | The approved requirement’s content and repository evidence are unavailable, so affected behavior, contracts, data, permissions, rollout, compatibility, and regression surfaces cannot be assessed. | `INV-001` | The pending decision | `AC-001` |

## One focused decision

**Decision needed:** provide the approved requirement text (or its authoritative identifier) and the repository scope/evidence to inspect before impact resolution proceeds. This is an evidence-gap question, not a choice of implementation policy.

Options:

1. Supply the approved requirement text plus the relevant repository paths, contracts, and tests.
2. Supply an authoritative approved-spec identifier/path; inspect the repository scope named by that specification.
3. Proceed with a planning handoff that explicitly carries `IMP-001` as blocked and treats impact analysis as an input to that later workflow.

No option is selected in the supplied request. No concrete `DEC-###` is recorded.

## Decisions and Accepted Risks

None. The request confirms approval and asks for refinement before the user’s own planning workflow, but it does not select an evidence source or implementation policy. No impact is accepted.

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Preserve supplied approved requirement; substantive content is unavailable. | none | none | `IMP-001` remains blocked; `new: none`. |

## Whole-set recalculation

The complete known set contains only `IMP-001`. It remains blocked because the approved requirement and repository scope are not available. No impact is resolved, mitigated, accepted, deferred, or superseded, and no new impact was identified.

## Delta

| Category | Impacts |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | none |
| accepted | none |
| deferred | none |
| blocked | `IMP-001` |
| new | none |

The categories are mutually exclusive and account for every known impact exactly once.

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Before implementation planning relies on this report, the approved requirement text/identifier and affected repository scope are available, and the impact ledger is recalculated against them. | Required specification and repository evidence are currently unavailable; validation is a planning-input gap, not proof of coverage. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | `blocked` | Approved requirement content, authoritative source, repository scope, and current-behavior evidence are missing. | The pending decision | Requirement owner / planning requestor |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Evaluation request and integration mode | `evals/cases.json` — `INT-generic`: approved requirement; no named orchestration framework | Confirms generic entry and requested handoff, but supplies no behavior to refine. |
| Requirements-impact-refiner instructions | `skills/requirements-impact-refiner/SKILL.md`, `references/evidence-model.md`, `references/impact-taxonomy.md`, `references/refinement-loop.md`, `references/integration-generic.md` | Establishes report structure, evidence labels, ID rules, delta rules, and generic handoff boundary; it is not product evidence. |
| Product repository/specification | No approved requirement body, source identifier, paths, contracts, or tests supplied | All product-specific impact claims remain unknown/blocked. |

## Stop check

The generic adapter’s boundary is satisfied: this is a canonical impact report, not an implementation plan, and no external orchestration framework was invoked. The material product impact remains blocked until the approved requirement and evidence scope are supplied. After that evidence gap is resolved (or explicitly carried by the user’s planning method), recalculate the complete impact set before planning.

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: refine the approved requirement using its authoritative text and repository evidence; substantive behavior remains unspecified in supplied evidence. | `INV-001`, `IMP-001` | All product-specific functionality, data, interface, authorization/privacy, state/concurrency, operations, compatibility, and regression impacts are unknown; `IMP-001` is blocked. | `AC-001` | User’s own planning method, to be selected by the user; no workflow is invoked automatically. |
