# Spec Kit Integration — Requirements Impact Refinement

## Requirement revision

`REQ-001` — Before implementation planning begins, refine the already-clarified Spec Kit requirement by preserving its clarification outcome, recording current behavior and invariants, identifying material impacts with evidence confidence, documenting open risks, and defining testable acceptance criteria. The refinement exits before `speckit.plan`; it does not invoke that workflow or create planning tasks.

Evidence: supplied task state says “Speckit clarify is complete” and “speckit.plan not started.” The clarified requirement artifact itself is not supplied in this evaluation scope.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Spec Kit clarification is complete before this refinement handoff. | `verified` | Supplied task state: “Speckit clarify is complete.” | `must-preserve` by `REQ-001` |
| `INV-002` | Spec Kit planning has not started at this handoff. | `verified` | Supplied task state: “speckit.plan not started.” | `must-preserve` by `REQ-001` |
| `INV-003` | The completed clarification outcome remains the requirement baseline; no replacement requirement is authorized by the supplied state. | `verified` | Spec Kit adapter contract, `Entry`/`Ownership`: consume the resulting requirement and do not repeat completed clarification. | `must-preserve` by `REQ-001` |
| `INV-004` | No concrete transition, compatibility, data, authorization, retry, cache, or migration policy has been selected in the supplied evidence. | `unknown` | No clarified requirement text or stakeholder mechanics selection is supplied. | `must-preserve` by `REQ-001` |

## Impact ledger

| ID | Impact / risk | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Planning can diverge from the completed clarification outcome if the authoritative clarification artifact is not carried into the handoff. | `verified` | Supplied state establishes clarification complete and planning not started; the adapter `Entry` and `Output` require consuming and preserving that requirement. | `refining` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | Functional, data, interface, authorization/privacy, state/concurrency, operations, compatibility, legal/policy, and regression impacts cannot be assessed from phase status alone. | `unknown` | The clarified requirement, repository sources, schemas, tests, deployment evidence, and policy artifacts are not supplied in scope. | `blocked` | `affects` `REQ-001`; `produces` `AC-002` |
| `IMP-003` | Starting `speckit.plan` before this report is handed off could convert unexamined impacts into untracked planning assumptions. | `inferred` | Supplied ordering says clarification is complete while planning has not started; the adapter `Exit` is explicitly before `speckit.plan`. | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-003` |
| `IMP-004` | A concrete decision about mechanics cannot be recorded without an explicit stakeholder selection; silence cannot be treated as acceptance. | `verified` | Requirements-impact-refiner evidence model requires an explicit selection for `DEC-###`; supplied state contains only phase status. | `blocked` | `affects` `REQ-001`, `INV-004`; `produces` `AC-004` |

## One focused decision

Decision needed: which artifact is the authoritative clarified requirement input for this refinement and the later planning handoff?

1. The completed `speckit.clarify` output (recommended): preserve its decisions as the source of truth and identify it by path or stable artifact ID.
2. A separately supplied requirement/specification artifact: use it only after its relationship to the completed clarification is explicitly identified.
3. Proceed with workflow-state-only planning: carry the missing requirement and impact evidence as blocked gaps.

No concrete `DEC-###` is recorded because the supplied evidence does not select an option or any transition mechanics.

## Recorded decision

No recorded decision. The pending decision is the authoritative clarified requirement input. The external Spec Kit workflow is not automatically invoked, and no `speckit.plan` work is started.

## Whole-set recalculation

No decision was supplied. All known impacts remain in their current states; none is accepted or resolved by silence.

### Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-003`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-002`, `IMP-004`
- `new`: none

Every known `IMP-###` appears exactly once in the delta categories.

## Stop check and Planning Handoff

This is a report-only handoff to the selected Spec Kit workflow. The impact refiner has consumed the phase-state evidence, preserved the completed clarification as the baseline, and stopped before `speckit.plan`. The clarified requirement artifact must be identified before the blocked product and integration impacts can be resolved; no implementation work breakdown or plan is created here.

### Open risks and evidence gaps

- The completed clarification output is not identified, so requirement-level decisions and scope cannot be traced.
- Repository behavior, contracts, data, permissions, operations, and regression coverage were not supplied; their impacts remain unknown.
- No stakeholder selection of transition or compatibility mechanics is recorded.

### Acceptance / regression criteria

| ID | Criterion | Level | Supporting evidence / gap | Links |
| --- | --- | --- | --- | --- |
| `AC-001` | The planning input identifies the completed clarification artifact and preserves its decisions without re-running general clarification. | `unknown` | Phase status is supplied, but the artifact identifier and contents are absent. | verifies `INV-001`, `INV-003`; produced by `IMP-001` |
| `AC-002` | Each material impact is classified with evidence, and unsupported functional, data, interface, authorization/privacy, state/concurrency, operations, compatibility, legal/policy, and regression claims remain explicitly unknown or blocked. | `unknown` | No requirement or repository evidence is supplied for assessment. | verifies `REQ-001`; produced by `IMP-002` |
| `AC-003` | No `speckit.plan` work is considered started before this report and its open risks are visible to the planning workflow. | `verified` | Supplied state says planning has not started; the downstream gate still needs confirmation. | verifies `INV-002`; produced by `IMP-003` |
| `AC-004` | Any selected transition or policy mechanics are traceable to an explicit stakeholder choice recorded as `DEC-###`; absent a choice, the risk remains blocked. | `verified` | Evidence model requires explicit selection and forbids silent acceptance; no selection is supplied. | verifies `INV-004`; produced by `IMP-004` |

