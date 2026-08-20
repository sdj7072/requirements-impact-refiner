# Requirements impact refinement: automatic charge retries

## Requirement revision

`REQ-001` — Retry every charge that is determined to have failed automatically, while preserving at-most-one provider charge for a logical payment attempt, reconciling provider outcomes that are unknown locally, and exposing payment status accurately until webhook settlement is received. The retry limit, backoff, and terminal state must be explicit; “failed” must not include an outcome that may already have been captured unless the provider’s idempotency/reconciliation contract makes a retry safe.

This is a refinement of the supplied request, “Retry every failed charge automatically.” The original wording does not define whether a timeout after capture is failed, how many retries are permitted, or whether a retry reuses the original idempotency key.

## Current behavior and preserved invariants

| ID | Current behavior to preserve | Level | Evidence | Link |
|---|---|---|---|---|
| `INV-001` | Charge requests accept an `idempotency_key`. | `verified` | Supplied repository fact: “charge requests accept an idempotency_key.” | `must-preserve` `REQ-001` |
| `INV-002` | Payment status can be rendered before webhook settlement. | `verified` | Supplied repository fact: “payment status is rendered before webhook settlement.” | `must-preserve` `REQ-001` |
| `INV-003` | The provider may time out after capture. | `verified` | Supplied repository fact: “the provider may time out after capture.” | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links |
|---|---|---|---|---|---|
| `IMP-001` | Retrying with a different idempotency key after a provider timeout can create a second charge when the first request captured successfully. | `verified` | `INV-001`, `INV-003`; the supplied timeout-after-capture fact establishes an ambiguous provider outcome, and the supplied idempotency-key contract provides the available duplicate-prevention mechanism. | `refining` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | Treating a timeout as a definitive failure can cause a retry while the original charge is captured or still settling. | `verified` | `INV-003`; provider outcome is not knowable from a timeout alone. | `refining` | `affects` `REQ-001`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | A payment status rendered before webhook settlement may show a transient failure or success and then contradict the eventual webhook result if retry state is not modeled separately. | `verified` | `INV-002`; webhook settlement is later than initial status rendering. | `detected` | `affects` `REQ-001`, `INV-002`; `produces` `AC-003` |
| `IMP-004` | “Every failed charge” leaves retry count, backoff, terminal handling, and the definition of failed unspecified; an unbounded policy can create repeated provider calls and operational load. | `inferred` | Ambiguity in the supplied request; no retry policy or terminal-state contract was supplied. | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Concurrent/manual and automatic attempts could race and issue more than one logical attempt unless retry scheduling and idempotency are coordinated. | `inferred` | `INV-001` establishes an idempotency mechanism, but no concurrency or job-claim behavior was supplied. | `blocked` | `affects` `REQ-001`, `INV-001`; `produces` `AC-005` |
| `IMP-006` | Provider retry/reconciliation semantics are external and unavailable; it is unknown whether reuse of the same key returns the original outcome or whether a status lookup is required. | `unknown` | No provider contract or SDK behavior was supplied. | `blocked` | `affects` `REQ-001`; `produces` `AC-006` |

## One focused decision

Which outcome policy should define “failed” for automatic retry?

1. **Recommended — Conservative reconciliation:** retry only provider-confirmed, retryable failures; treat timeouts and transport errors as `unknown`, reuse the same logical idempotency key, and reconcile by provider lookup/webhook before allowing another charge attempt. Use a finite, explicitly configured retry limit and backoff.
2. **Same-key retry of unknowns:** automatically retry timeouts/transport errors with the same idempotency key, relying on the provider to return the original captured result; still use a finite limit and backoff. This requires confirmation that the provider’s key scope and retention cover the whole retry window.
3. **New-key retry of unknowns:** retry every timeout/transport error with a new key. This maximizes recovery attempts but accepts duplicate-charge risk and requires compensating refunds/reconciliation.

`DEC-001` — Pending user selection. No option is recorded as accepted because the supplied request does not resolve the duplicate-charge tradeoff and provider semantics are unavailable.

## Whole-set recalculation (current decision state)

The decision is pending, so no impact can be marked accepted or resolved. The full set remains:

| ID | Result after recalculation | Reason |
|---|---|---|
| `IMP-001` | `refining` | Reduced only by choosing a same-key/reconciliation policy; not selected yet. |
| `IMP-002` | `refining` | Timeout classification remains undecided. |
| `IMP-003` | `detected` | Status semantics must account for pending/unknown/retrying until webhook settlement. |
| `IMP-004` | `blocked` | Retry limit/backoff/terminal policy is unspecified. |
| `IMP-005` | `blocked` | Concurrency and scheduler coordination are unspecified. |
| `IMP-006` | `blocked` | Provider idempotency and reconciliation contract is unavailable. |

Delta: `resolved` — none; `mitigated` — none; `unchanged` — `IMP-003`; `accepted` — none; `deferred` — none; `blocked` — `IMP-004`, `IMP-005`, `IMP-006`; `new` — none.

## Acceptance and regression criteria

| ID | Criterion | Evidence/state |
|---|---|---|
| `AC-001` | A retry of one logical payment preserves its idempotency identity; a provider timeout after capture cannot cause a second charge under the selected policy. | Verifies `IMP-001`; requires provider contract/test evidence. |
| `AC-002` | A timeout-after-capture is represented as `unknown`/pending (or reconciled to the provider result), never blindly treated as a definitive failed charge. | Verifies `IMP-002`; based on `INV-003`. |
| `AC-003` | Status shown before webhook settlement distinguishes pending/retrying/unknown from terminal failure or success, and converges to the webhook settlement without contradictory terminal transitions. | Verifies `IMP-003`; based on `INV-002`. |
| `AC-004` | Retryability, maximum attempts, backoff, and terminal behavior are explicit and bounded. | Verifies `IMP-004`; currently blocked pending policy. |
| `AC-005` | Concurrent workers or a manual retry cannot schedule duplicate logical attempts. | Verifies `IMP-005`; currently blocked pending concurrency design. |
| `AC-006` | The provider contract confirms idempotency-key scope/retention and the supported reconciliation operation for timeout outcomes. | Verifies `IMP-006`; currently blocked pending provider documentation or test evidence. |

## Stop check and planning handoff

Refinement stops here pending `DEC-001` and the missing provider contract. The implementation-planning workflow should receive `REQ-001`, preserved invariants `INV-001`–`INV-003`, the complete impact ledger, and acceptance criteria `AC-001`–`AC-006`. This is a planning handoff only; no implementation plan is created here.
