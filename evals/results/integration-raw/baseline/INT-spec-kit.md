# Integration Baseline — Spec-Kit Impact Refinement

## Requirement revision

`REQ-001` — Before implementation planning begins, refine the clarified Spec-Kit requirement by recording current behavior/invariants, material impacts, evidence confidence, open risks, and testable acceptance criteria. Preserve the completed clarification outcome as the baseline; do not imply that `speckit.plan` has started.

Evidence: supplied request states “Speckit clarify is complete” and “speckit.plan has not started.”

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | The clarification phase is complete before this refinement handoff. | `verified` | Supplied request: “Speckit clarify is complete.” | `must-preserve` by `REQ-001` |
| `INV-002` | The planning phase has not started at the time of this baseline. | `verified` | Supplied request: “speckit.plan has not started.” | `must-preserve` by `REQ-001` |
| `INV-003` | No adapter-specific contract, implementation mechanism, or compatibility promise is established by the supplied evidence. | `unknown` | No clarified requirement artifact or repository evidence was supplied in scope. | `must-preserve` by `REQ-001` |

## Impact ledger

| ID | Impact / risk | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Starting planning without carrying the clarified requirement forward could cause planning to diverge from the completed clarification outcome. | `verified` | Supplied workflow state establishes clarification complete and planning not started; the clarified content itself is not supplied. | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | The exact functional, data, interface, authorization/privacy, state/concurrency, operations, compatibility, legal/policy, and regression impacts cannot yet be assessed from workflow state alone. | `unknown` | No clarified requirement text, repository source, tests, schemas, or deployment evidence was supplied in scope. | `blocked` | `affects` `REQ-001` |
| `IMP-003` | Beginning `speckit.plan` before the impact baseline is closed could turn unknown impacts into untracked planning assumptions. | `inferred` | Workflow ordering in the supplied request: clarification is complete, while planning has not started; impact evidence is not present. | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-004` | A transition or compatibility decision cannot be recorded because no explicit stakeholder selection of mechanics is supplied. | `verified` | Supplied request identifies phase status only and contains no selection of transition, adapter, migration, retry, cache, or compatibility policy. | `blocked` | `affects` `REQ-001`, `INV-003` |

## One focused decision

Decision needed: which artifact should be treated as the authoritative clarified requirement input for the next refinement/planning handoff?

1. The completed `speckit.clarify` output (recommended): preserves the clarified decisions as the source of truth and enables impact evidence to be refined against them.
2. A separately supplied requirement/specification artifact: permits refinement against that artifact, provided it is identified and its relationship to clarification is explicit.
3. Proceed with workflow-state-only planning: leaves product and integration impacts blocked and carries the uncertainty into planning.

No concrete `DEC-###` is recorded because the supplied request does not select one of these options.

## Recorded decision

No recorded decision. The pending decision is the authoritative clarified requirement input; no transition mechanics or adapter policy are selected.

## Whole-set recalculation

No decision was supplied, so the complete known impact set remains unchanged. The workflow handoff is not treated as acceptance or resolution.

### Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-003`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-002`, `IMP-004`
- `new`: none

## Stop check and planning handoff

The refinement baseline is complete as far as the supplied evidence permits. `speckit.plan` remains not started. Before planning can safely consume this baseline, provide or identify the completed clarification artifact and make the focused source-of-truth choice. Until then, the material unknowns remain blocked; silence is not acceptance.

### Acceptance / regression criteria

| ID | Criterion | Level | Supporting evidence / gap | Links |
| --- | --- | --- | --- | --- |
| `AC-001` | The planning input explicitly references the completed clarification outcome and preserves its requirement decisions. | `unknown` | Current workflow state is supplied; the clarification artifact is not supplied. | verifies `INV-001`; produced by `IMP-001` |
| `AC-002` | No `speckit.plan` work is considered started until the impact baseline and its open blocked inputs are visible to the planning workflow. | `verified` | Supplied request states `speckit.plan` has not started; gate semantics beyond that state are not supplied. | verifies `INV-002`; produced by `IMP-003` |
| `AC-003` | The selected authoritative clarification artifact is traceable from the refined requirement into planning. | `unknown` | No artifact identifier or traceability mechanism was supplied. | verifies `REQ-001`; addresses `IMP-002`, `IMP-004` |

This is a report-only handoff: it supplies the refined requirement, preserved baseline, impact evidence, open risks, pending decision, and acceptance criteria. It does not create a work breakdown or implementation plan.
