# Requirements Impact Refinement — POS payments

## Requirement revision

**REQ-001 — Automatic retry of failed charges**

Retry every failed charge automatically. A retry MUST preserve the original
charge identity by supplying an idempotency key to each charge request, MUST
not create a second capture when the provider captured the charge but the
request timed out, and MUST keep the customer-visible payment state accurate
while webhook settlement is pending. The retry/termination policy, attempt
limits, and handling of non-retryable failures remain the pending decision.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| INV-001 | Charge requests accept `idempotency_key`. | verified | Supplied fact: “charge requests accept idempotency_key” | must-preserve REQ-001 |
| INV-002 | Payment status is rendered before webhook settlement. | verified | Supplied fact: “payment status rendered before webhook settlement” | must-preserve REQ-001 |
| INV-003 | A provider may time out after capture, so request timeout does not prove that no charge occurred. | verified | Supplied fact: “provider may time out after capture” | must-preserve REQ-001 |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| IMP-001 | Retrying without reusing a stable idempotency key can capture the same customer charge more than once. | verified | `INV-001`; supplied charge-request contract | refining | affects REQ-001, INV-001; produces AC-001 |
| IMP-002 | A timeout after provider capture can cause a retry to duplicate a settled charge if timeout is treated as an ordinary failed charge. | verified | `INV-003` | refining | affects REQ-001, INV-003; produces AC-002 |
| IMP-003 | Because status is rendered before webhook settlement, automatic retry or an eventual webhook can produce an intermediate status that differs from the final provider result. | verified | `INV-002`, `INV-003` | detected | affects REQ-001, INV-002; produces AC-003 |
| IMP-004 | The supplied facts do not define which failures are retryable, the maximum attempts, backoff, or the stopping condition. | unknown | No retry classification or policy supplied | blocked | affects REQ-001; produces AC-004 |
| IMP-005 | The supplied facts do not identify the authoritative reconciliation behavior when a charge request times out after capture and no webhook has yet settled the payment. | unknown | No reconciliation contract, webhook correlation rule, or timeout recovery behavior supplied | blocked | affects REQ-001, INV-003; produces AC-005 |

## Focused decision

Automatic retry requires a policy for retry classification and boundedness.
Which policy should refine REQ-001?

1. Retry only explicitly transient/provider-transport failures, with a bounded
   attempt count and backoff; never retry definitive declines or validation
   failures.
2. Retry every failure, with a bounded attempt count and backoff; rely on the
   idempotency key and webhook reconciliation for safety.
3. Retry transient failures automatically, but leave attempt count, backoff,
   and timeout reconciliation to a later decision.

**Decision needed:** No user/stakeholder selection is recorded. The pending
decision is required before a concrete `DEC-###` can be created. In particular,
the supplied facts do not select an attempt limit, backoff schedule, or the
authoritative source of truth during timeout reconciliation.

## Recorded decision

None recorded. No `DEC-###` is allocated or linked.

## Whole-set recalculation

No decision was recorded, so the requirement is not policy-complete. All known
impacts are retained and re-evaluated below.

### Delta

- **resolved:** none
- **mitigated:** none
- **unchanged:** IMP-001, IMP-002, IMP-003
- **accepted:** none
- **deferred:** none
- **blocked:** IMP-004, IMP-005
- **new:** none

## Stop check and planning handoff

The refined requirement, preserved invariants, linked impacts, and acceptance
criteria are ready for planning once the pending decision and timeout
reconciliation contract are supplied. IMP-004 and IMP-005 remain blocked by
named information gaps; silence is not acceptance.

## Acceptance and regression criteria

| ID | Criterion | Level | Verifies |
| --- | --- | --- | --- |
| AC-001 | Every retry for one logical charge uses the same stable idempotency key, and a provider honors it without producing a second capture. | verified | IMP-001, INV-001 |
| AC-002 | If the provider captures and the request times out, retry processing does not create a duplicate capture; the logical payment is reconciled to the provider result. | verified | IMP-002, INV-003 |
| AC-003 | While webhook settlement is pending, the rendered status is an explicit intermediate state and transitions deterministically to the provider-settled result; retries cannot overwrite a later settled result incorrectly. | verified | IMP-003, INV-002 |
| AC-004 | The selected retry policy defines retryable and non-retryable errors, an attempt limit, backoff, and a terminal state; each is testable for automatic retries. | unknown | IMP-004 |
| AC-005 | Timeout recovery defines how the payment is correlated and reconciled when capture may have occurred before webhook settlement, including the no-webhook case. | unknown | IMP-005 |
