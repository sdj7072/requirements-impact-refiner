# Requirements-impact refinement: rename `displayName` to `name`

## Requirement revision

`REQ-001` — Rename the public profile field from `displayName` to `name`, making `name` the canonical field for newly written API payloads and persisted profile JSON. Preserve the published one-version deprecation window for the legacy field so existing iOS readers and cached profiles remain usable during that window. The exact removal version is not supplied and remains an open release-planning input.

## Current behavior and preserved invariants

| ID | Invariant to preserve | Evidence | Level | Link |
| --- | --- | --- | --- | --- |
| `INV-001` | The iOS user DTO currently decodes the wire key `displayName`. | Supplied repository evidence: `ios/UserDTO.swift` — `UserDTO` decoding | `verified` | `must-preserve` `REQ-001` |
| `INV-002` | Cached profile JSON currently persists the key `displayName`; an upgrade must not make existing cached profiles unreadable or lose the profile name. | Supplied repository evidence: cached profile JSON persistence | `verified` | `must-preserve` `REQ-001` |
| `INV-003` | The public API contract promises one version of deprecation for `displayName`. | Supplied repository evidence: public API changelog — deprecation promise | `verified` | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Category | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the iOS consumer that currently decodes it. | Interfaces / compatibility | `verified` | `ios/UserDTO.swift` — `UserDTO` decoding | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | Strictly renaming the cache key can make pre-upgrade cached profiles unreadable or drop the stored name. | Data / compatibility | `verified` | Cached profile JSON persists `displayName` | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | The public contract needs a staged alias/removal boundary rather than an undocumented wire break. | Interfaces / compatibility | `verified` | Public API changelog promises one-version deprecation | `refining` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | Other clients, generated SDKs, fixtures, events, or integrations may still consume `displayName`; their complete inventory is not available in the supplied evidence. | Interfaces / regression | `inferred` | Existing iOS and cache surfaces imply additional contract consumers may exist; no complete consumer inventory supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | The exact API version/date at which legacy compatibility must be removed cannot be determined from the supplied evidence. | Compatibility / operations | `unknown` | Changelog promise gives duration (“one version”) but no concrete removal identifier | `blocked` | `affects` `REQ-001`; `produces` `AC-005` |

## Focused decision

The refinement requires one compatibility choice: what behavior should apply during the promised deprecation version?

1. **Dual-read / single-write (recommended):** read `name` first and fall back to `displayName`; write only `name`; when both are present, `name` wins. Keep the fallback through exactly the promised version.
2. **Dual-read / dual-write:** read both with `name` precedence and emit both keys for the deprecation version. This maximizes old-client interoperability but prolongs conflicting dual representations.
3. **Immediate break:** accept/read only `name` now. This violates the supplied one-version deprecation promise and risks existing iOS/cache breakage.

## Recorded decision

`DEC-001` — The supplied public-changelog constraint selects a one-version compatibility period. Refine `REQ-001` with **dual-read / single-write**: `name` is canonical; readers accept legacy `displayName` only as a fallback during the deprecation version; writers emit `name` only; if both keys exist, `name` takes precedence. Removal must occur at the changelog-defined next-version boundary once that concrete identifier is supplied.

## Whole-set recalculation

| ID | Recalculated state | Result after `DEC-001` | Evidence / decision link |
| --- | --- | --- | --- |
| `IMP-001` | `mitigated` | iOS can read `name` and retain a bounded `displayName` fallback during the compatibility window. | `ios/UserDTO.swift` evidence; mitigated by `DEC-001`; `AC-001` |
| `IMP-002` | `mitigated` | Existing cache data remains readable through a legacy fallback and is normalized to canonical `name` on safe persistence; new writes use `name`. | Cached profile JSON evidence; mitigated by `DEC-001`; `AC-002` |
| `IMP-003` | `mitigated` | The changelog promise is represented as an explicit bounded compatibility transition; exact removal identifier remains open. | Public API changelog evidence; `DEC-001`; `AC-003` |
| `IMP-004` | `blocked` | Full downstream-consumer coverage cannot be established without a consumer/schema inventory. | Missing supplied inventory; `AC-004` |
| `IMP-005` | `blocked` | One-version duration is known, but the concrete removal version/date is not. | Missing release identifier; `AC-005` |

Delta: `resolved: none`; `mitigated: IMP-001, IMP-002, IMP-003`; `unchanged: none`; `accepted: none`; `deferred: none`; `blocked: IMP-004, IMP-005`; `new: none`.

## Acceptance and regression criteria

| ID | Criterion | Evidence level | Produced by |
| --- | --- | --- | --- |
| `AC-001` | A payload containing only `name` decodes to the existing user-name value; during the deprecation version, a payload containing only `displayName` also decodes, and a payload containing both uses `name`. | `verified` for the current reader and required behavior; implementation coverage remains to be demonstrated | `IMP-001` |
| `AC-002` | Existing cached JSON containing only `displayName` loads without data loss; newly persisted profile JSON contains `name` and does not create new `displayName` data. | `verified` for the existing persisted shape; migration behavior requires validation | `IMP-002` |
| `AC-003` | Public API documentation/changelog identifies `name` as canonical, marks `displayName` deprecated for one version, and names the removal boundary once available. | `verified` for the supplied promise; concrete boundary is unknown | `IMP-003` |
| `AC-004` | Before removal, supported clients, generated contracts, fixtures, events, and integrations are inventoried and no required consumer is left dependent on the legacy key. | `unknown` until inventory is supplied and checked | `IMP-004` |
| `AC-005` | The release plan supplies the exact version/date for removal, and post-boundary behavior is tested according to the established unknown-field policy. | `unknown` until the release identifier is supplied | `IMP-005` |

## Stop check and planning handoff

The requirement is refined and the material known impacts are linked to invariants, a bounded compatibility decision, and acceptance criteria. Planning may proceed with `name` as canonical and one-version dual-read/single-write compatibility. The remaining handoff risks are the missing downstream-consumer inventory (`IMP-004`) and missing concrete removal identifier (`IMP-005`); these are blocked information gaps, not silently accepted risks. This is a report-only handoff; no implementation work breakdown is included.
