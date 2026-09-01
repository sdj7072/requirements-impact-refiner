# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Webhook retry behavior after provider timeout | A retry may deliver the same logical webhook event twice when the first attempt succeeded remotely but its acknowledgement was lost. | Webhook recipients, downstream side effects, delivery accounting, and operators reconciling webhook outcomes | retry_delivery is invoked after an ambiguous provider timeout without a proven idempotency key or provider delivery-status check | high | Select and verify an idempotency or reconciliation strategy before changing retry mechanics; retain one stable logical delivery identity across attempts and test the ambiguous-timeout case. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for changing webhook delivery retries at webhook/delivery.py and retry_delivery. The supplied evidence identifies an unresolved duplicate-delivery risk. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change webhook delivery retry behavior in webhook/delivery.py at retry_delivery for provider-timeout outcomes, while preventing a single logical webhook event from being delivered more than once. The retry mechanism must define how an ambiguous provider timeout is distinguished from a confirmed failure before another delivery attempt is issued. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | retry_delivery is the retry boundary used after a provider timeout and currently returns the supplied event for another delivery attempt. | verified | webhook/delivery.py defines TIMEOUT_SOURCE as "provider timeout" and retry_delivery(event) returns event. |
| `INV-002` | No configured or documented idempotency guarantee currently protects webhook timeout retries. | verified | webhook/idempotency.py contains STATUS = "not configured" and only references "provider timeout"; no idempotency behavior is defined. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | webhook/delivery.py defines TIMEOUT_SOURCE as "provider timeout" and retry_delivery(event) returns event. |
| `INV-002` | `REQ-001` | `IMP-001` | webhook/idempotency.py contains STATUS = "not configured" and only references "provider timeout"; no idempotency behavior is defined. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | high | blocked | unknown | The supplied files establish a provider-timeout retry boundary and no configured idempotency behavior. The provider acknowledgement and commit semantics are absent, so whether a timed-out first attempt can have committed—and therefore whether a retry duplicates delivery—remains unverified. | `INV-001`, `INV-002` | the pending decision | `AC-001`, `AC-002` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which duplicate-delivery control must govern retry_delivery after an ambiguous provider timeout? | Reuse a stable idempotency key for every attempt of one logical webhook event and require provider-side deduplication. | `IMP-001` | Strong retry simplicity and duplicate protection, but depends on a documented provider idempotency contract and key-retention window. |
| Which duplicate-delivery control must govern retry_delivery after an ambiguous provider timeout? | Reconcile the first attempt with the provider before retrying, and retry only when non-delivery is confirmed. | `IMP-001` | Avoids relying solely on deduplication, but adds status-query latency, provider integration complexity, and handling for inconclusive reconciliation. |
| Which duplicate-delivery control must govern retry_delivery after an ambiguous provider timeout? | Keep at-least-once retry semantics and require downstream consumers to deduplicate by a stable event identifier. | `IMP-001` | Preserves availability during ambiguous failures, but transfers correctness responsibility to every consumer and leaves duplicates possible for non-compliant consumers. |

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
| `REQ-001` | Change webhook delivery retry behavior in webhook/delivery.py at retry_delivery for provider-timeout outcomes, while preventing a single logical webhook event from being delivered more than once. The retry mechanism must define how an ambiguous provider timeout is distinguished from a confirmed failure before another delivery attempt is issued. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | A test that simulates a provider accepting the first delivery but timing out before acknowledgement must show that repeated retry_delivery processing produces no more than one committed downstream side effect for the same logical event. | Required acceptance evidence; the current idempotency module is not configured and provides no such guarantee. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | retry_delivery must preserve a stable logical delivery identity and follow the selected duplicate-control strategy before issuing another provider delivery attempt after a timeout. | Required implementation and test evidence; the current function only returns the event and does not document or enforce an ambiguous-timeout strategy. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The repository evidence establishes a retry boundary and the absence of configured idempotency, but does not establish which party guarantees deduplication or how provider timeout outcomes are reconciled. | none | Webhook delivery owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| webhook/delivery.py: retry_delivery and provider-timeout retry semantics | The file defines TIMEOUT_SOURCE = "provider timeout" and retry_delivery(event). | verified |
| webhook/idempotency.py: idempotency configuration and delivery identity contract | The file declares STATUS = "not configured" and contains no documented idempotency behavior. | verified |
| Provider and downstream duplicate-control guarantees | No provider idempotency contract, acknowledgement semantics, status-query behavior, or downstream deduplication contract is present in the supplied repository evidence. | unknown; must be resolved before implementation planning |
| Graph paths for IMP-001 | PATH-001: webhook/delivery.py → webhook/idempotency.py | PATH-001: provider builtin; confidence lexical; location webhook/delivery.py + webhook/idempotency.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt aa968c4c721fabc5f15d8be773833034; sha256 96658918506e3ef3b502bc9d00a4de736c1dd97eaf9dc2e9418e51fbd2e3e002; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `IMP-001` | `IMP-001` | `AC-001`, `AC-002` | Not ready |
