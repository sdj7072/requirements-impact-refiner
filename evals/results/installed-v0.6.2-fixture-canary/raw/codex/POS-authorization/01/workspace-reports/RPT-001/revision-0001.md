# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | authorization.workspace_edit role policy | A broad authorization change could accidentally admit unintended roles or remove existing owner/admin access. | All workspace members and every project protected by authorize_project_edit. | A user attempts to edit a project with a member, owner, admin, or unsupported role. | critical | Limit the policy change to adding member to the explicit permitted-role tuple and verify positive and negative role cases. | accepted |
| `IMP-002` | Edits performed by newly authorized members | Member edits could become less attributable if the existing role-aware audit contract were changed or bypassed. | Operators and reviewers relying on project.edit.audited records. | A newly authorized member edits a project and audit data is emitted. | high | Leave events/audit.py unchanged and verify emit_actor_role_audit continues to return event, actor, and role. | accepted |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Let workspace members edit every project by widening authorization.workspace_edit in auth/authorize.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Widen authorization.workspace_edit by adding the existing member role to auth/authorize.py's permitted roles, so workspace members—including users receiving the invitation default role—can edit every project. Preserve owner/admin access, deny roles outside owner/admin/member, and keep the existing project.edit.audited actor-and-role audit contract unchanged. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Project editing is controlled by authorization.workspace_edit and authorize_project_edit currently permits owner and admin roles. | verified | auth/authorize.py defines GATE = "authorization.workspace_edit", PERMITTED = ("owner", "admin"), and returns role in PERMITTED. |
| `INV-002` | New invitations receive the member role by default and reference the same workspace edit gate. | verified | roles/defaults.py defines INVITATION_DEFAULT_ROLE = "member" and GATE_REF = "authorization.workspace_edit". |
| `INV-003` | Project-edit auditing uses project.edit.audited and retains both actor and role in emitted audit data. | verified | events/audit.py defines AUDIT_EVENT = "project.edit.audited", links authorization.workspace_edit, and emit_actor_role_audit returns event, actor, and role. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002` | auth/authorize.py defines GATE = "authorization.workspace_edit", PERMITTED = ("owner", "admin"), and returns role in PERMITTED. |
| `INV-002` | `REQ-001` | `IMP-001` | roles/defaults.py defines INVITATION_DEFAULT_ROLE = "member" and GATE_REF = "authorization.workspace_edit". |
| `INV-003` | `REQ-001` | `IMP-002` | events/audit.py defines AUDIT_EVENT = "project.edit.audited", links authorization.workspace_edit, and emit_actor_role_audit returns event, actor, and role. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | accepted | unknown | The inspected gate excludes member while the invitation default is member. The promoted receipt connects these files using fallback graph evidence whose provider confidence is not verified. | `INV-001`, `INV-002` | `DEC-001` | `AC-001`, `AC-002`, `AC-003` |
| `IMP-002` | `REQ-001` | operations | high | accepted | unknown | The promoted receipt connects authorization to auditing using fallback graph evidence whose provider confidence is not verified; inspected code separately confirms the audit payload shape. | `INV-001`, `INV-003` | `DEC-001` | `AC-004` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Add member to the explicit PERMITTED roles in auth/authorize.py and preserve the existing default-role and audit contracts. | `REQ-001` | `IMP-001`, `IMP-002` | The user explicitly selected widening authorization.workspace_edit for workspace members and supplied the default-role and audit paths as required repository context. |

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
| `REQ-001` | Widen authorization.workspace_edit by adding the existing member role to auth/authorize.py's permitted roles, so workspace members—including users receiving the invitation default role—can edit every project. Preserve owner/admin access, deny roles outside owner/admin/member, and keep the existing project.edit.audited actor-and-role audit contract unchanged. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | authorize_project_edit("member") returns true, granting the invitation-default role edit access across every project using this gate. | Target behavior derived from the explicit request and roles/defaults.py. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | authorize_project_edit("owner") and authorize_project_edit("admin") continue to return true. | Existing permitted roles in auth/authorize.py must remain permitted. |
| `AC-003` | `REQ-001` | `IMP-001` | `INV-001` | Roles other than owner, admin, and member continue to return false. | The existing explicit membership check provides a deny-by-default boundary. |
| `AC-004` | `REQ-001` | `IMP-002` | `INV-003` | emit_actor_role_audit still emits project.edit.audited with the supplied actor and role, including role member. | Current events/audit.py behavior and the supplied audit requirement. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Authorization implementation | auth/authorize.py contains the complete role tuple and edit predicate. | high |
| Invitation role mapping | roles/defaults.py establishes member as the default and references the same gate; no source change is required. | high |
| Audit contract | events/audit.py defines the gate-linked event and role-aware payload; no source change is required. | high |
| Automated regression coverage | Repository inventory contains only the three supplied Python modules and no existing test files. | high |
| Graph paths for IMP-001 | PATH-002: authorization.workspace_edit → authorization.workspace_edit | PATH-002: provider builtin; confidence lexical; location auth/authorize.py + roles/defaults.py |
| Graph paths for IMP-002 | PATH-001: authorization.workspace_edit → authorization.workspace_edit | PATH-001: provider builtin; confidence lexical; location auth/authorize.py + events/audit.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 73c26f372620ec276af5a9dab5b0aa1c; sha256 ca47f874472353ca1534eab0d158c39e0100af215bb0e753e70e66c0972ef799; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `DEC-001` | `IMP-001`, `IMP-002` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Ready for implementation: make the localized permitted-role change, use direct assertions because no test harness exists, and verify authorization plus audit invariants. |
