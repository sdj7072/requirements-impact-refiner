# Implementation plan: profile nickname

The requirement and impact review are settled, so this is a direct planning handoff.

## Scope

Add an optional profile nickname to the existing account settings experience. Store it in the user profile table, include it in the existing profile API’s read and update contract, and cover the behavior with focused automated tests. Preserve all existing profile fields and account-settings behavior.

## Implementation steps

1. **Trace the existing profile flow.** Locate the account settings page/form, its profile data-loading and save path, the profile API handlers/schema/serializer, the user profile table definition and migration conventions, and the existing profile/settings test fixtures. Reuse established validation, authorization, error handling, and naming patterns.

2. **Extend persistence.** Add a nullable (or project-standard optional) nickname column to the user profile table, using the repository’s established string type and length constraints. Create the corresponding migration, with no destructive change to existing rows; existing users should read as having no nickname.

3. **Extend the profile API.** Include `nickname` in the existing profile response. Accept it in the existing profile update request, validate it using the product’s established profile rules (including trimming/empty-value behavior and maximum length), persist the normalized value, and return the updated profile. Keep the existing authorization boundary and response/error shape unchanged.

4. **Update account settings UI.** Add a labeled nickname input to the current account settings page, initialize it from the profile response, submit it through the existing save flow, show the existing loading/success/error states, and ensure keyboard/accessibility behavior matches neighboring fields. Do not alter unrelated settings.

5. **Add tests.** Add migration/schema coverage if the project tests migrations; API tests for reading a nickname, updating it, empty/omitted input, validation failure, persistence, and unauthorized access; and page/component or integration tests proving the field renders, is populated, submits successfully, and surfaces the existing error state. Include a regression assertion that existing profile fields and update behavior remain intact.

6. **Verify.** Run the targeted persistence, API, and UI tests, then the project’s relevant full test/typecheck/lint commands. Apply the migration against a clean database and an existing-user fixture if the repository supports those checks.

## Acceptance criteria

- Account settings displays an editable nickname field using the existing page conventions.
- A saved nickname is persisted in the user profile table and is returned by the existing profile API.
- Loading the page again displays the saved nickname.
- Omitted or empty nickname follows the repository’s established optional-field semantics; invalid values receive the existing validation response.
- Existing users and profile fields continue to work without backfill or data loss.
- Authorization, loading, success, and error behavior remain consistent with the existing profile flow.
- Automated tests cover persistence, API read/update/error paths, UI rendering/submission, and regression behavior.
