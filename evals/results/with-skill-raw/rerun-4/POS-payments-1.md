# Requirements Impact Refinement — POS payments

## Requirement revision

`REQ-001` — Retry every failed charge automatically.

The revision must define “failed” and the retry boundary for requests whose provider outcome is unknown. Charge requests accept an `idempotency_key`; payment status is rendered before webhook settlement; and the provider may time out after capture. These supplied facts constrain the refinement but do not select a retry count, backoff, terminal-state policy, or user-visible status policy.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Links |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`, so a retry can be correlated with the original charge attempt. | `verified` | Supplied fact: “charge requests accept idempotency_key.” | `must-preserve` `REQ-001` |
| `INV-002` | Payment status may be rendered before webhook settlement is received. | `verified` | Supplied fact: “payment status rendered before webhook settlement.” | `must-preserve` `REQ-001` |
| `INV-003` | A provider timeout can occur after capture, leaving the client without a definitive outcome. | `verified` | Supplied fact: “provider may time out after capture.” | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Blindly retrying an unknown outcome can create a second charge or otherwise duplicate the customer’s payment attempt. | `verified` | Supplied post-capture timeout fact plus `INV-003`; `idempotency_key` is available via `INV-001`, but its provider scope/retention is unspecified. | `refining` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | A status rendered before webhook settlement can show a transient failure while a later webhook settles the original charge, causing incorrect customer messaging or a premature retry. | `verified` | Supplied pre-webhook rendering fact plus `INV-002` and `INV-003`. | `refining` | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | “Every failed charge” does not specify which failure classes are retryable; retrying permanent declines, validation errors, fraud blocks, or configuration failures may repeat an impossible operation. | `unknown` | No failure taxonomy or provider error contract supplied. | `blocked` | `affects` `REQ-001`; `produces` `AC-003` |
| `IMP-004` | Automatic retries need bounded attempts, backoff, and a terminal state; without these, an outage can create an unbounded retry storm and operational load. | `unknown` | No retry budget, scheduler, queue, or operational policy supplied. | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Reconciliation between charge attempts, idempotency keys, and webhook events is required to avoid inconsistent payment records when outcomes arrive out of order. | `inferred` | Inferred from `INV-001`–`INV-003`; no event schema or persistence model supplied. | `detected` | `affects` `REQ-001`, `INV-001`, `INV-002`; `produces` `AC-005` |
| `IMP-006` | Customer and support-facing status must distinguish pending/unknown from definitively failed, otherwise an automatic retry may appear as multiple charges or contradictory receipts. | `inferred` | Inferred from pre-settlement rendering in `INV-002` and post-capture timeout in `INV-003`; copy/state contract not supplied. | `detected` | `affects` `REQ-001`, `INV-002`; `produces` `AC-006` |

## Focused decision

The pending decision is: how should an automatic retry treat a provider timeout after capture when the original payment outcome is unknown?

1. **Reconcile-first (recommended):** mark the attempt pending/unknown, query or await provider settlement using the same idempotency key, and retry only after the original attempt is definitively failed.
2. **Bounded immediate retry:** retry immediately with the same idempotency key, with a fixed bounded attempt count and backoff; retain pending status until settlement.
3. **No automatic retry for unknown outcomes:** automatically retry only explicit, classified failures; route timeout-after-capture cases to reconciliation/manual recovery.

No stakeholder selection is recorded, so no concrete `DEC-###` is created.

## Recorded decision

Decision needed — the pending decision above remains open. The requirement is not sufficiently specific to select retry mechanics or the timeout-after-capture policy.

## Whole-set recalculation

No decision was recorded; all known impacts remain in scope. Initial `refining` and `detected` impacts are unchanged, and the blocked impacts retain their named information gaps.

### Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-002`, `IMP-005`, `IMP-006`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-003`, `IMP-004`
- `new`: none

## Acceptance and regression criteria

| ID | Criterion | Evidence / relationship |
| --- | --- | --- |
| `AC-001` | A retry cannot create a second customer charge when the original provider outcome is unknown; attempts use a stable idempotency correlation and duplicate outcomes are safely collapsed. | Verifies `INV-001`, produced by `IMP-001`. Exact provider idempotency scope remains a validation input. |
| `AC-002` | A pre-webhook failure display cannot trigger a duplicate retry if the original charge later settles; settlement updates the payment state deterministically. | Verifies `INV-002`–`INV-003`, produced by `IMP-002`. |
| `AC-003` | Retry eligibility is explicitly classified, and permanent declines/validation/fraud/configuration failures are not retried unless the provider contract says they are transient. | Produced by `IMP-003`; requires the provider failure taxonomy. |
| `AC-004` | Automatic retries have a finite budget, backoff, terminal state, and observable exhaustion behavior. | Produced by `IMP-004`; requires the selected retry policy. |
| `AC-005` | Reordered, duplicated, and delayed webhooks reconcile to one authoritative payment outcome per charge attempt/idempotency key. | Produced by `IMP-005`; requires event and persistence contracts. |
| `AC-006` | Customer/support status distinguishes pending/unknown, retrying, definitively failed, and settled, without presenting an unknown outcome as a confirmed failure or duplicate charge. | Produced by `IMP-006`. |

## Stop check and planning handoff

Report-only handoff: the refined requirement, preserved invariants, linked impacts, open decision, named information gaps, and acceptance criteria are recorded. Implementation planning should wait for the pending timeout policy, retryable failure taxonomy, retry budget/backoff, and provider/event reconciliation contracts.
