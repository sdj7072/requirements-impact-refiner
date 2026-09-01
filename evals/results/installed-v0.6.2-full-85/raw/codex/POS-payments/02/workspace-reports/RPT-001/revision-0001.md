# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Automatic retries for failed payment.charge attempts | A timeout after capture can be retried as a second charge. | Customers, ledger reconciliation, and provider-side captures | The provider captures funds and the response times out. | critical | Reuse the exact idempotency key for every attempt and treat the timeout as an ambiguous pending outcome until settlement. | mitigated |
| `IMP-002` | Automatic retries for failed payment.charge attempts | The UI can display failed or settled while retries or webhook settlement are still outstanding. | Customers and support staff reading charge status | A charge attempt fails before webhook settlement. | high | Render pending before webhook settlement and reserve terminal statuses for the webhook outcome. | mitigated |
| `IMP-003` | Automatic retries for failed payment.charge attempts | Persistent failures can cause an unbounded retry storm. | Gateway capacity, application workers, and provider rate limits | The gateway remains unavailable or repeatedly returns failure. | high | Use a bounded total-attempt policy and make retry timing injectable/testable. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Retry every failed payment.charge automatically, starting in payments/charge.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Automatically retry every failed payment.charge attempt through a bounded retry policy. Every attempt for one logical charge must reuse the caller-supplied idempotency_key, including an ambiguous TIMEOUT_AFTER_CAPTURE outcome. Before webhook settlement, the UI must expose the charge as pending rather than failed or settled; only webhook settlement may make the displayed status terminal. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | All attempts for one logical payment.charge preserve the exact caller-supplied idempotency key. | verified | payments/charge.py accepts idempotency_key and returns it as the charge key. |
| `INV-002` | A provider timeout can occur after capture, so transport failure does not prove that no charge occurred. | verified | providers/gateway.py sets TIMEOUT_AFTER_CAPTURE = True for payment.charge. |
| `INV-003` | Displayed terminal status is not authoritative until webhook settlement. | verified | ui/status.py declares RENDERS_BEFORE_WEBHOOK_SETTLEMENT = True for payment.charge. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003` | payments/charge.py accepts idempotency_key and returns it as the charge key. |
| `INV-002` | `REQ-001` | `IMP-001` | providers/gateway.py sets TIMEOUT_AFTER_CAPTURE = True for payment.charge. |
| `INV-003` | `REQ-001` | `IMP-002` | ui/status.py declares RENDERS_BEFORE_WEBHOOK_SETTLEMENT = True for payment.charge. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | critical | mitigated | unknown | The fallback graph connects payments/charge.py to providers/gateway.py; together with the verified timeout-after-capture invariant, retrying with a new key could create a second capture. | `INV-001`, `INV-002` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | functionality | high | mitigated | unknown | The fallback graph connects payments/charge.py to ui/status.py; the verified pre-webhook rendering invariant means an attempt-level failure can be displayed before the authoritative outcome. | `INV-003` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | operations | high | mitigated | unknown | Retrying every failed attempt without an attempt bound or delay can loop indefinitely during a provider outage; no repository retry implementation exists yet. | `INV-001` | `DEC-001` | `AC-003` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Retry every failed charge under one bounded logical operation, preserving the same idempotency key and pending UI state until webhook settlement. | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | The user explicitly requested automatic retries for every failed payment.charge and supplied idempotency, timeout-after-capture, and pre-webhook UI evidence that defines the safety boundary. |

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
| `REQ-001` | Automatically retry every failed payment.charge attempt through a bounded retry policy. Every attempt for one logical charge must reuse the caller-supplied idempotency_key, including an ambiguous TIMEOUT_AFTER_CAPTURE outcome. Before webhook settlement, the UI must expose the charge as pending rather than failed or settled; only webhook settlement may make the displayed status terminal. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Given a charge whose first attempt fails, each subsequent gateway attempt receives the exact same amount and idempotency_key, including after TIMEOUT_AFTER_CAPTURE. | Directly tests the requested retry behavior and duplicate-capture mitigation. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | Before webhook settlement, status rendering returns pending even when an individual gateway attempt has failed; a webhook settlement may render the terminal status. | Directly tests the current render-before-settlement boundary. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-001` | A persistently failing gateway stops after the configured maximum total attempts and reports an exhausted, still-unsettled charge without changing its idempotency key. | Directly tests operational boundedness and safe failure semantics. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| payments/charge.py charge execution and retry orchestration | The requested starting point and current idempotency_key boundary are in payments/charge.py. | high |
| providers/gateway.py ambiguous timeout-after-capture semantics | The provider declares TIMEOUT_AFTER_CAPTURE for payment.charge. | high |
| ui/status.py pre-webhook status rendering | The UI declares that it renders before webhook settlement. | high |
| Graph paths for IMP-001 | PATH-001: payment.charge → payment.charge | PATH-001: provider builtin; confidence lexical; location payments/charge.py + providers/gateway.py |
| Graph paths for IMP-002 | PATH-002: payment.charge → payment.charge | PATH-002: provider builtin; confidence lexical; location payments/charge.py + ui/status.py |
| Graph paths for IMP-003 | Operational retry behavior is not represented in the supplied graph; this is retained as an unknown consequence to cover during implementation. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 2fa2d3a555419b06b0224dc70a538bd0; sha256 1ebb9e123e424ae455f4438957f85e9230c13eba43bd6d860f7cba8f66b4c992; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Ready — implement the bounded same-key retry behavior, ambiguous outcome state, pre-settlement pending rendering, and acceptance tests. |
