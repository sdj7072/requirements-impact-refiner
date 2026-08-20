# Requirements impact refinement: project editing for workspace members

## Requirement revision

`REQ-001` — Any authenticated workspace member may edit every project in that workspace. The authorization rule must no longer limit project editing to workspace owners and admins. The change applies to edit authorization only; it does not, on the supplied evidence, change invitation behavior, project visibility, membership management, or the audit-event contract.

No focused product decision is required for this revision because the requested scope explicitly says “workspace members” and “every project.” The security and audit consequences remain acceptance criteria for planning.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `INV-001` | `authorizeProjectEdit` currently permits project edits for owner and admin roles. | `verified` | Supplied repository fact: `authorizeProjectEdit` permits owner and admin roles. | `detected` | `must-preserve` by `REQ-001`; affected by `IMP-001` |
| `INV-002` | Workspace invitations default the invited user to the member role. | `verified` | Supplied repository fact: workspace invitations default to member. | `detected` | `must-preserve` by `REQ-001`; affected by `IMP-002` |
| `INV-003` | Project edits emit an audit event containing the actor role. | `verified` | Supplied repository fact: project edits emit an actor-role audit event. | `detected` | `must-preserve` by `REQ-001`; affected by `IMP-003` |

## Impact ledger

Ordered by severity and evidence confidence.

| ID | Impact / uncertainty | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Expanding `authorizeProjectEdit` to include members changes the authorization boundary for every project. A member who could previously be denied can now modify project state. | `verified` | Supplied repository fact: the current function permits only owner and admin roles. | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001`, `AC-002` |
| `IMP-002` | Because invitations default to member, newly invited users will inherit project-edit capability without an additional role change. This is a direct consequence of the requested policy, but the intended invitation-time access window and offboarding behavior are not supplied. | `verified` for the role default; `inferred` for the resulting access consequence | Supplied repository facts: invitation default is member; revised rule grants members edit access. | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-003` |
| `IMP-003` | Audit records will identify member actors for edits after the authorization expansion. Consumers or compliance checks that assume only owner/admin actors may edit could need adjustment. | `verified` for actor-role emission; `inferred` for downstream assumptions | Supplied repository fact: edits emit actor-role audit events; no consumer contract or test evidence supplied. | `detected` | `affects` `REQ-001`, `INV-003`; `produces` `AC-004` |
| `IMP-004` | The supplied evidence does not establish whether project-level ownership, visibility, sensitive fields, or separate edit restrictions exist beyond `authorizeProjectEdit`; those constraints may make “every project” broader than the intended safe boundary. | `unknown` | No model, policy, route, or test artifacts supplied for project scope or sensitive operations. | `blocked` | `affects` `REQ-001`; `produces` `AC-005` |
| `IMP-005` | Existing regression coverage for owner, admin, member, invitation, audit, and denied-access paths is not available in the supplied evidence. | `unknown` | Tests and validation artifacts were not supplied. | `blocked` | `affects` `REQ-001`, `INV-001`, `INV-002`, `INV-003`; `produces` `AC-001`–`AC-005` |

## Acceptance and regression criteria

| ID | Criterion | Evidence level required | Links |
| --- | --- | --- | --- |
| `AC-001` | An owner can edit every project in the workspace. | `verified` by authorization test | Produced by `IMP-001`; verifies `INV-001`/`REQ-001` |
| `AC-002` | An admin can edit every project in the workspace. | `verified` by authorization test | Produced by `IMP-001`; verifies `INV-001`/`REQ-001` |
| `AC-003` | A member, including a user whose invitation retained the default member role, can edit every project in the workspace; a user outside the workspace remains denied. | `verified` by authorization and invitation-flow tests | Produced by `IMP-002`; verifies `INV-002`/`REQ-001` |
| `AC-004` | A member-authored project edit succeeds and emits the existing audit event with the actor role recorded as member; owner/admin audit behavior remains unchanged. | `verified` by audit-event test | Produced by `IMP-003`; verifies `INV-003`/`REQ-001` |
| `AC-005` | Project-level scope, sensitive operations, and membership/offboarding behavior are explicitly checked and documented before implementation is considered complete. | `verified` by inspected authorization tests/policy or a recorded design constraint | Produced by `IMP-004`/`IMP-005` |

## Recorded decision

No `DEC-###` was recorded: the request specifies the target policy without presenting an unresolved product choice. The member access expansion is therefore part of `REQ-001`; the blocked evidence gaps must be resolved during planning/implementation discovery.

## Whole-set recalculation

The revised requirement leaves all known impacts applicable:

- `IMP-001`: unchanged in substance; remains `refining` until owner/admin/member authorization tests verify the expanded boundary.
- `IMP-002`: unchanged; the invitation default makes the expanded capability apply to newly invited members.
- `IMP-003`: unchanged; audit events must continue and represent the new actor role.
- `IMP-004`: remains `blocked` pending project-scope and sensitive-operation evidence.
- `IMP-005`: remains `blocked` pending test inspection or execution.

Delta: no impacts resolved, accepted, deferred, or superseded; no new impact was identified after the explicit scope revision.

## Stop check and planning handoff

The requirement is refined enough for a planning handoff, but the authorization/privacy and regression evidence gaps are explicitly blocked rather than silently treated as resolved. Planning should inspect the authorization entry point and all project-edit call sites, invitation and membership lifecycle behavior, audit-event consumers, project data sensitivity/visibility rules, and existing tests. It should retain the following invariants: owner/admin edit access, member invitation default, and actor-role audit emission.

Remaining risks are the breadth of “every project,” unintended access immediately after invitation, offboarding/revocation semantics, and downstream audit consumers that may encode the old owner/admin assumption.
