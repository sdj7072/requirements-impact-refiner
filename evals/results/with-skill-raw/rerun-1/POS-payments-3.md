# Requirements impact refinement: POS payments

## Requirement revision

`REQ-001` (original): Retry every failed charge automatically.

`REQ-002` (refined candidate; no decision recorded): Automatically retry a charge only when the outcome is retryable or indeterminate, using the original `idempotency_key`, bounded backoff, and provider-status reconciliation. Do not create a second charge for a confirmed successful capture, and do not retry a confirmed terminal failure. The retry budget, delay schedule, failure classification, and customer-visible status policy remain a **Decision needed**.

The supplied facts make “every failed charge” unsafe as an unconditional rule: a provider may time out after capture, while the payment status is rendered before webhook settlement.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`; retries must preserve the key for the same logical charge. | `verified` | Supplied repository fact: “charge requests accept an idempotency_key” | `detected` | `must-preserve` `REQ-002` |
| `INV-002` | Payment status can be rendered before webhook settlement is received. | `verified` | Supplied repository fact: “payment status is rendered before webhook settlement” | `detected` | `must-preserve` `REQ-002` |
| `INV-003` | The provider may time out after capture, so a timeout is not proof that no charge occurred. | `verified` | Supplied repository fact: “the provider may time out after capture” | `detected` | `must-preserve` `REQ-002` |

## Impact ledger

| ID | Category | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | State/concurrency | Retrying with a new key after a post-capture timeout can double-charge the customer. | `verified` | `INV-001`, `INV-003` | `refining` | `affects` `REQ-002`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | State/concurrency | A retry worker needs a reconciliation step for indeterminate outcomes; otherwise it can race provider capture and webhook delivery. | `verified` | `INV-002`, `INV-003` | `refining` | `affects` `REQ-002`, `INV-002`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | Functionality | “Failed” must distinguish confirmed terminal failure from retryable or indeterminate failure; retrying all failures may repeat declines or invalid requests. | `inferred` | Original wording `REQ-001`; no failure taxonomy supplied | `blocked` | `affects` `REQ-002`; `produces` `AC-003` |
| `IMP-004` | Interfaces | The pre-webhook status view may show failure/pending while a later webhook settles success; the status contract needs an explicit pending/indeterminate representation and idempotent webhook handling. | `verified` | `INV-002`, `INV-003` | `refining` | `affects` `REQ-002`, `INV-002`; `produces` `AC-004` |
| `IMP-005` | Data | Charge-attempt state, retry count, original key, provider reference, and reconciliation result must be durable enough to survive worker restarts and prevent duplicate attempts. | `inferred` | `INV-001`–`INV-003`; persistence details not supplied | `blocked` | `affects` `REQ-002`; `produces` `AC-005` |
| `IMP-006` | Operations | Automatic retries can amplify provider incidents and increase traffic; metrics, alerts, rate limits, a kill switch, and a bounded retry policy are required. | `inferred` | Retry behavior in `REQ-001`; operational configuration not supplied | `blocked` | `affects` `REQ-002`; `produces` `AC-006` |
| `IMP-007` | Regression | Existing successful, declined, timeout, and webhook-settlement flows need regression coverage; no test inventory was supplied. | `unknown` | Tests unavailable in supplied evidence | `blocked` | `affects` `REQ-002`, `INV-001`–`INV-003`; `produces` `AC-007` |
| `IMP-008` | Compatibility | Existing clients may interpret an early rendered failure as final; introducing pending/indeterminate status may require a backward-compatible contract change. | `unknown` | `INV-002`; client/version support not supplied | `blocked` | `affects` `REQ-002`, `INV-002`; `produces` `AC-008` |
| `IMP-009` | Authorization/privacy | Retry and reconciliation logs may contain payment/provider identifiers; access, masking, and retention requirements are not supplied. | `unknown` | No policy or audit evidence supplied | `blocked` | `affects` `REQ-002`; `produces` `AC-009` |
| `IMP-010` | Legal/policy | Automatic reattempts, customer notification, and duplicate/late-settlement handling may be subject to payment-network or regional policy. | `unknown` | No legal/policy evidence supplied | `blocked` | `affects` `REQ-002`; `produces` `AC-010` |

## Focused decision

**Decision needed:** What retry policy should govern a provider outcome that is failed or indeterminate?

1. **Conservative (recommended):** retry only explicitly retryable failures; reconcile every timeout/unknown outcome before any new attempt; use the same idempotency key; bounded attempts and backoff; expose `pending` until settlement is known.
2. **Availability-first:** retry retryable failures immediately and retry unknown outcomes after a short reconciliation window, still reusing the key and enforcing a strict cap; status may remain pending during the window.
3. **Literal “every failed charge”:** retry all failures, including unknown outcomes, with a new attempt after a fixed delay. This preserves the original wording but leaves material duplicate-charge and repeated-decline risk unresolved.

No option has been selected, so no `DEC-###` is created and no impact is marked `accepted`.

## Acceptance and regression criteria

| ID | Criterion | Evidence target | Produced by |
| --- | --- | --- | --- |
| `AC-001` | A post-capture provider timeout never causes a second capture for the same logical charge; all retries use the original idempotency key. | Provider/request traces and idempotency integration test | `IMP-001` |
| `AC-002` | Timeout/unknown outcomes enter reconciliation and cannot be retried concurrently with an unresolved capture. | State-transition/race test | `IMP-002` |
| `AC-003` | Confirmed terminal failures are not retried; retryable classifications have an explicit, tested allowlist. | Failure-classification tests/specification | `IMP-003` |
| `AC-004` | A pre-webhook response cannot permanently report failure when a later success webhook settles the charge; webhook processing is idempotent. | API/webhook contract and integration test | `IMP-004` |
| `AC-005` | Worker restart preserves logical charge identity, retry count, provider reference, and reconciliation state. | Persistence/restart test | `IMP-005` |
| `AC-006` | Retry volume is bounded and observable, with metrics, alerting, rate limiting, and an operational disable path. | Runbook/configuration/telemetry checks | `IMP-006` |
| `AC-007` | Success, terminal decline, transient failure, post-capture timeout, duplicate webhook, and late settlement are covered by regression tests. | Test inventory and CI results | `IMP-007` |
| `AC-008` | Existing clients receive a compatible status or a versioned contract for pending/indeterminate settlement. | Client contract/compatibility test | `IMP-008` |
| `AC-009` | Retry/reconciliation telemetry masks payment-sensitive data and follows an approved retention/access policy. | Logging and access-policy review | `IMP-009` |
| `AC-010` | The selected retry and notification behavior is approved for applicable payment and regional policies. | Policy approval record | `IMP-010` |

## Whole-set recalculation and delta

Because no policy option was selected, the requirement remains `REQ-002` as a refined candidate and all impacts remain in the ledger.

- `resolved: none`
- `mitigated: none` (the candidate requirement identifies safeguards but does not establish an approved policy)
- `unchanged: IMP-001, IMP-002, IMP-004`
- `accepted: none` (no `DEC-###`)
- `deferred: none`
- `blocked: IMP-003, IMP-005, IMP-006, IMP-007, IMP-008, IMP-009, IMP-010` pending the named evidence and/or policy choice
- `new: none`

## Stop check and planning handoff

The report-only refinement handoff is ready. Before implementation planning, record one choice as `DEC-###`, then recalculate the complete impact set. Planning should use `REQ-002`, preserved invariants `INV-001`–`INV-003`, the impact ledger, and acceptance criteria `AC-001`–`AC-010`. The principal open risks are duplicate capture after post-capture timeout, premature failure display before webhook settlement, unbounded retry amplification, and unknown compatibility/policy constraints.
