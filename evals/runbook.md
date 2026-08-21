# Requirements Impact Refiner Evaluation Runbook

## Deterministic CI versus live evaluation

CI runs the standard-library suite and compiles the evaluation harness with fake
executables only. It never invokes a live Codex model, replaces a plugin, or
installs Claude Code. Live evaluation is a separately approved release activity.

## Pre-live contract

The following machine-readable contract is repeated in every README. It records
the approved plan; it is not behavioral evidence and must not promote a
compatibility status before a sealed batch exists.

| Contract key | Requirement |
| --- | --- |
| planned-live-composition | Codex with Superpowers |
| planned-live-finals | 85 |
| run-local-model | gpt-5.6-sol |
| model-selection-owner | user |
| skill-model-selection | none |
| claude-evaluation | structural-only |
| claude-paid-auth | blocked: paid authentication unavailable |
| raw-evidence | all outcomes and attempts |
| approval-gates | plugin replacement; Claude installation; full batch |
| rerun-policy | no selective rerun of a valid model result |

The skill does not choose a model. `gpt-5.6-sol` with `high` reasoning is the
user-selected evaluation model for this planned batch only; model and reasoning
remain run-local inputs. Claude checks are structural and unauthenticated. A
command requiring paid authentication or model behavior is recorded as blocked,
not as behavioral compatibility.

## Evidence, scoring, and statuses

1. Use a fresh agent context for every repetition and supply only the case request and `repository_evidence`, never the rubric.
2. Record every prompt, command result, stream, final output, metadata, probe, and retained infrastructure attempt as raw evidence. Seal the complete raw tree with its manifest before adjudication or public-report editing.
3. Score `must_detect` only when output connects it to evidence or marks it inferred/unknown. Score `must_not_do` when output performs the forbidden neighboring workflow. A `partial`, `blocked`, `infra_error`, or `invalid_evidence` result never counts as a pass.
4. Treat unavailable repository access, fresh-context execution, or paid authentication as a disclosed `blocked` result. Require every negative case to avoid activation and every integration case to preserve one-orchestrator ownership.
5. The 17 applicable Codex-with-Superpowers cases run five times each: 85 final runs. This does not establish behavior for Codex standalone, generic clients, or Claude model behavior.

## Approval gates and execution sequence

Obtain fresh explicit approval before replacing the Codex plugin, installing
Claude Code, and starting the full 85-run batch. Retain Superpowers throughout;
do not remove or reconfigure it to create a different composition. Review the
probe and smoke evidence before requesting the full-batch approval.

Run these commands only after the applicable approval gate. They are documented
as parseable controller invocations, not CI steps:

```sh
python3 -m evals.harness.run --client codex --probe-only --output evals/results/installed-v0.3
```

```sh
python3 -m evals.harness.run --client codex --suite smoke --repetitions 1 --model gpt-5.6-sol --reasoning high --output evals/results/installed-v0.3
```

```sh
python3 -m evals.harness.run --client codex --suite installed-superpowers --repetitions 5 --model gpt-5.6-sol --reasoning high --output evals/results/installed-v0.3
```

Never selectively rerun a valid model result or discard an unfavorable valid
transcript. Retry only a classified infrastructure failure, retain its original
attempt and retry link, and start a new named batch if skill wording changes.
