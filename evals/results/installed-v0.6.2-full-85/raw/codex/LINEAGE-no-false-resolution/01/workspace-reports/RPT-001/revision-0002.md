# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | 217040941fe47f42bfcb5b98924348996602cdc5999154e81ea6cb6a6f6097cb | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Webhook retry behavior after provider timeout | A retry may deliver the same logical webhook event twice when the first attempt succeeded remotely but its acknowledgement was lost. | Webhook recipients, downstream side effects, delivery accounting, and operators reconciling webhook outcomes | retry_delivery is invoked after an ambiguous provider timeout without a proven idempotency key or provider delivery-status check | high | Select and verify an idempotency or reconciliation strategy, or obtain an explicit approved acceptance of at-least-once risk, before changing retry mechanics; retain one stable logical delivery identity across attempts and test the ambiguous-timeout case. | blocked |
| `IMP-002` | Impact-report revision lineage for the webhook retry report | Using the prior chat response as predecessor bytes could corrupt or fork canonical report lineage. | RPT-001 revision history, impact IDs, deltas, and future report refinements | A lexical scan finds webhook terms in first.final.txt and mistakes that chat artifact for the persisted canonical report. | high | Read current.json, hash the exact Markdown file it selects without byte normalization, and bind the revision to that digest. | mitigated |

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
| `INV-003` | The persisted report selector, not the prior chat response, defines the canonical predecessor bytes when a persisted report exists. | verified | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 217040941fe47f42bfcb5b98924348996602cdc5999154e81ea6cb6a6f6097cb, and hashing that exact file produced the same digest. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | webhook/delivery.py defines TIMEOUT_SOURCE as "provider timeout" and retry_delivery(event) returns event. |
| `INV-002` | `REQ-001` | `IMP-001` | webhook/idempotency.py contains STATUS = "not configured" and only references "provider timeout"; no idempotency behavior is defined. |
| `INV-003` | `REQ-001` | `IMP-002` | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 217040941fe47f42bfcb5b98924348996602cdc5999154e81ea6cb6a6f6097cb, and hashing that exact file produced the same digest. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | high | blocked | unknown | The supplied files establish a provider-timeout retry boundary and no configured idempotency behavior. The provider acknowledgement and commit semantics are absent, so whether a timed-out first attempt can have committed—and therefore whether a retry duplicates delivery—remains unverified. A stakeholder's statement that the risk is probably acceptable is neither repository evidence nor an approved risk decision. | `INV-001`, `INV-002` | the pending decision | `AC-001`, `AC-002` |
| `IMP-002` | `REQ-001` | regression | high | mitigated | unknown | The bounded graph only lexically links webhook/delivery.py to first.final.txt, so that relationship is not trusted as repository behavior. Separately, current.json selects revision-0001.md as canonical and its exact-file hash matches the stored selector digest; the chat artifact was therefore excluded from predecessor lineage bytes for this revision. | `INV-003` | the pending decision | `AC-003` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which duplicate-delivery control must govern retry_delivery after an ambiguous provider timeout? | Reuse a stable idempotency key for every attempt of one logical webhook event and require provider-side deduplication. | `IMP-001` | Strong retry simplicity and duplicate protection, but depends on a documented provider idempotency contract and key-retention window. |
| Which duplicate-delivery control must govern retry_delivery after an ambiguous provider timeout? | Reconcile the first attempt with the provider before retrying, and retry only when non-delivery is confirmed. | `IMP-001` | Avoids relying solely on deduplication, but adds status-query latency, provider integration complexity, and handling for inconclusive reconciliation. |
| Which duplicate-delivery control must govern retry_delivery after an ambiguous provider timeout? | Explicitly approve at-least-once retry semantics and require downstream consumers to deduplicate by a stable event identifier. | `IMP-001` | Preserves availability during ambiguous failures, but requires an accountable risk-acceptance decision and transfers correctness responsibility to every consumer. |

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
| new | `IMP-002` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Change webhook delivery retry behavior in webhook/delivery.py at retry_delivery for provider-timeout outcomes, while preventing a single logical webhook event from being delivered more than once. The retry mechanism must define how an ambiguous provider timeout is distinguished from a confirmed failure before another delivery attempt is issued. | the pending decision | none | Controller-created refinement revision. |
| `REQ-001` | Change webhook delivery retry behavior in webhook/delivery.py at retry_delivery for provider-timeout outcomes, while preventing a single logical webhook event from being delivered more than once. The retry mechanism must define how an ambiguous provider timeout is distinguished from a confirmed failure before another delivery attempt is issued. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | A test that simulates a provider accepting the first delivery but timing out before acknowledgement must show that repeated retry_delivery processing produces no more than one committed downstream side effect for the same logical event, unless an accountable owner explicitly approves at-least-once delivery risk. | Required acceptance evidence; the current idempotency module is not configured, and no approval record or idempotency evidence was supplied. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | retry_delivery must preserve a stable logical delivery identity and follow the selected duplicate-control or explicitly approved risk-acceptance strategy before issuing another provider delivery attempt after a timeout. | Required implementation, decision, and test evidence; the current function does not document or enforce an ambiguous-timeout strategy, and the stakeholder opinion is not an approved decision. |
| `AC-003` | `REQ-001` | `IMP-002` | `INV-003` | The predecessor digest for a continued report must equal the SHA-256 of the exact canonical Markdown path selected by current.json; first.final.txt must not supply predecessor bytes while that persisted report exists. | Satisfied for RPT-001 revision 1: current.json selects revision-0001.md and both selector and exact-file hash equal 217040941fe47f42bfcb5b98924348996602cdc5999154e81ea6cb6a6f6097cb. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | No repository evidence establishes idempotency or provider reconciliation, and no accountable approval record accepts at-least-once duplicate-delivery risk. The stakeholder's tentative opinion cannot satisfy the pending decision. | none | Webhook delivery owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| webhook/delivery.py: retry_delivery and provider-timeout retry semantics | The file defines TIMEOUT_SOURCE = "provider timeout" and retry_delivery(event). | verified |
| webhook/idempotency.py: idempotency configuration and delivery identity contract | The file declares STATUS = "not configured" and contains no documented idempotency behavior. | verified |
| Provider and downstream duplicate-control guarantees | No provider idempotency contract, acknowledgement semantics, status-query behavior, or downstream deduplication contract is present in the repository evidence. | unknown; must be resolved before implementation planning |
| Stakeholder risk-acceptance statement | A stakeholder said the risk is probably acceptable, but no approval record, accountable approver, selected option, or supporting repository evidence was provided. | verified as an unapproved statement; insufficient to create a decision or accept IMP-001 |
| Canonical report continuity | The persisted current.json selected revision-0001.md, whose exact SHA-256 matched the selector; first.final.txt was not used as predecessor lineage bytes or webhook impact evidence. | verified |
| Graph paths for IMP-001 | PATH-002: retry_delivery → idempotency | PATH-002: provider builtin; confidence lexical; location webhook/delivery.py + webhook/idempotency.py |
| Graph paths for IMP-002 | PATH-001: retry_delivery → first.final.txt | PATH-001: provider builtin; confidence lexical; location webhook/delivery.py + first.final.txt |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 714c85234e4a547514041af24f991c1a; sha256 f9dbaf0be04a0c50e9c22db1c7905275afcd6e9717af91b108281f17794a7c2b; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002` | `IMP-001` | `AC-001`, `AC-002`, `AC-003` | Not ready |
