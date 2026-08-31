# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | authorization.workspace_edit admits the member role. | Every invited workspace member gains edit authority over every project, including projects they do not own. | Current and newly invited workspace members and all projects in a workspace. | A member attempts a project edit after the authorization tuple is widened. | critical | Treat the broad workspace-wide grant as the explicit product decision and verify exact-role allow/deny behavior. | accepted |
| `IMP-002` | Member-originated project edits become authorized activity. | Operational review could lose role attribution if the existing audit contract were bypassed or changed. | Audit consumers and incident reviewers. | An authorized member edit emits its project edit audit event. | medium | Preserve project.edit.audited and verify member edits retain actor and member role attribution. | accepted |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Let workspace members edit every project by widening authorization.workspace_edit in auth/authorize.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Expand authorization.workspace_edit so the workspace role "member", including the invitation default role, may edit every project. Preserve owner and admin access, continue denying roles outside owner/admin/member, and keep project.edit.audited actor-role audit records unchanged for authorized edits. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Owners and admins remain authorized to edit projects. | verified | auth/authorize.py currently permits owner and admin through PERMITTED. |
| `INV-002` | Roles other than owner, admin, and member remain unauthorized for authorization.workspace_edit. | verified | authorize_project_edit performs exact membership testing against PERMITTED. |
| `INV-003` | Project edit auditing continues to emit project.edit.audited with actor and role. | verified | events/audit.py defines AUDIT_EVENT and emit_actor_role_audit returning event, actor, and role. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | auth/authorize.py currently permits owner and admin through PERMITTED. |
| `INV-002` | `REQ-001` | `IMP-001` | authorize_project_edit performs exact membership testing against PERMITTED. |
| `INV-003` | `REQ-001` | `IMP-002` | events/audit.py defines AUDIT_EVENT and emit_actor_role_audit returning event, actor, and role. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | accepted | unknown | The promoted receipt connects auth/authorize.py to roles/defaults.py, but its provider frontier prevents upgrading graph-path confidence; direct file inspection confirms the named endpoints. | `INV-001`, `INV-002` | `DEC-001` | `AC-001`, `AC-002`, `AC-003` |
| `IMP-002` | `REQ-001` | operations | medium | accepted | unknown | The promoted receipt connects auth/authorize.py to events/audit.py, but its provider frontier prevents upgrading graph-path confidence; direct file inspection confirms the named endpoints. | `INV-003` | `DEC-001` | `AC-004` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Authorize member alongside owner and admin for every project. | `REQ-001` | `IMP-001`, `IMP-002` | The request explicitly selects workspace-wide member edit access and names authorization.workspace_edit as the implementation boundary. |

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
| new | `IMP-001`, `IMP-002` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Expand authorization.workspace_edit so the workspace role "member", including the invitation default role, may edit every project. Preserve owner and admin access, continue denying roles outside owner/admin/member, and keep project.edit.audited actor-role audit records unchanged for authorized edits. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | authorize_project_edit("member") returns true. | Run a focused authorization check after implementation. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | authorize_project_edit("owner") and authorize_project_edit("admin") continue to return true. | Run focused regression checks for the two existing permitted roles. |
| `AC-003` | `REQ-001` | `IMP-001` | `INV-002` | A role outside owner/admin/member returns false. | Run a focused negative authorization check using a representative unsupported role. |
| `AC-004` | `REQ-001` | `IMP-002` | `INV-003` | A member edit audit remains project.edit.audited and includes the actor and role="member". | Inspect or test emit_actor_role_audit without changing its payload contract. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Authorization allowlist | auth/authorize.py defines PERMITTED and authorize_project_edit. | High; directly inspected. |
| Invitation role behavior | roles/defaults.py sets INVITATION_DEFAULT_ROLE to member. | High; directly inspected. Existing and future default invitees are affected by the widened gate. |
| Project edit audit contract | events/audit.py defines project.edit.audited and role-bearing audit payloads. | High; directly inspected. |
| Call sites and automated test suite | The supplied workspace contains only the three referenced Python source files and no tests or project configuration. | High for this workspace snapshot; external consumers are not inspectable here. |
| Graph paths for IMP-001 | PATH-002: authorization.workspace_edit → authorization.workspace_edit | PATH-002: provider builtin; confidence lexical; location auth/authorize.py + roles/defaults.py |
| Graph paths for IMP-002 | PATH-001: authorization.workspace_edit → authorization.workspace_edit | PATH-001: provider builtin; confidence lexical; location auth/authorize.py + events/audit.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 2f5a1ad43f9dc574f7ec96a325771c50; sha256 79b9a54da67402ade95f1fbaf5e3499f705af51a99991efca50bdc73ec77bcd7; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `DEC-001` | `IMP-001`, `IMP-002` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Ready for implementation: make the narrow allowlist change in auth/authorize.py, then verify exact allow/deny behavior and the unchanged audit payload. |
