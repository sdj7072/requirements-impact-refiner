# Requirements Impact Refinement — POS-payments-4

## Requirement revision

**REQ-001 — Retry every failed charge automatically.**

Refined working requirement: a failed charge attempt should be retried automatically, while preserving one logical payment’s idempotency identity and preventing a retry from creating a second capture when the provider timed out after capture. The retry trigger, retry budget/backoff, treatment of an indeterminate provider result, and user-visible status transition remain pending decisions.

Evidence scope is limited to the three supplied facts; no repository or provider-specific implementation evidence was supplied.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence | State | Links |
| --- | --- | --- | --- | --- |
| **INV-001** | Charge requests accept an `idempotency_key`. | Supplied fact: “charge requests accept an idempotency_key” | detected | must-preserve REQ-001 |
| **INV-002** | Payment status is rendered before webhook settlement. | Supplied fact: “payment status is rendered before webhook settlement” | detected | must-preserve REQ-001 |
| **INV-003** | The provider may time out after capture, leaving the client without a definitive result even though funds may already have been captured. | Supplied fact: “provider may time out after capture” | detected | must-preserve REQ-001 |

## Impact ledger

| ID | Impact | Category | Evidence level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| **IMP-001** | Retrying with a new idempotency key could create a duplicate capture when the original request timed out after capture. | State/concurrency, regression | verified | Supplied facts for `idempotency_key` and post-capture timeout | refining | affects REQ-001, INV-001, INV-003; produces AC-001 |
| **IMP-002** | “Failed” is ambiguous: a rendered pre-webhook status may be provisional, while a provider timeout after capture is indeterminate rather than evidence that no charge occurred. | State/concurrency, interfaces | verified | Supplied facts for pre-settlement rendering and post-capture timeout | refining | affects REQ-001, INV-002, INV-003; produces AC-002 |
| **IMP-003** | The retry trigger, maximum attempts, backoff, and retryable error classification are unspecified, so “every failed” could cause unbounded or unsafe retries. | Operations, state/concurrency | unknown | No retry policy, provider error taxonomy, or operational limits supplied | blocked | affects REQ-001; produces AC-003 |
| **IMP-004** | The user-visible status during automatic retry and until webhook settlement is unspecified; clients may display a terminal failure before the eventual settlement result. | Interfaces, regression | verified | Supplied fact that status renders before webhook settlement; no transition contract supplied | detected | affects REQ-001, INV-002; produces AC-004 |
| **IMP-005** | Webhook ordering, deduplication, and reconciliation behavior are unspecified, so a late settlement could conflict with a retry result. | Interfaces, state/concurrency | unknown | No webhook contract or ordering/reconciliation evidence supplied | blocked | affects REQ-001, INV-002, INV-003; produces AC-005 |

## One focused decision

What should the system do when a charge attempt is failed or indeterminate?

1. **Conservative bounded retry (recommended):** retry only explicitly retryable failures, use the same logical payment’s idempotency key, cap attempts with backoff, and reconcile an indeterminate/post-capture timeout through provider status or webhook before attempting another capture.
2. **Immediate bounded retry:** retry any client-observed failure up to a fixed limit using the same idempotency key; treat webhook settlement as authoritative afterward.
3. **Retry all failures:** retry every client-observed failure, including indeterminate outcomes, with a configured cap; duplicate-capture risk is accepted for operational simplicity.

No concrete `DEC-###` is recorded because no stakeholder selection was supplied. Until selected, impacts remain pending rather than accepted or resolved.

## Recorded decision

**Pending decision:** choose one retry and indeterminate-outcome policy above. No `DEC-###` exists yet.

## Whole-set recalculation

No decision was made, so all known impacts were re-evaluated and remain in their current state. The refined requirement narrows the safety boundary but does not resolve policy or webhook-contract gaps.

### Delta

- **resolved:** none
- **mitigated:** none
- **unchanged:** IMP-001, IMP-002, IMP-004
- **accepted:** none
- **deferred:** none
- **blocked:** IMP-003, IMP-005
- **new:** none

## Acceptance and regression criteria

| ID | Criterion | Evidence / status | Produced by |
| --- | --- | --- | --- |
| **AC-001** | A retry for one logical payment reuses the prescribed idempotency identity and cannot create a second capture solely because the first provider response timed out after capture. | Required criterion; implementation/provider verification unavailable | IMP-001 |
| **AC-002** | A provider timeout after capture is represented as indeterminate/pending until reconciliation or webhook settlement, not as proof that a new capture is safe. | Required criterion; current status contract unavailable | IMP-002 |
| **AC-003** | Automatic retries have an explicit retryable-error classification, finite attempt limit, and backoff; non-retryable failures stop without further charge attempts. | Blocked pending retry policy decision and provider error taxonomy | IMP-003 |
| **AC-004** | The pre-webhook UI does not expose a terminal payment failure that contradicts a later settlement; retrying status is distinguishable from settled failure. | Required criterion; UI contract unavailable | IMP-004 |
| **AC-005** | Duplicate/out-of-order webhooks and late settlement after a retry converge to one authoritative payment state without duplicate capture. | Blocked pending webhook contract and reconciliation evidence | IMP-005 |

## Stop check and planning handoff

This is a report-only handoff. The requirement is refined, preserved invariants and evidence-linked impacts are recorded, and open risks are explicit. Planning should resume only after the pending retry-policy decision and the missing provider/webhook contracts are supplied. No implementation work breakdown is created here.
