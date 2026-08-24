# Contributing

Thank you for improving Requirements Impact Refiner. English documentation and the canonical instructions under `skills/requirements-impact-refiner/` define behavior; packaging metadata must point to that single skill rather than fork it.

## Setup and tests

Python 3.11+ is recommended. Runtime and repository tests use only the Python standard library.

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_documentation -v
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py path/to/report.md
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py --previous previous.md current.md
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py --previous previous.md --print-expected-delta current.md
python3 -m py_compile skills/requirements-impact-refiner/scripts/impact_report.py skills/requirements-impact-refiner/scripts/validate-impact-report.py
```

For optional platform validation, use:

```sh
python3 /path/to/skill-creator/scripts/quick_validate.py skills/requirements-impact-refiner
python3 /path/to/plugin-creator/scripts/validate_plugin.py .
claude plugin validate .
```

Record an unavailable dependency or CLI as `blocked`; do not report a validator pass you did not observe. In the original release environment the Python platform validators were blocked by missing PyYAML, and the Claude validator was blocked because `claude` was unavailable.

## Installed-plugin evaluation boundary

Ordinary CI runs deterministic harness tests with fake executables and compiles
the harness. It does not run a live Codex model, replace a plugin, install
Claude Code, authenticate, or purchase access. Those are separate live-release
operations that require fresh approval before Codex plugin replacement, Claude
installation, and the full 85-final Codex-with-Superpowers batch.

For that planned batch, `gpt-5.6-sol` with `high` reasoning is a user-selected,
run-local evaluation configuration. The production skill does not select a
model or reasoning level. Claude validation is structural-only; any paid-auth
or model-behavior boundary is recorded as `blocked: paid authentication
unavailable`, not as behavioral compatibility.

Preserve all raw outcomes and attempts, including failures and blocked results,
then seal the raw tree and manifest before adjudication or compatibility edits.
Keep Superpowers enabled, make no same-batch skill changes, and never
selectively rerun a valid model result. Only classified infrastructure failures
may be retried, with the original attempt and retry relationship retained. See
[the evaluation runbook](evals/runbook.md) for the approved command sequence.

## Behavioral changes require RED first

Before changing skill instructions, references, templates, or wording intended to alter behavior:

1. Add or identify a stable case in `evals/cases.json` or `evals/v0.3-cases.json`.
2. Capture the failing behavior before the instruction change. Keep this RED baseline and its exact environment metadata.
3. For wording changes, run the no-guidance control five times in fresh contexts before loading the candidate skill. Do not replace the control with a single favorable sample.
4. Make the smallest instruction change that addresses the observed failure.
5. Run the same case five times with the candidate guidance, preserve raw outputs, score against `must_detect` and `must_not_do`, and disclose stochastic failures.
6. Re-run the full standard-library suite and relevant report/platform validators.

Lineage changes must exercise `tests.test_report_lineage` and preserve `RPT-###`, `IMP-###`, exact predecessor bytes, Revision sequencing, and calculated Delta behavior. Keep RED and GREEN behavioral outputs with client/model identity, repetition count, and deviations. Raw evidence is immutable: store it only in designated raw directories, preserve it with `.gitattributes` (`-text -whitespace`), inventory every file, and verify checksums rather than reformatting it.

Never rewrite an evaluation result to imply 25/25 when the preserved evidence is 24/25. Keep core and integration corpora distinct.

## Pull request checklist

- [ ] I added a genuine RED test or evaluation before production/instruction changes.
- [ ] Focused tests and `python3 -m unittest discover -s tests -v` pass.
- [ ] Relevant completed reports pass `validate-impact-report.py`.
- [ ] Revised reports pass `validate-impact-report.py --previous PREVIOUS.md CURRENT.md`, and the printed expected Delta matches the authored Delta.
- [ ] Platform-validator results are recorded as observed: passed, `blocked`, or `not tested`.
- [ ] New compatibility statements name an actually tested client/version/environment and do not generalize behavioral harness results into loader/runtime support.
- [ ] `README.md`, `README.ko.md`, and `README.ja.md` changed together for semantic documentation changes, or the PR explicitly records which translation is pending and why.
- [ ] Commands, paths, `REQ/INV/IMP/DEC/AC` IDs, evidence levels, and impact states remain identical across translations.
- [ ] `git diff --check` passes, excluding only intentionally byte-preserved evidence already covered by checksums.

## Translation synchronization

`README.md` is the semantic authority. Korean and Japanese should be natural developer documentation, not partial summaries. Preserve commands, paths, identifiers, state names, and evidence-level values in English. A pending translation is an explicit temporary exception, not permission to silently let versions drift.

## Related work and attribution

Related-work sections may describe Superpowers, Claude Code `feature-dev`, GitHub Spec Kit, BMAD, GSD, or other workflows. Link to the relevant upstream project and state the integration boundary. Do not claim dependency, endorsement, bundled execution, or code reuse unless the repository contains verifiable evidence and the applicable license/attribution requirements have been satisfied.

## Scope

Keep the project focused on repository-backed pre-planning impact discovery, traceability, user decisions, and whole-set recalculation. Since v0.4 the scope includes the narrow local MCP server that controls impact-report creation, the bounded built-in lexical scanner, and detect-only external provider adapters. Proposals for broad ideation, implementation planning, coding, debugging, code review, a full code-graph engine (AST parsing, import resolution, symbol tables), or automatic provider installation remain out of scope.
