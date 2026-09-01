# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | The workspace edit gate admits member in addition to owner and admin. | Every invited member gains edit capability across all projects governed by this gate, including projects they do not own. | Workspace members and all projects protected by authorization.workspace_edit. | authorize_project_edit is called with role member. | critical | Make the global scope explicit in tests and limit the code change to the requested role allowlist. | accepted |
| `IMP-002` | Successful member edits become part of the existing project edit audit stream. | Audit consumers may begin seeing role member for a previously privileged-only action. | Audit event consumers and operational monitoring for project edits. | A newly authorized member edit emits project.edit.audited. | medium | Verify that member remains present in the emitted role field and keep the event name and payload shape unchanged. | accepted |
| `IMP-003` | The allowlist is widened without changing existing privileged roles. | Owner or admin edit access could regress if the tuple is replaced rather than extended. | Workspace owners and admins. | The workspace edit permission constant is modified. | high | Assert owner, admin, and member are authorized and an unrelated role remains denied. | accepted |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Let workspace members edit every project by widening authorization.workspace_edit in auth/authorize.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Add the workspace member role to authorization.workspace_edit in auth/authorize.py so a member can edit any project, while preserving owner and admin access and continuing to emit project.edit.audited records with the acting role. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Owners and admins remain authorized to edit projects. | verified | auth/authorize.py defines PERMITTED as owner and admin and authorize_project_edit checks membership in that tuple. |
| `INV-002` | New invitations continue to receive the member role by default. | verified | roles/defaults.py sets INVITATION_DEFAULT_ROLE to member. |
| `INV-003` | Project edit auditing continues to emit project.edit.audited with the supplied actor and role. | verified | events/audit.py returns event, actor, and role from emit_actor_role_audit. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003` | auth/authorize.py defines PERMITTED as owner and admin and authorize_project_edit checks membership in that tuple. |
| `INV-002` | `REQ-001` | `IMP-001` | roles/defaults.py sets INVITATION_DEFAULT_ROLE to member. |
| `INV-003` | `REQ-001` | `IMP-002` | events/audit.py returns event, actor, and role from emit_actor_role_audit. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | accepted | unknown | The built-in receipt links auth/authorize.py to roles/defaults.py, but optional graph providers were unavailable; the files directly confirm member is currently excluded and is the invitation default. | `INV-001`, `INV-002` | `DEC-001` | `AC-001`, `AC-002` |
| `IMP-002` | `REQ-001` | operations | medium | accepted | unknown | The built-in receipt links the gate to events/audit.py, but optional graph providers were unavailable; the file directly confirms the event name and actor-role payload shape. | `INV-003` | `DEC-001` | `AC-003` |
| `IMP-003` | `REQ-001` | regression | high | accepted | unknown | The built-in receipt links the authorization gate to the default role, but optional graph providers were unavailable; preserving owner/admin access remains a testable regression constraint. | `INV-001` | `DEC-001` | `AC-002` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Grant the member role global project edit access through authorization.workspace_edit. | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | The request explicitly selects this authorization mechanic and scope: workspace members must be able to edit every project. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | none |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | `IMP-001`, `IMP-002`, `IMP-003` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Add the workspace member role to authorization.workspace_edit in auth/authorize.py so a member can edit any project, while preserving owner and admin access and continuing to emit project.edit.audited records with the acting role. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | authorize_project_edit('member') returns true. | Directly demonstrates that the default invitation role receives the requested edit permission. |
| `AC-002` | `REQ-001` | `IMP-003` | `INV-001` | authorize_project_edit returns true for owner and admin and remains false for an unrelated role. | Protects existing access and verifies the change is an allowlist widening. |
| `AC-003` | `REQ-001` | `IMP-002` | `INV-003` | emit_actor_role_audit for a member edit retains event project.edit.audited and the supplied actor and member role. | Confirms the widened authorization does not alter audit event identity or attribution. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| auth/authorize.py workspace edit role allowlist | The sole authorization function checks role membership in PERMITTED. | verified |
| roles/defaults.py invitation default | The default role is member and references authorization.workspace_edit. | verified; no code change requested here |
| events/audit.py project edit auditing | The event module links to authorization.workspace_edit and emits actor-role payloads. | verified; behavior should remain unchanged |
| Project-specific ownership or membership checks outside these files | No additional repository files are present in the supplied workspace inventory. | unknown beyond the inspected repository; the requested gate is role-only |
| Graph paths for IMP-001 | PATH-002: authorization.workspace_edit → authorization.workspace_edit | PATH-002: provider builtin; confidence lexical; location auth/authorize.py + roles/defaults.py |
| Graph paths for IMP-002 | PATH-001: authorization.workspace_edit → authorization.workspace_edit | PATH-001: provider builtin; confidence lexical; location auth/authorize.py + events/audit.py |
| Graph paths for IMP-003 | PATH-002: authorization.workspace_edit → authorization.workspace_edit | PATH-002: provider builtin; confidence lexical; location auth/authorize.py + roles/defaults.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 57f5f59ad353f0c155f96d3f73fc8e07; sha256 01addccec7752f40f8cc4bd808aa918eb6658751a78ee5809e6dd8092c82ce4c; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Ready for implementation planning. Limit the change to widening PERMITTED with member, then verify the three acceptance criteria. |
