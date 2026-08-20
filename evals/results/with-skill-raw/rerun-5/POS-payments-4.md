# Requirements Impact Report

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Retry every failed charge automatically. | User request |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Retry every failed charge automatically, while preserving the supplied idempotency-key contract and accounting for payment status being rendered before webhook settlement. Provider timeouts that may occur after capture remain an explicitly pending outcome to define. | the pending decision | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`. | `verified` | Supplied fact: “charge requests accept idempotency_key” |
| `INV-002` | Payment status can be rendered before webhook settlement. | `verified` | Supplied fact: “payment status rendered before webhook settlement” |
| `INV-003` | A provider may time out after capture, leaving the capture outcome ambiguous to the caller. | `verified` | Supplied fact: “provider may time out after capture” |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002` | Supplied idempotency-key contract |
| `INV-002` | `REQ-001` | `IMP-003` | Supplied pre-webhook status rendering behavior |
| `INV-003` | `REQ-001` | `IMP-001`, `IMP-004` | Supplied post-capture timeout behavior |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | State/concurrency | critical | refining | `verified` | The provider may time out after capture; the supplied request contract accepts `idempotency_key`. | `INV-001`, `INV-003` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | State/concurrency | high | refining | `verified` | Automatic retry changes the number and timing of charge attempts; idempotency is available as a request field. | `INV-001` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | Functionality/interface | high | detected | `verified` | Payment status is rendered before webhook settlement. | `INV-002` | — | `AC-003` |
| `IMP-004` | `REQ-001` | Operations/state | high | detected | `unknown` | No supplied evidence defines retry limits, backoff, reconciliation, observability, or terminal handling after an ambiguous timeout. | `INV-003` | the pending decision | `AC-004` |

## Decision Needed

How should an automatic retry treat a provider timeout that may have happened after capture?

1. Retry with the same idempotency key and a bounded retry/reconciliation policy, so a captured charge is not duplicated while the result is recovered.
2. Do not automatically retry ambiguous timeouts; retry only responses known to be pre-capture failures and route timeouts to reconciliation/manual handling.
3. Retry ambiguous timeouts with a newly generated key (higher availability, but duplicate capture risk).

No option has been selected, so no concrete `DEC-###` is recorded and no impact is accepted.

## Decisions and Accepted Risks

No recorded decision. The pending decision above is required before retry behavior for ambiguous post-capture timeouts can be treated as accepted or resolved.

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Initial refinement retains the automatic-retry request and supplied constraints; timeout semantics remain pending. | the pending decision | none | `resolved: none`; `mitigated: none`; `unchanged: IMP-001, IMP-002, IMP-003, IMP-004`; `accepted: none`; `deferred: none`; `blocked: none`; `new: none` |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001`, `INV-003` | A retry after a provider timeout that may follow capture cannot create a second charge for the same logical payment; the eventual payment result is recoverable. | Validation gap: timeout-after-capture test with repeated request and the selected idempotency/reconciliation policy. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-001` | Every response classified as a failed charge is retried automatically according to the selected retry policy, and attempts remain attributable to one logical payment. | Validation gap: automatic-retry test covering retry count, idempotency key handling, and terminal failure. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-002` | A status rendered before webhook settlement is not treated as final solely because the automatic retry path observed an intermediate failure; later settlement updates the displayed result consistently. | Validation gap: pre-webhook status/rendering test followed by settlement webhook. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-003` | Retry limits, backoff, timeout reconciliation, terminal state, and operational signals are explicit and observable once the pending timeout choice is selected. | Validation gap: policy/configuration and observability checks; no supplied implementation evidence. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | `refining` | Timeout may follow capture; exact duplicate-prevention and result-recovery behavior is not selected. | the pending decision | Product/payment owner |
| `IMP-002` | `refining` | Automatic retry limits and classification of retryable failures are unspecified. | the pending decision | Product/payment owner |
| `IMP-004` | `detected` | No evidence specifies retry budget, backoff, reconciliation, terminal handling, or telemetry. | the pending decision | Payment/platform owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Supplied payment facts only; no repository or integration implementation was inspected. | User-provided facts about `idempotency_key`, pre-webhook rendering, and post-capture timeout. | Current invariants are verified from the supplied facts, but implementation-specific retry, webhook, persistence, and operations impacts remain unverified; `IMP-004` is unknown. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `INV-001`–`INV-003`, `IMP-001`–`IMP-004`; no `DEC-###` yet | Duplicate capture or unrecoverable payment state if timeout-after-capture semantics are left unspecified; premature status may mislead users. | `AC-001`–`AC-004` | Requirements refinement stops pending one explicit choice above; after selection, recalculate the whole impact set before implementation planning. |
