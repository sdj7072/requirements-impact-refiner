# API-contract impact refinement: `displayName` → `name`

## Requirement revision

`REQ-001` — Rename the public profile field `displayName` to `name`, while honoring the published one-version deprecation promise for the old field. During that compatibility window, existing readers and persisted profile data must remain usable; after the window, removal of `displayName` may proceed according to the versioning policy.

The supplied request does not specify whether the rename applies to responses only, requests only, or both directions. That scope remains an explicit uncertainty (`IMP-006`) for implementation planning.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | The iOS profile DTO decodes a field named `displayName`. | `verified` | `ios/UserDTO.swift` — supplied repository fact | `must-preserve` by `REQ-001` |
| `INV-002` | Cached profile JSON persists a field named `displayName`. | `verified` | cached profile JSON — supplied repository fact | `must-preserve` by `REQ-001` |
| `INV-003` | The public API changelog promises one-version deprecation of `displayName`. | `verified` | public API changelog — supplied repository fact | `must-preserve` by `REQ-001` |
| `INV-004` | Existing profiles must remain readable across the compatibility window. | `inferred` | Consequence of `INV-001`, `INV-002`, and the deprecation promise in `INV-003` | `must-preserve` by `REQ-001` |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links / acceptance criterion |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the iOS decoder. | `verified` | `ios/UserDTO.swift` — supplied fact that the decoder reads `displayName` | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | A cache format that writes only `name` can make existing cached profiles unreadable unless the reader accepts the legacy key or data is migrated. | `verified` | cached profile JSON — supplied fact that `displayName` is persisted | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | A hard removal before one released version violates the public compatibility promise. | `verified` | public API changelog — supplied one-version deprecation promise | `refining` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | Other API consumers, generated clients, fixtures, or integrations may still use `displayName`. | `inferred` | Public API field rename plus the known iOS consumer and persisted representation | `detected` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Keeping both keys in a response can create precedence ambiguity when values differ. | `inferred` | Compatibility strategy implied by `INV-003`; no conflict-resolution rule supplied | `detected` | `affects` `REQ-001`; `produces` `AC-005` |
| `IMP-006` | The request/response direction of the rename is unspecified, so request validation and write compatibility cannot yet be assessed. | `unknown` | No supplied contract distinguishes response fields from request fields | `blocked` | `affects` `REQ-001`; named information gap |
| `IMP-007` | The exact release/version boundary and deprecation duration are not identified beyond “one version.” | `unknown` | Changelog promise supplied without version identifiers | `blocked` | `affects` `REQ-001`, `INV-003`; named information gap |
| `IMP-008` | No compatibility or cache migration test evidence was supplied, so regression coverage is unknown. | `unknown` | No tests or fixtures supplied for inspection | `blocked` | `affects` `REQ-001`, `INV-001`, `INV-002`; validation gap |

## Focused decision

The compatibility policy must define how the one-version deprecation is represented on the wire and in clients. The concrete options are:

1. **Dual-read / dual-write for one version (recommended):** emit and accept `name` and legacy `displayName` during the window; define `name` as canonical and require equal values when both are present. Remove the legacy key in the next version.
2. **Canonical `name` plus legacy read-only:** emit only `name`, but accept `displayName` in inbound payloads and cached data for one version. This reduces response duplication but requires all old response consumers to update immediately.
3. **Compatibility adapter at client/cache boundaries:** keep the public API change to `name`, and translate legacy `displayName` only in the iOS decoder and cache reader/writer. This limits wire compatibility but does not protect unknown external consumers.

## Recorded decision

`DEC-001` — Apply the published one-version deprecation promise using option 1: treat `name` as canonical, preserve legacy `displayName` read compatibility for the promised version, and remove the legacy field only in the subsequent version after the compatibility window. Existing cached data must remain readable during the window. This decision refines `REQ-001` and mitigates `IMP-001`, `IMP-002`, and `IMP-003`; it does not resolve the unknown request/response scope or release identifiers.

## Whole-set recalculation after `DEC-001`

| ID | Result after decision | State | Evidence / rationale |
| --- | --- | --- | --- |
| `IMP-001` | iOS can continue reading legacy data during the one-version window; it still needs an explicit fallback/canonicalization rule. | `mitigated` | `DEC-001` + `ios/UserDTO.swift` supplied fact |
| `IMP-002` | Existing cached JSON remains readable; cache writes should converge on canonical `name` while retaining a legacy-read path. | `mitigated` | `DEC-001` + cached profile JSON supplied fact |
| `IMP-003` | Immediate removal is ruled out; removal is deferred to the version after the promised window. | `mitigated` | `DEC-001` + public API changelog supplied fact |
| `IMP-004` | Unknown external consumers remain a compatibility risk until contract inventory is performed. | `detected` | No external-consumer inventory supplied |
| `IMP-005` | `name` is canonical; the implementation must define behavior for conflicting dual-key values. | `detected` | Decision establishes precedence but not conflict handling |
| `IMP-006` | Request-vs-response scope remains unspecified. | `blocked` | No supplied contract detail |
| `IMP-007` | Exact release identifiers remain unspecified. | `blocked` | No supplied version numbers |
| `IMP-008` | Test/fixture coverage remains unknown. | `blocked` | No supplied test evidence |

### Delta

- `IMP-001`, `IMP-002`, and `IMP-003`: `refining` → `mitigated` by `DEC-001`.
- `IMP-004` and `IMP-005`: unchanged `detected` risks requiring planning constraints.
- `IMP-006`, `IMP-007`, and `IMP-008`: unchanged `blocked` information/validation gaps.
- No impacts are resolved: the decision reduces risk but does not provide implementation evidence.
- No impacts are accepted: no explicit acceptance of residual risk was supplied.

## Acceptance and regression criteria

| ID | Criterion | Verifies |
| --- | --- | --- |
| `AC-001` | During the compatibility version, an iOS payload containing `displayName` decodes successfully, and a payload containing canonical `name` also decodes to the same profile value. | `INV-001`, `IMP-001` |
| `AC-002` | A previously persisted cache record containing only `displayName` remains readable; newly written records use canonical `name` according to the selected cache policy. | `INV-002`, `IMP-002` |
| `AC-003` | `displayName` is not removed before the version after the one-version deprecation window, and the changelog/versioned contract documents the removal boundary. | `INV-003`, `IMP-003` |
| `AC-004` | A contract/consumer inventory identifies generated clients, fixtures, and known external readers of `displayName`, with compatibility handling for each known consumer. | `IMP-004` |
| `AC-005` | If both keys are present with different values, the canonical `name` precedence and error/normalization behavior are deterministic and tested. | `IMP-005` |

## Stop check and planning handoff

The requirement is refined enough to hand off the compatibility design, but planning is blocked on three named gaps: (1) whether requests, responses, or both are in scope (`IMP-006`), (2) the concrete release/version identifiers for the one-version window (`IMP-007`), and (3) available compatibility/cache regression tests (`IMP-008`). The planning workflow should resolve those gaps before implementation tasks are finalized. No implementation plan is created here.
