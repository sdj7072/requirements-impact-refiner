# POS payments — requirements impact refinement

## Requirement revision

`REQ-001` — Retry every failed charge automatically. A failed charge attempt must be eligible for an automated follow-up attempt, while preserving the existing idempotency contract and reconciling provider outcomes before another attempt can create a second capture. The retry classification, retry limit, backoff, and terminal-state policy remain a pending decision.

This is a refinement rather than an implementation plan: it makes the safety boundary explicit without selecting a retry wire, schedule, or state transition that was not supplied.

## Current behavior and preserved invariants

| ID | Current behavior to preserve | Evidence level | Evidence | Link |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`; retries must remain correlated to the original charge intent through that contract. | `verified` | Task prompt — supplied repository facts | `must-preserve` `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement. The UI/API can therefore expose a pre-settlement view of a payment. | `verified` | Task prompt — supplied repository facts | `must-preserve` `REQ-001` |
| `INV-003` | The provider may time out after capture, so a client-visible timeout does not prove that no capture occurred. | `verified` | Task prompt — supplied repository facts | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact / uncertainty | Area | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Retrying a timed-out request can create a duplicate capture if the first request captured successfully and the follow-up is treated as a new charge. | State/concurrency; data | `verified` | `INV-001`, `INV-003`; task prompt — supplied repository facts | `refining` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | Automatic retry can race with webhook settlement because payment status is rendered before settlement; a retry decision based only on the rendered status can be stale or incorrect. | State/concurrency; interfaces | `verified` | `INV-002`, `INV-003`; task prompt — supplied repository facts | `refining` | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | “Every failed charge” does not define how permanent declines, validation failures, or provider failures are distinguished. Retrying non-retryable failures may create repeated customer-visible attempts and unnecessary provider traffic. | Functionality; operations | `inferred` | `REQ-001` wording; no failure taxonomy supplied | `detected` | `affects` `REQ-001`; `produces` `AC-003` |
| `IMP-004` | Maximum attempts, backoff, retry horizon, and terminal status are unspecified; an automatic retry loop could be unbounded or could stop earlier than the requirement intends. | State/concurrency; operations | `unknown` | No retry policy, queue configuration, or attempt schema supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | The contract for an in-flight/unknown provider result is unspecified. Without a reconciliation outcome, the system cannot safely decide whether to retry, wait, or mark the payment failed after a post-capture timeout. | Interfaces; state/concurrency | `unknown` | `INV-003`; no provider status-query or webhook contract supplied | `blocked` | `affects` `REQ-001`, `INV-003`; `produces` `AC-005` |
| `IMP-006` | Rendering status before settlement can expose a transient failure or pending state while an automatic retry is queued; the permitted customer-facing status and notification behavior are unspecified. | Interfaces; regression | `inferred` | `INV-002`; no status-state or notification contract supplied | `detected` | `affects` `REQ-001`, `INV-002`; `produces` `AC-006` |

## One focused decision

**Decision needed:** What retry boundary should “every failed charge” use when the provider has not conclusively established that the prior attempt was uncaptured?

1. **Recommended — bounded transient/unknown retries with reconciliation:** automatically retry classified transient failures and unresolved timeouts only after idempotent reconciliation, with a finite attempt cap, backoff, and a terminal review/failed state.
2. **Bounded retry for all provider-reported failures:** retry every provider-reported failure for a finite, configured number of attempts, but never retry local validation/authentication failures; unresolved timeouts still require reconciliation before another capture-capable request.
3. **Unbounded retry until settlement:** continue automatically until a capture or definitive failure is observed. This most literally satisfies “every,” but requires an explicit operational and customer-protection policy for indefinite retries.

No option is recorded here because the request supplies no selection. Therefore no `DEC-###` is created or referenced.

## Whole-set recalculation (before the pending decision)

The requirement has been made explicit about idempotency and timeout reconciliation, but no retry boundary was selected. Every known impact remains in scope:

- **resolved:** none
- **mitigated:** none
- **unchanged:** `IMP-001`, `IMP-002`, `IMP-003`, `IMP-006`
- **accepted:** none
- **deferred:** none
- **blocked:** `IMP-004`, `IMP-005`
- **new:** none

## Stop check and planning handoff

The report is ready for planning handoff only with the pending decision called out. A selected option must be recorded as a new `DEC-###`, then the complete impact set must be recalculated. Until then, the remaining risks are duplicate capture after post-capture timeout, stale pre-webhook status, undefined failure classification, undefined retry bounds, and undefined reconciliation behavior.

## Acceptance and regression criteria

| ID | Criterion | Evidence target | Verifies |
| --- | --- | --- | --- |
| `AC-001` | A retry of an attempt whose provider outcome may already be captured cannot produce a second capture for the same charge intent; the original `idempotency_key` correlation is preserved and exercised in a duplicate/timeout test. | Idempotency integration test and provider contract | `INV-001`, `INV-003`; produced by `IMP-001` |
| `AC-002` | A retry is not authorized solely from the pre-webhook rendered status; settlement/reconciliation ordering is deterministic for timeout and webhook races. | State-transition or race test | `INV-002`, `INV-003`; produced by `IMP-002` |
| `AC-003` | Each failure class has a documented retry eligibility outcome, and the automated path does not repeatedly retry a classified permanent failure beyond the selected policy. | Failure-taxonomy contract test | `REQ-001`; produced by `IMP-003` |
| `AC-004` | The selected policy specifies and enforces maximum attempts, backoff, retry horizon, and terminal state, with metrics/logging for exhaustion. | Retry policy/configuration test | `REQ-001`; produced by `IMP-004` |
| `AC-005` | A provider timeout after capture is reconciled to a definitive settlement state or an explicitly safe pending state before another capture-capable attempt is made. | Provider reconciliation/webhook contract test | `INV-003`; produced by `IMP-005` |
| `AC-006` | User-visible status and notifications distinguish pre-settlement, retrying, settled, and terminal failure states and do not report a transient retry as a final charge failure. | Payment status/UI regression test | `INV-002`; produced by `IMP-006` |

