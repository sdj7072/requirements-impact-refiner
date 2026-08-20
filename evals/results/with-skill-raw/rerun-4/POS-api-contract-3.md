# Requirements impact refinement — API contract

## Requirement revision

`REQ-001` — Rename the public user-profile API field `displayName` to `name`, while honoring the public API changelog's one-version deprecation promise. The transition must preserve existing readers and persisted profile data for the promised compatibility window; the exact wire and cache transition remains the pending decision.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | The iOS user DTO currently decodes the response field `displayName`. | `verified` | `ios/UserDTO.swift` — user DTO decoding | `must-preserve` `REQ-001` |
| `INV-002` | Cached profile JSON currently persists the key `displayName`. | `verified` | Supplied request fact — cached profile JSON persistence | `must-preserve` `REQ-001` |
| `INV-003` | The public API changelog promises one-version deprecation for this field transition. | `verified` | Supplied request fact — public API changelog | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the existing iOS decoder. | `verified` | `ios/UserDTO.swift` — user DTO decoding | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | Replacing the cached key immediately can make already-persisted profiles unreadable. | `verified` | Supplied request fact — cached profile JSON persists `displayName` | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | The public API contract must expose the rename consistently with the promised one-version deprecation window. | `verified` | Supplied request fact — public API changelog | `refining` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | Behavior of external consumers, if any, cannot be assessed from the supplied repository facts. | `unknown` | No external consumer contract or compatibility fixture supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |

## One focused decision

The pending decision is how the API and cache should represent the compatibility window. Select one:

1. **Dual-read / dual-write (recommended):** emit `name` and deprecated `displayName`, and read either key; prefer `name` when both exist.
2. **Dual-read / new-write:** emit only `name`, but accept both keys and migrate old cache entries on read.
3. **Versioned contract:** keep the old field in the current API version and introduce `name` only in a new version.

No explicit stakeholder selection is recorded in the supplied request, so no concrete `DEC-###` is created.

## Recorded decision

Decision needed — use the pending decision above. The one-version deprecation constraint does not select a wire or cache strategy.

## Whole-set recalculation

No decision was recorded; all known impacts were recalculated against `REQ-001` and remain open.

### Delta

- `resolved: none`
- `mitigated: none`
- `unchanged: IMP-001, IMP-002, IMP-003`
- `accepted: none`
- `deferred: none`
- `blocked: IMP-004`
- `new: none`

## Stop check and planning handoff

The refined requirement, preserved invariants, evidence links, open risks, and acceptance criteria are ready for the planning workflow after the pending API/cache strategy is selected. `IMP-004` remains blocked until an external-consumer contract or compatibility fixture is available. This is a report-only handoff; no implementation work breakdown is defined.

## Acceptance and regression criteria

| ID | Criterion | Evidence / relationship |
| --- | --- | --- |
| `AC-001` | Existing iOS payload decoding continues to work throughout the one-version deprecation window. | Verifies `INV-001`; produced by `IMP-001` |
| `AC-002` | Profiles persisted with `displayName` remain readable throughout the one-version deprecation window, with an explicit rule for records containing both keys. | Verifies `INV-002`; produced by `IMP-002` |
| `AC-003` | The published API contract and changelog consistently document `name`, the deprecated `displayName`, and the selected one-version transition behavior. | Verifies `INV-003`; produced by `IMP-003` |
| `AC-004` | External consumer behavior is either verified against a supplied contract/fixture or explicitly documented as an unresolved compatibility gap before release. | Produced by blocked `IMP-004` |
