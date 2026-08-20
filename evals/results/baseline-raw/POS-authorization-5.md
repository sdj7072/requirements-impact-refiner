# Authorization impact

Allowing every workspace member to edit every project requires broadening project-edit authorization from `owner` and `admin` to include the `member` role.

The workspace invitation default already produces `member` accounts, so no invitation-flow change is required. Once authorization is updated, newly invited members and existing members should both be able to edit any project in the workspace, subject to the normal workspace-membership check.

Project-edit audit events should continue to record the authenticated actor and their role. For member edits, the event must identify the actor role as `member`; no privilege escalation or role rewriting should occur. Existing owner/admin audit behavior remains unchanged.

Implementation impact:

- Update the project-edit authorization policy/check to permit `member` in addition to `owner` and `admin`.
- Preserve denial for users who are not workspace members and for any unrelated project-level restrictions.
- Add or update authorization coverage for owner, admin, and member editors, including an invited member using the default role.
- Add or update audit coverage proving a member edit emits the correct actor identity and `member` role.
- Review any UI or API capability checks that independently restrict editing to owner/admin so they match the server-side policy.

This is a permission expansion: all workspace members gain write access to all projects, and the change should be documented in release notes or workspace-permission guidance.
