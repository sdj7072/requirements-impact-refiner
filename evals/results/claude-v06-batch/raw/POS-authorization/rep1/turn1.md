Done. Widened the `authorization.workspace_edit` gate so workspace members can edit every project.

Change made in `/private/tmp/claude-501/-Users-p042890-workspace-polaris/074a0f85-287f-4435-929b-4948eb69c993/scratchpad/batch-v06/POS-authorization/rep1/auth/authorize.py`:
- `PERMITTED` was `("owner", "admin")` and is now `("owner", "admin", "member")`.

Rationale and related files reviewed:
- `roles/defaults.py` sets `INVITATION_DEFAULT_ROLE = "member"`, so newly invited workspace users land in the `member` role — adding `member` to the gate is exactly what grants them edit access to every project.
- `events/audit.py` (`emit_actor_role_audit`) records the actor's role on each project edit, so the widened permission will now surface `member` as the actor role in `project.edit.audited` events; no change needed there.

Note: this is a genuine authorization broadening — every workspace member can now edit any project in the workspace, with no per-project scoping. If the intent was to gate on project membership rather than blanket workspace-wide edit rights, that would need additional logic in `authorize_project_edit`.