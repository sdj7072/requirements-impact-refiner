# Integration Baseline — Feature-dev Clarification

## Requirement revision

`REQ-001` — Analyze the change impact after feature-dev clarification has completed, preserving the clarified feature intent and producing a report suitable for the next planning workflow. The analysis is a report-only handoff: it must identify current behavior/invariants, impacts, evidence confidence, open decisions or information gaps, and testable acceptance criteria. It must not assume that architecture design has started.

Supplied evidence: feature-dev Phase 3 is complete; feature-dev Phase 4 architecture has not started.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Feature-dev clarification is complete and is the current requirements baseline. | `verified` | Supplied task evidence: “feature-dev Phase 3 is complete” | `must-preserve` by `REQ-001` |
| `INV-002` | Feature-dev Phase 4 architecture has not started; no architecture decision may be represented as already selected. | `verified` | Supplied task evidence: “Phase 4 architecture has not started” | `must-preserve` by `REQ-001` |
| `INV-003` | This baseline must remain report-only and must hand off to planning rather than create an implementation work breakdown. | `verified` | Requirements-impact-refiner refinement-loop instruction | `must-preserve` by `REQ-001` |

No repository, source, test, schema, integration, or architecture artifact was supplied or inspected for this baseline. Consequently, behavior-specific claims beyond the two phase-status facts remain unknown.

## Impact ledger

| ID | Potential impact | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Architecture-dependent behavior, interfaces, data changes, authorization, concurrency, operations, compatibility, and regression exposure cannot yet be assessed from the supplied phase-status evidence. | `unknown` | No architecture or repository evidence supplied; Phase 4 has not started | `blocked` | `affects` `REQ-001`, `INV-002`; `produces` `AC-001` |
| `IMP-002` | Starting implementation planning before architecture decisions are recorded could cause the plan to encode unselected mechanics or invalidate the clarified requirement. | `inferred` | Phase 4 is explicitly not started; refinement-loop rule prohibits selecting mechanics without an explicit decision | `detected` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | The completed clarification may not fully capture downstream contract, migration, rollout, or test obligations because no Phase 4 artifact or repository evidence is available for comparison. | `unknown` | Phase 3 completion supplied, but no clarified-requirement artifact or downstream evidence supplied | `blocked` | `affects` `REQ-001`, `INV-001`; `produces` `AC-003` |
| `IMP-004` | A later architecture decision may materially revise this baseline and require the complete impact set to be recalculated. | `inferred` | Refinement-loop requirement to recalculate after every decision | `detected` | `affects` `REQ-001`, `INV-002`; `produces` `AC-004` |

## One focused decision

The pending decision is whether this baseline should hand off now for architecture work, and what scope that handoff should carry:

1. **Architecture-first handoff (recommended):** begin Phase 4 with `IMP-001` and `IMP-003` explicitly blocked, then recalculate after architecture decisions.
2. **Evidence-first refinement:** provide the clarified requirement and repository/contract artifacts before beginning Phase 4, so more impacts can be assessed now.
3. **Narrow-scope handoff:** proceed with architecture for only the explicitly clarified behavior and defer all unobserved cross-cutting impacts.

No option was selected in the supplied request, so no concrete `DEC-###` is recorded and no risk is silently accepted.

## Recorded decision

Decision needed; the pending decision has not been selected. Therefore, no `DEC-###` identifier is allocated.

## Whole-set recalculation

No decision or requirement revision was supplied after the baseline was formed. All known impacts remain in their current states:

- `IMP-001`: blocked — architecture/repository evidence gap remains.
- `IMP-002`: detected — sequencing risk remains until the pending handoff choice and architecture decisions are recorded.
- `IMP-003`: blocked — clarified requirement and downstream evidence gap remains.
- `IMP-004`: detected — future architecture decisions may require recalculation.

## Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-002`, `IMP-004`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-001`, `IMP-003`
- `new`: none

Categories are mutually exclusive; every known `IMP-###` appears exactly once.

## Stop check and planning handoff

The analysis stops at a report-only planning handoff. Material impacts are not resolved: `IMP-001` and `IMP-003` are blocked by named evidence gaps, while `IMP-002` and `IMP-004` remain detected. The next workflow must record the selected handoff scope and begin architecture only with the clarified requirement as its baseline; after any explicit architecture decision, recalculate the complete impact set.

### Acceptance / regression criteria

| ID | Criterion | Evidence or gap | Relationships |
| --- | --- | --- | --- |
| `AC-001` | Before architecture is complete, the impact report identifies the unsupported functionality, data, interface, authorization/privacy, state/concurrency, operations, compatibility, legal/policy, and regression questions as open or blocked rather than asserting answers. | Evidence gap: no repository or architecture artifacts supplied | Verifies `INV-002`; produced by `IMP-001` |
| `AC-002` | No implementation plan or architecture mechanic is treated as selected before an explicit stakeholder decision is recorded. | Supplied Phase 4-not-started status plus refinement-loop rule | Verifies `INV-002`/`INV-003`; produced by `IMP-002` |
| `AC-003` | The Phase 4 input contains the completed clarification and identifies any missing contract, migration, rollout, and test evidence before those impacts are marked resolved. | Evidence gap: Phase 3 artifact and downstream artifacts not supplied | Verifies `INV-001`; produced by `IMP-003` |
| `AC-004` | After each explicit architecture decision, the full known impact set is recalculated and each impact appears in exactly one delta category. | Refinement-loop rule; future evidence required | Verifies `INV-003`; produced by `IMP-004` |

### Remaining risks and required evidence

The baseline cannot determine the actual affected code paths, public/internal contracts, persistence or migration implications, permission/privacy behavior, concurrency/idempotency guarantees, rollout/rollback needs, compatibility window, legal/policy constraints, or existing regression coverage. Resolve the two blocked impacts by supplying the clarified Phase 3 artifact and the relevant repository/architecture/contract evidence; then record the single pending handoff decision and rerun the complete ledger.
