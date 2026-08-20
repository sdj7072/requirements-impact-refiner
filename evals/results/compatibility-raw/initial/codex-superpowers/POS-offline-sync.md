# Offline edits — reconnect synchronization

## First pass: requirement and impact refinement

### Requirement revision

`REQ-001`: Synchronize edits made while the app is offline when it reconnects, preserving record integrity across concurrent client/server changes, server deletions, and queued local operations. The conflict, tombstone-expiry, and replay-order policy remains the pending decision; no implementation behavior is selected here.

### Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence | Level | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Records carry `updated_at`, the available version/freshness signal for synchronization. | Supplied fact: records carry `updated_at`. | `verified` | `must-preserve` `REQ-001` |
| `INV-002` | Server deletions are represented by tombstones retained for 24 hours. | Supplied fact: server deletions create tombstones for 24 hours. | `verified` | `must-preserve` `REQ-001` |
| `INV-003` | The client queue preserves local creation order, but no stronger cross-device or server ordering guarantee is supplied. | Supplied fact: the client queue preserves local creation order only. | `verified` | `must-preserve` `REQ-001` |

### Initial impact ledger

| ID | Impact | Level | State | Evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Concurrent offline and server edits can overwrite one another if `updated_at` is treated as unconditional last-writer-wins without defining clock skew, equal timestamps, or timestamp authority. | `verified` | `refining` | `INV-001`; timestamp authority and tie-breaking are not supplied. | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | A client reconnecting after the 24-hour tombstone window may miss a deletion and replay a stale update that resurrects the record unless a durable deletion/version check exists. | `verified` | `refining` | `INV-002`; offline duration and retention beyond 24 hours are not supplied. | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | Local creation order alone cannot establish safe global order against server or other-client operations, so conflicting replay can diverge. | `verified` | `refining` | `INV-003`; no global sequence, causal token, or per-record operation version is supplied. | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | User-visible handling of an irreconcilable edit (overwrite, merge, retry, or manual conflict) is unspecified, leaving data-loss and UX expectations unassessable. | `unknown` | `blocked` | No conflict-resolution or notification policy supplied. | `affects` `REQ-001`; `produces` `AC-004` |

### Focused decision requested

Which synchronization policy should govern conflicts, deletions, and replay when the app reconnects?

1. **Server-versioned sync with durable deletion knowledge (recommended):** use a server version/cursor as authority, reject or surface stale writes, preserve deletion knowledge beyond 24 hours, and reconcile local queue order against server versions.
2. **`updated_at` last-writer-wins with bounded offline support:** compare timestamps, define equal-timestamp behavior, and require resnapshot/recovery after the tombstone window.
3. **Conflict-preserving merge/manual review:** use timestamps to detect concurrency, retain both sides where possible, and route unresolved edits to user review.

No decision was recorded in the first pass.

## User decision

The user selected: “Within the tombstone window, server deletion wins; otherwise use the existing timestamps for conflicts and preserve local creation order only when dependencies allow it.”

### Recorded decision

`DEC-001`: Within the tombstone window, server deletion wins; after the window, existing `updated_at` timestamps govern conflicts; local creation order is preserved only when dependencies allow it. This is an explicit user selection and refines `REQ-001`.

## Recalculated requirement

`REQ-001` is refined to: On reconnect, a server deletion wins whenever its 24-hour tombstone is available. Outside that window, resolve record conflicts using the existing `updated_at` timestamps. Replay queued local operations in local creation order only when dependencies permit; otherwise use dependency-safe ordering with the timestamp conflict rule. No durable deletion retention or global ordering guarantee is selected.

`INV-001`–`INV-003` remain unchanged and verified, and remain `must-preserve` by `REQ-001`.

## Whole-set recalculation

| ID | Recalculated impact | Level | State | Evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | `updated_at` is the selected conflict signal outside the tombstone window; clock skew, equal timestamps, and timestamp authority remain validation limits. | `verified` | `mitigated` | `DEC-001` and `INV-001`; no stronger timestamp semantics supplied. | `affects` `REQ-001`, `INV-001`; `mitigated by` `DEC-001`; `produces` `AC-001` |
| `IMP-002` | Server deletion is authoritative while its 24-hour tombstone exists, preventing stale replay during that window; after expiry, absent durable deletion knowledge leaves resurrection possible. | `verified` | `mitigated` | `DEC-001` and `INV-002`; tombstone retention remains 24 hours. | `affects` `REQ-001`, `INV-002`; `mitigated by` `DEC-001`; `produces` `AC-002` |
| `IMP-003` | Local queue order is preserved where dependencies permit it; dependency-constrained operations may use another safe order, so local order is not a global guarantee. | `verified` | `mitigated` | `DEC-001` and `INV-003`; dependency semantics are not supplied. | `affects` `REQ-001`, `INV-003`; `mitigated by` `DEC-001`; `produces` `AC-003` |
| `IMP-004` | The selected rules do not define user-visible handling of an irreconcilable conflict. | `unknown` | `blocked` | `DEC-001` leaves overwrite, merge, retry, and manual-review behavior unspecified. | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | After tombstone expiry, a stale client may resurrect a deleted record because no durable deletion/version check was selected. | `inferred` | `detected` | Inferred from `DEC-001` and `INV-002`: deletion wins only while the tombstone exists. | `affects` `REQ-001`, `INV-002`; `produces` `AC-005` |

## Delta

- `resolved`: none
- `mitigated`: `IMP-001`, `IMP-002`, `IMP-003`
- `unchanged`: none
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`
- `new`: `IMP-005`

The categories are mutually exclusive and exhaustive across `IMP-001`–`IMP-005`. No impact is silently accepted.

## Acceptance and regression criteria

| ID | Future criterion | Evidence / gap |
| --- | --- | --- |
| `AC-001` | Outside the tombstone window, conflicts use `updated_at` consistently, with deterministic handling for equal or invalid timestamps. | Produced by mitigated `IMP-001`; timestamp semantics remain a validation limit. |
| `AC-002` | While a deletion tombstone is within 24 hours, reconnecting clients retain the deletion and do not apply stale updates over it. | Produced by mitigated `IMP-002`; based on `DEC-001` and `INV-002`. |
| `AC-003` | Queued operations preserve local creation order when dependencies permit it and otherwise replay in dependency-safe order. | Produced by mitigated `IMP-003`; dependency semantics remain unspecified. |
| `AC-004` | An irreconcilable edit follows a documented merge, rejection/retry, or manual-review path and is visible to the user as required. | Produced by blocked `IMP-004`; conflict UX is unspecified. |
| `AC-005` | Reconnect after tombstone expiry explicitly prevents, detects, or reports stale resurrection, or documents the residual risk. | Produced by new `IMP-005`; no durable deletion check was selected. |

## Stop check and planning handoff

The selected policy is recorded as `DEC-001`, and the complete impact set has been recalculated. Remaining report-only risks are post-tombstone resurrection (`IMP-005`) and irreconcilable-conflict UX (`IMP-004`). This artifact is ready for a later planning workflow handoff; it contains no implementation tasks, work breakdown, or implementation plan.

**DONE**
