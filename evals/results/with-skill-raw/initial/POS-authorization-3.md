# Requirements impact refinement: workspace-member project editing

## Requirement revision

`REQ-001` — Any authenticated workspace member, including the default `member` role granted by a workspace invitation, may edit every project in that workspace. Existing project-edit audit events continue to record the actor’s role. The change is limited to project-edit authorization; it does not by itself grant project creation, deletion, workspace administration, invitation management, or access outside the actor’s workspace.

Status: `refining` pending the focused decision below.

## Current behavior and preserved invariants

The supplied repository facts establish the following baseline:

| ID | Current behavior / invariant | Level | Evidence | Links |
| --- | --- | --- | --- | --- |
| `INV-001` | `authorizeProjectEdit` currently permits project edits for owners and admins. | `verified` | Supplied repository fact: `authorizeProjectEdit` role check | `must-preserve` `REQ-001` |
| `INV-002` | Workspace invitations default the invited user to the `member` role. | `verified` | Supplied repository fact: workspace invitation default | `must-preserve` `REQ-001` |
| `INV-003` | Project edits emit an audit event containing the actor role. | `verified` | Supplied repository fact: project-edit actor-role audit event | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Area | Level | Evidence / gap | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Expanding the role check to `member` changes the authorization boundary for every project in the workspace. | Authorization/Privacy | `verified` | Directly follows from the supplied `authorizeProjectEdit` behavior and requested change | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | The invitation default means newly invited members will receive project-edit capability without an additional role transition. | Authorization/Privacy | `verified` | Supplied invitation-default fact | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | Audit consumers and investigations must continue to distinguish member, admin, and owner actors after authorization broadens. | Interfaces / Operations | `verified` | Supplied actor-role audit-event fact; downstream consumers not supplied | `mitigated` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | A member may be able to edit projects containing data or settings intended for restricted roles; the required project-level exceptions, if any, are not specified. | Authorization/Privacy | `unknown` | No project classification, exception rule, or policy supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Other authorization entry points may independently enforce owner/admin-only editing, producing inconsistent behavior if only `authorizeProjectEdit` changes. | Functionality / Regression | `unknown` | No call-site inventory or tests supplied | `blocked` | `affects` `REQ-001`; `produces` `AC-005` |
| `IMP-006` | Existing authorization and audit tests may encode the owner/admin-only rule and need updated expectations plus member coverage. | Regression | `inferred` | Role-check and audit behavior supplied; test inventory unavailable | `blocked` | `affects` `REQ-001`, `INV-001`, `INV-003`; `produces` `AC-006` |
| `IMP-007` | Cross-workspace project access must remain denied; broadening the role predicate must not weaken workspace scoping. | Authorization/Privacy | `inferred` | Requirement says workspace members and every project, but no scoping implementation supplied | `refining` | `affects` `REQ-001`; `produces` `AC-007` |

## Focused decision

Should `member` be the only newly authorized role, while owners and admins retain access and all project/workspace scoping remains unchanged?

Options:

1. **Members only (recommended):** authorize `owner`, `admin`, and `member`; preserve all other role and workspace boundaries.
2. **All authenticated users:** authorize any authenticated user who can identify a project; highest capability expansion and requires an explicit cross-workspace policy.
3. **Members with exceptions:** authorize members generally but retain an explicit restricted-project exception list or project-level permission model.

No user decision is present in the supplied request beyond “workspace members,” so options 2 and 3 cannot be selected without additional policy evidence. The remainder below records the conservative interpretation of option 1 as the proposed decision, pending confirmation.

## Recorded decision

`DEC-001` — Proposed conservative interpretation: add `member` to the existing allowed roles, retain `owner` and `admin`, preserve workspace scoping, and retain actor-role audit emission. This is a proposed decision, not user-confirmed acceptance.

## Whole-set recalculation under proposed `DEC-001`

| ID | Recalculated state | Rationale |
| --- | --- | --- |
| `IMP-001` | `mitigated` | The role expansion is explicitly bounded to owner/admin/member. |
| `IMP-002` | `mitigated` | Invitation-default members are intentionally covered. |
| `IMP-003` | `mitigated` | Actor role remains part of the audit event; downstream compatibility still needs verification. |
| `IMP-004` | `blocked` | No evidence establishes whether some projects require role exceptions. |
| `IMP-005` | `blocked` | No authorization call-site inventory is available. |
| `IMP-006` | `blocked` | No test inventory is available. |
| `IMP-007` | `mitigated` | Workspace scoping is an explicit requirement constraint, but implementation evidence is absent. |

### Delta

- `IMP-001`, `IMP-002`, `IMP-003`, and `IMP-007`: `refining`/`detected` → `mitigated` under proposed `DEC-001`.
- `IMP-004`, `IMP-005`, and `IMP-006`: remain `blocked` pending policy, call-site, and test evidence.
- No impacts are resolved; no risk is accepted because `DEC-001` is not user-confirmed.
- No new impact identified by the proposed decision.

## Acceptance and regression criteria

| ID | Criterion | Evidence needed | Produced by |
| --- | --- | --- | --- |
| `AC-001` | `owner`, `admin`, and invited/default `member` actors can edit every project in their own workspace. | Authorization tests or equivalent direct checks | `IMP-001` |
| `AC-002` | A newly invited default `member` can edit a project without an additional role change. | Invitation-to-edit integration test | `IMP-002` |
| `AC-003` | Every project edit still emits an audit event with the actual actor role (`member`, `admin`, or `owner`). | Audit-event assertion / schema check | `IMP-003` |
| `AC-004` | Any project-level or data-classification exceptions are either explicitly absent or enforced and tested. | Product/security policy plus authorization tests | `IMP-004` |
| `AC-005` | All project-edit entry points use the same member-inclusive authorization rule. | Call-site inventory and integration tests | `IMP-005` |
| `AC-006` | Existing owner/admin authorization and audit regressions pass, with new member cases covered. | Test suite and new role-matrix cases | `IMP-006` |
| `AC-007` | A member of workspace A cannot edit a project belonging to workspace B. | Cross-workspace negative authorization test | `IMP-007` |

## Stop check and planning handoff

The requirement is refined enough for planning only after the focused decision is confirmed and the blocked information gaps are resolved or explicitly deferred. Current handoff risks are: unknown project-level exceptions, unknown alternate authorization entry points, and unavailable test inventory. The implementation planner should use `REQ-001`, preserve `INV-001`–`INV-003`, and carry `AC-001`–`AC-007` into the plan. This artifact intentionally stops before creating an implementation plan.
