# Nickname in Settings and Profile Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persisted nickname setting, expose it through the profile API, and render it consistently in settings and the profile table without regressing existing profile fields.

**Architecture:** Keep nickname in the existing profile/settings persistence model as an optional user-owned string. Extend the existing profile read/update API with the same field and validation rules, then have both settings and the profile table consume that API contract rather than maintaining separate nickname state. Cover the contract, persistence, and UI behavior with focused unit/component tests plus one end-to-end update/read assertion.

**Tech Stack:** Existing application language and framework, existing profile/settings persistence layer, existing HTTP/API test harness, and the repository’s current component-test and end-to-end test tooling.

**Spec:** Task4 handoff requirements and completed impact review supplied by the parent agent on 2026-08-20.

## Global Constraints

- Nickname is optional; an absent value is represented as `null` in API responses and as an empty input in settings.
- Trim surrounding whitespace before persistence; reject a non-empty nickname longer than 50 Unicode characters with the API’s established validation error shape.
- A user may read or update only their own profile/settings record; retain the existing authentication and authorization checks.
- Existing profile fields and response compatibility must remain unchanged.
- Do not introduce a second nickname source of truth or a new persistence table.

---

### Task 1: Extend the profile persistence model and migration

**Files:**
- Modify: `src/server/profile/profile-model.*` — add the nullable `nickname` field to the existing profile record and mapper.
- Modify: `src/server/profile/profile-repository.*` — include nickname in profile reads and updates using the existing user-id key.
- Create: `src/server/profile/migrations/20260820_add_profile_nickname.*` — add the nullable column with the project’s existing migration format and rollback convention.
- Test: `src/server/profile/profile-repository.test.*`

**Interfaces:**
- Consumes: existing authenticated user identifier and profile repository interface.
- Produces: `ProfileRecord.nickname: string | null` and repository methods that preserve `null`, trim input, and enforce the 50-character limit before writing.

- [ ] **Step 1: Write the failing repository tests**

  Add tests that create a profile, read `nickname === null`, update it with `"  Ada  "`, and read back `"Ada"`. Add a test that a 51-character value returns the repository’s validation error and does not change the stored value.

- [ ] **Step 2: Run the focused repository tests to verify failure**

  Run the repository’s focused test command for `src/server/profile/profile-repository.test.*`. Expected: failure because the schema/model does not yet expose `nickname`.

- [ ] **Step 3: Add the nullable column and model/repository mapping**

  Use the existing migration syntax to add `profile.nickname` as nullable, map it on select and update, trim before persistence, and apply the exact existing validation-error type for values over 50 Unicode characters. Preserve the repository’s current transaction and user-id scoping.

- [ ] **Step 4: Run the focused repository tests to verify the persistence behavior**

  Re-run the same command. Expected: all nickname and pre-existing profile repository tests pass.

- [ ] **Step 5: Commit the persistence slice**

  ```bash
  git add src/server/profile/profile-model.* src/server/profile/profile-repository.* src/server/profile/migrations/20260820_add_profile_nickname.* src/server/profile/profile-repository.test.*
  git commit -m "feat: persist profile nicknames"
  ```

### Task 2: Extend the profile read/update API

**Files:**
- Modify: `src/server/profile/profile-service.*` — validate and delegate nickname reads/updates while retaining authorization.
- Modify: `src/server/profile/profile-api.*` — add `nickname` to the GET response and PATCH/PUT request schema.
- Test: `src/server/profile/profile-api.test.*`

**Interfaces:**
- Consumes: `ProfileRecord.nickname` and the existing authenticated request context.
- Produces: `GET /api/profile` returning `{ ..., nickname: string | null }`; the existing profile update endpoint accepting `{ nickname: string | null }` and returning the updated profile in the established envelope.

- [ ] **Step 1: Write failing API contract tests**

  Assert that an authenticated GET includes `nickname: null`, an authenticated update with `{ nickname: "  Ada  " }` returns `nickname: "Ada"`, `null` clears the value, a 51-character value returns the established 4xx validation shape, unauthenticated requests are rejected, and another user’s profile cannot be read or updated.

- [ ] **Step 2: Run the focused API tests to verify failure**

  Run the repository’s focused test command for `src/server/profile/profile-api.test.*`. Expected: failures for the missing response/request field and update behavior.

- [ ] **Step 3: Implement the API contract**

  Extend the existing request/response types and serializers with `nickname`, pass it through the existing service/repository path, and keep the current authentication, authorization, status codes, and error envelope. Treat `null` as clear and an omitted field as “leave unchanged” when the endpoint already supports partial updates.

- [ ] **Step 4: Run the focused API tests to verify the contract**

  Re-run the same command. Expected: all nickname contract tests and existing profile API tests pass.

- [ ] **Step 5: Commit the API slice**

  ```bash
  git add src/server/profile/profile-service.* src/server/profile/profile-api.* src/server/profile/profile-api.test.*
  git commit -m "feat: expose nickname in profile API"
  ```

### Task 3: Add nickname editing to Settings

**Files:**
- Modify: `src/client/settings/SettingsPage.*` — render the nickname field, load it from the profile query, and submit it through the existing update mutation.
- Modify: `src/client/settings/settings-schema.*` — apply the same trim/empty-to-null and 50-character rules before submission.
- Test: `src/client/settings/SettingsPage.test.*`

**Interfaces:**
- Consumes: the profile API contract from Task 2.
- Produces: an accessible settings input labeled “Nickname”, initialized from the current nickname, with save/clear/error states matching existing settings controls.

- [ ] **Step 1: Write failing settings component tests**

  Render a profile with `nickname: "Ada"` and assert the input value, label, and update request. Test whitespace trimming, clearing to `null`, disabled/loading behavior during save, and the API validation error rendered beside the field.

- [ ] **Step 2: Run the focused settings tests to verify failure**

  Run the repository’s focused client test command for `src/client/settings/SettingsPage.test.*`. Expected: failures because the nickname control is absent.

- [ ] **Step 3: Implement the settings control**

  Add the labeled text input to the existing profile/settings form, bind it to the fetched profile value, normalize whitespace and empty values in the established form path, and invalidate/refetch the current profile query after a successful update. Preserve existing submit controls and keyboard/screen-reader semantics.

- [ ] **Step 4: Run the focused settings tests to verify the UI**

  Re-run the same command. Expected: all nickname settings tests and existing settings tests pass.

- [ ] **Step 5: Commit the settings slice**

  ```bash
  git add src/client/settings/SettingsPage.* src/client/settings/settings-schema.* src/client/settings/SettingsPage.test.*
  git commit -m "feat: allow nickname editing in settings"
  ```

### Task 4: Render nickname in the profile table

**Files:**
- Modify: `src/client/profile/ProfileTable.*` — add the nickname column/cell using the profile query data.
- Test: `src/client/profile/ProfileTable.test.*`

**Interfaces:**
- Consumes: profile rows containing `nickname: string | null` from the existing profile data loader.
- Produces: a stable “Nickname” table header and a readable fallback for `null`/empty values without changing existing columns or row actions.

- [ ] **Step 1: Write failing profile-table tests**

  Render rows with `nickname: "Ada"` and `nickname: null`; assert the “Nickname” header, the visible nickname, and the agreed existing empty-value fallback. Assert that current profile columns and actions remain present.

- [ ] **Step 2: Run the focused profile-table tests to verify failure**

  Run the repository’s focused client test command for `src/client/profile/ProfileTable.test.*`. Expected: failure because no nickname column is rendered.

- [ ] **Step 3: Implement the nickname column**

  Add the column in the profile table’s existing column-definition order, render the value from the row model, and use the same empty-state styling/label as neighboring optional profile fields.

- [ ] **Step 4: Run the focused profile-table tests to verify the table**

  Re-run the same command. Expected: nickname and existing table tests pass.

- [ ] **Step 5: Commit the table slice**

  ```bash
  git add src/client/profile/ProfileTable.* src/client/profile/ProfileTable.test.*
  git commit -m "feat: show nickname in profile table"
  ```

### Task 5: Verify the cross-layer flow and regression surface

**Files:**
- Modify: `tests/e2e/profile-settings.*` — add the end-to-end nickname flow to the existing authenticated profile/settings scenario.
- Test: `src/server/profile/profile-api.test.*`, `src/client/settings/SettingsPage.test.*`, `src/client/profile/ProfileTable.test.*`

**Interfaces:**
- Consumes: the completed persistence, API, settings, and table slices.
- Produces: evidence that a nickname saved in Settings is returned by the API and appears in the profile table, including clear and reload behavior.

- [ ] **Step 1: Add the end-to-end assertion**

  In the existing authenticated scenario, set nickname to `"Ada"`, save, reload profile data, assert the API response contains `"Ada"`, assert the table displays `"Ada"`, then clear it and assert the API returns `null` and the table shows the optional-field fallback.

- [ ] **Step 2: Run the complete relevant test set**

  Run the project’s standard server, client, and end-to-end test commands, including migration/schema checks. Expected: all relevant tests pass with no changed behavior for existing profile fields.

- [ ] **Step 3: Review the diff against the approved requirements**

  Confirm the final diff contains only the nullable nickname persistence change, API contract wiring, Settings control, profile-table rendering, and their tests; confirm no duplicate profile store or authorization bypass was introduced.

- [ ] **Step 4: Commit the verification slice**

  ```bash
  git add tests/e2e/profile-settings.*
  git commit -m "test: verify nickname profile flow"
  ```

## Self-Review Checklist

- Persistence, API, Settings, profile table, clear behavior, validation, authorization, and regression coverage each have an explicit task.
- Every task has a failing test, a focused command, a minimal implementation, a passing-test check, and a commit boundary.
- The API type is consistent across all tasks: `nickname: string | null`; partial updates distinguish omitted from explicit `null`.
- No placeholder instruction is required; implementers can use the named interfaces and concrete test cases directly.
