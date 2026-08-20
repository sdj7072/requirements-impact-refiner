# Authorization impact: workspace members can edit every project

## Decision

Update `authorizeProjectEdit` so that workspace members, admins, and owners are all permitted to edit projects in the workspace. The existing owner and admin permissions remain unchanged.

## Existing behavior

- `authorizeProjectEdit` currently permits only `owner` and `admin` roles.
- Workspace invitations default to the `member` role.
- Project edits emit an audit event containing the actor's role.

## Required behavior

Any authenticated workspace member with the `member`, `admin`, or `owner` role can edit every project belonging to that workspace, subject to the existing authentication, workspace-membership, and project-scope checks. A user who is not a workspace member must continue to be denied.

Because invitations already create `member` users, newly accepted invitees should gain project-edit access without any invitation-flow change. No role escalation or invitation-default change is required.

## Audit implications

Keep emitting the existing project-edit audit event and preserve the actor-role field. Edits performed by ordinary members must be recorded with `actorRole: "member"`; admin and owner events should retain their current role values. The authorization change must not bypass or weaken audit logging.

## Acceptance criteria

1. A workspace `member` can edit any project in that workspace.
2. Workspace `admin` and `owner` users retain edit access.
3. Non-members cannot edit projects.
4. Invited users who accept an invitation with the default `member` role can edit projects immediately.
5. Every successful project edit emits the existing audit event with the correct actor role, including `member`.
6. Existing project ownership, membership validation, authentication, and error behavior remain intact except for the newly authorized `member` role.

## Test coverage expected

Add or update authorization tests for member, admin, owner, and non-member cases. Add an audit assertion verifying that a member edit records the actor role as `member`, and an invitation-path assertion confirming that the default invite role receives the new permission.
