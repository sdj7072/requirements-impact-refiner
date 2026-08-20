# POS payments — automatic charge retry refinement

## Requirement revision

`REQ-001` (proposed): Retry a charge automatically when the charge is eligible for retry, while preserving single-charge semantics and converging the displayed payment status with the provider’s eventual settlement result. A retry policy must distinguish definitive provider failures from indeterminate outcomes (including a provider timeout after capture), use the charge request’s idempotency contract, and stop after a bounded number of attempts or a terminal status.

The phrase “every failed charge” is not implementation-ready until “failed” is defined for an outcome that may be unknown locally but successful at the provider.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`; retries can therefore be correlated to the original logical charge if the same key is retained. | `verified` | Supplied repository fact: “charge requests accept an idempotency_key.” | `detected` | must-preserve `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement, so the initially rendered status can precede the authoritative settlement event. | `verified` | Supplied repository fact: “payment status is rendered before webhook settlement.” | `detected` | must-preserve `REQ-001` |
| `INV-003` | The provider may time out after capture; a client-visible timeout is therefore not proof that no charge occurred. | `verified` | Supplied repository fact: “the provider may time out after capture.” | `detected` | must-preserve `REQ-001` |

## Impact ledger

| ID | Impact | Area | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Retrying an indeterminate timeout with a new idempotency key can create a duplicate provider charge after the first attempt captured successfully. | State/concurrency, data | `verified` | `INV-001`, `INV-003` (supplied facts) | `refining` | affects `REQ-001`, `INV-003`; produces `AC-001` |
| `IMP-002` | Retrying only after a local “failed” result can race with webhook settlement and show a retrying/failed state even though the original attempt later settles successfully. | State/concurrency, functionality | `verified` | `INV-002`, `INV-003` (supplied facts) | `refining` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | “Every failed” is ambiguous: definitive declines, transport errors, timeouts, validation errors, and post-capture timeouts do not have the same retry safety. | Functionality, interfaces | `inferred` | Failure classes are not specified in the supplied facts; timeout-after-capture is explicitly possible in `INV-003`. | `blocked` | affects `REQ-001`; produces `AC-003` |
| `IMP-004` | Unbounded or rapid automatic retries can multiply provider requests, increase customer-visible latency, and create operational load; attempt limits and backoff are unspecified. | Operations, functionality | `inferred` | The proposed change says “automatically” and “every,” but supplies no retry budget, backoff, or alerting policy. | `blocked` | affects `REQ-001`; produces `AC-004` |
| `IMP-005` | Because status is rendered before webhook settlement, the UI/API needs an explicit pending/reconciling state or equivalent behavior; otherwise a retry may be presented as a second payment action. | Functionality, interfaces, regression | `verified` | `INV-002`, `INV-003` (supplied facts) | `refining` | affects `REQ-001`, `INV-002`; produces `AC-005` |
| `IMP-006` | The provider’s exact idempotency behavior, status-query/reconciliation API, webhook ordering, and deduplication guarantees are unavailable, so end-to-end duplicate prevention cannot yet be verified. | Interfaces, state/concurrency | `unknown` | No provider specification or implementation evidence was supplied. | `blocked` | affects `REQ-001`; produces `AC-006` |
| `IMP-007` | Existing consumers, persisted payment records, and retry-related tests may impose compatibility and regression constraints, but were not inspected per scope. | Compatibility, data, regression | `unknown` | Repository inspection was limited to the supplied repository facts. | `blocked` | affects `REQ-001`; produces `AC-007` |

## Focused decision

Which behavior should define an automatically retryable charge?

1. **Recommended — bounded retry with the same idempotency key plus reconciliation:** retry only classified transient/definitive-safe failures; for timeouts or any unknown outcome, query/reconcile first and reuse the original key for any retry; use exponential backoff, a maximum attempt count, and terminal/manual-review handling.
2. **Retry every non-success response with the same idempotency key:** simpler policy, but still requires provider guarantees that repeated requests with the key return the original outcome and that unknown outcomes can be reconciled.
3. **Retry every non-success response with a new idempotency key:** easiest to implement, but explicitly accepts duplicate-charge risk after post-capture timeouts and should not be selected for POS payments without a separate customer-compensation design.

No user decision has been supplied yet; therefore no `DEC-###` is recorded. The impact ledger remains blocked where the choice or provider contract is required.

## Recorded decision

Pending `DEC-001` from the focused decision above. Silence is not acceptance.

## Whole-set recalculation and delta

No decision has been recorded, so there is no post-decision recalculation. Current complete set remains:

- `IMP-001`, `IMP-002`, and `IMP-005`: `refining` because the proposed requirement must explicitly account for indeterminate outcomes and pre-webhook status.
- `IMP-003`, `IMP-004`, `IMP-006`, and `IMP-007`: `blocked` pending the retry policy, provider contract, and repository evidence.
- No impacts are `resolved`, `accepted`, or `deferred`; no new impacts can be safely introduced until `DEC-001` is answered.

## Stop check and planning handoff

The requirement is not ready for implementation planning. Resolve the focused decision first, then recalculate all impacts. At minimum, the selected requirement must produce these acceptance criteria:

| ID | Acceptance / regression criterion | Evidence needed |
| --- | --- | --- |
| `AC-001` | A post-capture timeout never causes a second provider charge for the same logical payment; retries retain the original idempotency key and/or reconcile before retrying. | Provider contract plus integration test or recorded provider behavior. |
| `AC-002` | A timeout or unknown response transitions to a reconciling/pending state and later converges to the webhook settlement result without creating a second logical payment. | State-machine test and webhook/timeout race test. |
| `AC-003` | Retry classification explicitly lists retryable, non-retryable, and indeterminate failure classes. | Approved retry policy and provider error mapping. |
| `AC-004` | Automatic retries use bounded attempts, backoff, and a terminal/manual-review path; exhaustion is observable. | Configuration, metrics/log assertions, and exhaustion test. |
| `AC-005` | The pre-webhook rendered status cannot mislead the operator into initiating a duplicate payment while an automatic retry or reconciliation is active. | UI/API contract and regression test. |
| `AC-006` | Provider idempotency, status lookup, webhook ordering, and deduplication guarantees are documented or tested. | Provider specification or authoritative integration tests. |
| `AC-007` | Existing payment consumers and persisted records remain compatible, and adjacent payment flows retain their prior behavior. | Repository call-site/schema review and regression suite. |

Planning handoff: after `DEC-001` and the named provider/repository evidence are available, update `REQ-001`, recalculate the entire `IMP-001`–`IMP-007` set, and pass the refined requirement plus `AC-001`–`AC-007` to the implementation-planning workflow. Do not implement from the unresolved “retry every failed charge” wording.
