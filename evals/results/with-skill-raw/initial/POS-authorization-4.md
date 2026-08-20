# Requirements Impact Report

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Let workspace members edit every project. | User request and supplied repository facts |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | A workspace member, including a member created through the default workspace invitation flow, may edit any project in that workspace. Existing owner and admin edit access remains. Every project edit continues to emit an audit event containing the actor role. | `DEC-001` | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Project editing is currently authorized for owner and admin roles. | `verified` | Supplied repository fact: `authorizeProjectEdit` currently permits owner and admin roles. |
| `INV-002` | Workspace invitations currently default to the member role. | `verified` | Supplied repository fact: workspace invitations default to member. |
| `INV-003` | Project edits emit an audit event that records the actor role. | `verified` | Supplied repository fact: project edits emit an actor-role audit event. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003` | Supplied behavior establishes owner/admin access; the revision adds member access without removing existing access. |
| `INV-002` | `REQ-001` | `IMP-002` | Supplied behavior establishes the role assigned by the default invitation flow. |
| `INV-003` | `REQ-001` | `IMP-004` | Supplied behavior establishes actor-role audit emission for edits. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Authorization/Privacy | High | `accepted` | `verified` | `authorizeProjectEdit` currently permits only owner and admin; the request explicitly expands this set to workspace members. | `INV-001` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | Authorization/Privacy | High | `accepted` | `verified` | Invitations default to member, so the change makes the existing default role sufficient for project editing. | `INV-002` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | Compatibility/Regression | Medium | `accepted` | `verified` | Existing owner and admin authorization must continue after member access is added. | `INV-001` | `DEC-001` | `AC-003` |
| `IMP-004` | `REQ-001` | Authorization/Privacy, Interfaces | Medium | `resolved` | `verified` | The current edit path already emits an audit event with actor role; the refined requirement preserves that behavior and requires it for the newly authorized role. | `INV-003` | — | `AC-004` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Grant project-edit permission to all workspace members, including invitees with the default member role; retain owner/admin access and actor-role auditing. | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | This is the explicit requested authorization policy. The broader write authority is intentional and must be covered by authorization and regression criteria. |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Initial refinement: add member to the project-edit authorization set while preserving owner/admin access and actor-role audit events. | `DEC-001` | — | New: `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`. `IMP-004` is resolved by the supplied current behavior plus the preservation constraint; the authorization impacts remain accepted. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | A workspace member can edit every project in that workspace; a member from another workspace cannot edit it; authorization does not depend on project ownership. | Authorization tests for member, cross-workspace member, owner, and admin actors. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | A user invited through the default invitation flow, with role `member`, can edit every project after joining the workspace. | Invitation-to-edit integration test. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-001` | Existing owner and admin edit cases continue to pass, and unauthorized actors remain denied. | Regression tests for owner, admin, unaffiliated user, and any non-member role. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-003` | Every successful project edit, including one by a member, emits an audit event containing the actor role; denied attempts do not create a misleading successful-edit event. | Audit-event test asserting actor identity/role and success semantics. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| — | — | No unresolved, deferred, or blocked impact remains in the supplied scope. Implementation planning must define the exact member/workspace boundary checks and test fixtures. | — | Planning workflow |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Analysis was limited to the supplied repository facts, per task scope. | `authorizeProjectEdit`; default invitation role; actor-role edit audit behavior. | The authorization policy and preserved behaviors are verified from supplied facts, but exact call sites, persistence/schema behavior, denial semantics, and existing test coverage were not inspected; those are planning/validation concerns. |
| “Every project” was interpreted as every project within the member’s workspace. | User wording plus workspace-scoped role facts. | Cross-workspace access remains explicitly disallowed in `AC-001`; confirm this boundary during implementation planning if the repository uses a different tenancy model. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: workspace members can edit every project in their workspace, with owner/admin access retained and actor-role audit events preserved. | `INV-001`–`INV-003`, `IMP-001`–`IMP-004`, `DEC-001` | Broader write authority; exact workspace-boundary enforcement and existing denial behavior require implementation-level verification. | `AC-001`–`AC-004` | Proceed to the approved implementation-planning workflow; this report stops before creating an implementation plan. |
