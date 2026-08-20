# Requirements Impact Report

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Let workspace members edit every project. | User request |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Workspace members must be able to edit every project, while the supplied invitation default and actor-role audit behavior remain unchanged. The exact authorization transition remains the pending decision. | the pending decision | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `authorizeProjectEdit` permits project edits for owner and admin roles; the member role is not currently permitted by that check. | `verified` | User-supplied fact: “authorizeProjectEdit currently permits owner and admin roles.” |
| `INV-002` | Workspace invitations default to the member role. | `verified` | User-supplied fact: “workspace invitations default to member.” |
| `INV-003` | A project edit emits an audit event containing the actor role. | `verified` | User-supplied fact: “project edits emit an actor-role audit event.” |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-002` | `REQ-001` | `IMP-002` | Invitation default is supplied directly by the user. |
| `INV-003` | `REQ-001` | `IMP-003` | Actor-role audit emission is supplied directly by the user. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Authorization/Privacy | high | `refining` | `verified` | `authorizeProjectEdit` currently accepts owner/admin roles only; supplied fact. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | Authorization/Privacy | medium | `detected` | `verified` | Invitations default to member; supplied fact. Broadening edit access changes the effective capability of newly invited members. | `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | Interfaces / Audit | medium | `detected` | `verified` | Project edits emit actor-role audit events; supplied fact. Any newly authorized member edit must retain the role-bearing event. | `INV-003` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | Regression | medium | `detected` | `unknown` | No repository tests or additional authorization boundaries were supplied, so coverage for existing owner/admin behavior and non-member denial is unknown. | `INV-001` | the pending decision | `AC-004` |

## One Focused Decision

Which authorization transition should satisfy “workspace members can edit every project”?

- **Option A — Expand the existing role check:** treat the member role as authorized wherever `authorizeProjectEdit` currently authorizes owner/admin.
- **Option B — Add a separate workspace-member capability:** keep the existing owner/admin check intact and grant members a distinct, explicitly named capability that covers every project.
- **Option C — Define a different boundary:** specify another concrete authorization mechanism or scope before implementation planning.

No option is selected in the supplied request. Therefore no concrete decision ID or recorded decision is created.

## Recorded Decision

No recorded decision; the pending decision is the authorization transition above.

## Decisions and Accepted Risks

No recorded decision or accepted risk exists before the user selects one of the options above.

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Initial refinement preserves the supplied invitation and audit invariants; authorization mechanics remain pending. | the pending decision | — | No decision made; all known impacts remain unchanged. |

## Whole-Set Recalculation

The complete known set remains `IMP-001` through `IMP-004`. No impact is superseded or newly discovered by the supplied facts. The impacts remain open until the authorization transition is selected and evidence is inspected.

## Delta

- resolved: none
- mitigated: none
- unchanged: `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`
- accepted: none
- deferred: none
- blocked: none
- new: none

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | A workspace member can edit every project after the selected authorization transition; owner and admin access continues to work. | Validation gap: implementation and authorization tests not supplied. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | A newly invited workspace member receives the member role and, under the selected transition, has the required edit access without changing the invitation default. | Validation gap: invitation-flow test not supplied. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | Every project edit performed by a member emits an audit event containing the actor role. | Validation gap: audit-event test not supplied. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-001` | Existing owner/admin authorization remains valid, and unauthorized roles remain denied according to the selected boundary. | Validation gap: repository authorization matrix/tests not supplied. |

## Unresolved, Deferred, and Blocked Items

No impact is deferred or blocked. `IMP-001`–`IMP-004` remain detected/refining pending the focused decision; they are not silently accepted.

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Supplied facts only; no repository inspection, tests, schemas, or policy files were requested for this turn. | Three user-supplied current-behavior facts. | Those three baselines are verified as supplied; repository coverage, hidden permission boundaries, and external consumers remain unknown. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: Let workspace members edit every project while preserving the member invitation default and actor-role audit events; exact authorization transition pending. | `INV-001`–`INV-003`, `IMP-001`–`IMP-004` | Authorization boundary and regression coverage remain unresolved until the pending decision is selected. | `AC-001`–`AC-004` | Superpowers; stop before `writing-plans` pending the focused decision. |

--- USER REVISION ---
I choose a narrower policy: members may edit ordinary project fields, but owner/admin-only sensitive fields remain restricted. I explicitly accept that default-member invitees gain ordinary edit access immediately.

# Requirements Impact Report — Recalculation After Decision

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Let workspace members edit every project. | User request |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Members may edit ordinary project fields on every project; owner/admin-only sensitive fields remain restricted. Default-member invitees gain ordinary edit access immediately. | `DEC-001` | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `authorizeProjectEdit` permits project edits for owner and admin roles. | `verified` | User-supplied fact: “authorizeProjectEdit currently permits owner and admin roles.” |
| `INV-002` | Workspace invitations default to the member role. | `verified` | User-supplied fact: “workspace invitations default to member.” |
| `INV-003` | A project edit emits an audit event containing the actor role. | `verified` | User-supplied fact: “project edits emit an actor-role audit event.” |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-004` | Existing owner/admin authorization remains a baseline while ordinary member edits are added and sensitive fields stay restricted. |
| `INV-002` | `REQ-001` | `IMP-002` | Invitation default remains member. |
| `INV-003` | `REQ-001` | `IMP-003` | Actor-role audit emission remains required for edits. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Authorization/Privacy | high | `mitigated` | `verified` | `DEC-001` narrows member access to ordinary fields and preserves owner/admin-only sensitive fields; current role check is supplied. | `INV-001` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | Authorization/Privacy | medium | `accepted` | `verified` | `DEC-001` explicitly accepts immediate ordinary edit access for default-member invitees; invitation default remains supplied. | `INV-002` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | Interfaces / Audit | medium | `detected` | `verified` | The supplied actor-role audit behavior remains a preserved requirement for ordinary member edits and restricted-field attempts. | `INV-003` | `DEC-001` | `AC-003` |
| `IMP-004` | `REQ-001` | Regression | medium | `blocked` | `unknown` | Repository authorization boundaries and regression coverage were not supplied or inspected; sensitive-field enforcement cannot be evidenced here. | `INV-001` | `DEC-001` | `AC-004` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Members may edit ordinary project fields on every project; sensitive fields remain owner/admin-only; default-member invitees gain ordinary edit access immediately. | `REQ-001` | `IMP-002` | Explicit user selection narrows the requested capability while accepting the immediate access consequence for default-member invitees. |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Workspace members edit every project, with ordinary/sensitive field distinction and immediate default-member access. | `DEC-001` | — | `IMP-001` mitigated; `IMP-002` accepted; `IMP-003` unchanged; `IMP-004` blocked. |

## Whole-Set Recalculation

All known impacts were re-evaluated: `IMP-001` is mitigated, `IMP-002` is accepted, `IMP-003` is unchanged, and `IMP-004` is blocked by the named evidence gap. No impact is superseded and no new impact was identified.

## Delta

- resolved: none
- mitigated: `IMP-001`
- unchanged: `IMP-003`
- accepted: `IMP-002`
- deferred: none
- blocked: `IMP-004`
- new: none

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Members can edit ordinary fields on every project; sensitive fields remain denied to members and available to owner/admin roles. | Validation gap: implementation and authorization tests not supplied. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | A newly invited default-member can edit ordinary fields immediately without changing the member invitation default. | Explicitly accepted by `DEC-001`; invitation-flow test not supplied. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | Ordinary member edits and sensitive-field authorization attempts emit audit events containing the actor role. | Validation gap: audit-event test not supplied. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-001` | Existing owner/admin authorization and all sensitive-field restrictions hold across the repository’s authorization boundaries. | Blocked: repository authorization matrix/tests not supplied or inspected. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-004` | `blocked` | Repository authorization boundaries and regression tests were not supplied or inspected, so sensitive-field enforcement cannot yet be evidenced. | `DEC-001` | Implementation owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Supplied facts and the explicit user revision only; no repository inspection or tests. | Three user-supplied current-behavior facts and `DEC-001`. | Baselines and selected policy are verified as supplied; implementation coverage and hidden permission boundaries remain unknown. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: Members edit ordinary fields on every project; sensitive fields remain owner/admin-only; default-member invitees gain ordinary access immediately. | `INV-001`–`INV-003`, `IMP-001`–`IMP-004`, `DEC-001` | `IMP-004` remains blocked pending repository evidence. | `AC-001`–`AC-004` | Superpowers report-only handoff; no implementation plan or tasks created. |
