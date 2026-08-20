# POS payments — raw requirements impact refinement

## Requirement revision

`REQ-001` — Retry every failed charge automatically. A retry remains part of
the same logical charge and must preserve payment correctness while provider
completion may arrive asynchronously. The supplied requirement does not yet
select the retry boundary, attempt budget, or terminal behavior.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Links |
| --- | --- | --- | --- | --- |
| `INV-001` | Charge requests accept an `idempotency_key`; retries must retain a stable identity for the same logical charge. | `verified` | Supplied fact: “charge requests accept idempotency_key” | `must-preserve` `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement arrives. | `verified` | Supplied fact: “payment status rendered before webhook settlement” | `must-preserve` `REQ-001` |
| `INV-003` | The provider may time out after capture, so a timeout does not establish that no charge occurred. | `verified` | Supplied fact: “provider may time out after capture” | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | An automatic retry after a timeout that followed capture can create a duplicate charge if it is treated as a new logical charge or uses a different idempotency identity. | `verified` | `INV-001`, `INV-003` | `refining` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-001` |
| `IMP-002` | Status rendered before webhook settlement can present a captured-but-unsettled payment as failed or final, prompting an unsafe retry or misleading the customer. | `verified` | `INV-002`, `INV-003` | `refining` | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | The phrase “failed charge” does not identify whether ambiguous/provider-timeout results are retryable, so the automatic retry boundary is underspecified. | `inferred` | Requirement wording plus `INV-002` and `INV-003` | `detected` | `affects` `REQ-001`; `produces` `AC-003` |
| `IMP-004` | Attempt limits, delay/backoff, and terminal handling are not supplied; automatic retries could be unbounded or leave a charge unresolved after repeated failures. | `unknown` | No retry budget, backoff, or terminal-state policy supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |

## One focused decision

Choose the retry boundary for an ambiguous provider result, especially a
timeout that may have occurred after capture:

1. **Reconcile before retry (recommended):** keep the logical charge’s stable
   idempotency identity and wait for provider/webhook status before authorizing
   another attempt.
2. **Retry immediately with the same key:** automatically resend using the
   stable idempotency key and rely on provider idempotency to collapse a
   duplicate request.
3. **Do not auto-retry ambiguous results:** retry only explicit non-capture
   failures; route timeouts to reconciliation.

No option is selected in the supplied request; this remains the pending
decision. Retry budget, backoff, and exhaustion behavior are also pending
policy decisions.

## Recorded decision

None. No concrete `DEC-###` is created without an explicit user/stakeholder
selection.

## Whole-set recalculation

The complete known impact set remains `IMP-001` through `IMP-004`. No finding
is obsolete and no new impact is identified from the supplied facts. Silence
does not resolve or accept an impact.

## Delta

- `resolved: none`
- `mitigated: none`
- `unchanged: IMP-001, IMP-002, IMP-003`
- `accepted: none`
- `deferred: none`
- `blocked: IMP-004`
- `new: none`

## Stop check and planning handoff

`REQ-001` is refined to require automatic retries without duplicate charges
and with settlement-aware status handling. Planning must preserve
`INV-001`–`INV-003`, classify explicit versus ambiguous failures, and resolve
the pending retry-boundary and retry-budget policies. `IMP-004` remains
blocked on the missing budget/backoff/terminal information.

### Acceptance / regression criteria

| ID | Criterion | Level | Evidence / relationship |
| --- | --- | --- | --- |
| `AC-001` | A timeout after capture followed by an automatic retry cannot create two charges for one logical payment; the retry uses the stable idempotency identity or an equivalent provider-supported deduplication guarantee. | `verified` | Derived from `IMP-001`; verifies `INV-001` and `INV-003` |
| `AC-002` | Before webhook settlement, the UI does not permanently present a captured payment as failed; later provider/webhook settlement converges the rendered status to the confirmed outcome. | `verified` | Derived from `IMP-002`; verifies `INV-002` and `INV-003` |
| `AC-003` | Explicit failures and ambiguous/time-out results are classified separately, and each class follows the selected retry boundary. | `inferred` | Derived from `IMP-003`; verifies `REQ-001` |
| `AC-004` | Automatic retries have a finite or otherwise explicitly bounded safety policy, defined backoff, and a terminal state or reconciliation path after exhaustion. | `unknown` | Derived from blocked `IMP-004`; validates the pending policy |

This is a report-only planning handoff; it contains no implementation work
breakdown.
