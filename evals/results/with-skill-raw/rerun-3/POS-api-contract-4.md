# API contract — `displayName` → `name`

## Requirement revision

**REQ-001 (revised):** Rename the public user-profile API field `displayName` to `name`, while honoring the published one-version deprecation promise. The contract must define the wire behavior during that deprecation version, preserve compatibility for the iOS decoder and cached profile JSON, and make the post-deprecation removal explicit. The exact read/write transition remains the pending decision.

## Current behavior and preserved invariants

- **INV-001:** The iOS `UserDTO` decodes the `displayName` field. **Evidence:** supplied fact `ios/UserDTO.swift` decodes `displayName`. **Level:** `verified`. **Relationship:** `REQ-001` must preserve it.
- **INV-002:** Cached profile JSON persists the `displayName` key. **Evidence:** supplied fact that cached profile JSON persists `displayName`. **Level:** `verified`. **Relationship:** `REQ-001` must preserve readable cached profiles through the compatibility window.
- **INV-003:** The public API has promised one version of deprecation before removal. **Evidence:** supplied fact that the public API changelog promises one-version deprecation. **Level:** `verified`. **Relationship:** `REQ-001` must preserve the promise.

## Impact ledger

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| **IMP-001** | Removing `displayName` immediately breaks the existing iOS decoder. | `verified` | supplied fact: `ios/UserDTO.swift` decodes `displayName` | `refining` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| **IMP-002** | Replacing the key without a cache read/migration path makes existing cached profile JSON unreadable or loses the displayed name. | `verified` | supplied fact: cached profile JSON persists `displayName` | `refining` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| **IMP-003** | Immediate removal violates the public one-version deprecation commitment. | `verified` | supplied fact: public API changelog promises one-version deprecation | `refining` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| **IMP-004** | The exact compatibility wire policy—whether to emit both keys, accept both keys, and precedence when both are present—is not specified by the supplied facts. | `unknown` | no supplied schema, version identifier, or compatibility test defines read/write precedence | `blocked` | affects `REQ-001`; produces `AC-004` |
| **IMP-005** | The post-deprecation version and removal signal are unspecified, so clients cannot know when `displayName` may be removed safely. | `unknown` | changelog promise gives duration (“one version”) but no version identifier or removal contract | `blocked` | affects `REQ-001`; produces `AC-005` |

## Focused decision

The pending decision is the compatibility wire policy for the one-version deprecation window:

1. **Dual-wire compatibility (recommended):** emit canonical `name`; accept both `name` and `displayName`; when both are present, `name` wins; continue reading old cache entries and write only `name` after a successful read.
2. **Read-alias only:** emit only `name`; accept both keys with `name` precedence; retain a cache fallback for `displayName` but do not emit it.
3. **Dual-wire with legacy precedence:** emit both keys and accept both, with `displayName` winning when both are present for maximum legacy behavior (but slower migration and greater ambiguity).

No explicit stakeholder selection is recorded in the request; therefore no `DEC-###` is created and no impact is marked `accepted`.

## Recorded decision

No recorded decision. The API contract cannot finalize the exact wire transition or the deprecation/removal version until the pending decision is selected.

## Whole-set recalculation

The requirement has been refined to include a one-version compatibility window, cache compatibility, and an explicit wire-policy decision. No decision has been supplied, so the impacts remain as follows:

- **resolved:** none.
- **mitigated:** none; the revised requirement identifies the required compatibility outcomes but does not select their implementation policy.
- **unchanged:** `IMP-001`, `IMP-002`, `IMP-003` remain `refining` because the requirement now directly addresses them but evidence of a concrete contract is absent.
- **accepted:** none; no `DEC-###` exists.
- **deferred:** none; no intentional postponement was supplied.
- **blocked:** `IMP-004`, `IMP-005`, due to the missing wire-policy choice and version/removal details.
- **new:** none.

## Acceptance and regression criteria

- **AC-001:** During the promised deprecation version, a payload containing the legacy `displayName` is decoded by `ios/UserDTO.swift` without loss of the user’s display name; produced by `IMP-001`.
- **AC-002:** A cached profile JSON document containing only `displayName` remains readable and yields the same profile name during the compatibility window; produced by `IMP-002`.
- **AC-003:** The published API contract and changelog identify `name` as the replacement and retain `displayName` for exactly one declared API version before removal; produced by `IMP-003`.
- **AC-004:** The finalized contract has tests for `name` only, `displayName` only, and both keys, with the selected precedence and emission behavior asserted; produced by `IMP-004`.
- **AC-005:** The finalized contract names the deprecation and removal versions and specifies the behavior/error for `displayName` after removal; produced by `IMP-005`.

## Stop check and planning handoff

This is a report-only handoff. The refined requirement, preserved invariants, impact ledger, open information gaps, and acceptance criteria are recorded above. Implementation planning should begin only after the pending wire-policy choice and the concrete deprecation/removal version are recorded; no implementation work breakdown is included here.
