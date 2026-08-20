# Requirements impact refinement: POS payments

## Requirement revision

`REQ-001` (refined): Automatically retry a charge when the provider has established that the charge failed, while preserving the existing idempotency contract and keeping payment status truthful until provider settlement is known. The retry policy must explicitly define how provider timeouts after capture are classified, how retries are bounded and delayed, and how the same logical charge is correlated across attempts.

The request says “Retry every failed charge automatically.” It does not by itself select a retry limit, backoff, timeout-reconciliation policy, or user-visible pending state. Those choices remain open below.

## Current behavior and preserved invariants

| ID | Current behavior to preserve | Level | Evidence | Link |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`. | `verified` | Supplied repository fact: “charge requests accept an idempotency_key” | `must-preserve` `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement. | `verified` | Supplied repository fact: “payment status is rendered before webhook settlement” | `must-preserve` `REQ-001` |
| `INV-003` | The provider may time out after capture, so a timeout does not necessarily mean that no charge occurred. | `verified` | Supplied repository fact: “the provider may time out after capture” | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Category | Level | Evidence | State | Links / acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Retrying a request whose provider call timed out after capture can create a duplicate charge unless the retry reuses the same logical idempotency identity and the provider’s idempotency behavior is honored. | State/concurrency, regression | `verified` | `INV-001`, `INV-003` | `refining` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | Because status is rendered before webhook settlement, an automatic retry can show a transient failure or success while the original attempt is still awaiting settlement; the UI and downstream actions could diverge from the final provider result. | Functionality, interfaces, regression | `verified` | `INV-002`, `INV-003` | `refining` | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | The retry flow must retain and propagate the idempotency key for the logical charge; generating a new key per attempt would weaken the existing duplicate-prevention contract. | Interfaces, state/concurrency | `inferred` | `INV-001`; the request does not state whether keys are persisted across attempts | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-003` |
| `IMP-004` | “Every” failed charge can cause unbounded retries, repeated provider traffic, customer-visible churn, or an operational retry storm unless attempts, delay, and terminal handling are bounded. | Operations, state/concurrency | `inferred` | The request specifies no maximum, backoff, queue, or rate-limit policy | `detected` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Automatic retries require durable attempt/outcome correlation so a worker restart or duplicate delivery does not lose the logical charge state or retry the wrong attempt. | Data, state/concurrency | `inferred` | Retry behavior is requested, but no attempt storage or state model is supplied | `detected` | `affects` `REQ-001`; `produces` `AC-005` |
| `IMP-006` | The provider’s exact distinction between definitive failure, accepted/pending, and post-capture timeout is unavailable; safe classification and reconciliation cannot be verified from the supplied facts. | Interfaces, state/concurrency | `unknown` | No provider error taxonomy, idempotency semantics, or status/reconciliation contract supplied | `blocked` | `affects` `REQ-001`, `INV-003`; `produces` `AC-006` |

No supplied evidence indicates a new authorization/privacy or legal/policy impact. Compatibility impact is currently `unknown` because supported clients and external consumers are not supplied; it should be checked during planning if the status or webhook contract changes.

## One focused decision

**Decision needed:** How should an automatic retry treat a provider timeout that may have happened after capture, and what retry bound should apply?

1. **Reconcile before retry (safest):** retry only definitive provider failures; classify post-capture timeouts as pending, reconcile by provider status/webhook, and use a finite retry limit with backoff for definitive failures.
2. **Bounded idempotent timeout retries:** retry definitive failures and timeouts with the same logical `idempotency_key`, exponential backoff, and a finite maximum; reconcile any final ambiguous outcome.
3. **Unbounded retry-until-success:** retry all non-success outcomes until success. This satisfies the literal “every” wording but leaves duplicate, load, and customer-impact risks unresolved and is not suitable for acceptance without an explicit operational policy.

No `DEC-###` is recorded because no stakeholder selection was supplied.

## Whole-set recalculation (before decision)

| Delta state | Impacts |
| --- | --- |
| `resolved` | none |
| `mitigated` | none |
| `unchanged` | none; this is the initial refinement ledger |
| `accepted` | none; silence is not acceptance |
| `deferred` | none |
| `blocked` | `IMP-006` — provider error/status semantics are missing |
| `new` | none |

## Acceptance and regression criteria

| ID | Criterion | Verifies |
| --- | --- | --- |
| `AC-001` | A provider timeout after capture cannot cause two successful captures for one logical charge; retries use the documented idempotency behavior and final outcome is reconciled. | `IMP-001`, `INV-003` |
| `AC-002` | Before webhook/provider settlement, the rendered status remains an explicitly non-final state (or otherwise follows the existing contract); it does not claim a final result solely because a retry was queued or returned. | `IMP-002`, `INV-002` |
| `AC-003` | All attempts for one logical charge carry the preserved idempotency identity, and a repeated worker/event delivery is harmless. | `IMP-003`, `INV-001` |
| `AC-004` | Definitive failures follow a documented maximum-attempt, backoff, and terminal-action policy; retries do not continue indefinitely or exceed configured operational limits. | `IMP-004` |
| `AC-005` | Attempt state and provider correlation survive worker restart and duplicate delivery, with no lost or mis-associated retry. | `IMP-005` |
| `AC-006` | The provider’s error taxonomy, idempotency-key scope/lifetime, and reconciliation behavior are documented or tested sufficiently to distinguish definitive failure from post-capture uncertainty. | `IMP-006` |

## Stop check and planning handoff

The report-only handoff is ready once the timeout/retry option is selected and the provider semantics in `IMP-006` are supplied or verified. Until then, `IMP-001` through `IMP-005` remain detected/refining rather than accepted or resolved. Planning should use `REQ-001`, preserve `INV-001`–`INV-003`, and carry `AC-001`–`AC-006`; this document intentionally does not prescribe an implementation work breakdown.
