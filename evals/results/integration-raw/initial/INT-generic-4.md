# Requirements Impact Refinement Report — INT-generic-4

## Requirement revision

`REQ-001` — Refine the already-approved requirement against the relevant repository evidence, preserve current behavior, and return a canonical impact report for the user’s own planning workflow. The report must not invoke a named external framework or create implementation tasks.

**Evidence:** supplied request: “Refine this approved requirement before I plan it with my own workflow.” Supplied evidence: “the requirement is approved” and “no named orchestration framework is active.” The substantive requirement text and product repository scope are not supplied.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Links |
| --- | --- | --- | --- | --- |
| `INV-001` | The requirement is approved and is the input to refinement; this report must not silently replace it with a new product specification. | `verified` | Supplied evidence: “the requirement is approved.” | `must-preserve` `REQ-001` |
| `INV-002` | The next planning workflow remains user-owned because no named orchestration framework is active. | `verified` | Supplied evidence: “no named orchestration framework is active”; `integration-generic.md` — Ownership/Exit. | `must-preserve` `REQ-001` |
| `INV-003` | Product-specific current behavior, contracts, schemas, permissions, and tests remain unverified until the approved requirement and repository scope are supplied. | `unknown` | No requirement body, repository path, diff, contract, schema, or test was supplied. | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Category | Severity | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | The affected functionality, data, interfaces, authorization/privacy, state/concurrency, operations, compatibility, legal/policy, and regression surface cannot be assessed from the supplied workflow evidence alone. | Cross-cutting | High | `unknown` | The approved requirement text and relevant repository evidence are absent. | `blocked` | `affects` `REQ-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | Proceeding without the authoritative requirement and repository scope could omit a material behavior or compatibility impact. | Regression / compatibility | High | `unknown` | No product-specific source, contract, schema, test, or scope was supplied. | `blocked` | `affects` `REQ-001`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | Automatically invoking an external orchestration framework would take ownership of a workflow the request leaves to the user. | Operations / workflow boundary | Medium | `verified` | Supplied evidence says no named framework is active; `integration-generic.md` — Output/Exit. | `resolved` | `affects` `REQ-001`, `INV-002`; `produces` `AC-003` |
| `IMP-004` | Turning this report into an implementation task list would cross the generic adapter’s report-only handoff boundary. | Regression / workflow boundary | Medium | `verified` | User will plan with their own workflow; `integration-generic.md` — Output/Exit. | `resolved` | `affects` `REQ-001`, `INV-002`; `produces` `AC-004` |

## One focused evidence-gap question

Please provide the approved requirement text (or authoritative identifier) and the repository scope to inspect (path, diff, API/schema, service, or named tests). This is an evidence request, not a selection of implementation policy. Until supplied, `IMP-001` and `IMP-002` remain blocked.

## Recorded decision

No concrete `DEC-###` is recorded. The wording “with my own workflow” establishes the generic handoff boundary, but does not select transition, migration, retry, cache, authorization, rollout, or rollback mechanics. No impact is silently accepted.

## Whole-set recalculation

The complete known impact set is `IMP-001` through `IMP-004`. The workflow-boundary findings are resolved by the supplied request and generic adapter contract; the product-impact findings remain blocked by the named evidence gap. No requirement revision introduced a superseded or new impact.

## Delta

- **resolved:** `IMP-003`, `IMP-004`
- **mitigated:** none
- **unchanged:** none
- **accepted:** none
- **deferred:** none
- **blocked:** `IMP-001`, `IMP-002`
- **new:** none

Each known impact appears in exactly one delta category.

## Acceptance and regression criteria

| ID | Criterion | Level | Supporting evidence / gap | Links |
| --- | --- | --- | --- | --- |
| `AC-001` | Before planning relies on this report, every material product impact and preserved invariant is identified from the approved requirement and relevant repository evidence, or explicitly marked blocked. | `unknown` | Current product evidence is missing; this is the validation target for `IMP-001`. | `produced by` `IMP-001`; `verifies` `REQ-001`, `INV-003` |
| `AC-002` | Planning does not treat unassessed product behavior as safe; the authoritative requirement and repository scope are named before the ledger is recalculated. | `unknown` | Current inputs are absent; this is the validation target for `IMP-002`. | `produced by` `IMP-002`; `verifies` `REQ-001` |
| `AC-003` | No external orchestration framework is invoked when none is selected, and ownership remains with the user’s chosen planning method. | `verified` | Supplied workflow evidence and `integration-generic.md` — Exit. | `produced by` `IMP-003`; `verifies` `INV-002` |
| `AC-004` | The handoff is a canonical impact report with `Planning Handoff` semantics, not an implementation task list or implementation plan. | `verified` | Generic adapter’s report-only Output/Exit contract. | `produced by` `IMP-004`; `verifies` `REQ-001`, `INV-002` |

## Stop check and Planning Handoff

Refinement stops at a report-only handoff. `IMP-001` and `IMP-002` are blocked by the named information gap; they are neither accepted nor resolved. `IMP-003` and `IMP-004` are resolved by the explicit generic workflow boundary. No framework is invoked and no implementation work breakdown is created.

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: refine the approved requirement using its authoritative text and repository evidence; preserve current behavior and hand the report to the user’s own planning method. | `INV-001`–`INV-003`, `IMP-001`–`IMP-004` | Product functionality, data, interface, authorization/privacy, state/concurrency, operations, compatibility, legal/policy, and regression impacts remain unknown until the requirement and scope are supplied. | `AC-001`–`AC-004` | User’s own planning method; no external workflow is started automatically. |

