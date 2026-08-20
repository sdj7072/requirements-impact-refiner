# POS — API contract rename (`displayName` → `name`)

## Requirement revision

**REQ-001** — Rename the public user profile field from `displayName` to `name`, while honoring the published one-version deprecation promise for existing consumers and preserving readable cached profiles throughout that compatibility window. The exact wire/cache transition mechanics remain the pending decision.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| **INV-001** | The iOS client decodes the profile field under the key `displayName`. | `verified` | `ios/UserDTO.swift` — `UserDTO` decoding | `must-preserve` REQ-001 |
| **INV-002** | Cached profile JSON persists the key `displayName`. | `verified` | Cached profile JSON persistence record supplied with the request | `must-preserve` REQ-001 |
| **INV-003** | The public API changelog promises a one-version deprecation period for the old field. | `verified` | Public API changelog — `displayName` deprecation commitment | `must-preserve` REQ-001 |

## Impact ledger

Ordered by severity, then evidence confidence.

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| **IMP-001** | Removing `displayName` immediately can break the iOS decoder. | `verified` | `ios/UserDTO.swift` — `UserDTO` decoding | `refining` | `affects` REQ-001, INV-001; `produces` AC-001 |
| **IMP-002** | Changing the persisted key immediately can make existing cached profile JSON unreadable or leave the profile name absent after cache reuse. | `verified` | Cached profile JSON persistence record supplied with the request | `refining` | `affects` REQ-001, INV-002; `produces` AC-002 |
| **IMP-003** | A public contract change that omits the promised one-version deprecation violates the published compatibility commitment. | `verified` | Public API changelog — `displayName` deprecation commitment | `refining` | `affects` REQ-001, INV-003; `produces` AC-003 |
| **IMP-004** | The exact compatibility mechanics (dual response fields, fallback decoding, cache migration, or another transition) are not specified by the supplied facts. | `unknown` | No implementation policy or compatibility test supplied; only the three named surfaces were provided | `blocked` | `affects` REQ-001; named gap: transition policy and test evidence |

## One focused decision

Which compatibility transition should implement the one-version deprecation window?

1. **Dual-read / dual-write (recommended):** expose `name` as canonical while accepting `displayName`, and keep both representations available as needed for old clients and cache entries during the window.
2. **Canonical new field with legacy read fallback:** write only `name`, but clients/cache readers accept `displayName` for the window and migrate on read.
3. **Versioned contract boundary:** serve old and new field shapes from explicitly versioned API contracts, with an explicit cache migration at the boundary.

No option has been selected; no concrete `DEC-###` is recorded. The pending decision is required before assigning an exact wire/cache policy.

## Recorded decision

**Decision needed.** The supplied requirement and deprecation promise constrain the compatibility window but do not explicitly select one of the transition mechanics above.

## Whole-set recalculation

No decision was recorded, so all known impacts were recalculated against REQ-001 as revised:

- **IMP-001:** remains `refining`; immediate removal is still unsafe until the pending transition policy preserves iOS decoding.
- **IMP-002:** remains `refining`; existing cached JSON still requires a compatibility path.
- **IMP-003:** remains `refining`; the one-version public deprecation commitment still governs the rename.
- **IMP-004:** remains `blocked`; the exact transition policy and validation evidence are unavailable.

## Delta

- resolved: none
- mitigated: none
- unchanged: IMP-001, IMP-002, IMP-003
- accepted: none (no recorded decision)
- deferred: none
- blocked: IMP-004
- new: none

## Acceptance and regression criteria

| ID | Criterion | Level | Supporting evidence / gap | Produced by |
| --- | --- | --- | --- | --- |
| **AC-001** | During the one-version compatibility window, an existing iOS payload using `displayName` still decodes the user’s name. | `verified` target criterion | `ios/UserDTO.swift` — `UserDTO` decoding; compatibility test evidence not supplied | IMP-001 |
| **AC-002** | A profile cached before the rename remains readable and yields the user’s name after the rename transition. | `verified` target criterion | Cached profile JSON persistence record supplied; cache migration/read-path test evidence not supplied | IMP-002 |
| **AC-003** | The public API preserves the documented one-version deprecation behavior before removing the legacy field. | `verified` target criterion | Public API changelog — deprecation commitment; contract/version test evidence not supplied | IMP-003 |

## Stop check and planning handoff

The requirement is refined enough for planning at the contract level, with the one-version compatibility promise and preserved iOS/cache behavior explicit. Planning remains gated on the pending transition-mechanics choice and on validation evidence for API decoding and cached-profile migration. Do not treat the absence of a decision as acceptance; IMP-004 is blocked by that named information gap.

