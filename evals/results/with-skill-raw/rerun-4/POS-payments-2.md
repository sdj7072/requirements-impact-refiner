# POS payments — raw requirements impact refinement

## Requirement revision

`REQ-001` — Retry every failed charge automatically. A charge attempt that is
reported as failed should be retried without manual intervention, while
preserving payment correctness when the provider response is delayed or
ambiguous.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Links |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`; retries must be able to reuse a stable key for the same logical charge. | `verified` | Supplied fact: “charge requests accept idempotency_key” | `must-preserve` `REQ-001` |
| `INV-002` | Payment status can be rendered before webhook settlement arrives. | `verified` | Supplied fact: “payment status rendered before webhook settlement” | `must-preserve` `REQ-001` |
| `INV-003` | The provider may time out after capture, so a timeout does not prove that no charge occurred. | `verified` | Supplied fact: “provider may time out after capture” | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | An automatic retry can duplicate a charge if the first request timed out after capture and the retry uses a different idempotency key. | `verified` | `INV-001`, `INV-003` | `refining` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | A pre-webhook status render can show failure or an intermediate state while the captured payment is still awaiting settlement, causing an incorrect user-visible failure signal. | `verified` | `INV-002`, `INV-003` | `refining` | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | “Failed” is not yet defined as a retryable condition versus an indeterminate/provider-timeout condition; automatic retry policy therefore remains underspecified. | `inferred` | Requirement wording plus `INV-002` and `INV-003` | `detected` | `affects` `REQ-001`; `produces` `AC-003` |
| `IMP-004` | Retry limits, delay/backoff, and the terminal handling of repeated failures are unspecified, so an automatic policy could create unbounded load or leave the payment unresolved. | `unknown` | No retry budget, backoff, or terminal-state policy supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |

## One focused decision

Choose the retry boundary for an ambiguous provider result (especially a
timeout after capture):

1. **Reconcile first (recommended):** reuse the same idempotency key and wait
   for provider/webhook status before permitting another logical attempt.
2. **Immediate retry with the same key:** retry automatically using the stable
   idempotency key, relying on provider idempotency to collapse duplicates.
3. **Do not retry ambiguous results automatically:** retry only explicit,
   non-capture failures and surface timeouts for reconciliation.

No explicit user/stakeholder selection is recorded; this remains the pending
decision. Retry budget and backoff are also pending decisions.

## Recorded decision

None. No concrete `DEC-###` is created without an explicit selection.

## Whole-set recalculation

The complete known impact set remains `IMP-001` through `IMP-004`. No finding is
obsolete, and no new impact is identified from the supplied facts.

## Delta

- `resolved: none`
- `mitigated: none`
- `unchanged: IMP-001, IMP-002, IMP-003`
- `accepted: none`
- `deferred: none`
- `blocked: IMP-004`
- `new: none`

## Stop check and planning handoff

The requirement is refined to require automatic retries without duplicate
charges and with reconciliation-aware status handling. Remaining risks are the
pending retry-boundary decision and the missing retry budget/backoff/terminal
policy; `IMP-004` is blocked on that information. Planning must preserve
`INV-001`–`INV-003` and resolve the pending decision before implementation.

### Acceptance / regression criteria

| ID | Criterion | Level | Evidence / relationship |
| --- | --- | --- | --- |
| `AC-001` | A timeout after capture followed by an automatic retry cannot create two charges for one logical payment; the retry reuses or otherwise honors the same idempotency identity. | `verified` | Derived from `IMP-001`; verifies `INV-001` and `INV-003` |
| `AC-002` | Status rendered before webhook settlement does not permanently present a captured payment as failed; later settlement updates converge to the provider-confirmed state. | `verified` | Derived from `IMP-002`; verifies `INV-002` and `INV-003` |
| `AC-003` | The system classifies explicit failures separately from ambiguous/time-out results and applies the selected retry boundary. | `inferred` | Derived from `IMP-003`; verifies `REQ-001` |
| `AC-004` | Automatic retries have a finite budget, defined backoff, and a terminal state or reconciliation path after exhaustion. | `unknown` | Derived from blocked `IMP-004`; validates the pending policy |
