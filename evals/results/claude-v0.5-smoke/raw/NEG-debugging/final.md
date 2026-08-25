Investigation complete. Here is what I found.

## The failing test

`usesH2InMemoryDatabaseByDefault` in `/Users/p042890/workspace/polaris/backend/src/test/java/com/polaris/common/config/LocalDataSourceTests.java` (line 20) — the only test in the repo whose outcome depends on the ambient environment rather than on repo-controlled inputs. Every other backend test is a pure unit test (fixed inputs, mocks, ArchUnit rules) or uses `@DataJpaTest`/`@WebMvcTest` with isolated replacement databases; the frontend has no tests at all.

## Root cause: the assertion depends on environment variables the test never pins

The test is a plain `@SpringBootTest` that asserts:

```java
assertThat(connection.getMetaData().getURL()).startsWith("jdbc:h2:mem:polaris");
```

But which datasource the context gets is decided entirely by the runtime environment:

1. `/Users/p042890/workspace/polaris/backend/src/main/resources/application.properties:3` — `spring.profiles.active=${SPRING_PROFILES_ACTIVE:local}`. The active profile is read from an **environment variable**, defaulting to `local`.
2. `local` profile → `application-local.properties` → `jdbc:h2:mem:polaris;DB_CLOSE_DELAY=-1;MODE=PostgreSQL` → test passes.
3. If `SPRING_PROFILES_ACTIVE=supabase` (or anything non-local) is present in the environment, the context loads `application-supabase.properties`, where `spring.datasource.url=${SPRING_DATASOURCE_URL}`. Then either:
   - the URL is a Postgres URL → the `startsWith("jdbc:h2:mem:polaris")` assertion fails; or
   - `SPRING_DATASOURCE_URL` is unset → placeholder resolution fails, the whole context fails to load — which also takes down `PolarisBackendApplicationTests.contextLoads`, since both classes share the same cached `@SpringBootTest` context; or
   - the URL points at a real Supabase instance → the test result additionally depends on network reachability (Hikari `connection-timeout=10000`), adding a genuine timing/flakiness component.

Nothing pins the profile for tests: there is no `@ActiveProfiles`, no `src/test/resources/` at all (no test-scoped `application.properties`), and the `.env` injection in `backend/build.gradle` is wired only into `bootRun`, not the `test` task.

## Why "only in CI" and "intermittent"

- **Only in CI**: developers run `./gradlew test` locally with a clean shell — `SPRING_PROFILES_ACTIVE`/`SPRING_DATASOURCE_URL` are never exported (they live in the gitignored `backend/.env`, used only by `bootRun`). CI is where deployment env vars/secrets get injected into the job environment (the repo has no committed CI config — no `.github/workflows`, only `Dockerfile.vercel` — so the pipeline environment is defined outside the repo).
- **Intermittent**: whether those vars are present depends on *which* pipeline/job/runner executes the tests — e.g., deploy-branch runs with secrets injected fail, PR runs without secrets pass; matrix jobs or runner pools with different env baselines flip results run-to-run. When the var points at real Supabase, network latency vs. the 10s connection timeout adds run-to-run variance on top.

The test's name ("...ByDefault") is misleading: it doesn't verify a repo-controlled default, it verifies whatever the ambient environment selected.

## Fix options (any one suffices)

- Pin the profile on the test: `@SpringBootTest(properties = "spring.profiles.active=local")` or `@ActiveProfiles("local")` on both `LocalDataSourceTests` and `PolarisBackendApplicationTests`.
- Add `backend/src/test/resources/application.properties` fixing the H2 datasource for all tests.
- Scrub the env in Gradle: `tasks.named('test') { environment 'SPRING_PROFILES_ACTIVE', 'local' }` in `/Users/p042890/workspace/polaris/backend/build.gradle`.

Ruled out: test-order dependence (the shared named H2 DB `polaris` is touched by only one cached context; `@DataJpaTest` replaces the datasource with a uniquely-named embedded DB), parallel execution (no `maxParallelForks`/JUnit parallelism configured), time/randomness in assertions (none found), and port conflicts (`@SpringBootTest` uses MOCK web environment, no port binding).
