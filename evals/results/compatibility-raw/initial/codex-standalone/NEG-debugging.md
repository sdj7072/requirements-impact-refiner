# CI-only intermittent test failure: debugging handoff

## Scope and trigger decision

The request is to find why a test intermittently fails, with the supplied fact
that the failure occurs only in CI. This is a debugging task, not a concrete
proposed software change requiring compatibility-impact refinement. The
requirements-impact-refiner skill therefore does not activate. No requirement
rewrite or impact-refinement artifacts are appropriate here.

## Evidence currently available

- The failure is intermittent.
- It occurs in CI but has not been observed locally.
- No failing test name, assertion, stack trace, runner, operating system,
  dependency versions, parallelism, or CI logs were supplied.

These facts establish an environment-dependent failure boundary, but they do
not identify the root cause. Any specific diagnosis at this point would be a
guess.

## Proper neighboring debugging workflow

1. Capture the complete CI failure: test name, assertion, stack trace, job
   matrix entry, retry number, timestamps, and relevant preceding warnings.
2. Compare the failing CI job with a passing local run and with passing/failing
   matrix entries: runtime and dependency versions, OS/container image,
   timezone/locale, environment variables, filesystem/network services,
   database state, and test-runner flags.
3. Make the CI execution observable at boundaries: log the effective
   configuration (excluding secrets), test seed, worker index, temp/cache
   paths, and setup/teardown results. Persist artifacts on failure.
4. Reproduce the CI conditions locally or in the same container. Run the
   single test repeatedly with a fixed seed, then vary one factor at a time:
   parallel workers, ordering, retries, clock/timezone, network, and clean
   versus warm caches.
5. Check recent changes to the test, fixtures, shared mutable state, cleanup,
   dependency lockfile, CI image, and workflow configuration. Compare the
   failing job's resolved lockfile and environment to the repository state.
6. Form one evidence-backed hypothesis and test it with the smallest
   diagnostic change. Do not apply a retry or timing workaround before the
   failing boundary and cause are demonstrated.

## Current hypothesis status

The only justified hypothesis is that CI-specific state or scheduling exposes
an unobserved race, ordering dependency, timing assumption, or environment
mismatch. It is not yet confirmed. The next required input is the full CI
failure log plus the job's matrix/configuration and test command.

## Exit condition

Once the failing boundary is reproduced, record the confirmed root cause,
add a deterministic regression test or diagnostic reproduction, and then make
one root-cause fix followed by a clean CI-equivalent verification. Until that
evidence exists, this remains a debugging investigation rather than a
requirements-impact report.
