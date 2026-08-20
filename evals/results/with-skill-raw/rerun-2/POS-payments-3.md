# Requirements impact refinement — POS payments

## Requirement revision

**REQ-001 — Automatic retry of failed charges**

The payment system shall automatically retry a charge that is classified as
failed, while preserving at-most-once capture for a logical charge and
converging the user-visible payment status with the provider's eventual
settlement result. The exact retry scope, retry limit/backoff, and terminal
classification remain **Decision needed**; a provider timeout after capture
must not be treated as proof that no capture occurred.

This revision narrows “every failed charge” into a requirement that distinguishes
a confirmed failure from an unknown outcome and makes duplicate capture
prevention and eventual status convergence explicit. It does not authorize
retrying an outcome that is merely unknown until its provider state is resolved.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`. | verified | Supplied repository fact: “charge requests accept an idempotency_key” | `must-preserve` by `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement. | verified | Supplied repository fact: “payment status is rendered before webhook settlement” | `must-preserve` by `REQ-001` |
| `INV-003` | The provider may time out after capture, so a timeout can represent an unknown final payment outcome. | verified | Supplied repository fact: “the provider may time out after capture” | `must-preserve` by `REQ-001` |

## Impact ledger

| ID | Impact | Category | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | A retry after a provider timeout can create a duplicate capture unless retries reuse the same logical idempotency key and first reconcile the provider outcome. | State/concurrency, regression | verified | `INV-001`, `INV-003` | refining | affects `REQ-001`, `INV-001`, `INV-003`; produces `AC-001` |
| `IMP-002` | Automatic retries need a defined classification separating confirmed failures from unknown outcomes; otherwise the system may retry an already-captured charge. | Functionality, state/concurrency | inferred | `INV-003`; no supplied failure taxonomy or provider-reconciliation contract | detected | affects `REQ-001`, `INV-003`; produces `AC-002` |
| `IMP-003` | The pre-webhook status view can show a transient failure or pending state while an automatic retry or eventual webhook is still in flight, creating stale or contradictory user feedback. | Functionality, interfaces, regression | verified | `INV-002`; `REQ-001` | refining | affects `REQ-001`, `INV-002`; produces `AC-003` |
| `IMP-004` | Retry count, backoff, retry ownership, and terminal failure behavior are unspecified, so “every” could cause unbounded attempts or repeated customer-visible processing. | Operations, functionality | unknown | No supplied retry policy, queue/job contract, or operational limits | blocked | affects `REQ-001`; produces `AC-004` |
| `IMP-005` | Charge and webhook contracts may need an attempt identifier or stable logical-charge correlation so repeated attempts and late settlement events can be reconciled safely. | Interfaces, data, compatibility | unknown | `INV-001` establishes an idempotency field, but no event schema or consumer contract was supplied | blocked | affects `REQ-001`, `INV-001`, `INV-002`; produces `AC-005` |
| `IMP-006` | Automatic retries can change customer messaging, support/audit records, and monitoring volume; the system's existing notification, audit, and alert behavior is not supplied. | Operations, regression | unknown | No notification, audit, metrics, or alert artifacts supplied | blocked | affects `REQ-001`; produces `AC-006` |

## One focused decision

**Decision needed:** What retry policy should govern a charge after the system
classifies it as failed or cannot immediately determine the provider outcome?

1. **Bounded automatic retry after reconciliation (recommended):** retry only
   confirmed-retryable failures; reconcile unknown outcomes first; use the same
   logical idempotency key; apply a finite attempt limit and backoff; stop with a
   terminal status when the limit is reached.
2. **Bounded retry for all non-success outcomes:** retry confirmed failures and
   unknown outcomes after a provider-status check, with a finite limit and
   backoff. This may increase latency and provider traffic.
3. **Unbounded retry until success:** keep retrying in the background. This
   maximizes eventual success but leaves duplicate-charge, cost, and operational
   runaway risk unless additional safeguards are specified.

No stakeholder selection was supplied in this request, so no `DEC-###` is
created and no impact is marked `accepted`.

## Recorded decision

**Pending.** The retry policy option, finite limits/backoff, and treatment of
unknown provider outcomes must be selected before implementation planning can
close the blocked impacts. The requirement remains `REQ-001` with the
reconciliation and boundedness constraints stated above.

## Whole-set recalculation

Because no decision was recorded, the complete impact set remains as follows.
No impact is resolved or accepted by silence; the known impacts are retained
with their evidence levels and current states.

### Delta

- **resolved:** none
- **mitigated:** none
- **unchanged:** `IMP-001`, `IMP-002`, `IMP-003`
- **accepted:** none
- **deferred:** none
- **blocked:** `IMP-004`, `IMP-005`, `IMP-006`
- **new:** none

## Acceptance and regression criteria

| ID | Criterion | Evidence level | Produced by / verifies |
| --- | --- | --- | --- |
| `AC-001` | A provider timeout that may have occurred after capture does not cause a second capture for the same logical charge; retries reuse the logical idempotency identity or otherwise prove the first outcome is unresolved before retrying. | verified baseline, implementation validation required | `IMP-001`; verifies `INV-001`, `INV-003` |
| `AC-002` | Confirmed non-retryable failures are terminal, confirmed retryable failures follow the selected bounded policy, and unknown outcomes are reconciled before any new capture attempt. | validation gap | `IMP-002` |
| `AC-003` | The rendered payment status transitions deterministically from the pre-webhook state through retry and late webhook settlement, without exposing a final failure before a still-valid retry or settlement can update it. | validation gap | `IMP-003`; verifies `INV-002` |
| `AC-004` | The selected policy specifies finite retry limits, backoff, ownership, cancellation, and terminal status; repeated failures do not create unbounded jobs or requests. | blocked pending policy selection | `IMP-004` |
| `AC-005` | Charge attempts and late webhook events can be correlated to one logical charge, and duplicate or out-of-order events converge to one final payment state without breaking existing consumers. | blocked pending contract inspection | `IMP-005` |
| `AC-006` | Retry attempts, reconciliations, terminal failures, and duplicate-prevention outcomes are observable with safe customer/support messaging and actionable alerts. | blocked pending operational evidence | `IMP-006` |

## Stop check and planning handoff

The refined requirement is ready for the selected planning workflow, but the
handoff must retain the pending retry-policy decision and the three named
information gaps. The material impacts are not all resolved: `IMP-001` through
`IMP-003` are still refining, while `IMP-004` through `IMP-006` are blocked by
missing policy, contract, and operational evidence. Planning should begin only
after the stakeholder selects one retry option and the missing provider/event,
job, notification, audit, and monitoring contracts are inspected. This is a
report-only handoff; it is not an implementation work breakdown.
