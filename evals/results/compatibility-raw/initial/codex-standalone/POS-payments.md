# Requirements impact refinement: automatic charge retries

## Requirement revision

`REQ-001` — Retry failed charge requests automatically, while preserving the provider’s idempotency contract, keeping payment status accurate until webhook settlement, and preventing a retry from creating an unintended duplicate capture. The precise classification of “failed,” retry bounds, and handling of an outcome that may already have captured require a decision.

This refines the supplied request, “Retry every failed charge automatically.” It does not yet select a retry or reconciliation policy.

## Current behavior and preserved invariants

| ID | Current behavior to preserve | Level | Evidence | Link |
|---|---|---|---|---|
| `INV-001` | Charge requests accept an `idempotency_key`. | `verified` | Supplied repository fact: “charge requests accept an idempotency_key.” | `must-preserve` `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement. | `verified` | Supplied repository fact: “payment status is rendered before webhook settlement.” | `must-preserve` `REQ-001` |
| `INV-003` | The provider may time out after capture. | `verified` | Supplied repository fact: “the provider may time out after capture.” | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links |
|---|---|---|---|---|---|
| `IMP-001` | A retry after a timeout-after-capture can create a duplicate capture if the retry is not correlated with the original charge attempt. | `inferred` | `INV-001` and `INV-003`; the supplied facts establish both the duplicate-prevention mechanism and an ambiguous post-capture timeout. | `refining` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | Treating every timeout as a definitive failure can issue another charge while the original may already have captured. | `inferred` | `INV-003`; a timeout does not establish the provider’s final capture outcome. | `refining` | `affects` `REQ-001`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | A status rendered before webhook settlement could contradict the eventual webhook if retrying, pending, success, and terminal failure are not distinguished. | `inferred` | `INV-002`; settlement arrives after the initial status is rendered. | `detected` | `affects` `REQ-001`, `INV-002`; `produces` `AC-003` |
| `IMP-004` | “Every failed charge” does not specify retryability, attempt limits, backoff, or terminal handling, leaving potentially unbounded provider calls. | `unknown` | Supplied request contains no retry classification or bounds. | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Provider idempotency-key scope, retention, and status/reconciliation behavior are unavailable, so safe handling of an ambiguous timeout cannot be confirmed. | `unknown` | No provider contract or SDK behavior was supplied. | `blocked` | `affects` `REQ-001`; `produces` `AC-005` |

## One focused decision

Which policy should define a charge as retryable when the provider request times out after capture?

1. **Conservative reconciliation (recommended):** retry only confirmed retryable failures; treat timeout outcomes as unknown and reconcile through provider status/webhook before issuing another capture.
2. **Same-key retry:** retry timeout/transport outcomes with the original idempotency key, relying on the provider to return the original result; this requires confirmation of key scope and retention.
3. **New-key retry:** retry timeout/transport outcomes with a new key, accepting duplicate-capture risk and requiring compensating reconciliation/refund handling.

No option is selected. The pending decision must resolve the duplicate-capture tradeoff before a concrete recorded decision can be created.

## Whole-set recalculation (decision pending)

| ID | Result | Reason |
|---|---|---|
| `IMP-001` | `refining` | Duplicate prevention depends on the pending policy and provider contract. |
| `IMP-002` | `refining` | Timeout classification is not selected. |
| `IMP-003` | `detected` | Pre-webhook status semantics still need to account for unresolved outcomes. |
| `IMP-004` | `blocked` | Retry limits, backoff, and terminal behavior are unspecified. |
| `IMP-005` | `blocked` | Provider idempotency and reconciliation guarantees are unavailable. |

Delta: `resolved` — none; `mitigated` — none; `unchanged` — `IMP-003`; `accepted` — none; `deferred` — none; `blocked` — `IMP-004`, `IMP-005`; `new` — none.

## Acceptance and regression criteria

| ID | Criterion | Evidence/state |
|---|---|---|
| `AC-001` | A timeout-after-capture cannot result in two provider captures for one logical payment under the selected policy. | Verifies `IMP-001`; pending policy/provider evidence. |
| `AC-002` | An ambiguous timeout is not blindly treated as a definitive failed charge before its provider outcome is resolved. | Verifies `IMP-002`; based on `INV-003`. |
| `AC-003` | Pre-webhook status distinguishes unresolved/retrying state from terminal failure or success and converges with the webhook result. | Verifies `IMP-003`; based on `INV-002`. |
| `AC-004` | Retry classification, limits, backoff, and terminal behavior are explicit and bounded. | Verifies `IMP-004`; blocked pending policy selection. |
| `AC-005` | Provider documentation or tests establish idempotency-key scope/retention and the supported reconciliation path for timeout outcomes. | Verifies `IMP-005`; blocked pending provider evidence. |

## Stop check and planning handoff

Refinement stops at the pending decision and provider evidence gap. Handoff includes `REQ-001`, `INV-001`–`INV-003`, `IMP-001`–`IMP-005`, and `AC-001`–`AC-005`. No concrete `DEC-###` is recorded because no stakeholder selection was supplied. This is a report-only planning handoff; no task breakdown or implementation edit is included.

--- USER REVISION ---

I choose: “Retry only when settlement is unknown, reuse the original idempotency key, reconcile provider state before retry, and keep the UI pending until settlement.”

# Second response — recalculation after `DEC-001`

## Requirement revision

`REQ-001` is refined to: When settlement is unknown, retry using the original idempotency key only after reconciling provider state. Keep the payment UI pending until settlement is known. Do not treat an unknown settlement as an ordinary definitive failure or issue an uncorrelated new capture.

## Current behavior and preserved invariants

`INV-001`–`INV-003` remain unchanged: charge requests accept an `idempotency_key`; payment status is rendered before webhook settlement; and the provider may time out after capture. These remain `verified` supplied facts and are still `must-preserve` by `REQ-001`.

## Recorded decision

`DEC-001`: The user selected: “Retry only when settlement is unknown, reuse the original idempotency key, reconcile provider state before retry, and keep the UI pending until settlement.”

## Whole-set recalculation

| ID | Recalculated impact | Level | State | Evidence | Links |
|---|---|---|---|---|---|
| `IMP-001` | Reusing the original idempotency key and reconciling before retry materially reduces duplicate-capture risk for a timeout-after-capture; provider enforcement of that key remains a validation dependency. | `inferred` | `mitigated` | `DEC-001` plus `INV-001` and `INV-003`; provider key semantics are not directly supplied. | `affects` `REQ-001`, `INV-001`, `INV-003`; `mitigated by` `DEC-001`; `produces` `AC-001` |
| `IMP-002` | A timeout-after-capture is handled as unknown settlement, and provider reconciliation precedes any retry, so it is no longer blindly treated as a definitive failure. | `verified` | `resolved` | Explicit selected policy in `DEC-001`; timeout-after-capture is established by `INV-003`. | `affects` `REQ-001`, `INV-003`; `resolved by` `DEC-001`; `produces` `AC-002` |
| `IMP-003` | The UI remains pending until settlement, preventing a pre-webhook unknown/retry state from being presented as terminal success or failure. | `verified` | `resolved` | Explicit selected policy in `DEC-001`; pre-webhook rendering is established by `INV-002`. | `affects` `REQ-001`, `INV-002`; `resolved by` `DEC-001`; `produces` `AC-003` |
| `IMP-004` | Retryable error classification, attempt limits, backoff, and terminal handling remain unspecified. | `unknown` | `blocked` | The request and `DEC-001` do not specify bounds or definitive-failure policy. | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Whether the provider preserves and honors the original idempotency key and supports the required reconciliation operation remains unverified. | `unknown` | `blocked` | No provider contract or SDK behavior was supplied. | `affects` `REQ-001`; `produces` `AC-005` |

## Delta

- `resolved`: `IMP-002`, `IMP-003`
- `mitigated`: `IMP-001`
- `unchanged`: none
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`, `IMP-005`
- `new`: none

The categories are disjoint and exhaustive across `IMP-001` through `IMP-005`.

## Stop check and planning handoff

The explicit retry, reconciliation, idempotency, and UI policy is recorded as `DEC-001`. Remaining report-only gaps are bounded retry policy (`IMP-004`) and provider contract verification (`IMP-005`). No implementation tasks, work breakdown, plan, or repository edit is included.

### Acceptance criteria targets

| ID | Future criterion | Evidence / gap |
|---|---|---|
| `AC-001` | A timeout-after-capture retry reuses the original idempotency key and cannot create an unintended second capture for the same logical payment. | Produced by mitigated `IMP-001`; provider enforcement remains unverified. |
| `AC-002` | An unknown settlement is reconciled before retry and is never blindly treated as a definitive failure. | Produced by resolved `IMP-002`; selected behavior is explicit in `DEC-001`. |
| `AC-003` | The UI remains pending until settlement is known and then converges with the provider/webhook result. | Produced by resolved `IMP-003`; selected behavior is explicit in `DEC-001`. |
| `AC-004` | Retry classification, maximum attempts, backoff, and terminal handling are explicit and bounded. | Produced by blocked `IMP-004`; policy remains unspecified. |
| `AC-005` | Provider evidence confirms original-key retention/semantics and the supported reconciliation path. | Produced by blocked `IMP-005`; provider contract is unavailable. |
