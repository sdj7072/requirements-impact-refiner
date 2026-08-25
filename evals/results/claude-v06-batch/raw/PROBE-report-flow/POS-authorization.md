Done. Widened the `authorization.workspace_edit` gate so workspace members can edit every project.

**Change made:**
- probe-v06/POS-authorization/auth/authorize.py — `PERMITTED` widened from `("owner", "admin")` to `("owner", "admin", "member")`; `authorize_project_edit(role)` now returns True for members.

**Related files checked, no changes needed:**
- roles/defaults.py — `INVITATION_DEFAULT_ROLE = "member"` stays as-is; since invitations already default to member, every newly invited workspace member now gets project-edit access automatically.
- events/audit.py — `emit_actor_role_audit` records the actor's role on each edit and works unchanged.
