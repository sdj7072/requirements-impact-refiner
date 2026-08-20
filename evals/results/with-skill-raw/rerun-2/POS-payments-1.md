# Requirements impact refinement: POS payments

## Requirement revision

`REQ-001` — Retry every failed charge automatically.

Refined scope: a charge that is known to have failed may be retried automatically, while a request whose final provider outcome is unknown (including a timeout after capture) must not be treated as safely retryable until its outcome is reconciled. Every retry must preserve the original idempotency identity or use an explicitly defined idempotency relationship so that a provider cannot capture the same charge twice. The payment status shown to the user must remain consistent with webhook settlement and retry outcomes.

The wording “every failed charge” is not yet operationally complete: the pending decision must define what counts as failed versus unknown, the retry limit/backoff/window, and the terminal user-visible state after exhaustion.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`. | `verified` | Supplied repository fact: charge request contract | `must-preserve` by `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement. | `verified` | Supplied repository fact: payment-status rendering flow | `must-preserve` by `REQ-001` |
| `INV-003` | The provider may time out after capture, leaving the client without a definitive outcome. | `verified` | Supplied repository fact: provider timeout-after-capture behavior | `must-preserve` by `REQ-001` |

## Impact ledger

| ID | Impact | Severity | Evidence level | Evidence | State / links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | A retry after a provider timeout that occurred after capture can create a duplicate capture/charge. | Critical | `verified` | `INV-003`; provider may time out after capture | `refining`; affects `REQ-001`, `INV-003`; produces `AC-001` |
| `IMP-002` | Automatic retries must carry a stable idempotency identity; otherwise repeated attempts can be interpreted as new charges. | Critical | `verified` | `INV-001`; charge requests accept `idempotency_key` | `refining`; affects `REQ-001`, `INV-001`; produces `AC-002` |
| `IMP-003` | Rendering status before webhook settlement can show a failed or pending state while a prior attempt later settles successfully, causing misleading UI or duplicate customer action. | High | `verified` | `INV-002`; payment status is rendered before webhook settlement | `detected`; affects `REQ-001`, `INV-002`; produces `AC-003` |
| `IMP-004` | “Every failed charge” is ambiguous for transport timeouts and other indeterminate provider outcomes; retrying all non-success responses may retry a captured charge. | Critical | `inferred` | `INV-003` plus the proposed word “every” in `REQ-001`; no failure taxonomy supplied | `refining`; affects `REQ-001`, `INV-003`; produces `AC-004` |
| `IMP-005` | Without a bounded retry count, backoff, and retry window, a transient outage can cause retry storms, repeated customer notifications, or prolonged nonterminal payments. | High | `unknown` | Retry limits, schedule, and operational controls were not supplied | `blocked`; affects `REQ-001`; produces `AC-005` |
| `IMP-006` | Reconciliation and webhook ordering may race with an automatic retry, leaving the payment record in an incorrect terminal state. | High | `inferred` | `INV-002` and `INV-003`; settlement is webhook-driven and may arrive after the request | `detected`; affects `REQ-001`, `INV-002`, `INV-003`; produces `AC-006` |
| `IMP-007` | The customer-facing status and failure messaging need a distinct retrying/unknown/exhausted outcome; otherwise users may retry manually or believe they were charged twice. | Medium | `inferred` | `INV-002`; proposed automatic behavior changes the visible lifecycle | `detected`; affects `REQ-001`, `INV-002`; produces `AC-007` |

## One focused decision

Decision needed: what retry policy should govern a charge that is reported as failed or whose provider outcome is indeterminate?

1. **Conservative reconciliation (recommended):** retry only provider-confirmed non-capture failures; treat timeouts as `unknown`, reconcile by idempotency key/webhook before any new attempt, then apply a small bounded retry policy.
2. **Bounded broad retry:** retry provider-confirmed failures and selected transport failures with the same idempotency key, using a fixed maximum attempt count, exponential backoff, and a retry window; never retry an unresolved post-capture timeout until reconciliation.
3. **Unbounded “every failure” retry:** automatically retry all non-success responses until success. This leaves duplicate-charge and retry-storm risks unresolved and is not safe to accept without additional provider guarantees.

No stakeholder selection is recorded in the supplied request, so no `DEC-###` is created and no impact is marked `accepted`.

## Recorded decision

None. The retry classification, bounds, reconciliation behavior, and terminal-state policy remain the pending decision.

## Whole-set recalculation

Because no decision was supplied, the complete known impact set remains in scope. No impact is superseded; no new impact was found during refinement.

### Delta

- `resolved: none`
- `mitigated: none`
- `unchanged: IMP-003, IMP-004, IMP-006, IMP-007`
- `accepted: none`
- `deferred: none`
- `blocked: IMP-005` — retry count, backoff, retry window, and operational limits are unspecified.
- `new: none`

`IMP-001` and `IMP-002` remain `refining` rather than being repeated in a second delta category; their required safeguards are captured in the revised requirement and acceptance criteria below. The pending decision is still required before they can be resolved or accepted.

## Stop check and planning handoff

This is a report-only handoff. The refined requirement, preserved invariants, evidence-linked impact ledger, open decision, and testable criteria are ready for the implementation-planning workflow after the retry policy is selected. Do not treat this report as authorization for unbounded retries.

## Acceptance and regression criteria

| ID | Criterion | Evidence level | Verifies |
| --- | --- | --- | --- |
| `AC-001` | A provider timeout that may have occurred after capture never causes a second capture before the original attempt is reconciled; a later webhook or reconciliation result determines the single payment outcome. | `verified` baseline risk; test criterion pending implementation | `IMP-001`, `INV-003` |
| `AC-002` | Automatic retry attempts preserve the defined idempotency relationship, and repeated delivery of the same request cannot create more than one successful charge. | `verified` contract support; test criterion pending implementation | `IMP-002`, `INV-001` |
| `AC-003` | If status is rendered before settlement, the UI exposes a nonterminal/pending state and updates to the webhook-settled result without allowing a stale failed state to trigger an unsafe duplicate attempt. | `verified` baseline; test criterion pending implementation | `IMP-003`, `INV-002` |
| `AC-004` | The retry classifier distinguishes confirmed failure from unknown/post-capture timeout, and unknown outcomes follow reconciliation rather than immediate blind retry. | `inferred` from supplied facts; exact classifier pending decision | `IMP-004`, `INV-003` |
| `AC-005` | Retries obey an explicit maximum, backoff, and time window; exhaustion produces an observable terminal outcome and does not loop indefinitely. | `unknown` until policy is selected | `IMP-005` |
| `AC-006` | Webhook settlement, reconciliation, and retry processing are idempotent and order-safe: a late success cannot be overwritten by a stale failure or retry result. | `inferred` from supplied flow; test coverage pending | `IMP-006`, `INV-002`, `INV-003` |
| `AC-007` | Customer-visible status distinguishes retrying, unknown/pending reconciliation, succeeded, and exhausted/failed outcomes, with no instruction that would cause a duplicate manual charge. | `inferred`; product copy/state contract pending | `IMP-007`, `INV-002` |

