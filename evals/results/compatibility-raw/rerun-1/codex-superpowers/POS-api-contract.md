# Requirements impact report — first response

## Requirement revision

`REQ-001`: Rename the public profile field `displayName` to `name`, while preserving the supplied compatibility constraint that the public API changelog promises a one-version deprecation period.

## Current behavior and preserved invariants

- `INV-001` — The iOS `UserDTO` currently decodes `displayName`; that reader remains usable during the promised compatibility window. **verified** — supplied repository fact: `ios/UserDTO.swift`.
- `INV-002` — Cached profile JSON currently persists `displayName`; existing cached profiles must remain representable/readable during the compatibility window. **verified** — supplied repository fact: cached profile JSON.
- `INV-003` — The public API contract includes a one-version deprecation promise for the renamed field. **verified** — supplied repository fact: public API changelog.

## Impact ledger

| ID | Impact | Evidence | State | Links |
| --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the iOS decoder. | `ios/UserDTO.swift` decodes `displayName` (supplied fact). | `refining` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | A rename that invalidates the persisted cache shape can strand cached profiles or require an unsafe cache transition. | Cached profile JSON persists `displayName` (supplied fact). | `refining` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | A one-version deprecation promise constrains the public API transition and release sequencing. | Public API changelog (supplied fact). | `refining` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | Behavior of consumers outside the supplied repository cannot be verified from the available evidence. | External consumer inventory/fixtures not supplied. | `blocked` | affects `REQ-001` |

## Acceptance criteria produced by the impacts

- `AC-001` — Existing iOS payload decoding continues to work throughout the one-version compatibility window. **verified basis:** `ios/UserDTO.swift`.
- `AC-002` — Existing cached profile JSON remains usable throughout the one-version compatibility window. **verified basis:** cached profile JSON persistence.
- `AC-003` — The shipped API transition honors the one-version deprecation promise. **verified basis:** public API changelog.

## Decision needed

How should the `displayName` → `name` contract transition be defined for the one-version window?

1. **Compatibility bridge (recommended):** publish `name` as the canonical field while accepting/serving `displayName` as a deprecated alias for one version, including a defined cache read/write bridge.
2. **Versioned contract:** introduce `name` only in a new API version; retain the old version’s `displayName` contract for the deprecation window.
3. **Coordinated cutover:** require all known clients and cached data to migrate before switching the contract, with the one-version period represented as a release/migration gate.

Please select one option (or specify a different transition). No decision has been recorded yet.

## Whole-set recalculation before selection

No user selection has been made, so no concrete `DEC-###` is allocated. The current impacts remain in scope:

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-002`, `IMP-003`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`
- `new`: none

## Stop check and planning handoff

The requirement is refined to the rename plus the supplied one-version deprecation constraint. Planning is blocked on the single contract-transition decision above and on the named external-consumer evidence gap (`IMP-004`). After a selection, recalculate the complete impact set and hand off the report (including all `AC-###` criteria) to the active Superpowers planning workflow. No implementation plan is created in this first response.

--- USER REVISION ---

Use a one-version compatibility window: emit and accept both fields, migrate cached payloads, then remove displayName only after the published window and compatibility evidence. Recalculate every impact. Continue the same evaluation. Do not write implementation tasks or modify the repository. Recalculate the entire known impact set, preserve accepted versus resolved semantics, and produce the report-only planning handoff. Preserve the existing .part1 byte-for-byte. Assemble the final transcript at .superpowers/sdd/2026-08-20-requirements-impact-refiner/task7-compat-rerun1/codex-superpowers/POS-api-contract.md by writing the exact .part1 content, then a `--- USER REVISION ---` separator, then the exact user revision above, then the complete second response. The second response delta must be pairwise disjoint and exhaustive and show resolved, mitigated, unchanged, accepted, deferred, blocked, and new using none where needed. Return only DONE plus the path.

# Requirements impact report — second response

## Requirement revision

`REQ-001` is revised by the explicit user selection: during one published compatibility version, emit and accept both `name` and `displayName`; migrate cached profile payloads; remove `displayName` only after the published window has ended and compatibility evidence is available.

## Current behavior and preserved invariants

- `INV-001` — The iOS `UserDTO` currently decodes `displayName`; it remains supported during the selected window. **verified** — supplied repository fact: `ios/UserDTO.swift`.
- `INV-002` — Cached profile JSON currently persists `displayName`; those payloads remain usable while cache migration occurs. **verified** — supplied repository fact: cached profile JSON.
- `INV-003` — The public API changelog promises one-version deprecation; the selected transition preserves that promise. **verified** — supplied repository fact: public API changelog.

## Recorded decision

`DEC-001`: “Use a one-version compatibility window: emit and accept both fields, migrate cached payloads, then remove displayName only after the published window and compatibility evidence.” This decision refines `REQ-001` and mitigates `IMP-001`, `IMP-002`, and `IMP-003`.

## Recalculated impact ledger

| ID | Impact | Evidence | State | Links |
| --- | --- | --- | --- | --- |
| `IMP-001` | Immediate removal could break the iOS decoder. | `ios/UserDTO.swift` decodes `displayName` (supplied fact); `DEC-001` retains acceptance during the window. | `mitigated` | affects `REQ-001`, `INV-001`; mitigated by `DEC-001`; produces `AC-001` |
| `IMP-002` | An incompatible cache shape could strand persisted profiles. | Cached profile JSON persists `displayName` (supplied fact); `DEC-001` requires migration before removal. | `mitigated` | affects `REQ-001`, `INV-002`; mitigated by `DEC-001`; produces `AC-002` |
| `IMP-003` | The public API transition must honor the one-version deprecation promise. | Public API changelog (supplied fact); `DEC-001` specifies the one-version window and evidence-gated removal. | `mitigated` | affects `REQ-001`, `INV-003`; mitigated by `DEC-001`; produces `AC-003` |
| `IMP-004` | Behavior of consumers outside the supplied repository remains unverifiable. | External consumer inventory/fixtures not supplied. | `blocked` | affects `REQ-001` |

## Acceptance criteria

- `AC-001` — During the published compatibility version, iOS payload decoding succeeds with `displayName`; removal occurs only after compatibility evidence. **Basis:** `ios/UserDTO.swift` plus the evidence gate in `DEC-001`.
- `AC-002` — Cached profile payloads are migrated and remain usable before `displayName` is removed. **Basis:** cached profile JSON persistence plus the migration requirement in `DEC-001`.
- `AC-003` — Both fields are emitted and accepted for exactly the published one-version window, and `displayName` is removed only after that window and compatibility evidence. **Basis:** public API changelog plus `DEC-001`.

## Delta

The categories below are pairwise disjoint and exhaustive over all known impacts:

- `resolved`: none — no implementation or compatibility evidence has been supplied, so no impact qualifies as resolved.
- `mitigated`: `IMP-001`, `IMP-002`, `IMP-003` — the selected transition directly reduces each risk, but evidence of completion is still required.
- `unchanged`: none.
- `accepted`: none — no residual risk was explicitly accepted; the user selected a mitigation policy.
- `deferred`: none.
- `blocked`: `IMP-004` — external consumer behavior remains a named evidence gap.
- `new`: none.

## Stop check and report-only planning handoff

The requirement is now refined with the selected compatibility mechanics, lifecycle gate, cache migration constraint, and evidence gate. Remaining risk is the blocked external-consumer assessment (`IMP-004`); the mitigated impacts require compatibility evidence before removal can be considered resolved. This is a report-only handoff containing `REQ-001`, `INV-001`–`INV-003`, `IMP-001`–`IMP-004`, `DEC-001`, and `AC-001`–`AC-003`. No implementation tasks or work breakdown are created.
