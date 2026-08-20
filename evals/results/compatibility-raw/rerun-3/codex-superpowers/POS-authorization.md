# Requirements impact report: project-edit authorization

## Requirement revision

`REQ-001`: Workspace members must be able to edit every project in the workspace.

The supplied request changes the project-edit authorization scope. It does not select a particular role-check implementation, invitation transition, audit schema, rollout policy, or migration mechanism.

## Current behavior and preserved invariants

| ID | Current behavior or invariant | Evidence | Level | Relationship |
|---|---|---|---|---|
| `INV-001` | `authorizeProjectEdit` currently permits project edits for owner and admin roles. | User-supplied fact: “authorizeProjectEdit currently permits owner and admin roles.” | `verified` | `REQ-001` must preserve or explicitly refine this authorization behavior. |
| `INV-002` | Workspace invitations default to the member role. | User-supplied fact: “workspace invitations default to member.” | `verified` | `REQ-001` must account for the default role assigned to invited users. |
| `INV-003` | Project edits emit an audit event containing the actor role. | User-supplied fact: “project edits emit an actor-role audit event.” | `verified` | `REQ-001` must preserve actor-role audit attribution. |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links |
|---|---|---|---|---|---|
| `IMP-001` | Expanding authorization from owner/admin to workspace members changes who can edit every project. The exact boundary for “member” is not yet selected. | `verified` | `authorizeProjectEdit` behavior supplied by the user; revised requirement `REQ-001` | `refining` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | Because invitations default to member, newly invited users may gain project-edit access under a broad interpretation of the requirement. | `verified` | Invitation default supplied by the user; revised requirement `REQ-001` | `refining` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | Newly authorized member edits must retain an accurate actor-role audit event, including the member role. | `verified` | Audit behavior supplied by the user; revised requirement `REQ-001` | `detected` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | The supplied facts do not establish whether “every project” includes projects with additional sensitivity, ownership, or privacy restrictions. | `unknown` | No supplied project-classification or exception policy | `blocked` | affects `REQ-001`; produces `AC-004` |

## One focused decision

How should the phrase “workspace members” be bounded for project-edit authorization?

1. **All members immediately** — any user with the workspace’s default `member` role may edit every project.
2. **Members subject to project exceptions** — members may edit projects generally, but some project classes remain restricted.
3. **Explicit project-level grant** — membership alone does not grant editing; each project requires a separate grant.

Please select one option. No recorded decision exists yet.

## Recorded decision

None. The pending decision is the authorization boundary above; no `DEC-###` is recorded.

## Whole-set recalculation

No decision has been recorded, so all known impacts remain in their pre-decision state. No obsolete impact or new impact is established from the supplied facts alone.

## Delta

- resolved: none
- mitigated: none
- unchanged: `IMP-001`, `IMP-002`, `IMP-003`
- accepted: none
- deferred: none
- blocked: `IMP-004`
- new: none

## Stop check and planning handoff

The report stops at the single authorization-boundary decision. `IMP-001`–`IMP-003` remain open pending that selection; `IMP-004` remains blocked pending a project-exception policy or equivalent authoritative information. No implementation work breakdown, plan, task list, or edit is created.

### Acceptance and regression criteria

| ID | Criterion | Evidence basis |
|---|---|---|
| `AC-001` | The selected authorization boundary is applied consistently when deciding whether a workspace user may edit any project. | `IMP-001`; current `authorizeProjectEdit` behavior supplied by the user |
| `AC-002` | Invitation-created users receive exactly the edit capability defined by the selected authorization boundary for the default `member` role. | `IMP-002`; invitation default supplied by the user |
| `AC-003` | Every permitted project edit records an audit event with the correct actor role, including member-role edits where applicable. | `IMP-003`; audit behavior supplied by the user |
| `AC-004` | Project classes or exceptions, if any, are explicitly identified before claiming complete “every project” coverage. | `IMP-004`; supplied-fact gap |

Planning handoff: after the pending decision and any missing project-exception policy are supplied, this report can be recalculated for planning. 

--- USER REVISION ---
I choose a narrower policy: members may edit ordinary project fields, but owner/admin-only sensitive fields remain restricted. I explicitly accept that default-member invitees gain ordinary edit access immediately. Recalculate every impact.

## Recalculated requirement revision

`REQ-002` refines `REQ-001`: workspace members may edit ordinary project fields in every project; sensitive fields that are owner/admin-only remain restricted to owner and admin roles.

## Recalculated preserved invariants

`INV-001`, `INV-002`, and `INV-003` remain in force. The explicit policy also preserves the owner/admin restriction for sensitive fields and accepts ordinary edit access for default-member invitees.

## Recorded decision

`DEC-001`: “I choose a narrower policy: members may edit ordinary project fields, but owner/admin-only sensitive fields remain restricted.”

`DEC-001` refines `REQ-002` and mitigates `IMP-001`; its acceptance clause explicitly accepts `IMP-002`.

## Recalculated impact ledger

| ID | Recalculated impact | Level | Evidence | State | Links |
|---|---|---|---|---|---|
| `IMP-001` | The authorization expansion is bounded: members gain ordinary-field edit access, while sensitive owner/admin-only fields remain restricted. | `verified` | Explicit user revision; current owner/admin behavior supplied for `authorizeProjectEdit` | `mitigated` | affects `REQ-002`, `INV-001`; mitigated by `DEC-001`; produces `AC-001` |
| `IMP-002` | Default-member invitees gain ordinary project-field edit access immediately. | `verified` | Explicit user acceptance plus supplied member invitation default | `accepted` | affects `REQ-002`, `INV-002`; accepted by `DEC-001`; produces `AC-002` |
| `IMP-003` | Member ordinary-field edits must continue to emit an audit event with the accurate actor role; sensitive-field denials or permitted owner/admin edits must retain the existing attribution behavior. | `verified` | Supplied audit invariant and explicit authorization revision | `unchanged` | affects `REQ-002`, `INV-003`; produces `AC-003` |
| `IMP-004` | The prior uncertainty about project exceptions is resolved for the stated policy: field sensitivity, rather than an unspecified project class, defines the restriction boundary. | `unknown` | Explicit user revision supplies the policy; no repository evidence was inspected | `resolved` | affects `REQ-002`; produces `AC-004` |

## Delta

- resolved: `IMP-004`
- mitigated: `IMP-001`
- unchanged: `IMP-003`
- accepted: `IMP-002`
- deferred: none
- blocked: none
- new: none

The seven categories are disjoint and exhaustive over all known impacts.

## Stop check and planning handoff

The authorization requirement is refined and the explicit decision is recorded. `IMP-001` is mitigated rather than resolved because the implementation and complete field classification are not evidenced here. `IMP-002` is accepted through `DEC-001`, not resolved. `IMP-004` is resolved as a requirements ambiguity by the explicit field-based policy, while its evidence level remains `unknown` because no repository implementation evidence was inspected.

### Acceptance and regression criteria

| ID | Criterion | Evidence basis |
|---|---|---|
| `AC-001` | A member can edit ordinary project fields, while sensitive owner/admin-only fields remain unavailable to members. | `IMP-001`; `DEC-001` |
| `AC-002` | A user invited with the default `member` role can edit ordinary project fields immediately, as explicitly accepted. | `IMP-002`; `DEC-001` and supplied invitation default |
| `AC-003` | Every permitted project edit records the accurate actor role, including member-role ordinary edits; sensitive-field authorization outcomes do not corrupt audit attribution. | `IMP-003`; supplied audit invariant and `DEC-001` |
| `AC-004` | The authorization boundary is defined by ordinary versus sensitive fields, with sensitive fields retaining owner/admin-only access. | `IMP-004`; `DEC-001` |

Planning handoff: this recalculated report is ready for a later planning workflow. No implementation work breakdown, plan, task list, or edit is created.
