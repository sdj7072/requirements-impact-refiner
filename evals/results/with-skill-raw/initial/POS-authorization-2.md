# Requirements impact refinement: project editing by workspace members

## Requirement revision

`REQ-001` — Any authenticated workspace member, including a member created through the normal invitation flow, may edit every project belonging to that workspace. The authorization change must be scoped to project-edit operations and must continue to emit an audit event containing the acting user’s role.

The phrase “workspace member” is interpreted as the existing `member` role in addition to the currently authorized `owner` and `admin` roles. No cross-workspace access or unrelated permission is implied.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Project-edit authorization currently permits `owner` and `admin` roles. | `verified` | Supplied repository fact: `authorizeProjectEdit` currently permits owner and admin roles. | `must-preserve` by `REQ-001`; `affects` `IMP-001` |
| `INV-002` | Workspace invitations default to the `member` role. | `verified` | Supplied repository fact: workspace invitations default to member. | `must-preserve` by `REQ-001`; `affects` `IMP-002` |
| `INV-003` | Project edits emit an audit event that records the actor’s role. | `verified` | Supplied repository fact: project edits emit an actor-role audit event. | `must-preserve` by `REQ-001`; `affects` `IMP-003` |

## Impact ledger

| ID | Finding | Area | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Adding `member` to `authorizeProjectEdit` changes the effective authorization boundary for every project in a workspace. The check must remain workspace-scoped and must not grant access to projects in another workspace. | Authorization/privacy | `verified` for the changed role boundary; `unknown` for cross-workspace enforcement because no implementation path was supplied | Supplied `authorizeProjectEdit` behavior; cross-workspace implementation details unavailable | `accepted` | `affects` `REQ-001`, `INV-001`; `mitigated-by` `DEC-001`; `produces` `AC-001`, `AC-002` |
| `IMP-002` | Invitation-created users currently enter as `member`; after the change they will be able to edit projects without a role-promotion step. Existing invitation and membership semantics must therefore align with the new permission. | Functionality / authorization | `verified` | Supplied invitation default fact | `accepted` | `affects` `REQ-001`, `INV-002`; `mitigated-by` `DEC-001`; `produces` `AC-003` |
| `IMP-003` | Audit records will now include member-originated project edits. The actor-role field must continue to identify `member` accurately, rather than being omitted, misclassified, or recorded as an elevated role. | Interfaces / auditability | `verified` for the existing audit invariant; `unknown` for event schema/consumer compatibility | Supplied actor-role audit fact; event schema and consumers not supplied | `accepted` | `affects` `REQ-001`, `INV-003`; `mitigated-by` `DEC-001`; `produces` `AC-004`, `AC-005` |
| `IMP-004` | Existing owner and admin editing must not regress while the role predicate expands. | Regression | `inferred` | Follows from the current owner/admin authorization behavior supplied in the request; no tests supplied | `accepted` | `affects` `INV-001`; `mitigated-by` `DEC-001`; `produces` `AC-006` |
| `IMP-005` | Unauthenticated users, users without membership, and members of a different workspace may be accidentally admitted if the change broadens authorization beyond the role predicate. | Authorization/privacy | `unknown` | Authentication, membership lookup, and project-to-workspace linkage were not supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-001`, `AC-002`, `AC-007`; information gap: authorization call path and workspace-boundary tests |
| `IMP-006` | Any downstream audit consumer or reporting logic that assumes only owner/admin actors may edit could require compatibility review. | Interfaces / compatibility | `unknown` | No audit schema, consumer, or compatibility contract supplied | `blocked` | `affects` `REQ-001`, `INV-003`; `produces` `AC-005`; information gap: audit event schema and consumers |

## Focused decision

The explicit request selects the following scope: grant the existing `member` role project-edit access for every project in that member’s workspace, while preserving workspace isolation and actor-role auditing. This is the only decision needed for the requirement as supplied.

Options considered:

1. **Selected — all workspace members:** add the existing `member` role to project-edit authorization for all projects in the same workspace.
2. Restrict members to projects they created or are explicitly assigned to; this does not satisfy “every project.”
3. Add a separate elevated “project editor” role; this is unnecessary because the request names existing workspace members and would not make invitation-default members editors.

## Recorded decision

`DEC-001` — Select option 1. The existing `member` role is authorized to edit every project in its own workspace. Preserve owner/admin access, deny non-members and cross-workspace access, and retain the actor role in each edit audit event.

This decision refines `REQ-001` and mitigates `IMP-001` through `IMP-004`. It does not resolve implementation-information gaps in `IMP-005` or `IMP-006`.

## Acceptance and regression criteria

| ID | Criterion | Evidence level | Verifies / produced by |
| --- | --- | --- | --- |
| `AC-001` | A workspace `member` can successfully edit any project belonging to that member’s workspace. | `unknown` until an authorization test or equivalent evidence exists | Verifies `REQ-001`; produced by `IMP-001` |
| `AC-002` | A `member` cannot edit a project belonging to another workspace, even if the project identifier is known. | `unknown` | Verifies workspace isolation; produced by `IMP-001`, `IMP-005` |
| `AC-003` | A user invited through the default invitation flow (role `member`) can edit every project in the inviting workspace without role promotion. | `unknown` | Verifies `INV-002` under `REQ-001`; produced by `IMP-002` |
| `AC-004` | A successful member-originated project edit emits an audit event containing the acting user and role `member`. | `unknown` | Verifies `INV-003`; produced by `IMP-003` |
| `AC-005` | Existing audit-event consumers accept or correctly process an edit event whose actor role is `member`. | `unknown` | Verifies interface compatibility; produced by `IMP-003`, `IMP-006` |
| `AC-006` | Owners and admins retain project-edit access, with no change to their existing audit-role attribution. | `unknown` | Verifies `INV-001` and `INV-003`; produced by `IMP-004` |
| `AC-007` | Unauthenticated users and users without membership are denied project edits. | `unknown` | Verifies authorization boundary; produced by `IMP-005` |

## Whole-set recalculation and delta

The requirement decision broadens only the project-edit role predicate. `IMP-001` remains accepted because the requested authorization expansion is intentional, with workspace isolation retained as an explicit constraint. `IMP-002`, `IMP-003`, and `IMP-004` remain accepted through `DEC-001`, subject to the acceptance criteria above. `IMP-005` and `IMP-006` remain blocked because the authorization call path, workspace linkage, audit schema, and consumers were not supplied. No impacts are resolved by the decision; no prior impacts are superseded; no new impact is identified beyond the explicitly recorded compatibility gap.

## Stop check and planning handoff

The requirement is sufficiently refined for implementation planning, but the two named information gaps must be carried into planning: inspect the complete authorization/membership/workspace path and inspect the audit event schema plus consumers. The selected planner should create tests or equivalent validation for `AC-001` through `AC-007`, preserving the three supplied invariants.

Remaining risks are limited to the blocked cross-workspace/unauthenticated authorization evidence (`IMP-005`) and audit-consumer compatibility evidence (`IMP-006`).
