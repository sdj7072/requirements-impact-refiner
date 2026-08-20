# Requirements impact refinement: API contract field rename

## Requirement revision

`REQ-001` — Rename the public API/profile field `displayName` to `name`, while honoring the published one-version deprecation promise and preserving existing cached-profile readability during that compatibility window.

The supplied evidence establishes the rename and a compatibility obligation, but does not select the exact wire and cache migration policy. That policy remains a decision needed below.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence level | Evidence | Link |
| --- | --- | --- | --- | --- |
| `INV-001` | The iOS `UserDTO` decodes the profile field under the key `displayName`. | `verified` | `ios/UserDTO.swift` — supplied `UserDTO` decoding fact | `must-preserve` `REQ-001` |
| `INV-002` | Cached profile JSON persists the key `displayName`. | `verified` | Supplied cached-profile persistence fact | `must-preserve` `REQ-001` |
| `INV-003` | The public API changelog promises one-version deprecation for the old field. | `verified` | Supplied public API changelog fact | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Category | Finding | Evidence level | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Interfaces | Removing `displayName` immediately can break the iOS decoder. | `verified` | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | Compatibility | The old field must remain supported for the promised one-version deprecation window; an immediate cutover would violate the published contract. | `verified` | `refining` | `affects` `REQ-001`, `INV-003`; `produces` `AC-002` |
| `IMP-003` | Data / Compatibility | Existing cached profile JSON contains `displayName`; a reader that only accepts `name` can fail to load existing profiles. | `verified` | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-003` |
| `IMP-004` | Interfaces | Other API consumers may decode `displayName` and are not identified by the supplied evidence. | `inferred` | `detected` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Data / Compatibility | The required persisted-cache write format, precedence when both keys exist, and removal timing are unspecified. | `unknown` | `blocked` | `affects` `REQ-001`, `INV-002`; `produces` `AC-005` |
| `IMP-006` | Regression | No compatibility fixtures or tests were supplied, so preservation of old payloads and the deprecation boundary cannot yet be demonstrated. | `unknown` | `blocked` | `affects` `REQ-001`, `INV-001`–`INV-003`; `produces` `AC-006` |

No authorization/privacy, state/concurrency, operations, or legal/policy impact is evidenced by the supplied facts; those areas are `new: none` for this scoped review. Deployment/rollback and external-consumer inventory remain unverified outside the supplied scope.

## Decision needed

Choose the compatibility policy for the one-version deprecation window:

1. **Dual-read, new-name write (recommended):** accept both `name` and legacy `displayName` in clients/cache readers, prefer `name` when both are present, and emit only `name` from the new API/cache writer while documenting the old field as deprecated for one version.
2. **Dual-read, dual-write:** accept both keys and emit both for one version, then remove `displayName`. This maximizes legacy interoperability but prolongs duplicate-field ambiguity.
3. **Versioned cutover:** expose `name` only in a new API version and retain `displayName` in the old version. This gives the clearest contract boundary but requires version negotiation/routing not evidenced here.

No `DEC-###` is recorded because no stakeholder selection was supplied. Silence is not acceptance.

## Whole-set recalculation before a decision

- `resolved: none` — no impact has evidence that it is eliminated.
- `mitigated: none` — the compatibility promise constrains the requirement but does not select an implementation policy.
- `unchanged: IMP-004` — possible external consumers remain unverified.
- `accepted: none` — no recorded decision exists.
- `deferred: none` — no intentional deferral was supplied.
- `blocked: IMP-005, IMP-006` — cache policy/test evidence is missing.
- `new: none`.

## Acceptance and regression criteria

| ID | Criterion | Evidence / status | Relationship |
| --- | --- | --- | --- |
| `AC-001` | During the compatibility window, an iOS payload containing the legacy key remains decodable. | Must be demonstrated against `ios/UserDTO.swift` behavior. | Verifies `INV-001`; produced by `IMP-001` |
| `AC-002` | The API contract documents `name` as the replacement and retains `displayName` as deprecated for exactly one promised version. | Must be verified against the public changelog/contract. | Verifies `INV-003`; produced by `IMP-002` |
| `AC-003` | Existing cached JSON containing only `displayName` remains readable, with no profile loss. | Must be demonstrated with a legacy cache fixture. | Verifies `INV-002`; produced by `IMP-003` |
| `AC-004` | The migration inventory identifies affected consumers, or explicitly records external consumers as out of scope. | Currently not supplied. | Produced by `IMP-004` |
| `AC-005` | The selected policy specifies behavior for old-only, new-only, and both-key payloads, including cache read/write and removal timing. | Currently blocked pending `DEC-001` (if selected). | Produced by `IMP-005` |
| `AC-006` | Compatibility tests cover legacy API responses, new responses, cached legacy JSON, and the post-deprecation removal boundary. | Currently no tests supplied; validation gap. | Produced by `IMP-006` |

## Stop check and planning handoff

The refined requirement is ready for the selected planning workflow only after the wire/cache policy is chosen and recorded as `DEC-001`; until then, `IMP-005` and `IMP-006` remain blocked. The handoff should carry this report, the supplied evidence links, the open external-consumer question, and `AC-001`–`AC-006`. This is a report-only handoff; no implementation work breakdown or plan is created here.
