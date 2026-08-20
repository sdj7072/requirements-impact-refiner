# POS-payments-3 — Requirements impact refinement

## Requirement revision

`REQ-001` — Retry every failed charge automatically. A retry must be safe when the provider may have captured the charge but the client received a timeout, and it must preserve the existing idempotency-key contract and the distinction between a provider result and webhook settlement.

This refinement is based on the supplied facts only; no repository inspection was requested for this rerun.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence | Level | Links |
|---|---|---|---|---|
| `INV-001` | Charge requests accept an `idempotency_key`. | Supplied fact: “charge requests accept idempotency_key” | `verified` | must-preserve `REQ-001` |
| `INV-002` | Payment status can be rendered before webhook settlement is received. | Supplied fact: “payment status rendered before webhook settlement” | `verified` | must-preserve `REQ-001` |
| `INV-003` | A provider timeout can occur after capture, so a client-visible failure is not proof that no charge exists. | Supplied fact: “provider may time out after capture” | `verified` | must-preserve `REQ-001` |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links |
|---|---|---|---|---|---|
| `IMP-001` | Retrying a timed-out request with a different idempotency key could create a second capture. | `verified` | `INV-001`, `INV-003`; supplied provider-timeout fact | `refining` | affects `REQ-001`, `INV-001`, `INV-003`; produces `AC-001` |
| `IMP-002` | A retry can race with a late webhook, leaving the rendered payment status inconsistent with the eventual provider settlement. | `verified` | `INV-002`, `INV-003`; supplied status/webhook facts | `detected` | affects `REQ-001`, `INV-002`, `INV-003`; produces `AC-002` |
| `IMP-003` | “Every failed charge” is ambiguous when the provider outcome is unknown; an unbounded or immediate retry policy could amplify charges, load, and provider rate-limit failures. | `inferred` | Derived from `INV-001`–`INV-003`; retry count/backoff and terminal-state policy were not supplied | `detected` | affects `REQ-001`; produces `AC-003` |
| `IMP-004` | Automatic retries require a durable way to correlate attempts and reconcile a late capture; the available facts do not specify storage, worker, or reconciliation behavior. | `unknown` | No repository or architecture evidence supplied for retry persistence/reconciliation | `blocked` | affects `REQ-001`; produces `AC-004` |
| `IMP-005` | Existing consumers may observe an interim failure before webhook settlement and need a stable transition when a later retry or webhook succeeds. | `inferred` | `INV-002`; consumer behavior and compatibility contract were not supplied | `detected` | affects `REQ-001`, `INV-002`; produces `AC-005` |

## Focused decision needed

What should “retry every failed charge automatically” mean when the provider result is unknown after a timeout?

1. **Bounded, idempotent retries (recommended):** reuse the same logical idempotency key, retry with bounded exponential backoff and a maximum attempt/age window, then mark the payment `unknown`/`needs_reconciliation` until webhook or provider lookup resolves it.
2. **Unbounded background retries:** continue retrying with the same logical key until a definitive provider result arrives; requires an explicit operational stop, queue, and alert policy.
3. **Retry only definitive failures:** automatically retry provider-declared retriable failures, but do not issue a new charge request for timeouts; resolve unknown outcomes through webhook/provider reconciliation only.

No user/stakeholder selection is recorded in the supplied request, so no concrete `DEC-###` is created. The pending decision must be recorded before implementation planning.

## Recorded decision

**Decision needed.** No concrete decision ID is recorded.

## Whole-set recalculation

No decision was recorded; all known impacts remain in scope. No impact is resolved or accepted by silence.

## Delta

- resolved: none
- mitigated: none
- unchanged: `IMP-001`, `IMP-002`, `IMP-003`, `IMP-005`
- accepted: none
- deferred: none
- blocked: `IMP-004` (retry persistence/reconciliation design and repository evidence are unavailable)
- new: none

## Stop check and planning handoff

The requirement is refined but not implementation-ready until the pending retry-policy decision is recorded and the blocked persistence/reconciliation gap is addressed. Planning may proceed only with the linked requirement, invariants, impacts, and the following testable criteria.

### Acceptance and regression criteria

- `AC-001` (from `IMP-001`): A retry of a request whose provider outcome is unknown reuses the same logical idempotency key and cannot create two captures for one payment intent.
- `AC-002` (from `IMP-002`): A late webhook and a retry completion are processed idempotently; the rendered status converges to the provider settlement and does not regress due to event ordering.
- `AC-003` (from `IMP-003`): The selected policy defines retriable outcomes, maximum attempts or age, backoff, terminal handling, and rate-limit behavior; tests prove no retry occurs beyond those bounds.
- `AC-004` (from `IMP-004`): Each retry attempt and unknown outcome is durably correlated to the payment intent, and a captured-but-unacknowledged payment can be reconciled without issuing an uncorrelated second charge.
- `AC-005` (from `IMP-005`): A client-visible interim failure has a documented stable transition to success, final failure, or reconciliation-required state when a retry or webhook later resolves the payment.
