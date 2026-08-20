# Requirements Impact Report — POS-payments-5

## Requirement revision

`REQ-001` — “Retry every failed charge automatically.”

Refined requirement: automatically retry only a charge attempt whose failure is confirmed as retryable; preserve the logical charge’s `idempotency_key`; do not treat a pre-webhook status or a provider timeout after possible capture as proof that a new capture is safe; reconcile the original outcome before any retry that could create another capture. Retryable-error classification, backoff, attempt/time limits, and terminal user-visible outcomes remain the pending decision.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`. | `verified` | Supplied fact: “charge requests accept an idempotency_key” | `must-preserve` by `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement. | `verified` | Supplied fact: “payment status is rendered before webhook settlement” | `must-preserve` by `REQ-001` |
| `INV-003` | The provider may time out after capture; therefore a timeout does not prove that no capture occurred. | `verified` | Supplied fact: “provider may time out after capture” | `must-preserve` by `REQ-001` |

## Impact ledger

| ID | Requirement | Category | Severity | Finding | Evidence level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | State/concurrency | Critical | Retrying with a new or missing key after a post-capture timeout can create a duplicate capture for one logical charge. | `verified` | `INV-001` and `INV-003` | `refining` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | `REQ-001` | Interfaces / state | High | A status rendered before webhook settlement may be provisional and can be contradicted by a later settlement; it cannot alone authorize a retry. | `verified` | `INV-002` and `INV-003` | `refining` | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | `REQ-001` | Functionality / regression | High | “Every failed” does not define retry eligibility; blindly retrying declines, validation, fraud, permanent provider errors, or ambiguous timeouts can change terminal behavior or duplicate a charge. | `inferred` | Requirement wording plus `INV-003`; no provider error taxonomy supplied | `detected` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | `REQ-001` | Operations / state | High | No attempt cap, overall time window, backoff, jitter, queue, cancellation, or outage behavior is supplied, so retry storms and unbounded work cannot be assessed. | `unknown` | No retry-budget or operational contract supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | `REQ-001` | Interfaces / state | High | Retry processing can race with webhook settlement; without an authoritative, idempotent transition rule, a late webhook could conflict with or duplicate the retry result. | `unknown` | `INV-002` and `INV-003`; webhook ordering/deduplication contract not supplied | `blocked` | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-005` |
| `IMP-006` | `REQ-001` | Compatibility / interfaces | Medium | Provider idempotency-key retention and replay semantics are unknown, so reuse may not protect the full retry window without provider evidence. | `unknown` | Local acceptance fact only; provider contract unavailable | `blocked` | `affects` `REQ-001`, `INV-001`; `produces` `AC-006` |

## One focused decision

Choose the policy for a failed or indeterminate charge attempt:

1. **Reconcile before retry (recommended):** retry only explicitly retryable failures; reuse the logical charge’s key; use bounded exponential backoff; reconcile provider status/webhook after an ambiguous timeout before any new capture attempt.
2. **Bounded same-key retry:** retry provider/client failures for a fixed limit using the same key, relying on confirmed provider idempotency retention; reconcile webhook settlement afterward.
3. **Conservative recovery:** automatically retry only failures confirmed before provider submission; route post-submission timeouts to pending reconciliation/manual recovery rather than a new automatic capture.

**Recorded decision:** none. The request supplies the requirement and three facts but does not select a policy, error taxonomy, retry budget, reconciliation source, or terminal status. No concrete `DEC-###` is created, and no impact is `accepted`.

## Whole-set recalculation

No decision was recorded, so every known impact was re-evaluated and remains in the complete set.

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-002`, `IMP-003` (initially `refining`/`detected`)
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`, `IMP-005`, `IMP-006`
- `new`: none

## Acceptance and regression criteria

| ID | Criterion | Evidence/test target | Produced by |
| --- | --- | --- | --- |
| `AC-001` | A provider timeout after capture followed by retry produces at most one capture for the logical charge, and the original idempotency key is preserved for the same logical attempt. | Provider stub/integration replay test | `IMP-001` |
| `AC-002` | A pre-webhook rendered status is not treated as proof of non-capture; webhook settlement can advance the payment to its authoritative state without contradictory terminal UI. | Status-before-webhook integration test | `IMP-002` |
| `AC-003` | Explicit retryable failures, permanent failures, and ambiguous post-capture timeouts follow distinct selected rules; ambiguous outcomes are not blindly retried. | Provider error/state-transition matrix test | `IMP-003` |
| `AC-004` | Retry attempts obey the selected attempt/time cap, backoff/jitter, queue, cancellation, and observability controls, and exhaustion reaches a durable terminal state. | Retry-budget and outage simulation test | `IMP-004` |
| `AC-005` | Duplicate, out-of-order, and late success webhooks race safely with retries and converge to one authoritative payment outcome without duplicate settlement or duplicate enqueueing. | Concurrent webhook/retry integration test | `IMP-005` |
| `AC-006` | Provider idempotency-key retention/replay semantics are evidenced for the full retry window, or the design uses reconciliation/manual recovery when that guarantee is unavailable. | Provider contract evidence and integration test | `IMP-006` |

## Unresolved, deferred, and blocked items

| Impact | State | Gap | Owner |
| --- | --- | --- | --- |
| `IMP-001` | `refining` | Need selected duplicate-capture and same-key retry policy. | Payment owner |
| `IMP-002` | `refining` | Need authoritative status semantics while settlement is outstanding. | Product/payment owner |
| `IMP-003` | `detected` | Need retryable-error taxonomy and terminal outcomes. | Product/payment owner |
| `IMP-004` | `blocked` | Need retry budget, backoff, cap, cancellation, and operational controls. | Operations owner |
| `IMP-005` | `blocked` | Need webhook authentication, ordering, deduplication, and reconciliation contract. | Payment integration owner |
| `IMP-006` | `blocked` | Need provider retention/replay guarantees for idempotency keys. | Provider integration owner |

## Analysis scope and limitations

Only the three supplied facts were inspected. No repository implementation, provider documentation, webhook schema, error taxonomy, operational policy, or tests were supplied; claims beyond those facts are therefore marked `inferred` or `unknown` as applicable. Missing tests are a validation gap, not evidence of coverage.

## Stop check and planning handoff

This is a report-only planning handoff. `REQ-001`, preserved `INV-001`–`INV-003`, impacts `IMP-001`–`IMP-006`, open risks, and `AC-001`–`AC-006` are recorded. The pending retry-policy decision and blocked provider/webhook/operations evidence must be supplied before implementation planning; no imperative work breakdown is included.
