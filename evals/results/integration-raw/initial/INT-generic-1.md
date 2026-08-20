# Requirements Impact Refinement Report

## Context and workflow boundary

- **Selected mode:** `generic`.
- **Entry:** The request says the requirement is approved and asks for repository-impact refinement before planning.
- **Exit:** This report is a planning handoff only. It does not invoke an external orchestration framework and does not create implementation tasks.
- **Supplied evidence:** “the requirement is approved”; “no named orchestration framework is active.”
- **Inspection scope:** No approved requirement text, repository paths, diff, tests, schema, or contract were supplied in this handoff. Claims about current behavior and concrete change impacts therefore remain unknown rather than inferred.

## Requirement revision

`REQ-001` — Refine the approved requirement against the repository before the user starts their chosen planning workflow. Preserve the approved requirement’s intended behavior and identify affected contracts, data, permissions, compatibility, operational concerns, and regression criteria. The approved requirement text itself is not present in the supplied evidence, so no more specific revision is asserted here.

`REQ-001` is **not** a recorded mechanics choice. Approval establishes that the requirement may proceed to refinement; it does not select an API transition, migration, retry policy, rollout, or other implementation policy.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `INV-001` | The current behavior that the approved requirement must preserve cannot be identified from the supplied handoff. | `unknown` | No repository artifact or approved requirement text supplied; only the evidence statement “the requirement is approved.” | `blocked` | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | The affected functionality, data, interfaces, authorization/privacy boundaries, state/concurrency behavior, operations, compatibility promises, and regression surface cannot be assessed because the approved requirement and repository evidence are absent. | `unknown` | No requirement body, repository path, diff, test, schema, contract, or deployment artifact was supplied. | `blocked` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | A material impact may be missed if refinement proceeds without the approved requirement text and the relevant repository scope. | `unknown` | The handoff identifies approval but supplies no content or inspection target. | `blocked` | `affects` `REQ-001`; `produces` `AC-002` |

### Focused evidence-gap question

Please provide the approved requirement text and the repository scope that implements or consumes it (for example, a path, diff, API/schema identifier, or named service). This is an evidence request, not a selection among implementation policies; no `DEC-###` is recorded.

## Recorded decision

**Decision needed:** No concrete decision is recorded. The supplied approval is not an explicit selection of transition, compatibility, migration, authorization, retry, rollout, or rollback mechanics.

## Whole-set recalculation

No decision or requirement revision with implementation mechanics was supplied. The complete known impact set remains `IMP-001`, `IMP-002`; no impacts are superseded or newly introduced.

## Delta

- **resolved:** none
- **mitigated:** none
- **unchanged:** none
- **accepted:** none
- **deferred:** none
- **blocked:** `IMP-001`, `IMP-002`
- **new:** none

## Acceptance and regression criteria

| ID | Criterion | Level | Evidence / gap | Links |
| --- | --- | --- | --- | --- |
| `AC-001` | After the requirement text and repository scope are supplied, every material affected behavior and preserved invariant is identified and linked to evidence before planning begins. | `unknown` | Validation target derived from blocked `IMP-001`; current coverage cannot be verified without artifacts. | produced by `IMP-001`; verifies `REQ-001`, `INV-001` |
| `AC-002` | Refinement does not proceed to implementation planning while the approved requirement or relevant repository scope is missing; the missing inputs are named in the handoff. | `verified` | This report names both missing inputs and stops before implementation planning. | produced by `IMP-002`; verifies `REQ-001` |

## Stop check and planning handoff

The refinement stops at a report-only handoff because the two material impacts are blocked by named information gaps. No risk is silently accepted, and no concrete decision ID is created. Once the approved requirement text and repository scope are supplied, the generic workflow can recalculate the complete ledger and produce evidence-backed acceptance criteria. The resulting report should then be handed to the user’s chosen planning method; this report does not start that method automatically.
