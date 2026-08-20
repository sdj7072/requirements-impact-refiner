# Requirements Impact Refinement: POS-payments-5

## Requirement revision

`REQ-001` — Automatically retry a failed charge, while preserving payment correctness and avoiding a second capture when the provider may already have captured the original request. A retry must be correlated to the original charge and remain safe when provider responses are delayed or lost.

Scope is limited to charge-attempt retry behavior. The request does not define retry eligibility, attempt limits, backoff, terminal states, or the source of truth for an uncertain provider outcome; those remain the pending decision.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`. | `verified` | Supplied repository fact: charge requests accept an `idempotency_key` | `must-preserve` by `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement. | `verified` | Supplied repository fact: payment status is rendered before webhook settlement | `must-preserve` by `REQ-001` |
| `INV-003` | The provider may time out after capture, so a timeout does not prove that no charge occurred. | `verified` | Supplied repository fact: provider may time out after capture | `must-preserve` by `REQ-001` |

## Impact ledger

| ID | Severity | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Critical | Retrying with a new or missing idempotency key can create a duplicate capture when the first request timed out after capture. | `verified` | `INV-001`, `INV-003` | `refining` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | High | A pre-webhook status render can show a failed or pending-looking result while a retry is being scheduled, then be contradicted by webhook settlement. | `verified` | `INV-002`, `INV-003` | `refining` | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | High | The phrase “every failed charge” does not establish whether an ambiguous timeout is retryable; treating all non-success responses as failed risks retrying an already-captured charge. | `inferred` | `INV-003`; retry eligibility is not specified | `detected` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | High | Without a bounded attempt count and backoff, automatic retry can cause repeated provider calls, duplicate customer-facing activity, and an avoidable retry storm during an outage. | `unknown` | No attempt limit, backoff, or outage policy supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Medium | Settlement and retry processing may race; the system needs one authoritative terminal outcome so a late webhook cannot reopen a completed charge or make a retry appear successful twice. | `inferred` | `INV-002`, `INV-003`; state-transition rules not supplied | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-005` |
| `IMP-006` | Medium | Provider-specific idempotency-key retention and replay semantics are not supplied, so safety across retries beyond the provider’s retention window is unknown. | `unknown` | Local request contract states key acceptance, but provider retention/semantics are unavailable | `blocked` | `affects` `REQ-001`, `INV-001`; `produces` `AC-006` |

## One focused decision

The pending decision is: what policy should govern an automatic retry when the outcome is uncertain (especially a timeout after possible capture)?

1. **Reconcile before retry (recommended):** reuse the same idempotency key and query/reconcile the provider outcome; retry only after the provider confirms the attempt was not captured, with a bounded exponential backoff and attempt limit.
2. **Retry all transport/application failures:** reuse the same idempotency key for a bounded number of retries, treating the provider’s idempotency behavior as the duplicate-capture guard; this requires confirmed provider retention semantics.
3. **Do not automatically retry ambiguous outcomes:** automatically retry only explicit, provider-confirmed declines/transient failures; route timeouts after possible capture to reconciliation/manual recovery.

No stakeholder selection was supplied, so no `DEC-###` is recorded and no impact is marked `accepted`.

## Recorded decision

None recorded. The pending decision above must be selected before the requirement can be treated as fully refined.

## Whole-set recalculation

No decision changed the requirement in this pass. All known impacts remain in scope and were re-evaluated as a complete set.

### Delta

- `resolved: none`
- `mitigated: none`
- `unchanged: ` `IMP-001`, `IMP-002`, `IMP-003`, `IMP-005` (remain `refining`/`detected`)
- `accepted: none` (no recorded decision)
- `deferred: none`
- `blocked: ` `IMP-004`, `IMP-006`
- `new: none`

## Acceptance and regression criteria

| ID | Criterion | Evidence target | Verifies |
| --- | --- | --- | --- |
| `AC-001` | A retry of an attempt that may have been captured cannot create a second capture; the original idempotency key is preserved or the selected reconciliation policy proves the original was not captured before a new attempt. | Provider-call integration test covering timeout-after-capture and retry | `IMP-001`, `INV-001`, `INV-003` |
| `AC-002` | UI/payment status remains consistent with the eventual webhook settlement and clearly represents an in-progress or uncertain retry state rather than asserting a final failure prematurely. | End-to-end status/webhook ordering test | `IMP-002`, `INV-002` |
| `AC-003` | Explicit declines/transient failures and ambiguous post-capture timeouts follow distinct retry eligibility rules; an ambiguous timeout is not classified as a safe retry solely because no response arrived. | State-transition and provider-outcome matrix test | `IMP-003`, `INV-003` |
| `AC-004` | Automatic retries are bounded by a documented attempt limit and backoff, and exhaustion reaches a terminal recoverable state without an unbounded loop. | Retry scheduler test plus outage/failure simulation | `IMP-004` |
| `AC-005` | A late webhook and a retry completion are idempotent and converge on one terminal payment outcome; neither can reopen or double-settle the charge. | Concurrent webhook/retry race test | `IMP-005` |
| `AC-006` | The selected design documents and tests provider idempotency-key retention/replay behavior for the full retry window, or uses reconciliation/manual recovery when that guarantee is unavailable. | Provider contract evidence and integration test | `IMP-006` |

## Stop check and planning handoff

The refined requirement, preserved invariants, complete impact ledger, open information gaps, and acceptance criteria are ready for the planning workflow. Refinement stops here because the retry policy for ambiguous outcomes and the provider’s idempotency retention semantics are not selected or evidenced. `IMP-004` and `IMP-006` remain blocked; the remaining impacts are not resolved or accepted. No imperative implementation plan is included.
