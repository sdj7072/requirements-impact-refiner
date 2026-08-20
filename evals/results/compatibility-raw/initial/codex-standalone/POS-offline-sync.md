# Offline edits — reconnect synchronization

## Requirement revision

`REQ-001`: Synchronize edits made while the app is offline when it reconnects, preserving record integrity across concurrent client/server changes, server deletions, and queued local operations. The conflict, tombstone-expiry, and replay-order policy remains the pending decision; no implementation behavior is selected here.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence | Level | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Records carry `updated_at`, which is the available version/freshness signal for synchronization. | Supplied fact: records carry `updated_at`. | `verified` | `must-preserve` `REQ-001` |
| `INV-002` | Server deletions are represented by tombstones retained for 24 hours. | Supplied fact: server deletions create tombstones 24h. | `verified` | `must-preserve` `REQ-001` |
| `INV-003` | The client queue preserves local creation order, but no stronger cross-device or server ordering guarantee is supplied. | Supplied fact: client queue preserves local creation order only. | `verified` | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | State | Evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Concurrent offline and server edits can overwrite one another if synchronization treats `updated_at` as an unconditional last-writer-wins rule without defining clock skew, equal timestamps, or the authoritative timestamp source. | `verified` | `refining` | `INV-001`; the supplied facts do not define timestamp authority or tie-breaking. | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | An offline client that reconnects after the 24-hour tombstone window may not observe a server deletion and can replay a stale update that resurrects the deleted record unless the sync contract has a durable deletion/version check. | `verified` | `refining` | `INV-002`; offline duration and tombstone retention are not bounded to 24 hours. | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | Local creation order alone cannot establish a safe global order against server operations or edits from another client; replay can therefore produce divergent state when operations conflict. | `verified` | `refining` | `INV-003`; no global sequence, causal token, or per-record operation version is supplied. | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | The required user-visible handling of an irreconcilable edit (automatic overwrite, merge, retry, or manual conflict) is unspecified, so data-loss and UX expectations cannot yet be assessed. | `unknown` | `blocked` | No conflict-resolution or notification policy supplied. | `affects` `REQ-001`; `produces` `AC-004` |

## One focused decision

Which synchronization policy should govern conflicts, deletions, and replay when the app reconnects?

1. **Server-versioned sync with durable deletion knowledge (recommended)** — use a server-issued per-record version or sync cursor as the authority (with `updated_at` retained as metadata), reject or surface stale writes, and retain/query deletion knowledge beyond 24 hours or provide a durable “deleted at/version” check so an old client cannot resurrect a record. Replay local operations in queue order, but reconcile each operation against the server version and define a deterministic tie-breaker for equal versions.
2. **`updated_at` last-writer-wins with bounded offline support** — compare `updated_at` on reconnect, define a deterministic equal-timestamp tie-breaker, and document that clients offline beyond the 24-hour tombstone window may lose edits or require a full resnapshot/re-authentication before replay. This is simpler, but it explicitly limits deletion safety and depends on reliable timestamp semantics.
3. **Conflict-preserving merge/manual review** — use `updated_at` only to detect concurrent changes, retain both sides (field-level merge where safe), and put unresolved edits into a conflict state for user review; require a resnapshot or durable deletion lookup before replaying a client that missed the tombstone. This minimizes silent loss but adds storage, UI, and operational complexity.

Please select one option or specify another policy, including the authoritative version signal, behavior after the 24-hour tombstone window, and treatment of conflicting queued operations. No decision has been recorded.

## Recorded decision

**NEEDS_DECISION** — no `DEC-###` is recorded because no user/stakeholder option has been selected.

## Whole-set recalculation (before decision)

All supplied impacts have been checked against the offline-reconnect requirement. No impact is resolved, mitigated, accepted, deferred, or new before the conflict/deletion/replay decision.

## Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-002`, `IMP-003`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`
- `new`: none

## Stop check and planning handoff

Stopped at the single focused synchronization-policy decision. The refined requirement, preserved invariants, evidence-backed impacts, open information gap, and provisional acceptance criteria are ready for continuation after selection. No implementation tasks, work breakdown, or plan is included.

### Acceptance criteria targets

| ID | Future criterion | Evidence / gap |
| --- | --- | --- |
| `AC-001` | Concurrent edits follow the selected version/conflict policy without silent loss caused by clock skew or equal timestamps. | Produced by `IMP-001`; timestamp authority and conflict policy are not supplied. |
| `AC-002` | A client reconnecting after 24 hours cannot resurrect a server-deleted record without the selected explicit recovery/conflict behavior. | Produced by `IMP-002`; durable deletion lookup/retention policy is not supplied. |
| `AC-003` | Queued operations replay in local creation order while each operation is reconciled against the selected global/version ordering rules. | Produced by `IMP-003`; no global ordering contract is supplied. |
| `AC-004` | An irreconcilable edit follows a documented automatic-merge, rejection/retry, or manual-review path and is visible to the user as required. | Produced by blocked `IMP-004`; product conflict UX is unspecified. |

---

## USER REVISION

I choose: “Within the tombstone window, server deletion wins; otherwise use the existing timestamps for conflicts and preserve local creation order only when dependencies allow it.”

## Second response — recalculation after `DEC-001`

### Requirement revision

`REQ-001` is refined to: On reconnect, a server deletion wins whenever its 24-hour tombstone is still available. Outside that tombstone window, resolve record conflicts using the existing `updated_at` timestamps. Replay queued local operations in local creation order only when their dependencies permit that order; otherwise follow the dependency-safe order and the timestamp conflict rule. No new durable deletion retention or global ordering guarantee is selected.

### Preserved invariants

`INV-001`–`INV-003` remain unchanged and `verified`: records carry `updated_at`; server deletion tombstones last 24 hours; and the client queue preserves local creation order only. They remain `must-preserve` by `REQ-001`.

### Recorded decision

`DEC-001`: The user selected: “Within the tombstone window, server deletion wins; otherwise use the existing timestamps for conflicts and preserve local creation order only when dependencies allow it.”

### Whole-set recalculation

| ID | Recalculated impact | Level | State | Evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Existing `updated_at` timestamps are now the selected conflict signal outside the tombstone window; unresolved clock skew, equal timestamps, and timestamp authority remain validation limits rather than an unselected policy gap. | `verified` | `mitigated` | Explicit `DEC-001` plus `INV-001`; no stronger timestamp semantics were supplied. | `affects` `REQ-001`, `INV-001`; `mitigated by` `DEC-001`; `produces` `AC-001` |
| `IMP-002` | A server deletion is authoritative while its 24-hour tombstone exists, preventing stale offline replay during that window; after expiry, the absence of durable tombstone knowledge leaves resurrection possible under timestamp comparison. | `verified` | `mitigated` | Explicit `DEC-001` plus `INV-002`; tombstone retention remains 24 hours. | `affects` `REQ-001`, `INV-002`; `mitigated by` `DEC-001`; `produces` `AC-002` |
| `IMP-003` | Local queue order is preserved only where dependencies allow it; dependency-constrained operations may use a different safe order, so local order is no longer treated as a global ordering guarantee. | `verified` | `mitigated` | Explicit `DEC-001` plus `INV-003`; dependency graph semantics are not supplied. | `affects` `REQ-001`, `INV-003`; `mitigated by` `DEC-001`; `produces` `AC-003` |
| `IMP-004` | The selected rule defines deletion precedence, timestamp conflict resolution, and dependency-aware replay, but does not define the user-visible handling of an irreconcilable conflict. | `unknown` | `blocked` | `DEC-001` leaves automatic overwrite, merge, retry, and manual-review behavior unspecified. | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | After a tombstone expires, a stale client may resurrect a deleted record because no durable deletion/version check was selected; this is a newly surfaced residual data-integrity risk. | `inferred` | `detected` | Inferred from `DEC-001` plus `INV-002`: deletion wins only while the 24-hour tombstone exists. | `affects` `REQ-001`, `INV-002`; `produces` `AC-005` |

### Delta

- `resolved`: none
- `mitigated`: `IMP-001`, `IMP-002`, `IMP-003`
- `unchanged`: none
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`
- `new`: `IMP-005`

The categories are disjoint and exhaustive across `IMP-001` through `IMP-005`.

### Stop check and planning handoff

The explicit deletion precedence, timestamp conflict, and dependency-aware replay policy is recorded as `DEC-001`. Remaining report-only gaps are irreconcilable-conflict UX (`IMP-004`) and post-tombstone deletion resurrection risk (`IMP-005`). No implementation tasks, work breakdown, plan, or repository edit is included.

### Acceptance criteria targets

| ID | Future criterion | Evidence / gap |
| --- | --- | --- |
| `AC-001` | Outside the tombstone window, conflicting edits use `updated_at` consistently, with deterministic handling for equal or invalid timestamps. | Produced by mitigated `IMP-001`; clock/authority semantics remain validation limits. |
| `AC-002` | While a server deletion tombstone is within 24 hours, reconnecting clients retain the deletion and do not apply a stale update over it. | Produced by mitigated `IMP-002`; based on explicit `DEC-001` and `INV-002`. |
| `AC-003` | Queued operations preserve local creation order when dependencies permit it and otherwise replay in a dependency-safe order. | Produced by mitigated `IMP-003`; dependency semantics remain to be specified. |
| `AC-004` | An irreconcilable edit follows a documented automatic-merge, rejection/retry, or manual-review path and is visible to the user as required. | Produced by blocked `IMP-004`; conflict UX remains unspecified. |
| `AC-005` | Reconnect behavior after tombstone expiry explicitly prevents, detects, or reports stale resurrection, or documents the residual risk. | Produced by new `IMP-005`; no durable deletion check was selected. |
