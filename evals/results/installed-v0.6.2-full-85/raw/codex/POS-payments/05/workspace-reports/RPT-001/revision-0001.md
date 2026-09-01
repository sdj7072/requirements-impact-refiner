# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Automatic retry of failed payment.charge attempts | An ambiguous timeout may be retried as a new capture and charge the customer twice. | Customers, payment records, refunds, and reconciliation | The gateway captures funds and then times out before the caller receives the result. | critical | Reuse the same idempotency key for every attempt of one logical charge and require provider-side deduplication or reconciliation before treating an ambiguous timeout as retryable. | blocked |
| `IMP-002` | Automatic retry of every failed payment.charge | Permanent declines may be retried unnecessarily, while unbounded retries can create runaway work and unclear terminal behavior. | Gateway traffic, payment latency, customers, and operational monitoring | A charge returns any error without a defined retry class or attempt budget. | high | Define retryable failure classes, a finite attempt budget and backoff, and an explicit exhausted state. | blocked |
| `IMP-003` | Charge status while automatic retries are in progress | The UI may show failure after a timeout even though capture succeeded, or success before settlement is confirmed. | Customer-visible payment status and downstream user actions | The UI renders between an attempt result and authoritative webhook settlement. | high | Represent retrying and ambiguous outcomes as non-terminal pending states and let settlement determine the final status. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Retry every failed payment.charge automatically, starting in payments/charge.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Automatically retry failed payment.charge operations from payments/charge.py, while preserving one logical charge identity across attempts, preventing duplicate capture when the gateway times out after capture, and keeping pre-webhook UI status non-terminal until settlement is authoritative. The retry eligibility, attempt limit, and treatment of ambiguous post-capture timeouts require an explicit policy choice. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | payment.charge accepts and exposes the caller-supplied idempotency_key. | verified | payments/charge.py defines charge(amount, idempotency_key) and returns the key. |
| `INV-002` | A gateway timeout can occur after capture, so timeout does not prove that the charge failed. | verified | providers/gateway.py sets TIMEOUT_AFTER_CAPTURE = True for payment.charge. |
| `INV-003` | The UI renders status before webhook settlement is available. | verified | ui/status.py sets RENDERS_BEFORE_WEBHOOK_SETTLEMENT = True and references payment.charge. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002` | payments/charge.py defines charge(amount, idempotency_key) and returns the key. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | providers/gateway.py sets TIMEOUT_AFTER_CAPTURE = True for payment.charge. |
| `INV-003` | `REQ-001` | `IMP-003` | ui/status.py sets RENDERS_BEFORE_WEBHOOK_SETTLEMENT = True and references payment.charge. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | critical | blocked | unknown | The charge function accepts an idempotency key, but the repository contains no provider call or deduplication store; the gateway declares timeout-after-capture behavior. | `INV-001`, `INV-002` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | operations | high | blocked | unknown | payments/charge.py has no provider invocation, failure taxonomy, retry limit, backoff, attempt persistence, or terminal-state behavior. | `INV-001`, `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | interfaces | high | blocked | unknown | ui/status.py renders before webhook settlement, and no reconciliation or pending/unknown status implementation exists. | `INV-003`, `INV-002` | the pending decision | `AC-003` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which retry-safety policy should payment.charge use? | Bounded safe retries (recommended): retry transient failures with the same idempotency key; keep post-capture timeouts pending for reconciliation; use a finite attempt limit and backoff. | `IMP-001`, `IMP-002`, `IMP-003` | Safest default, but requires defining the attempt budget/backoff and a reconciliation or settlement path. |
| Which retry-safety policy should payment.charge use? | Retry only confirmed pre-capture transient failures; never automatically retry ambiguous timeouts or permanent declines. | `IMP-001`, `IMP-002`, `IMP-003` | Minimizes duplicate-charge risk but retries fewer failures than requested and may require manual recovery. |
| Which retry-safety policy should payment.charge use? | Retry every error with the same idempotency key, including post-capture timeouts. | `IMP-001`, `IMP-002`, `IMP-003` | Matches the broadest reading of the request, but is unsafe unless provider-side deduplication is guaranteed and still needs a finite stopping rule. |

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
| `REQ-001` | Automatically retry failed payment.charge operations from payments/charge.py, while preserving one logical charge identity across attempts, preventing duplicate capture when the gateway times out after capture, and keeping pre-webhook UI status non-terminal until settlement is authoritative. The retry eligibility, attempt limit, and treatment of ambiguous post-capture timeouts require an explicit policy choice. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Every retry of one logical charge uses the original idempotency_key, and an ambiguous post-capture timeout cannot issue an unprotected second capture. | Automated tests simulate capture followed by timeout and prove at most one provider capture for the logical key. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | Retry eligibility, maximum attempts, backoff, and the exhausted result are explicit and deterministic. | Automated tests cover transient recovery, permanent failure, and retry exhaustion with no unbounded loop. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | Before webhook settlement, retrying and ambiguous charge outcomes render as non-terminal pending/processing rather than success or failure. | UI tests cover the interval before settlement and verify the webhook result becomes authoritative. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The repository does not establish provider-side idempotency or reconciliation for timeout-after-capture. | none | Payments owner |
| `IMP-002` | blocked | No retry eligibility, attempt budget, or backoff policy has been selected. | none | Payments owner |
| `IMP-003` | blocked | No pending/retrying status contract or settlement reconciliation behavior is defined. | none | Payments/UI owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| payments/charge.py | Defines payment.charge and accepts idempotency_key but currently has no provider call or retry behavior. | verified |
| providers/gateway.py | Declares TIMEOUT_AFTER_CAPTURE for payment.charge but has no executable gateway/deduplication implementation. | verified |
| ui/status.py | Declares rendering before webhook settlement for payment.charge but has no status model or reconciliation implementation. | verified |
| Tests and persistence/queue/webhook infrastructure | No such files exist in the repository; their contracts would be required for a production retry implementation. | verified absence in current repository |
| Graph paths for IMP-001 | PATH-001: payment.charge → payment.charge | PATH-001: provider builtin; confidence lexical; location payments/charge.py + providers/gateway.py |
| Graph paths for IMP-002 | PATH-001: payment.charge → payment.charge | PATH-001: provider builtin; confidence lexical; location payments/charge.py + providers/gateway.py |
| Graph paths for IMP-003 | PATH-002: payment.charge → payment.charge | PATH-002: provider builtin; confidence lexical; location payments/charge.py + ui/status.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt bb89232b776f89201122b8f6b1909e6c; sha256 417c1c52a3cb07e4959afe12950702d28bbfc31883f0540a027eb434d275cf53; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Not ready |
