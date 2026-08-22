# Cross-Client Installed Plugin Evaluation Design

Date: 2026-08-21

## Purpose

Requirements Impact Refiner 0.3.0 has strong deterministic report validation, but its release evidence does not yet demonstrate reliable behavior through an actually installed plugin. The local Codex installation still exposes version 0.2.0, the broader Codex release audits remain `not verified`, and Claude Code behavior is unavailable without paid authentication.

This design adds a reusable, client-neutral evaluation harness. It will evaluate the installed 0.3.0 plugin through Codex, structurally validate the Claude Code package without paid model access, preserve every execution artifact, and update compatibility claims only from auditable evidence. It does not change skill behavior during the evaluation batch.

## Decisions

- Use one common evaluation contract with client adapters.
- Preserve every execution transcript and command result, not only failures.
- Run Codex behavior with the user-selected `gpt-5.6-sol` model and `high` reasoning for this batch in the actually installed Codex-with-Superpowers environment.
- Keep the skill and harness model-neutral. A model is a run parameter, never a skill requirement or default imposed by the plugin.
- Install the Claude Code native CLI, but do not purchase a plan, authenticate, or run model behavior.
- Treat unavailable Claude model behavior as `blocked`, never as a pass.
- Run live client evaluations explicitly, not in ordinary CI.
- Do not tune the skill within the same evaluation batch.
- Do not remove or reconfigure Superpowers to manufacture a standalone environment; bound live claims to the active installed-plugin composition.

## Architecture

The harness lives under `evals/harness/` and stays independent of the canonical skill implementation.

```text
case catalog
    -> evaluation controller
        -> Codex adapter -> installed-plugin behavior
        -> Claude adapter -> CLI/package structure
    -> raw evidence recorder
    -> mechanical scorer + human adjudication
    -> result report + SHA-256 manifest
```

### Case catalog

The catalog extends the existing `evals/cases.json` and `evals/v0.3-cases.json` contracts. Each case declares:

- stable case ID and kind;
- one-turn or multi-turn prompts;
- supplied repository evidence;
- expected activation or non-activation;
- required impacts and evidence relationships;
- forbidden neighboring workflows or fabricated decisions;
- expected report phase, lifecycle state, and Delta transition where applicable;
- clients and orchestrators to which the case applies.

The controller supplies the request and repository evidence to the model. It never supplies the rubric.

### Evaluation controller

The controller validates the catalog, probes the selected client, creates a fresh execution for every repetition, invokes the adapter, records artifacts, and continues after case-level failures. Its public interface is:

```sh
python3 evals/harness/run.py \
  --client codex \
  --model gpt-5.6-sol \
  --reasoning high \
  --repetitions 5 \
  --output evals/results/installed-v0.3
```

`--model` and `--reasoning` are optional. When omitted, the adapter preserves the client's current selection and records the resolved model and reasoning setting when the client exposes them. The skill itself never changes a model or reasoning setting.

### Adapter contract

Every client adapter implements three operations:

1. `probe`: identify executable availability, client version, authentication state when safely exposed, plugin version, and supported evaluation capabilities.
2. `prepare`: verify that the requested plugin and test inputs are available without changing skill behavior.
3. `execute`: run one case or return a structured non-behavior result such as `blocked` or `infra_error`.

The controller owns repetition, paths, timestamps, and result status. Adapters own only client-specific commands and output parsing.

### Codex adapter

The Codex adapter uses the installed marketplace plugin, not direct prompt injection of repository skill files. Before evaluation it records the current plugin version and enabled-plugin inventory, refreshes the marketplace, installs 0.3.0, and verifies both `codex plugin list` and the installed skill metadata. Superpowers remains installed and enabled; results apply only to the `Codex with Superpowers` composition.

Each one-turn run uses an ephemeral fresh context through `codex exec --ephemeral --json`. A multi-turn lineage case starts one new non-ephemeral session and resumes only its parsed UUID; it never uses `--last`. This is required because an ephemeral run does not persist a resumable session. The adapter captures JSONL events, the final message, stderr, exit code, client version, resolved model, reasoning level, active plugin version, orchestrator mode, and any persisted evaluation session ID. Persisted evaluation sessions remain visible in local Codex history and are disclosed as an environment side effect; the harness does not delete or reuse them across cases.

The production skill remains model-neutral. This batch pins `gpt-5.6-sol` with `high` reasoning solely because the user selected that evaluation configuration.

### Claude adapter

Claude Code is installed using Anthropic's native macOS installer after an explicit environment-mutation approval. The adapter performs only unauthenticated or non-model checks:

- `claude --version`;
- `claude doctor` when it does not require login;
- root plugin-manifest validation;
- marketplace registration and resolution;
- plugin discovery and installed skill inventory;
- package path and version inspection.

Any command that requires a paid account or model response stops at the authentication boundary and records `blocked — paid authentication unavailable`. Structural success must not be described as behavioral compatibility.

### Recorder

The recorder writes immutable artifacts under:

```text
evals/results/installed-v0.3/
  run.json
  manifest.sha256
  scores.json
  report.md
  raw/
    codex/<case-id>/<repetition>/
      prompt.txt
      events.jsonl
      final.md
      stderr.txt
      metadata.json
    claude/<probe-name>/
      command.txt
      stdout.txt
      stderr.txt
      metadata.json
```

The raw subtree is marked `-text -whitespace` in `.gitattributes`. A deterministic sorted `relative-path SHA-256` manifest covers every raw file. Tests assert the exact inventory and manifest digest.

### Scoring

Mechanical scoring covers report structure, activation, forbidden sections, known IDs, evidence levels, decision links, lifecycle states, Delta categories, lineage hashes, CLI exit codes, and exact repeated-case inventory. For `INT-superpowers`, the only mechanically scored workflow boundary is the exact structured `Planning Handoff` marker; free-text claims or contradictions about automatic planning are not parsed mechanically.

Substantive requirements such as whether the response found an important repository impact or avoided automatic planning require human adjudication. Every `must_detect` and `must_not_do` rubric is adjudicated for every repetition: the fixed 17-case matrix contains 80 rubrics and therefore requires 400 unique, transcript-bound rows. The adjudicator records the rubric item, result, exact transcript quotation, and rationale. Mechanical scores and adjudicated scores remain separate. `partial` is never counted as `pass`.

## Execution Protocol

### Environment gates

1. Record the existing Codex plugin version and path.
2. Refresh the Codex marketplace and verify that it advertises 0.3.0.
3. Replace the installed plugin and verify its canonical skill metadata.
4. Install the Claude native CLI after explicit approval.
5. Run both adapters' probes.
6. Run one repetition of a six-case smoke set.
7. Show the smoke results before starting the full Codex batch.

The smoke set covers at least one positive activation, one negative exclusion, one Superpowers boundary, one stable-lineage transition, one reopened transition, and one unsupported-resolution rejection. A skill failure in smoke does not justify modifying the skill in place. An infrastructure failure must be resolved before the full batch.

### Full Codex-with-Superpowers matrix

The full matrix has 17 cases and five repetitions each:

- 8 positive cases: 40 executions;
- 5 negative cases: 25 executions;
- 1 Superpowers integration case: 5 executions;
- 3 lineage cases: 15 executions.

Total live Codex execution count is 85. The generic, Claude feature-dev, and Spec Kit adapter contracts remain covered by deterministic structural tests; they receive no installed-client behavioral claim from this environment.

The default concurrency is one. This avoids rate-limit distortion and hidden cross-session state. The controller continues after ordinary skill failures. It pauses or records an infrastructure state for rate limits, network failures, CLI crashes, or timeouts.

### Rerun policy

- Never rerun a model or skill failure selectively.
- Never discard an unfavorable valid transcript.
- Retry only a classified infrastructure failure.
- Preserve the failed infrastructure attempt and its retry relationship.
- If skill wording changes, close the current batch and create a new named candidate batch from all selected cases.
- Seal raw evidence and its manifest before adjudication or public result editing.

## Status Model

| Status | Meaning |
| --- | --- |
| `pass` | All required contract items passed. |
| `partial` | Some required behavior appeared, but the strict contract failed. |
| `fail` | The client or skill produced a valid execution that violated the contract. |
| `blocked` | Authentication, permissions, or an unsupported environment prevented execution. |
| `infra_error` | Timeout, network, rate limit, or client crash interrupted execution. |
| `invalid_evidence` | Evidence is missing, corrupted, checksum-invalid, or unscorable. |

`blocked`, `infra_error`, and `invalid_evidence` do not count as skill passes. Every status is included in the public result report.

## Verification Thresholds

Codex-with-Superpowers installed-plugin behavior may be documented as `verified` only if all of the following hold:

- positive cases: 40/40 strict passes;
- negative cases: 25/25 without false activation;
- Superpowers integration case: 5/5 preserving its entry and exit boundary;
- lineage cases: 15/15 with correct Report ID, revision, predecessor SHA-256, lifecycle state, and Delta;
- zero fabricated decisions, implementation plans, or code execution outside the impact-refinement boundary;
- every mechanical and adjudicated claim links to preserved evidence.

Any contract violation keeps the `Codex with Superpowers` environment `not verified`. The documentation publishes the exact score and failure categories rather than softening the threshold. Codex standalone and the other orchestrator adapters remain `not verified` or structurally tested only.

Claude results use separate structural and behavioral dimensions. Successful CLI and package checks may be recorded as structurally validated. Behavior remains `blocked` until a paid authenticated execution exists.

## Security and Privacy

- Never capture the process environment wholesale.
- Never read or store tokens, Keychain entries, API keys, or Claude credential files.
- Record only prompts, model outputs, public command output, explicit client metadata, and exit status.
- Record multi-turn Codex session UUIDs only as execution metadata; never use `--last` or resume an unrelated session.
- Scan prospective evidence for likely secrets before adding it to the repository.
- If a secret may be present, quarantine the artifact outside the repository without rewriting it and mark the execution `blocked: potential secret exposure`.
- Do not auto-redact an artifact and then describe it as raw evidence.

## Error Handling

Timeouts are configurable per adapter and recorded with elapsed time. Malformed Codex JSONL, incomplete final messages, checksum differences, duplicate run IDs, and unsupported case versions fail evidence validation deterministically. Rate limits are distinguished from ordinary model failures. Controller crashes must not overwrite an existing run directory; output paths are created per run and finalized atomically.

## Testing

The harness uses the Python standard library. Tests cover:

- catalog and result schema validation;
- deterministic command construction;
- user-selected model pass-through and no model override when omitted;
- fake Codex and Claude executables;
- multi-turn session linkage;
- timeout, crash, rate-limit, and malformed-output classification;
- complete raw inventory and checksum manifests;
- secret-detection quarantine behavior;
- mechanical scoring and human-adjudication schema separation;
- report generation without promoting `partial` or `blocked` to `pass`.

Ordinary CI runs only deterministic harness tests. Live model execution, marketplace mutation, and Claude installation occur only in an explicitly approved release-evaluation workflow.

## Version and Documentation Policy

This cycle builds evaluation infrastructure and evidence. If canonical skill, template, or plugin behavior is unchanged, the plugin remains 0.3.0. Evaluation failures do not trigger same-batch prompt tuning.

After the batch:

- all strict Codex passes may promote the installed Codex row to `verified` with exact environment metadata;
- any strict failure retains `not verified` and publishes the score;
- Claude structure and behavior are reported separately;
- English, Korean, and Japanese compatibility tables change together;
- any proposed skill correction starts a separate requirements-impact refinement and version decision.

## Out of Scope

- report-workspace CLI;
- JSON impact-report output;
- MCP server or code-graph engine;
- new orchestrator adapters;
- temporary removal or reconfiguration of Superpowers to simulate standalone Codex;
- GitHub marketing, releases, or Showcase submission;
- skill wording or template changes based on this batch's results;
- paid Claude authentication or model behavior.

## Acceptance Criteria

The work is complete when the common harness and adapters pass deterministic tests, the installed Codex plugin is confirmed at 0.3.0 with Superpowers enabled, Claude structural checks are captured without authentication, the smoke checkpoint is reviewed, the full 85-run Codex-with-Superpowers batch is preserved and scored, the manifest verifies, and all three README compatibility tables state only what the evidence supports.
