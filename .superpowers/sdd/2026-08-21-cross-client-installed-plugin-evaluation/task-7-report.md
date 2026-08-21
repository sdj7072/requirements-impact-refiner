# Task 7 Report: Deterministic CI and Pre-live Documentation

## Scope delivered

- CI runs the full standard-library suite and compiles `evals/harness/`; it has
  no `codex exec` invocation or Claude installer command.
- The runbook and contribution guidance distinguish fake-client CI from
  approval-gated live evaluation, define the 85-final Codex-with-Superpowers
  plan, retain all raw outcomes and attempts, and prohibit selective reruns of
  valid model results.
- English, Korean, and Japanese READMEs share a structured pre-live contract:
  `gpt-5.6-sol` is the user's run-local evaluation model, not a skill-selected
  default; Claude is structural-only and remains blocked without paid
  authentication.
- Compatibility-table identity and status rows remain unchanged: Codex with
  Superpowers is `not verified`; Claude behavior is `blocked`.

## TDD and verification evidence

1. Added structured documentation and CI tests before the documentation/CI
   changes. The focused RED run failed as expected because the contract table,
   runbook commands, and harness compilation command were absent.
2. `python3 -m unittest tests.test_documentation tests.test_packaging -v` —
   passed: 20 tests.
3. `python3 -m unittest discover -s tests -v` — passed: 188 tests.
4. `PYTHONPYCACHEPREFIX=/tmp/task7-eval-harness-pycache python3 -m compileall -q evals/harness` — passed. The equivalent unprefixed local command was blocked only by the sandbox's unwritable macOS bytecode-cache path.
5. `git diff --check` — passed.

## Review notes

- Documentation assertions parse compatibility rows, the structured contract,
  and runnable controller arguments. They do not add arbitrary prose-token
  grep tests.
- No live clients, raw-result changes, adapter/scorer/controller changes, or
  external reviewers were used.
