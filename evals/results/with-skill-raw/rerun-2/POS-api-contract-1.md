# Requirements impact refinement: API contract rename

## Requirement revision

`REQ-001` — Rename the public/API profile field `displayName` to `name`, while honoring the public API changelog’s promised one-version deprecation period. The revised requirement must preserve readability of existing payloads and persisted profile data during that period; the exact wire and storage transition remains a pending decision.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | The iOS `UserDTO` currently decodes the field `displayName`. | `verified` | Supplied repository fact: `ios/UserDTO.swift` | `must-preserve` `REQ-001` |
| `INV-002` | Cached profile JSON currently persists the key `displayName`. | `verified` | Supplied repository fact: cached profile JSON | `must-preserve` `REQ-001` |
| `INV-003` | The public API contract promises one-version deprecation for this rename. | `verified` | Supplied repository fact: public API changelog | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Category | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the existing iOS decoder. | Interfaces / compatibility | `verified` | `ios/UserDTO.swift` decodes `displayName` | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | A newly written `name` key alone may make already-cached profile JSON unreadable, or a writer that still emits only `displayName` may fail the renamed contract. | Data / compatibility | `verified` | Cached profile JSON persists `displayName` | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | External API consumers may still send or decode `displayName` during the deprecation window. | Interfaces / compatibility | `inferred` | Public API changelog promises one-version deprecation; external consumer inventory was not supplied | `detected` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | The exact compatibility transition is underspecified: whether the API accepts both names, emits both names, and how cached data is migrated or rewritten is not established by the supplied facts. | Interfaces / data / regression | `unknown` | No transition rule, cache migration rule, or compatibility test was supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |

## Focused decision

The pending decision is the one-version compatibility shape. Which behavior should the implementation contract require during that version?

1. **Dual-read, new-write** — accept `displayName` and `name`; emit only `name`; lazily rewrite cached `displayName` data when read.
2. **Dual-read, dual-write** — accept both names and emit both for one version; remove `displayName` after the window.
3. **Adapter/migration-first** — keep the API transition explicit through a compatibility adapter and perform a separately specified cache migration before `displayName` is removed.

No `DEC-###` is recorded because the supplied request states the deprecation promise but does not select one of these exact transition policies.

## Recorded decision

None. The one-version deprecation promise is a verified constraint (`INV-003`), not a selection among the concrete transition options above. The pending decision must be recorded before an impact can be marked `accepted`.

## Whole-set recalculation

The proposed rename does not supersede any known invariant or impact. Current evidence keeps `IMP-001` and `IMP-002` under refinement, leaves `IMP-003` detected, and blocks `IMP-004` until the transition policy is selected. No additional impact is established from the supplied scope.

## Delta

- `resolved: none`
- `mitigated: none`
- `unchanged: IMP-001, IMP-002, IMP-003` (initial `refining`/`detected` impacts remain open)
- `accepted: none` (no recorded `DEC-###`)
- `deferred: none`
- `blocked: IMP-004` (missing exact API/cache transition policy)
- `new: none`

## Acceptance and regression criteria

| ID | Criterion | Level | Evidence / relationship |
| --- | --- | --- | --- |
| `AC-001` | Existing iOS payload decoding continues to work throughout the promised one-version deprecation window, including payloads containing the legacy field. | `verified` | Verifies `INV-001`; produced by `IMP-001` |
| `AC-002` | Cached profiles persisted with `displayName` remain readable throughout the window, and the selected write/migration behavior is deterministic for subsequent saves. | `verified` | Verifies `INV-002`; produced by `IMP-002` |
| `AC-003` | The public API contract documents and tests the selected handling of both `displayName` and `name` for the complete deprecation version. | `inferred` | Verifies `INV-003`; produced by `IMP-003` |
| `AC-004` | A compatibility test or migration fixture proves the selected API and cache transition, including downgrade/legacy-read behavior and removal timing after one version. | `unknown` | Closes the information gap in `IMP-004`; produced by `IMP-004` |

## Stop check and planning handoff

The requirement is refined to a field rename constrained by a one-version deprecation window. The report links the known iOS and cache invariants, identifies the external-consumer uncertainty, and provides acceptance criteria. Planning may proceed only after the pending compatibility decision is recorded; until then, `IMP-004` is blocked and no impact is accepted or resolved by assumption.
