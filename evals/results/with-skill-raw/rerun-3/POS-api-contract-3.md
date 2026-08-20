# API contract impact refinement: `displayName` → `name`

## Requirement revision

`REQ-001` — Rename the public API field `displayName` to `name`, while honoring the already-published one-version deprecation promise. During that compatibility window, existing iOS payload decoding and cached profile data must remain readable. The exact wire and cache transition policy remains a pending decision because the supplied evidence does not specify whether the server writes one or both field names, nor whether a cache migration is required.

## Current behavior and preserved invariants

`INV-001` — The iOS client currently decodes the `displayName` field. **Evidence level: verified.** Evidence: supplied repository fact `ios/UserDTO.swift decodes displayName`. `REQ-001` must preserve successful decoding of existing `displayName` payloads through the promised compatibility window.

`INV-002` — Cached profile JSON currently persists `displayName`. **Evidence level: verified.** Evidence: supplied repository fact `cached profile JSON persists displayName`. `REQ-001` must not make profiles already present in cache unreadable during the compatibility window.

`INV-003` — The public API changelog promises one-version deprecation for this rename. **Evidence level: verified.** Evidence: supplied repository fact `the public API changelog promises one-version deprecation`. The old field therefore cannot be treated as immediately removed without violating the published compatibility promise.

## Impact ledger

| ID | Impact | Evidence level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the current iOS decoder. | `verified` | `ios/UserDTO.swift decodes displayName` | `refining` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Renaming the persisted cache key immediately can make existing cached profiles unreadable. | `verified` | `cached profile JSON persists displayName` | `refining` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | Immediate removal of `displayName` would violate the public one-version deprecation promise. | `verified` | `the public API changelog promises one-version deprecation` | `refining` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | The exact API transition (dual-read, dual-write, aliasing, or another compatibility adapter) is unspecified. | `unknown` | No supplied evidence selects a wire transition policy. | `blocked` | affects `REQ-001`; produces `AC-004` |
| `IMP-005` | The exact cache migration/read-fallback policy is unspecified. | `unknown` | No supplied evidence specifies cache migration timing or fallback behavior. | `blocked` | affects `REQ-001`, `INV-002`; produces `AC-005` |

## One focused decision

Which compatibility policy should implement the one-version deprecation?

1. **Canonical-new with legacy read (recommended):** emit/read `name` as canonical, continue accepting `displayName` from API payloads and cache, and remove legacy support after the promised version.
2. **Dual read and dual write:** accept both names and write both for the compatibility version, then remove `displayName`.
3. **Explicit adapter policy:** use a separately documented mapping/adapter, with its own chosen read/write and cache migration rules.

No concrete `DEC-###` is recorded because the request supplies the deprecation promise but does not select one of these transition policies.

## Recorded decision

No recorded decision. The pending decision is the compatibility policy above; no impact is marked `accepted`.

## Whole-set recalculation

No decision was supplied, so all known impacts were re-evaluated against `REQ-001`:

- `IMP-001`: remains `refining`; preserving the iOS legacy decoder is required by `INV-001`.
- `IMP-002`: remains `refining`; preserving readability of cached legacy JSON is required by `INV-002`.
- `IMP-003`: remains `refining`; the one-version deprecation promise constrains removal timing.
- `IMP-004`: remains `blocked`; the API read/write transition is not evidenced.
- `IMP-005`: remains `blocked`; cache migration/fallback behavior is not evidenced.

### Delta

- `resolved`: none.
- `mitigated`: none.
- `unchanged`: `IMP-001`, `IMP-002`, `IMP-003`.
- `accepted`: none.
- `deferred`: none.
- `blocked`: `IMP-004`, `IMP-005`.
- `new`: none.

## Stop check and planning handoff

The refined requirement is ready for the selected planning workflow, but implementation planning must retain the one-version compatibility constraint and resolve the pending API/cache transition policy first. Remaining risks are breakage of current iOS decoding, unreadable cached profiles, and breach of the published deprecation promise if legacy support is removed early. External consumers and generated contracts are not covered by the supplied evidence and should be assessed by the planning workflow if in scope.

### Acceptance and regression criteria

`AC-001` — Existing API payloads containing `displayName` continue to decode successfully in `ios/UserDTO.swift` throughout the promised compatibility version. Produced by `IMP-001`; verifies `INV-001`.

`AC-002` — A cached profile JSON written with `displayName` remains readable throughout the promised compatibility version, or is migrated without data loss under the selected cache policy. Produced by `IMP-002`; verifies `INV-002`.

`AC-003` — The public contract exposes `name` according to the selected transition and does not remove `displayName` before the one-version deprecation window ends. Produced by `IMP-003`; verifies `INV-003`.

`AC-004` — The chosen API policy has an executable compatibility test covering old and new field names and the post-deprecation behavior. Produced by `IMP-004`.

`AC-005` — The chosen cache policy has an executable regression test for pre-rename cached JSON and confirms preservation of the profile value. Produced by `IMP-005`.

