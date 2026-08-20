# API contract impact refinement

## Requirement revision

`REQ-001` — Rename the public user-profile field from `displayName` to `name`, while honoring the published one-version deprecation promise for `displayName`. During that compatibility window, existing clients and persisted profile payloads must remain readable; the new contract should make `name` canonical. After the window, removal of `displayName` may proceed only through the separately planned compatibility release.

## Current behavior and preserved invariants

| ID | Current behavior to preserve | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | The iOS user DTO decodes the `displayName` response key. | `verified` | Supplied repository fact: `ios/UserDTO.swift` decodes `displayName`. | `must-preserve` `REQ-001` |
| `INV-002` | Cached profile JSON persists the `displayName` key. | `verified` | Supplied repository fact: cached profile JSON persists `displayName`. | `must-preserve` `REQ-001` |
| `INV-003` | The public API changelog promises one-version deprecation for `displayName`. | `verified` | Supplied repository fact: public API changelog commitment. | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately would break the existing iOS decoder. | `verified` | `ios/UserDTO.swift` decodes `displayName`. | `mitigated` | `affects` `REQ-001`, `INV-001`; `mitigated by` `DEC-001`; `produces` `AC-001` |
| `IMP-002` | Changing the persisted cache key immediately would make existing cached profiles unreadable or require a cache reset. | `verified` | Cached profile JSON persists `displayName`. | `mitigated` | `affects` `REQ-001`, `INV-002`; `mitigated by` `DEC-001`; `produces` `AC-002` |
| `IMP-003` | A breaking removal before the promised release window would violate the public compatibility commitment. | `verified` | Public API changelog promises one-version deprecation. | `mitigated` | `affects` `REQ-001`, `INV-003`; `mitigated by` `DEC-001`; `produces` `AC-003` |
| `IMP-004` | The exact server serializer/schema and the release version that starts and ends the window are not supplied, so the authoritative response shape and cutoff cannot be verified here. | `unknown` | Only the supplied iOS, cache, and changelog facts were inspected; server contract and version metadata were unavailable. | `blocked` | `affects` `REQ-001`; named information gap: server serializer/schema and release identifiers |

## Focused decision

The contract needs an explicit compatibility shape. The available options are:

1. `DEC-001` (selected): emit canonical `name` and retain `displayName` as a deprecated alias for one version; accept/read both keys in clients and cache migration logic, preferring `name` when both are present.
2. Emit both keys indefinitely, with no removal release (preserves compatibility but leaves the old contract permanent).
3. Emit only `name` immediately and require client/cache migration (violates the supplied one-version deprecation invariant).

## Recorded decision

`DEC-001` — Select option 1. Treat `name` as canonical, retain `displayName` as a compatibility alias for exactly the promised one-version window, and make readers tolerant of either key with deterministic precedence (`name` over `displayName`). Do not remove the alias until the cutoff release and its migration evidence are established.

## Whole-set recalculation

| Impact | Result after `DEC-001` |
| --- | --- |
| `IMP-001` | `mitigated`: iOS remains able to decode the legacy alias during the window; `AC-001` verifies this. |
| `IMP-002` | `mitigated`: cached legacy JSON remains readable and can be rewritten under the canonical key; `AC-002` verifies this. |
| `IMP-003` | `mitigated`: the API retains the deprecated alias for the promised version; `AC-003` verifies the window. |
| `IMP-004` | `blocked` and unchanged: server serializer/schema and exact release identifiers remain required before implementation planning can finalize removal timing. |

Delta: no impacts are resolved; `IMP-001`–`IMP-003` are mitigated by `DEC-001`; `IMP-004` remains blocked; no new impacts identified from the supplied evidence.

## Acceptance and regression criteria

- `AC-001` — During the compatibility version, an iOS payload containing `displayName` still decodes successfully; a payload containing `name` also decodes successfully; when both are present, `name` wins.
- `AC-002` — Existing cached JSON containing only `displayName` remains readable, and a successful read may rewrite it using canonical `name` without data loss; new writes use `name`.
- `AC-003` — The public response contract documents `name` as canonical and `displayName` as deprecated for exactly one version; the alias is not removed before the documented cutoff.

## Stop check and planning handoff

The API-contract requirement is refined and the known impacts are classified. Planning may proceed with the dual-name compatibility adapter, but removal timing is blocked until the server serializer/schema and the release identifiers defining the one-version window are supplied. No implementation plan is created here.
