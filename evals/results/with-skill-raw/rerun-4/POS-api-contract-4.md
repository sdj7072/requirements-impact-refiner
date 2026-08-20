# POS API contract impact refinement — green rerun 4

## Requirement revision

`REQ-001`: Rename the public user/profile API field from `displayName` to `name`, while honoring the published one-version deprecation window for `displayName`. The exact wire and cache transition mechanics remain the pending decision.

## Current behavior and preserved invariants

- `INV-001` (`verified`): The iOS user DTO currently decodes `displayName`; this reader behavior must remain compatible during the promised deprecation window. Evidence: `ios/UserDTO.swift` — `UserDTO` decoding of `displayName`. Links: `must-preserve` `REQ-001`.
- `INV-002` (`verified`): Cached profile JSON currently persists `displayName`; previously cached profiles must remain usable during the promised deprecation window. Evidence: cached profile JSON persistence of `displayName` (supplied repository fact). Links: `must-preserve` `REQ-001`.
- `INV-003` (`verified`): The public API changelog promises one-version deprecation for `displayName`; the rename must not remove the legacy contract before that window completes. Evidence: public API changelog, one-version deprecation commitment (supplied repository fact). Links: `must-preserve` `REQ-001`.

## Impact ledger

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the existing iOS decoder. | `verified` | `ios/UserDTO.swift` — `UserDTO` decoding of `displayName` | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | Renaming or rewriting the cache without a compatibility read can make persisted profile JSON unreadable. | `verified` | Cached profile JSON persists `displayName` (supplied repository fact) | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | A public contract change that removes `displayName` before one subsequent API version violates the changelog promise. | `verified` | Public API changelog, one-version deprecation commitment (supplied repository fact) | `refining` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | Other external API consumers may still read or send `displayName`, but their release and fallback behavior is not available in the inspected evidence. | `inferred` | Public API field and deprecation promise; no external consumer inventory supplied | `detected` | `affects` `REQ-001` |
| `IMP-005` | The required canonical-field and alias mechanics (dual read, dual write, or version-gated behavior) cannot be selected from the supplied facts alone. | `unknown` | No explicit stakeholder choice of wire/cache transition mechanics | `blocked` | `affects` `REQ-001` |

## Focused decision

Which compatibility mechanics should implement the one-version deprecation window?

1. **Dual-read, canonical-write (recommended):** accept `name` and legacy `displayName`, emit/persist only `name`, and retain legacy reads for the deprecation version.
2. **Dual-read, dual-write:** accept both fields and emit/persist both for the deprecation version, then remove `displayName`.
3. **Version-gated contract:** expose `name` only for the new API version and retain `displayName` in the prior version, with cache migration defined separately.

No explicit selection is recorded in this rerun; the pending decision remains open. Therefore no concrete `DEC-###` is allocated.

## Recorded decision

Decision needed: select one compatibility mechanic above and specify whether cached profile JSON follows the same version boundary.

## Whole-set recalculation

No decision was supplied, so all known impacts are recalculated against `REQ-001` without changing their evidence-backed state:

- `IMP-001`: `refining` — remains open until the iOS reader compatibility behavior is specified and testable.
- `IMP-002`: `refining` — remains open until cache read/write and migration behavior is specified and testable.
- `IMP-003`: `refining` — remains open until the one-version boundary is mapped to the public contract.
- `IMP-004`: `detected` — remains open pending an external-consumer inventory or an explicit compatibility assumption.
- `IMP-005`: `blocked` — blocked by the absent stakeholder choice of transition mechanics.

## Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-005`
- `new`: none

## Acceptance and regression criteria

- `AC-001`: During the one-version deprecation window, an iOS payload using the supported compatibility form decodes the user name successfully; evidence target: `ios/UserDTO.swift` — `UserDTO` decoding path. Produced by `IMP-001`; verifies `INV-001`.
- `AC-002`: A cached profile JSON produced before the rename remains readable during the one-version window, and the selected write policy is deterministic afterward. Evidence target: cached profile JSON persistence/reader tests. Produced by `IMP-002`; verifies `INV-002`.
- `AC-003`: The public API contract and changelog show `name` as the replacement while retaining `displayName` for exactly the promised one-version deprecation window; removal is rejected before that boundary. Evidence target: public API contract/changelog compatibility test. Produced by `IMP-003`; verifies `INV-003`.

## Stop check and planning handoff

The requirement is refined to a field rename with a one-version compatibility constraint. The report links `REQ-001` to the preserved iOS decoder, cached profile JSON, and changelog invariants, and provides `AC-001`–`AC-003`. Remaining risks are the unknown external-consumer behavior (`IMP-004`) and the blocked mechanics selection (`IMP-005`); the latter must be resolved by the pending decision before implementation planning can finalize. This is a report-only handoff, not an implementation plan.
