# Integration Impact Report — Claude Feature-Dev

## Requirement revision

`REQ-001` — Analyze the change impact after feature-dev clarification has completed, preserving the clarified feature intent and producing a report-only handoff suitable for the next planning workflow. The report must identify current behavior and invariants, impacts with evidence confidence, open decisions or information gaps, and testable acceptance criteria. It must not perform or assume Phase 4 architecture design.

Supplied evidence: feature-dev Phase 3 is complete; feature-dev Phase 4 architecture has not started.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Feature-dev clarification is complete and is the current requirements baseline. | `verified` | Supplied case evidence: “feature-dev Phase 3 is complete” | `must-preserve` by `REQ-001` |
| `INV-002` | Feature-dev Phase 4 architecture has not started; no architecture decision or mechanic is selected. | `verified` | Supplied case evidence: “Phase 4 architecture has not started” | `must-preserve` by `REQ-001` |
| `INV-003` | This activity returns a canonical impact report and stops at a planning handoff; it does not create an implementation work breakdown. | `verified` | Claude feature-dev adapter, `Output`/`Exit`; refinement-loop stop rule | `must-preserve` by `REQ-001` |

No Phase 3 artifact, repository source, test, schema, contract, or architecture artifact was supplied or inspected. Behavior-specific impacts therefore remain unknown.

## Impact ledger

| ID | Potential impact | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Functionality, data, interface, authorization/privacy, state/concurrency, operations, compatibility, legal/policy, and regression effects cannot be assessed from phase-status evidence alone. | `unknown` | No repository or architecture evidence supplied; Phase 4 has not started | `blocked` | `affects` `REQ-001`, `INV-002`; `produces` `AC-001` |
| `IMP-002` | Beginning architecture or implementation planning before decisions are recorded could encode unselected mechanics or diverge from the clarified requirement. | `inferred` | Phase 4 is explicitly not started; refinement-loop decision rule | `detected` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | The completed clarification may omit downstream contract, migration, rollout, or test obligations because no Phase 3 artifact or downstream evidence is available for comparison. | `unknown` | Phase 3 completion supplied, but no clarified-requirement artifact or downstream evidence supplied | `blocked` | `affects` `REQ-001`, `INV-001`; `produces` `AC-003` |
| `IMP-004` | A later Phase 4 architecture decision may materially revise this baseline and require the complete impact set to be recalculated. | `inferred` | Refinement-loop recalculation rule; architecture is pending | `detected` | `affects` `REQ-001`, `INV-002`; `produces` `AC-004` |

## One focused decision

The pending decision is the evidence scope to carry into the Phase 4 handoff:

1. **Architecture-first handoff:** begin Phase 4 with `IMP-001` and `IMP-003` explicitly blocked, then recalculate after architecture decisions.
2. **Evidence-first refinement:** supply the clarified Phase 3 artifact and relevant repository, contract, and test evidence before Phase 4.
3. **Narrow-scope handoff:** architect only the explicitly clarified behavior and defer unobserved cross-cutting impacts.

No option was selected in the supplied request. No concrete `DEC-###` is allocated, and no risk is silently accepted.

## Recorded decision

Decision needed; the pending decision has not been selected. No `DEC-###` is recorded.

## Whole-set recalculation

No decision or requirement revision was supplied after the baseline. All known impacts remain unchanged in their current states: `IMP-001` and `IMP-003` remain blocked by named evidence gaps; `IMP-002` and `IMP-004` remain detected sequencing/recalculation risks.

## Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-002`, `IMP-004`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-001`, `IMP-003`
- `new`: none

Categories are mutually exclusive; every known `IMP-###` appears exactly once.

## Stop check and Planning Handoff

The Claude feature-dev adapter owns this report after Phase 3 clarification and exits before Phase 4 architecture. The analysis stops here: it does not repeat general clarification, invoke architecture design automatically, or author implementation tasks. The next workflow may begin Phase 4 only with the clarified requirement as its baseline, the selected handoff scope recorded, and the blocked evidence gaps visible; after each explicit architecture decision, recalculate the complete impact set.

### Acceptance / regression criteria

| ID | Criterion | Evidence or gap | Relationships |
| --- | --- | --- | --- |
| `AC-001` | Before architecture is complete, unsupported functionality, data, interface, authorization/privacy, state/concurrency, operations, compatibility, legal/policy, and regression questions are identified as open or blocked rather than asserted. | No repository or architecture artifacts supplied | Verifies `INV-002`; produced by `IMP-001` |
| `AC-002` | No architecture mechanic or implementation plan is treated as selected before an explicit stakeholder decision is recorded. | Phase 4-not-started evidence plus refinement-loop rule | Verifies `INV-002`/`INV-003`; produced by `IMP-002` |
| `AC-003` | The Phase 4 input contains the completed clarification and identifies missing contract, migration, rollout, and test evidence before those impacts are marked resolved. | Phase 3 artifact and downstream artifacts not supplied | Verifies `INV-001`; produced by `IMP-003` |
| `AC-004` | After each explicit architecture decision, the full known impact set is recalculated and each impact appears in exactly one delta category. | Refinement-loop rule; future evidence required | Verifies `INV-003`; produced by `IMP-004` |

### Remaining risks and required evidence

The actual affected code paths, contracts, persistence/migration implications, permission/privacy behavior, concurrency/idempotency guarantees, rollout/rollback needs, compatibility window, legal/policy constraints, and regression coverage remain unknown. Resolve `IMP-001` and `IMP-003` by supplying the clarified Phase 3 artifact and relevant repository/architecture/contract/test evidence; then record the one pending handoff decision and rerun the complete ledger.
