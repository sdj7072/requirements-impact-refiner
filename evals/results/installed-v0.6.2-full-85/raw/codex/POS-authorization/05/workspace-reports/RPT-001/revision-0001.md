# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Workspace project-edit authorization expands to include members. | A role wider than member could be unintentionally authorized, or existing owner/admin access could regress. | All workspace members and all projects protected by authorization.workspace_edit. | authorize_project_edit evaluates a member or another role. | critical | Change only the explicit PERMITTED tuple and cover member, owner/admin, and an unrelated role with regression checks. | accepted |
| `IMP-002` | Default invitees gain project-edit permission because their role is member. | Newly invited users receive edit capability immediately, which is a deliberate broadening of authorization. | Users accepted with INVITATION_DEFAULT_ROLE and every project behind the workspace_edit gate. | An invitation produces the default member role and the user attempts an edit. | high | Treat immediate default-member edit access as an explicit acceptance criterion and avoid changing the default-role constant. | accepted |
| `IMP-003` | Member-originated project edits enter the existing audit stream. | The newly authorized role could be omitted or mislabeled in audit output even though the edit succeeds. | Audit consumers and investigations of edits performed by members. | A member edit is audited through emit_actor_role_audit. | high | Verify the member role is retained in the unchanged project.edit.audited payload. | accepted |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Let workspace members edit every project by widening authorization.workspace_edit in auth/authorize.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Add the existing workspace role &#96;member&#96; to the roles permitted by &#96;authorization.workspace_edit&#96; in &#96;auth/authorize.py&#96;, so a member—including the invitation default role—can edit any project governed by this gate. Preserve owner/admin access, continue denying unrecognized or other roles, and keep &#96;project.edit.audited&#96; actor/role audit payloads unchanged. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | &#96;owner&#96; and &#96;admin&#96; remain authorized for project edits. | verified | auth/authorize.py currently lists owner and admin in PERMITTED and authorize_project_edit checks membership in that tuple. |
| `INV-002` | Roles other than owner, admin, and the newly authorized member role remain unauthorized. | verified | auth/authorize.py implements authorization as exact membership in PERMITTED; widening the tuple only with member preserves denial for all other values. |
| `INV-003` | Successful edit auditing continues to emit &#96;project.edit.audited&#96; and includes the unchanged actor and role fields. | verified | events/audit.py defines AUDIT_EVENT and emit_actor_role_audit independently of the permission tuple. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | auth/authorize.py currently lists owner and admin in PERMITTED and authorize_project_edit checks membership in that tuple. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002` | auth/authorize.py implements authorization as exact membership in PERMITTED; widening the tuple only with member preserves denial for all other values. |
| `INV-003` | `REQ-001` | `IMP-003` | events/audit.py defines AUDIT_EVENT and emit_actor_role_audit independently of the permission tuple. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | accepted | unknown | auth/authorize.py defines authorization.workspace_edit using PERMITTED=(owner, admin); roles/defaults.py establishes member as the invitation default. The promoted graph receipt connects the gate to the role default through PATH-002, but optional graph providers were unavailable. | `INV-001`, `INV-002` | `DEC-001` | `AC-001`, `AC-002`, `AC-003` |
| `IMP-002` | `REQ-001` | authorization/privacy | high | accepted | unknown | roles/defaults.py sets INVITATION_DEFAULT_ROLE to member and references authorization.workspace_edit; after the gate widens, newly invited default-role users receive edit access without another role transition. PATH-002 is fallback graph evidence because optional providers were unavailable. | `INV-002` | `DEC-001` | `AC-004` |
| `IMP-003` | `REQ-001` | operations | high | accepted | unknown | events/audit.py links project.edit.audited to authorization.workspace_edit and emits actor and role. PATH-001 is fallback graph evidence because optional providers were unavailable. | `INV-003` | `DEC-001` | `AC-005` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Authorize the existing member role through authorization.workspace_edit for every governed project. | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | The request explicitly selects the authorization expansion and names the gate; no alternate scope or role mechanism is requested. |

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
| `REQ-001` | Add the existing workspace role &#96;member&#96; to the roles permitted by &#96;authorization.workspace_edit&#96; in &#96;auth/authorize.py&#96;, so a member—including the invitation default role—can edit any project governed by this gate. Preserve owner/admin access, continue denying unrecognized or other roles, and keep &#96;project.edit.audited&#96; actor/role audit payloads unchanged. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | authorize_project_edit("member") returns True. | Directly verifies the requested role expansion. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | authorize_project_edit("owner") and authorize_project_edit("admin") continue to return True. | Protects the current privileged-role behavior. |
| `AC-003` | `REQ-001` | `IMP-001` | `INV-002` | A role not equal to owner, admin, or member returns False. | Ensures the authorization change is limited to member. |
| `AC-004` | `REQ-001` | `IMP-002` | `INV-002` | authorize_project_edit(INVITATION_DEFAULT_ROLE) returns True while INVITATION_DEFAULT_ROLE remains member. | Covers the transitive permission received by newly invited default-role users. |
| `AC-005` | `REQ-001` | `IMP-003` | `INV-003` | emit_actor_role_audit(actor, "member") returns event project.edit.audited with the same actor and role member. | Confirms audit continuity for the newly authorized actor role. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Authorization gate implementation | auth/authorize.py contains the complete role-membership decision for project editing. | high |
| Invitation-role interaction | roles/defaults.py defines member as the default invitation role and links it to the workspace_edit gate. | high |
| Edit audit contract | events/audit.py defines the event name and actor/role payload linked to the same gate. | high |
| Callers and existing automated tests | Repository inventory contains only the three supplied Python modules and no test files or additional callers. | high for this workspace snapshot |
| Graph paths for IMP-001 | PATH-002: authorization.workspace_edit → authorization.workspace_edit | PATH-002: provider builtin; confidence lexical; location auth/authorize.py + roles/defaults.py |
| Graph paths for IMP-002 | PATH-002: authorization.workspace_edit → authorization.workspace_edit | PATH-002: provider builtin; confidence lexical; location auth/authorize.py + roles/defaults.py |
| Graph paths for IMP-003 | PATH-001: authorization.workspace_edit → authorization.workspace_edit | PATH-001: provider builtin; confidence lexical; location auth/authorize.py + events/audit.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt e05c0120eca10970914b56057197d1f3; sha256 06758dfc6ceb8bb02ccae313bd73e0e1b24919355d45a78ac0bdfb612bbb23b8; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005` | Ready for implementation. Make the minimal explicit-role change in auth/authorize.py and verify all five acceptance criteria with focused automated checks. |
