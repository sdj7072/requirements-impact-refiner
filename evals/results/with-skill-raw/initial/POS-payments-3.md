# Requirements impact refinement: POS payments

## Requirement revision

`REQ-001` — Retry every failed charge automatically.

Refined working wording: after a charge attempt fails or reaches an indeterminate outcome, the system should retry automatically using the provider-supported `idempotency_key`, while preventing duplicate capture, exposing a truthful pending/unknown state until settlement is known, and making retry exhaustion observable. The exact retryable failure classes, retry budget, and customer-facing terminal state still require a product decision.

## Current behavior and preserved invariants

The following facts are supplied repository evidence and are treated as the baseline:

| ID | Preserved behavior | Level | Evidence | Link |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`. | `verified` | Supplied repository fact: “charge requests accept an idempotency_key” | `must-preserve` `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement. | `verified` | Supplied repository fact: “payment status is rendered before webhook settlement” | `must-preserve` `REQ-001` |
| `INV-003` | The provider may time out after capture, so a timeout does not prove that no charge occurred. | `verified` | Supplied repository fact: “the provider may time out after capture” | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Area | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | A retry with a new idempotency key could capture the same payment twice when the first attempt timed out after capture. | State/concurrency, regression | `verified` | `INV-001`, `INV-003` | `detected` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | Retrying immediately on a provider timeout can race with webhook settlement and create conflicting payment states. | State/concurrency, interfaces | `verified` | `INV-002`, `INV-003` | `detected` | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | “Every failed charge” is ambiguous: retrying non-retryable failures (decline, fraud/risk rejection, invalid request) can create repeated attempts, poor UX, or provider violations. | Functionality, interfaces | `inferred` | Requirement wording; no failure taxonomy supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-003` |
| `IMP-004` | An unbounded or overly large retry policy can cause duplicate customer notifications, provider load, and uncontrolled processing cost. | Operations, functionality | `inferred` | Requirement says “every”; retry budget/backoff/attempt limit not supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Rendering a failed state before settlement can mislead the customer if a retry or webhook later confirms capture. | Functionality, interfaces | `verified` | `INV-002`, `INV-003` | `detected` | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-005` |
| `IMP-006` | A retry outcome and webhook outcome may arrive out of order; last-write-wins handling could regress a settled payment to failed or charge it twice. | State/concurrency, data | `inferred` | `INV-002`; webhook settlement is asynchronous; persistence/schema details unavailable | `blocked` | `affects` `REQ-001`, `INV-002`; `produces` `AC-006` |
| `IMP-007` | Retry attempts, idempotency reuse, timeout/settlement correlation, and exhaustion need logs/metrics/alerts to operate safely; existing observability is not supplied. | Operations | `unknown` | No deployment, metrics, alert, or runbook evidence supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-007` |
| `IMP-008` | Existing clients may already interpret the pre-webhook status; introducing a pending/unknown state or changing terminal-state timing may be a compatibility change. | Compatibility, interfaces | `unknown` | No client contract/versioning evidence supplied beyond `INV-002` | `blocked` | `affects` `REQ-001`, `INV-002`; `produces` `AC-008` |

## Focused decision

What should “automatically” mean for failures and provider timeouts?

1. **Recommended — bounded safe retry:** retry only explicitly retryable/transient failures; for timeout/unknown outcomes, reuse the same idempotency key and reconcile via provider lookup/webhook before any new capture; use exponential backoff with a finite attempt/time budget; show `pending`/`payment verification` until resolved.
2. **Aggressive retry:** retry all provider-reported failures, including declines, with a finite budget; timeout handling still requires idempotency-key reuse and reconciliation.
3. **Minimal retry:** retry only transport failures; treat post-capture timeouts as pending and rely on webhook/provider reconciliation, with no automatic second attempt.

No user choice is supplied in the request. `DEC-001` is therefore **pending**, and the requirement cannot be finalized as accepted until option 1, 2, or 3 is selected. The recommendation is option 1 because it preserves capture safety while satisfying automatic recovery for transient failures.

## Whole-set recalculation (current, pending decision)

Because `DEC-001` has not been answered, no impact is resolved or accepted. The complete set remains:

- `IMP-001`: `detected` — needs explicit idempotency-key reuse/correlation rules.
- `IMP-002`: `detected` — needs ordering/reconciliation behavior around webhooks.
- `IMP-003`: `blocked` — needs the retryable failure taxonomy.
- `IMP-004`: `blocked` — needs retry budget and backoff limits.
- `IMP-005`: `detected` — needs a truthful pending/unknown customer state.
- `IMP-006`: `blocked` — needs persistence/state-transition evidence and monotonic settlement rules.
- `IMP-007`: `blocked` — needs observability evidence and operational ownership.
- `IMP-008`: `blocked` — needs client/API compatibility evidence.

### Delta

| Category | Impacts |
| --- | --- |
| Resolved | None; no decision or implementation evidence exists. |
| Mitigated | None; the working wording identifies safeguards but does not constitute implementation evidence. |
| Unchanged | `IMP-001`, `IMP-002`, `IMP-005` remain detected; `IMP-003`, `IMP-004`, `IMP-006`, `IMP-007`, `IMP-008` remain blocked. |
| Accepted | None; silence is not acceptance. |
| Deferred | None. |
| Blocked | `IMP-003`, `IMP-004`, `IMP-006`, `IMP-007`, `IMP-008`; plus the pending choice represented by `DEC-001`. |
| New | None at this refinement pass. |

## Acceptance and regression criteria

These are planning-handoff criteria, not claims that current tests exist:

- `AC-001` (from `IMP-001`): a retry of an indeterminate attempt uses the original idempotency key (or an equivalently provider-safe correlation) and cannot create a second capture; test a timeout-after-capture scenario.
- `AC-002` (from `IMP-002`): retry scheduling and webhook settlement are concurrency-safe and converge to one authoritative payment outcome regardless of arrival order.
- `AC-003` (from `IMP-003`): only the selected failure classes are retried; non-retryable declines/validation/risk failures do not loop automatically.
- `AC-004` (from `IMP-004`): backoff, maximum attempts, and maximum elapsed retry time are finite, configurable, and enforced; exhaustion yields a defined terminal outcome.
- `AC-005` (from `IMP-005`): before webhook settlement, the UI does not claim success or definitive failure when the provider outcome is unknown; it displays the selected pending/reconciliation state.
- `AC-006` (from `IMP-006`): late webhook events and retry responses cannot regress a settled payment or trigger another capture.
- `AC-007` (from `IMP-007`): each attempt records correlation/idempotency key, reason, outcome, retry number, and settlement transition; metrics and alerts cover repeated failures and stuck pending payments without exposing sensitive payment data.
- `AC-008` (from `IMP-008`): existing clients remain compatible with any new status or timing semantics, or the API/versioning migration is explicitly specified and tested.

## Stop check and planning handoff

The refinement stops here because a product choice is required before implementation planning. Planning may proceed after `DEC-001` selects a retry policy and the blocked evidence gaps are answered: retryable failure taxonomy, retry/backoff budget, authoritative reconciliation mechanism, persistence/state-transition contract, observability ownership, and client compatibility requirements. The implementation plan must preserve `INV-001`–`INV-003` and include tests for every `AC-001`–`AC-008` criterion.
