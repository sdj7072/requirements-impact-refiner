# Implementation plan: profile nickname

## Objective

Add a nickname to the existing account-settings/profile flow. A signed-in user must be able to view, set, edit, clear, and persist the nickname. The value must live in the existing user profile table and be exposed through the existing profile API without breaking clients that do not send it.

## Implementation sequence

1. **Map the existing profile flow.** Locate the user-profile table/entity and migration conventions, profile repository/service, existing read and update API schemas/handlers, and the account-settings form. Record the current authorization, validation, partial-update, error, loading, and success-state conventions so the new field follows them.

2. **Add the database field.** Create an additive migration for a `nickname` column on the existing user profile table, using the project’s established text type and length convention. Make it nullable (or use the repository’s established unset representation) so existing rows migrate safely. Add the normal rollback/down path if the project maintains one, and update schema snapshots/generated artifacts when applicable.

3. **Update persistence and domain types.** Add `nickname` to the profile model/entity, repository projections, create/update mappings, and serialization code. Preserve the existing empty-value convention: define and implement whether clearing stores `NULL` or an empty string, and apply the same normalization and maximum-length validation at the server boundary.

4. **Extend the existing profile API.** Add `nickname` to the profile response contract and to the existing profile update request. Thread it through the handler/service/repository path. Preserve established partial-update semantics: an omitted nickname leaves the current value unchanged, while an explicit clear follows the chosen empty-value behavior. Reuse the endpoint’s existing authentication and ownership checks; do not add a parallel endpoint. Refresh generated API/client types if the repository uses them.

5. **Add the settings control.** Add a labeled, accessible nickname input to the existing account-settings form using its current form components and layout. Initialize it from the profile response, submit it through the existing save action, and use the current loading, success, validation, and API-error states. Cover unset, edited, cleared, and rejected values without changing unrelated profile fields.

6. **Add regression coverage.** Follow existing test layers and fixtures:
   - migration/schema verification confirms the field is created safely;
   - model/repository tests cover reading, setting, updating, and clearing the value;
   - API tests cover response serialization, authorized update, omitted-field preservation, explicit clearing, validation/length rejection, and cross-user read/update denial;
   - settings-page/component tests cover initial rendering, editing, save submission, clear behavior, loading/success states, and API validation errors.

7. **Verify and review.** Run focused database, backend/API, and UI tests first, then the project’s full test, typecheck, lint, and build commands plus migration checks. Inspect the final diff for accidental contract changes, confirm generated artifacts are synchronized, and verify an existing profile without a nickname still loads and updates normally.

## Acceptance criteria

- The account-settings page lets the authenticated user view, set, edit, and clear a nickname.
- Reloading the page shows the persisted value.
- The existing profile API returns `nickname` and accepts it on updates.
- Omitting `nickname` from an update preserves the existing value; explicit clearing behaves according to the project’s selected null/empty convention.
- Existing profile fields and older clients remain compatible.
- The same authorization boundary protects nickname reads and writes.
- The migration is safe for existing rows and follows repository rollback/update conventions.
- Automated tests cover persistence, API contract and authorization, validation/clearing, UI interaction, and regression behavior.

## Risks to resolve during implementation

- Confirm the repository’s exact null versus empty-string representation before finalizing the column and API schema.
- Confirm whether the update endpoint is PATCH-like or replacement-based so omitted fields cannot be cleared accidentally.
- Reuse the established nickname/profile length and character rules rather than introducing a new policy.
- Ensure schema/client generation and migration ordering match the project’s deployment process.
