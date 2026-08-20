# Requirements impact refinement: API contract field rename

## Requirement revision

`REQ-001` — Rename the public API profile field `displayName` to `name`, while honoring the published one-version deprecation promise for `displayName`. Existing readers and persisted profile data must remain usable throughout that compatibility window; the final removal point is the subsequent contract/version transition covered by the deprecation promise.

The supplied facts establish the compatibility constraint, but do not specify the exact wire shape during the deprecation window (for example, whether responses emit both fields, whether `name` is canonical with a fallback, or whether a versioned endpoint carries the transition). That wire choice remains the pending decision.

## Current behavior and preserved invariants

| ID | Current behavior to preserve | Evidence | Level | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | The iOS client decodes the profile value from the `displayName` field. | `ios/UserDTO.swift` — supplied fact: `UserDTO` decodes `displayName` | `verified` | `must-preserve` by `REQ-001` |
| `INV-002` | Cached profile JSON persists the `displayName` key. | Cached profile JSON — supplied repository fact | `verified` | `must-preserve` by `REQ-001` |
| `INV-003` | The public API contract provides a one-version deprecation window for `displayName`. | Public API changelog — supplied repository fact | `verified` | `must-preserve` by `REQ-001` |

## Impact ledger

| ID | Impact | Category | Evidence | Level | State | Relationships |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the shipped iOS decoder. | Interfaces / Compatibility | `ios/UserDTO.swift` — supplied fact that `UserDTO` decodes `displayName` | `verified` | `refining` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | A rename changes the public response contract for other consumers that still read `displayName`. | Interfaces / Compatibility | Public API changelog and public-field rename supplied in the request; external consumer inventory not supplied | `inferred` | `detected` | affects `REQ-001`, `INV-003`; produces `AC-002` |
| `IMP-003` | Rewriting or invalidating cached profiles without a compatibility read path can lose the existing display value or produce an empty value after cache hydration. | Data / Compatibility | Cached profile JSON persists `displayName` — supplied repository fact | `verified` | `detected` | affects `REQ-001`, `INV-002`; produces `AC-003` |
| `IMP-004` | The exact transition wire behavior is not determined: dual emission, canonical `name` with legacy fallback, or a versioned contract would have different rollout and downgrade behavior. | Interfaces / Operations / Compatibility | One-version deprecation promise is supplied, but no response schema, version boundary, or rollout rule is supplied | `unknown` | `blocked` | affects `REQ-001`, `INV-003`; produces `AC-004` |
| `IMP-005` | Existing compatibility and regression coverage for old/new payloads is not evidenced by the supplied facts. | Regression | No test names, fixtures, or compatibility assertions supplied | `unknown` | `blocked` | affects `REQ-001`, `INV-001`, `INV-002`, `INV-003`; produces `AC-005` |

## One focused decision

Decision needed: what exact public wire contract applies during the promised one-version deprecation window?

1. Emit both `name` and deprecated `displayName`, with `name` canonical (recommended for the stated compatibility promise).
2. Emit `name` only and provide a versioned/negotiated legacy response for old clients.
3. Emit `name` and make clients/cache readers fall back from `name` to legacy `displayName`, retaining legacy response emission only where separately required.

No stakeholder selection is recorded in the supplied request, so no `DEC-###` is allocated and no impact is marked `accepted`.

## Recorded decision

None recorded. The pending decision is the transition wire contract above.

## Whole-set recalculation

No decision was supplied after the impact ledger, so the requirement remains under refinement and all known impacts remain in scope. No impact is superseded and no new impact was identified.

## Delta

- `resolved: none`
- `mitigated: none`
- `unchanged: IMP-001, IMP-002, IMP-003, IMP-004, IMP-005`
- `accepted: none`
- `deferred: none`
- `blocked: IMP-004, IMP-005`
- `new: none`

## Acceptance and regression criteria

| ID | Criterion | Evidence target | Verifies |
| --- | --- | --- | --- |
| `AC-001` | During the one-version compatibility window, an iOS build using `UserDTO` continues to decode a profile response without losing the display value. | Compatibility fixture/test for `ios/UserDTO.swift` | `INV-001`, produced by `IMP-001` |
| `AC-002` | The published API contract documents `name`, the deprecation status of `displayName`, and the exact removal/version boundary. | API schema/changelog and contract test | `INV-003`, produced by `IMP-002` |
| `AC-003` | A cache containing legacy `displayName` hydrates correctly after the rename, and newly written cache data follows the selected contract without value loss. | Cache migration/read-write fixture | `INV-002`, produced by `IMP-003` |
| `AC-004` | The selected transition wire behavior is exercised for new clients, legacy clients, and downgrade/rollback behavior. | Versioned response fixtures and rollout/rollback test | `IMP-004` |
| `AC-005` | Regression tests cover old payloads, new payloads, and the one-version deprecation boundary; absence of such tests remains a validation gap rather than proof of coverage. | Named compatibility tests/fixtures | `IMP-005` |

## Stop check and planning handoff

This is a report-only planning handoff, not an implementation plan. `REQ-001` is refined by the one-version compatibility constraint and is ready for the selected planning workflow once the pending wire-contract decision is recorded. Remaining risks are the unresolved transition shape (`IMP-004`) and unverified test/fixture coverage (`IMP-005`); the iOS, cache, and public-contract compatibility obligations remain explicit in `INV-001`–`INV-003` and `AC-001`–`AC-005`.
