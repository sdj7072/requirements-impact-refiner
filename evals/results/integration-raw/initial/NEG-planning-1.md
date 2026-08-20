# Implementation Plan: Profile Nickname in Settings

The requirements and impact review are approved and authoritative. Implement the profile nickname as a persisted user-profile attribute, expose it through the existing settings/profile API, and cover the behavior with focused API, persistence, validation, and regression tests.

## 1. Establish the data model and migration

- Add a nullable `nickname` column to the existing user profile table, using the project’s normal string/text type and naming conventions.
- Set the column’s length and nullability to match the approved contract. Preserve existing rows by making the migration backward-compatible; existing users should read as having no nickname.
- Add the migration to the project’s normal migration sequence and verify it works on both an empty database and a database containing existing profiles.
- Update the profile entity/model, database mapping, and repository/query projections so reads and writes include `nickname` without changing existing fields.

## 2. Extend the existing settings/profile API

- Locate the current authenticated settings/profile read and update endpoints and extend their existing DTOs/contracts with `nickname` rather than introducing a parallel endpoint.
- On reads, return the persisted nickname (or the contract’s defined empty/null representation) for the current user.
- On updates, accept nickname changes, persist them against the authenticated user’s profile, and return the same canonical representation used by the read response.
- Reuse the endpoint’s existing authentication, authorization, transaction, error, and response conventions. Do not allow a caller to select another user by supplying an ID.
- Apply the approved validation rules consistently at the API boundary: trim only if that is part of the approved behavior, enforce the agreed maximum length, and reject invalid input using the API’s existing validation error shape. Define the empty-value behavior explicitly in the implementation (clear to null/empty, according to the approved contract).
- Ensure partial-update semantics remain unchanged for fields omitted from the request; an omitted nickname must not accidentally overwrite the stored value.

## 3. Update settings/profile presentation and client types

- Add the nickname field to the existing settings/profile form and wire it to the existing load/save flow.
- Initialize the control from the API response, submit the field using the established update payload, and display server-side validation errors through the existing form mechanism.
- Update generated/manual client types, serializers, fixtures, and any profile selectors/view models that mirror the API contract.
- Preserve current behavior and layout for users who have no nickname, including loading, save success, retry, and error states.

## 4. Add tests before implementation changes are considered complete

- Migration/persistence tests: create a profile with a nickname, read it back, update it, clear it, and confirm old rows migrate/read safely.
- API contract tests: authenticated read returns nickname; authenticated update persists and returns it; omitted nickname preserves the prior value; invalid/overlong input uses the existing error response; unauthenticated and cross-user attempts remain rejected.
- Service/repository tests where the project normally places business and persistence coverage, including null/empty handling and transaction behavior.
- UI/client tests for initial population, editing/submission, clearing, validation feedback, and regression of existing settings fields.
- Run the focused test suites, migration checks, type checks/lint, and the full regression suite used by the project. Verify the API contract or generated client artifacts are up to date.

## 5. Delivery checkpoints

1. Confirm the approved nickname rules and identify the existing profile/settings endpoint, DTOs, table, migration convention, and test locations.
2. Add the backward-compatible schema migration and model/repository mapping; run persistence tests.
3. Extend the existing API read/update path with validation and unchanged partial-update/auth semantics; run API tests.
4. Wire the settings UI/client contract and add UI regression coverage.
5. Run all verification commands, inspect the migration and API diff, and document the endpoint/schema behavior in the project’s normal API/database documentation if such documentation exists.

## Completion criteria

- A user’s nickname is stored in the existing user profile table and survives subsequent reads.
- The existing settings/profile API can read, set, update, and clear the nickname according to the approved contract.
- Existing profile fields, omitted-field semantics, authentication/authorization, and error conventions are unchanged.
- Empty/legacy profiles remain valid after migration.
- Focused and full regression tests pass, including migration, API, persistence, and client/settings coverage.
