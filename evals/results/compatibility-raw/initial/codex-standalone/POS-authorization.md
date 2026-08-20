# Requirements Impact Refinement — Project edit authorization

## Requirement revision

`REQ-001`: Every workspace member must be able to edit every project. The existing project-edit behavior, workspace invitation behavior, and actor-role audit behavior are in scope for compatibility refinement; the exact role transition or permission boundary remains pending.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence | Level | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | `authorizeProjectEdit` permits project edits for workspace owners and administrators; the member role is not currently permitted. | Supplied fact: “authorizeProjectEdit currently permits owner and admin roles.” | `verified` | `must-preserve` `REQ-001` |
| `INV-002` | Workspace invitations default to the `member` role. | Supplied fact: “workspace invitations default to member.” | `verified` | `must-preserve` `REQ-001` |
| `INV-003` | Project edits emit an audit event containing the actor’s role. | Supplied fact: “project edits emit an actor-role audit event.” | `verified` | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | State | Evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | The requested outcome conflicts with the current authorization boundary: members cannot currently edit projects. | `verified` | `refining` | Supplied current behavior for `authorizeProjectEdit`. | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | Because invitations default to `member`, broadening member editability changes the effective privileges of newly accepted invitees; changing the invitation role policy would instead affect onboarding and least-privilege expectations. | `verified` | `detected` | Supplied invitation-default fact. | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | Newly permitted member edits will create audit events whose actor role is `member`, affecting audit interpretation and any downstream review or alerting that distinguishes roles. | `verified` | `detected` | Supplied actor-role audit fact. | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | The supplied facts do not establish whether “every workspace member” includes only accepted members or also pending invitees, nor whether any project-level exceptions exist. | `unknown` | `blocked` | No repository contract, role matrix, or project-exception policy supplied. | `affects` `REQ-001`; `produces` `AC-004` |

## One focused decision

What permission boundary should “every workspace member” establish?

1. **Accepted members only (recommended)** — permit the existing `member` role to edit every project after membership is active; keep invitation defaults and actor-role audit fields unchanged.
2. **Role-policy expansion** — revise the invitation/role policy as part of the change so the edit-capable role assignment is explicitly controlled, including the default for new invitees.
3. **All workspace-associated identities** — include pending invitees or other non-member workspace identities in the edit boundary, with corresponding authorization and audit semantics.

Please select one option. No decision has been recorded yet; the pending decision is required before a concrete `DEC-###` can be created.

## Recorded decision

Decision needed — no `DEC-###` is recorded because no user/stakeholder option has been selected.

## Whole-set recalculation (before decision)

All known impacts were rechecked against the supplied facts. No impact is resolved, mitigated, accepted, deferred, or new before the boundary decision.

## Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-002`, `IMP-003`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`
- `new`: none

## Stop check and planning handoff

Stopped at the single required permission-boundary decision. The refined requirement, preserved invariants, evidence-backed impacts, and provisional acceptance criteria are ready for continuation after selection; no implementation plan or edit is produced.

### Acceptance criteria targets

| ID | Future criterion | Evidence / gap |
| --- | --- | --- |
| `AC-001` | An accepted workspace member can edit every project, while the selected boundary is enforced consistently. | Target derived from `IMP-001`; authorization contract beyond the supplied fact is not inspected. |
| `AC-002` | The selected invitation and role policy is reflected consistently in who can edit after invitation acceptance. | Target derived from `IMP-002`; role matrix and onboarding tests are not supplied. |
| `AC-003` | Every project edit records the actor’s effective role, including edits by members if permitted. | Target derived from `IMP-003`; audit schema/consumer behavior is not supplied. |
| `AC-004` | The chosen treatment of pending invitees and any project-level exceptions is explicit and testable. | Target derived from blocked `IMP-004`; repository authorization policy is unavailable. |

--- USER REVISION ---

I choose a narrower policy: members may edit ordinary project fields, but owner/admin-only sensitive fields remain restricted. I explicitly accept that default-member invitees gain ordinary edit access immediately.

# Second response — recalculation after `DEC-001`

## Requirement revision

`REQ-001` is refined to: Workspace members, including default-member invitees once they have workspace membership, may edit ordinary fields on every project. Sensitive project fields that are owner/admin-only remain restricted to owners and administrators. Project edits continue to emit an audit event containing the actor’s role. The accepted risk is that default-member invitees gain ordinary edit access immediately.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence | Level | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | `authorizeProjectEdit` currently permits project edits for owners and administrators; members are not currently permitted by the supplied behavior. | Supplied current behavior for `authorizeProjectEdit`. | `verified` | `must-preserve` `REQ-001` |
| `INV-002` | Workspace invitations default to the `member` role. | Supplied invitation-default fact. | `verified` | `must-preserve` `REQ-001` |
| `INV-003` | Project edits emit an audit event containing the actor’s role. | Supplied actor-role audit fact. | `verified` | `must-preserve` `REQ-001` |

## Recorded decision

`DEC-001`: The user selected a narrower policy: “members may edit ordinary project fields, but owner/admin-only sensitive fields remain restricted,” and explicitly accepted that “default-member invitees gain ordinary edit access immediately.”

## Whole-set recalculation

| ID | Recalculated impact | Level | State | Evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | The requested ordinary-field edit capability still changes the current member authorization boundary, but the narrower field scope limits the change. | `verified` | `mitigated` | Current `authorizeProjectEdit` behavior is supplied; the ordinary/sensitive field taxonomy is supplied by the user’s decision. | `affects` `REQ-001`, `INV-001`; `mitigated by` `DEC-001`; `produces` `AC-001` |
| `IMP-002` | Default-member invitees gaining ordinary edit access is an intentional privilege change and accepted compatibility risk. | `verified` | `accepted` | User explicitly accepted the consequence in the revision sentence. | `affects` `REQ-001`, `INV-002`; `accepted by` `DEC-001`; `produces` `AC-002` |
| `IMP-003` | Member edits will produce actor-role audit events, so audit consumers must continue to distinguish member edits from owner/admin edits. | `verified` | `unchanged` | Supplied actor-role audit behavior remains an invariant; no consumer behavior was supplied. | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | The treatment of pending invitees and any project-level exceptions remains unverified; the user clarified ordinary access for default-member invitees but did not establish whether a pending, non-member invitee can edit or identify all existing exceptions. | `unknown` | `blocked` | No repository role matrix, membership lifecycle contract, or project-exception policy supplied. | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | Sensitive-field protection must remain owner/admin-only while ordinary fields become member-editable; the supplied facts do not show a field-level authorization mechanism or test coverage. | `inferred` | `refining` | The user’s selected policy establishes the target split; current authorization evidence is only role-level. | `affects` `REQ-001`, `INV-001`; `mitigated by` `DEC-001`; `produces` `AC-005` |

## Delta

- `resolved`: none
- `mitigated`: `IMP-001`
- `unchanged`: `IMP-003`
- `accepted`: `IMP-002`
- `deferred`: none
- `blocked`: `IMP-004`
- `new`: `IMP-005`

The categories are disjoint and exhaustive across `IMP-001` through `IMP-005`.

## Stop check and planning handoff

The requirement is refined and the explicit choice is recorded. Remaining work is report-only handoff: `IMP-004` is blocked by the missing membership/exception policy, `IMP-005` remains a field-level authorization validation gap, and `IMP-002` is accepted through `DEC-001`. No implementation tasks, work breakdown, plan, or repository edit is included.

### Acceptance criteria targets

| ID | Future criterion | Evidence / gap |
| --- | --- | --- |
| `AC-001` | A workspace member can edit ordinary fields on every project; the same member cannot edit owner/admin-only sensitive fields. | Produced by `IMP-001`; field-level enforcement is not inspected. |
| `AC-002` | A default-member invitee receives ordinary project edit access immediately at the selected membership point, and this behavior is documented as accepted. | Produced by accepted `IMP-002` and linked to `DEC-001`; lifecycle semantics remain partly unverified. |
| `AC-003` | Every project edit records the actor’s effective role, including ordinary edits by members. | Produced by `IMP-003`; audit schema and consumers are not supplied. |
| `AC-004` | Pending-invite and project-exception behavior is explicitly defined and tested. | Produced by blocked `IMP-004`; role/membership policy is unavailable. |
| `AC-005` | Sensitive fields remain editable only by owners/admins while ordinary fields are editable by members. | Produced by `IMP-005`; current evidence does not demonstrate field-level authorization or coverage. |
