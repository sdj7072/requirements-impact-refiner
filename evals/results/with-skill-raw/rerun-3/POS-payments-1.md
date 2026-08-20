# Requirements impact refinement — POS payments

## Requirement revision

**REQ-001 — Retry failed charges automatically.**

The payment system should automatically retry a charge that is known to have
failed, while preserving one logical charge attempt through the request's
`idempotency_key`. A provider timeout after capture must not be treated as a
confirmed failure or retried with a new logical charge until settlement or
reconciliation establishes the outcome. The exact retryable-error set,
attempt limit, backoff, and behavior after an unresolved timeout remain the
pending decision.

This is a refinement of “Retry every failed charge automatically”: “failed”
must mean a confirmed retryable failure, not an ambiguous outcome.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| **INV-001** | Charge requests accept an `idempotency_key`. | `verified` | Supplied fact: “charge requests accept an idempotency_key” | `must-preserve` by `REQ-001` |
| **INV-002** | Payment status can be rendered before webhook settlement. | `verified` | Supplied fact: “payment status is rendered before webhook settlement” | `must-preserve` by `REQ-001` |
| **INV-003** | A provider may time out after capture, leaving the request outcome ambiguous to the caller. | `verified` | Supplied fact: “provider may time out after capture” | `must-preserve` by `REQ-001` |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links / acceptance |
| --- | --- | --- | --- | --- | --- |
| **IMP-001** | Retrying a timed-out request as a new charge can double-capture the payment when the provider captured before the timeout. | `verified` | Supplied provider-timeout-after-capture fact; `INV-003` | `refining` | `affects` `REQ-001`, `INV-003`; `produces` `AC-001` |
| **IMP-002** | The retry path must reuse the same logical `idempotency_key` (or an equivalently stable key) so a retry cannot create a second charge. | `inferred` | `INV-001`; idempotency semantics are not otherwise supplied | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-002` |
| **IMP-003** | Rendering status before webhook settlement can expose a transient failure or non-final state while an automatic retry or settlement is still possible. | `verified` | Supplied pre-webhook-rendering fact; `INV-002` | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-003` |
| **IMP-004** | The requirement does not define which provider errors are retryable; blindly retrying all failures could retry permanent declines or invalid requests. | `unknown` | No retryability/error taxonomy supplied | `blocked` | `affects` `REQ-001`; named gap: provider error classification |
| **IMP-005** | “Automatically” does not define retry count, backoff, maximum elapsed time, or a stopping condition, so repeated attempts and operational load cannot be bounded. | `unknown` | No retry policy, queue, or operational limits supplied | `blocked` | `affects` `REQ-001`; named gap: retry budget and scheduling policy |
| **IMP-006** | The system’s reconciliation behavior when a timeout follows capture is unspecified; duplicate prevention cannot be verified without settlement/webhook correlation semantics. | `unknown` | Provider settlement and webhook-correlation contract not supplied; `INV-003` | `blocked` | `affects` `REQ-001`, `INV-003`; named gap: provider settlement/reconciliation contract |
| **IMP-007** | A pre-settlement status may be overwritten or contradicted by a later webhook unless status transitions distinguish pending, confirmed failure, and settled success. | `inferred` | `INV-002`; webhook settlement is known to occur after rendering, but transition rules are not supplied | `detected` | `affects` `REQ-001`, `INV-002`; `produces` `AC-004` |

### Acceptance and regression criteria

| ID | Criterion | Evidence level | Verifies |
| --- | --- | --- | --- |
| **AC-001** | If the provider may have captured before returning a timeout, the system does not issue a second logical charge; it keeps/reuses the stable idempotency identity and reconciles settlement before any new charge is authorized. | `verified` | `IMP-001`, `INV-003` |
| **AC-002** | An automatic retry carries the same logical `idempotency_key` across attempts, and a new key is never generated merely because the first request timed out. | `inferred` | `IMP-002`, `INV-001` |
| **AC-003** | A status rendered before webhook settlement is explicitly non-final (or otherwise cannot be mistaken for confirmed failure), and later settlement updates it consistently. | `verified` | `IMP-003`, `INV-002` |
| **AC-004** | Webhook settlement cannot regress a settled success to a retryable failure, and a retry cannot race a settlement into a duplicate capture. | `inferred` | `IMP-007`, `INV-002`, `INV-003` |

## Focused decision needed

Which retry policy should refine `REQ-001`?

1. **Conservative payment-safe (recommended):** retry only explicitly retryable
   confirmed failures; reuse the same idempotency key; treat timeout-after-
   capture as pending/reconciliation; use a bounded attempt/time budget.
2. **Bounded broad retry:** retry all provider-declared transient failures
   (including selected timeout responses) with the same idempotency key, but
   stop after a fixed attempt/time budget and surface pending outcomes.
3. **Unbounded “every failure” retry:** retry every failure until success,
   retaining the same idempotency key. This leaves cost, latency, and
   unresolved-provider-outcome risks open.

No stakeholder selection was supplied, so no concrete `DEC-###` is recorded.
No impact is marked `accepted` or `resolved`.

## Recorded decision

**Pending.** The exact retryable-error classification, retry budget/backoff,
and timeout reconciliation policy require one of the options above (or an
explicit alternative). Therefore there is no `DEC-###` to link yet.

## Whole-set recalculation and delta

No decision was recorded; all known impacts remain in the ledger and were
re-evaluated as a complete set:

- **resolved:** none.
- **mitigated:** none.
- **unchanged:** `IMP-001`, `IMP-002`, `IMP-003`, `IMP-007` remain detected/refining; no selected policy has reduced them.
- **accepted:** none (acceptance requires a recorded `DEC-###`).
- **deferred:** none.
- **blocked:** `IMP-004`, `IMP-005`, `IMP-006` remain blocked by the named information gaps.
- **new:** none.

## Stop check and planning handoff

This is a report-only handoff. The refined requirement is `REQ-001`; current
behavior to preserve is `INV-001`–`INV-003`; open impacts are
`IMP-001`–`IMP-007`; and testable criteria are `AC-001`–`AC-004`.

Planning should not begin as if the retry policy were settled. First record
the pending policy decision, then recalculate the complete impact set and
define provider error/reconciliation evidence for the blocked impacts.
