# POS API Contract — Requirements Impact Refinement (Round 5)

## Requirement revision

`REQ-001` — Rename the public API profile field from `displayName` to `name`, while honoring the published one-version deprecation window for the old field. Existing persisted profile payloads and supported clients must remain readable during that window; the post-window contract must use `name`.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | The iOS profile DTO currently decodes the `displayName` field. | `verified` | `ios/UserDTO.swift — UserDTO decoding` | `must-preserve` `REQ-001` |
| `INV-002` | Cached profile JSON currently persists the `displayName` field. | `verified` | `cached profile JSON — persisted profile field` | `must-preserve` `REQ-001` |
| `INV-003` | The public API changelog promises a one-version deprecation period for `displayName`. | `verified` | `public API changelog — field deprecation promise` | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing or ceasing to emit `displayName` immediately can break the existing iOS decoder. | `verified` | `ios/UserDTO.swift — UserDTO decoding` | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | Renaming the persisted cache key without a compatibility read/migration can make cached profiles unreadable. | `verified` | `cached profile JSON — persisted displayName field` | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | A one-version compatibility period is required by the published API contract; an immediate hard cutover would violate that promise. | `verified` | `public API changelog — one-version deprecation promise` | `refining` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | Handling by external consumers of the public API is not directly observable from the supplied evidence. | `unknown` | External consumers and their release schedules were not supplied. | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |

## One focused decision

The pending decision is the exact wire/cache compatibility mechanics for the one-version deprecation window (for example, dual read/write, read-old/write-new, or an explicitly scoped adapter). The request establishes the rename and the required window but does not select one of these mechanics.

## Recorded decision

No concrete `DEC-###` is recorded. The one-version deprecation promise is a supplied contract constraint, not a selection of implementation mechanics.

## Whole-set recalculation

No decision was recorded; all known impacts were re-evaluated against the revised requirement and supplied compatibility constraint. `IMP-001`–`IMP-003` remain refining because the exact compatibility mechanics are pending. `IMP-004` remains blocked by the named external-consumer information gap.

## Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-002`, `IMP-003`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`
- `new`: none

## Stop check and planning handoff

The refined requirement is ready for planning with the one-version deprecation constraint preserved. Planning must account for iOS decoding, cached profile readability, and the public changelog promise; external-consumer behavior remains a named validation gap.

### Acceptance criteria

| ID | Criterion | Level | Evidence / gap | Relationship |
| --- | --- | --- | --- | --- |
| `AC-001` | Supported iOS payload decoding continues to work throughout the one-version compatibility window while the API transitions to `name`. | `verified` target | `ios/UserDTO.swift — UserDTO decoding` | verifies `INV-001`; produced by `IMP-001` |
| `AC-002` | Profiles cached before the rename remain readable, and newly persisted profiles follow the selected post-window `name` contract. | `verified` target | `cached profile JSON — persisted displayName field` | verifies `INV-002`; produced by `IMP-002` |
| `AC-003` | The public contract and changelog expose `name` as the replacement and retain `displayName` compatibility for exactly the promised one-version deprecation period. | `verified` target | `public API changelog — one-version deprecation promise` | verifies `INV-003`; produced by `IMP-003` |
| `AC-004` | External consumer compatibility is assessed or explicitly documented before finalizing the transition mechanics. | `unknown` target | External consumer inventory/release support unavailable. | produced by `IMP-004` |
