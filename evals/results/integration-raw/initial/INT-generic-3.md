# Requirements Impact Report — INT-generic-3

## Requirement revision

`REQ-001` — Refine the approved requirement for repository and compatibility impacts, then hand the resulting report to the user’s own planning workflow. Do not select or invoke an orchestration framework, and do not turn this report into implementation tasks.

Evidence: supplied request, “Refine this approved requirement before I plan it with my own workflow”; supplied evidence, “the requirement is approved” and “no named orchestration framework is active.”

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Links |
| --- | --- | --- | --- | --- |
| `INV-001` | The supplied requirement is already approved and is the input to impact refinement; refinement must not replace that approval with a new product specification. | `verified` | Supplied evidence: “the requirement is approved.” | `must-preserve` `REQ-001` |
| `INV-002` | No named orchestration framework is active, so ownership of the subsequent planning method remains with the user. | `verified` | Supplied evidence: “no named orchestration framework is active”; `integration-generic.md — Ownership/Exit`. | `must-preserve` `REQ-001` |

No repository implementation, contract, schema, or test artifact was supplied. Claims about domain-specific functionality, data, interfaces, authorization, operations, or regression behavior therefore remain unassessed rather than being inferred as safe.

## Impact ledger

| ID | Impact | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Automatically invoking a named framework would take ownership of the next workflow despite no framework being selected. | `verified` | Supplied evidence: no named orchestration framework is active; `integration-generic.md — Exit`. | `resolved` | `affects` `REQ-001`, `INV-002`; `produces` `AC-001` |
| `IMP-002` | The actual repository change surface and its functionality, data, interface, authorization/privacy, state/concurrency, operations, compatibility, legal/policy, and regression impacts cannot be assessed from the supplied integration evidence. | `unknown` | No repository artifacts or concrete domain requirement supplied; only approval and orchestration-status evidence is available. | `blocked` | `affects` `REQ-001`; `produces` `AC-002` |
| `IMP-003` | Producing an implementation task list here would replace the user’s subsequent planning workflow and exceed this report-only handoff. | `verified` | Supplied request says the user will plan with their own workflow; `integration-generic.md — Output/Exit`. | `resolved` | `affects` `REQ-001`, `INV-002`; `produces` `AC-003` |

## One focused decision

No additional impact-resolution question is required. The request explicitly selects a user-owned planning workflow and supplies no named orchestrator. The pending handoff is therefore generic: the user chooses and starts planning after receiving this report. Any domain-specific impact decision remains blocked until the concrete approved requirement and repository evidence are available.

## Recorded decision

`DEC-001` — Use a generic, report-only handoff to the user’s own planning workflow; do not invoke an external framework automatically.

Recorded selection: “before I plan it with my own workflow.” This decision refines `REQ-001` and mitigates the workflow-ownership risk in `IMP-001` and `IMP-003`.

## Whole-set recalculation

All known impacts were reconsidered after `DEC-001`:

- `IMP-001` is resolved because no framework is selected or invoked.
- `IMP-002` remains blocked because repository/domain evidence is absent.
- `IMP-003` is resolved because this output stops at a report-only handoff.

No impact was superseded; no new impact was found.

## Delta

- resolved: `IMP-001`, `IMP-003`
- mitigated: none
- unchanged: none
- accepted: none
- deferred: none
- blocked: `IMP-002` — named information gap: the concrete approved requirement plus the repository paths/contracts/tests it may affect.
- new: none

## Stop check and planning handoff

The workflow boundary is refined and can stop here. The only remaining material item is explicitly blocked by missing domain/repository evidence; it is not silently accepted. This report is ready for the user’s chosen planning method. No external framework was invoked and no implementation work breakdown or plan was created.

### Acceptance and regression criteria

| ID | Criterion | Supporting evidence / gap | Links |
| --- | --- | --- | --- |
| `AC-001` | The handoff does not invoke or prescribe a named orchestration framework when none is active. | Verified integration evidence and `integration-generic.md — Exit`. | verifies `INV-002`; produced by `IMP-001` |
| `AC-002` | Before planning, the selected workflow receives an explicit list of domain impacts and validation gaps; no unsupported repository behavior is claimed. | Gap recorded in `IMP-002`; no repository artifacts supplied. | verifies `REQ-001`; produced by `IMP-002` |
| `AC-003` | The output ends as an impact report with a planning handoff, not implementation tasks or an implementation plan. | Supplied user-owned planning request and `integration-generic.md — Output/Exit`. | verifies `INV-001`; produced by `IMP-003` |

