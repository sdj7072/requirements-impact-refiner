# POS payments — requirements impact refinement

## Requirement revision

`REQ-001` — A failed charge attempt must be retried automatically until the system can determine a terminal payment outcome, while preventing duplicate capture and keeping the customer-visible status consistent with provider settlement. The requirement is intentionally refined from “Retry every failed charge automatically”: a failure is not necessarily safe to retry when the provider may have captured the payment but the response timed out.

## Current behavior and preserved invariants

The supplied facts establish these current contracts:

- `INV-001` — Charge requests accept an `idempotency_key`; retries must reuse the key for the same logical charge. (`verified`, supplied fact: “charge requests accept an idempotency_key”)
- `INV-002` — Payment status can be rendered before webhook settlement is received. (`verified`, supplied fact: “payment status is rendered before webhook settlement”)
- `INV-003` — The provider may time out after capture, so a timed-out response does not prove that no charge occurred. (`verified`, supplied fact: “provider may time out after capture”)

## Impact ledger

| ID | Impact | Evidence | Level | State | Links |
|---|---|---|---|---|---|
| `IMP-001` | Blindly issuing a new charge after a failure can double-capture a customer when the provider timed out after capture. | `INV-001`, `INV-003` | `verified` | `refining` | affects `REQ-001`, `INV-001`, `INV-003`; produces `AC-001` |
| `IMP-002` | Automatic retries need a bounded policy (attempt count, delay/backoff, and terminal conditions); “every failed” does not define one. | `REQ-001`; no retry policy supplied | `unknown` | `blocked` | affects `REQ-001`; produces `AC-002` |
| `IMP-003` | Rendering a failure before webhook settlement can expose a false failure while a captured payment is still settling. | `INV-002`, `INV-003` | `verified` | `refining` | affects `REQ-001`, `INV-002`, `INV-003`; produces `AC-003` |
| `IMP-004` | Retrying after a timeout requires reconciliation or provider-status lookup so the system can distinguish pending, captured, declined, and unknown outcomes. | `INV-003`; no reconciliation contract supplied | `inferred` | `detected` | affects `REQ-001`, `INV-003`; produces `AC-004` |
| `IMP-005` | Repeated attempts and late webhooks must converge on one payment record and preserve auditability; the supplied facts do not establish webhook deduplication or ordering behavior. | `INV-001`–`INV-003`; webhook deduplication/ordering not supplied | `unknown` | `blocked` | affects `REQ-001`, `INV-002`; produces `AC-005` |
| `IMP-006` | Automatic retries can increase provider traffic, customer notifications, and operational load; no metrics, alerts, or rollout controls are supplied. | `REQ-001`; operational controls not supplied | `unknown` | `blocked` | affects `REQ-001`; produces `AC-006` |
| `IMP-007` | Existing callers that interpret an immediate failed status may observe a new pending/retrying state and need a compatible contract. | `INV-002`; consumer compatibility not supplied | `inferred` | `detected` | affects `REQ-001`, `INV-002`; produces `AC-007` |

## One focused decision

What should the retry policy do when a charge response fails or times out and capture status is not yet known?

1. **Reconcile-then-retry (recommended):** reuse the same `idempotency_key`, query or await provider status/webhook, retry only after a confirmed non-captureable failure, and expose `pending` while outcome is unknown.
2. **Bounded retry with pending fallback:** reuse the key and retry a fixed number of times; if status remains unknown, stop retrying and retain `pending/unknown` for reconciliation.
3. **Immediate automatic retry:** reuse the key and retry all failures immediately; this preserves the literal wording but retains higher latency/load and provider-contract risk.

No stakeholder selection is recorded yet; the decision remains pending.

## Recorded decision

No `DEC-###` is recorded because no option was selected. Therefore no impact is marked `accepted`.

## Whole-set recalculation

No decision was supplied, so the requirement remains `REQ-001` and all impacts remain in scope. The complete delta is:

- `resolved: none`
- `mitigated: none`
- `unchanged: IMP-001, IMP-003, IMP-004, IMP-005, IMP-006, IMP-007` (still `refining` or `detected`)
- `accepted: none`
- `deferred: none`
- `blocked: IMP-002, IMP-005, IMP-006`
- `new: none`

## Acceptance and regression criteria

- `AC-001` — A retry of the same logical charge reuses the original `idempotency_key` and cannot create a second capture when the first attempt captured before timing out.
- `AC-002` — The selected policy specifies maximum attempts, delay/backoff, and terminal conditions for declined, rejected, pending, and unknown outcomes.
- `AC-003` — Before webhook settlement, the customer-visible state is not presented as a definitive failure when provider outcome is unknown; it is an explicitly defined pending/retrying state.
- `AC-004` — A provider timeout after capture is reconciled to the single payment record, with captured/settled status applied when evidence arrives.
- `AC-005` — Duplicate or late webhooks and retry responses converge idempotently on one payment record and retain an auditable attempt history.
- `AC-006` — Retry counts, outcomes, and exhaustion are observable, and operational safeguards exist for retry storms or provider degradation.
- `AC-007` — Existing consumers either continue to handle the status contract or receive a documented compatibility transition for the new pending/retrying state.

## Stop check and planning handoff

The report is ready for the selected planning workflow once the pending retry-policy decision and the blocked provider/webhook/operations contract gaps are resolved. The handoff consists of `REQ-001`, preserved invariants `INV-001`–`INV-003`, impacts `IMP-001`–`IMP-007`, and acceptance criteria `AC-001`–`AC-007`. This is a report-only refinement; no implementation work breakdown is created.
