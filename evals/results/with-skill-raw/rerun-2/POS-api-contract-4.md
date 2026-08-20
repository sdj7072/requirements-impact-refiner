# API contract impact refinement: `displayName` → `name`

## Requirement revision

`REQ-001` — Rename the public API field `displayName` to `name`, while honoring the public API changelog's promised one-version deprecation period for the old field. The refined requirement preserves existing iOS decoding and cached-profile readability during that compatibility window; the exact wire transition remains a pending decision.

## Current behavior and preserved invariants

`INV-001` — The iOS `UserDTO` currently decodes the `displayName` field. **Evidence level:** verified. **Evidence:** supplied repository fact, `ios/UserDTO.swift` decoding path. **Relationship:** `must-preserve` by `REQ-001`.

`INV-002` — Cached profile JSON currently persists the `displayName` field. **Evidence level:** verified. **Evidence:** supplied repository fact, cached profile JSON persistence. **Relationship:** `must-preserve` by `REQ-001`.

`INV-003` — The public API contract promises one-version deprecation for the old field. **Evidence level:** verified. **Evidence:** supplied repository fact, public API changelog. **Relationship:** `must-preserve` by `REQ-001`.

## Impact ledger

| ID | Category | Finding | Evidence level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Interfaces / compatibility | Removing `displayName` immediately can break the existing iOS decoder. | `verified` | `ios/UserDTO.swift` decoding path | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | Data / compatibility | Renaming the field without a read-compatible transition can make already-cached profile JSON unreadable. | `verified` | Cached profile JSON persistence | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | Compatibility / interfaces | A one-version deprecation promise requires the old field to remain supported for the promised version window; the supplied facts do not specify whether support means dual wire fields, an alias, or another adapter. | `verified` for the promise; `unknown` for the exact mechanism | Public API changelog; no transition semantics supplied | `refining` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | Interfaces / regression | Consumers beyond the supplied iOS decoder may depend on `displayName`; the external-consumer inventory and compatibility coverage are not supplied. | `unknown` | No external consumer inventory or compatibility tests supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |

## Focused decision needed

What wire-level compatibility policy should implement the one-version deprecation?

1. **Dual-field response (recommended):** emit `name` as canonical and continue emitting `displayName` for one version; accept both on input where applicable.
2. **Canonical `name` plus response alias:** emit only `name`, but keep a compatibility reader/adapter for `displayName` during the window.
3. **Immediate wire cutover:** emit and accept only `name`, treating the changelog promise as documentation to revise.

No decision was supplied, so no `DEC-###` is recorded and no impact is marked `accepted`.

## Recorded decision

None. The pending decision is the exact wire-level compatibility policy for the one-version deprecation.

## Whole-set recalculation

Because no decision was recorded, the requirement and all known impacts remain in scope. No impact is superseded; no new impact was identified.

## Delta

- **resolved:** none.
- **mitigated:** none; the compatibility risks are identified but not yet reduced by a selected policy.
- **unchanged:** `IMP-001`, `IMP-002`, `IMP-003` remain `refining`.
- **accepted:** none; no `DEC-###` exists.
- **deferred:** none.
- **blocked:** `IMP-004` — external consumers and compatibility coverage are not supplied.
- **new:** none.

## Acceptance and regression criteria

`AC-001` — During the one-version compatibility window, an existing iOS payload using `displayName` continues to decode successfully. **Evidence basis:** `ios/UserDTO.swift`; verifies `INV-001`; produced by `IMP-001`.

`AC-002` — Cached profile JSON written before the rename remains readable during the compatibility window, and the renamed representation can be read after migration. **Evidence basis:** cached profile JSON persistence; verifies `INV-002`; produced by `IMP-002`.

`AC-003` — The selected wire policy exposes canonical `name` and enforces the public changelog's one-version deprecation semantics for `displayName`, with behavior documented for reads and writes. **Evidence basis:** public API changelog; verifies `INV-003`; produced by `IMP-003`.

`AC-004` — Before removing `displayName`, the supported-consumer inventory and compatibility test coverage are identified, or the gap is explicitly documented. **Evidence basis:** currently unavailable external-consumer inventory/tests; produced by `IMP-004`.

## Stop check and planning handoff

The refined requirement, preserved invariants, impact ledger, open decision, blocked information gap, and acceptance criteria are ready for the planning workflow. Implementation planning should wait for the wire-level compatibility decision and, if available, the external-consumer inventory; no implementation work breakdown is defined here.
