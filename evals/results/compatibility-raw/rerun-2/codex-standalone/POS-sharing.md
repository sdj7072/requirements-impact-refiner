# Requirements Impact Refinement Report

## Requirement revision

`REQ-001` — Make shared links permanent. The revised requirement must define how permanence interacts with the existing authorization-revocation behavior and signing-key rotation; no exact transition policy has been selected.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Share tokens expire after seven days. | `verified` | User-supplied fact: “share tokens currently expire after seven days” | `REQ-001` must preserve or explicitly revise this behavior |
| `INV-002` | Permission changes revoke active share tokens. | `verified` | User-supplied fact: “permission changes revoke active tokens” | `REQ-001` must preserve or explicitly revise this behavior |
| `INV-003` | Token-signing keys rotate every 90 days. | `verified` | User-supplied fact: “token signing keys rotate every 90 days” | `REQ-001` must remain compatible with this operational invariant or explicitly revise it |

Repository artifacts and implementation scope were not supplied or inspected in this standalone turn; repository-dependent effects are therefore recorded as unknown below.

## Impact ledger

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Permanent links conflict with the current seven-day token expiry unless the requirement explicitly defines what “permanent” means for the link and its authorization material. | `verified` | User-supplied fact corresponding to `INV-001` | `refining` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Permanent links may conflict with the current revocation effect of permission changes; the requested change does not state whether revocation remains authoritative. | `verified` | User-supplied fact corresponding to `INV-002` | `refining` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | Permanent links must account for 90-day signing-key rotation; the supplied request does not define the required rollover behavior for already-issued links. | `verified` | User-supplied fact corresponding to `INV-003` | `refining` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | The implementation’s data, interface, authorization, compatibility, and operational effects cannot be assessed without repository scope or artifacts. | `unknown` | No repository evidence supplied or inspected in this turn | `blocked` | affects `REQ-001`; produces `AC-004` |

## One focused decision

What authorization policy should “permanent” shared links use?

1. Permanent link identity, with access still rechecked on use: permission changes continue to revoke access, and key rotation must remain transparent to existing links.
2. Permanent access grant: permission changes do not revoke an already-created link; key rotation must remain transparent to existing links.
3. Permanent link identity with renewable authorization tokens: permission revocation remains configurable or explicit, and rollover is handled through token renewal.

No option has been selected. The pending decision must be recorded before a concrete `DEC-###` can be created.

## Whole-set recalculation

No decision was made, so all known impacts remain in their current states. `IMP-004` remains blocked because the repository evidence gap is unchanged.

## Delta

- `resolved: none`
- `mitigated: none`
- `unchanged: IMP-001, IMP-002, IMP-003`
- `accepted: none`
- `deferred: none`
- `blocked: IMP-004`
- `new: none`

## Stop check and planning handoff

Stop at the focused decision. No decision ID, implementation plan, work breakdown, or repository edit is created. After the pending policy choice and repository evidence target are supplied, refine `REQ-001`, recalculate the complete ledger, and define the resulting acceptance criteria.

### Acceptance criteria

| ID | Criterion | Evidence / gap | Links |
| --- | --- | --- | --- |
| `AC-001` | The selected definition of permanence supersedes or preserves the seven-day expiry behavior consistently for shared-link access. | Current seven-day expiry is verified; implementation behavior is an evidence gap. | verifies `INV-001`; produced by `IMP-001` |
| `AC-002` | The selected policy gives a deterministic result when permissions change after a shared link is created. | Current revocation behavior is verified; selected policy is pending. | verifies `INV-002`; produced by `IMP-002` |
| `AC-003` | Existing permanent links remain valid or fail according to the selected policy across each 90-day signing-key rotation. | Key rotation cadence is verified; rollover behavior is an evidence gap. | verifies `INV-003`; produced by `IMP-003` |
| `AC-004` | Repository-specific data, interface, authorization, compatibility, and operational effects are identified and validated. | Repository scope and artifacts were not supplied or inspected. | produced by `IMP-004` |


--- USER REVISION ---
Make links non-expiring, but preserve revocation on permission changes and key rotation. I explicitly accept exposure until an explicit revoke event. Recalculate every impact.
# Requirements Impact Refinement Report

## Requirement revision

`REQ-001` — Make links non-expiring, while preserving revocation on permission changes and continued validity across signing-key rotation. The requester explicitly accepts exposure until an explicit revoke event.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Share tokens expire after seven days. | `verified` | User-supplied fact: “share tokens currently expire after seven days” | `REQ-001` explicitly revises this expiry behavior |
| `INV-002` | Permission changes revoke active share tokens. | `verified` | User-supplied fact: “permission changes revoke active tokens” | Must be preserved by `REQ-001` |
| `INV-003` | Token-signing keys rotate every 90 days. | `verified` | User-supplied fact: “token signing keys rotate every 90 days” | Must remain compatible with `REQ-001` |
 
Repository artifacts and implementation scope were not supplied or inspected in this standalone evaluation; repository-dependent effects remain unknown.

## Impact ledger

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | The current seven-day expiry is incompatible with the revised non-expiring-link requirement. | `verified` | Current expiry fact and explicit user revision | `resolved` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | The previously ambiguous interaction between permanence and permission-change revocation is resolved by preserving revocation. | `verified` | Current revocation fact and explicit user revision | `resolved` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | The previously ambiguous interaction between permanence and 90-day signing-key rotation is resolved by preserving key rotation compatibility. | `verified` | Current rotation fact and explicit user revision | `resolved` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | The implementation’s data, interface, authorization, compatibility, and operational effects cannot be assessed without repository scope or artifacts. | `unknown` | No repository evidence supplied or inspected in this evaluation | `blocked` | affects `REQ-001`; produces `AC-004` |
| `IMP-005` | Until an explicit revoke event, a non-expiring link may remain usable longer than the current seven-day window, creating exposure the requester has explicitly accepted. | `verified` | Explicit user revision: “I explicitly accept exposure until an explicit revoke event.” | `accepted` | affects `REQ-001`; linked to `DEC-001`; produces `AC-005` |

## Recorded decision

`DEC-001` — Selected policy: links are non-expiring; permission changes continue to revoke access; signing-key rotation remains compatible with existing links; exposure until an explicit revoke event is accepted.

Evidence: explicit user revision: “Make links non-expiring, but preserve revocation on permission changes and key rotation. I explicitly accept exposure until an explicit revoke event.”

## Whole-set recalculation

All known impacts were recalculated after `DEC-001`. `IMP-001`, `IMP-002`, and `IMP-003` are resolved by the explicit requirement and its preserved invariants. `IMP-004` remains blocked by the repository evidence gap. `IMP-005` is accepted through `DEC-001`; it is not resolved because the exposure remains by design.

## Delta

- `resolved: IMP-001, IMP-002, IMP-003`
- `mitigated: none`
- `unchanged: none`
- `accepted: IMP-005`
- `deferred: none`
- `blocked: IMP-004`
- `new: none`

## Stop check and planning handoff

The requirement is refined and the policy decision is recorded. Remaining risk is the explicitly accepted exposure until revocation, plus the blocked repository-evidence gap. No tasks, implementation plan, work breakdown, or repository edit is created.

### Acceptance criteria

| ID | Criterion | Evidence / gap | Links |
| --- | --- | --- | --- |
| `AC-001` | Shared links do not expire after seven days solely because of token age. | Non-expiry is explicitly selected; implementation behavior is an evidence gap. | verifies `INV-001`; produced by `IMP-001` |
| `AC-002` | A permission change revokes access through an already-created shared link. | Revocation is an explicit preserved invariant; implementation behavior is an evidence gap. | verifies `INV-002`; produced by `IMP-002` |
| `AC-003` | Existing non-expiring links continue to follow the selected policy across each 90-day signing-key rotation. | Rotation cadence is verified; rollover implementation is an evidence gap. | verifies `INV-003`; produced by `IMP-003` |
| `AC-004` | Repository-specific data, interface, authorization, compatibility, and operational effects are identified and validated. | Repository scope and artifacts were not supplied or inspected. | produced by `IMP-004` |
| `AC-005` | The accepted exposure lasts only until an explicit revoke event, after which the link no longer grants access. | Exposure acceptance is explicit; revoke implementation is an evidence gap. | produced by `IMP-005`; linked to `DEC-001` |

