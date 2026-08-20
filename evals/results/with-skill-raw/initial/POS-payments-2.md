# Requirements impact refinement: POS-payments-2

## Requirement revision

`REQ-001` (detected): Retry every failed charge automatically.

This is not yet implementation-ready because “failed” may include a provider timeout after capture, and the supplied facts establish that a charge can be captured even when the request does not receive a timely response. The requirement must therefore define retry eligibility, attempt limits/backoff, and the terminal state shown while webhook settlement is pending.

## Current behavior and preserved invariants

| ID | Current behavior to preserve | Level | Evidence | State | Links |
|---|---|---|---|---|---|
| `INV-001` | Charge requests accept an `idempotency_key`. | verified | Supplied repository fact: “charge requests accept an idempotency_key.” | detected | must-preserve `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement. | verified | Supplied repository fact: “payment status is rendered before webhook settlement.” | detected | must-preserve `REQ-001` |
| `INV-003` | The provider may time out after capture. | verified | Supplied repository fact: “the provider may time out after capture.” | detected | must-preserve `REQ-001` |

## Impact ledger

| ID | Impact | Level | Evidence / rationale | State | Links |
|---|---|---|---|---|---|
| `IMP-001` | Retrying a timeout after capture can create a second charge if the retry is not correlated to the original attempt with a stable idempotency key. | verified | `INV-001` and `INV-003`: idempotency is available, while capture may have happened before timeout. | refining | affects `REQ-001`, `INV-001`, `INV-003`; produces `AC-001` |
| `IMP-002` | “Every failed charge” is ambiguous: a transport timeout, provider-declined payment, validation failure, and an already-captured-but-unsettled payment may require different handling. | inferred | Derived from `INV-003` and the distinction between request response and webhook settlement in `INV-002`; exact provider failure taxonomy is not supplied. | blocked | affects `REQ-001`; produces `AC-002` |
| `IMP-003` | The UI can show a failure before the webhook settles a successful capture, causing the customer to retry manually or perceive a duplicate when automatic retry starts. | verified | `INV-002` and `INV-003`: rendering precedes settlement and timeout can follow capture. | refining | affects `REQ-001`, `INV-002`, `INV-003`; produces `AC-003` |
| `IMP-004` | Concurrent automatic retry and late webhook delivery can race and produce conflicting payment states unless settlement is idempotent and state transitions are ordered. | inferred | Derived from pre-webhook rendering plus post-capture timeout; webhook/state-machine implementation is not supplied. | blocked | affects `REQ-001`, `INV-002`; produces `AC-004` |
| `IMP-005` | Unbounded retries can create retry storms, repeated provider calls, customer confusion, and operational cost. | inferred | Automatic retry is requested, but no maximum attempts, backoff, queue, or stop condition is supplied. | refining | affects `REQ-001`; produces `AC-005` |
| `IMP-006` | Persisted attempt identity and an audit trail are needed to reconcile a late capture/webhook with the original request and explain retries. | inferred | `INV-001` supplies request idempotency, but persistence, reconciliation, and audit behavior are unspecified. | blocked | affects `REQ-001`, `INV-003`; produces `AC-006` |
| `IMP-007` | Existing successful-charge and webhook behavior must remain unchanged for non-retried payments. | inferred | Regression expectation derived from the request’s scope; no tests or implementation artifacts were supplied. | blocked | affects `REQ-001`, `INV-002`; produces `AC-007` |
| `IMP-008` | Provider-specific idempotency-key scope, retention, and behavior after a timeout are unknown, so duplicate-charge protection cannot be proven from the supplied facts alone. | unknown | Provider contract/SDK documentation was not supplied. | blocked | affects `REQ-001`, `INV-001`, `INV-003`; produces `AC-008` |

## One focused decision

Which retry policy should refine `REQ-001`?

1. **Retry only uncertain/transient outcomes (recommended):** retry timeouts and explicitly retryable provider errors; stop for definitive declines/validation failures; use the same logical payment id and idempotency key across attempts, with bounded exponential backoff and a manual/reconciliation terminal state.
2. **Retry every provider-reported failure:** also retry definitive declines, with a configured maximum attempt count and backoff. This follows the literal wording but can repeat non-retryable failures and increase customer/provider friction.
3. **Retry every failure with a fresh idempotency key:** not recommended because a timeout-after-capture can produce a duplicate charge; use only if the provider contract guarantees a separate reconciliation mechanism.

No user choice is present in the supplied request, so no `DEC-###` can truthfully be recorded. The requirement remains `blocked` pending this decision and the provider’s idempotency semantics.

## Recorded decision

`DEC-001`: **pending user decision** on retry eligibility and whether timeout-after-capture attempts share one logical idempotency identity. No impact is marked `accepted` because silence is not acceptance.

## Whole-set recalculation (before decision)

| Impact | Recalculated status | Rationale |
|---|---|---|
| `IMP-001` | refining | The existing idempotency contract is a mitigation, but key reuse/lifecycle is not decided. |
| `IMP-002` | blocked | Failure taxonomy and retry eligibility are unspecified. |
| `IMP-003` | refining | Pre-settlement rendering must be reconciled with retry/pending UI behavior. |
| `IMP-004` | blocked | Webhook ordering and idempotent settlement behavior are not supplied. |
| `IMP-005` | refining | A bounded retry policy is still required. |
| `IMP-006` | blocked | Persistence/reconciliation and audit requirements are not supplied. |
| `IMP-007` | blocked | No implementation or regression tests were supplied. |
| `IMP-008` | blocked | Provider contract is unavailable. |

Delta: no impacts are resolved, accepted, deferred, or superseded. `IMP-001`, `IMP-003`, and `IMP-005` are mitigable by the focused decision; `IMP-002`, `IMP-004`, `IMP-006`, `IMP-007`, and `IMP-008` remain blocked by named information gaps. No new impacts were identified in recalculation.

## Acceptance and regression criteria for the planning handoff

| ID | Criterion | Evidence needed | Produced by |
|---|---|---|---|
| `AC-001` | A timeout-after-capture cannot create a second provider charge when an automatic retry occurs; retries use the documented stable logical payment/idempotency identity. | Provider contract plus integration test that delays the response after capture and delivers the webhook late. | `IMP-001` |
| `AC-002` | Each provider outcome is classified as retryable, non-retryable, or pending reconciliation, with definitive declines/validation failures not retried unless the selected policy explicitly requires it. | Provider error mapping and tests for each outcome. | `IMP-002` |
| `AC-003` | Before webhook settlement, the rendered status communicates pending/retrying/reconciliation rather than an irreversible failure; late settlement updates the same payment. | UI/state-transition test covering timeout, retry, and late webhook. | `IMP-003` |
| `AC-004` | Automatic retry and webhook delivery are idempotent and converge to one final payment state regardless of arrival order. | Concurrency/race test with both event orderings. | `IMP-004` |
| `AC-005` | Retries are bounded and use documented backoff/jitter, with an observable terminal state and no retry storm. | Configuration, queue/job test, and metrics/log assertion. | `IMP-005` |
| `AC-006` | Every attempt records logical payment ID, idempotency key, provider reference (when available), outcome, and retry linkage for reconciliation/audit. | Persistence schema/fixture and reconciliation test. | `IMP-006` |
| `AC-007` | Existing successful charges and webhook settlement continue to behave as before when no retry is needed. | Existing regression suite plus unchanged-flow test. | `IMP-007` |
| `AC-008` | The provider’s idempotency-key scope, retention, and timeout-after-capture semantics are documented and verified in an integration test; otherwise this risk remains blocked. | Authoritative provider documentation or sandbox evidence. | `IMP-008` |

## Stop check and planning handoff

The refinement stops here pending `DEC-001` and provider idempotency evidence. The planning workflow should use the selected policy to revise `REQ-001`, then recalculate all `IMP-###` statuses and preserve `INV-001`–`INV-003`. Do not implement “retry every failed charge” until timeout-after-capture handling, retry bounds, state convergence, and provider idempotency semantics are explicitly decided and testable.
