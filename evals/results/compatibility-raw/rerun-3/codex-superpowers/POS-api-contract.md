# Requirements Impact Report: API field rename

## Requirement revision

`REQ-001` — Rename the public API field `displayName` to `name`, subject to the supplied one-version deprecation promise and preservation of existing consumer and persisted-profile compatibility during that window.

Evidence level: `verified` from the supplied facts only.

## Current behavior and preserved invariants

- `INV-001` — The iOS client decodes the `displayName` field from `ios/UserDTO.swift`; that existing payload decoding must remain readable during the promised compatibility window. Evidence: supplied fact, `ios/UserDTO.swift`.
- `INV-002` — Cached profile JSON persists the `displayName` field; existing cached profile data must remain interpretable during the promised compatibility window. Evidence: supplied fact, cached profile JSON.
- `INV-003` — The public API changelog promises one-version deprecation for this field transition. Evidence: supplied fact, public API changelog.

## Impact ledger

| ID | Finding | Evidence | State | Links |
| --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the existing iOS decoder. | `verified` — supplied fact, `ios/UserDTO.swift` | `refining` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Replacing or rewriting the field immediately can make cached profile JSON persisted under `displayName` unreadable. | `verified` — supplied fact, cached profile JSON | `refining` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | The rename must honor the public one-version deprecation promise; the exact wire and reader/writer mechanics are not selected by that promise alone. | `verified` for the promise; `unknown` for the mechanics — supplied fact, public API changelog | `refining` | affects `REQ-001`, `INV-003`; produces `AC-003` |

## One focused decision

What compatibility transition should implement the one-version deprecation window?

1. **Dual-field compatibility** — publish `name` while continuing to emit and accept `displayName` for the deprecation version, with an explicit precedence rule if both are present.
2. **Read-legacy/write-new** — publish and persist only `name`, while readers accept legacy `displayName` for the deprecation version.
3. **Compatibility adapter boundary** — keep the external/API transition policy at an adapter boundary, allowing the API and cache representations to be migrated independently while both legacy readers remain supported for the deprecation version.

No option is selected. The pending decision is required before a concrete `DEC-###` can be recorded.

## Recorded decision

None. No explicit stakeholder selection was supplied.

## Whole-set recalculation

No decision has been recorded, so all known impacts remain in scope. The supplied facts do not resolve the transition mechanics.

## Delta

- resolved: none
- mitigated: none
- unchanged: `IMP-001`, `IMP-002`, `IMP-003`
- accepted: none
- deferred: none
- blocked: none
- new: none

## Stop check and planning handoff

The refined requirement, preserved invariants, evidence, open compatibility risk, and acceptance criteria are ready for the next planning workflow after the pending decision is selected. This report intentionally stops before implementation planning.

### Acceptance criteria

- `AC-001` — Existing iOS payload decoding of `displayName` remains readable throughout the one-version deprecation window. Evidence basis: supplied fact, `ios/UserDTO.swift`; target behavior, not current proof.
- `AC-002` — Cached profile JSON persisted with `displayName` remains interpretable throughout the one-version deprecation window. Evidence basis: supplied fact, cached profile JSON; target behavior, not current proof.
- `AC-003` — The selected transition visibly honors the one-version deprecation promise for the public API. Evidence basis: supplied fact, public API changelog; exact verification depends on the pending decision.

--- USER REVISION ---
Use a one-version compatibility window: emit and accept both fields, migrate cached payloads, then remove displayName only after the published window and compatibility evidence. Recalculate every impact.

## Recalculated response

### Requirement revision

`REQ-001` — Rename the public API field `displayName` to `name` using a one-version compatibility window: emit and accept both fields, migrate cached payloads, and remove `displayName` only after the published window and compatibility evidence.

Evidence level: `verified` for the selected policy because it is an explicit user revision; evidence that the future compatibility conditions have been met is not supplied.

### Current behavior and preserved invariants

- `INV-001` — The iOS client decodes `displayName` from `ios/UserDTO.swift`; existing payload decoding must remain readable during the compatibility window. Evidence: supplied fact, `ios/UserDTO.swift`.
- `INV-002` — Cached profile JSON persists `displayName`; existing cached profile data must remain interpretable while it is migrated. Evidence: supplied fact, cached profile JSON.
- `INV-003` — The public API changelog promises one-version deprecation. Evidence: supplied fact, public API changelog.

### Impact ledger

| ID | Finding | Evidence | State | Links |
| --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the existing iOS decoder. | `verified` — supplied fact, `ios/UserDTO.swift`; selected dual-field emission and acceptance | `mitigated` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Replacing the field immediately can make cached profile JSON persisted under `displayName` unreadable. | `verified` — supplied fact, cached profile JSON; selected cache migration and continued dual-field acceptance | `mitigated` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | The rename must honor the public one-version deprecation promise. | `verified` — supplied fact, public API changelog; selected one-version window | `mitigated` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | Compatibility evidence and an inventory of external consumers are not supplied, so the safe point for removing `displayName` cannot yet be established. | `unknown` — future compatibility evidence and external consumer inventory unavailable | `blocked` | affects `REQ-001`, `INV-001`, `INV-002`, `INV-003`; produces `AC-004` |

### Recorded decision

`DEC-001` — “Use a one-version compatibility window: emit and accept both fields, migrate cached payloads, then remove displayName only after the published window and compatibility evidence.”

This decision refines `REQ-001` and mitigates `IMP-001`, `IMP-002`, and `IMP-003`. It does not resolve `IMP-004`; evidence is still required.

### Whole-set recalculation

The selected policy mitigates the immediate iOS, cached-payload, and published-window risks. The removal gate remains blocked because no compatibility evidence or external consumer inventory was supplied. No impact is resolved or accepted merely by selecting the policy.

### Delta

- resolved: none
- mitigated: `IMP-001`, `IMP-002`, `IMP-003`
- unchanged: none
- accepted: none
- deferred: none
- blocked: `IMP-004`
- new: none

### Stop check and planning handoff

The requirement is refined and the transition policy is recorded. Planning must retain the removal gate and obtain compatibility evidence plus an external-consumer inventory before treating the rename as complete. No implementation work or task breakdown is included.

### Acceptance criteria

- `AC-001` — During the one-version window, API payloads emit and accept both `name` and `displayName`, and the existing iOS decoder remains readable. Evidence gap: no compatibility test evidence supplied.
- `AC-002` — Cached profile payloads persisted with `displayName` are migrated and remain interpretable during the window. Evidence gap: no migration or fixture evidence supplied.
- `AC-003` — `displayName` is removed only after the published one-version window and compatibility evidence. Evidence basis: explicit user revision and public changelog promise; completion evidence not supplied.
- `AC-004` — Before removal, compatibility evidence covers known consumers and an external-consumer inventory has been assessed. Evidence gap: neither was supplied; this criterion remains blocked.
