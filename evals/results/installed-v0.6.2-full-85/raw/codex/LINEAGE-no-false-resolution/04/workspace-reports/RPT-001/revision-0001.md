# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Webhook delivery retry behavior in retry_delivery | The same webhook may be delivered more than once when the first provider request succeeds but its response times out. | Webhook recipients and any downstream side effects triggered by the provider | A provider timeout followed by retry_delivery retrying the event without an effective stable idempotency policy | high | Select and document an idempotency strategy, carry its stable identity across attempts, and verify the ambiguous-timeout case before implementation proceeds. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for changing webhook delivery retries at webhook/delivery.py and retry_delivery. The supplied evidence identifies an unresolved duplicate-delivery risk. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change webhook/delivery.py retry_delivery behavior for provider timeouts only after defining an idempotency contract that prevents an ambiguous timeout from causing the same webhook event to produce duplicate provider-side effects. The retry must reuse a stable delivery identity or apply another explicitly selected duplicate-control policy, and the selected behavior must be documented at the webhook/idempotency.py boundary. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | retry_delivery is the webhook retry entry point used after a provider timeout and currently returns the same event. | verified | Supplied evidence states that webhook/delivery.py defines retry_delivery after provider timeout; repository inspection shows TIMEOUT_SOURCE = "provider timeout" and retry_delivery(event) returns event. |
| `INV-002` | No repository-documented idempotency behavior currently defines how timeout retries avoid repeating a provider-side effect. | verified | webhook/idempotency.py contains only STATUS = "not configured" and DELIVERY_REF = "provider timeout"; no idempotency contract or behavior is documented. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | Supplied evidence states that webhook/delivery.py defines retry_delivery after provider timeout; repository inspection shows TIMEOUT_SOURCE = "provider timeout" and retry_delivery(event) returns event. |
| `INV-002` | `REQ-001` | `IMP-001` | webhook/idempotency.py contains only STATUS = "not configured" and DELIVERY_REF = "provider timeout"; no idempotency contract or behavior is documented. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | high | blocked | unknown | A provider timeout is ambiguous: the provider may have accepted the first delivery before its response was lost. Retrying without a documented idempotency mechanism may repeat the provider-side effect. The promoted fallback scan links webhook/delivery.py to webhook/idempotency.py, but provider integration evidence is unavailable. | `INV-001`, `INV-002` | the pending decision | `AC-001` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which delivery guarantee should retry_delivery enforce for an ambiguous provider timeout? | Persist and reuse a stable delivery idempotency key across every retry. | `IMP-001` | Provides the strongest duplicate protection, but requires durable key/state handling and provider or local deduplication support. |
| Which delivery guarantee should retry_delivery enforce for an ambiguous provider timeout? | Use the provider's idempotency-key contract and reuse the same key across retries. | `IMP-001` | Keeps local state simpler, but safety depends on the provider's documented key scope, retention period, and retry semantics. |
| Which delivery guarantee should retry_delivery enforce for an ambiguous provider timeout? | Retain at-least-once delivery and explicitly accept possible duplicates. | `IMP-001` | Minimizes implementation work, but downstream consumers must tolerate duplicate webhook effects and the high risk remains accepted. |

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
| new | `IMP-001` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Change webhook/delivery.py retry_delivery behavior for provider timeouts only after defining an idempotency contract that prevents an ambiguous timeout from causing the same webhook event to produce duplicate provider-side effects. The retry must reuse a stable delivery identity or apply another explicitly selected duplicate-control policy, and the selected behavior must be documented at the webhook/idempotency.py boundary. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | A test must simulate a first provider attempt that takes effect but times out, then invoke retry_delivery and demonstrate the selected contract: one effective delivery for an idempotent guarantee, or an explicitly documented duplicate outcome for accepted at-least-once delivery. | No such test or documented guarantee is present in the supplied evidence or inspected webhook files. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The required delivery guarantee and its idempotency mechanism have not been selected, so changing retry behavior could introduce or preserve duplicate provider-side effects. | none | Webhook delivery owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| webhook/delivery.py: retry_delivery and its provider-timeout retry behavior | The file defines TIMEOUT_SOURCE = "provider timeout" and retry_delivery(event). | verified |
| webhook/idempotency.py: idempotency contract used by delivery retries | The file contains STATUS = "not configured" and no documented idempotency behavior. | verified |
| Provider-side duplicate handling and persistence semantics | No provider contract, stable delivery key, retention rule, or deduplication store is identified in the supplied evidence. | unknown; must be established by the selected option |
| Graph paths for IMP-001 | PATH-001: webhook/delivery.py → webhook/idempotency.py | PATH-001: provider builtin; confidence lexical; location webhook/delivery.py + webhook/idempotency.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 30c5b90f3ac7dc506ed1616e93025909; sha256 28a12f3da4e6d19cfc5cf2de7ebf8fbeb9811ccb343a26128c5effff8998aeb0; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `IMP-001` | `IMP-001` | `AC-001` | Not ready |
