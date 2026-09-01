# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Webhook delivery retry behavior after a provider timeout | The same logical webhook can be delivered more than once when the provider accepted the first attempt but its response timed out. | Webhook recipients, their downstream side effects, and operators reconciling delivery incidents | An ambiguous provider timeout followed by retry_delivery for the same event | high | Select and document the delivery guarantee, then verify stable idempotency across attempts or suppress the ambiguous retry; otherwise explicitly accept at-least-once duplicate risk. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for changing webhook delivery retries at webhook/delivery.py and retry_delivery. The supplied evidence identifies an unresolved duplicate-delivery risk. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py at retry_delivery while preserving its event-facing API and timeout-triggered retry boundary, but do not release the change until the delivery guarantee for an ambiguous provider timeout is selected and the unresolved duplicate-delivery risk is prevented or explicitly accepted. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | retry_delivery continues to accept one event at the provider-timeout retry boundary and returns an event-compatible result. | verified | webhook/delivery.py defines TIMEOUT_SOURCE as "provider timeout" and retry_delivery(event) currently returns event. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | webhook/delivery.py defines TIMEOUT_SOURCE as "provider timeout" and retry_delivery(event) currently returns event. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | high | blocked | unknown | The supplied evidence identifies duplicate delivery as unresolved. The initial provider attempt may complete before its response times out, after which retry_delivery may repeat the same logical delivery; however, provider runtime semantics are unavailable. webhook/idempotency.py exposes only STATUS = "not configured" and documents no idempotency behavior. No repository tests or other webhook files establish duplicate suppression. | `INV-001` | the pending decision | `AC-001`, `AC-002` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which delivery guarantee should retry_delivery enforce after an ambiguous provider timeout? | Retry with a stable provider-supported idempotency key for the logical event. | `IMP-001` | Preserves retries and can suppress duplicates, but depends on provider idempotency support and stable key propagation. |
| Which delivery guarantee should retry_delivery enforce after an ambiguous provider timeout? | Do not automatically retry an ambiguous timeout. | `IMP-001` | Avoids retry-created duplicates but can lose deliveries that the provider did not accept. |
| Which delivery guarantee should retry_delivery enforce after an ambiguous provider timeout? | Keep at-least-once retries and explicitly accept possible duplicates. | `IMP-001` | Maximizes delivery attempts with the least implementation work, but recipients must tolerate and reconcile duplicate side effects. |

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
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py at retry_delivery while preserving its event-facing API and timeout-triggered retry boundary, but do not release the change until the delivery guarantee for an ambiguous provider timeout is selected and the unresolved duplicate-delivery risk is prevented or explicitly accepted. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | An automated test simulates the provider accepting a webhook and then timing out; the selected retry policy produces the documented externally visible outcome and does not silently violate the selected delivery guarantee. | No such test is present in the supplied repository; this criterion remains unmet. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | The retry contract documents whether delivery is at-most-once, at-least-once, or effectively-once with idempotency, including how the same logical event is identified across attempts. | webhook/idempotency.py contains no documented idempotency behavior, so the delivery guarantee is currently unspecified. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The repository does not define an idempotency contract, and no delivery guarantee or duplicate-risk acceptance decision has been supplied. | none | Webhook delivery owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| webhook/delivery.py: retry_delivery and the provider-timeout retry boundary | Direct source inspection shows TIMEOUT_SOURCE = "provider timeout" and retry_delivery(event) returning event. | High for the current local implementation; the requested retry mechanics are not yet specified. |
| webhook/idempotency.py: idempotency contract used by retries | Direct source inspection shows STATUS = "not configured" and no documented idempotency behavior. | High for this repository snapshot; external provider guarantees are unknown. |
| Webhook retry tests and downstream/provider behavior | No test files or additional webhook implementation files were found; the scan frontier reports provider tooling unavailable and fallback-only graph coverage. | Unknown beyond the supplied repository; must be verified before implementation. |
| Graph paths for IMP-001 | PATH-001: webhook/delivery.py → webhook/idempotency.py | PATH-001: provider builtin; confidence lexical; location webhook/delivery.py + webhook/idempotency.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 3777aff647603ab0cb711b130a48f647; sha256 db3313e00e5034b346a5dacd8364d91926d738bedf071d2f578d1468a9411521; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `IMP-001` | `IMP-001` | `AC-001`, `AC-002` | Not ready |
