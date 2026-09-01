# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | The workspace_edit permission set expands to include member. | Every member, including newly invited users receiving the default role, gains edit access to every project. | All workspace projects and all current or future workspace members. | authorize_project_edit is called with role member. | critical | Restrict the permitted tuple exactly to owner, admin, and member and verify positive and negative role cases. | accepted |
| `IMP-002` | Default invitation recipients become project editors without an additional role promotion. | Invitation flows may grant broader project edit access than prior operational expectations. | Users accepting invitations with INVITATION_DEFAULT_ROLE. | A user receives the default member role and attempts any project edit. | high | Make the default-role consequence explicit in acceptance coverage and keep non-member roles denied. | accepted |
| `IMP-003` | Member-initiated edits will newly pass authorization. | Newly authorized member edits could become untraceable if auditing filtered or omitted their role. | Audit consumers and incident reviewers. | An authorized member edit emits its audit record. | medium | Preserve emit_actor_role_audit behavior and verify it records role member with project.edit.audited. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Let workspace members edit every project by widening authorization.workspace_edit in auth/authorize.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change authorization.workspace_edit so the member role, as well as owner and admin, can edit every project in the workspace. Preserve denial for roles outside owner, admin, and member, and preserve project.edit.audited actor-role audit output. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Owner and admin roles are authorized to edit projects. | verified | auth/authorize.py defines PERMITTED as owner and admin and authorize_project_edit checks membership in that tuple. |
| `INV-002` | Roles not listed in PERMITTED are denied project editing. | verified | auth/authorize.py returns role in PERMITTED without a permissive fallback. |
| `INV-003` | Project edit auditing records the project.edit.audited event together with actor and role. | verified | events/audit.py returns AUDIT_EVENT, actor, and role from emit_actor_role_audit. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | auth/authorize.py defines PERMITTED as owner and admin and authorize_project_edit checks membership in that tuple. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002` | auth/authorize.py returns role in PERMITTED without a permissive fallback. |
| `INV-003` | `REQ-001` | `IMP-003` | events/audit.py returns AUDIT_EVENT, actor, and role from emit_actor_role_audit. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | accepted | unknown | The receipt links auth/authorize.py with roles/defaults.py, but the provider frontier prevents stronger transitive confidence; direct file evidence remains available in the invariants and criteria. | `INV-001`, `INV-002` | `DEC-001` | `AC-001`, `AC-002`, `AC-003` |
| `IMP-002` | `REQ-001` | authorization/privacy | high | accepted | unknown | The receipt connects auth/authorize.py and roles/defaults.py, but the provider frontier prevents stronger transitive confidence; roles/defaults.py directly identifies member as the invitation default. | `INV-002` | `DEC-001` | `AC-004` |
| `IMP-003` | `REQ-001` | operations | medium | mitigated | unknown | The receipt links auth/authorize.py to events/audit.py, but the provider frontier prevents stronger transitive confidence; events/audit.py directly shows actor and role emission. | `INV-003` | none | `AC-005` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Add member to authorization.workspace_edit for every project. | `REQ-001` | `IMP-001`, `IMP-002` | The user explicitly requested this exact authorization expansion and supplied the default-role consequence as repository evidence. |

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
| `REQ-001` | Change authorization.workspace_edit so the member role, as well as owner and admin, can edit every project in the workspace. Preserve denial for roles outside owner, admin, and member, and preserve project.edit.audited actor-role audit output. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | authorize_project_edit("member") returns true. | Directly verifies the requested new behavior at the authorization boundary. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | authorize_project_edit continues to return true for owner and admin. | Protects existing privileged editing access while widening the gate. |
| `AC-003` | `REQ-001` | `IMP-001` | `INV-002` | authorize_project_edit returns false for roles outside owner, admin, and member. | Bounds the authorization expansion to the requested role. |
| `AC-004` | `REQ-001` | `IMP-002` | `INV-002` | INVITATION_DEFAULT_ROLE remains member and that role is authorized by workspace_edit. | Verifies the transitive access effect identified in roles/defaults.py. |
| `AC-005` | `REQ-001` | `IMP-003` | `INV-003` | emit_actor_role_audit for a member returns event project.edit.audited and retains the actor and member role. | Protects audit observability for the newly authorized role. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Authorization implementation | auth/authorize.py contains the complete PERMITTED tuple and membership check. | high |
| Invitation default role | roles/defaults.py fixes INVITATION_DEFAULT_ROLE to member and points to the same authorization gate. | high |
| Edit audit emission | events/audit.py defines project.edit.audited and emits actor and role without role filtering. | high |
| Graph paths for IMP-001 | PATH-002: authorization.workspace_edit → authorization.workspace_edit | PATH-002: provider builtin; confidence lexical; location auth/authorize.py + roles/defaults.py |
| Graph paths for IMP-002 | PATH-002: authorization.workspace_edit → authorization.workspace_edit | PATH-002: provider builtin; confidence lexical; location auth/authorize.py + roles/defaults.py |
| Graph paths for IMP-003 | PATH-001: authorization.workspace_edit → authorization.workspace_edit | PATH-001: provider builtin; confidence lexical; location auth/authorize.py + events/audit.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt d3e0d60e511a9c8f4f2a011b4c0b4043; sha256 ec6ae51ec9fbb07f76cc09c4e070bef58585c2dafc9382956d470120ad998ba3; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001` | `IMP-001`, `IMP-002` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005` | Ready for implementation. Apply the narrow permission-set change and verify all five acceptance criteria with focused tests or direct assertions. |
