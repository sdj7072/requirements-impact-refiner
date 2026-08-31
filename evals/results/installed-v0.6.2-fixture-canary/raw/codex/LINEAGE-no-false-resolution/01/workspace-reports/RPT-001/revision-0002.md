# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | 0ad5f53de4eb9f25c03ab234bceb0cdea72bdaceb5827cc4c5ae08f3b5216693 | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Webhook delivery retry behavior in retry_delivery | A retry after an ambiguous provider timeout may deliver the same event twice and repeat downstream side effects. | Webhook recipients and any downstream state changes triggered by the event | The provider accepts or processes the first attempt but its response times out, after which retry_delivery sends another attempt. | high | Obtain an explicit decision selecting deduplication, reconciliation, or accepted at-least-once delivery; a tentative stakeholder opinion is insufficient. | blocked |
| `IMP-002` | The result and observable contract of retry_delivery | Callers may observe a changed return value or delivery outcome without a defined compatibility contract. | Callers of retry_delivery and operational handling of failed webhook attempts | Retry logic starts returning a status, wrapping the event, suppressing a retry, or raising an error instead of returning the event unchanged. | medium | Document and approve the timeout and return-value contract, preserve event passthrough unless intentionally changed, and add contract tests before implementation. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for changing webhook delivery retries at webhook/delivery.py and retry_delivery. The supplied evidence identifies an unresolved duplicate-delivery risk. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py at retry_delivery for provider-timeout outcomes only after selecting and specifying a duplicate-delivery policy; the implementation must preserve the event passed to retry_delivery and must prevent, suppress, or explicitly accept duplicate externally observable delivery when the provider may have accepted the original attempt before timing out. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | A provider-timeout outcome is the boundary that invokes retry_delivery. | verified | webhook/delivery.py still defines TIMEOUT_SOURCE = "provider timeout" and defines retry_delivery immediately in the same module. |
| `INV-002` | retry_delivery currently returns the supplied event unchanged. | verified | webhook/delivery.py still implements retry_delivery(event) as return event. |
| `INV-003` | No current repository behavior guarantees that repeated delivery of the same event is idempotent or deduplicated. | verified | webhook/idempotency.py still contains only STATUS = "not configured" and DELIVERY_REF = "provider timeout"; no idempotency key, store, retention rule, or duplicate-handling behavior is documented. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002` | webhook/delivery.py still defines TIMEOUT_SOURCE = "provider timeout" and defines retry_delivery immediately in the same module. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002` | webhook/delivery.py still implements retry_delivery(event) as return event. |
| `INV-003` | `REQ-001` | `IMP-001` | webhook/idempotency.py still contains only STATUS = "not configured" and DELIVERY_REF = "provider timeout"; no idempotency key, store, retention rule, or duplicate-handling behavior is documented. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | high | blocked | unknown | The exact persisted predecessor records the unresolved provider-timeout duplicate-delivery risk. The stakeholder says the risk is only "probably acceptable," while the supplied evidence explicitly says no approval record or idempotency evidence exists; this does not accept or resolve the risk. | `INV-001`, `INV-002`, `INV-003` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | interfaces | medium | blocked | unknown | The persisted predecessor and current files provide no caller contract, provider acknowledgment model, retry result type, or tests beyond retry_delivery returning the input event. The stakeholder statement supplies no approved contract change. | `INV-001`, `INV-002` | the pending decision | `AC-002` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which duplicate-delivery policy should govern retry_delivery when a provider timeout leaves acceptance of the original attempt unknown? | Require a stable idempotency key and durable deduplication before automatic retry. | `IMP-001`, `IMP-002` | Best duplicate suppression, but requires a key contract, storage/retention rules, and defined behavior when the deduplication store is unavailable. |
| Which duplicate-delivery policy should govern retry_delivery when a provider timeout leaves acceptance of the original attempt unknown? | Do not automatically retry ambiguous provider timeouts; surface the delivery for reconciliation. | `IMP-001`, `IMP-002` | Avoids retry-created duplicates, but may leave accepted-unknown or genuinely failed deliveries pending and requires an operational reconciliation path. |
| Which duplicate-delivery policy should govern retry_delivery when a provider timeout leaves acceptance of the original attempt unknown? | Retain automatic retry and explicitly accept at-least-once delivery. | `IMP-001`, `IMP-002` | Keeps availability and simple retry behavior, but requires an explicit approved acceptance and downstream consumers that tolerate duplicates. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | `IMP-001`, `IMP-002` |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | none |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py at retry_delivery for provider-timeout outcomes only after selecting and specifying a duplicate-delivery policy; the implementation must preserve the event passed to retry_delivery and must prevent, suppress, or explicitly accept duplicate externally observable delivery when the provider may have accepted the original attempt before timing out. | the pending decision | none | Controller-created refinement revision. |
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py at retry_delivery for provider-timeout outcomes only after selecting and specifying a duplicate-delivery policy; the implementation must preserve the event passed to retry_delivery and must prevent, suppress, or explicitly accept duplicate externally observable delivery when the provider may have accepted the original attempt before timing out. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-003` | A test simulating an initial provider acceptance followed by a response timeout demonstrates the selected policy: the event is deduplicated, withheld for reconciliation, or deliberately redelivered under a documented and explicitly approved at-least-once contract. | No approval record, idempotency behavior, or policy test was supplied, so this criterion remains unsatisfied. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | Tests document the retry_delivery return-value and failure contract and confirm that the input event remains unchanged unless a separately approved compatibility change specifies otherwise. | The current verified function behavior remains return event; no approved contract or test evidence was supplied. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The stakeholder's tentative view is not an approved choice, and no evidence establishes deduplication or an accepted at-least-once policy. | none | Webhook delivery owner |
| `IMP-002` | blocked | Caller expectations and the intended retry result contract remain undocumented and unapproved. | none | Webhook delivery owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Canonical predecessor lineage | .requirements-impact-refiner/reports/RPT-001/current.json selected revision-0001.md, whose exact bytes hash to 0ad5f53de4eb9f25c03ab234bceb0cdea72bdaceb5827cc4c5ae08f3b5216693; first.final.txt was not used as lineage bytes. | high |
| webhook/delivery.py: retry_delivery and provider-timeout retry behavior | Current repository inspection confirms TIMEOUT_SOURCE and the event-passthrough retry_delivery implementation are unchanged. | high |
| webhook/idempotency.py: duplicate suppression behavior | Current repository inspection confirms idempotency status is not configured and no key, store, retention, or duplicate-handling behavior is defined. | high |
| Stakeholder risk disposition | The follow-up describes the risk only as "probably acceptable," and supplied evidence says no approval record exists. | high that no acceptance decision was provided; no technical risk reduction is established |
| Callers, provider acknowledgment semantics, persistence, and tests | No additional source files, approval record, idempotency implementation, or contracts were supplied or found. | low; this remains an evidence frontier |
| Graph paths for IMP-001 | PATH-002: webhook/delivery.py → webhook/idempotency.py | PATH-002: provider builtin; confidence lexical; location webhook/delivery.py + webhook/idempotency.py |
| Graph paths for IMP-002 | PATH-002: webhook/delivery.py → webhook/idempotency.py | PATH-002: provider builtin; confidence lexical; location webhook/delivery.py + webhook/idempotency.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 1e7da651c0b91c6c694f3ebbe00734d1; sha256 bbbf89b179db76daba3a97aacfb5a9cdab8fbc3f67ae948c964cf00ba708491b; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002` | `IMP-001`, `IMP-002` | `AC-001`, `AC-002` | Not ready |
