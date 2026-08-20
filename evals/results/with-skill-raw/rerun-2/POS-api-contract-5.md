# Requirements impact review: `displayName` → `name`

## Requirement revision

`REQ-001` — Rename the public profile field from `displayName` to `name`, while preserving the existing `displayName` compatibility behavior for the one-version deprecation window promised by the public API changelog. The revision must cover API payloads, iOS decoding, and cached profile JSON; the exact read/write transition remains a pending decision.

## Current behavior and preserved invariants

`INV-001` — The iOS `UserDTO` currently decodes `displayName` and must continue to decode profiles during the compatibility window. **Verified** from the supplied fact: `ios/UserDTO.swift` decodes `displayName`.

`INV-002` — Existing cached profile JSON containing `displayName` must remain readable during the compatibility window. **Verified** from the supplied fact that cached profile JSON persists `displayName`.

`INV-003` — The public API must honor the changelog's promised one-version deprecation period for `displayName`. **Verified** from the supplied public API changelog fact.

## Impact ledger

| ID | Impact | Category | Evidence level and evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately would break the current iOS decoder. | Interfaces / Regression | **verified** — `ios/UserDTO.swift` decodes `displayName`. | `refining` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Rewriting the field without a compatibility reader could make persisted profile caches unreadable. | Data / Compatibility | **verified** — cached profile JSON persists `displayName`. | `refining` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | A field-only rename that removes `displayName` before the promised window ends would violate the public API contract. | Interfaces / Compatibility | **verified** — public API changelog promises one-version deprecation. | `refining` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | Other API consumers may still decode or send `displayName`, so an immediate wire removal may cause external breakage. | Interfaces / Compatibility | **inferred** — `displayName` is a public API field and the changelog explicitly promises deprecation. | `detected` | affects `REQ-001`, `INV-003`; produces `AC-004` |
| `IMP-005` | The repository facts do not establish whether the transition should emit both fields, accept both fields, or use an adapter, nor how the one-version boundary is identified. | Interfaces / Data / Compatibility | **unknown** — no transition schema, version marker, or migration behavior supplied. | `blocked` | affects `REQ-001`, `INV-001`, `INV-002`, `INV-003`; produces `AC-005` |

## One focused decision

**Decision needed:** What exact compatibility transition should implement the one-version deprecation?

1. **Dual-wire compatibility (recommended):** write `name`, read both `name` and legacy `displayName`, and continue emitting `displayName` alongside `name` until the documented one-version boundary.
2. **Read-only legacy compatibility:** write only `name`, but read `name` and fall back to `displayName` for iOS and cached JSON throughout the window.
3. **Versioned adapter:** keep a version-aware adapter that maps `displayName` ↔ `name` per client/API version, with the removal boundary enforced by the version contract.

No stakeholder selection was supplied, so no `DEC-###` is recorded and no impact is marked `accepted`.

## Recorded decision

None. The exact wire, cache, and version-transition policy is still pending.

## Whole-set recalculation

The requirement revision narrows the change by explicitly preserving the one-version compatibility window, but it does not select the transition mechanics. `IMP-001`, `IMP-002`, and `IMP-003` remain material until the pending decision is recorded; `IMP-004` remains an external-consumer risk; `IMP-005` remains blocked by missing transition evidence.

## Delta

- **resolved:** none.
- **mitigated:** none; the compatibility-window wording constrains the requirement but does not establish implementation behavior.
- **unchanged:** `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`.
- **accepted:** none; no `DEC-###` exists.
- **deferred:** none.
- **blocked:** `IMP-005` — transition schema/version-boundary information is missing.
- **new:** none.

## Stop check and planning handoff

The refined requirement, preserved invariants, evidence links, open risks, and acceptance criteria are ready for planning after the pending transition decision. This review stops before an implementation plan because material impacts are not yet resolved, accepted, or explicitly deferred.

### Acceptance and regression criteria

`AC-001` — During the one-version compatibility window, an iOS payload containing legacy `displayName` still decodes successfully; produced by `IMP-001`, verifies `INV-001`.

`AC-002` — Cached profile JSON containing legacy `displayName` remains readable and maps to the profile's `name`; produced by `IMP-002`, verifies `INV-002`.

`AC-003` — The public API exposes the new `name` field without removing legacy `displayName` before the changelog-promised one-version boundary; produced by `IMP-003`, verifies `INV-003`.

`AC-004` — A compatibility test documents the behavior for an external consumer using `displayName` during the deprecation window; produced by `IMP-004`.

`AC-005` — The selected transition policy explicitly defines read behavior, write behavior, cache behavior, and the version at which `displayName` may be removed; produced by `IMP-005`.
