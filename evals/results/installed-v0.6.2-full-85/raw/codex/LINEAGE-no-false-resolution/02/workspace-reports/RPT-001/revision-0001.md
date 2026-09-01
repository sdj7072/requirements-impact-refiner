# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Webhook retry behavior after a provider timeout | The same logical event may be delivered and applied more than once when the first attempt succeeded remotely but its response timed out. | Webhook recipients and any non-idempotent downstream side effects such as writes, notifications, billing, or state transitions. | retry_delivery runs after an ambiguous provider-timeout result. | high | Select and implement one explicit delivery guarantee: stable idempotency enforcement, no automatic retry, or documented at-least-once delivery with downstream deduplication. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for changing webhook delivery retries at webhook/delivery.py and retry_delivery. The supplied evidence identifies an unresolved duplicate-delivery risk. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py for provider-timeout outcomes only after defining the delivery guarantee and duplicate-prevention contract. retry_delivery must preserve the original logical event identity across attempts, and the selected policy must specify whether retries are idempotent, suppressed, or explicitly at-least-once with downstream deduplication. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | A retry represents the same logical webhook event and preserves the original event data/identity rather than creating an unrelated delivery. | verified | webhook/delivery.py defines retry_delivery(event) and returns the same event object; the file identifies the trigger source as provider timeout. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | webhook/delivery.py defines retry_delivery(event) and returns the same event object; the file identifies the trigger source as provider timeout. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | high | blocked | unknown | A provider timeout does not prove that the provider rejected or failed to process the first attempt. webhook/delivery.py associates retry_delivery with provider timeout, while webhook/idempotency.py declares STATUS = "not configured" and contains no idempotency contract. The receipt links those files only through lexical and structural inference, and the provider remains an explicit coverage frontier. | `INV-001` | the pending decision | `AC-001`, `AC-002` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which duplicate-handling guarantee should govern retry_delivery after an ambiguous provider timeout? | Require a stable idempotency key and make retries safe to replay. | `IMP-001` | Best preserves retry-based reliability, but requires a documented key lifecycle, persistence/deduplication behavior, and provider or receiver support. |
| Which duplicate-handling guarantee should govern retry_delivery after an ambiguous provider timeout? | Suppress automatic retry after provider timeout. | `IMP-001` | Avoids retry-created duplicates but can lose deliveries when the timed-out first attempt was not processed. |
| Which duplicate-handling guarantee should govern retry_delivery after an ambiguous provider timeout? | Keep at-least-once retries and require downstream deduplication. | `IMP-001` | Keeps delivery availability but makes duplicates part of the public contract and shifts correctness responsibility to recipients. |

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
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py for provider-timeout outcomes only after defining the delivery guarantee and duplicate-prevention contract. retry_delivery must preserve the original logical event identity across attempts, and the selected policy must specify whether retries are idempotent, suppressed, or explicitly at-least-once with downstream deduplication. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | An automated test models a provider that applies the event and then times out; the selected retry policy produces no undocumented duplicate side effect and preserves the same logical event identity. | No such test or selected timeout policy is present in the supplied two-file repository scope. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | The selected delivery guarantee, idempotency key source and lifetime, retry conditions, and duplicate ownership are documented and enforced by code before retry behavior is enabled. | webhook/idempotency.py currently reports idempotency as not configured and documents no behavior. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The implementation cannot safely choose between possible delivery loss and possible duplicate side effects until the timeout delivery guarantee is selected. | none | Webhook delivery product/engineering owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| webhook/delivery.py and retry_delivery | The file contains TIMEOUT_SOURCE = "provider timeout" and retry_delivery(event), which currently returns the event unchanged. | High for the current local behavior; the repository contains no provider call or broader retry scheduling implementation. |
| webhook/idempotency.py | The file contains STATUS = "not configured" and DELIVERY_REF = "provider timeout" with no implemented or documented idempotency behavior. | High within the supplied repository. |
| Webhook provider and downstream consumer side effects | The scan frontier reports the external provider unavailable and used only built-in repository analysis; no recipient contract or provider semantics are present. | Unknown; external behavior must be supplied or documented before resolving the risk. |
| Graph paths for IMP-001 | PATH-001: webhook/delivery.py → webhook/idempotency.py | PATH-001: provider builtin; confidence lexical; location webhook/delivery.py + webhook/idempotency.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt f06d951b7a3d5d39d238e1235a6f8f46; sha256 18445be14eb34e107232272148179ce71732044f05361a7c0bd7915d506071c7; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `IMP-001` | `IMP-001` | `AC-001`, `AC-002` | Not ready |
