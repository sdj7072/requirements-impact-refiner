# Implementation plan: profile nickname

The requirement and impact review are approved and authoritative. Implement a profile nickname that is persisted with the user profile, editable through the existing settings flow/API, and covered by regression tests. Preserve all existing settings behavior and response fields.

## 1. Map the existing settings/profile path

- Locate the user profile table/schema and its migration convention.
- Locate the profile/settings model, repository/data-access methods, existing settings API route/handler, request validation, and serialization types.
- Identify the existing API and test fixtures used for reading and updating profile settings; use the established naming and error conventions.

## 2. Add persistence

- Add a forward-only database migration that adds a `nickname` column to the user profile table, using the project’s established type, nullability, length, and timestamp conventions.
- Make the column nullable (or otherwise backward-compatible with existing rows) and avoid changing defaults for unrelated profile fields.
- Update the profile entity/model and read/write projections so nickname is loaded and saved without dropping existing fields.
- If the project has generated schema/types, regenerate or update them through the normal project mechanism.

## 3. Extend the existing settings API

- Add nickname to the existing settings/profile response contract, representing an unset value consistently with current API conventions.
- Accept nickname in the existing profile/settings update request rather than creating a new endpoint.
- Apply the existing validation and authorization path: trim/normalize only if that is already the settings contract, enforce the selected maximum length, and reject invalid input using the API’s existing validation shape.
- Ensure partial updates remain partial: omitted nickname leaves the stored value unchanged, while an explicit empty/null value follows the existing clearing semantics.
- Keep response status codes, authentication/authorization checks, and all unrelated fields backward-compatible.

## 4. Update settings/profile UI integration (if present in this codebase)

- Add the nickname field to the existing settings form/view model and bind it to the existing read/update call.
- Preserve loading, save, error, and optimistic/concurrent-update behavior already used by neighboring profile fields.
- Add the same accessible label/help/error treatment as the existing settings inputs.

## 5. Tests

- Migration/schema test: the profile table accepts an unset nickname and stores/retrieves a populated nickname.
- Data-access/model test: profile reads and updates round-trip nickname while retaining unrelated fields.
- API contract tests: authenticated read returns nickname; update persists and returns it; omitted nickname does not overwrite; clearing works as specified; invalid/overlong input returns the existing validation response; unauthorized access remains rejected.
- Regression tests: existing settings fields and response shape continue to work for profiles created before the migration.
- If UI tests exist, cover initial population, editing/saving, clearing, and validation display.

## 6. Verification and delivery

- Run the focused migration, model, and API/UI tests first, then the full relevant test suite and type/lint checks.
- Inspect the generated migration and API schema/diff for accidental changes to unrelated fields.
- Confirm a fresh database and a database containing pre-migration users both work, and document the migration/rollback limitation according to the project’s migration policy.

## Acceptance checklist

- Existing user profiles migrate without data loss or required backfill.
- Nickname can be read, set, updated, and cleared through the existing settings API.
- Partial updates preserve omitted values.
- Validation, authorization, and error formats match existing behavior.
- Focused and full regression tests pass, including pre-existing profiles.
