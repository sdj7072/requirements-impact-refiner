# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Automatic retry of payment.charge failures | An attempt that captured funds but timed out can be submitted again and charge the customer twice. | Customers, payment records, refunds, and provider reconciliation | A transport timeout or exception occurs after the gateway captured the payment. | critical | Reuse the exact idempotency key and treat post-capture timeout as pending reconciliation; retry only under a selected provider-safe policy. | refining |
| `IMP-002` | Retry every failed payment.charge automatically | Permanent declines, invalid requests, authentication failures, or unbounded repeated failures may be retried even though they cannot succeed. | Gateway load, customer experience, rate limits, and operational stability | Any result is classified generically as failed. | high | Select and encode a retry policy that distinguishes retryable pre-capture failures, ambiguous outcomes, and terminal failures, with bounded attempts and backoff. | blocked |
| `IMP-003` | Automatic background charge retry and reconciliation | The UI can show failed while capture already succeeded, or show a retry result that is later contradicted by settlement. | Payment status UI and any consumer acting on displayed status | Status is rendered after a request error but before the settlement webhook. | high | Represent retrying or unknown outcomes as non-final and make authoritative settlement idempotently supersede provisional status. | refining |
| `IMP-004` | Operational automatic retries | A local loop in payments/charge.py would not establish durable retries, provider idempotency, crash recovery, or settlement coordination. | Charge execution, monitoring, restart behavior, and incident response | The process exits, the provider contract differs from assumptions, or settlement arrives while a retry is scheduled. | high | Define the gateway result/error interface and observable retry lifecycle, then add deterministic tests for retries, reconciliation, and status ordering. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Retry every failed payment.charge automatically, starting in payments/charge.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Add automatic retry behavior for payment.charge beginning in payments/charge.py, but define retry eligibility and ambiguous-outcome handling so one logical charge retains the caller's idempotency key, post-capture timeouts cannot create duplicate captures, terminal declines are not retried indefinitely, and UI status remains non-final until webhook settlement or reconciliation. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | All attempts for one logical payment.charge use the same caller-supplied idempotency key end to end. | verified | payments/charge.py:3-4 accepts idempotency_key and exposes it in the operation result. |
| `INV-002` | A timeout can occur after capture, so timeout is an unknown outcome rather than proof that the charge failed. | verified | providers/gateway.py:1 sets TIMEOUT_AFTER_CAPTURE = True. |
| `INV-003` | Rendered payment status may precede authoritative webhook settlement and therefore must not convert an unknown outcome into a final failure. | verified | ui/status.py:1 sets RENDERS_BEFORE_WEBHOOK_SETTLEMENT = True. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-004` | payments/charge.py:3-4 accepts idempotency_key and exposes it in the operation result. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | providers/gateway.py:1 sets TIMEOUT_AFTER_CAPTURE = True. |
| `INV-003` | `REQ-001` | `IMP-003`, `IMP-004` | ui/status.py:1 sets RENDERS_BEFORE_WEBHOOK_SETTLEMENT = True. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | critical | refining | unknown | The receipt contains a lexical/structural-inferred path from payments/charge.py to providers/gateway.py, but its provider frontier prevents proving executable forwarding or reconciliation. Direct inspection separately confirms the idempotency input and timeout-after-capture flags. | `INV-001`, `INV-002` | the pending decision | `AC-001`, `AC-002` |
| `IMP-002` | `REQ-001` | functionality | high | blocked | unknown | The receipt contains a lexical/structural-inferred charge-to-gateway path with an unavailable-provider frontier. Local files show no failure taxonomy, retry bound, or backoff, but external runtime behavior is not covered. | `INV-002` | the pending decision | `AC-003`, `AC-004` |
| `IMP-003` | `REQ-001` | interfaces | high | refining | unknown | The receipt contains a lexical/structural-inferred path from payment.charge to ui/status.py with an unavailable-provider frontier. Direct inspection confirms pre-settlement rendering, but no executable status transition graph is covered. | `INV-003`, `INV-002` | the pending decision | `AC-005`, `AC-006` |
| `IMP-004` | `REQ-001` | operations | high | blocked | unknown | Repository inspection found only three minimal source files and no executable gateway adapter, webhook handler, persistence, queue, callers, tests, or documented provider idempotency contract; the scan receipt cannot prove whether those contracts exist outside this repository. | `INV-001`, `INV-002`, `INV-003` | the pending decision | `AC-007`, `AC-008` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| What should count as an automatically retryable payment.charge failure, especially when the gateway times out after capture? | Reconcile first, then retry only retryable failures (recommended) | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | Safest: keep the same idempotency key, mark post-capture timeouts pending, reconcile by provider result/webhook, retry only confirmed-not-captured transient failures with bounded attempts and backoff; requires a reconciliation/status contract. |
| What should count as an automatically retryable payment.charge failure, especially when the gateway times out after capture? | Immediately retry transient errors with the same idempotency key | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | Faster recovery and simpler flow, but safety depends on an explicit provider guarantee that the idempotency key is honored across timeout-after-capture retries; that guarantee is not present in the repository. |
| What should count as an automatically retryable payment.charge failure, especially when the gateway times out after capture? | Literally retry every non-success result | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | Matches the broad wording, but can retry declines and ambiguous captures, cause retry storms, and risk duplicate charges; unsuitable without additional hard safety constraints. |

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
| new | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Add automatic retry behavior for payment.charge beginning in payments/charge.py, but define retry eligibility and ambiguous-outcome handling so one logical charge retains the caller's idempotency key, post-capture timeouts cannot create duplicate captures, terminal declines are not retried indefinitely, and UI status remains non-final until webhook settlement or reconciliation. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Every attempt and reconciliation lookup for one logical charge forwards the exact same non-empty idempotency key; tests prove a retry never substitutes or regenerates it. | Required by payments/charge.py's existing idempotency_key boundary and the timeout-after-capture risk. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-002` | A timeout after possible capture never directly schedules a new capture unless the selected provider-safe policy establishes that the original attempt was not captured. | providers/gateway.py declares TIMEOUT_AFTER_CAPTURE = True. |
| `AC-003` | `REQ-001` | `IMP-002` | `INV-002` | Tests distinguish retryable transient pre-capture failures, ambiguous outcomes, and terminal failures such as declines or validation errors. | No failure taxonomy currently exists, and timeout is explicitly ambiguous. |
| `AC-004` | `REQ-001` | `IMP-002` | `INV-001` | Automatic retries have a finite attempt limit and deterministic backoff behavior, and exhaustion produces an observable non-success outcome without an infinite loop. | The request supplies no attempt or backoff bound and the current function has no retry logic. |
| `AC-005` | `REQ-001` | `IMP-003` | `INV-003` | Before authoritative settlement, retrying or ambiguous charges render a non-final pending/reconciling state rather than failed. | ui/status.py declares that rendering occurs before webhook settlement. |
| `AC-006` | `REQ-001` | `IMP-003` | `INV-003` | Duplicate or out-of-order retry and webhook events converge idempotently on the authoritative settled state. | Settlement can arrive after UI rendering and potentially during retries. |
| `AC-007` | `REQ-001` | `IMP-004` | `INV-002` | Each attempt, retry decision, reconciliation result, and exhaustion is observable with the logical idempotency key while excluding sensitive payment data. | No retry worker, persistence, or telemetry contract exists in the repository. |
| `AC-008` | `REQ-001` | `IMP-004` | `INV-001` | A gateway interface used by payments/charge.py explicitly accepts the idempotency key and returns or raises outcomes sufficient to classify retryable, terminal, captured, and unknown states. | providers/gateway.py currently contains constants only, so executable provider semantics are absent. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-002` | blocked | The request does not select which failures are retryable or how timeout-after-capture is handled. | none | Product/payment engineering |
| `IMP-004` | blocked | Implementation requires a gateway outcome contract and retry lifecycle not present in the current repository. | none | Payment engineering |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| payments/charge.py automatic charge execution and retry orchestration | The requested starting point exists, but currently only returns operation metadata and the idempotency key. | high |
| providers/gateway.py gateway failure and idempotency behavior | The file explicitly marks timeout-after-capture but provides no callable provider interface. | high for the risk; low for the intended API |
| ui/status.py provisional status before webhook settlement | The file explicitly marks pre-settlement rendering and links to payment.charge. | high for ordering; low for the intended status API |
| Webhook, persistence, background jobs, callers, and tests | No such files are present in the inspected repository. | high that they are absent locally; unknown outside the repository |
| Graph paths for IMP-001 | PATH-001: payment.charge → payment.charge | PATH-001: provider builtin; confidence lexical; location payments/charge.py + providers/gateway.py |
| Graph paths for IMP-002 | PATH-001: payment.charge → payment.charge | PATH-001: provider builtin; confidence lexical; location payments/charge.py + providers/gateway.py |
| Graph paths for IMP-003 | PATH-002: payment.charge → payment.charge | PATH-002: provider builtin; confidence lexical; location payments/charge.py + ui/status.py |
| Graph paths for IMP-004 | This is a supplied-and-inspected absence with no receipt-local path establishing external runtime contracts, so confidence remains unknown beyond the repository boundary. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt ed237cb2b7374f530c656b752332fb54; sha256 f114f6811999de99a759d91358834a25599d9395b41e54f65c648cd344341bce; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | `IMP-002`, `IMP-004` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005`, `AC-006`, `AC-007`, `AC-008` | Not ready |
