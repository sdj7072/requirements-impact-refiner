# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Webhook delivery retry behavior after provider timeout | The original delivery may have succeeded even though the caller observed a timeout, so retrying can repeat the webhook's downstream side effects. | Webhook recipients, downstream state changed by webhook handlers, and operators reconciling delivery attempts | retry_delivery processes an event after an ambiguous provider timeout without an established idempotency or deduplication contract | high | Select and implement one explicit contract: reuse a provider-enforced idempotency key, suppress/reconcile duplicates in a durable local ledger, or explicitly accept at-least-once delivery with a documented consumer deduplication obligation. | blocked |

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
| `INV-002` | All attempts for one logical webhook event must retain enough stable identity to apply the selected duplicate-delivery contract. | unknown | The supplied evidence and inspected files do not show an event identity, attempt identity, persistence rule, or idempotency-key behavior. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | webhook/delivery.py defines TIMEOUT_SOURCE as "provider timeout" and retry_delivery(event) returns the event. |
| `INV-002` | `REQ-001` | `IMP-001` | The supplied evidence and inspected files do not show an event identity, attempt identity, persistence rule, or idempotency-key behavior. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | high | blocked | unknown | retry_delivery is present in the provider-timeout context, where the provider outcome may be ambiguous, while webhook/idempotency.py only declares STATUS = "not configured" and contains no idempotency behavior. The scan connects webhook/delivery.py to webhook/idempotency.py through PATH-001, but its provider frontier prevents stronger confidence. | `INV-001`, `INV-002` | the pending decision | `AC-001`, `AC-002` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which duplicate-delivery contract should govern retry_delivery after a provider timeout? | Reuse a stable provider-enforced idempotency key for every attempt of the same logical webhook event. | `IMP-001` | Simplest delivery-side behavior when the provider guarantees idempotency, but requires verified provider support and stable key persistence. |
| Which duplicate-delivery contract should govern retry_delivery after a provider timeout? | Maintain a durable local delivery ledger and reconcile ambiguous outcomes before or during retry. | `IMP-001` | Does not depend entirely on provider idempotency, but adds persistence, concurrency control, retention, and recovery complexity. |
| Which duplicate-delivery contract should govern retry_delivery after a provider timeout? | Explicitly retain at-least-once delivery and require webhook consumers to deduplicate. | `IMP-001` | Keeps the producer simpler but transfers correctness risk to every consumer and requires a documented stable event identifier and compatibility commitment. |

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
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py at retry_delivery so a provider timeout does not cause an uncontrolled duplicate delivery. Preserve retry capability for timeout failures, but define and enforce an explicit duplicate-delivery contract before implementation. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | A test covering 'provider accepted the original delivery but the caller timed out' demonstrates the selected contract: either the retry has no second external effect, or an explicitly accepted at-least-once contract supplies the same documented stable event identifier for consumer deduplication. | No current test or implementation evidence was supplied or found for ambiguous-timeout duplicate control. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | A provider-timeout delivery remains retryable under the selected contract, and a test verifies that duplicate protection does not silently discard an event whose original attempt did not take effect. | Current retry_delivery(event) returns the event, establishing the retry behavior that must be preserved while adding protection. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The repository does not establish idempotency behavior or identify which component owns duplicate suppression; implementation would encode an unapproved delivery guarantee. | none | Webhook delivery owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| webhook/delivery.py: retry_delivery and provider-timeout retry behavior | The file defines TIMEOUT_SOURCE = "provider timeout" and retry_delivery(event). | verified |
| webhook/idempotency.py: duplicate-suppression contract and supporting behavior | The file contains STATUS = "not configured" and DELIVERY_REF = "provider timeout", but no documented or executable idempotency behavior. | verified |
| Provider guarantees, persistence for delivery identity/attempt state, downstream consumer deduplication, and retry tests | No provider contract, storage implementation, consumer contract, or tests were supplied or discovered in the named evidence. | unknown |
| Graph paths for IMP-001 | PATH-001: webhook/delivery.py → webhook/idempotency.py | PATH-001: provider builtin; confidence lexical; location webhook/delivery.py + webhook/idempotency.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 0508663919442f6a3ff2df1b54183056; sha256 826bd2a9a0cf20c396023bf92f733ccc463b94a6c1fa5c5659dc788dcea732d2; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `IMP-001` | `IMP-001` | `AC-001`, `AC-002` | Not ready |
