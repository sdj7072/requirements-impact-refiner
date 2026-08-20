# Requirements Impact Refiner — API Contract

## Requirement revision

`REQ-001` — Rename the public user API field `displayName` to `name`, while preserving compatibility for one version through the explicitly supplied deprecation window.

Scope is limited to the API contract and its known readers/writers. The compatibility behavior must cover the supplied iOS decoder and cached profile JSON.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `INV-001` | The iOS user DTO currently decodes the `displayName` field. | `verified` | Supplied repository fact: `ios/UserDTO.swift` decodes `displayName`. | `detected` | `must-preserve` `REQ-001` |
| `INV-002` | Cached profile JSON currently persists the `displayName` field. | `verified` | Supplied repository fact: cached profile JSON persists `displayName`. | `detected` | `must-preserve` `REQ-001` |
| `INV-003` | The public API has a one-version deprecation promise for this rename. | `verified` | Supplied repository fact: public API changelog promises one-version deprecation. | `detected` | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Category | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the iOS decoder. | Interfaces / Regression | `verified` | `ios/UserDTO.swift` decodes `displayName`. | `mitigated` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | Renaming or rewriting the field without a compatibility rule can make existing cached profile JSON unreadable. | Data / Compatibility | `verified` | Cached profile JSON persists `displayName`. | `mitigated` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | A public contract change must honor the promised one-version deprecation window. | Interfaces / Compatibility | `verified` | Public API changelog promises one-version deprecation. | `mitigated` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | Behavior of consumers beyond the supplied iOS decoder and cached profile JSON is not assessed. | Compatibility | `unknown` | No additional consumer artifacts were supplied for this rerun. | `blocked` | `affects` `REQ-001` |

## Decision needed

The supplied one-version deprecation promise establishes the compatibility window, but the wire representation during that window still needs to be explicit. The contract must choose one of:

1. **Dual field (recommended):** responses expose both `name` and deprecated `displayName` for one API version; requests accept both with a defined precedence, then `displayName` is removed in the next version.
2. **Read-alias only:** responses expose `name`; readers accept legacy `displayName` for one version, including cached data, but writers never emit it.
3. **Versioned media/endpoint contract:** the old version continues to expose `displayName`, while the new version exposes `name`; migration between versions is explicit.

No additional stakeholder choice was supplied for this wire-policy detail, so no `DEC-###` is recorded and no impact is marked accepted.

## Recorded decision

No new decision. The one-version deprecation commitment is an explicit input constraint, not a selection among the three wire-policy options above.

## Whole-set recalculation

The requirement remains `REQ-001`. `INV-001` through `INV-003` remain preserved invariants. `IMP-001` through `IMP-003` are reduced to `mitigated` by the one-version compatibility constraint, but cannot be `resolved` until the wire policy and validation evidence are defined. `IMP-004` remains `blocked` because additional consumers were not supplied.

### Delta

- `resolved`: none
- `mitigated`: `IMP-001`, `IMP-002`, `IMP-003`
- `unchanged`: `INV-001`, `INV-002`, `INV-003`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`; wire-policy decision remains open
- `new`: none

## Acceptance criteria

| ID | Criterion | Evidence target | Links |
| --- | --- | --- | --- |
| `AC-001` | During the one-version compatibility window, an iOS payload using legacy `displayName` remains decodable, and the renamed `name` value is available through the DTO’s public name semantics. | iOS decoder compatibility test or equivalent fixture for `ios/UserDTO.swift`. | verifies `INV-001`; produced by `IMP-001` |
| `AC-002` | Existing cached profile JSON containing `displayName` remains readable during the compatibility window, and newly written cache data follows the selected wire policy. | Cache read/write compatibility test with legacy and renamed fixtures. | verifies `INV-002`; produced by `IMP-002` |
| `AC-003` | The public API documents `name` as the replacement, marks `displayName` deprecated for exactly one version, and removes the legacy field only at the subsequent version boundary according to the selected wire policy. | Published API contract/changelog compatibility check. | verifies `INV-003`; produced by `IMP-003` |

## Stop check and planning handoff

The refined requirement, preserved invariants, complete impact ledger, open wire-policy decision, blocked external-consumer assessment, and acceptance criteria are ready for the selected planning workflow. This is a report-only handoff; no implementation work breakdown is included.

