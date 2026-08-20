# Profile Nickname Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an editable nickname setting that is persisted with the user profile, shown in the profile table, exposed through the profile API, and covered by focused regression tests.

**Architecture:** Treat `nickname` as a profile-owned field. The settings form submits it through the existing profile update path; the profile repository/model persists it; profile reads and the profile table use the same response field so there is one source of truth. Validation is applied at the API boundary and the UI displays the server-confirmed value after save.

**Tech Stack:** Existing application UI/settings components, existing profile model/repository and HTTP API conventions, and the repository's current unit/integration test runner.

**Spec:** Approved requirements and impact review for Task 4 (nickname in settings, profile table, API, and tests), supplied with this task.

## Global Constraints

- Keep the field name exactly `nickname` across form state, API payloads/responses, persistence, and table columns.
- Preserve existing profile fields and update behavior; nickname changes must be partial-update safe.
- Enforce the approved nickname validation/length rules at the server boundary and return the existing API error shape.
- Do not expose unrelated account or profile fields through the new API response.
- Cover both successful persistence and invalid-input behavior with automated tests.

---

### Task 1: Add the profile data contract and persistence field

**Files:**
- Modify: `src/profile/profile.types.ts` (or the existing canonical profile type module)
- Modify: `src/profile/profile.repository.ts` (or the existing profile persistence adapter)
- Modify: `src/profile/profile.schema.ts` (or the existing profile/database schema definition)
- Test: `tests/profile/profile.repository.test.ts`

**Interfaces:**
- Consumes: Existing profile record and repository read/write methods.
- Produces: A profile shape containing `nickname: string | null`; repository methods preserve `nickname` on reads and partial updates without overwriting unspecified fields.

- [ ] **Step 1: Write the failing persistence tests**

```ts
it('returns nickname with the profile record', async () => {
  await profiles.insert({ userId: 'u-1', nickname: 'Mina' });
  await expect(profiles.findByUserId('u-1')).resolves.toMatchObject({ nickname: 'Mina' });
});

it('updates nickname without clearing other profile fields', async () => {
  await profiles.insert({ userId: 'u-1', displayName: 'Minji', nickname: null });
  await profiles.updateByUserId('u-1', { nickname: 'Mina' });
  await expect(profiles.findByUserId('u-1')).resolves.toMatchObject({ displayName: 'Minji', nickname: 'Mina' });
});
```

- [ ] **Step 2: Run the focused repository tests to verify they fail**

Run: `npm test -- --runInBand tests/profile/profile.repository.test.ts`

Expected: FAIL because the profile schema/type and repository mapping do not yet provide `nickname`.

- [ ] **Step 3: Add `nickname` to the canonical profile schema/type and mapping**

Add a nullable string field to the profile record, map it in both directions in the repository adapter, and include it in the partial-update patch object. Keep omitted patch properties omitted so an update such as `{ nickname: 'Mina' }` does not reset `displayName`, avatar, or other existing fields.

- [ ] **Step 4: Run the focused repository tests to verify they pass**

Run: `npm test -- --runInBand tests/profile/profile.repository.test.ts`

Expected: PASS, including both read and partial-update cases.

- [ ] **Step 5: Commit the persistence contract**

```bash
git add src/profile/profile.types.ts src/profile/profile.repository.ts src/profile/profile.schema.ts tests/profile/profile.repository.test.ts
git commit -m "feat: persist profile nickname"
```

### Task 2: Expose nickname through the profile API

**Files:**
- Modify: `src/api/profile.ts` (the existing profile GET/PATCH route/controller)
- Modify: `src/api/profile.validation.ts` (the existing request validation module)
- Test: `tests/api/profile.test.ts`

**Interfaces:**
- Consumes: Repository contract from Task 1 and the existing authenticated-user/profile route.
- Produces: `GET /api/profile` responses containing `nickname`; `PATCH /api/profile` accepts `{ nickname }`, validates it, persists it, and returns the updated profile using the existing response envelope/error format.

- [ ] **Step 1: Write failing API contract tests**

```ts
it('includes nickname in GET /api/profile', async () => {
  await seedProfile({ userId: 'u-1', nickname: 'Mina' });
  const response = await request(app).get('/api/profile').set('x-test-user', 'u-1');
  expect(response.status).toBe(200);
  expect(response.body.data.nickname).toBe('Mina');
});

it('updates nickname through PATCH /api/profile', async () => {
  const response = await request(app)
    .patch('/api/profile')
    .set('x-test-user', 'u-1')
    .send({ nickname: 'Mina' });
  expect(response.status).toBe(200);
  expect(response.body.data.nickname).toBe('Mina');
});

it('rejects a nickname that violates the approved validation rules', async () => {
  const response = await request(app)
    .patch('/api/profile')
    .set('x-test-user', 'u-1')
    .send({ nickname: 'x'.repeat(101) });
  expect(response.status).toBe(400);
  expect(response.body.error.code).toBe('VALIDATION_ERROR');
});
```

- [ ] **Step 2: Run the focused API tests to verify they fail**

Run: `npm test -- --runInBand tests/api/profile.test.ts`

Expected: FAIL because the response serializer omits nickname and the PATCH validator/controller does not accept it.

- [ ] **Step 3: Extend the API validator, update handler, and response serializer**

Allow an explicitly supplied `nickname` according to the approved constraints, distinguish omitted from `null` if null-clearing is supported by the existing profile contract, pass only validated fields to the repository update method, and serialize `nickname` on GET and successful PATCH responses. Reuse the established authentication, status codes, envelope, and validation error code.

- [ ] **Step 4: Run the focused API tests to verify they pass**

Run: `npm test -- --runInBand tests/api/profile.test.ts`

Expected: PASS for GET, PATCH, and invalid input, with no regression to existing profile fields.

- [ ] **Step 5: Commit the API contract**

```bash
git add src/api/profile.ts src/api/profile.validation.ts tests/api/profile.test.ts
git commit -m "feat: expose nickname in profile API"
```

### Task 3: Add nickname to settings and the profile table

**Files:**
- Modify: `src/settings/ProfileSettings.tsx` (the existing profile settings form)
- Modify: `src/profile/ProfileTable.tsx` (the existing profile table)
- Test: `tests/settings/ProfileSettings.test.tsx`
- Test: `tests/profile/ProfileTable.test.tsx`

**Interfaces:**
- Consumes: API contract from Task 2 and the existing profile query/update hooks.
- Produces: A controlled nickname input that loads the server value, submits it through the profile update mutation, shows the confirmed value after save, and a profile-table column rendering the same `nickname` value with the established empty-value presentation.

- [ ] **Step 1: Write failing UI tests**

```tsx
it('loads and saves nickname from settings', async () => {
  render(<ProfileSettings profile={{ nickname: 'Mina' }} />);
  expect(screen.getByLabelText('Nickname')).toHaveValue('Mina');
  await userEvent.clear(screen.getByLabelText('Nickname'));
  await userEvent.type(screen.getByLabelText('Nickname'), 'Nana');
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(updateProfile).toHaveBeenCalledWith({ nickname: 'Nana' });
});

it('renders nickname in the profile table', () => {
  render(<ProfileTable rows={[{ id: 'u-1', nickname: 'Mina' }]} />);
  expect(screen.getByRole('cell', { name: 'Mina' })).toBeVisible();
});
```

- [ ] **Step 2: Run the focused UI tests to verify they fail**

Run: `npm test -- --runInBand tests/settings/ProfileSettings.test.tsx tests/profile/ProfileTable.test.tsx`

Expected: FAIL because the settings form and table do not render or submit nickname.

- [ ] **Step 3: Implement the settings field and table column**

Initialize the controlled input from the profile query, keep edits local until Save, submit `{ nickname }` via the existing mutation, preserve the form's loading/error/success behavior, and render a `Nickname` table header/cell using the shared profile value. Use the existing placeholder for null/empty values and add the same accessible label/order conventions as neighboring profile fields.

- [ ] **Step 4: Run the focused UI tests to verify they pass**

Run: `npm test -- --runInBand tests/settings/ProfileSettings.test.tsx tests/profile/ProfileTable.test.tsx`

Expected: PASS, including initial value, update payload, and table rendering.

- [ ] **Step 5: Commit the UI integration**

```bash
git add src/settings/ProfileSettings.tsx src/profile/ProfileTable.tsx tests/settings/ProfileSettings.test.tsx tests/profile/ProfileTable.test.tsx
git commit -m "feat: add nickname profile controls"
```

### Task 4: Run the complete regression suite and verify the end-to-end contract

**Files:**
- Test: `tests/profile/nickname.integration.test.ts`

**Interfaces:**
- Consumes: Persistence, API, and UI changes from Tasks 1–3.
- Produces: An end-to-end regression test proving the entered nickname survives the settings-to-API-to-profile-table flow.

- [ ] **Step 1: Write the end-to-end regression test**

```ts
it('persists a nickname entered in settings and displays it in the profile table', async () => {
  await openProfileSettingsAs('u-1');
  await userEvent.type(screen.getByLabelText('Nickname'), 'Mina');
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Saved'));
  await openProfileTableAs('u-1');
  expect(await screen.findByRole('cell', { name: 'Mina' })).toBeVisible();
});
```

- [ ] **Step 2: Run the end-to-end test to verify it fails before wiring is complete**

Run: `npm test -- --runInBand tests/profile/nickname.integration.test.ts`

Expected: FAIL if any settings, API, persistence, or table boundary is not connected; use the failure boundary to correct the missing wiring.

- [ ] **Step 3: Run the end-to-end test after all implementation tasks**

Run: `npm test -- --runInBand tests/profile/nickname.integration.test.ts`

Expected: PASS, with the saved nickname visible after navigating to the profile table.

- [ ] **Step 4: Run the full project test suite**

Run: `npm test -- --runInBand`

Expected: PASS with no regressions in existing settings, profile, authentication, or API tests.

- [ ] **Step 5: Commit the regression coverage**

```bash
git add tests/profile/nickname.integration.test.ts
git commit -m "test: cover nickname profile flow"
```

## Self-Review Checklist

- Settings field, profile persistence, API read/update, table display, valid input, invalid input, null/empty rendering, and end-to-end persistence each have an explicit task and test.
- Every use of `nickname` has the same field name and nullable string semantics.
- Existing partial-update behavior, authentication, response envelopes, and validation error shape remain unchanged.
- No step depends on an undefined helper or an unassigned implementation decision; each test names the expected route, payload, status, and assertion.
