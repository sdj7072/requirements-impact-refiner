# Requirements Impact Report — POS-payments-5

## Requirement revision

### Original requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | “Retry every failed charge automatically.” | User request |

### Current refined requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Automatically retry a charge only when the charge attempt is retryable and its final capture outcome is not known; reuse the same `idempotency_key` for every retry of the same logical charge, preserve the pre-settlement status semantics, and reconcile webhook settlement before treating the charge as terminal. Backoff, attempt limit, retryable-error set, and terminal user-visible outcomes remain the pending decision. | No decision recorded; pending decision required | — |

## Current behavior and preserved invariants

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`. | `verified` | Supplied fact: “charge requests accept an idempotency_key” |
| `INV-002` | Payment status is rendered before webhook settlement. | `verified` | Supplied fact: “payment status is rendered before webhook settlement” |
| `INV-003` | A provider may time out after capture, so a timeout does not prove that no capture occurred. | `verified` | Supplied fact: “provider may time out after capture” |

### Preserved invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003`, `IMP-004` | Supplied idempotency-key contract |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-005` | Supplied status-rendering order |
| `INV-003` | `REQ-001` | `IMP-001`, `IMP-003`, `IMP-006` | Supplied post-capture-timeout behavior |

## Impact ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | State/concurrency | Critical | `detected` | `verified` | `INV-001` and `INV-003` together show that a retry without the original key can create a second capture after a post-capture timeout. | `INV-001`, `INV-003` | Pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | State/concurrency | High | `detected` | `inferred` | Because status is rendered before webhook settlement, a displayed failure or pending state cannot by itself establish that a provider-side capture did not happen. | `INV-002`, `INV-003` | Pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | Interfaces / state | Critical | `detected` | `verified` | The provider timeout-after-capture case requires an explicit unknown/outcome-reconciliation path; blindly retrying every timeout is unsafe. | `INV-001`, `INV-003` | Pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | Interfaces | High | `detected` | `verified` | Automatic retries must preserve and propagate the logical charge’s `idempotency_key`; otherwise the existing request contract is not sufficient to prevent duplicate effects. | `INV-001` | Pending decision | `AC-004` |
| `IMP-005` | `REQ-001` | Functionality / regression | High | `detected` | `inferred` | The requirement says “every failed charge,” but failure classification is unspecified; retrying validation, authorization, fraud, or permanent provider errors may change current user-visible behavior. | `INV-002` | Pending decision | `AC-005` |
| `IMP-006` | `REQ-001` | Operations | Medium | `blocked` | `unknown` | No retry budget, backoff, attempt cap, queue behavior, observability, or operator stop condition was supplied; retry storms and unbounded work cannot be assessed. | `INV-002`, `INV-003` | Pending decision | `AC-006` |

## One focused decision

Choose the retry policy for a logical charge:

1. **Bounded automatic retry (recommended):** retry only explicitly retryable/transient failures, use exponential backoff with jitter, cap attempts/time, and route ambiguous post-timeout outcomes to idempotent reconciliation before any further capture attempt.
2. **Aggressive automatic retry:** retry all provider-reported failures, including timeouts, with the same idempotency key; this maximizes automatic recovery but requires provider support for key retention and still needs a bounded retry budget.
3. **Conservative recovery:** automatically retry only failures confirmed before provider submission; treat post-submission timeouts as pending and reconcile through webhook/provider lookup without an automatic new charge attempt.

**Recorded decision:** none. The user supplied the requirement and three facts, but did not select a retry policy, retryable-error set, attempt limit, backoff, or terminal status behavior. Therefore no `DEC-###` is created and no impact is marked `accepted`.

## Whole-set recalculation

No decision was recorded, so no impact is resolved, mitigated, accepted, deferred, or superseded by a selected policy. The complete current set is retained:

- `unchanged`: `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005` (initially detected; still require the pending decision).
- `blocked`: `IMP-006` (the operational retry budget and controls are not supplied).
- `resolved`: none.
- `mitigated`: none.
- `accepted`: none.
- `deferred`: none.
- `new`: none.

## Acceptance and regression criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001`, `INV-003` | A provider timeout after capture followed by retry results in at most one capture for the logical charge. | Idempotency/replay test with capture-then-timeout provider stub |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | A pre-webhook rendered status is not used as proof that no provider capture occurred; webhook settlement can advance the payment to its authoritative state. | Status-before-webhook integration test |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | Post-submission timeout enters the specified pending/reconciliation path and does not create an unkeyed second attempt. | Timeout-after-capture scenario test |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-001` | Every retry of one logical charge carries the original `idempotency_key`, and a new user-initiated charge gets a distinct key. | Request-contract and retry propagation test |
| `AC-005` | `REQ-001` | `IMP-005` | `INV-002` | Only the selected retryable failure classes retry automatically; permanent failures remain terminal with the selected user-visible status. | Error-classification matrix test |
| `AC-006` | `REQ-001` | `IMP-006` | `INV-002`, `INV-003` | Retry attempts obey the selected backoff, cap, queue, cancellation, logging, metric, and alert controls. | Retry-budget and operational-observability test |

## Requirement revision history

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Initial refinement: bounded/semantically safe automatic retries are required, with idempotency-key reuse and settlement reconciliation; exact policy is open. | No decision recorded | None | `IMP-001`–`IMP-005` unchanged; `IMP-006` blocked; new: none |

## Unresolved, deferred, and blocked items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | `detected` | Need selected policy confirming same-key retry and duplicate-capture behavior. | Pending decision | Product/payment owner |
| `IMP-002` | `detected` | Need authoritative rule for status while webhook settlement is outstanding. | Pending decision | Product/payment owner |
| `IMP-003` | `detected` | Need explicit handling of post-capture timeout and reconciliation source. | Pending decision | Payment integration owner |
| `IMP-004` | `detected` | Need contract rule for key lifetime and propagation across queued retries. | Pending decision | Payment integration owner |
| `IMP-005` | `detected` | Need retryable error taxonomy and terminal outcomes. | Pending decision | Product/payment owner |
| `IMP-006` | `blocked` | Retry budget, backoff, cap, cancellation, and observability requirements are absent. | Pending decision | Operations owner |

## Analysis scope and limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Supplied facts only; no repository, provider documentation, schema, webhook contract, or tests were supplied or inspected. | Three user-supplied facts listed as `INV-001`–`INV-003`. | Those three facts are verified as supplied; all implementation, provider-retention, error-taxonomy, and operational claims beyond them are inferred or unknown. |

## Stop check and planning handoff

The impact review stops at a report-only handoff. The refined requirement is not implementation-ready until the single retry-policy decision is recorded; no implementation work breakdown is created. Once the pending decision is selected, recalculate the complete impact set and create the corresponding `DEC-###` links before planning.

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: safely retry eligible failed logical charges with idempotency-key reuse and webhook-aware settlement reconciliation; exact policy pending. | `INV-001`–`INV-003`, `IMP-001`–`IMP-006` | Duplicate capture, ambiguous post-timeout outcome, premature status interpretation, incorrect retry classification, and unbounded retries. | `AC-001`–`AC-006` | Pending retry-policy decision, then requirements-impact-refiner handoff to the planning workflow |
