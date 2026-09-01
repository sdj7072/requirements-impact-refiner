# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | 5a954c3f6742040f97094b5b16fdfcd2ba3f3efd22342bd77489c2ff82de35f5 | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Webhook delivery retry behavior in retry_delivery | The same webhook may be delivered more than once when the first provider request succeeds but its response times out. | Webhook recipients and any downstream side effects triggered by the provider | A provider timeout followed by retry_delivery retrying the event without an effective stable idempotency policy | high | Select and document an idempotency strategy, or obtain an explicit authorized approval accepting at-least-once duplicate risk, then verify and document the selected behavior. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for changing webhook delivery retries at webhook/delivery.py and retry_delivery. The supplied evidence identifies an unresolved duplicate-delivery risk. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change webhook/delivery.py retry_delivery behavior for provider timeouts only after defining an idempotency contract that prevents an ambiguous timeout from causing the same webhook event to produce duplicate provider-side effects, or after an authorized stakeholder explicitly approves at-least-once delivery and its duplicate risk. The retry must reuse a stable delivery identity or apply another explicitly selected duplicate-control policy, and the selected behavior must be documented at the webhook/idempotency.py boundary. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | retry_delivery is the webhook retry entry point used after a provider timeout and currently returns the same event. | verified | Supplied repository evidence and repository inspection establish that webhook/delivery.py defines retry_delivery after provider timeout; retry_delivery(event) returns event. |
| `INV-002` | No repository-documented idempotency behavior or approved duplicate-risk acceptance currently defines how timeout retries handle repeated provider-side effects. | verified | webhook/idempotency.py remains not configured, and the continuation evidence explicitly states that no approval record or idempotency evidence exists. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | Supplied repository evidence and repository inspection establish that webhook/delivery.py defines retry_delivery after provider timeout; retry_delivery(event) returns event. |
| `INV-002` | `REQ-001` | `IMP-001` | webhook/idempotency.py remains not configured, and the continuation evidence explicitly states that no approval record or idempotency evidence exists. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | high | blocked | unknown | A provider timeout remains ambiguous: the provider may have accepted the first delivery before its response was lost, and retrying without a documented idempotency mechanism may repeat the provider-side effect. A stakeholder's statement that the risk is probably acceptable is neither repository evidence nor an approved decision, so it does not accept or resolve this impact. | `INV-001`, `INV-002` | the pending decision | `AC-001` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which delivery guarantee should retry_delivery enforce for an ambiguous provider timeout? | Persist and reuse a stable delivery idempotency key across every retry. | `IMP-001` | Provides the strongest duplicate protection, but requires durable key/state handling and provider or local deduplication support. |
| Which delivery guarantee should retry_delivery enforce for an ambiguous provider timeout? | Use the provider's idempotency-key contract and reuse the same key across retries. | `IMP-001` | Keeps local state simpler, but safety depends on the provider's documented key scope, retention period, and retry semantics. |
| Which delivery guarantee should retry_delivery enforce for an ambiguous provider timeout? | Retain at-least-once delivery and explicitly accept possible duplicates. | `IMP-001` | Minimizes implementation work, but requires an authorized approval record and makes downstream consumers responsible for duplicate tolerance. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | `IMP-001` |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | none |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Change webhook/delivery.py retry_delivery behavior for provider timeouts only after defining an idempotency contract that prevents an ambiguous timeout from causing the same webhook event to produce duplicate provider-side effects. The retry must reuse a stable delivery identity or apply another explicitly selected duplicate-control policy, and the selected behavior must be documented at the webhook/idempotency.py boundary. | the pending decision | none | Controller-created refinement revision. |
| `REQ-001` | Change webhook/delivery.py retry_delivery behavior for provider timeouts only after defining an idempotency contract that prevents an ambiguous timeout from causing the same webhook event to produce duplicate provider-side effects, or after an authorized stakeholder explicitly approves at-least-once delivery and its duplicate risk. The retry must reuse a stable delivery identity or apply another explicitly selected duplicate-control policy, and the selected behavior must be documented at the webhook/idempotency.py boundary. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | A test must simulate a first provider attempt that takes effect but times out, then invoke retry_delivery and demonstrate the selected contract: one effective delivery for an idempotent guarantee, or an explicitly documented duplicate outcome backed by an authorized approval record for accepted at-least-once delivery. | No idempotency evidence, approval record, or approved decision was supplied. The stakeholder's statement that the risk is probably acceptable does not satisfy this criterion. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The delivery guarantee remains unselected, and neither an idempotency mechanism nor an authorized decision accepting duplicates is evidenced. | none | Webhook delivery owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| webhook/delivery.py: retry_delivery and its provider-timeout retry behavior | The file defines TIMEOUT_SOURCE = "provider timeout" and retry_delivery(event). | verified |
| webhook/idempotency.py: idempotency contract used by delivery retries | The file contains STATUS = "not configured" and no documented idempotency behavior. | verified |
| Risk-acceptance decision | A stakeholder said the risk is probably acceptable, but no approved decision or approval record was provided. | verified statement; insufficient for decision acceptance |
| Canonical report lineage | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md; hashing that exact file yields 5a954c3f6742040f97094b5b16fdfcd2ba3f3efd22342bd77489c2ff82de35f5, matching the controller predecessor SHA-256. | verified; first.final.txt was not used as predecessor bytes |
| Provider-side duplicate handling and persistence semantics | No provider contract, stable delivery key, retention rule, or deduplication store is identified. | unknown; provider evidence remains unavailable |
| Graph paths for IMP-001 | PATH-001: provider timeout → first.final.txt &#124;&#124; PATH-002: provider timeout → idempotency | PATH-001: provider builtin; confidence lexical; location webhook/delivery.py + first.final.txt &#124;&#124; PATH-002: provider builtin; confidence lexical; location webhook/delivery.py + webhook/idempotency.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 90d373c97c963fc13b65b184c63f00a1; sha256 624dcc35cdf4fb8b6f8311a1153242575b7e00e98b817fbe85acc429e63cbb11; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `IMP-001` | `IMP-001` | `AC-001` | Not ready |
