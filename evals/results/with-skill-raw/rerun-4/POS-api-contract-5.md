# API contract impact: rename `displayName` to `name`

## Requirement revision

`REQ-001`: Rename the public profile API field from `displayName` to `name`, while preserving the behavior promised by the public API changelog for its one-version deprecation window. `name` is the canonical field for new contract payloads and persisted profile JSON; legacy `displayName` data remains readable only for that compatibility window and is removed at its published boundary.

## Current behavior and preserved invariants

- `INV-001` (`verified`): The iOS `UserDTO` decoder currently reads `displayName`; existing payloads must continue to decode to the same user-visible name during the promised compatibility window. Evidence: supplied repository fact `ios/UserDTO.swift decodes displayName`.
- `INV-002` (`verified`): Cached profile JSON currently persists `displayName`; existing cached profiles must remain readable without profile/name loss during the compatibility window. Evidence: supplied repository fact `cached profile JSON persists displayName`.
- `INV-003` (`verified`): The public API contract includes a one-version deprecation promise for this field migration. Evidence: supplied repository fact `the public API changelog promises one-version deprecation`.

## Impact ledger

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the iOS decoder and lose the profile name. | `verified` | `ios/UserDTO.swift decodes displayName` | `refining` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Renaming the cache key without a legacy read/migration path can make existing cached profiles unreadable or lose their name. | `verified` | `cached profile JSON persists displayName` | `refining` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | A public contract change before the promised window ends would violate the published compatibility commitment. | `verified` | `the public API changelog promises one-version deprecation` | `refining` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | Other clients or integrations may still send or decode `displayName` during the deprecation version. | `inferred` | Public API changelog promise; no external consumer inventory supplied | `detected` | affects `REQ-001`; produces `AC-004` |
| `IMP-005` | The exact release/version boundary for removing the legacy field is not supplied, so post-window behavior cannot yet be assessed precisely. | `unknown` | Changelog promise supplied, but removal version/boundary not supplied | `blocked` | affects `REQ-001`; produces `AC-005` |

## Decision needed

No exact transition mechanics were selected by the request. The pending decision is how the one-version compatibility window is implemented:

1. **Dual-read / single-write (recommended):** read `name`, fall back to `displayName` during the window, and write only `name`; normalize legacy cache data on the next safe save.
2. **Dual-read / dual-write:** read either key and emit both for the window, increasing interoperability but prolonging duplicate contract state.
3. **Immediate cutover:** read and write only `name`, accepting breakage or requiring an external migration before rollout.

## Recorded decision

No `DEC-###` is recorded: the request supplies the deprecation constraint but does not select one of the transition mechanics.

## Whole-set recalculation

The requirement remains refined only by the supplied one-version compatibility constraint. All known impacts were re-evaluated; none is resolved or accepted without an explicit decision and evidence.

## Delta

- resolved: none
- mitigated: none
- unchanged: `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`
- accepted: none
- deferred: none
- blocked: `IMP-005`
- new: none

## Acceptance and regression criteria

- `AC-001` (`verified`): During the compatibility version, an iOS payload containing legacy `displayName` still decodes to the existing user-name value; a payload containing `name` decodes as the canonical value. Evidence: `ios/UserDTO.swift` behavior and `INV-001`; produced by `IMP-001`.
- `AC-002` (`verified`): Existing cached profile JSON containing `displayName` loads without data loss, while newly persisted profile JSON uses `name` as the canonical key. Evidence: cached profile persistence fact and `INV-002`; produced by `IMP-002`.
- `AC-003` (`verified`): The public API documentation/changelog identifies `name` as the replacement, keeps `displayName` supported for exactly one version, and does not remove that support before the promised boundary. Evidence: public API changelog promise and `INV-003`; produced by `IMP-003`.
- `AC-004` (`inferred`): Contract fixtures and supported-consumer checks demonstrate that the legacy key is not required beyond the announced compatibility version. Evidence: external consumer inventory is not supplied; produced by `IMP-004`.
- `AC-005` (`unknown`): The published removal version/boundary is identified before planning post-deprecation removal behavior. Evidence: exact boundary is missing; produced by `IMP-005`.

## Stop check and planning handoff

The refined requirement, preserved invariants, linked impacts, open decision, named information gap, and acceptance criteria are ready for the planning workflow. Planning must first record the pending transition-mechanics choice and obtain the exact published removal boundary; no implementation plan is implied here.
