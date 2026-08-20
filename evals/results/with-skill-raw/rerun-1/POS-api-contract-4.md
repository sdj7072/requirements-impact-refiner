# Requirements impact refinement — API contract

## Requirement revision

`REQ-001` — Rename the public user/profile field `displayName` to `name`, while honoring the already-published one-version deprecation promise. The rename must preserve existing iOS decoding and cached-profile readability during that compatibility window, and must define the transition behavior for both response payloads and persisted profile JSON.

Scope is limited to the API contract and the directly supplied consumers/storage facts. No additional repository files or external consumers were inspected in this rerun.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | The iOS `UserDTO` currently decodes the field named `displayName`. | `verified` | Supplied repository fact: `ios/UserDTO.swift` decodes `displayName`. | `must-preserve` `REQ-001` |
| `INV-002` | Cached profile JSON currently persists the field named `displayName`. | `verified` | Supplied repository fact: cached profile JSON persists `displayName`. | `must-preserve` `REQ-001` |
| `INV-003` | Existing clients receive a one-version deprecation window for the public field rename. | `verified` | Supplied repository fact: the public API changelog promises one-version deprecation. | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Category | Finding | Level | State | Evidence / scope | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Interfaces | Removing `displayName` immediately breaks the current iOS decoder. | `verified` | `mitigated` | `ios/UserDTO.swift` decodes `displayName`; the one-version deprecation window requires a transition payload. | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Interfaces | Public API consumers may still read `displayName` during the deprecation version. | `inferred` | `mitigated` | The public API changelog promises one-version deprecation; external consumer inventory was not supplied. | affects `REQ-001`, `INV-003`; produces `AC-002` |
| `IMP-003` | Compatibility | Existing cached profile JSON may be unreadable if only `name` is accepted. | `verified` | `mitigated` | Cached profile JSON persists `displayName`. | affects `REQ-001`, `INV-002`; produces `AC-003` |
| `IMP-004` | Data | Dual field handling can create conflicting values if `name` and `displayName` differ. | `inferred` | `mitigated` | Both the renamed API field and legacy persisted field are in scope; no precedence rule was supplied. | affects `REQ-001`; produces `AC-004` |
| `IMP-005` | Regression | No compatibility test, fixture, or version-boundary evidence was supplied for the transition. | `unknown` | `blocked` | Fresh rerun was restricted to the supplied facts; test inventory and release/version identifiers were unavailable. | affects `REQ-001`; produces `AC-005` |
| `IMP-006` | Operations | Rollback or mixed-version deployments may emit/read different field names. | `inferred` | `deferred` | A one-version public deprecation implies mixed client/server versions; deployment and rollback details were not supplied. | affects `REQ-001`; produces `AC-006` |
| `IMP-007` | Authorization/Privacy | No change to authorization or privacy semantics is indicated by a display-field rename. | `unknown` | `blocked` | No auth/privacy artifacts were supplied, so absence of impact cannot be verified. | affects `REQ-001`; produces `AC-007` |
| `IMP-008` | Legal/Policy | No policy requirement for the display field was supplied. | `unknown` | `blocked` | Legal, retention, and regional-policy artifacts were out of the supplied evidence scope. | affects `REQ-001`; produces `AC-008` |

## Decision needed

The requirement supplies the compatibility policy: honor the public changelog’s one-version deprecation. The contract still needs an explicit transition wire rule for that version. The recorded choice below adopts the compatibility-preserving option implied by the supplied iOS and cache invariants.

## Recorded decision

`DEC-001` — During the one-version deprecation window, responses expose canonical `name` and retain legacy `displayName` as a deprecated alias with the same value. Readers accept both names, preferring `name` when both are present and falling back to `displayName`; writers/readers for cached profile JSON must preserve readability of legacy `displayName`. After the window, `displayName` may be removed only in a separately versioned contract change with migration evidence.

Evidence basis: this decision is constrained by the supplied `ios/UserDTO.swift` decoder, cached JSON persistence fact, and public changelog promise. Exact release/version identifiers remain unknown.

## Whole-set recalculation

The decision does not eliminate the compatibility work; it reduces the breakage risk by defining an alias and precedence rule.

| ID | Recalculated result | Level | State | Required verification |
| --- | --- | --- | --- | --- |
| `IMP-001` | Immediate iOS break is avoided while the deprecated alias remains readable. | `verified` | `mitigated` | `AC-001` |
| `IMP-002` | Existing public consumers can continue reading `displayName` for one version; unknown consumers still require contract-level testing. | `inferred` | `mitigated` | `AC-002` |
| `IMP-003` | Legacy cached JSON remains readable through fallback decoding. | `verified` | `mitigated` | `AC-003` |
| `IMP-004` | Conflicts are deterministic: `name` wins, and legacy value is fallback-only. | `inferred` | `mitigated` | `AC-004` |
| `IMP-005` | Versioned compatibility tests are still absent from supplied evidence. | `unknown` | `blocked` | `AC-005`; requires test/release inventory |
| `IMP-006` | Mixed-version behavior is covered at the field-contract level, but deployment rollback behavior remains unverified. | `inferred` | `deferred` | `AC-006`; requires deployment evidence |
| `IMP-007` | No authorization/privacy change is intended, but supplied evidence cannot verify this. | `unknown` | `blocked` | `AC-007`; requires auth/privacy review |
| `IMP-008` | No legal/policy change is intended, but supplied evidence cannot verify this. | `unknown` | `blocked` | `AC-008`; requires policy review |

### Delta

- `resolved`: none.
- `mitigated`: `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` through `DEC-001`.
- `unchanged`: none.
- `accepted`: none; no residual risk is accepted by an explicit decision.
- `deferred`: `IMP-006`, pending deployment/rollback evidence.
- `blocked`: `IMP-005`, `IMP-007`, `IMP-008`, each with a named evidence gap above.
- `new`: none.

## Acceptance and regression criteria

| ID | Criterion | Evidence target | Relationship |
| --- | --- | --- | --- |
| `AC-001` | During the deprecation version, an iOS payload containing legacy `displayName` remains decodable; a payload containing canonical `name` is also decodable. | iOS decoder compatibility test or fixture covering both payloads. | verifies `INV-001`; produced by `IMP-001` |
| `AC-002` | The public response contract documents `name` as canonical and `displayName` as deprecated for exactly one version, with removal/version boundary identified. | Versioned API schema/changelog and contract test. | verifies `INV-003`; produced by `IMP-002` |
| `AC-003` | Cached profile JSON containing only `displayName` loads successfully and can be rewritten without data loss; new writes use `name` as canonical. | Cache migration/read-write fixture. | verifies `INV-002`; produced by `IMP-003` |
| `AC-004` | When both fields are present with different values, `name` is selected deterministically; when `name` is absent, `displayName` is used. | Decoder precedence test. | produced by `IMP-004` |
| `AC-005` | Compatibility tests run across the pre-rename, deprecation, and post-deprecation contract versions before removing the alias. | Test and release matrix; currently unavailable. | produced by `IMP-005` |
| `AC-006` | Mixed-version rollout and rollback behavior does not strand either field format. | Deployment/rollback smoke test; currently unavailable. | produced by `IMP-006` |
| `AC-007` | The rename changes no authorization, access, consent, deletion, or privacy behavior. | Auth/privacy review evidence; currently unavailable. | produced by `IMP-007` |
| `AC-008` | The rename satisfies any applicable display-name policy and retention requirements. | Policy review evidence; currently unavailable. | produced by `IMP-008` |

## Stop check and planning handoff

The API-contract requirement is refined and decision-linked. The contract should plan for canonical `name`, one-version deprecated `displayName` alias, deterministic reader precedence, and legacy cache readability. Remaining risks are explicitly deferred or blocked because release/version, test, deployment, authorization/privacy, and policy evidence was not supplied. Planning may proceed only with those evidence gaps tracked as validation inputs; this report intentionally stops short of an implementation work breakdown.
