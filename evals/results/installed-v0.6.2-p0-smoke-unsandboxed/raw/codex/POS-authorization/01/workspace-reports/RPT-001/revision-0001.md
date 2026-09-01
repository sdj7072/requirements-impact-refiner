# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | authorization.workspace_edit admits the member role. | Every workspace member gains edit authority over every project, broadening write access beyond owners and admins. | All projects and users assigned the workspace member role, including invitation-default users. | authorize_project_edit evaluates role member. | critical | Implement only the explicitly selected role widening, retain existing roles, deny unrecognized roles, and cover the boundary with authorization tests. | accepted |
| `IMP-002` | Member-authorized project edits enter the existing edit/audit behavior. | A newly authorized member edit could bypass or lose actor-role audit attribution if downstream code special-cases privileged roles. | Audit consumers and operators investigating project edits. | A member performs an authorized project edit. | high | Preserve emit_actor_role_audit behavior and verify a member edit produces project.edit.audited with the member actor and role. | mitigated |
| `IMP-003` | The permitted-role set gains member. | A broader or replacement edit could accidentally remove owner/admin access or authorize roles other than member. | Existing owners and admins, plus callers passing unsupported roles. | The permission set is changed. | high | Append member to the existing permitted roles and test positive and negative role cases. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Let workspace members edit every project by widening authorization.workspace_edit in auth/authorize.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Widen authorization.workspace_edit so the member role, including the invitation-default member role, may edit every project; retain owner and admin access, continue denying unrecognized roles, and preserve project.edit.audited actor/role audit data for member edits. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Owner and admin roles remain authorized to edit projects. | verified | auth/authorize.py defines PERMITTED as owner and admin and authorize_project_edit checks membership in that tuple. |
| `INV-002` | New workspace invitations continue to default to the member role. | verified | roles/defaults.py sets INVITATION_DEFAULT_ROLE to member and references authorization.workspace_edit. |
| `INV-003` | Project edit audit records retain event, actor, and role fields through emit_actor_role_audit. | verified | events/audit.py defines project.edit.audited and emit_actor_role_audit returns event, actor, and role. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003` | auth/authorize.py defines PERMITTED as owner and admin and authorize_project_edit checks membership in that tuple. |
| `INV-002` | `REQ-001` | `IMP-001` | roles/defaults.py sets INVITATION_DEFAULT_ROLE to member and references authorization.workspace_edit. |
| `INV-003` | `REQ-001` | `IMP-002` | events/audit.py defines project.edit.audited and emit_actor_role_audit returns event, actor, and role. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | accepted | unknown | Supplied files show the role set and invitation default; PATH-002 suggests the cross-file relationship, but the fallback graph provider could not independently verify it. | `INV-001`, `INV-002` | `DEC-001` | `AC-001`, `AC-002` |
| `IMP-002` | `REQ-001` | operations | high | mitigated | unknown | events/audit.py defines project.edit.audited with actor and role fields; PATH-001 suggests a gate-to-audit relationship, but no edit-call site or provider-verified path proves member edits traverse it. | `INV-003` | `DEC-001` | `AC-003` |
| `IMP-003` | `REQ-001` | regression | high | mitigated | unknown | The direct membership check suggests the bounded code change; PATH-002 identifies the affected role/gate relationship but remains fallback graph evidence. | `INV-001` | `DEC-001` | `AC-001`, `AC-002` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Add member to authorization.workspace_edit while retaining owner/admin access and existing edit auditing. | `REQ-001` | `IMP-001` | The user explicitly selected this exact authorization widening and supplied the default-role and audit paths as required evidence. |

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
| `REQ-001` | Widen authorization.workspace_edit so the member role, including the invitation-default member role, may edit every project; retain owner and admin access, continue denying unrecognized roles, and preserve project.edit.audited actor/role audit data for member edits. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | authorize_project_edit returns true for member, owner, and admin. | Directly verifies the requested widening without regressing existing privileged roles. |
| `AC-002` | `REQ-001` | `IMP-003` | `INV-001` | authorize_project_edit returns false for unsupported or absent roles. | Bounds the permission change to the three intended roles. |
| `AC-003` | `REQ-001` | `IMP-002` | `INV-003` | The member edit audit path emits project.edit.audited and retains the member actor and role. | Verifies the operational audit consequence identified through PATH-001. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Authorization role set in auth/authorize.py | PERMITTED and authorize_project_edit directly implement authorization.workspace_edit. | high |
| Invitation default role in roles/defaults.py | INVITATION_DEFAULT_ROLE is member and GATE_REF names authorization.workspace_edit. | high |
| Project edit auditing in events/audit.py | AUDIT_EVENT is project.edit.audited and emit_actor_role_audit returns actor and role; the scan connects it to the gate. | medium because no edit-call site or test is present in the supplied repository. |
| Every-project scope | The authorization function accepts only a role and has no project-specific argument or exception. | high |
| Graph paths for IMP-001 | PATH-002: authorization.workspace_edit → authorization.workspace_edit | PATH-002: provider builtin; confidence lexical; location auth/authorize.py + roles/defaults.py |
| Graph paths for IMP-002 | PATH-001: authorization.workspace_edit → authorization.workspace_edit | PATH-001: provider builtin; confidence lexical; location auth/authorize.py + events/audit.py |
| Graph paths for IMP-003 | PATH-002: authorization.workspace_edit → authorization.workspace_edit | PATH-002: provider builtin; confidence lexical; location auth/authorize.py + roles/defaults.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 1f59606c1e55b61a45f5e494d56d0681; sha256 0e3170eb90c5fa8cb471a4815ad58bdf5799e3b949079829ed9d364974364a89; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001` | `IMP-001` | `AC-001`, `AC-002`, `AC-003` | Ready for planning: implement the narrowly selected role-set change and verify authorization boundaries plus member edit audit continuity. |
