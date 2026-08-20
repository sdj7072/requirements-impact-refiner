# Requirements impact refinement — API contract

## Requirement revision

`REQ-001` — Rename the public API profile field `displayName` to `name`, while honoring the published one-version deprecation promise for the old field. The transition must preserve existing iOS decoding and cached profile data during that compatibility window.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | The iOS `UserDTO` currently decodes the `displayName` field. | `verified` | Supplied repository fact: `ios/UserDTO.swift` decodes `displayName`. | `must-preserve` `REQ-001` |
| `INV-002` | Cached profile JSON currently persists `displayName`. | `verified` | Supplied repository fact: cached profile JSON persists `displayName`. | `must-preserve` `REQ-001` |
| `INV-003` | The public API has a one-version deprecation promise for the old field. | `verified` | Supplied repository fact: public API changelog promises one-version deprecation. | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Severity | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately would make the current iOS decoder unable to read the renamed response field. | High | `verified` | `ios/UserDTO.swift` decodes `displayName`. | `mitigated` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | Rewriting cached profile JSON without a compatibility reader could make existing on-device profiles unreadable. | High | `verified` | Cached profile JSON persists `displayName`. | `mitigated` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | A public response that exposes only `name` before the promised deprecation window ends would violate the published API contract for consumers still using `displayName`. | High | `verified` | Public API changelog promises one-version deprecation. | `mitigated` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | External consumers and undocumented persisted payload variants may still depend on `displayName`; their complete behavior is not available in the supplied evidence. | Medium | `unknown` | No external consumer inventory or compatibility fixtures supplied. | `blocked` | `affects` `REQ-001` |
| `IMP-005` | The API contract, iOS decoder, and cache migration can disagree on whether `name` or `displayName` is authoritative during rollout. | Medium | `inferred` | The supplied facts identify three independently affected representations: public API, iOS DTO, and cached JSON. | `mitigated` | `affects` `REQ-001`; `produces` `AC-004` |

## Decision needed

The supplied changelog commitment provides the compatibility policy: use a one-version transition in which the API introduces `name` and continues accepting/returning `displayName` as the deprecated alias. No additional stakeholder choice is required for this contract refinement.

## Recorded decision

`DEC-001` — Adopt the published one-version deprecation policy: add `name` as the canonical field, retain `displayName` as a deprecated compatibility alias for one supported API version, and remove the alias only after that version boundary. During the window, clients and cache readers must remain able to consume legacy payloads.

Evidence: supplied public API changelog fact. This decision refines `REQ-001` and mitigates `IMP-001`, `IMP-002`, `IMP-003`, and `IMP-005`.

## Whole-set recalculation

| Impact | Result after `DEC-001` | Rationale |
| --- | --- | --- |
| `IMP-001` | `mitigated` | The compatibility alias and one-version window preserve the existing iOS reader while it is migrated to `name`. |
| `IMP-002` | `mitigated` | Cache reads remain backward-compatible with stored `displayName`; writes can move to canonical `name` without invalidating old records. |
| `IMP-003` | `mitigated` | Retaining the deprecated alias through the promised version satisfies the published contract. |
| `IMP-004` | `blocked` | External consumer inventory and legacy payload fixtures remain unavailable. |
| `IMP-005` | `mitigated` | `name` is explicitly canonical, while `displayName` is an alias only during the transition. |

### Delta

- `resolved`: none; removal safety cannot be established until the compatibility boundary is verified.
- `mitigated`: `IMP-001`, `IMP-002`, `IMP-003`, `IMP-005` by `DEC-001`.
- `unchanged`: none.
- `accepted`: none; no risk is accepted as permanent.
- `deferred`: none.
- `blocked`: `IMP-004`, pending an external-consumer inventory and legacy payload fixtures.
- `new`: none.

## Acceptance and regression criteria

| ID | Criterion | Evidence level | Verifies |
| --- | --- | --- | --- |
| `AC-001` | During the one-version window, an API response containing either canonical `name` or legacy `displayName` remains decodable by the supported iOS client; after client migration, `name` is the canonical mapped value. | `verified` criterion derived from supplied decoder fact | `INV-001`, `IMP-001` |
| `AC-002` | Existing cached profile JSON containing `displayName` remains readable, and newly written cache records use `name` without losing the profile value. | `verified` criterion derived from supplied cache fact | `INV-002`, `IMP-002` |
| `AC-003` | The public contract documents `name` as canonical and `displayName` as deprecated, and the alias remains available for exactly the promised one-version compatibility window. | `verified` criterion derived from supplied changelog fact | `INV-003`, `IMP-003` |
| `AC-004` | Payloads containing both fields have deterministic precedence: `name` wins when present; `displayName` is the fallback only when `name` is absent. | `inferred` contract criterion | `IMP-005` |

## Stop check and planning handoff

The refined requirement is ready for the API-contract planning workflow. The material known impacts are mitigated by the recorded one-version policy; `IMP-004` remains blocked because the supplied evidence does not include external consumer inventory or legacy fixtures. Planning must retain the compatibility reader/alias, cache fallback, deterministic field precedence, and explicit deprecation/removal boundary, and must add validation for the blocked external-consumer gap before the alias is removed.
