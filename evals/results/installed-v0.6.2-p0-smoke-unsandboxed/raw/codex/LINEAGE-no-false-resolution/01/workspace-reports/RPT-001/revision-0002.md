# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | d6de4e630283351c79105a668af9fcb839b9e4a17cac207a7b08bb6ba415f648 | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Webhook delivery retries after provider timeout | An ambiguous timeout can cause the same logical webhook delivery to be attempted again after the provider already accepted it, producing duplicate consumer-visible effects. | Webhook consumers and downstream state changed by webhook handlers | The provider accepts or processes a delivery but the caller observes a timeout and retry_delivery issues another attempt. | high | Select and implement a documented idempotency or no-retry strategy, or explicitly accept the risk through an approved decision record; then verify the selected contract. | blocked |
| `IMP-002` | Concurrent execution of retry_delivery | Two workers can race and both deliver the same event if duplicate detection is absent or non-atomic. | Retry workers, the delivery provider, and webhook consumers | Multiple retry attempts for the same logical event overlap after a timeout or redelivery. | high | Make the selected duplicate-protection operation atomic and test simultaneous attempts, or document explicit approval to accept this concurrency risk. | blocked |
| `IMP-003` | Delivery identity and duplicate-retention semantics introduced by safer retries | An unstable or overly broad key can suppress legitimate events, while a short or undocumented retention window can allow late duplicates. | Webhook producers, retry operators, consumers, and replay/backfill workflows | The implementation classifies attempts as the same logical delivery or expires duplicate-protection state. | medium | Document the key source, scope, retention window, replay policy, and behavior when identity is missing before implementation, or explicitly approve acceptance of the compatibility risk. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for changing webhook delivery retries at webhook/delivery.py and retry_delivery. The supplied evidence identifies an unresolved duplicate-delivery risk. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py at retry_delivery only after selecting and documenting a duplicate-protection strategy for ambiguous provider timeouts. The selected strategy must preserve retryability for distinct webhook events while ensuring that repeated or concurrent attempts for the same logical delivery cannot create more than one consumer-visible effect. A stakeholder opinion that the risk is probably acceptable does not select a strategy or accept the risk without an approved decision record. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | A provider timeout is the condition associated with the retry_delivery entry point, and retry_delivery accepts an event and currently returns that event unchanged. | verified | webhook/delivery.py defines TIMEOUT_SOURCE as "provider timeout" and retry_delivery(event) returns event. |
| `INV-002` | Distinct logical webhook events must remain independently deliverable when retry behavior changes. | inferred | The requested change concerns retrying webhook deliveries; no repository evidence authorizes collapsing distinct events. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002` | webhook/delivery.py defines TIMEOUT_SOURCE as "provider timeout" and retry_delivery(event) returns event. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-003` | The requested change concerns retrying webhook deliveries; no repository evidence authorizes collapsing distinct events. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | high | blocked | unknown | webhook/delivery.py retries/returns the event after a provider timeout, while webhook/idempotency.py says idempotency is not configured. Because a timeout does not prove non-delivery, another attempt may repeat a delivery already accepted by the provider; no runtime or provider evidence proves whether that duplicate occurs. The stakeholder supplied no approval record or new repository evidence. | `INV-001`, `INV-002` | the pending decision | `AC-001`, `AC-003` |
| `IMP-002` | `REQ-001` | state/concurrency | high | blocked | unknown | The idempotency module contains no configured behavior, so the supplied evidence does not establish an atomic claim, lock, or durable deduplication record when more than one retry worker handles the same event; concurrent runtime behavior is not evidenced. No approved risk-acceptance decision was supplied. | `INV-001` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | compatibility | medium | blocked | unknown | webhook/idempotency.py contains only STATUS = "not configured" and DELIVERY_REF = "provider timeout"; no evidence defines the logical delivery key, duplicate retention period, replay behavior, compatibility expectations, or approved acceptance of those gaps. | `INV-002` | the pending decision | `AC-004` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which duplicate-protection contract should govern retry_delivery after an ambiguous provider timeout, or should an authorized owner explicitly accept the documented risks? | Persist a stable logical-delivery idempotency key locally and atomically claim it before delivery. | `IMP-001`, `IMP-002`, `IMP-003` | Provides strong local control and concurrency safety, but requires durable state, key and retention definitions, cleanup, and failure-recovery behavior. |
| Which duplicate-protection contract should govern retry_delivery after an ambiguous provider timeout, or should an authorized owner explicitly accept the documented risks? | Require and pass through a documented provider-native idempotency key and guarantee. | `IMP-001`, `IMP-002`, `IMP-003` | Avoids local deduplication state, but safety depends on verified provider semantics, key propagation, retention, and behavior during provider outages. |
| Which duplicate-protection contract should govern retry_delivery after an ambiguous provider timeout, or should an authorized owner explicitly accept the documented risks? | Explicitly accept the duplicate-delivery, concurrency, and compatibility risks through an approved decision record. | `IMP-001`, `IMP-002`, `IMP-003` | Avoids immediate implementation work but leaves duplicate effects, retry races, and undefined identity/retention behavior as accepted operational risks that require named ownership. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | `IMP-001`, `IMP-002`, `IMP-003` |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | none |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py at retry_delivery only after selecting and documenting a duplicate-protection strategy for ambiguous provider timeouts. The selected strategy must preserve retryability for distinct webhook events while ensuring that repeated or concurrent attempts for the same logical delivery cannot create more than one consumer-visible effect. | the pending decision | none | Controller-created refinement revision. |
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py at retry_delivery only after selecting and documenting a duplicate-protection strategy for ambiguous provider timeouts. The selected strategy must preserve retryability for distinct webhook events while ensuring that repeated or concurrent attempts for the same logical delivery cannot create more than one consumer-visible effect. A stakeholder opinion that the risk is probably acceptable does not select a strategy or accept the risk without an approved decision record. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Given a provider attempt that is accepted but returns a timeout, invoking the retry path for the same logical delivery results in no more than one consumer-visible effect, unless an authorized decision record explicitly accepts this failure mode. | Not currently evidenced; no automated scenario or approved risk-acceptance record was supplied. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-001` | Two or more concurrent retry_delivery calls for the same logical delivery cannot all perform the external delivery; losing attempts receive a deterministic duplicate/in-progress outcome, unless an authorized decision record explicitly accepts the race. | Not currently evidenced; no concurrency test, atomic protection implementation, or approved risk-acceptance record was supplied. |
| `AC-003` | `REQ-001` | `IMP-001` | `INV-002` | Two distinct logical events, including events with otherwise identical payloads, remain independently deliverable under the selected retry policy. | Not currently evidenced; add tests using distinct delivery identities with matching payload content. |
| `AC-004` | `REQ-001` | `IMP-003` | `INV-002` | Documentation and tests define the delivery identity source and scope, missing-identity behavior, deduplication retention window, replay/backfill semantics, and recovery after partial failure, or an authorized decision record explicitly accepts each omitted contract. | webhook/idempotency.py currently provides no documented idempotency behavior, and no approval record was supplied. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The repository does not define duplicate safety, and the stakeholder's statement that the risk is probably acceptable is not an approved decision record. | none | Webhook delivery owner |
| `IMP-002` | blocked | No atomic duplicate-protection behavior, concurrency evidence, or approved risk acceptance is documented. | none | Webhook delivery owner |
| `IMP-003` | blocked | The identity key, retention period, replay behavior, and missing-key policy remain undefined and unaccepted by any approved decision. | none | Webhook delivery owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| webhook/delivery.py: retry_delivery and the provider-timeout retry path | Source inspection confirms TIMEOUT_SOURCE = "provider timeout" and retry_delivery(event) returns event. | high |
| webhook/idempotency.py: duplicate-protection status and delivery reference | Source inspection confirms STATUS = "not configured" and DELIVERY_REF = "provider timeout". | high |
| Stakeholder risk-acceptance statement | A stakeholder says the risk is probably acceptable, but no approval record, selected option, rationale, named accepting authority, or idempotency evidence was supplied. | insufficient for a decision; the report remains pre-decision |
| Canonical report lineage | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 d6de4e630283351c79105a668af9fcb839b9e4a17cac207a7b08bb6ba415f648, and hashing that exact file produced the same digest. first.final.txt was not used as predecessor bytes. | high |
| Provider and consumer idempotency semantics | No provider contract, storage implementation, consumer guarantee, or retry policy is present in the supplied evidence; optional graph providers were unavailable. | unknown |
| Graph paths for IMP-001 | PATH-002: provider timeout → idempotency | PATH-002: provider builtin; confidence lexical; location webhook/delivery.py + webhook/idempotency.py |
| Graph paths for IMP-002 | PATH-002: provider timeout → idempotency | PATH-002: provider builtin; confidence lexical; location webhook/delivery.py + webhook/idempotency.py |
| Graph paths for IMP-003 | The current trace exposes PATH-002 between webhook/delivery.py and webhook/idempotency.py, plus a lexical path to first.final.txt that is chat output rather than canonical lineage or runtime evidence. The supplied sources still do not define an external identity or retention contract. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 838799f6b9044cffafde2198a7c238c7; sha256 b31bb324ea12bb84705f67a76b5d1e4f29fb16b4f54e80f2527d85e0125a5e4b; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Not ready |
