# Authorization impact: workspace members may edit every project

## Current behavior

- `authorizeProjectEdit` permits project edits only for owners and admins.
- Workspace invitations default to the `member` role.
- Project edits emit an audit event containing the actor's role.

## Required behavior

Every workspace member must be authorized to edit every project in that workspace. The authorization rule must therefore include the `member` role alongside `owner` and `admin`, while still enforcing the existing workspace/project relationship and any other applicable authorization constraints.

Because invitations already default to `member`, newly invited users should gain project-edit access through the updated authorization rule without changing the invitation default. Existing members should also gain the capability once the rule is deployed.

## Audit implications

Project-edit audit events must continue to record the actor's role. The system should accept and accurately persist `member` as a valid actor role for project edits, so edits by ordinary workspace members remain attributable and distinguishable from edits by owners or admins. No audit event should be emitted for an unauthorized edit attempt unless existing conventions explicitly record denied actions.

## Scope and compatibility

- Update the project-edit authorization policy/check to allow `member`.
- Leave invitation role defaults unchanged.
- Preserve owner/admin access and existing denial behavior for users outside the workspace or with unrelated roles.
- Preserve the audit event shape and role attribution; extend role handling only where validation or fixtures currently assume owners/admins are the only possible editors.

## Acceptance criteria

1. A workspace owner can edit any project in the workspace.
2. A workspace admin can edit any project in the workspace.
3. A workspace member, including a user who joined through an invitation with the default role, can edit any project in the workspace.
4. A user who is not a member of the workspace cannot edit its projects.
5. Audit events for edits by members identify the actor and record `member` as the actor role.
6. Existing owner/admin audit attribution and authorization behavior remain unchanged.
