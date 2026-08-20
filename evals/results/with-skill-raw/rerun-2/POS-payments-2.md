# Requirements impact refinement: POS payments

## Requirement revision

`REQ-001` — Retry every failed charge automatically.

The request is intentionally preserved as stated, but “failed” and “automatically” need operational boundaries before implementation planning. In particular, the requirement does not yet say whether a provider timeout after capture is retryable, how long retries may continue, or whether each retry reuses the original idempotency key.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`. | `verified` | Supplied repository fact: charge requests accept an `idempotency_key`. | `must-preserve` by `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement. | `verified` | Supplied repository fact: payment status is rendered before webhook settlement. | `must-preserve` by `REQ-001` |
| `INV-003` | The provider may time out after capture, so a timeout does not prove that no charge occurred. | `verified` | Supplied repository fact: the provider may time out after capture. | `must-preserve` by `REQ-001` |

## Impact ledger

| ID | Severity | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Critical | Retrying a timeout after capture can create a duplicate charge if the retry is not recognized as the same logical charge. | `verified` | `INV-001`, `INV-003`; supplied facts establish idempotency support and post-capture timeout behavior, but not retry-key reuse. | `blocked` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | High | “Every failed charge” may retry permanent declines, invalid requests, or other non-transient failures indefinitely or unnecessarily. | `unknown` | No failure taxonomy, retry limit, backoff, or terminal-error policy supplied. | `blocked` | `affects` `REQ-001`; `produces` `AC-002` |
| `IMP-003` | High | Automatic retries may make the rendered payment status disagree with the eventual webhook settlement, especially while a retry is pending. | `verified` | `INV-002`; webhook settlement occurs after status rendering. | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-003` |
| `IMP-004` | High | A retry mechanism needs durable ownership, deduplication, and recovery across worker/process restarts; otherwise a retry can be lost or run more than once. | `unknown` | No queue, job-store, transaction, or recovery contract supplied. | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Medium | Repeated attempts can alter customer-visible attempt history, notifications, metrics, and reconciliation volume. | `unknown` | No audit, notification, observability, or reconciliation policy supplied. | `detected` | `affects` `REQ-001`; `produces` `AC-005` |
| `IMP-006` | Medium | Concurrent retry workers or a user-triggered retry could race with automatic retry and produce conflicting payment transitions. | `unknown` | No locking, compare-and-set, or state-machine contract supplied. | `blocked` | `affects` `REQ-001`; `produces` `AC-006` |
| `IMP-007` | Medium | Retry traffic changes provider load, latency, rate-limit exposure, and operational cost. | `unknown` | No retry budget, backoff, rate-limit handling, or alert thresholds supplied. | `detected` | `affects` `REQ-001`; `produces` `AC-007` |
| `IMP-008` | Medium | Existing clients may observe additional intermediate or terminal payment states while webhook settlement remains asynchronous. | `inferred` | `INV-002`; the request changes attempt behavior without a supplied response/event compatibility contract. | `detected` | `affects` `REQ-001`, `INV-002`; `produces` `AC-008` |

The highest-risk uncertainty is the timeout-after-capture case. The supplied idempotency-key capability is evidence of a useful contract, not evidence that the current flow automatically reuses the key or that the provider retains it for the required duration.

## Focused decision needed

What retry policy should define “failed” and the automatic retry boundary?

1. **Conservative payment-safe policy (recommended):** retry only explicitly transient failures and unknown/time-out outcomes using the same logical charge/idempotency key; stop after a bounded schedule and move unresolved attempts to a review/reconciliation state.
2. **Broad bounded policy:** retry every non-success outcome, including declines, for a fixed maximum number of attempts with backoff; preserve the same logical charge key.
3. **Unbounded literal policy:** retry every failed outcome until success, with no stated attempt/time limit.

The pending decision must also establish whether a provider timeout after possible capture is treated as “retry with the same idempotency key,” “reconcile before retry,” or another explicitly defined transition. No `DEC-###` is recorded because no stakeholder selection was supplied.

## Recorded decision

None. The request supplies a desired behavior but does not select one of the retry policies above, so no `DEC-###` is allocated.

## Whole-set recalculation

No decision was recorded; therefore the requirement is not yet refined enough to resolve the material impacts. The complete known impact set is categorized below exactly once.

### Delta

- `resolved: none`
- `mitigated: none`
- `unchanged: IMP-003, IMP-005, IMP-007, IMP-008` (still `refining`/`detected`)
- `accepted: none`
- `deferred: none`
- `blocked: IMP-001, IMP-002, IMP-004, IMP-006`
- `new: none`

## Planning handoff

Refined requirement pending the decision: automatically retry eligible failed charge outcomes under an explicitly bounded, idempotent, recoverable policy; preserve the existing idempotency-key contract and represent pending/reconciled outcomes consistently with asynchronous webhook settlement.

Remaining risks are duplicate capture, misclassification of permanent failures, lost or duplicated jobs, concurrent state races, customer/operational side effects, provider rate limits, and compatibility of intermediate statuses. The named information gaps are the provider failure taxonomy and idempotency retention semantics, retry schedule/budget, durable retry/reconciliation mechanism, state-transition/concurrency rules, and audit/notification/observability contracts.

Acceptance and regression criteria:

- `AC-001` — A timeout after possible capture never causes a second provider charge for the same logical payment; retries use the agreed idempotency/reconciliation behavior and remain safe across repeated execution.
- `AC-002` — The selected failure taxonomy, maximum attempts, backoff, and terminal handling are explicit; permanent failures do not retry outside that policy.
- `AC-003` — Payment status remains truthful while retries and webhook settlement are pending, and final webhook settlement converges to one terminal outcome.
- `AC-004` — Retry work survives worker restart, is deduplicated, and records attempt outcomes for recovery/reconciliation.
- `AC-005` — Attempt history, customer notifications, metrics, and reconciliation records follow one defined policy without duplicate side effects.
- `AC-006` — Concurrent automatic and manual attempts cannot produce conflicting transitions or duplicate logical charges.
- `AC-007` — Retry load is bounded by the selected budget/backoff and exposes failures, rate limits, and exhausted attempts to operations.
- `AC-008` — Existing consumers can handle the defined intermediate and terminal statuses, or a compatibility transition is explicitly specified.

Stop check: report-only refinement handoff is complete, but implementation planning should wait for the single pending retry-policy decision and the named provider/recovery information gaps.
