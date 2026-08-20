# POS — API contract rename: `displayName` → `name`

## Requirement revision

`REQ-001` — Rename the public user/profile API field from `displayName` to `name`, while honoring the published one-version deprecation promise and preserving reads of already-cached profile payloads during that window. The exact wire and persistence transition remains the pending decision.

## Current behavior and preserved invariants

`INV-001` — The iOS `UserDTO` decoder currently reads `displayName`; existing payloads using that key must remain decodable through the promised compatibility window. **verified** — `ios/UserDTO.swift — UserDTO` decoding path (supplied repository fact).

`INV-002` — Cached profile JSON currently persists `displayName`; profiles already stored under that key must remain readable through the promised compatibility window. **verified** — cached profile JSON persistence (supplied repository fact).

`INV-003` — The public API contract includes a one-version deprecation promise for `displayName`; the rename must not shorten that promised window. **verified** — public API changelog (supplied repository fact).

## Impact ledger

| ID | Finding | Evidence level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the iOS decoder. | `verified` | `ios/UserDTO.swift — UserDTO` decoding path | `refining` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Rewriting or invalidating cached profile JSON immediately can make existing cached profiles unreadable. | `verified` | cached profile JSON persistence | `refining` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | A direct contract cutover would violate the public one-version deprecation promise. | `verified` | public API changelog | `refining` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | Other clients or integrations may still send or decode `displayName`, and their release/support state is not supplied. | `inferred` | public API field and published compatibility promise; external consumer inventory unavailable | `blocked` | affects `REQ-001`; produces `AC-004` |

`AC-001` — During the one-version compatibility window, an iOS payload containing `displayName` decodes successfully; the renamed representation is also covered by the selected contract transition. **verified criterion derived from** `IMP-001`.

`AC-002` — A cached profile JSON document persisted with `displayName` remains readable during the compatibility window, with no loss of the profile value. **verified criterion derived from** `IMP-002`.

`AC-003` — The public API exposes and documents the `displayName` deprecation for at least the promised one version before removing it, and the `name` field is available according to the selected transition. **verified criterion derived from** `IMP-003`.

`AC-004` — The compatibility behavior for external clients is validated against an identified consumer/support inventory, or the gap is explicitly retained as blocked. **inferred criterion derived from** `IMP-004`.

## One focused decision

Choose the transition mechanics for the one-version deprecation window:

1. **Dual-read/dual-write (recommended)** — accept and emit both keys during the window, prefer `name`, then remove `displayName` in the next version.
2. **Dual-read/single-write** — accept both keys, emit only `name`, and retain a compatibility reader for the window.
3. **Versioned contract split** — expose `name` in a new API version and keep the old version on `displayName` for the window.

No explicit stakeholder selection was supplied. The pending decision must be recorded before assigning a concrete `DEC-###`.

## Recorded decision

None. The one-version deprecation constraint and the observed readers/writers do not select a transition mechanic. The pending decision remains open.

## Whole-set recalculation

No decision was recorded; all known impacts were re-evaluated against `REQ-001` and the preserved invariants. No impact is resolved or accepted by silence.

### Delta

- resolved: none
- mitigated: none
- unchanged: `IMP-001`, `IMP-002`, `IMP-003`
- accepted: none
- deferred: none
- blocked: `IMP-004` — external consumer/support inventory is unavailable
- new: none

## Stop check and planning handoff

The refined requirement is ready for planning as a report-only handoff, subject to the pending transition decision and the named external-consumer information gap. The planning workflow must preserve `INV-001`–`INV-003` and verify `AC-001`–`AC-004`; this artifact does not prescribe an implementation work breakdown.
