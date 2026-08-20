# Requirements impact refinement: project editing by workspace members

## Requirement revision

`REQ-001` — Every authenticated member of a workspace, including the default `member` role and existing elevated roles, may edit every project in that workspace. The authorization decision must remain scoped to workspace membership and the target workspace's projects; it must not grant project-edit access to users who are not workspace members.

The request is explicit, so no additional product-scope question is required. The supplied request is recorded as `DEC-001`: include the `member` role in project-edit authorization while preserving workspace membership scope and actor-role audit attribution.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `INV-001` | Project editing is currently authorized for workspace owners and admins. | `verified` | Supplied repository fact: `authorizeProjectEdit` currently permits owner and admin roles. | `detected` | `must-preserve` `REQ-001`; `affects` `IMP-001` |
| `INV-002` | Newly invited workspace users default to the `member` role. | `verified` | Supplied repository fact: workspace invitations default to member. | `detected` | `must-preserve` `REQ-001`; `affects` `IMP-001`, `IMP-002` |
| `INV-003` | Project edits emit an audit event containing the actor role. | `verified` | Supplied repository fact: project edits emit an actor-role audit event. | `detected` | `must-preserve` `REQ-001`; `affects` `IMP-003` |

## Impact ledger

| ID | Impact | Area | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | The authorization predicate must add the `member` role without accidentally allowing non-members or unrelated roles to edit projects. | Authorization/privacy | `verified` | `authorizeProjectEdit` currently admits owner/admin; invitation default is member. | `refining` | `affects` `REQ-001`, `INV-001`, `INV-002`; `mitigated-by` `DEC-001`; `produces` `AC-001`, `AC-002` |
| `IMP-002` | Existing invited users with the default member role may gain edit access immediately, changing the effective privilege of already-created accounts. | Authorization/privacy, regression | `verified` | Workspace invitations default to member. | `mitigated` | `affects` `REQ-001`, `INV-002`; `mitigated-by` `DEC-001`; `produces` `AC-003` |
| `IMP-003` | Audit records must continue to identify the actor as `member`, `admin`, or `owner` after members can edit; changing or omitting the role would weaken audit interpretation. | Interfaces, authorization/privacy | `verified` | Project edits emit an actor-role audit event. | `mitigated` | `affects` `REQ-001`, `INV-003`; `mitigated-by` `DEC-001`; `produces` `AC-004` |
| `IMP-004` | Tests or downstream consumers may assume only owner/admin edits are possible; their coverage and compatibility are not available in the supplied evidence. | Regression, interfaces | `unknown` | No test, event schema, or consumer artifact was supplied for inspection. | `blocked` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-005` |

## Focused decision

No further decision is needed: the requested phrase “workspace members” is operationalized as all workspace roles, including the existing `member` role, while retaining the existing workspace-membership boundary and audit role attribution. This is recorded as `DEC-001`.

## Recorded decision

`DEC-001` — Extend `authorizeProjectEdit` to permit workspace members in the `member` role, alongside owner and admin, for every project in that workspace. Keep non-member denial, workspace scoping, and actor-role audit emission unchanged.

## Whole-set recalculation

After `DEC-001`, the complete impact set is:

- `IMP-001`: `mitigated` — the role expansion and boundary are explicit; authorization tests remain required.
- `IMP-002`: `mitigated` — the privilege change is intentional for default invitees and is covered by acceptance criteria.
- `IMP-003`: `mitigated` — role-valued audit attribution remains an invariant.
- `IMP-004`: `blocked` — repository tests, event schema, and consumers were not supplied; planning must name this validation gap.

Delta: no impacts are resolved, superseded, or accepted. `IMP-001` and `IMP-002` move from `refining`/`detected` to `mitigated`; `IMP-003` remains `mitigated`; `IMP-004` remains `blocked`.

## Stop check and planning handoff

The requirement is sufficiently refined for implementation planning. One validation gap remains blocked: inspect authorization tests and any audit-event consumers/schema before implementation is considered complete. No implementation plan is created here.

Acceptance and regression criteria:

| ID | Criterion | Level | Verifies |
| --- | --- | --- | --- |
| `AC-001` | A workspace `member` can edit any project belonging to that workspace. | `verified` after implementation | `REQ-001`, `IMP-001` |
| `AC-002` | A user who is not a member of the target workspace cannot edit its projects, regardless of project identifier or role in another workspace. | `verified` after implementation | `REQ-001`, `IMP-001` |
| `AC-003` | An invited user whose role defaults to `member` can edit workspace projects after invitation acceptance, subject to normal authentication and membership checks. | `verified` after implementation | `INV-002`, `IMP-002` |
| `AC-004` | Edits by members, admins, and owners each emit the existing actor-role audit event with the correct role value. | `verified` after implementation | `INV-003`, `IMP-003` |
| `AC-005` | Existing owner/admin authorization and denial behavior are covered by available authorization and audit tests; if no such tests or consumers exist, that absence is recorded as a validation gap. | `unknown` until inspected | `INV-001`, `INV-003`, `IMP-004` |

