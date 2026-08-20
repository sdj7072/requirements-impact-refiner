# Requirements Impact Refinement — API Contract

## Requirement revision

`REQ-001` (proposed): Rename the public API field `displayName` to `name`.

Refined requirement: the public contract should expose `name` as the replacement for `displayName`, while honoring the published one-version deprecation promise. Existing iOS decoding and cached profile data must remain usable during that compatibility window. The exact wire transition (whether both fields are emitted, which field is authoritative, and when the legacy field stops being accepted) remains the pending decision.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence | State | Link |
| --- | --- | --- | --- | --- |
| `INV-001` | The iOS user DTO decodes the `displayName` field. | `ios/UserDTO.swift` — supplied fact: `UserDTO` decodes `displayName` | `detected` | `must-preserve` `REQ-001` |
| `INV-002` | Cached profile JSON persists the `displayName` key. | `cached profile JSON` — supplied fact: persisted profile data contains `displayName` | `detected` | `must-preserve` `REQ-001` |
| `INV-003` | The public API changelog promises one-version deprecation for this rename. | `public API changelog` — supplied fact: one-version deprecation promise | `detected` | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Evidence level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can make the current iOS DTO fail to populate the user name. | `verified` | `ios/UserDTO.swift` — supplied fact that decoding reads `displayName` | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | A rename without a cache compatibility path can leave previously persisted profiles unreadable or blank after upgrade. | `verified` | `cached profile JSON` — supplied fact that persisted records use `displayName` | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | A breaking cutover before the promised deprecation window expires would violate the published API compatibility contract. | `verified` | `public API changelog` — supplied one-version deprecation promise | `refining` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | Other API consumers may still send or decode `displayName`; their release versions and migration behavior are not supplied. | `inferred` | Public API rename plus the one-version deprecation promise; no external consumer inventory supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | The authoritative read/write direction during the compatibility window is unspecified, so clients could observe divergent values if both keys are present. | `unknown` | No selected wire-transition policy supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-005` |

## Focused decision

Choose the compatibility transition for the one-version deprecation window:

1. **Dual-field compatibility (recommended):** emit `name`, accept/read both keys with an explicit precedence rule, and retain legacy `displayName` handling for one version.
2. **Read-legacy/write-new:** emit only `name`, but accept `displayName` on input and migrate iOS/cache readers during the window.
3. **Immediate cutover:** emit and accept only `name` (requires changing or withdrawing the published deprecation promise).

No explicit stakeholder selection is recorded in this artifact; therefore no `DEC-###` is created and no impact is marked `accepted`.

## Recorded decision

Pending. The requirement is refined by the existing one-version deprecation promise, but that constraint does not select an exact wire, precedence, or cache migration policy.

## Whole-set recalculation

The complete known impact set remains `IMP-001` through `IMP-005`. No impact is superseded because the requirement has not changed to a different field or compatibility horizon.

### Delta

- `resolved: none`
- `mitigated: none`
- `unchanged: IMP-001, IMP-002, IMP-003` (still `refining` pending the transition choice)
- `accepted: none` (no recorded decision)
- `deferred: none`
- `blocked: IMP-004, IMP-005`
- `new: none`

## Acceptance and regression criteria

| ID | Criterion | Evidence / relationship |
| --- | --- | --- |
| `AC-001` | During the compatibility window, an iOS payload using the legacy `displayName` key continues to populate the user name, and the new `name` key is supported according to the selected transition policy. | Verifies `INV-001`; produced by `IMP-001` |
| `AC-002` | Existing cached profile JSON containing `displayName` remains readable and yields the same user-visible name after the rename. | Verifies `INV-002`; produced by `IMP-002` |
| `AC-003` | The API contract and release behavior preserve the published one-version deprecation window before legacy handling is removed. | Verifies `INV-003`; produced by `IMP-003` |
| `AC-004` | The supported external-consumer/version matrix is identified and each supported consumer has a documented migration or compatibility assertion. | Resolves the information gap in `IMP-004` |
| `AC-005` | The selected wire policy specifies emission, acceptance, precedence, and cache behavior when `name` and `displayName` coexist, with contract tests covering those cases. | Resolves the policy gap in `IMP-005` |

## Stop check and planning handoff

Report-only handoff is appropriate. The refined requirement is to rename `displayName` to `name` while preserving iOS decoding, cached profile readability, and the published one-version deprecation promise. Planning must first record the pending transition decision, then carry `AC-001`–`AC-005` into API, client, cache, and compatibility validation. Remaining risks are the unknown external-consumer inventory (`IMP-004`) and unspecified coexistence/precedence policy (`IMP-005`). No implementation work breakdown is included here.
