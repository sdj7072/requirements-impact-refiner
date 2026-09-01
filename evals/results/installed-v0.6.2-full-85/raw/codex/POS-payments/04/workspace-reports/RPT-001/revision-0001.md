# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Automatic retry of payment.charge failures | A post-capture timeout may be retried as another charge and debit the customer twice. | Customers, payment records, refunds, and reconciliation | The gateway captures successfully, returns a timeout, and automatic retry runs without proven idempotent replay semantics. | critical | Choose a retry policy that reuses one stable idempotency key for the same logical charge and treats post-capture timeouts as pending until replay/query/webhook reconciliation is safe. | blocked |
| `IMP-002` | Automatic retry and its visible payment status | The UI may show failure, retry, or success as final while the original attempt has already captured and settlement remains unresolved. | Customers and support staff reading payment status | Status is rendered after an attempt-level error but before webhook settlement or reconciliation. | high | Represent ambiguous/retrying charges as pending and transition to a final state only from authoritative settlement or a proven terminal outcome. | blocked |
| `IMP-003` | Retry every failed payment.charge automatically | Permanent failures or prolonged outages may cause retry storms, repeated provider calls, and charges that never reach a terminal operational state. | Gateway capacity, workers, observability, and customer support | A terminal or persistent error is classified as retryable without an attempt cap and backoff. | high | Define retryable versus terminal errors, a finite attempt limit, backoff, and an exhausted state with observable reason. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Retry every failed payment.charge automatically, starting in payments/charge.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Add automatic retry handling for payment.charge beginning in payments/charge.py, while defining which failure classes are retryable, preserving one logical charge's idempotency identity across retries, and keeping user-visible status non-final until gateway/webhook settlement resolves ambiguous outcomes. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | payment.charge accepts an idempotency_key and exposes that key on the charge request/result. | verified | payments/charge.py defines charge(amount, idempotency_key) and returns the payment.charge operation with the supplied key. |
| `INV-002` | A gateway timeout can occur after funds have already been captured, so a timeout is not evidence that no charge occurred. | verified | providers/gateway.py sets TIMEOUT_AFTER_CAPTURE = True for payment.charge. |
| `INV-003` | The UI renders charge status before webhook settlement, so the initially rendered state is not authoritative settlement evidence. | verified | ui/status.py sets RENDERS_BEFORE_WEBHOOK_SETTLEMENT = True for payment.charge. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | payments/charge.py defines charge(amount, idempotency_key) and returns the payment.charge operation with the supplied key. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | providers/gateway.py sets TIMEOUT_AFTER_CAPTURE = True for payment.charge. |
| `INV-003` | `REQ-001` | `IMP-002` | ui/status.py sets RENDERS_BEFORE_WEBHOOK_SETTLEMENT = True for payment.charge. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | critical | blocked | unknown | The charge path accepts an idempotency key and the linked gateway path permits timeout after capture. Retrying an ambiguous timeout as a new logical attempt may capture funds twice; provider deduplication behavior is not present in the repository. | `INV-001`, `INV-002` | the pending decision | `AC-001`, `AC-002` |
| `IMP-002` | `REQ-001` | functionality | high | blocked | unknown | The linked UI path renders before webhook settlement. Automatic retries add intermediate states whose authoritative settlement behavior is not defined in the repository. | `INV-003`, `INV-002` | the pending decision | `AC-003` |
| `IMP-003` | `REQ-001` | operations | high | blocked | unknown | No retry limit, backoff, retryable-error taxonomy, or terminal failure contract is present in the inspected repository files. | `INV-002` | the pending decision | `AC-004` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| How should automatic retries handle failures that may occur after capture? | Retry only with the same idempotency key; keep ambiguous post-capture timeouts pending until safe replay or settlement reconciliation. | `IMP-001`, `IMP-002`, `IMP-003` | Safest default and supports automatic recovery, but requires stable retry state, bounded policy, and pending/reconciliation behavior. |
| How should automatic retries handle failures that may occur after capture? | Retry only failures proven to occur before capture; do not automatically retry ambiguous post-capture timeouts. | `IMP-001`, `IMP-002`, `IMP-003` | Minimizes duplicate-charge risk and implementation scope, but some recoverable ambiguous failures require webhook settlement or manual recovery. |
| How should automatic retries handle failures that may occur after capture? | Retry every reported failure immediately, including post-capture timeouts. | `IMP-001`, `IMP-002`, `IMP-003` | Maximizes retry coverage but is unsafe unless the gateway's idempotent replay and settlement contracts are proven; those contracts are absent here. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | none |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | `IMP-001`, `IMP-002`, `IMP-003` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Add automatic retry handling for payment.charge beginning in payments/charge.py, while defining which failure classes are retryable, preserving one logical charge's idempotency identity across retries, and keeping user-visible status non-final until gateway/webhook settlement resolves ambiguous outcomes. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | All automatic attempts for one logical payment.charge use exactly the original idempotency_key; the retry layer never generates a new key for an ambiguous result. | Test with a simulated TIMEOUT_AFTER_CAPTURE and assert every provider invocation for the logical charge receives the same key. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-002` | A timeout that can follow capture is never treated as proof of failure and does not create a second logical charge. | Test the post-capture timeout path and verify it enters pending/reconciliation or a documented idempotent replay path without duplicate capture. |
| `AC-003` | `REQ-001` | `IMP-002` | `INV-003` | While retry or post-capture outcome is unresolved, ui/status.py renders a non-final pending state and only authoritative settlement or a proven terminal outcome produces final status. | UI/state tests cover initial error, retry scheduled, retry exhausted with ambiguous settlement, webhook success, and webhook terminal failure. |
| `AC-004` | `REQ-001` | `IMP-003` | `INV-002` | Automatic retries use a documented retryable-error taxonomy, finite maximum attempts, backoff, and an observable exhausted state. | Unit tests verify terminal errors are not retried, retryable errors stop at the limit, backoff is applied, and exhaustion is recorded. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The phrase 'every failed' does not resolve whether an ambiguous post-capture timeout is a retryable failed attempt or an unsettled charge, and provider replay guarantees are absent. | none | Product/payment owner |
| `IMP-002` | blocked | The repository has no defined intermediate status contract for retries and webhook settlement. | none | Payment/UI owner |
| `IMP-003` | blocked | Retry count, backoff, and terminal/retryable failure classes are unspecified. | none | Payment platform owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| payments/charge.py automatic retry entry point and stable idempotency identity | Direct inspection of payments/charge.py. | verified |
| providers/gateway.py post-capture timeout semantics | Direct inspection of providers/gateway.py and promoted graph PATH-001. | verified source; graph relationship confidence limited by scan provider availability |
| ui/status.py pre-webhook status rendering | Direct inspection of ui/status.py and promoted graph PATH-002. | verified source; graph relationship confidence limited by scan provider availability |
| Provider-side idempotency retention, replay response, retryable error taxonomy, persistence, workers, and webhook handler | No implementation or contract for these areas exists in the inspected repository. | unknown |
| Graph paths for IMP-001 | PATH-001: payment.charge → payment.charge | PATH-001: provider builtin; confidence lexical; location payments/charge.py + providers/gateway.py |
| Graph paths for IMP-002 | PATH-002: payment.charge → payment.charge | PATH-002: provider builtin; confidence lexical; location payments/charge.py + ui/status.py |
| Graph paths for IMP-003 | PATH-001: payment.charge → payment.charge | PATH-001: provider builtin; confidence lexical; location payments/charge.py + providers/gateway.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt d93a705b1a32693dbde9915f8b6e9c93; sha256 f56a635a85108350ec71c7eadf48b533c9f7bfd44b6cbf1f3cdcc9fe11395b60; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Not ready |
