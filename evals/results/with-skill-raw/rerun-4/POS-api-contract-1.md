# Requirements impact refinement: API field rename

## Requirement revision

`REQ-001` — Rename the public API profile field `displayName` to `name` while preserving the published one-version deprecation promise for the old field. The compatibility behavior for existing iOS readers and cached profile JSON remains part of the requirement; the exact wire and cache transition mechanics are pending a decision.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Link |
| --- | --- | --- | --- | --- |
| `INV-001` | The iOS `UserDTO` decodes the API field `displayName`. | `verified` | Supplied repository evidence: `ios/UserDTO.swift` decodes `displayName`. | `must-preserve` `REQ-001` |
| `INV-002` | Cached profile JSON persists the field under the key `displayName`. | `verified` | Supplied repository evidence: cached profile JSON persists `displayName`. | `must-preserve` `REQ-001` |
| `INV-003` | The public API contract promises a one-version deprecation window for `displayName`. | `verified` | Supplied repository evidence: public API changelog promises one-version deprecation. | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` from the response immediately can break the iOS `UserDTO` decoder. | `verified` | `ios/UserDTO.swift` decodes `displayName`. | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | Renaming only the wire field without a cache compatibility path can make existing cached profiles unreadable or lose the persisted display name. | `verified` | Cached profile JSON persists `displayName`. | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | A change that removes or deprecates `displayName` outside the promised one-version window violates the public API contract. | `verified` | Public API changelog promises one-version deprecation. | `refining` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | Other external consumers may still read `displayName`, and their release/version support is not identified in the supplied evidence. | `inferred` | Public API field and deprecation promise imply consumers beyond the inspected iOS reader; no consumer inventory was supplied. | `blocked` | `affects` `REQ-001`; named gap: consumer inventory and supported-version matrix |
| `IMP-005` | The exact precedence when both `name` and legacy `displayName` are present is unspecified, so inconsistent values could produce divergent profile values across clients or cache writes. | `unknown` | Supplied evidence establishes the old reader/cache key but does not specify dual-field precedence. | `blocked` | `affects` `REQ-001`; named gap: authoritative dual-field precedence rule; `produces` `AC-004` |

## Acceptance criteria

| ID | Criterion | Level | Evidence / verification target | Links |
| --- | --- | --- | --- | --- |
| `AC-001` | Existing iOS payload decoding continues to work throughout the one-version compatibility window, including payloads carrying the legacy field. | `verified` | Exercise `ios/UserDTO.swift` decoding against legacy and transition payload fixtures. | Verifies `INV-001`; produced by `IMP-001` |
| `AC-002` | Existing cached profile JSON containing `displayName` remains readable, and a migration or read/write compatibility rule preserves the profile value when the canonical field becomes `name`. | `verified` | Read/write compatibility tests using cached profile JSON fixtures. | Verifies `INV-002`; produced by `IMP-002` |
| `AC-003` | The public API exposes the new `name` field while retaining the documented `displayName` deprecation behavior for exactly the promised one-version window; removal is not earlier than that window. | `verified` | API contract/changelog compatibility test and versioned response fixtures. | Verifies `INV-003`; produced by `IMP-003` |
| `AC-004` | The selected transition policy defines deterministic precedence for payloads containing both `name` and `displayName`, and tests enforce it. | `unknown` | Requires the pending decision and a dual-field fixture. | Produced by `IMP-005` |

## Focused decision (pending)

Which compatibility shape should the rename use during the one-version window?

1. **Dual-read / dual-write (recommended):** accept both fields, emit both with `name` canonical, and keep cached reads/writes compatible until the window ends.
2. **Dual-read / new-write:** accept both fields, emit and persist only `name`, with a reader fallback for old cached JSON.
3. **Versioned contract split:** expose `name` only in a new API version and leave the old version unchanged for the deprecation window.

No explicit stakeholder selection is recorded, so no concrete `DEC-###` is created. The pending decision must also specify dual-field precedence and the cache rewrite/removal boundary.

## Recorded decision

None. The one-version deprecation promise is a constraint, not a selection of wire, cache, or precedence mechanics.

## Whole-set recalculation

No decision was recorded; all known impacts remain in scope. No finding is superseded. The pending decision must be applied to the complete ledger after selection.

## Delta

- `resolved: none`
- `mitigated: none`
- `unchanged: IMP-001, IMP-002, IMP-003`
- `accepted: none`
- `deferred: none`
- `blocked: IMP-004, IMP-005`
- `new: none`

## Stop check and planning handoff

The refined requirement is ready for a report-only planning handoff, with `IMP-004` blocked on an external consumer/version inventory and `IMP-005` blocked on the pending dual-field precedence decision. Planning must carry `AC-001` through `AC-004`, preserve `INV-001` through `INV-003`, and recalculate the whole ledger after the compatibility choice. No implementation work breakdown is recorded here.
