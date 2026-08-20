# Authorization impact

Let every workspace member edit every project by expanding project-edit authorization from the current owner/admin-only rule to include the `member` role.

Workspace invitations already default to `member`, so newly invited users will receive project-edit access without an invitation-flow change. Preserve the existing actor-role audit event for project edits; it will now record member actors as well as owners and admins. Update authorization tests and any permission documentation to cover member edits, while retaining the existing workspace boundary and authentication checks.
