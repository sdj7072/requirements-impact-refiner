# Nickname in Settings and Profile

## Objective

Allow an authenticated user to view and update a personal nickname from Settings. Persist the value in the profile table, expose it through the profile API, and cover the behavior with focused unit/integration tests. Existing users and existing profile fields must continue to work unchanged.

## Implementation plan

1. **Trace the existing profile/settings path before editing.**
   - Locate the profile table/model and its migration convention.
   - Locate the settings screen/form, profile read endpoint, profile update endpoint/server action, validation layer, and their existing tests.
   - Reuse the existing naming, authentication, authorization, error, and serialization conventions rather than introducing a parallel profile flow.

2. **Add the persisted field.**
   - Add a nullable `nickname` text/string column to the existing profile table using the project’s normal migration mechanism.
   - Preserve null for existing rows; do not backfill from email, username, or display name unless the existing product contract already defines such a fallback.
   - Update the profile ORM/schema type and any generated database types.
   - Add the appropriate length/character constraints at the validation boundary (and a database constraint only if that is already the project convention). Normalize whitespace consistently with other profile fields, rejecting or converting an all-whitespace value to null according to the existing update semantics.

3. **Extend the profile API contract.**
   - Include `nickname` in the authenticated profile read response, returning `null` (or the API’s established empty-value representation) when unset.
   - Accept `nickname` in the existing profile update operation, distinguishing an omitted field (leave unchanged) from an explicit empty value (clear, if supported by the existing update contract).
   - Enforce that only the current authenticated user can update the field; preserve current response status and error shapes for authentication, validation, and persistence failures.
   - Update shared request/response schemas, serializers, client types, and API documentation/generated artifacts where applicable.

4. **Add the Settings UI.**
   - Add a labeled nickname input to the existing Settings profile section, initialized from the profile read data.
   - Wire it into the existing form state, dirty-state detection, submit/loading state, success feedback, and error rendering.
   - Use the same accessible label, control, layout, and validation patterns as neighboring profile fields. Ensure keyboard submission and screen-reader error association continue to work.
   - On successful save, keep the returned canonical value in local state so trimming/normalization is reflected immediately; on failure, retain the user’s input and show the existing error treatment.

5. **Update tests.**
   - **Schema/migration:** verify the migration adds `nickname`, existing rows remain valid, and the ORM/schema exposes the field.
   - **API read:** verify an authenticated user receives a populated nickname and an unset nickname; verify another user cannot read beyond the existing authorization boundary.
   - **API update:** verify create/update, clearing behavior if supported, omission semantics, normalization/length validation, unauthenticated access, cross-user access, and persistence across a subsequent read.
   - **UI/component or end-to-end:** verify the field renders with the fetched value, submits the nickname through the existing update path, shows validation/server errors, handles loading/success, and does not regress neighboring settings fields.
   - Update fixtures/factories and snapshots only where required; include a regression assertion that profiles without a nickname continue to render correctly.

6. **Verify and hand off.**
   - Run the focused schema/API/UI test suites first, then the project’s full test/lint/typecheck commands.
   - Apply the migration to a fresh database and an existing-data fixture if the project supports both paths.
   - Review the final diff for accidental changes to profile visibility, update authorization, or unrelated settings behavior.

## API behavior to preserve

| Case | Expected behavior |
|---|---|
| Existing profile with no nickname | Read succeeds and returns the established empty representation. |
| Valid nickname | Read returns it; update persists it and returns the canonical profile shape. |
| Omitted nickname on partial update | Existing nickname remains unchanged. |
| Explicit empty nickname | Clear or reject exactly as the existing profile update contract specifies; document the chosen behavior in the API test. |
| Invalid nickname | Existing validation status/error envelope; no partial persistence. |
| Unauthenticated/cross-user update | Existing authorization response; no write occurs. |

## Acceptance criteria

- A user can set, view, and update their nickname from Settings.
- The value is stored in the profile table and survives reloads/sessions.
- Profile read/update contracts and generated/shared types include the field.
- Existing profiles migrate safely with no required data backfill.
- Validation, authorization, error handling, accessibility, and neighboring settings behavior match existing conventions.
- Focused regression tests and the full project verification suite pass.

## Open implementation decisions to resolve from existing conventions

- Exact migration/table/model/endpoint/component file locations.
- Whether empty nickname clears to `null` or is rejected.
- Maximum length and allowed characters, matching current product validation conventions.
- Whether profile read responses use `null`, an omitted key, or another established empty representation.
