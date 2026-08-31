# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Webhook delivery retry behavior after provider timeout | The same webhook event may be delivered more than once when the first provider attempt succeeded but its response timed out. | Webhook consumers and any non-idempotent downstream side effects triggered by retry_delivery. | An ambiguous provider timeout followed by retry_delivery, especially overlapping or repeated retry attempts. | high | Select and document an idempotency policy before implementation, then enforce a stable attempt identity or explicitly accept at-least-once duplicates and verify the chosen concurrency behavior. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for changing webhook delivery retries at webhook/delivery.py and retry_delivery. The supplied evidence identifies an unresolved duplicate-delivery risk. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py for retry_delivery after a provider timeout, but do not enable a retry path until the delivery idempotency contract is selected and specified. The selected contract must define how an ambiguous provider timeout is distinguished from a failed delivery, how repeated attempts are identified, and what duplicate side effects are permitted or prevented. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | retry_delivery is the webhook retry boundary associated with a provider timeout and currently returns the supplied event unchanged. | verified | webhook/delivery.py:1-4 defines TIMEOUT_SOURCE as provider timeout and retry_delivery(event) returning event. |
| `INV-002` | No configured or documented idempotency behavior currently protects repeated webhook delivery attempts. | verified | webhook/idempotency.py:1-2 contains only STATUS = not configured and DELIVERY_REF = provider timeout; no idempotency key, deduplication store, retention window, or concurrency semantics are defined. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | webhook/delivery.py:1-4 defines TIMEOUT_SOURCE as provider timeout and retry_delivery(event) returning event. |
| `INV-002` | `REQ-001` | `IMP-001` | webhook/idempotency.py:1-2 contains only STATUS = not configured and DELIVERY_REF = provider timeout; no idempotency key, deduplication store, retention window, or concurrency semantics are defined. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | high | blocked | unknown | A provider timeout is an ambiguous outcome: the provider may have accepted the webhook before the caller retries. retry_delivery is linked to that timeout boundary, while webhook/idempotency.py documents no configured protection. Repository scan PATH-001 connects webhook/delivery.py to webhook/idempotency.py, but the configured provider was unavailable and built-in lexical/structural fallback evidence cannot establish runtime duplicate behavior. | `INV-001`, `INV-002` | the pending decision | `AC-001`, `AC-002`, `AC-003` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| What duplicate-delivery contract should retry_delivery enforce after an ambiguous provider timeout? | Require a stable event idempotency key and suppress or coalesce duplicate attempts. | `IMP-001` | Prevents duplicate side effects but requires a durable deduplication record, atomic concurrency semantics, and a defined retention window. |
| What duplicate-delivery contract should retry_delivery enforce after an ambiguous provider timeout? | Keep at-least-once delivery and explicitly allow duplicates. | `IMP-001` | Keeps retry handling simpler, but pushes idempotency onto every webhook consumer and leaves duplicate side effects as an accepted operational risk. |
| What duplicate-delivery contract should retry_delivery enforce after an ambiguous provider timeout? | Do not automatically retry ambiguous provider timeouts. | `IMP-001` | Avoids timeout-driven duplicates, but may lose deliveries when the provider did not accept the first attempt and requires reconciliation or manual recovery. |

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
| `REQ-001` | Change webhook retry behavior in webhook/delivery.py for retry_delivery after a provider timeout, but do not enable a retry path until the delivery idempotency contract is selected and specified. The selected contract must define how an ambiguous provider timeout is distinguished from a failed delivery, how repeated attempts are identified, and what duplicate side effects are permitted or prevented. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | The retry contract documents whether delivery is at-most-once or at-least-once, identifies the idempotency key source, defines deduplication persistence and retention when applicable, and assigns ownership for downstream duplicate handling. | Required to resolve the documented absence of idempotency behavior in webhook/idempotency.py. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | Automated verification covers both ambiguous timeout outcomes: the provider accepted the first attempt before timeout, and the provider did not accept it; observed delivery counts match the selected contract. | The change is specifically at retry_delivery after provider timeout, where success cannot be inferred from the timeout alone. |
| `AC-003` | `REQ-001` | `IMP-001` | `INV-002` | Automated verification covers simultaneous retry_delivery calls for the same event and demonstrates the selected duplicate-delivery contract under concurrency. | Without an atomic idempotency rule, overlapping attempts can bypass a check-then-record implementation. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The repository and supplied evidence do not define whether duplicates must be prevented, tolerated, or avoided by disabling automatic retry. Those choices lead to materially different retry and storage behavior. | none | Webhook delivery owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| webhook/delivery.py: retry_delivery and provider-timeout retry behavior | The supplied evidence names this function and file; direct inspection confirms retry_delivery at lines 3-4 and the timeout source at line 1. | high |
| webhook/idempotency.py: idempotency contract and duplicate suppression boundary | The supplied evidence names this file; direct inspection shows idempotency is not configured and no behavior is documented. | high |
| Provider and webhook-consumer side effects after an ambiguous timeout | The timeout-to-idempotency path is structurally inferred by repository scan PATH-001, but no provider adapter, persistence implementation, consumer contract, or tests are present in the inspected repository. | unknown; configured provider was unavailable and runtime behavior is not evidenced |
| Graph paths for IMP-001 | PATH-001: webhook/delivery.py → webhook/idempotency.py | PATH-001: provider builtin; confidence lexical; location webhook/delivery.py + webhook/idempotency.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 4ff37b9c72927ac43c202fd5a3ba918d; sha256 0b56f51128e561f79dee62ece21f79ccdc3e40ddd2e3d7ff01d68caa1c88b789; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `IMP-001` | `IMP-001` | `AC-001`, `AC-002`, `AC-003` | Not ready |
