# Requirements impact report

## Requirement revision

`REQ-001` — Rename the public user display field from `displayName` to `name`, while preserving the promised one-version deprecation window and current consumers’ ability to read existing data during that window.

The exact transition mechanics remain pending; this revision does not select a wire, persistence, or migration policy.

## Current behavior and preserved invariants

- `INV-001` — `ios/UserDTO.swift` decodes `displayName`; that existing payload compatibility must be preserved through the promised deprecation window. (verified; supplied fact: `ios/UserDTO.swift`)
- `INV-002` — Cached profile JSON persists `displayName`; existing cached profile data must remain readable or be otherwise handled without silent loss during the window. (verified; supplied fact: cached profile JSON)
- `INV-003` — The public API changelog promises one-version deprecation for this rename; that compatibility commitment must be honored. (verified; supplied fact: public API changelog)

## Impact ledger

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing `displayName` immediately can break the iOS decoder. | verified | `ios/UserDTO.swift` decodes `displayName` (supplied fact) | refining | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Renaming or rewriting the field without compatibility handling can strand or invalidate cached profile JSON containing `displayName`. | verified | Cached profile JSON persists `displayName` (supplied fact) | refining | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | A transition that removes the old public field before one version violates the published deprecation promise. | verified | Public API changelog promises one-version deprecation (supplied fact) | refining | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | The supplied evidence does not establish the exact compatibility mechanics or the version boundary used to determine the one-version window. | unknown | No transition policy or version identifier supplied | blocked | affects `REQ-001`; produces `AC-004` |

## One focused decision

Which compatibility contract should `REQ-001` adopt for the one-version deprecation window?

1. **Dual public representation** — expose `name` as the replacement while continuing to expose/read `displayName` for the window, with an explicitly defined precedence when both are present.
2. **Replacement plus legacy-read compatibility** — make `name` the only emitted public field while accepting `displayName` on input and in persisted cache reads for the window.
3. **Explicit migration boundary** — define a versioned migration for clients and cached data, with the old field removed only after that boundary.

Please select one option (or state a different explicit contract). No decision has been recorded yet; therefore no concrete `DEC-###` exists.

## Recorded decision

None. The pending decision is the compatibility contract above.

## Whole-set recalculation

All known impacts remain applicable; no requirement has been selected that resolves or accepts them.

## Delta

- resolved: none
- mitigated: none
- unchanged: `IMP-001`, `IMP-002`, `IMP-003`
- accepted: none
- deferred: none
- blocked: `IMP-004`
- new: none

## Stop check and planning handoff

Stop before implementation planning. The report is ready to hand off after the pending compatibility-contract choice is explicitly recorded. Remaining risks are the iOS decoder breakage, cached-profile compatibility, and compliance with the public one-version deprecation promise; the exact version boundary and mechanics remain blocked.

Acceptance criteria for the eventual selected contract:

- `AC-001` — Existing iOS payload decoding continues to work through the one-version window. (produced by `IMP-001`; target supported by supplied `ios/UserDTO.swift` evidence)
- `AC-002` — Existing cached profile JSON containing `displayName` remains readable or is safely migrated through the window. (produced by `IMP-002`; target supported by supplied cache-persistence evidence)
- `AC-003` — The public API honors the one-version `displayName` deprecation promise before removal. (produced by `IMP-003`; target supported by supplied changelog evidence)
- `AC-004` — The selected contract names the version boundary and exact compatibility mechanics. (produced by `IMP-004`; currently a validation gap)

--- USER REVISION ---
Use a one-version compatibility window: emit and accept both fields, migrate cached payloads, then remove displayName only after the published window and compatibility evidence.

# Requirements impact report — recalculated after decision

## Requirement revision

`REQ-001` — Rename the public user display field from `displayName` to `name` using a one-version compatibility window: emit and accept both fields, migrate cached payloads, then remove `displayName` only after the published window and compatibility evidence.

## Current behavior and preserved invariants

- `INV-001` — `ios/UserDTO.swift` decodes `displayName`; existing payload compatibility remains preserved during the one-version window. (verified; supplied fact: `ios/UserDTO.swift`)
- `INV-002` — Cached profile JSON persists `displayName`; cached payloads remain handled through migration during the window. (verified; supplied fact: cached profile JSON)
- `INV-003` — The public API changelog promises one-version deprecation; `displayName` is not removed before that published window and compatibility evidence exist. (verified; supplied fact: public API changelog)

## Impact ledger

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Immediate removal could break the iOS decoder; the selected dual-field window reduces this risk. | verified | `ios/UserDTO.swift` decodes `displayName` (supplied fact); explicit user revision | mitigated | affects `REQ-001`, `INV-001`; produces `AC-001`; mitigated by `DEC-001` |
| `IMP-002` | Existing cached profile JSON could be stranded; the selected cached-payload migration reduces this risk. | verified | Cached profile JSON persists `displayName` (supplied fact); explicit user revision | mitigated | affects `REQ-001`, `INV-002`; produces `AC-002`; mitigated by `DEC-001` |
| `IMP-003` | Removing the old field before the promised window would violate the public contract; the selected timing constraint reduces this risk pending evidence. | verified | Public API changelog promises one-version deprecation (supplied fact); explicit user revision | mitigated | affects `REQ-001`, `INV-003`; produces `AC-003`; mitigated by `DEC-001` |
| `IMP-004` | The previously missing transition mechanics and window rule are now specified, but repository evidence that they are implemented is not available in this report. | unknown | Explicit user revision supplies the contract; no implementation evidence supplied | resolved | affects `REQ-001`; produces `AC-004`; resolved by `DEC-001` as a requirement-level design constraint |

## Recorded decision

`DEC-001` — The user selected: “Use a one-version compatibility window: emit and accept both fields, migrate cached payloads, then remove displayName only after the published window and compatibility evidence.”

This decision refines `REQ-001` and mitigates `IMP-001`, `IMP-002`, and `IMP-003`; it resolves the previously unspecified contract mechanics in `IMP-004` at the requirement level. It does not claim implementation or compatibility-test evidence.

## Whole-set recalculation

Every known impact was reconsidered. No impact was superseded, accepted, deferred, or newly introduced by the revision.

## Delta

- resolved: `IMP-004`
- mitigated: `IMP-001`, `IMP-002`, `IMP-003`
- unchanged: none
- accepted: none
- deferred: none
- blocked: none
- new: none

## Stop check and planning handoff

Stop before implementation planning. The refined requirement and decision are ready for the selected planning workflow. Remaining risks are implementation and compatibility evidence: iOS decoding must work during the window, cached payload migration must preserve data, and removal must wait for the published window and evidence. No tasks, work breakdown, or repository edits are included.

Acceptance criteria:

- `AC-001` — During the one-version window, payloads containing either field are accepted and existing iOS decoding remains functional; after the window, removal occurs only with compatibility evidence. (produced by `IMP-001`; current code evidence is the supplied decoder fact, implementation validation remains open)
- `AC-002` — Cached payloads containing `displayName` are migrated without data loss during the window. (produced by `IMP-002`; current cache evidence is supplied, migration validation remains open)
- `AC-003` — Both fields are emitted during the window, and `displayName` is removed only after the published window and compatibility evidence. (produced by `IMP-003`; current changelog evidence is supplied, implementation validation remains open)
- `AC-004` — The contract is exactly: one version, emit and accept both fields, migrate cached payloads, then remove `displayName` after the published window and compatibility evidence. (produced by `IMP-004`; supported by `DEC-001`, with implementation evidence still open)
