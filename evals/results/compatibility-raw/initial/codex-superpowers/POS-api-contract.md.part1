# Requirements Impact Report — API field rename

## Requirement revision

`REQ-001`: Rename the public profile field `displayName` to `name`, while preserving the stated one-version deprecation promise and readability of existing cached profiles during that compatibility window. The exact wire and cache transition mechanics remain the pending decision.

## Current behavior and preserved invariants

| ID | Current behavior that must be preserved | Evidence | Level |
| --- | --- | --- | --- |
| `INV-001` | The iOS/mobile consumer decodes `displayName`. | Supplied fact: `ios/UserDTO.swift` decodes `displayName`. | `verified` |
| `INV-002` | Cached profile JSON persists `displayName`. | Supplied fact: cached profile JSON persists `displayName`. | `verified` |
| `INV-003` | The public API promises one-version deprecation for this rename. | Supplied fact: public API changelog promises one-version deprecation. | `verified` |

## Impact ledger

| ID | Category | Severity | Finding | Evidence | State |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Interfaces / Compatibility | high | Removing `displayName` immediately can prevent the existing mobile consumer from populating the user-visible value. | `ios/UserDTO.swift` decodes `displayName`. | `refining` |
| `IMP-002` | Data / Compatibility | high | Renaming the persisted key without a legacy-read path can make stored profile payloads unreadable or lose their value. | Cached profile JSON persists `displayName`. | `refining` |
| `IMP-003` | Compatibility / Regression | high | Immediate removal would contradict the public one-version deprecation promise. | Public API changelog promise. | `refining` |
| `IMP-004` | Interfaces / Compatibility | medium | Other clients or integrations may decode the old field; the supplied evidence does not enumerate them. | Inferred from the public API contract; consumer inventory is not supplied. | `inferred` |

## Focused decision needed — `NEEDS_DECISION`

Which compatibility mechanics should govern the promised one-version window?

1. **Dual-write / dual-read:** emit both `name` and deprecated `displayName`; readers accept either; remove `displayName` after one version. This maximizes wire compatibility but prolongs duplicate-field ambiguity.
2. **Single-write / dual-read:** emit only canonical `name`; readers accept `name` plus legacy `displayName`; migrate legacy cached data to `name`; remove the fallback after one version. This avoids new legacy data while preserving existing payloads.
3. **Other explicit policy:** specify a different wire/cache transition, including precedence when both keys exist, how old cached JSON is read or migrated, and the exact removal version.

No recorded decision has been supplied. The one-version deprecation promise is a constraint, not a selection among these mechanics. Please select one option before the requirement can be finalized or handed to implementation planning.

--- USER REVISION ---

Use a one-version compatibility window: emit and accept both fields, migrate cached payloads, then remove `displayName` only after the published window and compatibility evidence.

# Second response — recalculation after `DEC-001`

## Requirement revision

`REQ-001` is refined to: During the published one-version compatibility window, the API emits and accepts both canonical `name` and legacy `displayName`; cached profile payloads are migrated without data loss; `displayName` is removed only after the window ends and compatibility evidence confirms supported consumers no longer depend on it.

## Recorded decision

`DEC-001`: The user selected a one-version dual-write/dual-read compatibility window, with cached-payload migration, and explicitly conditioned removal of `displayName` on both the published window ending and compatibility evidence.

## Whole-set recalculation

| ID | Recalculated impact | Level | State | Evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | The mobile decoder must accept the canonical and legacy fields during the window; the selected dual-read policy prevents immediate loss of the displayed value. | `verified` | `mitigated` | Supplied `ios/UserDTO.swift` fact plus the user-selected dual-read window. | `affects` `REQ-001`, `INV-001`; `mitigated by` `DEC-001` |
| `IMP-002` | Stored payloads remain readable during the window and are explicitly migrated, reducing the risk of losing cached profile values. | `verified` | `mitigated` | Supplied cached-profile fact plus the user-selected migration requirement. | `affects` `REQ-001`, `INV-002`; `mitigated by` `DEC-001` |
| `IMP-003` | Immediate removal no longer conflicts with the one-version changelog promise because removal is explicitly gated on the published window and compatibility evidence. | `verified` | `resolved` | Supplied changelog promise and explicit user-selected removal gate. | `affects` `REQ-001`, `INV-003`; `resolved by` `DEC-001` |
| `IMP-004` | Other clients or integrations may still decode `displayName`; the selected policy requires compatibility evidence before removal, but the consumer inventory and evidence are not supplied. | `inferred` | `blocked` | Public-contract context implies possible consumers; supported-consumer inventory and compatibility results are unavailable. | `affects` `REQ-001`; `produces` `AC-004` |

## Delta

- `resolved`: `IMP-003`
- `mitigated`: `IMP-001`, `IMP-002`
- `unchanged`: none
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`
- `new`: none

The categories are disjoint and exhaustive across `IMP-001` through `IMP-004`.

## Acceptance criteria targets

| ID | Future criterion | Evidence / gap |
| --- | --- | --- |
| `AC-001` | During the one-version window, mobile decoding produces the same user-visible value from either `name` or legacy `displayName`; after the window, `name` is canonical. | Produced by `IMP-001`; decoder implementation and tests are not supplied. |
| `AC-002` | Existing cached JSON containing `displayName` remains readable, is migrated without data loss, and newly written payloads follow the selected dual-field window policy. | Produced by `IMP-002`; cache migration implementation and fixtures are not supplied. |
| `AC-003` | `displayName` is not removed before the published one-version window ends and compatibility evidence is recorded. | Produced by resolved `IMP-003`; release evidence is a future validation target. |
| `AC-004` | Compatibility evidence covers supported mobile clients, stored payloads, and other known consumers before `displayName` removal. | Produced by blocked `IMP-004`; consumer inventory and evidence are unavailable. |

## Stop check and planning handoff

The compatibility decision is recorded and the full impact set has been recalculated. `IMP-004` remains blocked pending consumer inventory and compatibility evidence; no implementation plan, work breakdown, or repository edit is included. The refined requirement, decision, risks, and `AC-001`–`AC-004` are ready for the selected planning workflow.
