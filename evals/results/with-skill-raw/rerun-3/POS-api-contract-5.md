# API contract impact refinement: `displayName` → `name`

## Requirement revision

`REQ-001` — Rename the public user/profile API field `displayName` to `name`.

The rename must account for existing iOS decoding, already-persisted cached profile JSON, and the public API changelog commitment that the old field is deprecated for one version. The exact wire transition and removal point remain a pending decision; this report does not select one.

## Current behavior and preserved invariants

`INV-001` — The iOS `UserDTO` currently decodes the key `displayName`. **Evidence: verified, task-supplied fact `ios/UserDTO.swift` (current decoder).** `REQ-001` must preserve the ability of supported iOS clients to decode profiles during the promised compatibility window.

`INV-002` — Cached profile JSON currently persists the key `displayName`. **Evidence: verified, task-supplied fact `cached profile JSON`.** Existing cached payloads must remain readable or be migrated; a cold-cache/network refresh cannot be the only recovery path unless that behavior is explicitly accepted.

`INV-003` — The public API changelog promises one-version deprecation for the old field. **Evidence: verified, task-supplied fact `public API changelog`.** The old contract cannot be removed immediately if that promise applies to this field and version stream.

## Impact ledger

| ID | Finding | Evidence level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` from responses immediately can break the current iOS decoder or yield missing profile display data. | `verified` | `ios/UserDTO.swift` — current `displayName` decoder (task-supplied fact) | `refining` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Existing cached profile JSON can become unreadable or semantically incomplete if only `name` is recognized. | `verified` | cached profile JSON persists `displayName` (task-supplied fact) | `refining` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | Immediate removal conflicts with the public one-version deprecation promise. | `verified` | public API changelog — one-version deprecation (task-supplied fact) | `refining` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | The behavior of uninspected external consumers, generated SDKs, fixtures, and integrations that may read `displayName` is not known. | `unknown` | Those consumers/contracts were not supplied or available for inspection | `blocked` | affects `REQ-001`; produces `AC-004` |
| `IMP-005` | The exact API version in which dual-read/dual-write compatibility ends is unspecified. | `unknown` | Changelog promise gives duration but not the concrete version boundary or release identifiers | `blocked` | affects `REQ-001`; produces `AC-005` |

## Focused decision

Choose the wire-compatibility policy for the one-version deprecation window:

1. **Recommended — dual contract for one version:** emit `name` as canonical and continue emitting `displayName` as a deprecated alias for exactly one API version; accept/read both names, with deterministic precedence documented. Continue reading legacy cached JSON and write the new canonical key after a successful read.
2. **Read-compatibility only:** emit only `name` immediately, while iOS/cache readers accept both keys for one version. This satisfies newer consumers but risks older clients that still require the old response key.
3. **Versioned hard cutover:** keep `displayName` on the old API version and expose only `name` on a new version, with an explicit cache migration. This has the clearest wire contract but requires version routing and client migration coordination.

No stakeholder selection is recorded in the request; therefore no concrete `DEC-###` is created and no impact is marked `accepted`.

## Recorded decision

No decision recorded. The pending decision is the wire-compatibility policy above. The one-version deprecation promise is a constraint/invariant, not a selection among the three transition policies.

## Whole-set recalculation

The requirement remains `REQ-001`; no impacts are superseded and no new impacts were discovered from the supplied evidence. Until the pending decision and version boundary are supplied:

- `resolved: none`
- `mitigated: none`
- `unchanged: IMP-001, IMP-002, IMP-003` (still `refining`)
- `accepted: none`
- `deferred: none`
- `blocked: IMP-004, IMP-005`
- `new: none`

## Acceptance and regression criteria

`AC-001` — During the one-version compatibility window, a supported iOS client can decode a response containing the new contract without losing the user’s display name, and the existing `displayName` decoding path remains supported according to the selected policy. **Verifies `INV-001`; produced by `IMP-001`.**

`AC-002` — A cache containing legacy `displayName` JSON remains readable and yields the same logical display name; after a successful read, the selected migration/write policy is deterministic. **Verifies `INV-002`; produced by `IMP-002`.**

`AC-003` — The API behavior and changelog/documentation preserve `displayName` for exactly the promised one-version deprecation period, then remove or stop emitting it only at the selected boundary. **Verifies `INV-003`; produced by `IMP-003`.**

`AC-004` — Before declaring the rename complete, identify and test external consumers, generated contracts, fixtures, and integrations that read or write `displayName`; if any remain unassessed, retain this impact as blocked. **Produced by `IMP-004`.**

`AC-005` — Record the concrete API version/release boundary and precedence rule for `name` versus `displayName`, including downgrade and cache behavior. **Produced by `IMP-005`.**

## Stop check and planning handoff

This is a report-only handoff, not an implementation plan. The refined requirement is to introduce `name` while preserving current iOS decoding, legacy cached profile readability, and the public one-version deprecation commitment. Planning may proceed only after the pending wire policy and concrete version boundary are selected, or the unresolved impacts are explicitly deferred/blocked with named owners and information sources. The planning workflow should carry forward `REQ-001`, `INV-001`–`INV-003`, `IMP-001`–`IMP-005`, and `AC-001`–`AC-005`.
