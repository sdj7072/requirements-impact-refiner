# Requirements impact refinement: API field rename

## Requirement revision

`REQ-001` — Rename the public API user/profile field from `displayName` to `name`, while honoring the published one-version deprecation promise for `displayName`. The compatibility behavior must cover the existing iOS decoder and locally cached profile JSON during that window. The exact request/response wire transition remains a pending decision.

## Current behavior and preserved invariants

`INV-001` — The iOS client currently decodes the user field under the key `displayName`.

- Evidence level: `verified`
- Evidence: supplied repository fact, `ios/UserDTO.swift` decoder
- Relationship: `must-preserve` `REQ-001`

`INV-002` — Cached profile JSON currently persists the key `displayName`; profiles already written to the cache must remain readable during the compatibility window.

- Evidence level: `verified`
- Evidence: supplied repository fact, cached profile JSON persistence
- Relationship: `must-preserve` `REQ-001`

`INV-003` — The public API contract promises one-version deprecation for `displayName`; immediate removal is not compatible with that promise.

- Evidence level: `verified`
- Evidence: supplied repository fact, public API changelog
- Relationship: `must-preserve` `REQ-001`

## Impact ledger

| ID | Impact | Area | Evidence level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the existing iOS decoder. | Interfaces / compatibility | `verified` | `ios/UserDTO.swift` decoder | `refining` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Renaming the persisted cache key without a compatibility read or migration can make existing cached profiles unreadable. | Data / compatibility | `verified` | cached profile JSON persistence | `refining` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | Removing `displayName` before the promised deprecation window ends would violate the public API changelog. | Interfaces / compatibility | `verified` | public API changelog | `refining` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | The repository facts do not establish whether the transitional contract should emit both keys, accept both keys, or use another explicit wire policy. | Interfaces / external compatibility | `unknown` | No request/response schema or external-consumer evidence supplied | `blocked` | affects `REQ-001`; produces `AC-004` |
| `IMP-005` | External consumers may still decode `displayName`, so an unverified consumer population could regress after the deprecation window. | Compatibility / regression | `inferred` | Public API field and changelog imply consumers beyond the supplied iOS client; consumer inventory unavailable | `blocked` | affects `REQ-001`; produces `AC-005` |

## Focused decision

**Decision needed:** What exact wire behavior implements the one-version deprecation?

1. **Dual-read and dual-write for one version (recommended):** accept `name` and `displayName`, and emit both; then remove `displayName` in the next version. This maximizes compatibility but temporarily duplicates the contract.
2. **Dual-read, new-name-only write:** accept both keys, but emit only `name` immediately; remove the legacy read after one version. This reduces response duplication but can break consumers that only read `displayName`.
3. **Versioned contract transition:** keep the old response under the old API version and expose `name` only in a new version, with an explicit migration boundary. This gives a clear contract boundary but requires versioning and consumer migration support.

No `DEC-###` is recorded because the supplied facts state the deprecation duration, not the selected wire policy.

## Whole-set recalculation

No decision has been recorded, so the complete known impact set remains as follows:

- `IMP-001` — unchanged (`refining`)
- `IMP-002` — unchanged (`refining`)
- `IMP-003` — unchanged (`refining`)
- `IMP-004` — blocked pending the wire-policy selection
- `IMP-005` — blocked pending an external-consumer inventory or explicit compatibility boundary

### Delta

- resolved: none
- mitigated: none
- unchanged: `IMP-001`, `IMP-002`, `IMP-003`
- accepted: none
- deferred: none
- blocked: `IMP-004`, `IMP-005`
- new: none

## Acceptance and regression criteria

`AC-001` — During the one-version compatibility window, an iOS payload using the legacy `displayName` key continues to decode successfully, and a payload using the selected new contract is covered by the client contract test.

- Evidence target: `ios/UserDTO.swift` decoder and its compatibility tests
- Verifies `INV-001`; produced by `IMP-001`

`AC-002` — A profile cached before the rename, with `displayName`, remains readable during the compatibility window; newly persisted profiles follow the selected wire policy without silently losing the user name.

- Evidence target: cached profile JSON reader/writer and migration/compatibility test
- Verifies `INV-002`; produced by `IMP-002`

`AC-003` — The published one-version deprecation promise is reflected in the API contract and release behavior: `displayName` is not removed before the promised boundary, and removal is explicitly tested at that boundary.

- Evidence target: public API contract/changelog and versioned compatibility test
- Verifies `INV-003`; produced by `IMP-003`

`AC-004` — The selected wire policy is documented and tested for both request and response directions, including precedence when both keys are present and the behavior when only the legacy key is present.

- Evidence target: API schema, serialization tests, and recorded decision
- Produced by `IMP-004`

`AC-005` — Before legacy removal, the supported external-consumer boundary is identified or explicitly declared; the release check verifies that consumers inside that boundary can use `name` and the promised legacy behavior.

- Evidence target: consumer inventory, API compatibility test, or published support boundary
- Produced by `IMP-005`

## Stop check and planning handoff

The refined requirement is ready for planning only after the pending wire-policy decision is recorded and the external-consumer boundary is supplied or explicitly declared. Until then, `IMP-004` and `IMP-005` remain blocked; silence is not acceptance. The planning handoff must carry `REQ-001`, `INV-001`–`INV-003`, the complete impact ledger, the selected transition policy, and `AC-001`–`AC-005`. No implementation work breakdown is included here.
