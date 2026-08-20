# Requirements impact report: API field rename

## Requirement revision

`REQ-001` — Rename the public profile field `displayName` to `name`, while honoring the public API changelog's one-version deprecation promise for the old field.

The deprecation window is a supplied constraint. The exact compatibility mechanism (wire shape, read/write precedence, and cache migration behavior) remains the pending decision.

## Current behavior and preserved invariants

- `INV-001` — The iOS client decodes a profile field named `displayName`; payloads containing that field must remain readable during the promised compatibility window. **verified** — `ios/UserDTO.swift` (supplied fact).
- `INV-002` — Cached profile JSON persists a field named `displayName`; already-cached profiles must not become unusable solely because the API field is renamed. **verified** — cached profile JSON (supplied fact).
- `INV-003` — The public API contract provides a one-version deprecation window for `displayName`. **verified** — public API changelog (supplied fact).

## Impact ledger

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break iOS profile decoding. | verified | `ios/UserDTO.swift` decodes `displayName` (supplied fact) | refining | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Renaming the persisted key without a compatibility path can make existing cached profile JSON unreadable or lose the displayed profile name. | verified | Cached profile JSON persists `displayName` (supplied fact) | refining | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | A cutover that removes the old field before one released compatibility version violates the published deprecation promise. | verified | Public API changelog promises one-version deprecation (supplied fact) | refining | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | Other consumers, fixtures, or persisted variants may still depend on `displayName`; their complete inventory is unavailable from the supplied facts. | unknown | No external-consumer inventory or compatibility fixture supplied | blocked | affects `REQ-001`; produces `AC-004` |

## One focused decision

How should the one-version compatibility window be implemented for API responses and cached profiles?

1. **Dual-field window (recommended):** emit `name` as canonical and retain `displayName` as a deprecated alias for one version; readers accept both, and cached data is lazily upgraded.
2. **Read-compatibility only:** emit only `name`, but readers (including cache readers) accept both keys for one version.
3. **Explicit migration boundary:** use a versioned endpoint/schema and migrate cached profiles at that boundary before removing `displayName`.

No option has been selected, so no concrete `DEC-###` is recorded. The pending decision must specify response shape, read precedence, and cache migration timing.

## Recorded decision

Decision needed — the pending decision described above.

## Whole-set recalculation

No decision was recorded. All known impacts remain applicable: `IMP-001`, `IMP-002`, and `IMP-003` remain `refining`; `IMP-004` remains `blocked` pending an external-consumer/cache-variant inventory. No impact is superseded, resolved, accepted, or deferred.

## Delta

- resolved: none
- mitigated: none
- unchanged: `IMP-001`, `IMP-002`, `IMP-003`
- accepted: none
- deferred: none
- blocked: `IMP-004` (named gap: external-consumer inventory and compatibility fixtures)
- new: none

## Acceptance and regression criteria

- `AC-001` — During the one-version deprecation window, an existing iOS payload containing `displayName` decodes successfully and yields the same profile name. **Target produced by `IMP-001`; current coverage not supplied.**
- `AC-002` — A profile cached before the rename, with `displayName`, remains readable and preserves its value after the rename; the chosen policy defines whether/when it is rewritten as `name`. **Target produced by `IMP-002`; current coverage not supplied.**
- `AC-003` — The published contract exposes the canonical `name` field while retaining the old-field behavior required by the one-version deprecation promise, then removes the alias only at the selected boundary. **Target produced by `IMP-003`; current coverage not supplied.**
- `AC-004` — Before cutover, the owner supplies an inventory or compatibility fixture for external consumers and persisted cache variants, or explicitly records the remaining unknown scope. **Target produced by `IMP-004`.**

## Stop check and planning handoff

The requirement is refined to include the `name` rename and the one-version compatibility constraint. Planning may proceed after the pending decision selects the compatibility mechanics and the `IMP-004` information gap is addressed or explicitly bounded. Remaining risks are `IMP-001`–`IMP-003` (unresolved until that decision) and `IMP-004` (blocked). Handoff criteria are `AC-001`–`AC-004`; this report creates no implementation work breakdown.
