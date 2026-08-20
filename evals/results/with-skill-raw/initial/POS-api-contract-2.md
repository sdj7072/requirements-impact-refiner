# POS-api-contract-2 — `displayName` → `name`

## Requirement revision

`REQ-001` (refined): Rename the public profile field from `displayName` to `name`, while preserving one-version compatibility for existing readers and persisted profile payloads in accordance with the public API changelog. The compatibility behavior and removal point must be explicit in the contract; this artifact stops at planning handoff and does not prescribe implementation.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | The iOS client decodes the profile field under the key `displayName`. | `verified` | `ios/UserDTO.swift` — supplied repository fact | `must-preserve` by `REQ-001` |
| `INV-002` | Cached profile JSON persists the key `displayName`. | `verified` | Cached profile JSON — supplied repository fact | `must-preserve` by `REQ-001` |
| `INV-003` | The public API changelog promises a one-version deprecation window. | `verified` | Public API changelog — supplied repository fact | `must-preserve` by `REQ-001` |

## Impact ledger

| ID | Impact | Severity | Evidence level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the existing iOS decoder. | Critical | `verified` | `ios/UserDTO.swift` decodes `displayName` | `mitigated` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | Rewriting only the response contract leaves cached profile JSON with a legacy key and can make reads inconsistent across versions. | High | `verified` | Cached profile JSON persists `displayName` | `detected` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | An external or older client may continue to read `displayName` during the promised deprecation window. | High | `inferred` | Public API changelog commitment; existing iOS decoder is one confirmed consumer | `mitigated` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | The exact response serialization, alias precedence, and version at which `displayName` is removed are not available in the supplied evidence. | High | `unknown` | No API schema, serializer, version matrix, or compatibility test was supplied/inspected | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Other consumers, generated SDKs, fixtures, or webhook/event contracts may reference `displayName`; the inspected scope cannot establish completeness. | Medium | `unknown` | Only `ios/UserDTO.swift`, cached profile JSON, and changelog facts were supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-005` |

## Focused decision

The rename needs a compatibility shape for the one-version window. The planning workflow should choose one of:

1. **Recommended — dual-read/dual-write window:** emit `name` as canonical, accept both keys, and emit `displayName` as a deprecated alias until the next version boundary.
2. **Read alias only:** emit only `name`, but accept `displayName` for one version; this reduces response duplication but risks older response-only clients.
3. **Versioned hard cutover:** expose `name` only in a new API version and leave the old version unchanged; this is clearest contractually but is broader than a field-level rename.

## Recorded decision

`DEC-001`: The supplied changelog promise is recorded as a compatibility constraint: `displayName` cannot be removed at the rename boundary and must remain supported through one version. The exact option above is **not selected by the supplied evidence** and remains a planning decision. `DEC-001` refines `REQ-001` and mitigates `IMP-001` and `IMP-003` at the requirement level.

## Whole-set recalculation

| Impact | Recalculated result |
| --- | --- |
| `IMP-001` | `mitigated`: the one-version constraint prevents an immediate breaking removal, but implementation/contract tests are still required. |
| `IMP-002` | `detected`: cached JSON migration and fallback behavior remain unspecified. |
| `IMP-003` | `mitigated`: the changelog commitment covers the known compatibility window; external consumer behavior remains unverified. |
| `IMP-004` | `blocked`: requires the API schema/serializer and explicit version matrix. |
| `IMP-005` | `blocked`: requires repository-wide consumer and contract inspection. |

Delta: `IMP-001` and `IMP-003` moved from `detected`/`refining` to `mitigated` under `DEC-001`; `IMP-002` is unchanged; `IMP-004` and `IMP-005` remain blocked; no new impact was identified.

## Acceptance and regression criteria

- `AC-001` (`IMP-001`): An existing iOS payload containing `displayName` continues to decode throughout the promised compatibility version.
- `AC-002` (`IMP-002`): A cached profile written before the rename remains readable, and its legacy key is handled deterministically during the compatibility window.
- `AC-003` (`IMP-003`): The published contract documents `name` as canonical, `displayName` as deprecated, and the precise version boundary for removal.
- `AC-004` (`IMP-004`): The selected response/request alias behavior, serializer rules, and removal version are captured in an authoritative API schema or compatibility test.
- `AC-005` (`IMP-005`): Repository-wide consumers, generated contracts, fixtures, and event/webhook payloads are searched; each remaining `displayName` use is migrated, covered by the compatibility adapter, or explicitly documented.

## Stop check and planning handoff

The requirement is refined enough for implementation planning, but the impact set is not fully resolved: `IMP-002` remains detected and `IMP-004`/`IMP-005` are blocked by missing contract and consumer evidence. No implementation plan is created here. The selected planning workflow must first choose the compatibility shape, obtain the missing API/version evidence, and carry `AC-001`–`AC-005` into the plan.
