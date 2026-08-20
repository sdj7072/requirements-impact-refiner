# Requirements impact refinement: POS payments

## Requirement revision

`REQ-001` — Retry every failed charge automatically.

Refined scope: when a charge attempt is reported as failed or times out, the system should retry it automatically while preserving one logical payment outcome. Retries must use the available `idempotency_key`, must not create an additional capture when the provider captured the original request but the response timed out, and must not present a settled success before webhook settlement is known. The exact retryability classification, retry budget/backoff, and terminal customer-visible state remain pending decisions.

## Current behavior and preserved invariants

| ID | Current behavior or invariant | Evidence level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`. | `verified` | Supplied fact `F-001` | `must-preserve` `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement. | `verified` | Supplied fact `F-002` | `must-preserve` `REQ-001` |
| `INV-003` | A provider may time out after capture, so a timeout does not prove that no charge occurred. | `verified` | Supplied fact `F-003` | `must-preserve` `REQ-001` |
| `INV-004` | The current retry eligibility rules, retry budget/backoff, and terminal status vocabulary are not supplied. | `unknown` | No implementation, contract, or test artifacts were supplied for this review | `must-preserve` `REQ-001` until clarified |

## Impact ledger

| ID | Impact | Evidence level | Evidence | State | Links / acceptance |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Retrying with a new or missing idempotency key could create duplicate captures. | `verified` | `F-001` (idempotency key exists); `F-003` (capture may precede timeout) | `refining` | `affects` `REQ-001`, `INV-001`, `INV-003`; produces `AC-001` |
| `IMP-002` | A provider timeout after capture can be misclassified as a failed charge, causing a second capture or an incorrect failure shown to the customer. | `verified` | `F-003` | `refining` | `affects` `REQ-001`, `INV-003`; produces `AC-002` |
| `IMP-003` | Automatic retries may race with webhook settlement and overwrite a settled result or expose conflicting status. | `verified` | `F-002` plus `F-003` | `refining` | `affects` `REQ-001`, `INV-002`, `INV-003`; produces `AC-003` |
| `IMP-004` | “Every failed charge” may retry permanent failures (for example, invalid payment details or a declined instrument), causing repeated provider calls and poor customer experience. | `inferred` | Requirement wording `REQ-001`; no failure taxonomy supplied | `detected` | `affects` `REQ-001`; produces `AC-004` |
| `IMP-005` | An unbounded or unspecified retry budget/backoff can create duplicate workload, rate-limit pressure, and delayed terminal outcomes. | `unknown` | `INV-004`; retry policy artifacts unavailable | `blocked` | `affects` `REQ-001`; produces `AC-005` |
| `IMP-006` | Status rendered before webhook settlement may show an intermediate failure or pending state even when a later webhook confirms capture; clients need a stable transition model. | `verified` | `F-002`, `F-003` | `detected` | `affects` `REQ-001`, `INV-002`; produces `AC-006` |
| `IMP-007` | Observability and reconciliation requirements for retries, timeouts, duplicate suppression, and late webhooks are unspecified. | `unknown` | No metrics, logs, alerts, or runbook artifacts supplied | `blocked` | `affects` `REQ-001`; produces `AC-007` |

### Focused decision

Choose the retry contract for a charge that is reported failed or times out:

1. **Bounded safe retry (recommended):** retry only explicitly retryable failures and ambiguous timeouts; reuse the same logical payment/idempotency key, use bounded exponential backoff with a finite attempt limit, and leave the payment pending for reconciliation when capture status is unknown.
2. **Bounded retry for all provider-declared failures:** retry every provider failure up to a finite limit, still reusing the idempotency key; permanent-failure classification is deferred to the provider response.
3. **Unbounded automatic retry:** keep retrying until success or manual cancellation.

No concrete decision is recorded in this report; the choice remains the pending decision.

## Recorded decision

None. The request supplies the desired outcome but does not select a retryability taxonomy, attempt limit, backoff, or timeout-reconciliation policy. Therefore no `DEC-###` is allocated and no impact is marked `accepted`.

## Whole-set recalculation

Because no decision was supplied, the requirement remains in refinement and all known impacts are retained. No impact is superseded; no new impact was identified during recalculation.

- `resolved: none`
- `mitigated: none`
- `unchanged: ` `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-006`
- `accepted: none`
- `deferred: none`
- `blocked: ` `IMP-005`, `IMP-007`
- `new: none`

## Acceptance and regression criteria

- `AC-001` — A retry reuses the same logical idempotency key; a provider replay of the request cannot create a second capture.
- `AC-002` — If the provider may have captured before a timeout, the system does not issue an independent capture; it enters an explicitly defined pending/reconciliation path and adopts the webhook result.
- `AC-003` — A late settlement webhook is idempotent and wins over an earlier provisional failure/pending display without creating a second payment outcome.
- `AC-004` — The selected retry contract has executable classification tests proving which failures are retried and which become terminal without another charge request.
- `AC-005` — The selected contract defines and tests maximum attempts, backoff, cancellation, and behavior after the budget is exhausted.
- `AC-006` — Customer-visible status transitions are monotonic and documented: a pre-webhook status cannot permanently contradict a later settled webhook.
- `AC-007` — Each attempt, idempotency key, provider response/timeout, webhook correlation, deduplication event, and terminal outcome is observable for reconciliation and alerting.

## Stop check and planning handoff

This is a report-only handoff. The material risks are linked to `REQ-001`, with `IMP-005` and `IMP-007` blocked on missing retry/operations evidence and the remaining impacts awaiting the pending decision. Planning may proceed only after the retry contract is selected and the whole-set ledger is recalculated; implementation work breakdown is intentionally not included here.
