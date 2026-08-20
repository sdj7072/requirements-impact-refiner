# Requirements-impact refinement: generic integration baseline

## Requirement revision

`REQ-001` — Refine the already-approved requirement into a planning-ready statement for the user’s own workflow, preserving its approved intent and supplied constraints. The refinement must remain framework-neutral: no orchestration framework, adapter, connector, or framework-specific integration is selected or presumed.

Scope is evidence-limited because the approved requirement’s text, affected product area, and repository location were not supplied in this integration request.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | The requirement has already been approved and must be treated as the baseline intent rather than silently rewritten. | `verified` | Supplied evidence: “the requirement is approved” | `must-preserve` `REQ-001` |
| `INV-002` | No named orchestration framework is active; the refinement must not introduce framework-specific mechanics or adapter references. | `verified` | Supplied evidence: “no named orchestration framework is active”; request for a “fresh integration baseline without adapter references” | `must-preserve` `REQ-001` |
| `INV-003` | Existing product behavior, contracts, data, permissions, and compatibility guarantees remain unassessed until the approved requirement and affected repository scope are available. | `unknown` | No requirement text or repository evidence supplied; no repository inspection performed for this baseline | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Potential impact / uncertainty | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | The intended product change and its affected behavior cannot be determined from the approval status alone. | `unknown` | Approved requirement text and affected scope unavailable | `blocked` | `affects` `REQ-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | Data, interface, authorization/privacy, concurrency, operations, compatibility, policy, and regression effects cannot be assessed without a named scope and repository evidence. | `unknown` | No source, schema, contract, configuration, or test evidence supplied; inspection was intentionally limited to the skill’s core references | `blocked` | `affects` `REQ-001`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | A later planning handoff could accidentally add adapter or orchestration-framework coupling despite no active framework selection. | `inferred` | Supplied framework-neutrality constraint; no concrete plan or integration target exists yet | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-003` |

## One focused decision

The pending decision is what authoritative content and scope should be used to refine the approved requirement:

1. Supply the approved requirement text or identifier (recommended), allowing intent and acceptance targets to be refined without guessing.
2. Supply the affected repository path, contract, or specification, allowing repository-backed impact analysis.
3. Proceed with an evidence-limited, framework-neutral handoff and explicitly carry all unassessed impacts as blocked.

No explicit option was selected in the supplied request. Therefore, no concrete `DEC-###` is recorded.

## Recorded decision

Decision needed: the pending decision above remains open. Approval of the requirement does not select an implementation mechanism, orchestration framework, adapter, or compatibility policy.

## Whole-set recalculation

Because no decision was recorded and no requirement or repository evidence was added, the complete known impact set remains `IMP-001`, `IMP-002`, and `IMP-003`:

- `IMP-001`: remains `blocked` pending the approved requirement’s content and scope.
- `IMP-002`: remains `blocked` pending authoritative repository/specification evidence.
- `IMP-003`: remains `refining`; framework-neutrality is retained as a constraint, but no implementation choice has been made.

## Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-003`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-001`, `IMP-002`
- `new`: none

## Acceptance criteria

| ID | Criterion | Evidence / gap | Relationships |
| --- | --- | --- | --- |
| `AC-001` | The refined requirement identifies the approved intent, affected scope, and preserved behavior without inventing missing product semantics. | Gap: approved requirement text and scope are unavailable | verifies `REQ-001`, produced by `IMP-001` |
| `AC-002` | Before planning, material data, interface, authorization/privacy, state/concurrency, operations, compatibility, policy, and regression impacts are assessed or explicitly named as blocked. | Gap: repository/specification evidence is unavailable | verifies `INV-003`, produced by `IMP-002` |
| `AC-003` | The planning handoff contains no adapter references, connector assumptions, or framework-specific orchestration mechanics unless explicitly selected later. | Supported by the supplied framework-neutrality constraint; no concrete plan exists yet | verifies `INV-002`, produced by `IMP-003` |

## Stop check and planning handoff

This refinement stops at a report-only handoff. `IMP-001` and `IMP-002` are blocked by named information gaps; `IMP-003` remains under refinement. The planning workflow may proceed only with this evidence-limited baseline, or after the pending decision supplies the approved requirement and/or affected scope. No work breakdown or implementation plan is created here, and no adapter or orchestration framework is referenced.
