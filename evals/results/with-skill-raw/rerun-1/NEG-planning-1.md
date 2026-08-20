# Implementation plan: profile nickname

## Objective

Add an optional profile nickname to the existing account settings page. The value must be stored in the user profile table, returned by the existing profile API, editable through the current settings flow, and covered by automated tests.

## Scope and assumptions

- Extend the existing account-settings form and its current save/update path; do not introduce a second settings page or endpoint.
- Treat the nickname as user-owned profile data, scoped to the authenticated user and subject to the same authorization and validation rules as the other profile fields.
- Preserve existing behavior for users with no nickname. A missing or blank value should remain representable as empty/null according to the project’s existing profile-field convention.
- Reuse the project’s established migration, API response, form validation, and test patterns. Exact file names should be confirmed during implementation from the existing account settings, profile model/table, and profile API code.

## Planned changes

1. **Data model and persistence**

   - Add a nullable nickname column to the user profile table using the repository’s normal schema migration mechanism.
   - Match the existing naming, type, length limit, collation, and timestamp conventions for profile text fields.
   - Update the profile entity/model, ORM mapping, serializers, and repository/query projections so reads and writes include the new field.
   - Ensure the migration is safe for existing rows by providing a null/empty-compatible default and does not overwrite existing profile data.

2. **Profile API**

   - Extend the existing profile read response with a `nickname` field, using the API’s established representation for absent values.
   - Extend the existing profile update/request schema and handler so an authenticated user can set, change, or clear their own nickname.
   - Apply the established validation and normalization rules: trim surrounding whitespace, enforce the agreed maximum length, and reject invalid input consistently with neighboring fields.
   - Preserve response status codes, error format, authentication checks, and unrelated profile fields.

3. **Account settings UI**

   - Add a labeled nickname input to the existing account settings form, placed with the other profile fields.
   - Initialize it from the profile API response, submit it through the existing save action, and reflect successful updates without requiring a separate refresh beyond the current flow.
   - Add accessible label/description and validation/error messaging consistent with the current form components.
   - Support clearing the value and show the same loading, disabled, success, and failure states used by the existing settings controls.

4. **Tests**

   - Add migration/model or repository coverage proving the nickname can be persisted, read, updated, and cleared.
   - Add profile API tests for response inclusion, authenticated self-update, validation failures, clearing, and protection against modifying another user’s profile.
   - Add account-settings component/integration tests covering initial rendering, editing, submission payload, validation/error handling, and successful persistence feedback.
   - Retain regression coverage for existing profile fields and run the project’s full relevant test suite plus migration/schema checks.

## Acceptance criteria

- Existing users can open account settings and see an empty nickname when none is stored.
- A user can enter a valid nickname, save it, reload the settings page, and see the persisted value.
- A user can edit or clear the nickname; the API and database reflect the change.
- The profile API exposes `nickname` on reads and accepts it on the existing update path without changing unrelated contract behavior.
- Invalid or overlong values receive the project-standard validation response and do not alter stored data.
- Authorization prevents cross-user profile updates.
- Automated tests cover persistence, API behavior, UI behavior, and regressions, and all relevant checks pass.

## Implementation order and verification

Implement the schema/model migration first, then wire the profile API, then connect the settings form, and finally add/adjust end-to-end coverage. Verify the generated migration against an existing database, run focused tests after each layer, and finish with the complete relevant test suite and lint/type checks. Document the final field semantics (nullable versus empty string and maximum length) alongside the API/schema definition.

## Open implementation detail

Before coding, confirm the repository’s existing conventions for profile text fields and the exact migration/API/UI test locations. This is a code-navigation step, not a requirement decision; the approved behavior above remains unchanged.
