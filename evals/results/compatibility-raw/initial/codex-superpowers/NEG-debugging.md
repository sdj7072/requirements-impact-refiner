# CI-only intermittent test failure: debugging handoff

## Scope and routing

The request is to find why a test intermittently fails, with the supplied fact
that the failure occurs only in CI. Following Superpowers routing, this is a
debugging investigation, so the systematic-debugging workflow owns the work.
The requirements-impact-refiner skill does not activate: there is no concrete
proposed software change to refine. Do not rewrite the requirement or create
`REQ-###`, `INV-###`, `IMP-###`, `DEC-###`, or `AC-###` artifacts.

## Evidence currently available

- The test failure is intermittent.
- The failure occurs only in CI.
- No test name, assertion, stack trace, job/matrix entry, runner image,
  dependency/runtime versions, parallelism settings, seed, or CI log was
  supplied.

The evidence establishes a CI-specific failure boundary, but it does not
identify the failing component or root cause. A diagnosis such as a race,
ordering dependency, timing assumption, or environment mismatch would be only
a hypothesis until the failure is observed and traced.

## Debugging workflow

1. Capture the complete failing CI record: test name, assertion and stack
   trace, job/matrix entry, retry number, timestamps, and preceding warnings.
2. Compare failing and passing executions for runner image, OS, runtime and
   dependency versions, timezone/locale, environment variables, filesystem or
   service state, database fixtures, and test-runner flags.
3. Add diagnostic observability at component boundaries (without exposing
   secrets): effective configuration, seed, worker/index, temp and cache paths,
   setup/teardown results, and relevant state entering and leaving the test.
   Persist those diagnostics as failure artifacts.
4. Reproduce in the CI-equivalent container or runner. Repeat the single test
   with a fixed seed, then vary one factor at a time: worker count and order,
   retries, clock/timezone, network, and clean versus warm caches.
5. Check recent changes to the test, fixtures, shared mutable state, cleanup,
   dependency lockfile, CI image, and workflow configuration. Compare the
   resolved dependency and environment information from the failing job.
6. State one evidence-backed hypothesis and test it with the smallest
   diagnostic change. Do not add retries or timing workarounds before the
   failing boundary and cause are demonstrated.

## Current hypothesis status

No root cause is established. CI scheduling/state or an environment mismatch
may expose a race, ordering dependency, or timing assumption, but none can be
selected from the supplied fact alone. The next required input is the complete
CI failure log together with the job configuration, matrix entry, test command,
and resolved runtime/dependency versions.

## Exit condition

After reproducing the failing boundary, record the confirmed cause, add a
deterministic regression test or diagnostic reproduction, apply one root-cause
fix, and run CI-equivalent verification. Until then, this remains a debugging
investigation and produces no requirements-impact report.
