# Requirements impact refinement: POS payments

## Requirement revision

`REQ-001` — Retry failed charge requests automatically, while preserving a single customer charge when the provider outcome is uncertain and making the final payment state observable after webhook settlement.

The supplied request mandates automatic retry for every failed charge. That wording is not yet implementation-ready because “failed” can mean a definitive pre-capture rejection or an indeterminate provider timeout after capture. The refined requirement therefore keeps the mandate but adds the safety boundary that a retry must not create a second capture. The retry count, backoff, retryable failure classification, and terminal outcome still require one policy decision.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`. | `verified` | Supplied repository fact: “charge requests accept an idempotency_key.” | `must-preserve` by `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement. | `verified` | Supplied repository fact: “payment status is rendered before webhook settlement.” | `must-preserve` by `REQ-001` |
| `INV-003` | The provider may time out after capture, so a timeout does not prove that no charge occurred. | `verified` | Supplied repository fact: “the provider may time out after capture.” | `must-preserve` by `REQ-001` |

## Impact ledger

| ID | Impact | Category | Level | Evidence | State | Links / resulting criterion |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Retrying with a new key after a post-capture timeout can create a duplicate customer charge. | State/concurrency, regression | `verified` | `INV-001`, `INV-003` | `detected` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | Retrying with the same idempotency key may safely deduplicate a repeated request, but the provider’s replay/lookup semantics and retention window are not supplied. | State/concurrency, interfaces | `unknown` | `INV-001`; provider behavior not supplied | `blocked` | `affects` `REQ-001`; named gap: provider idempotency semantics and retention |
| `IMP-003` | A status rendered before webhook settlement can show a provisional result while an automatic retry or later webhook changes the authoritative state. | Functionality, interfaces | `verified` | `INV-002` | `detected` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-004` | Without an explicit retryability classification, “every failed charge” could retry permanent declines, malformed requests, or policy failures and produce noisy or harmful repeated attempts. | Functionality, state/concurrency | `inferred` | `REQ-001`; no supplied failure taxonomy | `detected` | `affects` `REQ-001`; `produces` `AC-003` |
| `IMP-005` | Automatic retries need bounded attempts/backoff and durable recovery after worker or process failure; otherwise one failure can create an unbounded request loop or be silently lost. | Operations, state/concurrency | `inferred` | `REQ-001`; no retry/job/alert policy supplied | `detected` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-006` | Existing clients may observe new intermediate, retrying, or reconciliatory payment states and may need stable API/event semantics. | Compatibility, interfaces | `inferred` | `INV-002`; no published state contract supplied | `detected` | `affects` `REQ-001`, `INV-002`; `produces` `AC-005` |
| `IMP-007` | Charge-attempt records, retry metadata, and provider references may need persistence for deduplication, audit, support, and reconciliation; the available schema is not supplied. | Data, operations | `unknown` | `INV-001`, `INV-003`; schema unavailable | `blocked` | `affects` `REQ-001`; named gap: attempt/outcome persistence model |

## Decision needed

How should an automatic retry handle an indeterminate provider timeout that may have happened after capture?

1. Retry the same request with the original `idempotency_key`, with bounded backoff, and reconcile the provider result before declaring failure (recommended; safest against duplicate capture).
2. Do not retry indeterminate timeouts automatically; mark the payment pending and reconcile asynchronously, while retrying only definitive pre-capture failures.
3. Retry all failures, including timeouts, with newly generated keys (not recommended because it conflicts with `INV-003` and risks duplicate charges).

No `DEC-###` is recorded because the request does not select one of these policies.

## Whole-set recalculation

No stakeholder decision was supplied, so no impact is accepted or resolved by choice. The complete current delta is:

| Delta | Impacts |
| --- | --- |
| `resolved` | `none` |
| `mitigated` | `none` |
| `unchanged` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `IMP-007` remain as listed |
| `accepted` | `none` — no `DEC-###` |
| `deferred` | `none` |
| `blocked` | `IMP-002`, `IMP-007`, pending provider and schema evidence |
| `new` | `none` |

## Acceptance and regression criteria

- `AC-001`: For a provider timeout after capture, an automatic retry cannot create a second capture for the same logical charge; the behavior must be demonstrated with the selected idempotency/reconciliation policy.
- `AC-002`: The pre-webhook response clearly represents a provisional/pending state, and a later webhook or reconciliation transitions it to the authoritative final state without regressing a settled result.
- `AC-003`: Each retry decision is covered by an explicit failure classification; permanent failures are not retried indefinitely.
- `AC-004`: Retries are bounded and durable across worker/process restarts, with observable attempt count, backoff, terminal failure, and operator-relevant errors.
- `AC-005`: Existing payment clients and webhook consumers remain compatible with any new retrying, pending, reconciled, or terminal states.

## Stop check and planning handoff

The requirement is refined and the preserved invariants, impacts, evidence levels, open information gaps, and acceptance criteria are recorded. Planning should not start until the timeout policy is selected and provider idempotency semantics plus the attempt/outcome persistence model are verified. At that point, record the selected choice as `DEC-001`, recalculate every `IMP-###`, and hand the resulting report to the implementation-planning workflow.
