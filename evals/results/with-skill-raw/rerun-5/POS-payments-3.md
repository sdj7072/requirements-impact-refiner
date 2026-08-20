# Requirements impact refinement — payments 3

## Requirement revision

`REQ-001` — Retry every failed charge automatically.

Supplied constraints/invariants: charge requests accept `idempotency_key`; payment status is rendered before webhook settlement; a provider may time out after capture. No exact retry schedule, failure classification, attempt limit, or terminal-status policy was selected.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Links |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`, which must remain usable for retry attempts. | `verified` | User-supplied fact: “charge requests accept idempotency_key” | `must-preserve` `REQ-001` |
| `INV-002` | Payment status can be rendered before webhook settlement is received. | `verified` | User-supplied fact: “payment status rendered before webhook settlement” | `must-preserve` `REQ-001` |
| `INV-003` | The provider may time out after capture, so a timeout does not establish that no charge occurred. | `verified` | User-supplied fact: “provider may time out after capture” | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Retrying a request without preserving the same idempotency identity could create a duplicate charge when the first attempt captured funds but its response was lost. | `inferred` | `INV-001`, `INV-003`; user-supplied payment facts | `refining` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | A pre-webhook rendered status may show a failed or non-settled result while an automatic retry or the original attempt later settles, causing a transient status contradiction. | `inferred` | `INV-002`, `INV-003`; user-supplied payment facts | `refining` | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | The requirement does not define which failures are retryable; retrying a permanent decline or malformed request could repeat an invalid charge and create avoidable provider load. | `unknown` | No failure taxonomy, provider error mapping, or retry policy supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-003` |
| `IMP-004` | The requirement does not define backoff, maximum attempts, or the terminal state after repeated failures, so automatic retries could continue indefinitely or delay a reliable failure result. | `unknown` | No retry schedule, attempt limit, or terminal-status policy supplied | `blocked` | `affects` `REQ-001`, `INV-002`; `produces` `AC-004` |
| `IMP-005` | The requirement does not define how retries and late webhooks are ordered or reconciled, leaving the final payment status and customer-visible outcome uncertain. | `unknown` | No settlement state machine, webhook ordering guarantee, or reconciliation rule supplied | `blocked` | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-005` |

## One focused decision

How should automatic retries be bounded and reconciled with an uncertain provider outcome?

1. Retry only explicitly transient/provider-timeout failures, reuse the original idempotency key, use bounded exponential backoff, and keep the payment pending until webhook/reconciliation determines the final state.
2. Retry all non-success responses up to a fixed attempt limit, then mark the payment failed while allowing late webhooks to reconcile it.
3. Retry asynchronously through a durable payment-attempt queue with provider-specific classification, bounded backoff, and an explicit reconciliation state machine.

The pending decision must select one policy (or supply an equivalent explicit policy) before a concrete `DEC-###` can be recorded. No recorded decision exists in the supplied request.

## Recorded decision

None. The pending decision is not selected; therefore no concrete `DEC-###` is allocated or linked.

## Whole-set recalculation

No user/stakeholder selection changed the requirement or the impact set. All known impacts were re-evaluated:

- `IMP-001` remains `refining` because idempotency preservation is required but the retry wire is not selected.
- `IMP-002` remains `refining` because pre-webhook rendering must coexist with eventual settlement, but the state/reconciliation behavior is not selected.
- `IMP-003`, `IMP-004`, and `IMP-005` remain `blocked` by the named policy/state-machine gaps.

## Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-002`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-003`, `IMP-004`, `IMP-005`
- `new`: none

## Stop check and planning handoff

The refined requirement is to add automatic retries while preserving idempotency-key semantics, pre-webhook status rendering, and the possibility of post-capture provider timeouts. Planning is blocked until the pending retry/reconciliation policy is explicitly selected and recorded.

Acceptance criteria for the eventual selected policy:

- `AC-001` — A retry after an ambiguous timeout reuses the charge’s idempotency identity and cannot create a second capture for the same logical charge (`IMP-001`).
- `AC-002` — A status rendered before webhook settlement converges to the provider/webhook outcome without exposing a contradictory duplicate-charge result (`IMP-002`).
- `AC-003` — Permanent/non-retryable failures are not retried, according to the selected provider error classification (`IMP-003`).
- `AC-004` — Retries follow a finite, observable backoff/attempt policy and reach a defined terminal outcome (`IMP-004`).
- `AC-005` — Late, duplicated, or reordered webhooks reconcile deterministically with retry attempts and the customer-visible payment status (`IMP-005`).

