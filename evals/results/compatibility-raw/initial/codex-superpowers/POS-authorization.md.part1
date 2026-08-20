# Requirements Impact Refinement — Project edit authorization

**Status:** `NEEDS_DECISION` — the permission boundary is under-specified. No option has been selected; no implementation plan or repository edit is proposed.

## Requirement revision

`REQ-001`: Let workspace members edit every project. Preserve the existing workspace invitation default and actor-role audit behavior while refining the authorization boundary; the exact treatment of membership state and role policy remains the pending decision.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence | Level | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | `authorizeProjectEdit` currently permits project edits for workspace owners and administrators; the `member` role is not currently permitted. | Supplied fact: “authorizeProjectEdit currently permits owner and admin roles.” | `verified` | `must-preserve` `REQ-001` |
| `INV-002` | Workspace invitations default to the `member` role. | Supplied fact: “workspace invitations default to member.” | `verified` | `must-preserve` `REQ-001` |
| `INV-003` | Project edits emit an audit event containing the actor’s role. | Supplied fact: “project edits emit an actor-role audit event.” | `verified` | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | State | Evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | The requested outcome conflicts with the current authorization boundary: workspace members cannot currently edit projects. | `verified` | `refining` | Supplied current behavior for `authorizeProjectEdit`. | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | Because invitations default to `member`, allowing members to edit broadens the effective privileges of newly accepted invitees; changing the invitation role policy would instead alter onboarding and least-privilege expectations. | `verified` | `detected` | Supplied invitation-default fact. | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | Newly permitted member edits will produce audit events whose actor role is `member`, affecting audit interpretation and any downstream review or alerting that distinguishes roles. | `verified` | `detected` | Supplied actor-role audit fact. | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | The supplied facts do not establish whether “workspace members” means accepted members only or also pending invitees, or whether project-level exceptions exist. | `unknown` | `blocked` | No role matrix, membership-state contract, or project-exception policy supplied. | `affects` `REQ-001`; `produces` `AC-004` |

## One focused decision

What permission boundary should “workspace members” establish?

1. **Accepted members only (recommended)** — permit the existing `member` role to edit every project once membership is active; keep invitation defaults and actor-role audit fields unchanged.
2. **Role-policy expansion** — revise the invitation/role policy as part of this change so the edit-capable role assignment is explicit, including the default for new invitees.
3. **All workspace-associated identities** — include pending invitees or other non-member workspace identities in the edit boundary, with corresponding authorization and audit semantics.

Please select one option or specify another policy covering accepted versus pending membership, invitation defaults, project exceptions, and audit semantics. No decision has been recorded; the pending decision is required before a concrete `DEC-###` can be created.

## Recorded decision

Decision needed — no `DEC-###` is recorded because no user/stakeholder option has been selected.

## Whole-set recalculation (before decision)

All known impacts were rechecked against the supplied authorization, invitation, and audit facts. No impact is resolved, mitigated, accepted, deferred, or new before the permission-boundary decision.

## Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-002`, `IMP-003`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`
- `new`: none

## Stop check and planning handoff

Stopped at the single required permission-boundary decision. The refined requirement, preserved invariants, evidence-backed impacts, open evidence gap, and provisional acceptance criteria are ready for continuation after selection. This report does not invoke `writing-plans` and contains no implementation tasks or repository edit.

### Acceptance criteria targets

| ID | Future criterion | Evidence / gap |
| --- | --- | --- |
| `AC-001` | An accepted workspace member can edit every project, while the selected authorization boundary is enforced consistently. | Target derived from `IMP-001`; authorization contract beyond the supplied fact is not inspected. |
| `AC-002` | The selected invitation and role policy is reflected consistently in who can edit after invitation acceptance. | Target derived from `IMP-002`; role matrix and onboarding tests are not supplied. |
| `AC-003` | Every project edit records the actor’s effective role, including edits by members if permitted. | Target derived from `IMP-003`; audit schema and consumer behavior are not supplied. |
| `AC-004` | The chosen treatment of pending invitees and any project-level exceptions is explicit and testable. | Target derived from blocked `IMP-004`; repository authorization policy is unavailable. |

---

## Decision response and whole-set recalculation

### Recorded decision

`DEC-001`: **Narrowed ordinary-field policy.** Members may edit ordinary project fields, while sensitive project fields remain restricted to workspace owners and administrators. The requester explicitly accepts that default-member invitees gain ordinary edit access immediately. This decision preserves actor-role audit events and does not grant pending or non-member identities access unless they have the `member` role.

### Revised requirement

`REQ-001` (revised): A workspace member with the `member` role can edit ordinary fields on every project. Sensitive fields remain owner/admin-only. Default-member invitees receive ordinary edit access immediately when the invitation establishes their member role. Every edit continues to emit an audit event containing the actor’s effective role.

### Disjoint lifecycle recalculation

| ID | Post-decision impact | Level | State | Decision effect / evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | The former all-or-nothing authorization conflict is removed for ordinary fields: the selected policy explicitly grants members ordinary edits while retaining the owner/admin boundary for sensitive fields. | `verified` | `resolved` | Explicit scope selected in `DEC-001`; current owner/admin-only behavior supplied as the baseline. | `affects` `REQ-001`, `INV-001`; `resolved-by` `DEC-001` |
| `IMP-002` | Default-member invitees gain ordinary project-edit privileges immediately, broadening their effective access as intentionally selected. | `verified` | `accepted` | Explicit requester acceptance in the second-turn decision and `DEC-001`; invitation default remains `member`. | `affects` `REQ-001`, `INV-002`; `accepted-by` `DEC-001`; `produces` `AC-002` |
| `IMP-003` | Member edits will be recorded with actor role `member`; the existing actor-role audit invariant remains, but audit consumers must interpret ordinary member edits as authorized activity. | `verified` | `mitigated` | `DEC-001` preserves actor-role audit events and makes the new member role explicit; downstream consumer behavior is not supplied. | `affects` `REQ-001`, `INV-003`; `mitigated-by` `DEC-001`; `produces` `AC-003` |
| `IMP-004` | The membership boundary is explicit: the policy applies to identities holding the `member` role, including default-member invitees once that role is established; pending or non-member identities are not granted access. | `verified` | `resolved` | Membership and invitation treatment selected in `DEC-001`; no separate pending-invite access is authorized. | `affects` `REQ-001`; `resolved-by` `DEC-001`; `produces` `AC-004` |

### New impacts introduced by the decision

| ID | New impact | Level | State | Evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-005` | Authorization must distinguish ordinary project fields from sensitive fields on every edit path; a member must not reach a sensitive-field update through a bulk, alternate, or indirect path. | `verified` | `detected` | The selected ordinary-versus-sensitive boundary in `DEC-001`; field-level authorization implementation is not supplied. | `affects` `REQ-001`, `INV-001`; `produces` `AC-005` |
| `IMP-006` | Audit records must preserve the actor’s effective role and distinguish member ordinary edits from owner/admin sensitive edits so downstream review does not misclassify the new access. | `inferred` | `detected` | Actor-role audit invariant combined with the selected role expansion; audit consumers are not supplied. | `affects` `REQ-001`, `INV-003`; `produces` `AC-006` |

### Delta

- `resolved`: `IMP-001`, `IMP-004`
- `mitigated`: `IMP-003`
- `unchanged`: none
- `accepted`: `IMP-002`
- `deferred`: none
- `blocked`: none
- `new`: `IMP-005`, `IMP-006`

### Acceptance criteria after decision

| ID | Criterion | Traceability |
| --- | --- | --- |
| `AC-001` | A member can edit ordinary fields on every project, while owner/admin-only sensitive-field restrictions remain enforced. | Resolves `IMP-001`; `DEC-001` |
| `AC-002` | A default-member invitee receives ordinary edit access immediately when the member role is established; this access is recorded as an explicitly accepted policy consequence. | Accepted `IMP-002`; `DEC-001` |
| `AC-003` | Every project edit, including a member ordinary-field edit, records the actor’s effective role in the audit event. | Mitigates `IMP-003`; `DEC-001` |
| `AC-004` | Pending or non-member identities cannot edit ordinary or sensitive project fields unless and until they receive the selected member role. | Resolves `IMP-004`; `DEC-001` |
| `AC-005` | All update paths reject member attempts to change sensitive fields, including bulk and alternate update paths. | New `IMP-005`; field-level authorization evidence is currently unavailable. |
| `AC-006` | Audit review can distinguish member ordinary edits from owner/admin sensitive edits without losing the actor-role field. | New `IMP-006`; audit-consumer behavior is currently unavailable. |

## Stop check

`DEC-001` is recorded and every known impact has been recalculated exactly once in the disjoint delta. `IMP-002` remains explicitly accepted; the remaining detected impacts have concrete acceptance criteria and evidence gaps. This response stops at the refined requirement and planning handoff. No implementation plan, task breakdown, or repository code edit is produced.
