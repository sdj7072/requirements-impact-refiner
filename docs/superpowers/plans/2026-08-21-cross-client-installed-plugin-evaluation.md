# Cross-Client Installed Plugin Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run an auditable client-neutral harness that evaluates Requirements Impact Refiner 0.3.0 in the installed Codex-with-Superpowers environment and structurally validates Claude Code without paid authentication.

**Architecture:** A Python standard-library controller loads a fixed case catalog, delegates commands to Codex and Claude adapters, records immutable raw artifacts, separates mechanical scoring from quoted human adjudication, and renders bounded compatibility evidence. Live installation and model execution are explicit user-approved release checkpoints; ordinary CI uses fake executables only.

**Tech Stack:** Python 3.11 standard library, `unittest`, subprocess, Codex CLI 0.148.0-alpha.21, Claude Code native CLI, JSON/JSONL, Markdown, SHA-256, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-21-cross-client-installed-plugin-evaluation-design.md`

**Impact report:** `docs/superpowers/specs/2026-08-21-cross-client-installed-plugin-evaluation-impact-report.md` Revision 3

## Global Constraints

- Keep plugin and skill version `0.3.0` unless a separately approved behavior change modifies plugin content.
- Use only the Python 3.11 standard library.
- Keep the production skill model-neutral. Model and reasoning arguments are run-local inputs.
- Bound live claims to `Codex with Superpowers`; do not remove or reconfigure Superpowers.
- Run one-turn Codex cases with `--ephemeral`; start a new persisted session for each multi-turn case and resume only its parsed UUID. Never use `--last`.
- Preserve every prompt, JSONL stream, final message, stderr stream, metadata object, probe, and infrastructure attempt.
- Never read or record complete process environments, Keychain entries, auth files, tokens, or API keys.
- Quarantine suspicious output outside the repository; never redact it and call it raw evidence.
- Live clients, marketplace mutation, installers, and model calls are forbidden in ordinary CI.
- Never selectively rerun a valid model failure or tune the skill inside the same batch.
- Require fresh approval before Codex plugin replacement, Claude installation, and the full 85-run batch.

## File Structure

- `evals/harness/models.py`: immutable case, command, probe, run, score, and status types.
- `evals/harness/catalog.py`: exact validation and smoke/full suite selection.
- `evals/harness/process.py`: `shell=False` execution and timeout capture.
- `evals/harness/evidence.py`: secret screening, atomic writes, inventory, and SHA-256 verification.
- `evals/harness/adapters/base.py`: adapter protocol.
- `evals/harness/adapters/codex.py`: installed composition probe, commands, JSONL parsing, and UUID resume.
- `evals/harness/adapters/claude.py`: unauthenticated Claude structural probes and blocked behavior.
- `evals/harness/scoring.py`: mechanical checks and adjudication completeness.
- `evals/harness/reporting.py`: bounded JSON and Markdown summaries.
- `evals/harness/run.py`: CLI, scheduling, gates, retries, and adapter registry.
- `evals/installed-v0.3-lineage-cases.json`: full prompts and rubrics for three lineage cases.
- `evals/harness/schemas/*.json`: public contracts synchronized with Python validation.
- `tests/test_eval_harness_*.py`: focused standard-library tests.
- `evals/results/installed-v0.3/`: live evidence created only after approval.

---

### Task 1: Domain Types, Schemas, and Case Catalog

**Files:**
- Create: `evals/harness/__init__.py`
- Create: `evals/harness/models.py`
- Create: `evals/harness/catalog.py`
- Create: `evals/harness/adapters/__init__.py`
- Create: `evals/harness/adapters/base.py`
- Create: `evals/harness/schemas/case.schema.json`
- Create: `evals/harness/schemas/result.schema.json`
- Create: `evals/installed-v0.3-lineage-cases.json`
- Test: `tests/test_eval_harness_contract.py`

**Interfaces:**
- Consumes: `evals/cases.json`, full lineage catalog, client/model/reasoning/repetition/output inputs.
- Produces: `RunStatus`, `CaseTurn`, `CaseSpec`, `RunRequest`, `CommandResult`, `ClientProbe`, `RunResult`, `MechanicalScore`, `Adjudication`, `ClientAdapter`, `load_catalog()`, and `select_suite()`.

- [ ] **Step 1: Write failing exact-inventory tests**

~~~python
def test_installed_superpowers_suite_has_seventeen_cases():
    selected = select_suite(load_all(), "installed-superpowers")
    self.assertEqual(len(selected), 17)
    self.assertEqual(sum(case.kind == "positive" for case in selected), 8)
    self.assertEqual(sum(case.kind == "negative" for case in selected), 5)
    self.assertEqual([c.id for c in selected if c.kind == "integration"], ["INT-superpowers"])
    self.assertEqual(sum(case.kind == "lineage" for case in selected), 3)

def test_smoke_suite_is_the_approved_gate():
    self.assertEqual([c.id for c in select_suite(load_all(), "smoke")], [
        "POS-authorization", "NEG-debugging", "INT-superpowers",
        "LINEAGE-stable-blocked", "LINEAGE-reopened",
        "LINEAGE-no-false-resolution",
    ])
~~~

- [ ] **Step 2: Run RED**

Run: `python3 -m unittest tests.test_eval_harness_contract -v`

Expected: import failure because `evals.harness` does not exist.

- [ ] **Step 3: Implement immutable types**

~~~python
class RunStatus(str, Enum):
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"
    BLOCKED = "blocked"
    INFRA_ERROR = "infra_error"
    INVALID_EVIDENCE = "invalid_evidence"

@dataclass(frozen=True)
class CaseTurn:
    prompt: str
    repository_evidence: tuple[str, ...]

@dataclass(frozen=True)
class CaseSpec:
    id: str
    kind: str
    turns: tuple[CaseTurn, ...]
    must_detect: tuple[str, ...]
    must_not_do: tuple[str, ...]
    modes: tuple[str, ...]
    expected_transition: str | None = None

@dataclass(frozen=True)
class RunRequest:
    case: CaseSpec
    repetition: int
    client: str
    model: str | None
    reasoning: str | None
    output_root: Path
~~~

Define immutable command/probe/result/score/adjudication types with fields mirrored in `result.schema.json`. Define `ClientAdapter` as a `Protocol` with `probe()`, `prepare()`, and `execute(request)`.

- [ ] **Step 4: Add complete lineage cases**

Create two-turn `LINEAGE-stable-blocked` and `LINEAGE-reopened` cases and one unsupported-resolution case. Prompts include scenario/evidence but never rubric. Rubrics require stable IDs, exact predecessor bytes, approved transitions, and no unsupported resolution.

- [ ] **Step 5: Implement strict loader and selectors**

Reject duplicate IDs, unknown kinds/modes, blank prompts, non-list evidence, missing rubric arrays, and incomplete lineage transitions. Preserve `evals/cases.json` bytes.

- [ ] **Step 6: Run GREEN and commit**

Run: `python3 -m unittest tests.test_eval_harness_contract tests.test_eval_cases -v`

~~~bash
git add evals/harness evals/installed-v0.3-lineage-cases.json tests/test_eval_harness_contract.py
git commit -m "feat: define installed plugin evaluation contract"
~~~

### Task 2: Safe Process Execution and Evidence Integrity

**Files:**
- Create: `evals/harness/process.py`
- Create: `evals/harness/evidence.py`
- Test: `tests/test_eval_harness_evidence.py`

**Interfaces:** Produces `run_command()`, `find_potential_secrets()`, `record_run()`, `build_manifest()`, and `verify_manifest()`.

- [ ] **Step 1: Write failing timeout, secret, and checksum tests**

~~~python
def test_timeout_is_preserved():
    result = run_command([sys.executable, "-c", "import time; time.sleep(2)"], ROOT, 0.01)
    self.assertTrue(result.timed_out)
    self.assertIsNone(result.returncode)

def test_secret_detector_requires_concrete_value():
    self.assertEqual(find_potential_secrets("API key is required"), ())
    self.assertIn("github-token", find_potential_secrets("token=gho_abcdefghijklmnopqrstuvwxyz123456"))

def test_one_byte_change_breaks_manifest():
    manifest = build_manifest(raw_root)
    target.write_bytes(target.read_bytes() + b"x")
    self.assertEqual(verify_manifest(raw_root, manifest), ["checksum mismatch: codex/POS-authorization/01/final.md"])
~~~

- [ ] **Step 2: Run RED**

Run: `python3 -m unittest tests.test_eval_harness_evidence -v`

- [ ] **Step 3: Implement safe subprocess execution**

Use `subprocess.run(..., shell=False)`, UTF-8 replacement decoding, monotonic elapsed time, and captured `TimeoutExpired` output. Never pass a copied full environment.

- [ ] **Step 4: Implement secret screening and atomic recording**

Detect concrete GitHub/OpenAI/Anthropic token shapes, private-key headers, and long credential assignments. Write to a sibling temporary directory and finalize with `os.replace`; refuse overwrite.

- [ ] **Step 5: Implement deterministic manifests**

Rows are `relative/path lowercase_sha256`, sorted by POSIX path, with one final newline. Exclude the manifest itself.

- [ ] **Step 6: Run GREEN and commit**

~~~bash
python3 -m unittest tests.test_eval_harness_evidence -v
git add evals/harness/process.py evals/harness/evidence.py tests/test_eval_harness_evidence.py
git commit -m "feat: preserve evaluation evidence safely"
~~~

### Task 3: Codex Installed-Composition Adapter

**Files:**
- Create: `evals/harness/adapters/codex.py`
- Test: `tests/test_eval_harness_codex.py`

**Interfaces:** Produces `CodexAdapter.probe()`, `prepare()`, `execute()`, `build_first_turn_command()`, `build_resume_command()`, and `parse_thread_id()`.

- [ ] **Step 1: Write failing model and session-boundary tests**

~~~python
def test_one_turn_is_ephemeral_and_omitted_model_stays_omitted():
    argv = adapter.build_first_turn_command(request_without_model, paths)
    self.assertIn("--ephemeral", argv)
    self.assertNotIn("-m", argv)
    self.assertNotIn("model_reasoning_effort", " ".join(argv))

def test_selected_model_is_run_local():
    argv = adapter.build_first_turn_command(sol_request, paths)
    self.assertIn("gpt-5.6-sol", argv)
    self.assertIn('model_reasoning_effort="high"', argv)

def test_resume_uses_only_parsed_uuid():
    tid = adapter.parse_thread_id('{"type":"thread.started","thread_id":"123e4567-e89b-12d3-a456-426614174000"}\n')
    argv = adapter.build_resume_command(sol_request, tid, "second turn", paths)
    self.assertIn(tid, argv)
    self.assertNotIn("--last", argv)
~~~

- [ ] **Step 2: Run RED**

Run: `python3 -m unittest tests.test_eval_harness_codex -v`

- [ ] **Step 3: Implement probe parsing**

Run `codex --version` and `codex plugin list --json`. Require enabled Requirements Impact Refiner 0.3.0 and enabled Superpowers; record every enabled plugin ID and label the environment `Codex with Superpowers`.

- [ ] **Step 4: Implement commands**

One-turn argv uses `codex exec --ephemeral --json -s read-only --approve-for-me -o FINAL`. Multi-turn first argv omits only `--ephemeral`. Add `-m MODEL` and `-c model_reasoning_effort="LEVEL"` only when supplied.

- [ ] **Step 5: Implement exact resume and error classification**

Accept only a UUID from `thread.started`. Resume with `codex exec resume --json -o FINAL THREAD_ID PROMPT`; never use `--last`. Missing JSONL/thread/final output and nonzero/timeout results become preserved `infra_error` attempts.

- [ ] **Step 6: Run GREEN and commit**

~~~bash
python3 -m unittest tests.test_eval_harness_codex -v
git add evals/harness/adapters/codex.py tests/test_eval_harness_codex.py
git commit -m "feat: add installed Codex evaluation adapter"
~~~

### Task 4: Claude Structural Adapter

**Files:**
- Create: `evals/harness/adapters/claude.py`
- Test: `tests/test_eval_harness_claude.py`

**Interfaces:** Produces `ClaudeAdapter.probe()`, `prepare()`, `execute()`, and `structural_commands()`.

- [ ] **Step 1: Write failing authentication-boundary tests**

~~~python
def test_commands_never_authenticate_or_prompt_model():
    flattened = " ".join(a for command in adapter.structural_commands(ROOT) for a in command)
    self.assertNotIn("login", flattened)
    self.assertNotIn("auth", flattened)
    self.assertIn("plugin validate", flattened)

def test_behavior_is_blocked():
    result = adapter.execute(request)
    self.assertEqual(result.status, RunStatus.BLOCKED)
    self.assertEqual(result.reason, "paid authentication unavailable")
~~~

- [ ] **Step 2: Run RED**

Run: `python3 -m unittest tests.test_eval_harness_claude -v`

- [ ] **Step 3: Implement structural probes**

Probe `claude --version`, bounded `claude doctor`, `claude plugin validate .`, `claude plugin marketplace list`, and `claude plugin list --json`. If doctor requires login, time it out and mark only that probe blocked.

- [ ] **Step 4: Enforce no behavior execution**

Never run interactive Claude, `claude -p`, `/login`, or `claude auth login`. Return the paid-authentication block for behavior.

- [ ] **Step 5: Run GREEN and commit**

~~~bash
python3 -m unittest tests.test_eval_harness_claude -v
git add evals/harness/adapters/claude.py tests/test_eval_harness_claude.py
git commit -m "feat: add Claude structural evaluation adapter"
~~~

### Task 5: Scoring and Bounded Reporting

**Files:**
- Create: `evals/harness/scoring.py`
- Create: `evals/harness/reporting.py`
- Test: `tests/test_eval_harness_scoring.py`

**Interfaces:** Produces `score_mechanical()`, `validate_adjudications()`, `summarize()`, and `render_report()`.

- [ ] **Step 1: Write failing strict arithmetic and quotation tests**

~~~python
def test_nonpass_statuses_never_count_as_pass():
    summary = summarize(results_with_every_status)
    self.assertEqual(summary["strict_passes"], 1)
    self.assertEqual(summary["partial"], 1)
    self.assertEqual(summary["blocked"], 1)

def test_adjudication_requires_quote_and_rationale():
    row = Adjudication("POS-authorization", 1, "authorization impact", False, "", "")
    self.assertEqual(validate_adjudications([row]), ["POS-authorization/01 authorization impact requires quote and rationale"])
~~~

- [ ] **Step 2: Run RED**

Run: `python3 -m unittest tests.test_eval_harness_scoring -v`

- [ ] **Step 3: Implement mechanical scoring**

Use the canonical report validator for complete reports. Negative cases pass only without refinement IDs/workflow. `INT-superpowers` checks approved entry/exit and no automatic planning. Lineage checks transition and resolution rejection.

- [ ] **Step 4: Implement bounded rendering**

Require client, version, enabled composition, model, reasoning, and repetitions. Only 85/85 may render `verified` for `Codex with Superpowers`; never promote another Codex mode or Claude behavior.

- [ ] **Step 5: Run GREEN and commit**

~~~bash
python3 -m unittest tests.test_eval_harness_scoring -v
git add evals/harness/scoring.py evals/harness/reporting.py tests/test_eval_harness_scoring.py
git commit -m "feat: score installed plugin evaluations"
~~~

### Task 6: Controller CLI, Scheduling, and Retries

**Files:**
- Create: `evals/harness/run.py`
- Test: `tests/test_eval_harness_cli.py`

**Interfaces:** Consumes `--client`, `--suite smoke|installed-superpowers`, `--repetitions`, optional model/reasoning, `--output`, timeout, and `--probe-only`. Produces exit 0 for complete batch, 1 for invalid evidence/controller failure, and 2 for invocation errors.

- [ ] **Step 1: Write failing parser and schedule tests**

~~~python
def test_omitted_model_is_none():
    args = build_parser().parse_args(["--client", "codex", "--suite", "smoke", "--output", "out"])
    self.assertIsNone(args.model)
    self.assertIsNone(args.reasoning)

def test_schedule_sizes():
    self.assertEqual(len(build_schedule(load_all(), "smoke", 1)), 6)
    self.assertEqual(len(build_schedule(load_all(), "installed-superpowers", 5)), 85)
~~~

- [ ] **Step 2: Run RED**

Run: `python3 -m unittest tests.test_eval_harness_cli -v`

- [ ] **Step 3: Implement argparse and deterministic schedule**

Reject model/reasoning for Claude structural mode. Schedule canonical case order then repetition 1–N. Persist multi-turn UUIDs only in run metadata.

- [ ] **Step 4: Implement retry and finalization rules**

Never overwrite completed IDs. Infrastructure retries use `attempt-02` plus `retry_of`; pass/partial/fail never retry. Verify manifest before exit 0.

- [ ] **Step 5: Run all harness tests and commit**

~~~bash
python3 -m unittest tests.test_eval_harness_contract tests.test_eval_harness_evidence tests.test_eval_harness_codex tests.test_eval_harness_claude tests.test_eval_harness_scoring tests.test_eval_harness_cli -v
git add evals/harness/run.py tests/test_eval_harness_cli.py
git commit -m "feat: orchestrate installed plugin evaluations"
~~~

### Task 7: CI and Documentation Before Live Evaluation

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `evals/runbook.md`
- Modify: `CONTRIBUTING.md`
- Modify: `README.md`, `README.ko.md`, `README.ja.md`
- Modify: `tests/test_documentation.py` and `tests/test_packaging.py`

**Interfaces:** Produces fake-client-only CI, approval gates, model-neutral wording, and unchanged pre-evaluation statuses.

- [ ] **Step 1: Add RED docs/CI tests**

Require all README languages to contain `85`, `Codex with Superpowers`, `gpt-5.6-sol`, `user-selected evaluation model`, `Claude structural`, and `paid authentication unavailable`, while stating the skill does not select a model. Require CI compilation and forbid `codex exec` and Claude installer commands.

- [ ] **Step 2: Run RED**

Run: `python3 -m unittest tests.test_documentation tests.test_packaging -v`

- [ ] **Step 3: Update CI, runbook, and contributing**

Add harness tests/compilation. Document live versus fake clients, statuses, all-raw evidence, approval gates, composition bounds, and no selective reruns.

- [ ] **Step 4: Synchronize EN/KO/JA docs without status promotion**

Explain the planned user-selected Sol batch and model-neutral skill. Keep current statuses until sealed evidence exists.

- [ ] **Step 5: Run full tests and commit**

~~~bash
python3 -m unittest discover -s tests -v
git add .github/workflows/ci.yml evals/runbook.md CONTRIBUTING.md README.md README.ko.md README.ja.md tests/test_documentation.py tests/test_packaging.py
git commit -m "docs: define installed plugin evaluation workflow"
~~~

### Task 8: Live Preparation and Six-Case Smoke — Two Approval Gates

**Files:**
- Create after approval: `evals/results/installed-v0.3/raw/codex/` and `raw/claude/`
- Create after approval: `run.json` and `manifest.sha256`
- Modify after safe capture: `.gitattributes`
- Create: `tests/test_installed_plugin_evidence.py`

**Interfaces:** Produces before/after Codex inventory, Claude structural probes, six smoke runs, sealed manifest, and projected duration.

- [ ] **Step 1: STOP and request approval for both mutations**

Show exact actions: replace Requirements Impact Refiner, retain Superpowers, install Claude, never login or purchase.

- [ ] **Step 2: Capture Codex before-state**

Run: `python3 -m evals.harness.run --client codex --probe-only --output evals/results/installed-v0.3`

- [ ] **Step 3: Refresh and replace Requirements Impact Refiner only**

~~~bash
codex plugin marketplace upgrade requirements-impact-refiner
codex plugin remove requirements-impact-refiner@requirements-impact-refiner --json
codex plugin add requirements-impact-refiner@requirements-impact-refiner --json
~~~

Verify RIR 0.3.0 and Superpowers still enabled; stop otherwise.

- [ ] **Step 4: Install Claude and run structural probes**

~~~bash
curl -fsSL https://claude.ai/install.sh | bash
claude --version
python3 -m evals.harness.run --client claude --probe-only --output evals/results/installed-v0.3
~~~

Do not run interactive Claude or authentication.

- [ ] **Step 5: Run smoke**

~~~bash
python3 -m evals.harness.run --client codex --suite smoke --repetitions 1 --model gpt-5.6-sol --reasoning high --output evals/results/installed-v0.3
~~~

- [ ] **Step 6: Seal and verify smoke evidence**

Add `-text -whitespace` for raw. Require six final records or disclosed infrastructure attempts. Quarantine and stop on any potential secret.

- [ ] **Step 7: Commit safe smoke evidence without skill changes**

Commit only safe artifacts, manifest, metadata, attributes, and evidence tests.

- [ ] **Step 8: STOP and request approval for full batch**

Report smoke statuses, elapsed time, rate limits, persisted session IDs, and projected duration.

### Task 9: Full Batch, Adjudication, Claims, and Review

**Files:**
- Extend: `evals/results/installed-v0.3/raw/codex/`
- Modify: `run.json` and `manifest.sha256`
- Create: `scores.json`, `adjudication.json`, `report.md`
- Modify: `tests/test_installed_plugin_evidence.py`
- Modify: all three READMEs

**Interfaces:** Produces 85 scheduled finals plus retained infra attempts, complete adjudication, strict score, and bounded multilingual claims.

- [ ] **Step 1: Confirm harness/skill/catalog/scorer hashes match smoke metadata**

Stop if evaluation or canonical skill files changed.

- [ ] **Step 2: Run full suite sequentially**

~~~bash
python3 -m evals.harness.run --client codex --suite installed-superpowers --repetitions 5 --model gpt-5.6-sol --reasoning high --output evals/results/installed-v0.3
~~~

- [ ] **Step 3: Retry only infrastructure attempts**

Use controller retry IDs; never retry pass/partial/fail. Preserve `retry_of`.

- [ ] **Step 4: Seal raw before adjudication**

Require 85 finals, five repetitions per applicable case, complete artifacts, no duplicate IDs, exact manifest, and no secret finding.

- [ ] **Step 5: Adjudicate every substantive item**

Record case, repetition, rubric, boolean, exact quotation, and rationale. Reject missing fields and checksum-invalid citations.

- [ ] **Step 6: Write RED final evidence/docs tests**

Assert inventory, manifest, 85 results, versions, plugin composition, model metadata, arithmetic, Claude structural-only wording, and cross-language parity.

- [ ] **Step 7: Update claims conditionally**

Set only `Codex with Superpowers` to `verified` if all 85 strictly pass; otherwise retain `not verified` with exact failures. Keep standalone/other adapters unchanged and Claude behavior blocked.

- [ ] **Step 8: Run full verification**

~~~bash
python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=/tmp/requirements-impact-refiner-eval-pycache python3 -m py_compile evals/harness/*.py evals/harness/adapters/*.py skills/requirements-impact-refiner/scripts/*.py
git diff --check
~~~

- [ ] **Step 9: Commit sealed evidence and bounded docs**

Stage only named safe evidence, tests, and READMEs. Commit `test: record installed cross-client evaluation`.

- [ ] **Step 10: Request independent review**

Use `superpowers:requesting-code-review`. Probe model pass-through, composition, ephemeral/persisted boundaries, no `--last`, fake-client CI, secret quarantine, manifest tampering, 85-run inventory, arithmetic, Claude block, and multilingual parity.

- [ ] **Step 11: Fix P0–P2 with RED tests and report local readiness**

Use `receiving-code-review` and `systematic-debugging`; never edit sealed raw evidence. Report test count, environment, score, manifest digest, commit range, and clean status. Do not merge or push without user instruction.

