# Requirements impact refinement — POS payments

## Requirement revision

`REQ-001` — Retry every failed charge automatically.

This is refined as: a charge that is eligible for retry is retried by the system without requiring a cashier or customer action, while preserving the existing charge identity and preventing a second capture when the provider outcome is ambiguous. The retryable failure classes, attempt limit, backoff, and handling of an outcome that may have captured must be selected before implementation planning.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`; retries must not accidentally create an additional logical charge. | `verified` | Supplied repository fact: charge requests accept an `idempotency_key` | `detected` | `must-preserve` `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement, so the displayed status can precede the provider’s final settlement event. | `verified` | Supplied repository fact: payment status is rendered before webhook settlement | `detected` | `must-preserve` `REQ-001` |
| `INV-003` | The provider may time out after capture; a timeout is therefore not proof that no charge occurred. | `verified` | Supplied repository fact: provider may time out after capture | `detected` | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Blindly retrying a post-capture timeout can create a duplicate capture or duplicate customer charge. | `verified` | `INV-001`, `INV-003`; supplied provider timeout-after-capture fact | `blocked` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | A pre-webhook rendered failure may be provisional; automatic retry or a failure message can race with the later settlement webhook. | `verified` | `INV-002`; supplied payment-status-before-webhook fact | `blocked` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | Reusing or regenerating idempotency keys changes whether attempts represent one logical charge or independent charges; the required scope is not specified. | `verified` | `INV-001` | `blocked` | `affects` `REQ-001`, `INV-001`; `produces` `AC-003` |
| `IMP-004` | “Every failed charge” does not define retryable failure classes, maximum attempts, backoff, or a terminal state, so the system could retry permanent declines indefinitely or create an unbounded queue. | `unknown` | No retry classification, limit, backoff, or terminal-state policy was supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Customer/operator-visible status and reconciliation behavior are unspecified while a retry or provider lookup is pending. | `inferred` | `INV-002`, `INV-003`; no pending/reconciliation behavior supplied | `blocked` | `affects` `REQ-001`, `INV-002`; `produces` `AC-005` |
| `IMP-006` | Retry attempts need observable outcomes and safe recovery signals; without attempt records, duplicate-prevention evidence and alerts are difficult to validate operationally. | `inferred` | `INV-001`–`INV-003`; no attempt/audit/alert contract supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-006` |

### Decision needed

For a timeout or other outcome that may have occurred after capture, which retry policy should define “every failed charge”?

1. **Reconcile first (recommended):** do not issue another capture while the outcome is ambiguous; query/reconcile the provider, then retry only after a confirmed non-capture or terminal failure. Use a bounded retry policy for definitively retryable failures.
2. **Same-key provider idempotency:** retry with the same logical idempotency key and rely on the provider’s documented replay semantics, still with bounded attempts. This is acceptable only if the provider’s persistence and post-capture semantics are confirmed.
3. **Retry immediately:** issue a bounded retry for every local failure, including ambiguous timeouts. This maximizes automatic recovery but explicitly accepts duplicate-charge risk and requires compensating refunds/reconciliation.

No stakeholder selection has been supplied, so no `DEC-###` is recorded and no impact is marked `accepted`.

## Whole-set recalculation (before decision)

| Delta category | Result |
| --- | --- |
| `resolved` | none |
| `mitigated` | none |
| `unchanged` | `IMP-001`–`IMP-006` remain blocked pending the retry/outcome policy and supporting provider contract |
| `accepted` | none; silence is not acceptance |
| `deferred` | none; the policy is required to define the behavior |
| `blocked` | `IMP-001`–`IMP-006`, due to the named retry classification, idempotency scope, reconciliation, and observability gaps |
| `new` | none |

## Stop check and planning handoff

The requirement is refined enough to expose the implementation boundary, but planning must wait for the single policy decision above and confirmation of the provider’s idempotency/reconciliation semantics. After selection, recalculate all six impacts and record `DEC-001` linked to `REQ-001`; obsolete findings must be superseded rather than silently dropped.

Acceptance and regression criteria:

- `AC-001` (from `IMP-001`): a provider timeout that may follow capture never causes a second capture before reconciliation, or the selected policy’s explicitly documented compensating control is exercised.
- `AC-002` (from `IMP-002`): a webhook settlement supersedes any provisional rendered failure, and the UI/API does not present an unreconciled retry as a confirmed second payment.
- `AC-003` (from `IMP-003`): retry attempts use the selected idempotency-key scope consistently, and repeated delivery/retry of the same logical charge is demonstrably duplicate-safe.
- `AC-004` (from `IMP-004`): only the selected retryable failure classes retry; attempts are bounded with deterministic backoff and a terminal outcome for permanent failures.
- `AC-005` (from `IMP-005`): pending, reconciled-success, reconciled-failure, and terminal states are distinct and remain consistent across rendering and webhook settlement.
- `AC-006` (from `IMP-006`): each attempt and reconciliation result is observable enough to diagnose retries, duplicate prevention, and exhausted attempts, with an alert/recovery path for stuck ambiguity.

