# POS-payments — Requirements Impact Refinement (decision needed)

## Requirement revision

`REQ-001`: Retry every failed charge automatically, while preserving the existing idempotency contract, keeping the pre-webhook payment state accurate, and preventing a timeout after capture from becoming a duplicate capture. The exact retry and reconciliation policy remains the pending decision.

## Current behavior and preserved invariants

| ID | Invariant | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`. | `verified` | Supplied fact: charge requests accept an `idempotency_key`. |
| `INV-002` | Payment status is rendered before webhook settlement. | `verified` | Supplied fact: payment status is rendered before webhook settlement. |
| `INV-003` | The provider may time out after capture. | `verified` | Supplied fact: the provider may time out after capture. |

## Impact ledger

| ID | Category | Severity | Finding | Evidence | State |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | State / idempotency / retries | high | Retrying after a timeout-after-capture can create a duplicate capture unless the retry remains correlated with the original logical charge. | `INV-001`, `INV-003` | `refining` |
| `IMP-002` | Payments / state | high | Treating every timeout as a definitive failure can trigger another charge even though the original request may already have captured. | `INV-003` | `refining` |
| `IMP-003` | User-visible state / regression | high | Pre-webhook status can contradict eventual settlement if pending, retrying, success, and terminal failure are not distinct. | `INV-002` | `detected` |
| `IMP-004` | Operations / retries | medium | “Every failed charge” does not define retryable classes, attempt limits, backoff, or terminal handling. | Request omits policy | `blocked` |
| `IMP-005` | External interface / compatibility | high | Provider idempotency-key scope/retention and status-reconciliation behavior after timeout are unavailable. | No provider contract supplied | `blocked` |

## Focused decision needed — `NEEDS_DECISION`

When a charge request times out after the provider may already have captured it, select a retry/reconciliation policy:

1. **Conservative reconciliation (recommended):** retry only confirmed retryable failures; treat timeout outcomes as unknown, reconcile provider status/webhook first, and keep payment pending until settlement.
2. **Same-key retry:** retry transport/timeout outcomes with the original `idempotency_key`, relying on the provider to return the original result; confirm key scope and retention.
3. **New-key retry:** retry with a new key, accepting duplicate-capture risk and requiring compensating reconciliation/refund handling.

The policy must also specify retry bounds, backoff, and terminal handling. No `DEC-###` is recorded until selected.

## Acceptance and regression criteria (proposed)

| ID | Criterion | Evidence / gap |
| --- | --- | --- |
| `AC-001` | One logical payment cannot produce two provider captures when the original request times out after capture. | Idempotency/timeout facts supplied; provider enforcement and tests unavailable. |
| `AC-002` | An ambiguous timeout is not treated as a definitive failure until provider settlement is reconciled. | Timeout fact supplied; policy pending. |
| `AC-003` | Pre-webhook UI distinguishes pending/retrying from terminal success/failure and converges with webhook settlement. | Pre-webhook fact supplied; state-transition tests unavailable. |
| `AC-004` | Retry classes, maximum attempts, backoff, and terminal behavior are explicit and bounded. | Missing from request. |
| `AC-005` | Provider evidence establishes idempotency-key scope/retention and supported reconciliation after timeout. | Provider contract unavailable. |

## Stop check / planning handoff

Stop at this decision gate. Do not hand off to implementation planning until a retry/reconciliation policy is selected and the complete impact set is recalculated.

---

## User revision — `DEC-001`

The user selected: “Retry only when settlement is unknown, reuse the original idempotency key, reconcile provider state before retry, and keep the UI pending until settlement.”

## Refined requirement

`REQ-001` is refined to: Retry only when settlement is unknown, and only after reconciling provider state. Reuse the original `idempotency_key` for any permitted retry. Keep the payment UI pending until settlement is known. Do not treat unknown settlement as an ordinary definitive failure or issue an uncorrelated new capture.

## Recorded decision

`DEC-001`: The user selected reconciliation before retry, original-key reuse, and a pending UI until settlement. This decision mitigates duplicate-capture and premature-status risks; it does not establish provider key retention/enforcement or retry bounds.

## Whole-set recalculation

| ID | Recalculated impact | Evidence level | State | Evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Original-key reuse plus provider reconciliation before retry materially reduces duplicate-capture risk for timeout-after-capture; provider enforcement remains a validation dependency. | `inferred` | `mitigated` | `DEC-001` + `INV-001` + `INV-003`; provider semantics not supplied. | affects `REQ-001`, `INV-001`, `INV-003`; mitigated by `DEC-001`; produces `AC-001` |
| `IMP-002` | Unknown settlement is reconciled before retry and is not blindly treated as definitive failure. | `verified` | `resolved` | Explicit policy in `DEC-001` + timeout fact `INV-003`. | affects `REQ-001`, `INV-003`; resolved by `DEC-001`; produces `AC-002` |
| `IMP-003` | UI remains pending until settlement, avoiding premature terminal success/failure and converging with webhook state. | `verified` | `resolved` | Explicit policy in `DEC-001` + pre-webhook fact `INV-002`. | affects `REQ-001`, `INV-002`; resolved by `DEC-001`; produces `AC-003` |
| `IMP-004` | Retryable error classes, attempt limits, backoff, and terminal handling remain unspecified. | `unknown` | `blocked` | `REQ-001` and `DEC-001` do not define bounds or definitive-failure policy. | affects `REQ-001`; produces `AC-004` |
| `IMP-005` | Provider preservation/honoring of the original key and support for reconciliation remain unverified. | `unknown` | `blocked` | No provider contract or SDK behavior supplied. | affects `REQ-001`; produces `AC-005` |

## Delta after `DEC-001`

- `resolved`: `IMP-002`, `IMP-003`
- `mitigated`: `IMP-001`
- `unchanged`: none
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`, `IMP-005`
- `new`: none

## Acceptance criteria after recalculation

| ID | Criterion | Evidence / remaining gap |
| --- | --- | --- |
| `AC-001` | A timeout-after-capture retry reuses the original idempotency key and cannot create an unintended second capture for the same logical payment. | `IMP-001` mitigated; provider enforcement remains unverified. |
| `AC-002` | Unknown settlement is reconciled before retry and never blindly treated as definitive failure. | `IMP-002` resolved by `DEC-001`. |
| `AC-003` | UI remains pending until settlement is known and then converges with provider/webhook result. | `IMP-003` resolved by `DEC-001`. |
| `AC-004` | Retry classification, maximum attempts, backoff, and terminal handling are explicit and bounded. | `IMP-004` blocked; policy unspecified. |
| `AC-005` | Provider evidence confirms original-key retention/semantics and supported reconciliation path. | `IMP-005` blocked; provider contract unavailable. |

## Final stop check / planning handoff

The explicit retry, reconciliation, idempotency, and pending-UI policy is recorded as `DEC-001`, and the complete impact set has been recalculated. Handoff remains report-only: `IMP-004` is blocked on bounded retry policy and `IMP-005` on provider contract evidence. No implementation plan, task breakdown, or repository edit is included.
