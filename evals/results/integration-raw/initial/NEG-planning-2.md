# Implementation plan: profile nickname in settings

## Objective

Allow an authenticated user to view and update a profile nickname from the existing settings flow. Persist the nickname in the user-profile table, expose it through the existing settings/profile API contract, and protect the behavior with unit, integration, and migration coverage. Existing users and existing settings fields must continue to work unchanged.

## Implementation steps

1. **Map the existing settings/profile flow before editing.**
   - Identify the current user-profile table/schema definition and migration numbering convention.
   - Locate the settings read/update API handler, request/response DTOs or schemas, service/repository methods, and settings UI/client types.
   - Follow the repository’s existing naming, authorization, validation, transaction, and error-response conventions. Record the exact files discovered in the implementation PR; no new endpoint is needed if the existing API already owns profile settings.

2. **Extend the user-profile schema with a backward-compatible column.**
   - Add a nullable (or the project’s established optional-string equivalent) `nickname` column to the user-profile table, preserving existing rows and avoiding a required-value backfill.
   - Add the next forward migration and its rollback/down migration if the project supports rollbacks.
   - Use the established length, character-set, collation, and indexing conventions. Do not add a uniqueness constraint unless the approved product requirement already mandates unique nicknames; the default plan treats nickname as display data and permits duplicates.
   - Update schema snapshots/generated types/ORM models and seed fixtures as applicable.

3. **Update domain and persistence layers.**
   - Add an optional nickname field to the profile entity/model and repository projection.
   - Include nickname in the existing settings/profile read query and update command.
   - Keep update semantics explicit: an omitted field leaves the current value unchanged; a supplied empty value follows the existing settings convention (either clears to `NULL` or is rejected by validation), and the chosen behavior must be covered by tests.
   - Preserve authorization so a caller can read/update only the authenticated user’s profile, using the existing transaction and not-found behavior.

4. **Extend the existing API contract.**
   - Add `nickname` to the existing settings/profile response schema and client-facing type.
   - Add `nickname` to the existing update request schema, with the project’s standard trimming and maximum-length validation; reject invalid input with the same 4xx shape used by other settings fields.
   - Return the persisted value on both read and successful update, while retaining all existing response fields and status codes.
   - Update API documentation/OpenAPI or generated contract artifacts if present.

5. **Wire the settings UI/client.**
   - Add a controlled nickname input to the existing profile/settings section, initialized from the API response.
   - Submit it through the existing settings update path, preserving loading, optimistic/error, reset, and success behavior.
   - Ensure labels, accessible descriptions, character limits, and validation messages follow the existing settings components and localization conventions.

6. **Add and update tests.**
   - Migration test: apply the migration against a representative pre-existing schema, verify existing profiles survive, and verify the new column accepts the intended empty/optional state; test rollback where supported.
   - Repository/service tests: read and update nickname, omitted-field preservation, empty-value behavior, authorization, and missing-profile behavior.
   - API tests: response includes nickname, valid update persists and echoes it, invalid/overlong input returns the standard validation response, and existing fields remain compatible.
   - UI/client tests: initial rendering, edit/save, validation error, API error, and successful persistence/reload if this layer has tests.
   - Run the focused suites first, then the full test/build/typecheck commands used by the repository.

## Verification and rollout

- Review the generated migration SQL and generated model/contract diffs before applying them.
- Verify a pre-migration user can load settings, save unrelated settings, set a nickname, clear it according to the approved semantics, and load the value in a new session.
- Confirm authorization and existing API consumers remain compatible because the response addition is non-breaking and the request field is optional.
- Deploy the migration before or atomically with the application version according to the project’s migration policy; monitor API validation/error rates and profile update failures after release.

## Completion criteria

- Existing user profiles migrate without data loss or a mandatory backfill.
- Authenticated settings reads and updates round-trip nickname correctly.
- Validation, empty/omitted update semantics, and authorization are tested.
- Existing settings fields, response shape, status codes, and clients continue to pass their regression suites.
- Migration, API/schema artifacts, UI, and tests are all included in the same reviewed change.
