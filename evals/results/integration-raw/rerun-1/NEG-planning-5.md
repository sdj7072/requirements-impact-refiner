# Nickname in Settings, Profile Table, and API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional user nickname that can be edited in Settings, displayed in the profile table, and exposed consistently through the profile API without changing authentication identity or unrelated profile fields.

**Architecture:** Persist `nickname` as a nullable profile attribute and make the profile read/write path the single source of truth. The Settings form sends a trimmed nickname through the existing profile update API; profile-table rendering consumes the API response and falls back to the existing identity label when no nickname exists. Validation and authorization remain server-side, with client tests covering the happy path and explicit negative cases.

**Tech Stack:** Existing application UI/settings form, existing profile persistence layer, existing HTTP/API validation conventions, and the repository’s current unit/integration test runner.

**Spec:** Approved requirements and impact review for Task 4 (nickname in Settings, profile table, and API), supplied by the parent task.

## Global Constraints

- `nickname` is optional; omitted or blank input is represented as no nickname, not as a fabricated default.
- Preserve the existing account/user identifier and current display behavior when `nickname` is absent.
- Only the authenticated owner may update their nickname; requests must not permit changing another user’s profile.
- Apply the project’s existing length, character, normalization, and error-envelope conventions; do not introduce a second validation policy.
- API responses and profile-table data must use one consistent property name: `nickname`.
- Do not modify unrelated profile attributes, authentication claims, permissions, or settings.

---

### Task 1: Add the profile nickname data contract and persistence mapping

**Files:**
- Modify: `src/profile/profile-schema.ts` (the canonical profile model/schema identified in the impact review)
- Modify: `src/profile/profile-repository.ts` (the existing profile read/write repository)
- Create: `tests/profile/profile-nickname-persistence.test.ts`

**Interfaces:**
- Consumes: Existing profile record and repository methods.
- Produces: `Profile.nickname: string | null`; repository read methods return it, and the owner-scoped update method accepts `{ nickname: string | null }` while preserving all other fields.

- [ ] **Step 1: Write the failing persistence tests**

```ts
it('reads and writes nickname without changing the profile id or other fields', async () => {
  const before = await profiles.getByUserId(userId);
  const updated = await profiles.updateNickname(userId, 'Mina');
  expect(updated).toMatchObject({ id: before.id, userId, nickname: 'Mina' });
  expect(updated.email).toBe(before.email);
});

it('stores an absent nickname as null', async () => {
  await profiles.updateNickname(userId, null);
  expect((await profiles.getByUserId(userId)).nickname).toBeNull();
});
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run the repository’s focused profile test command against `tests/profile/profile-nickname-persistence.test.ts`.

Expected: FAIL because the profile contract/repository has no `nickname` field or owner-scoped update method.

- [ ] **Step 3: Implement the minimal schema and repository change**

Add nullable `nickname` to the canonical profile type and persistence mapping. Implement `updateNickname(userId, nickname)` using the existing parameterized update/query mechanism and owner key; return the updated profile through the same mapper used by reads. Do not overwrite the whole record from client input.

- [ ] **Step 4: Run the focused test to verify it passes**

Run the same focused profile test command.

Expected: PASS, including preservation of existing profile fields and null storage.

- [ ] **Step 5: Commit**

```bash
git add src/profile/profile-schema.ts src/profile/profile-repository.ts tests/profile/profile-nickname-persistence.test.ts
git commit -m "feat: persist optional profile nickname"
```

### Task 2: Expose nickname through the authenticated profile API

**Files:**
- Modify: `src/api/profile.ts` (existing profile GET/PATCH handlers)
- Modify: `src/api/profile-validation.ts` (existing request validation module)
- Create: `tests/api/profile-nickname.test.ts`

**Interfaces:**
- Consumes: Task 1’s `Profile.nickname` and `profiles.updateNickname(userId, nickname)`.
- Produces: `GET /api/profile` includes `nickname: string | null`; owner `PATCH /api/profile` accepts `{ nickname?: string | null }` and returns the updated profile; invalid and unauthorized requests use the existing API error envelope.

- [ ] **Step 1: Write failing API contract and negative tests**

```ts
it('returns nickname from the authenticated profile', async () => {
  await profiles.updateNickname(userId, 'Mina');
  const response = await request.get('/api/profile').set(auth(userId));
  expect(response.status).toBe(200);
  expect(response.body.nickname).toBe('Mina');
});

it('updates only the authenticated owner profile', async () => {
  const response = await request.patch('/api/profile').set(auth(userId)).send({ nickname: 'Mina' });
  expect(response.status).toBe(200);
  expect(response.body.nickname).toBe('Mina');
});

it.each(['   ', 'x'.repeat(MAX_NICKNAME_LENGTH + 1)])('rejects invalid nickname %p', async (nickname) => {
  const response = await request.patch('/api/profile').set(auth(userId)).send({ nickname });
  expect(response.status).toBe(400);
  expect(response.body.error.code).toBe('VALIDATION_ERROR');
});

it('rejects an unauthenticated update and cannot target another user', async () => {
  expect((await request.patch('/api/profile').send({ nickname: 'Mina' })).status).toBe(401);
  const response = await request.patch('/api/profile').set(auth(userId)).send({ userId: otherUserId, nickname: 'Mina' });
  expect(response.status).toBe(403);
});
```

- [ ] **Step 2: Run the focused API tests to verify they fail**

Run the repository’s API test command for `tests/api/profile-nickname.test.ts`.

Expected: FAIL because GET/PATCH do not expose or validate `nickname` yet.

- [ ] **Step 3: Implement the API contract**

Extend the existing response serializer with `nickname`. Extend the existing PATCH validator using the project’s established max length/character rules, trim once at the API boundary, convert blank to `null`, and reject caller-supplied identity fields rather than using them for lookup. Resolve the user exclusively from the authenticated session and call `updateNickname`.

- [ ] **Step 4: Run the focused API tests to verify they pass**

Run the same focused API test command.

Expected: PASS for read/update, null fallback, validation errors, unauthenticated access, and cross-user targeting.

- [ ] **Step 5: Commit**

```bash
git add src/api/profile.ts src/api/profile-validation.ts tests/api/profile-nickname.test.ts
git commit -m "feat: expose nickname in profile API"
```

### Task 3: Add nickname editing to Settings and display it in the profile table

**Files:**
- Modify: `src/settings/SettingsProfileForm.tsx` (existing Settings profile form)
- Modify: `src/profile/ProfileTable.tsx` (existing profile table)
- Create: `tests/ui/nickname-settings-profile-table.test.tsx`

**Interfaces:**
- Consumes: Task 2’s `GET /api/profile` and owner `PATCH /api/profile` contract.
- Produces: A labeled Settings nickname input with save/loading/error states and a profile-table nickname column/cell that displays the nickname or the existing identity fallback.

- [ ] **Step 1: Write failing UI tests**

```tsx
it('loads and saves the nickname from Settings', async () => {
  render(<SettingsProfileForm />);
  expect(await screen.findByLabelText('Nickname')).toHaveValue('Mina');
  await user.clear(screen.getByLabelText('Nickname'));
  await user.type(screen.getByLabelText('Nickname'), '  Jae  ');
  await user.click(screen.getByRole('button', { name: /save/i }));
  expect(mockPatch).toHaveBeenCalledWith('/api/profile', { nickname: 'Jae' });
});

it('falls back when nickname is null and does not show an empty table cell', async () => {
  render(<ProfileTable profile={{ nickname: null, displayName: 'Existing Name' }} />);
  expect(screen.getByRole('cell', { name: 'Existing Name' })).toBeInTheDocument();
});

it('shows the API validation error and preserves entered input', async () => {
  mockPatch.mockRejectedValueOnce(new Error('Nickname is invalid'));
  render(<SettingsProfileForm />);
  const input = await screen.findByLabelText('Nickname');
  await user.clear(input);
  await user.type(input, 'bad value');
  await user.click(screen.getByRole('button', { name: /save/i }));
  expect(await screen.findByText('Nickname is invalid')).toBeInTheDocument();
  expect(input).toHaveValue('bad value');
});
```

- [ ] **Step 2: Run the focused UI tests to verify they fail**

Run the repository’s component test command for `tests/ui/nickname-settings-profile-table.test.tsx`.

Expected: FAIL because Settings has no nickname control and the table has no nickname mapping/fallback.

- [ ] **Step 3: Implement the minimal UI behavior**

Hydrate the controlled input from profile data, trim before PATCH, disable submission while saving, render the existing error presentation on rejection, and retain user input after failure. Add the table field using `profile.nickname ?? profile.displayName` (or the established identity fallback), with accessible label/header text and no changes to sorting or unrelated columns.

- [ ] **Step 4: Run focused UI and regression tests**

Run the focused UI test, then the existing Settings/profile test suites.

Expected: PASS with no regressions in existing profile display or Settings saves.

- [ ] **Step 5: Commit**

```bash
git add src/settings/SettingsProfileForm.tsx src/profile/ProfileTable.tsx tests/ui/nickname-settings-profile-table.test.tsx
git commit -m "feat: edit and display profile nickname"
```

### Task 4: Verify the complete contract and negative boundaries

**Files:**
- Modify: existing API, persistence, Settings, and profile-table tests only where assertions need to cover the approved contract.
- Create: `tests/integration/profile-nickname-flow.test.ts`

- [ ] **Step 1: Write the end-to-end contract test**

```ts
it('round-trips nickname from Settings through API to profile table', async () => {
  await openSettingsFor(userId);
  await saveNickname('Nari');
  expect(await getProfile().then(profile => profile.nickname)).toBe('Nari');
  await openProfileTable();
  expect(await screen.findByRole('cell', { name: 'Nari' })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the complete focused flow and negative suite**

Run the project’s standard test command for the new integration test plus all existing profile/API/Settings tests.

Expected: PASS; verify absent, blank, over-length, unauthenticated, and cross-user cases remain rejected or correctly fall back.

- [ ] **Step 3: Run formatting, type-check, and build verification**

Run the repository’s formatter check, type checker, and production build using the project-standard commands.

Expected: all commands exit successfully with no generated artifacts committed.

- [ ] **Step 4: Commit verification updates**

```bash
git add tests
git commit -m "test: verify nickname profile flow and boundaries"
```

## Self-review checklist

- Schema, persistence, API serialization/update, Settings editing, profile-table fallback, and regression coverage are each assigned to a task.
- Every negative requirement has an executable assertion: blank/invalid input, unauthenticated update, cross-user targeting, null fallback, and update failure preserving input.
- The single property name `nickname` and the owner-scoped `updateNickname(userId, nickname)` signature are used consistently across tasks.
- No task changes authentication identity, unrelated profile fields, permissions, or other settings.
