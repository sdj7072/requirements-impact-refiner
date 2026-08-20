# Implementation Plan: Profile Nickname

## Approved scope

Add a profile nickname to settings, persist it in the user profile table, expose it through the existing profile/settings API, and cover the behavior with tests. The approved requirements and completed impact review are authoritative; implementation should preserve existing settings and API behavior for users who do not provide a nickname.

## Plan

1. **Trace the existing profile/settings flow.**
   - Locate the user profile table/model, its migration conventions, profile/settings request and response types, the existing API handler/service, and current tests.
   - Confirm the authenticated user identifier and the project’s established null/default handling before changing contracts.

2. **Extend persistence.**
   - Add a nullable `nickname` column to the user profile table using the repository’s normal migration mechanism.
   - Map the column in the profile entity/model and repository queries, preserving existing rows with `NULL` and avoiding a destructive backfill.
   - Apply the project’s established length, trimming, encoding, and validation conventions; do not introduce uniqueness unless the approved requirement explicitly requires it.

3. **Extend the existing settings/profile API.**
   - Add nickname to the existing read response so current clients receive the persisted value (or the established empty/null representation).
   - Add nickname to the existing update request and write path, including validation and authorization through the same authenticated-user path already used for other profile settings.
   - Keep the field optional for backward compatibility: omitted update payloads must leave the stored nickname unchanged, while an explicitly supported empty value follows the approved clear/reset semantics.
   - Update API schemas, serializers, OpenAPI/contract fixtures, and client-facing types if this repository maintains them.

4. **Add focused tests.**
   - Migration/model test: the column exists and round-trips a nickname, while legacy/null profiles remain readable.
   - Service/API tests: read returns the nickname; update persists it; omitted nickname preserves the prior value; clearing behaves as approved; invalid input is rejected consistently; one user cannot update another user’s profile.
   - Regression tests: existing settings fields and existing request shapes continue to work unchanged.
   - Update snapshots/fixtures only where the new response field is intentionally part of the contract.

5. **Verify and document.**
   - Run the focused persistence, service, and API test suites, then the repository’s broader test/lint/type-check commands.
   - Exercise the migration against a representative pre-change profile dataset if migration tooling permits it.
   - Document the new request/response field and migration/release note in the repository’s established location.

## Acceptance criteria

- A user can set, read, and (where approved) clear their nickname through the existing settings/profile API.
- The nickname is stored in the user profile table and survives subsequent reads.
- Existing users, settings fields, and clients that omit the field remain compatible.
- Validation and authorization match existing profile settings behavior.
- Automated tests cover persistence, API contract, backward compatibility, clearing, invalid input, and cross-user protection.
- Migration and the full relevant verification suite complete successfully.

## Implementation notes / risks

- Use the existing profile table and API rather than introducing a parallel endpoint or table.
- Preserve null/default semantics consistently across database, domain, serialization, and API layers.
- Check generated schema/type artifacts into the repository only if that is already the project convention.
- Do not deploy the schema change separately from code that can tolerate both pre- and post-migration states unless the repository’s rollout process requires a staged migration.
