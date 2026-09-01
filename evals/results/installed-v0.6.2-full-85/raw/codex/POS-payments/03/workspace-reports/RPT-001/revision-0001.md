# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Automatic retries for failed payment.charge attempts | A timeout after a successful capture may be retried as a new capture and debit the payer twice. | Payers, merchant balances, charge records, and reconciliation | The provider captures funds and the caller observes TIMEOUT_AFTER_CAPTURE as a failure. | critical | Reuse one request-bound idempotency key backed by durable provider/application deduplication, and reconcile ambiguous outcomes before another capture. | refining |
| `IMP-002` | Retry-driven charge state transitions | The UI may show failed or retrying even though capture succeeded, or show success before settlement. | Customers and support staff relying on payment status | A charge is retried or has an ambiguous outcome before its settlement webhook. | high | Expose an explicit pending/unknown state and allow webhook or reconciliation to make the terminal transition. | refining |
| `IMP-003` | Retry every failed payment.charge automatically | Permanent declines or persistent outages can create an endless retry loop and sustained provider load. | Payment workers, provider quotas, operations, and customers awaiting a final state | A non-retryable failure or repeated transient failure is classified only as failed. | high | Define retryable versus terminal outcomes, bounded attempts with backoff, and a final operational state. | refining |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Retry every failed payment.charge automatically, starting in payments/charge.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Add automatic handling for failed payment.charge attempts beginning in payments/charge.py, with retry eligibility, idempotency, ambiguous post-capture timeouts, visible pre-settlement status, and termination behavior explicitly defined. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | payment.charge accepts an idempotency_key and preserves it in the charge result. | verified | payments/charge.py:1-4 defines payment.charge and returns the supplied idempotency_key as key. |
| `INV-002` | The gateway declares that payment.charge may time out after capture. | verified | providers/gateway.py:1-2 declares TIMEOUT_AFTER_CAPTURE = True for payment.charge; no runtime implementation is present. |
| `INV-003` | The UI declares that payment.charge status renders before webhook settlement. | verified | ui/status.py:1-2 declares RENDERS_BEFORE_WEBHOOK_SETTLEMENT = True for payment.charge; no runtime implementation is present. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003` | payments/charge.py:1-4 defines payment.charge and returns the supplied idempotency_key as key. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002` | providers/gateway.py:1-2 declares TIMEOUT_AFTER_CAPTURE = True for payment.charge; no runtime implementation is present. |
| `INV-003` | `REQ-001` | `IMP-002` | ui/status.py:1-2 declares RENDERS_BEFORE_WEBHOOK_SETTLEMENT = True for payment.charge; no runtime implementation is present. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | critical | refining | unknown | The graph links payments/charge.py to providers/gateway.py lexically/structurally, but provider analysis was unavailable and the repository has no executable gateway or durable deduplication behavior. | `INV-001`, `INV-002` | the pending decision | `AC-001`, `AC-002` |
| `IMP-002` | `REQ-001` | functionality | high | refining | unknown | The graph links payments/charge.py to ui/status.py lexically/structurally, but provider analysis was unavailable and no executable status or settlement model exists. | `INV-003`, `INV-002` | the pending decision | `AC-003` |
| `IMP-003` | `REQ-001` | operations | high | refining | unknown | The graph path to the gateway is limited to lexical/structural inference with an unavailable provider; no failure taxonomy, attempt limit, backoff, scheduler, or terminal-error contract exists. | `INV-001` | the pending decision | `AC-004` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which retry contract should govern failures and ambiguous timeout-after-capture outcomes? | Retry only bounded, definitively transient pre-capture failures with the same request-bound key; mark post-capture timeouts pending and reconcile before any further capture. | `IMP-001`, `IMP-002`, `IMP-003` | Safest against duplicate charges, but not every observed failure immediately produces another capture attempt. |
| Which retry contract should govern failures and ambiguous timeout-after-capture outcomes? | Retry every non-terminal and ambiguous outcome with the same key, after implementing durable idempotency/deduplication and bounded backoff. | `IMP-001`, `IMP-002`, `IMP-003` | Closest safe interpretation of automatic retry, but requires gateway/storage contracts absent from this repository. |
| Which retry contract should govern failures and ambiguous timeout-after-capture outcomes? | Retry every observed failure literally with the current key passthrough only. | `IMP-001`, `IMP-002`, `IMP-003` | Smallest local change, but duplicate captures and unbounded retries cannot be prevented with current evidence. |

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
| `REQ-001` | Add automatic handling for failed payment.charge attempts beginning in payments/charge.py, with retry eligibility, idempotency, ambiguous post-capture timeouts, visible pre-settlement status, and termination behavior explicitly defined. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | All attempts for one immutable charge request use the same validated idempotency key, and concurrent/replayed calls cause at most one provider capture. | Requires new durable deduplication behavior and tests; current code only echoes the key. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-002` | A timeout after capture enters an unknown/pending state and is reconciled by key before any operation capable of creating another capture. | Required because providers/gateway.py declares TIMEOUT_AFTER_CAPTURE. |
| `AC-003` | `REQ-001` | `IMP-002` | `INV-003` | Before webhook settlement, the UI distinguishes pending/unknown/retrying from terminal succeeded or failed, and settlement resolves the visible state consistently. | Required because ui/status.py declares rendering before settlement and has no current state model. |
| `AC-004` | `REQ-001` | `IMP-003` | `INV-001` | Retryable failures have a documented finite attempt limit and backoff; permanent failures terminate without retry and preserve the charge key for diagnosis. | No retry policy or failure taxonomy currently exists. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| payments/charge.py charge orchestration and retry contract | The requested starting point exists but currently returns only operation and key. | verified |
| providers/gateway.py idempotency, capture outcome, and reconciliation behavior | The file declares TIMEOUT_AFTER_CAPTURE but contains no callable gateway or deduplication implementation. | verified current surface; runtime behavior unknown |
| ui/status.py pre-settlement and terminal status rendering | The file declares rendering before webhook settlement but contains no status model. | verified current surface; runtime behavior unknown |
| Tests and runtime infrastructure | The repository contains only the three named Python files and no test/configuration files. | verified |
| Graph paths for IMP-001 | PATH-001: payment.charge → payment.charge | PATH-001: provider builtin; confidence lexical; location payments/charge.py + providers/gateway.py |
| Graph paths for IMP-002 | PATH-002: payment.charge → payment.charge | PATH-002: provider builtin; confidence lexical; location payments/charge.py + ui/status.py |
| Graph paths for IMP-003 | PATH-001: payment.charge → payment.charge | PATH-001: provider builtin; confidence lexical; location payments/charge.py + providers/gateway.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt b5ff9363820f300057d8fa48768b0647; sha256 cda3f8eeafc7f35fff9c48b49a97268da5360a72d76c058dcd4480fd57fdac71; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Not ready |
