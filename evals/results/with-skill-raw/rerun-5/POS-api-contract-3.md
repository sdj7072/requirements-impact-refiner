# API contract impact refinement: `displayName` → `name`

## Requirement revision

`REQ-001` — Rename the public profile/API field from `displayName` to `name`, while preserving existing readers and cached profile data for the one-version deprecation window promised by the public API changelog. The revised requirement does not select the wire shape, fallback precedence, or cache rewrite mechanics; those remain the pending decision.

## Current behavior and preserved invariants

`INV-001` — The iOS `UserDTO` decoder currently reads `displayName` and must continue to decode payloads containing that field during the promised compatibility window. (`ios/UserDTO.swift` — `UserDTO` decoding; supplied task fact.)

`INV-002` — Cached profile JSON currently persists `displayName`; existing cached profiles must remain readable during the compatibility window. (Cached profile JSON persistence; supplied task fact.)

`INV-003` — The public API contract includes a one-version deprecation promise for `displayName`; the rename must honor that promise. (Public API changelog; supplied task fact.)

## Impact ledger

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the iOS decoder. | `verified` | `ios/UserDTO.swift` — `UserDTO` decoder; supplied task fact | `refining` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Rewriting/removing the persisted key immediately can make existing cached profile JSON unreadable. | `verified` | Cached profile JSON persistence; supplied task fact | `refining` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | A public contract change without the promised one-version deprecation period violates the published compatibility promise. | `verified` | Public API changelog; supplied task fact | `refining` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | Other external clients or stored payloads may still consume `displayName`; their release/version coverage is not available in the supplied evidence. | `unknown` | No external consumer inventory or compatibility test supplied | `blocked` | affects `REQ-001` |

## Decision needed

Choose the compatibility mechanics for the one-version window:

1. Emit `name` and accept both `name` and legacy `displayName` on reads, with `name` taking precedence; migrate cached data lazily on read/write.
2. Emit both fields for one version and accept both on reads; remove `displayName` after the window.
3. Use a versioned adapter/schema so v1 retains `displayName` and the next version uses `name`, with an explicit cache migration.

No concrete `DEC-###` is recorded because no option has been explicitly selected.

## Recorded decision

Decision needed — the pending decision governs wire compatibility, read precedence, and cache migration timing.

## Whole-set recalculation

No decision was recorded, so all impacts were re-evaluated against `REQ-001` and the preserved invariants. `IMP-001`–`IMP-003` remain material compatibility risks; `IMP-004` remains information-limited.

## Delta

- resolved: none
- mitigated: none
- unchanged: `IMP-001`, `IMP-002`, `IMP-003`
- accepted: none
- deferred: none
- blocked: `IMP-004`
- new: none

## Acceptance criteria and planning handoff

`AC-001` — During the one-version window, an iOS payload containing only legacy `displayName` decodes successfully. (Verifies `INV-001`; produced by `IMP-001`.)

`AC-002` — A profile cached before the rename, with `displayName`, remains readable during the one-version window; any migration behavior follows the selected compatibility mechanics. (Verifies `INV-002`; produced by `IMP-002`.)

`AC-003` — The public API release documents `displayName` as deprecated for exactly the promised one-version window, and removal is not effective before that window closes. (Verifies `INV-003`; produced by `IMP-003`.)

Planning may proceed with the refined requirement, this impact ledger, the pending compatibility decision, the named external-consumer inventory gap, and `AC-001`–`AC-003`. The API wire/read/cache mechanics require the pending decision before implementation planning is finalized.
