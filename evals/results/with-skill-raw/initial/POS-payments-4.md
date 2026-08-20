# Requirements impact refinement: automatic retry of failed charges

## Requirement revision

`REQ-001` — Retry a charge automatically when the charge attempt is genuinely failed, while preserving one logical payment and preventing duplicate capture. A provider timeout after capture must be treated as an indeterminate outcome: the system must reconcile the provider result before any retry can create another capture. The payment status shown to the user must remain truthful while webhook settlement is pending.

The phrase “every failed charge” is therefore refined to mean every attempt proven failed by the provider or by a safe reconciliation result, not every client-visible error or timeout.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Link |
|---|---|---|---|---|
| `INV-001` | Charge requests accept an `idempotency_key`; retries must remain within that idempotency boundary. | verified | User-supplied repository fact: “charge requests accept an idempotency_key” | must-preserve `REQ-001` |
| `INV-002` | Payment status is rendered before webhook settlement completes. | verified | User-supplied repository fact: “payment status is rendered before webhook settlement” | must-preserve `REQ-001` |
| `INV-003` | The provider may time out after capture, so a request timeout does not prove that no charge occurred. | verified | User-supplied repository fact: “the provider may time out after capture” | must-preserve `REQ-001` |

## Impact ledger

| ID | Impact | Area | Level | Evidence | State | Links |
|---|---|---|---|---|---|---|
| `IMP-001` | A naive retry after a timeout can create a duplicate capture if the first request captured before timing out. | State/concurrency | verified | `INV-003`; `INV-001` | refining | affects `REQ-001`, `INV-001`, `INV-003`; produces `AC-001` |
| `IMP-002` | Reusing the same idempotency key across the logical charge is required for safe retry semantics; generating a new key per attempt can defeat deduplication. | State/concurrency / interfaces | inferred | `INV-001`; exact key lifecycle is not supplied | refining | affects `REQ-001`, `INV-001`; produces `AC-002` |
| `IMP-003` | The pre-webhook rendered status can falsely appear failed, pending, or successful during retry/reconciliation unless an explicit indeterminate/pending state is preserved. | Functionality / interfaces | verified | `INV-002`, `INV-003` | refining | affects `REQ-001`, `INV-002`; produces `AC-003` |
| `IMP-004` | Automatic retries can continue indefinitely or amplify provider/merchant load without a bounded attempt policy and backoff. | Operations / functionality | inferred | Requirement asks for automatic retry; retry limits and backoff are not supplied | blocked | affects `REQ-001`; produces `AC-004` |
| `IMP-005` | Webhook delivery may race with a retry worker; settlement handling must be idempotent and order-safe. | State/concurrency | inferred | `INV-002`; webhook settlement is supplied, but handler guarantees are not | blocked | affects `REQ-001`, `INV-002`; produces `AC-005` |
| `IMP-006` | A retry policy changes external API traffic, latency, fees, and observability requirements. | Operations / legal-policy | unknown | No provider retry/fee policy, metrics, alerting, or runbook evidence supplied | blocked | affects `REQ-001`; produces `AC-006` |
| `IMP-007` | Existing clients may observe a changed status sequence if a visible failure becomes pending/reconciling and later settles. | Compatibility / interfaces | inferred | `INV-002`; consumer/version compatibility evidence not supplied | detected | affects `REQ-001`, `INV-002`; produces `AC-007` |

## Focused decision needed

The retry trigger and timeout handling need one policy choice before planning:

1. **Conservative reconciliation (recommended):** retry only provider-confirmed failures; keep timeout-after-capture attempts in `pending_reconciliation` until webhook or provider lookup resolves them, then retry only if proven failed.
2. **Bounded optimistic retry:** retry timeouts after a short reconciliation window with the same logical idempotency key, subject to a strict cap; residual duplicate-capture risk remains provider-dependent.
3. **No automatic timeout retry:** automatically retry explicit failures only; route unresolved timeouts to manual or asynchronous reconciliation.

No decision was supplied, so the recommendation is recorded as the refinement baseline rather than as user acceptance.

## Recorded decision

`DEC-001` — Proposed baseline, pending product/provider confirmation: choose option 1, conservative reconciliation. This decision refines `REQ-001` and mitigates `IMP-001`, `IMP-002`, and `IMP-003`; it does not resolve the missing retry-limit, webhook-ordering, provider-policy, or compatibility details.

## Whole-set recalculation

Applying the proposed conservative baseline to all findings:

| ID | Result after `DEC-001` | Rationale |
|---|---|---|
| `IMP-001` | mitigated | Timeout attempts are reconciled before another capture is allowed; duplicate prevention still needs implementation evidence. |
| `IMP-002` | mitigated | One logical charge is retained, but the exact idempotency-key persistence and provider replay behavior remain unverified. |
| `IMP-003` | mitigated | A pending/reconciliation state is required, but status contract and rendering evidence are not supplied. |
| `IMP-004` | blocked | Attempt cap, backoff, and retry window are still unspecified. |
| `IMP-005` | blocked | Webhook/worker idempotency and ordering guarantees are still unspecified. |
| `IMP-006` | blocked | Provider policy, fees, metrics, alerts, and operational controls are unavailable. |
| `IMP-007` | detected | Compatibility impact remains until client-visible status semantics and supported clients are inspected. |

Delta: `IMP-001`–`IMP-003` mitigated; `IMP-004`–`IMP-006` remain blocked; `IMP-007` remains detected; no impact is resolved or accepted. Because `DEC-001` is only a proposed baseline and not a confirmed user choice, it must be confirmed before implementation planning.

## Acceptance and regression criteria

| ID | Criterion | Evidence required |
|---|---|---|
| `AC-001` | A provider timeout after capture never causes a second capture before reconciliation establishes that the original attempt failed. | Deterministic timeout-after-capture test plus provider interaction trace. |
| `AC-002` | All retries for one logical payment preserve the documented idempotency-key behavior and are safe across worker restarts. | Persistence/restart test and provider idempotency contract. |
| `AC-003` | The rendered status cannot claim final failure or success while settlement is indeterminate; webhook settlement transitions it correctly. | Status-state tests covering pre-webhook, timeout, retry, success, and failure. |
| `AC-004` | Automatic retries use an approved maximum attempt count, backoff, and retry window; exhaustion is observable. | Policy decision, worker tests, metrics/alert assertions. |
| `AC-005` | A webhook racing with a retry produces one final payment outcome and no duplicate capture or duplicate settlement. | Race/concurrency test with idempotent webhook processing. |
| `AC-006` | Retry traffic, provider errors, fees, and exhausted attempts are measurable and alertable under the provider’s policy. | Provider agreement plus metric, dashboard, and alert evidence. |
| `AC-007` | Existing clients receive a compatible status contract or an explicitly versioned migration path. | Client/contract compatibility tests and release support matrix. |

## Stop check and planning handoff

The requirement is ready for planning only after the product/provider owner confirms `DEC-001` (or selects another option), and the blocked inputs for `IMP-004`–`IMP-006` plus the compatibility scope for `IMP-007` are supplied. The planning handoff is `REQ-001`, `INV-001`–`INV-003`, the complete impact ledger above, and `AC-001`–`AC-007`.

This artifact intentionally does not provide an implementation plan.
