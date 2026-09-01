# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | authorization.workspace_edit role allowlist | All default invitees gain edit access to every workspace project, broadening write authority beyond owners and admins. | Existing and future workspace members and every project in their workspace. | A user with role member attempts a project edit. | critical | Make the expansion explicit in the allowlist and verify member, owner, admin, and an unlisted role at the authorization boundary. | accepted |
| `IMP-002` | Auditable project edits by the newly authorized member role | Member edits could be authorized without preserving actor-and-role attribution at the audit boundary. | Audit consumers and operators investigating project changes. | An authorized member edit emits project.edit.audited. | high | Verify emit_actor_role_audit still returns the existing event name, actor, and member role. | detected |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Let workspace members edit every project by widening authorization.workspace_edit in auth/authorize.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Expand authorization.workspace_edit so the workspace role member, including the default invitation role, is authorized to edit every project in the workspace; preserve existing owner and admin authorization and preserve project.edit.audited actor-and-role audit payload behavior. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Owner and admin roles remain authorized by authorize_project_edit. | verified | auth/authorize.py currently defines PERMITTED as owner and admin and returns membership in that tuple. |
| `INV-002` | New invitations continue to default to the member workspace role. | verified | roles/defaults.py defines INVITATION_DEFAULT_ROLE = member. |
| `INV-003` | Project edit auditing continues to emit project.edit.audited with both actor and role. | verified | events/audit.py defines project.edit.audited and emit_actor_role_audit returns event, actor, and role. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | auth/authorize.py currently defines PERMITTED as owner and admin and returns membership in that tuple. |
| `INV-002` | `REQ-001` | `IMP-001` | roles/defaults.py defines INVITATION_DEFAULT_ROLE = member. |
| `INV-003` | `REQ-001` | `IMP-002` | events/audit.py defines project.edit.audited and emit_actor_role_audit returns event, actor, and role. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | accepted | unknown | The supplied graph infers a relationship from auth/authorize.py to roles/defaults.py; direct inspection confirms member is excluded today and is the default invitation role, while the requested change explicitly grants workspace-wide edit access. | `INV-001`, `INV-002` | `DEC-001` | `AC-001`, `AC-002`, `AC-003` |
| `IMP-002` | `REQ-001` | operations | high | detected | unknown | The supplied graph infers a relationship from auth/authorize.py to events/audit.py; direct inspection confirms the actor-and-role audit payload that newly permitted edits must preserve. | `INV-003` | none | `AC-004` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Add member to authorization.workspace_edit for every workspace project. | `REQ-001` | `IMP-001` | The user explicitly selected workspace-wide member edit access and identified member as the default invitation role. |

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
| `REQ-001` | Expand authorization.workspace_edit so the workspace role member, including the default invitation role, is authorized to edit every project in the workspace; preserve existing owner and admin authorization and preserve project.edit.audited actor-and-role audit payload behavior. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | authorize_project_edit(member) returns true. | Focused authorization test or direct executable assertion. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | authorize_project_edit(owner) and authorize_project_edit(admin) both remain true. | Focused authorization regression assertions. |
| `AC-003` | `REQ-001` | `IMP-001` | `INV-001` | A role not listed by authorization.workspace_edit remains unauthorized. | Focused negative authorization assertion. |
| `AC-004` | `REQ-001` | `IMP-002` | `INV-003` | emit_actor_role_audit(actor, member) returns project.edit.audited with the same actor and role member. | Focused audit contract assertion. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Authorization allowlist and authorize_project_edit in auth/authorize.py. | Direct repository inspection. | high |
| Default invitation role in roles/defaults.py is an affected caller/role source but does not require a value change. | INVITATION_DEFAULT_ROLE is member and references the same authorization gate. | high |
| Audit payload contract in events/audit.py is an affected operational invariant but does not require a production-code change. | AUDIT_EVENT and emit_actor_role_audit directly expose the required event, actor, and role. | high |
| No test suite or project configuration is present in the supplied three-file repository. | Repository file inventory contains only auth/authorize.py, roles/defaults.py, and events/audit.py. | high |
| Graph paths for IMP-001 | PATH-002: authorization.workspace_edit → authorization.workspace_edit | PATH-002: provider builtin; confidence lexical; location auth/authorize.py + roles/defaults.py |
| Graph paths for IMP-002 | PATH-001: authorization.workspace_edit → authorization.workspace_edit | PATH-001: provider builtin; confidence lexical; location auth/authorize.py + events/audit.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 5e31987b2005c8445d7dbf3b6da3d683; sha256 b2f3135e9bcb7a7eb6f1bef7c14a818bfc544782497e5deb24a00e62d7ff1e46; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `DEC-001` | `IMP-001` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Ready for implementation: update the role allowlist, then verify the four acceptance criteria with focused executable assertions. |
