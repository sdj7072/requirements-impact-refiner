# Implementation plan: profile nickname

## Objective

Add an editable profile nickname to the existing account settings page, persist it in the user profile table, expose it through the existing profile API, and cover the change with automated tests.

## Scope and assumptions

- Extend the existing account-settings/profile flow; do not create a new page or API family.
- Reuse the current authenticated-user lookup, profile table, request validation, response serialization, and UI form conventions.
- The nickname is a user-owned profile attribute. Keep existing behavior unchanged when it is omitted or empty, subject to the project’s established null/empty-string convention.
- Preserve existing API compatibility: existing profile response fields and request behavior remain valid, with `nickname` added as an optional field.
- Apply the project’s existing length, trimming, character, authorization, and error-handling conventions rather than inventing new policy.

## Work breakdown

### 1. Trace the existing vertical slice

Identify the account settings page/component, its form state and submit path, the profile API route/controller and schema, the user profile table/model, and the existing test fixtures/helpers. Confirm the authenticated identity used by the API and the migration/test commands before editing.

### 2. Add the persistence field

- Add a nullable or otherwise optional `nickname` column to the existing user profile table using the repository’s migration conventions.
- Update the profile ORM/model/type definition and any select/insert/update mappings.
- Ensure existing rows migrate safely with the established default (`NULL` or empty value according to current profile semantics).
- Keep the migration reversible if the project convention supports down migrations.

### 3. Extend the profile API

- Add optional `nickname` input to the existing profile update request schema.
- Normalize it consistently with current profile fields (for example, trim surrounding whitespace) and enforce the existing validation/error format, including the maximum length.
- Persist the value only for the authenticated user’s profile; do not permit a caller to select another user’s profile.
- Include `nickname` in the existing profile GET/read response and in the update response or refreshed profile payload, matching current response serialization and omission/null conventions.
- Preserve partial-update semantics so omitted fields are not overwritten.

### 4. Update account settings UI

- Add a labeled nickname input to the existing account settings form, using the project’s established field component, accessibility labeling, validation messaging, loading state, dirty/submit behavior.
- Initialize it from the profile API response and include it in the existing save request.
- Render server-side validation errors through the existing form error path and show the saved value after a successful update.
- Keep the current settings layout and unrelated fields/flows unchanged.

### 5. Add tests

Persistence/API tests:

- Migration/model coverage verifies the field can be read and written for an existing profile.
- Profile read test verifies `nickname` is returned.
- Profile update test verifies a valid nickname persists and is returned.
- Partial-update test verifies omitted nickname remains unchanged.
- Validation tests cover the established boundary/invalid cases (including over-length and normalization behavior).
- Authorization test verifies one user cannot update or read another user’s profile through this path, using the project’s existing auth test pattern.
- Regression assertions verify existing profile fields and response shape remain intact.

UI tests:

- The settings form renders the current nickname.
- Editing and saving sends the nickname through the existing API flow and reflects the saved value.
- Validation/server errors are displayed using the existing conventions.

Add the smallest focused tests in the existing test suites, plus a migration/schema check if that is a standard repository practice.

### 6. Verification

- Run formatter/linter/type checks for changed files.
- Run the focused persistence/API and settings UI tests.
- Run the full relevant test suite and migration validation.
- Manually smoke-test: load settings, edit nickname, save, reload, and verify persistence; exercise blank/invalid input and confirm existing settings still save correctly.

## Acceptance criteria

- A user can edit and save a nickname from the existing account settings page.
- The value is stored in the existing user profile table and survives reloads.
- The existing profile API accepts the optional nickname and returns it in profile data using the established contract conventions.
- Omitted nickname updates preserve the previous value; existing fields and clients continue to work.
- Validation, authorization, loading, and error behavior follow existing application conventions.
- Automated tests cover persistence, API read/update/partial-update/validation/authorization behavior, and the UI interaction; all relevant checks pass.

## Delivery notes

Implement in dependency order: migration/model, API contract and handlers, UI, then tests/verification (tests may be written alongside each slice). Include the migration and any generated schema/type artifacts in the change. Document the final nickname length/normalization behavior in the API schema or nearby developer documentation if the project maintains it there.
