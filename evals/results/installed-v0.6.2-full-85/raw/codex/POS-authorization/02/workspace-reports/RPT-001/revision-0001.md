# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | authorization.workspace_edit admits the member role. | Every member gains edit access to every project, including projects they do not own; an overbroad tuple change could also admit unintended roles. | All workspaces, projects, and users assigned the member role. | authorize_project_edit is evaluated for a member or another role. | critical | Make the narrow role-list change to add only member and verify allowed and denied role cases. | accepted |
| `IMP-002` | Members become valid actors for audited project edits. | Downstream audit consumers may previously have assumed only owner/admin roles appear for project edits. | Audit logs and consumers of project.edit.audited. | A member performs a project edit and the audit event is emitted. | medium | Preserve actor and role fields and verify member is retained as the emitted role. | accepted |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Let workspace members edit every project by widening authorization.workspace_edit in auth/authorize.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Widen authorization.workspace_edit in auth/authorize.py so roles owner, admin, and member are authorized to edit every project in the workspace. Preserve the existing owner/admin access, the default invitation role of member, and the project.edit.audited actor/role audit payload. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Owner and admin roles continue to pass authorize_project_edit. | verified | auth/authorize.py currently defines PERMITTED as ("owner", "admin") and authorize_project_edit checks membership in that tuple. |
| `INV-002` | New invitations continue to default to the member role. | verified | roles/defaults.py defines INVITATION_DEFAULT_ROLE = "member" and links it to authorization.workspace_edit. |
| `INV-003` | Project edits continue to emit project.edit.audited with the actor and role recorded. | verified | events/audit.py defines AUDIT_EVENT and emit_actor_role_audit(actor, role), returning event, actor, and role. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | auth/authorize.py currently defines PERMITTED as ("owner", "admin") and authorize_project_edit checks membership in that tuple. |
| `INV-002` | `REQ-001` | `IMP-001` | roles/defaults.py defines INVITATION_DEFAULT_ROLE = "member" and links it to authorization.workspace_edit. |
| `INV-003` | `REQ-001` | `IMP-002` | events/audit.py defines AUDIT_EVENT and emit_actor_role_audit(actor, role), returning event, actor, and role. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | accepted | unknown | The receipt lexically/structurally links auth/authorize.py to roles/defaults.py, but optional graph providers were unavailable; local inspection confirms the gate and default-role definitions without proving additional transitive consumers. | `INV-001`, `INV-002` | `DEC-001` | `AC-001`, `AC-002`, `AC-003` |
| `IMP-002` | `REQ-001` | operations | medium | accepted | unknown | The receipt lexically/structurally links auth/authorize.py to events/audit.py, but optional graph providers were unavailable; local inspection confirms the helper payload without proving all downstream consumers. | `INV-003` | `DEC-001` | `AC-004` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Add member to authorization.workspace_edit while retaining owner and admin. | `REQ-001` | `IMP-001`, `IMP-002` | The request explicitly selects role-based widening to all workspace members; the narrow implementation is to add only member to the existing permitted roles. |

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
| `REQ-001` | Widen authorization.workspace_edit in auth/authorize.py so roles owner, admin, and member are authorized to edit every project in the workspace. Preserve the existing owner/admin access, the default invitation role of member, and the project.edit.audited actor/role audit payload. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | authorize_project_edit("member") returns true. | Directly verifies that the default invitation role receives the requested project-edit capability. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | authorize_project_edit("owner") and authorize_project_edit("admin") both remain true. | Protects existing privileged access from regression. |
| `AC-003` | `REQ-001` | `IMP-001` | `INV-001` | A role other than owner, admin, or member remains unauthorized. | Confines the widened gate to the three selected roles. |
| `AC-004` | `REQ-001` | `IMP-002` | `INV-003` | emit_actor_role_audit for a member edit returns project.edit.audited and preserves the supplied actor and role="member". | Verifies operational attribution remains intact for the newly authorized actor role. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Authorization implementation | auth/authorize.py owns PERMITTED and authorize_project_edit for authorization.workspace_edit. | verified |
| Role default compatibility | roles/defaults.py assigns member by default and references the same gate. | verified; no role-default code change is required |
| Audit compatibility | events/audit.py emits project.edit.audited with actor and role for the same gate. | verified; no audit code change is required |
| Test coverage | No test files or test configuration are present in the supplied repository snapshot. | verified inventory; acceptance may be checked with a focused Python assertion if no test harness exists |
| Graph paths for IMP-001 | PATH-002: authorization.workspace_edit → authorization.workspace_edit | PATH-002: provider builtin; confidence lexical; location auth/authorize.py + roles/defaults.py |
| Graph paths for IMP-002 | PATH-001: authorization.workspace_edit → authorization.workspace_edit | PATH-001: provider builtin; confidence lexical; location auth/authorize.py + events/audit.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 99e8e18acfb5489a1be2cd8906b4659e; sha256 74e4528a8ff7e8076a28582e9e3fd69baf42e7967da8fea8307b80d0cca16982; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `DEC-001` | `IMP-001`, `IMP-002` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Ready for implementation planning: make the narrow authorization role-list change, then verify allowed/denied roles and unchanged audit payload. |
