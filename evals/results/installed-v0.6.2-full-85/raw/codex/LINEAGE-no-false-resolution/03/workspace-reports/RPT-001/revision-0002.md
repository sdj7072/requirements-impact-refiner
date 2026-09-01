# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | 45b69b1d934704667ee1ab725e5e99d940fb7759281dafcba03d8e956495fbde | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Webhook delivery retry behavior after provider timeout | The original delivery may have succeeded even though the caller observed a timeout, so retrying can repeat the webhook's downstream side effects. | Webhook recipients, downstream state changed by webhook handlers, and operators reconciling delivery attempts | retry_delivery processes an event after an ambiguous provider timeout without an established idempotency or deduplication contract | high | Obtain an explicit approved decision selecting a provider-enforced idempotency key, a durable local delivery ledger, or accepted at-least-once delivery with a documented consumer deduplication obligation. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for changing webhook delivery retries at webhook/delivery.py and retry_delivery. The supplied evidence identifies an unresolved duplicate-delivery risk. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py at retry_delivery so a provider timeout does not cause an uncontrolled duplicate delivery. Preserve retry capability for timeout failures, but define and enforce an explicit duplicate-delivery contract before implementation. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Webhook deliveries that encounter a provider timeout remain eligible for retry. | verified | webhook/delivery.py defines TIMEOUT_SOURCE as "provider timeout" and retry_delivery(event) returns the event. |
| `INV-002` | All attempts for one logical webhook event must retain enough stable identity to apply the selected duplicate-delivery contract. | unknown | No idempotency evidence, stable event identity, attempt identity, persistence rule, or approved consumer-deduplication contract has been provided. |
| `INV-003` | first.final.txt is excluded from canonical report lineage; the predecessor is the exact Markdown file selected by RPT-001/current.json. | verified | current.json selects revision-0001.md and records SHA-256 45b69b1d934704667ee1ab725e5e99d940fb7759281dafcba03d8e956495fbde; hashing that exact file produces the same digest. first.final.txt is the chat response and was not used as predecessor bytes. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | webhook/delivery.py defines TIMEOUT_SOURCE as "provider timeout" and retry_delivery(event) returns the event. |
| `INV-002` | `REQ-001` | `IMP-001` | No idempotency evidence, stable event identity, attempt identity, persistence rule, or approved consumer-deduplication contract has been provided. |
| `INV-003` | `REQ-001` | `IMP-001` | current.json selects revision-0001.md and records SHA-256 45b69b1d934704667ee1ab725e5e99d940fb7759281dafcba03d8e956495fbde; hashing that exact file produces the same digest. first.final.txt is the chat response and was not used as predecessor bytes. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | high | blocked | unknown | retry_delivery remains in the provider-timeout context and webhook/idempotency.py still has no established idempotency behavior. A stakeholder says the risk is probably acceptable, but the supplied evidence explicitly contains no approval record or idempotency evidence. PATH-003 connects webhook/delivery.py to webhook/idempotency.py; first.final.txt is covered only as a verified noncanonical-lineage invariant, and the provider frontier prevents stronger confidence. | `INV-001`, `INV-002`, `INV-003` | the pending decision | `AC-001`, `AC-002` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which duplicate-delivery contract should govern retry_delivery after a provider timeout? | Reuse a stable provider-enforced idempotency key for every attempt of the same logical webhook event. | `IMP-001` | Simplest delivery-side behavior when the provider guarantees idempotency, but requires verified provider support and stable key persistence. |
| Which duplicate-delivery contract should govern retry_delivery after a provider timeout? | Maintain a durable local delivery ledger and reconcile ambiguous outcomes before or during retry. | `IMP-001` | Does not depend entirely on provider idempotency, but adds persistence, concurrency control, retention, and recovery complexity. |
| Which duplicate-delivery contract should govern retry_delivery after a provider timeout? | Explicitly retain at-least-once delivery and require webhook consumers to deduplicate. | `IMP-001` | Keeps the producer simpler but transfers correctness risk to every consumer and requires an approved compatibility commitment plus a documented stable event identifier. |

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
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py at retry_delivery so a provider timeout does not cause an uncontrolled duplicate delivery. Preserve retry capability for timeout failures, but define and enforce an explicit duplicate-delivery contract before implementation. | the pending decision | none | Controller-created refinement revision. |
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py at retry_delivery so a provider timeout does not cause an uncontrolled duplicate delivery. Preserve retry capability for timeout failures, but define and enforce an explicit duplicate-delivery contract before implementation. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | A test covering 'provider accepted the original delivery but the caller timed out' demonstrates the selected contract: either the retry has no second external effect, or an explicitly approved at-least-once contract supplies the same documented stable event identifier for consumer deduplication. | No approval record, idempotency evidence, or current test evidence was provided for ambiguous-timeout duplicate control. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | A provider-timeout delivery remains retryable under the selected contract, and a test verifies that duplicate protection does not silently discard an event whose original attempt did not take effect. | Current retry_delivery(event) returns the event, establishing the retry behavior that must be preserved while adding protection. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | A stakeholder's statement that the risk is probably acceptable is not an approved decision. No approval record, idempotency behavior, or consumer deduplication guarantee exists, so the impact cannot be marked accepted or resolved. | none | Webhook delivery owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Persisted report lineage RPT-001 revision 1 | current.json selects revision-0001.md, whose exact canonical bytes hash to 45b69b1d934704667ee1ab725e5e99d940fb7759281dafcba03d8e956495fbde; the chat response was not used as predecessor bytes. | verified |
| webhook/delivery.py: retry_delivery and provider-timeout retry behavior | The file defines TIMEOUT_SOURCE = "provider timeout" and retry_delivery(event). | verified |
| webhook/idempotency.py: duplicate-suppression contract and supporting behavior | No documented or executable idempotency behavior or new idempotency evidence exists. | unknown |
| Stakeholder risk-acceptance statement | The stakeholder says the risk is probably acceptable, but no approval record or selected decision was provided. | supplied opinion only; insufficient for a decision or accepted impact state |
| Provider guarantees, persistence for delivery identity/attempt state, downstream consumer deduplication, and retry tests | No provider contract, storage implementation, consumer contract, approval record, or tests were supplied. | unknown |
| Graph paths for IMP-001 | PATH-003: webhook/delivery.py → webhook/idempotency.py | PATH-003: provider builtin; confidence lexical; location webhook/delivery.py + webhook/idempotency.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt e10cd25050fcf6504a59f34e1ae69f10; sha256 be0d1701515a5db929ba96fbf3068cca3a1aad1c7305a4e53188468aa5f35fc1; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001` | `IMP-001` | `AC-001`, `AC-002` | Not ready |
