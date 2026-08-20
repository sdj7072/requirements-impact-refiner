# Requirements impact refinement: POS payments

## Requirement revision

`REQ-001` — Automatically retry a charge when the payment attempt is considered failed, while preserving the provider’s idempotency contract and preventing duplicate capture. The retry classification, attempt limit, backoff, and treatment of ambiguous provider timeouts remain to be selected.

Scope is limited to charge attempts and their payment-status presentation. No repository files beyond the supplied facts were inspected.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`. A retry must be correlated to the same logical charge rather than create an uncorrelated capture. | verified | Supplied repository fact: “charge requests accept an idempotency_key” | detected | `must-preserve` `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement arrives, so the initial status can precede the provider’s authoritative settlement result. | verified | Supplied repository fact: “payment status is rendered before webhook settlement” | detected | `must-preserve` `REQ-001` |
| `INV-003` | The provider may time out after capture, making a client-visible timeout insufficient to conclude that no capture occurred. | verified | Supplied repository fact: “the provider may time out after capture” | detected | `must-preserve` `REQ-001` |
| `INV-004` | Existing authorization, persistence, queue, observability, compatibility, policy, and regression behavior is not established by the supplied facts. | unknown | Repository inspection intentionally limited to supplied facts | blocked | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Category | Level | Evidence | State | Links / acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | A retry that changes or omits `idempotency_key` can produce a duplicate capture or an untraceable second charge. | State/concurrency; interfaces | verified | `INV-001`; supplied charge-request contract | refining | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Retrying a timeout after capture can double-charge the customer unless the system reconciles the original attempt before issuing another capture. | State/concurrency; functionality | verified | `INV-003` | refining | affects `REQ-001`, `INV-003`; produces `AC-002` |
| `IMP-003` | “Every failed charge” is ambiguous: transport failure, provider-declined payment, validation failure, and an unresolved timeout may require different handling. | Functionality; state/concurrency | inferred | `REQ-001` wording plus `INV-003`; no failure taxonomy supplied | blocked | affects `REQ-001`; produces `AC-003` |
| `IMP-004` | Unbounded or rapid retries can create duplicate work, provider load, customer confusion, and an outage-amplifying retry storm. | Operations; state/concurrency | inferred | Automatic retry behavior implied by `REQ-001`; retry policy not supplied | blocked | affects `REQ-001`; produces `AC-004` |
| `IMP-005` | Because status renders before webhook settlement, the UI may show a transient failure or pending state while a retry is already queued, and later webhook delivery may arrive out of order. | Functionality; interfaces; regression | verified | `INV-002` | refining | affects `REQ-001`, `INV-002`; produces `AC-005` |
| `IMP-006` | Retry attempts need durable attempt identity and an auditable link to the original charge; otherwise reconciliation, support, and recovery are incomplete. | Data; operations | inferred | `INV-001` and `INV-003`; persistence/audit schema not supplied | blocked | affects `REQ-001`; produces `AC-006` |
| `IMP-007` | Existing client/API consumers may observe additional pending, retrying, or terminal statuses and changed timing. | Interfaces; compatibility | inferred | `INV-002`; published status contract and consumers not supplied | blocked | affects `REQ-001`, `INV-002`; produces `AC-007` |
| `IMP-008` | Authentication, authorization, privacy, retention, legal/policy, deployment, alerting, backup, and rollback effects cannot be assessed from the supplied facts. | Authorization/privacy; legal/policy; operations | unknown | No repository or policy evidence supplied | blocked | affects `REQ-001`; validation gap |
| `IMP-009` | Existing tests for duplicate capture, webhook ordering, timeout recovery, and status transitions are unknown; absence of test evidence is not evidence of coverage. | Regression | unknown | No test files inspected | blocked | affects `REQ-001`, `INV-001`–`INV-003`; produces `AC-001`–`AC-007` |

## One focused decision

**Decision needed:** What retry policy should define “failed,” especially for an ambiguous timeout after possible capture?

1. **Conservative reconciliation (recommended):** retry only confirmed retryable transport/provider failures; treat post-capture timeouts as `pending/reconcile`, query or await webhook settlement using the same idempotency key, and use a bounded exponential backoff with a small maximum attempt count.
2. **Bounded retry of all non-successes:** retry declines and unresolved timeouts as well, with a fixed maximum and backoff. This risks retrying non-retryable declines and post-capture timeouts.
3. **Single automatic retry:** retry once for transport failures only; route all other failures and ambiguous timeouts to manual/reconciliation handling. This minimizes automation risk but gives less recovery.

No stakeholder selection was supplied, so no `DEC-###` is recorded and no impact is marked `accepted`.

## Recorded decision

None. The focused policy choice above is still required.

## Whole-set recalculation

No decision was recorded; the complete current impact set remains in force. The requirement is refined only to expose the unresolved retry policy and preserve the supplied invariants.

### Delta

- `resolved`: none.
- `mitigated`: `IMP-001`, `IMP-002`, and `IMP-005` are narrowed by the explicit preservation of idempotency, settlement reconciliation, and status ordering, but remain open pending policy/design evidence.
- `unchanged`: none.
- `accepted`: none; no `DEC-###` exists.
- `deferred`: none.
- `blocked`: `IMP-003`, `IMP-004`, `IMP-006`, `IMP-007`, `IMP-008`, and `IMP-009` remain blocked by the missing policy choice and/or repository evidence.
- `new`: none.

## Acceptance and regression criteria

| ID | Criterion | Verifies |
| --- | --- | --- |
| `AC-001` | Every automatic retry reuses the logical charge’s idempotency key (or an explicitly documented provider-safe idempotency strategy), and duplicate capture is prevented. | `INV-001`, `IMP-001` |
| `AC-002` | If the provider can time out after capture, the system reconciles the original attempt before issuing another capture and never creates two captures for one logical charge. | `INV-003`, `IMP-002` |
| `AC-003` | The selected policy has an explicit retryability matrix for transport errors, provider declines, validation errors, and ambiguous post-capture timeouts. | `IMP-003` |
| `AC-004` | Retries are durable, bounded, backoff-controlled, observable, and safe under worker/job redelivery; exhaustion reaches a documented terminal state. | `IMP-004`, `IMP-006` |
| `AC-005` | Status transitions remain monotonic/reconcilable when the initial render, retry result, and webhook arrive in any supported order; a late webhook cannot be overwritten by a stale retry result. | `INV-002`, `IMP-005` |
| `AC-006` | Each retry attempt, provider response, idempotency key, reconciliation outcome, and terminal result are linked in durable records suitable for support and audit. | `IMP-006` |
| `AC-007` | Existing API/UI consumers either continue to function or receive a versioned/documented contract for any new retrying, pending, or terminal status. | `IMP-007` |

## Stop check and planning handoff

The requirement is refined and the preserved invariants, evidence levels, impacts, open risks, and acceptance criteria are recorded. Planning is blocked until the retry-policy decision is supplied and repository evidence is available for the unknown authorization/privacy, policy, operations, compatibility, and regression surfaces. After that decision, recalculate every `IMP-###` and route the resulting report to the implementation-planning workflow; no implementation work breakdown is included here.
