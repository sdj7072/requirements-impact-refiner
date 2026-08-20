# Implementation plan: profile nickname

## Scope

Implement the approved requirement to add a profile nickname to the existing account settings experience. The nickname is user-owned profile data, persisted in the existing user profile table, and exposed through the existing profile API. Existing behavior and API consumers must remain compatible when the nickname is unset.

## Plan

1. **Extend the profile data model and schema**
   - Add a nullable `nickname` column to the existing user profile table using the project’s established string type and length convention.
   - Add the corresponding model/entity field, serialization mapping, and migration entry.
   - Make the migration additive and safe for existing rows; no backfill is required unless the repository’s profile model requires a non-null value.

2. **Update the profile API contract and persistence path**
   - Add `nickname` to the existing profile response DTO/schema.
   - Accept `nickname` in the existing profile update request, applying the same authorization and ownership checks already used for profile fields.
   - Validate and normalize according to existing profile-field rules (trim surrounding whitespace, enforce the chosen maximum length, and define whether an empty value is stored as `NULL` or an empty string consistently with current conventions).
   - Read and write the field through the existing profile repository/service path; do not introduce a parallel endpoint.
   - Preserve backward compatibility: omitted nickname fields leave the current value unchanged for updates, and older clients can ignore the new response field.

3. **Add the account-settings UI field**
   - Add a controlled nickname input to the current account settings/profile form.
   - Initialize it from the profile API response, submit it through the existing save flow, and show the existing loading, success, and error states.
   - Reuse the page’s current form components, labels, validation messaging, accessibility wiring, and layout styles.
   - Ensure the field works for unset, edited, cleared, and validation-error states.

4. **Tests**
   - Migration/schema test (or equivalent repository migration verification) confirms the column is created safely.
   - Model/repository tests cover reading, creating, updating, and clearing a nickname.
   - API tests cover the field in profile responses, authorized updates, omitted-field preservation, clearing, validation/length rejection, and unauthorized access/update behavior using the existing test conventions.
   - UI tests cover rendering the fetched nickname, editing and submitting it, clearing it, and displaying API validation errors.
   - Run the focused test suites, then the full project verification command and migration checks.

## Acceptance criteria

- A user can enter, save, view, edit, and clear a nickname from the existing account settings page.
- The value persists in the user profile table and is returned by the existing profile API.
- Profile updates enforce existing authorization and validation conventions.
- Existing users and clients continue to work when no nickname is set or when they omit the new field.
- Automated coverage verifies schema, persistence, API, UI, validation, and regression behavior.

## Delivery notes

Implement in dependency order: schema/model, API/service, UI, then tests and verification. Keep the migration independently deployable before code that reads or writes the new field, and document the final field name, maximum length, empty-value semantics, and API examples in the project’s existing contract documentation if present.
