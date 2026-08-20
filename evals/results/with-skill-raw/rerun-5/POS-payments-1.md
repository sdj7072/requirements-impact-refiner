# POS payments — requirements impact refinement

## Requirement revision

**REQ-001 — Automatic retry of failed charges**

Retry every failed charge automatically. A retry belongs to the same logical
charge attempt and must preserve the existing charge-request contract and the
fact that provider completion may arrive asynchronously. The exact retry
mechanics remain the pending decision.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`. | `verified` | Supplied constraint: “charge requests accept idempotency_key” | `must-preserve` `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement. | `verified` | Supplied fact: “payment status rendered before webhook settlement” | `must-preserve` `REQ-001` |
| `INV-003` | A provider may time out after capture. | `verified` | Supplied fact: “provider may time out after capture” | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Automatic retry after a provider timeout can issue a second capture for the same logical charge if the retry is not deduplicated. | `verified` | `INV-001`; `INV-003` | `refining` | `affects` `REQ-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | The existing idempotency contract may be undermined if retries generate a new key instead of retaining the logical charge’s key; the required key scope and lifetime are not specified. | `inferred` | `INV-001`; no key-scope/lifetime rule supplied | `detected` | `affects` `REQ-001`, `INV-001`; `produces` `AC-002` |
| `IMP-003` | Because status is rendered before webhook settlement, a retried or timed-out charge can be shown as failed or otherwise final before the provider’s captured result is known. | `verified` | `INV-002`; `INV-003` | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-003` |
| `IMP-004` | “Every failed charge” does not define retryable failure classes, attempt limits, delay/backoff, or the terminal state after exhaustion; implementation behavior is therefore under-specified. | `unknown` | No failure taxonomy or retry policy supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Repeated retries can create duplicate customer-visible processing and operational load unless retry attempts are observable and bounded by an explicit policy. | `unknown` | No metrics, alert, or operational retry policy supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-005` |

## Decision needed

Choose the retry-policy mechanics for the pending decision. The requirement
alone does not select an attempt limit, delay, failure classification, or
idempotency-key lifetime.

1. **Bounded automatic retry** — retry only defined transient/unknown failures
   with an explicit attempt limit and backoff; leave permanent failures
   terminal.
2. **Unbounded automatic retry** — keep retrying all failures until a provider
   outcome settles the charge; requires an explicit stop/safety mechanism.
3. **Automatic retry with operator policy** — use a configurable retry
   classifier, limit, and backoff, with exhausted charges routed for review.

No option was selected in the supplied request, so no concrete `DEC-###` is
recorded.

## Recorded decision

**Decision needed.** No stakeholder selection was supplied.

## Whole-set recalculation

No decision has been recorded. All known impacts remain in their current
state; no impact is resolved or accepted by silence. `IMP-001` and `IMP-003`
remain under refinement, `IMP-002` remains detected, and `IMP-004`/`IMP-005`
remain blocked on named policy information.

## Delta

- resolved: none
- mitigated: none
- unchanged: `IMP-001`, `IMP-002`, `IMP-003`
- accepted: none
- deferred: none
- blocked: `IMP-004`, `IMP-005`
- new: none

## Stop check and planning handoff

The refined requirement is `REQ-001`. The pending decision must define the
retry classifier, attempt/backoff policy, terminal behavior, and idempotency
key scope before implementation planning can close the blocked impacts.

### Acceptance and regression criteria

| ID | Criterion | Evidence basis | Links |
| --- | --- | --- | --- |
| `AC-001` | A provider timeout after capture cannot cause a second capture for the same logical charge when automatic retry runs. | `INV-001`, `INV-003`; exact provider/idempotency behavior remains to be validated | verifies `INV-003`; produced by `IMP-001` |
| `AC-002` | Retried requests use a documented idempotency-key policy that prevents duplicate settlement of one logical charge. | `INV-001`; key scope/lifetime is currently unspecified | verifies `INV-001`; produced by `IMP-002` |
| `AC-003` | Before webhook settlement, the UI exposes a non-final/pending state and does not misreport an unresolved timed-out charge as permanently failed. | `INV-002`, `INV-003` | verifies `INV-002`; produced by `IMP-003` |
| `AC-004` | Each failure class has a documented retryability rule, attempt limit/backoff, and terminal outcome. | Policy gap identified by `IMP-004` | produced by `IMP-004` |
| `AC-005` | Retry attempts and exhaustion are observable, and the selected policy prevents uncontrolled retry load. | Operational policy gap identified by `IMP-005` | produced by `IMP-005` |

This is a report-only planning handoff; it contains no implementation
work breakdown.
