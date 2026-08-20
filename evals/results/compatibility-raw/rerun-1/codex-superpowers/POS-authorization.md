# Authorization impact report

## Requirement revision

`REQ-001`: Every workspace member can edit every project in that workspace. The supplied request does not define any additional role (such as guest) or a separate per-project grant.

## Current behavior and preserved invariants

- `INV-001`: `authorizeProjectEdit` currently permits the owner and admin roles. Evidence: supplied repository fact; `verified`.
- `INV-002`: Workspace invitations currently default to the member role. Evidence: supplied repository fact; `verified`.
- `INV-003`: Project edits emit an audit event containing the actor role. Evidence: supplied repository fact; `verified`.

These invariants should remain intact unless the pending decision explicitly changes them. In particular, invitation role defaults and actor-role audit attribution are not silently changed by this requirement revision.

## Impact ledger

| ID | Finding | Evidence | State | Links |
| --- | --- | --- | --- | --- |
| `IMP-001` | Existing members are denied project edits because the current authorization rule recognizes only owner and admin. | Supplied repository fact: `authorizeProjectEdit` permits owner/admin; `verified` | `refining` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Because invitations default to member, newly invited members will also be unable to edit unless the member role becomes covered by the requirement. | Supplied repository fact: invitations default to member; `verified` | `detected` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | Allowing member edits changes the set of successful edit actors, so audit consumers must continue to receive the actual member actor role rather than an elevated or substituted role. | Current actor-role audit behavior is supplied; the downstream consumer contract is not supplied; `inferred` | `detected` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | Coverage of authorization call sites, existing regression tests, and any role values beyond owner/admin/member cannot be assessed from the supplied facts alone. | No additional repository inspection is in scope; `unknown` | `blocked` | affects `REQ-001` |

## Decision needed

Should the existing `member` role itself become edit-capable for every project, including members created by the current default invitation flow, while preserving actor-role audit attribution?

1. **All workspace members** — treat owner, admin, and member as edit-capable for every project; keep invitation default `member` and record `member` as the audit actor role.
2. **Existing members only** — permit currently active members, but require a separate grant or transition for future invitees; this does not fully satisfy the stated “every workspace member” requirement.
3. **Change invitation semantics** — keep the current edit check and change the default invitation role to an already-authorized role; this broadens invitee privileges and changes the supplied invitation invariant.

Please select one option. No recorded decision ID is created until an explicit selection is supplied.

## Whole-set recalculation before selection

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-002`, `IMP-003`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`
- `new`: none

## Stop check and planning handoff

The material authorization policy is still pending user selection, and `IMP-004` remains blocked by the stated inspection boundary. Stop here for the focused decision; do not begin an implementation plan.

If option 1 is selected, the refined requirement should preserve `INV-002` and `INV-003` and target these acceptance criteria:

- `AC-001`: owner, admin, and member actors can edit every project in their workspace.
- `AC-002`: a newly invited member, using the unchanged default invitation role, can edit every project in that workspace.
- `AC-003`: a member edit emits an audit event whose actor role is `member`.

The pending decision must be recorded before these criteria can be finalized and handed to the selected planning workflow.

--- USER REVISION ---

I choose a narrower policy: members may edit ordinary project fields, but owner/admin-only sensitive fields remain restricted. I explicitly accept that default-member invitees gain ordinary edit access immediately. Recalculate every impact. Continue the same evaluation. Do not write implementation tasks or modify the repository. Recalculate the entire known impact set, preserve accepted versus resolved semantics, and produce the report-only planning handoff. Preserve the existing .part1 byte-for-byte. Assemble the final transcript at .superpowers/sdd/2026-08-20-requirements-impact-refiner/task7-compat-rerun1/codex-superpowers/POS-authorization.md by writing the exact .part1 content, then a `--- USER REVISION ---` separator, then the exact user revision above, then the complete second response. The second response delta must be pairwise disjoint and exhaustive and show resolved, mitigated, unchanged, accepted, deferred, blocked, and new using none where needed. Return only DONE plus the path.

# Recalculated authorization impact report

## Requirement revision

`REQ-002`: Workspace members may edit ordinary fields on every project in their workspace. Sensitive project fields remain editable only by owners and admins. Members created through the existing default-member invitation flow receive ordinary-field edit access immediately. The supplied revision does not define the sensitive-field inventory or any role beyond owner, admin, and member.

## Current behavior and preserved invariants

- `INV-001`: `authorizeProjectEdit` currently permits owner and admin roles. Evidence: supplied repository fact; `verified`.
- `INV-002`: Workspace invitations default to member. Evidence: supplied repository fact; `verified`.
- `INV-003`: Project edits emit an audit event containing the actor role. Evidence: supplied repository fact; `verified`.

The revision preserves invitation defaults and actor-role attribution. It narrows the authorization change to ordinary fields and explicitly preserves owner/admin-only access for sensitive fields.

## Recalculated impact ledger

| ID | Finding | Evidence | State | Links |
| --- | --- | --- | --- | --- |
| `IMP-001` | Members must move from complete project-edit denial to ordinary-field edit access, while sensitive-field edits remain restricted to owners/admins. | Existing owner/admin-only rule plus explicit user revision; `verified` | `mitigated` | affects `REQ-002`, `INV-001`; produces `AC-004` |
| `IMP-002` | Default-member invitees gain ordinary-field edit access immediately. | Invitation default plus explicit user acceptance; `verified` | `accepted` | affects `REQ-002`, `INV-002`; mitigated by `DEC-001`; produces `AC-005` |
| `IMP-003` | Successful member edits must continue to emit the actual member actor role; sensitive-field denials must not be represented as successful edits. | Current actor-role audit behavior supplied; denial-event behavior not supplied; `inferred` | `unchanged` | affects `REQ-002`, `INV-003`; produces `AC-006` |
| `IMP-004` | Authorization call-site coverage, regression tests, role values beyond owner/admin/member, and the sensitive-field inventory cannot be assessed from the supplied facts alone. | No additional repository inspection is in scope; `unknown` | `blocked` | affects `REQ-002` |

## Recorded decision

`DEC-001`: The user selected a narrower policy: members may edit ordinary project fields, owner/admin-only sensitive fields remain restricted, and default-member invitees gain ordinary edit access immediately. This decision refines `REQ-002`, accepts `IMP-002`, and mitigates `IMP-001`.

## Whole-set recalculation

- `resolved`: none
- `mitigated`: `IMP-001`
- `unchanged`: `IMP-003`
- `accepted`: `IMP-002`
- `deferred`: none
- `blocked`: `IMP-004`
- `new`: none

The delta categories are pairwise disjoint and exhaustive over the known impact set: `IMP-001`, `IMP-002`, `IMP-003`, and `IMP-004` each appears exactly once.

## Acceptance criteria

- `AC-004`: A member can edit ordinary fields on every project in the workspace, while attempts to edit sensitive fields remain denied for members and permitted for owners/admins.
- `AC-005`: A newly invited member using the unchanged default invitation role can edit ordinary fields immediately.
- `AC-006`: A successful member edit emits an audit event with actor role `member`; a denied sensitive-field attempt is not recorded as a successful edit.

## Stop check and report-only planning handoff

The policy decision is recorded and the known impacts have been recalculated. `IMP-004` remains blocked pending the sensitive-field inventory and broader repository/test evidence; it is not silently accepted or resolved. This is the complete report-only handoff for planning: refined requirement `REQ-002`, preserved invariants `INV-001`–`INV-003`, decision `DEC-001`, impacts `IMP-001`–`IMP-004`, and acceptance criteria `AC-004`–`AC-006`. No implementation tasks or work breakdown are included.
