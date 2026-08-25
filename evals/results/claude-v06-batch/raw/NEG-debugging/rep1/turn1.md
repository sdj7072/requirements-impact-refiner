Root cause identified and verified end-to-end. Here is the summary.

## The flaky test

`DemoFlowIntegrationTests.packageDetailIncludesResourceItemsAndLinkedPackages` (Order 11) in
`/Users/p042890/workspace/polaris/backend/src/test/java/com/polaris/api/DemoFlowIntegrationTests.java` (lines 156–175).

It asserts an exact **position** in a list whose order the backend never specifies:

```java
.andExpect(jsonPath("$.linkedPackages[0].id").value("SRC-001"))   // for DST-001
...
.andExpect(jsonPath("$.linkedPackages[0].id").value("DST-001"))   // for SRC-001
```

## Why it is order-nondeterministic

1. **The query has no ORDER BY.** `linkedPackages` flows from `PackageQueryService.linkedSources/linkedDestinations` → `AccessBindingPersistenceAdapter.findSourceIdsByDestination/findDestinationIdsBySource` (`/Users/p042890/workspace/polaris/backend/src/main/java/com/polaris/packagepolicy/adapter/out/persistence/AccessBindingPersistenceAdapter.java`, lines 31–52), which call the derived queries `findByDestinationPackageIdAndStatusIn` / `findBySourcePackageIdAndStatusIn` — no ordering clause at all. SQL row order without ORDER BY is unspecified; the test encodes whatever order the local engine happens to return.

2. **DST-001 has multiple candidate rows.** Seed (`backend/src/main/resources/data.sql`) gives DST-001 five live bindings (SRC-001/002/003/004/010), and there is no usable tiebreaker anyway — every seeded `created_at` in the whole file is the identical `2026-08-25 09:00:00+09`.

3. **A per-run random row is injected before the assertion runs.** Test 5 (Order 5) approves REQ-2026-0021; the synchronous `AutomaticProvisioningListener` → `ProvisioningService.applyCompletedSideEffects` → `AccessBindingPersistenceAdapter.bind(...)` inserts **new** `access_bindings` rows for the SRC-009×DST-001 / SRC-009×DST-002 pairs with `UUID.randomUUID()` primary keys (line 68). So by the time test 11 queries DST-001, the unordered result set contains a row whose key is different on every run — the classic recipe for a run-to-run coin flip instead of a stable wrong answer.

## Why only in CI

- Locally the suite runs the `local` profile: H2 in-memory (`jdbc:h2:mem:polaris`, `application-local.properties`), where this small unindexed query is a table scan returning **insertion order** — seeded SRC-001 row always first, new random-UUID rows appended last. I ran the class 13 times on this machine: 13/13 green, confirming local stability.
- In the CI/deployment environment the engine and plan differ: the Supabase/Postgres baseline schema (`supabase/migrations/20260825044114_polaris_baseline_schema.sql`, line 555) defines `idx_access_bindings_destination_status`, so the same query runs as an index scan whose duplicate-key ordering (and IN-list scan order across `PENDING/ACTIVE/SUSPENDED`) is not insertion order and is not guaranteed between runs. Whenever any row other than the seeded SRC-001 binding surfaces first — including the freshly inserted random-UUID SRC-009 row — `linkedPackages[0]` flips and the jsonPath assertion fails. Same data, same code, different (equally legal) row order.

## Fix direction

Either assert set membership instead of position (like test 12 already does with `hasItem`), or give the query a deterministic sort key (e.g., order linked packages by package code in `AccessBindingPersistenceAdapter`/repository). Note the same latent hazard exists in `PolicyRequestPersistenceAdapter.toDomain` (`bindings.get(0)` after `OrderByCreatedAtAsc` where all six of REQ-2026-0021's `request_bindings` share one timestamp and only one row carries the real `impact_summary` metadata) — ordering by a fully-tied column is no ordering at all, so the display metadata (currentAssignee, period, injectedFailure flags) can silently come from the wrong `'{}'` row under the same conditions.