# Requirements Impact Report

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Rename the public API field `displayName` to `name`. | User request |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Rename `displayName` to `name` while preserving the stated one-version deprecation promise and existing cached-profile readability during that compatibility window. The exact wire and cache transition mechanics remain the pending decision. | the pending decision | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `ios/UserDTO.swift` decodes the `displayName` field. | `verified` | Supplied fact: `ios/UserDTO.swift` decodes `displayName`. |
| `INV-002` | Cached profile JSON persists the `displayName` field. | `verified` | Supplied fact: cached profile JSON persists `displayName`. |
| `INV-003` | The public API changelog promises a one-version deprecation period for this field. | `verified` | Supplied fact: public API changelog promises one-version deprecation. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-004` | Supplied iOS decoder fact. |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-003` | Supplied cached-profile persistence fact. |
| `INV-003` | `REQ-001` | `IMP-005` | Supplied changelog compatibility promise. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Interfaces / Compatibility | high | `refining` | `verified` | The iOS decoder currently expects `displayName`; removing it immediately can make the existing client fail to populate the value. Supplied `ios/UserDTO.swift` fact. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | Data / Compatibility | high | `detected` | `verified` | Existing cached profile JSON contains persisted `displayName`. Supplied cached-profile fact. | `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | Data / Regression | high | `detected` | `inferred` | A cache reader that only understands the renamed key may lose the cached profile value; the reader/migration implementation is not present in the supplied evidence. | `INV-002` | the pending decision | `AC-002` |
| `IMP-004` | `REQ-001` | Interfaces / Compatibility | medium | `detected` | `inferred` | Other clients may decode `displayName`, but the supplied scope does not enumerate external consumers or their release versions. | `INV-001` | the pending decision | `AC-001` |
| `IMP-005` | `REQ-001` | Compatibility / Regression | high | `refining` | `verified` | Immediate removal without a one-version compatibility period would contradict the public API changelog promise. Supplied changelog fact. | `INV-003` | the pending decision | `AC-003` |

## Focused Decision Needed

Select the compatibility mechanics for the promised one-version window:

1. Emit canonical `name` and legacy `displayName` together for the window; readers accept either, and the next version removes `displayName`.
2. Emit only canonical `name`; readers (including iOS and cache loading) accept `displayName` as a legacy alias for the window, then remove the alias.
3. Specify another explicit wire/cache policy, including how old cached JSON is read and when the legacy field is removed.

No recorded decision exists yet. The one-version deprecation promise is a constraint, not a selection of these mechanics.

## Recorded Decision

None. The pending decision must be recorded before any impact can be marked `accepted`.

## Whole-Set Recalculation

No decision has been supplied, so the complete impact set remains `IMP-001` through `IMP-005`; no impact is superseded or silently accepted. `IMP-001` and `IMP-005` remain under refinement, while `IMP-002`, `IMP-003`, and `IMP-004` remain detected pending the compatibility choice and additional consumer/cache evidence.

## Delta

- resolved: none
- mitigated: none
- unchanged: `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`
- accepted: none
- deferred: none
- blocked: none
- new: none

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001`, `IMP-004` | `INV-001` | During the one-version window, an existing iOS payload using `displayName` and a new payload using `name` both produce the same user display value; after the window, the documented canonical field is `name`. | Add/execute iOS decoder compatibility coverage; current source is the supplied `ios/UserDTO.swift` fact. |
| `AC-002` | `REQ-001` | `IMP-002`, `IMP-003` | `INV-002` | A profile cached before the rename remains readable with its display value, and a profile cached after the rename reloads correctly; the retirement behavior is explicit after one version. | Add cache read/write or migration fixture coverage; implementation evidence is not supplied. |
| `AC-003` | `REQ-001` | `IMP-005` | `INV-003` | The API contract and changelog document `name` as canonical, identify `displayName` as deprecated for exactly one version, and verify that removal occurs only after that window. | Add contract/changelog release check; current support is the supplied changelog fact. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-003` | `detected` | Cache reader/migration behavior is not included in the supplied evidence. | the pending decision | API/cache owner |
| `IMP-004` | `detected` | External consumer inventory and supported client versions are unavailable. | the pending decision | API consumer owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Supplied facts only; the referenced product files are not present in this worktree. | `ios/UserDTO.swift` decoder fact; cached profile JSON persistence fact; public API changelog fact. | Those three baseline behaviors are treated as `verified` from the request; implementation details, external consumers, and tests remain `inferred` or unknown until inspected. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: rename `displayName` to `name` with one-version compatibility and cached-profile readability preserved. | `REQ-001`, `INV-001`–`INV-003`, `IMP-001`–`IMP-005` | Pending wire/cache mechanics; external consumer inventory; cache migration evidence. | `AC-001`–`AC-003` | Requirements refinement handoff; do not begin implementation planning until the focused compatibility decision is recorded. |
