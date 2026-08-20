# Requirements impact refinement: API field rename

## Requirement revision

`REQ-001` — Rename the public user field from `displayName` to canonical field `name`, while preserving one-version backward compatibility. During the deprecation version, responses and readers must remain compatible with existing consumers and cached profiles that use `displayName`; after that window, `name` is the supported contract and `displayName` may be removed only through an explicitly versioned breaking change.

This revision treats the changelog's one-version deprecation promise as part of the requirement, not as optional release guidance.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | The iOS user DTO currently decodes the `displayName` field. | `verified` | Supplied repository fact: `ios/UserDTO.swift` decodes `displayName`. | `must-preserve` by `REQ-001` |
| `INV-002` | Cached profile JSON can contain the persisted key `displayName`. | `verified` | Supplied repository fact: cached profile JSON persists `displayName`. | `must-preserve` by `REQ-001` |
| `INV-003` | The public API has promised a one-version deprecation period for this rename. | `verified` | Supplied repository fact: public API changelog. | `must-preserve` by `REQ-001` |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links / acceptance |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the existing iOS decoder. | `verified` | `ios/UserDTO.swift` decodes `displayName`. | `mitigated` | A compatibility reader/alias is required; produces `AC-001`. |
| `IMP-002` | Changing the cached key immediately can make existing profile data unreadable or cause a profile value to disappear after upgrade. | `verified` | Cached profile JSON persists `displayName`. | `mitigated` | The migration must read the legacy key during the deprecation version; produces `AC-002`. |
| `IMP-003` | Removing or ceasing to support `displayName` before one version violates the published API promise. | `verified` | Public API changelog promises one-version deprecation. | `mitigated` | Deprecation timing and removal must be versioned; produces `AC-003`. |
| `IMP-004` | Other API consumers or generated contracts may still use `displayName`. | `inferred` | `displayName` is a public API field and the changelog documents its compatibility window; no complete consumer inventory was supplied. | `detected` | Contract and consumer verification remain required; produces `AC-004`. |
| `IMP-005` | The exact release/version boundary and post-window removal mechanism are not identified in the supplied facts. | `unknown` | Changelog commitment is supplied, but no version numbers, schema, or release policy were supplied. | `blocked` | Named information gap: the deprecation and removal versions plus authoritative API schema. |

### Acceptance criteria

| ID | Criterion | Verifies |
| --- | --- | --- |
| `AC-001` | A payload containing legacy `displayName` remains decodable by the existing iOS client throughout the one-version compatibility window, and a payload using canonical `name` is also decoded to the same user-name value. | `INV-001`, `IMP-001` |
| `AC-002` | A cached profile containing only `displayName` is read without data loss and is migrated or rewritten to the canonical `name` representation during the compatibility window; the canonical representation can subsequently be read. | `INV-002`, `IMP-002` |
| `AC-003` | The published API contract and release notes identify `name` as canonical, retain `displayName` as deprecated for exactly the promised one version, and do not remove the legacy field earlier. | `INV-003`, `IMP-003` |
| `AC-004` | API contract fixtures/compatibility checks cover both `name` and legacy `displayName`, including the deprecation-version behavior and the planned post-window behavior. | `IMP-004` |

## Focused decision

The supplied facts require a compatibility choice for the deprecation version. The recommended option is:

1. `DEC-001` (recommended): make `name` canonical immediately, accept/read `displayName` as a deprecated legacy alias for one version, and preserve cached-profile reads with a one-time migration or rewrite to `name`. Document removal only after the promised window.

This preserves existing iOS and cached data while making the new contract unambiguous. Alternatives are (a) keep writing both fields for the window, which maximizes wire compatibility but prolongs ambiguity, or (b) make the rename an immediate breaking change, which conflicts with `INV-003` and is therefore not acceptable under the stated facts.

## Recorded decision

`DEC-001` — Adopt the recommended compatibility-window design: `name` is canonical; `displayName` remains readable as a deprecated alias for one API version; legacy cached JSON remains readable and is migrated/re-written; removal is deferred until the documented window ends.

Because no interactive user decision was provided, this is a requirement-derived recommendation, not evidence that a stakeholder has accepted the risk. The exact version boundary remains blocked by `IMP-005`.

## Whole-set recalculation

| Impact | Result after `DEC-001` | Rationale |
| --- | --- | --- |
| `IMP-001` | `mitigated` | Legacy iOS decoding remains supported during the window. |
| `IMP-002` | `mitigated` | Legacy cached keys remain readable and are migrated/re-written. |
| `IMP-003` | `mitigated` | Removal is deferred until after the promised version. |
| `IMP-004` | `detected` | The design supports external consumers, but no consumer inventory or contract fixtures were supplied. |
| `IMP-005` | `blocked` | Exact release/version identifiers and authoritative schema remain unavailable. |

### Delta

- `mitigated`: `IMP-001`, `IMP-002`, `IMP-003`.
- `unchanged`: `IMP-004` remains detected because the supplied evidence does not establish complete consumer coverage.
- `blocked`: `IMP-005` remains blocked pending the exact deprecation/removal versions and API schema.
- `new`: none.
- `resolved`, `accepted`, `deferred`, `superseded`: none. No impact is marked `accepted` because no stakeholder acceptance was supplied.

## Stop check and planning handoff

The requirement is refined enough for implementation planning, but the handoff must carry the explicit information gap: identify the exact compatibility release, removal release, and authoritative public API schema before scheduling removal. Do not claim the rename is complete until `AC-001` through `AC-004` are demonstrated.

Planning handoff summary:

- Implement canonical `name` with one-version legacy read compatibility for `displayName`.
- Preserve and migrate cached profile JSON from `displayName` to `name` without data loss.
- Update the public API contract/changelog and compatibility fixtures.
- Validate iOS decoding, cache migration, and both-version contract behavior.
- Resolve `IMP-005` using the release/version policy and authoritative schema; then recalculate the ledger before planning legacy-field removal.
