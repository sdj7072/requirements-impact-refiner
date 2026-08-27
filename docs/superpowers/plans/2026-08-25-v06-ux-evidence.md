# v0.6 UX and Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the instant-report runtime as structured en/ko/ja previous, Fast Scan, and detailed reports, then produce a sealed five-repetition Codex and Claude release matrix.

**Architecture:** Locale selection is explicit-first and presentation-only. Renderers share one catalog and preserve machine identifiers. The evaluation harness stages isolated repositories and sessions, records every first attempt, and fails closed on any mechanical or evidence-integrity error.

**Tech Stack:** Python standard library; existing renderer/controller schemas; Codex CLI; Claude Code; sealed JSONL/Markdown evidence.

**Spec:** `docs/superpowers/specs/2026-08-25-v0.6-production-readiness-design.md` and `docs/superpowers/specs/2026-08-25-v0.6-instant-report-performance-design.md`

## Global Constraints

- Complete the quality-foundation, controller/graph, and instant-report runtime plans first.
- Locale never changes scan identity, evidence values, IDs, lifecycle enums, or canonical transition rules.
- Exact machine strings such as `verified`, `IMP-001`, provider names, paths, and the Superpowers handoff marker stay untranslated.
- Fast Scan remains at most 180 words; compact detailed output remains at most 450 words.
- Every live run uses an isolated repository, session, and output directory.
- A failed first attempt remains a release failure even if a diagnostic retry passes.
- Rendering consumes `PreviousReportResult` and `PerformanceMetrics` without changing report identity, freshness classification, timeout state, cache status, or token calculations.
- Every locale exposes previous-result freshness, changed-file count, unknown frontier, elapsed time, cache, bytes, and token estimate fields with the same semantics.

---

### Task 1: Add explicit locale to settings and request contracts

**Files:**
- Create: `scripts/presentation_locale.py`
- Create: `skills/requirements-impact-refiner/scripts/presentation_locale.py`
- Modify: `scripts/resolve-settings.py`
- Modify: `scripts/fast_scan.py`
- Modify: `scripts/rir_contracts.py`
- Modify: `scripts/rir_mcp_server.py`
- Modify: `schemas/controller-analysis.schema.json`
- Modify: installed-skill mirrors
- Test: `tests/test_presentation_locale.py`

**Interfaces:**
- Produces: `resolve_locale(explicit: object, request_text: str, evidence: Sequence[str]) -> tuple[str, str]`
- Consumes: explicit request override, repository `locale`, character inference

- [ ] **Step 1: Write locale precedence tests**

```python
def test_locale_precedence_is_explicit_then_repository_then_inference(self):
    self.assertEqual(resolve_locale("ja", "한국어 요청", ()), ("ja", "request"))
    self.assertEqual(resolve_locale(None, "English", (), repository="ko"), ("ko", "repository"))
    self.assertEqual(resolve_locale(None, "한국어 요청", ()), ("ko", "inferred"))
    self.assertEqual(resolve_locale(None, "plain request", ()), ("en", "fallback"))
```

- [ ] **Step 2: Run and observe the missing module**

Run: `python3 -m unittest -q tests.test_presentation_locale`

- [ ] **Step 3: Implement bounded locale resolution**

Allow only `en`, `ko`, and `ja`. Reject invalid explicit values. Repository invalid values fall back with a disclosed warning. Character inference detects Hangul before kana; English is the fallback. Add `locale` and `locale_source` to presentation settings but not graph identity.

- [ ] **Step 4: Verify settings, MCP, and cache behavior**

Run: `python3 -m unittest -q tests.test_presentation_locale tests.test_presentation_settings tests.test_rir_mcp_server tests.test_fast_scan`

- [ ] **Step 5: Commit**

```bash
git add scripts/presentation_locale.py skills/requirements-impact-refiner/scripts/presentation_locale.py scripts/resolve-settings.py scripts/fast_scan.py scripts/rir_contracts.py scripts/rir_mcp_server.py schemas/controller-analysis.schema.json skills/requirements-impact-refiner tests/test_presentation_locale.py
git commit -m "feat: add explicit presentation locale"
```

### Task 2: Preserve structured Fast Scan Markdown under the word budget

**Files:**
- Modify: `scripts/fast_scan_renderer.py`
- Modify: installed-skill mirror
- Test: `tests/test_fast_scan_renderer.py`
- Create: `tests/fixtures/fast-scan-rendered-en.md`
- Create: `tests/fixtures/fast-scan-rendered-ko.md`
- Create: `tests/fixtures/fast-scan-rendered-ja.md`

**Interfaces:**
- Produces: `render_fast_scan(receipt, audience, locale) -> str` with newline-preserving blocks
- Consumes: existing receipt, optional `PreviousReportResult`, `PerformanceMetrics`, and locale catalog

- [ ] **Step 1: Write golden structure tests**

```python
def test_balanced_korean_output_keeps_sections_and_numbered_paths(self):
    text = render_fast_scan(PARTIAL_RECEIPT, "balanced", "ko")
    self.assertEqual(text, KO_GOLDEN.read_text(encoding="utf-8"))
    self.assertIn("\n### 발생 가능한 영향 경로\n", text)
    self.assertIn("\n1. `api/profile.py` → `mobile/profile.py`\n", text)
    self.assertIn("\n### 미확인 범위\n", text)
    self.assertIn("\n### 이전 결과\n", text)
    self.assertIn("기준 커밋:", text)
    self.assertIn("변경 파일:", text)
    self.assertIn("\n### 검사 정보\n", text)
    self.assertIn("예상 토큰:", text)
    self.assertTrue(text.rstrip().endswith("상세 영향도 정제를 진행할까요?"))
```

- [ ] **Step 2: Run and confirm the flattened renderer fails**

Run: `python3 -m unittest -q tests.test_fast_scan_renderer`

Expected: golden tests fail because `_bounded_lines` joins blocks with spaces.

- [ ] **Step 3: Replace word arrays with complete render blocks**

Represent status, previous-result identity/freshness, path records, cause-impact-prevention rows, frontier records, performance metadata, and the question as complete blocks. Count words across blocks. Drop the lowest-priority complete path block before freshness, safety, or metadata blocks. Simple mode emits freshness, path, risk, and next action; balanced adds cause, impact, prevention, and selected provenance; technical adds provider, confidence, locations, receipt coverage, byte/token metrics, and omission counts.

- [ ] **Step 4: Verify all locales and boundary mutations**

Run: `python3 -m unittest -q tests.test_fast_scan_renderer tests.test_fast_scan tests.test_fast_scan_eval_cases`

Assert all golden outputs are at most 180 words, contain the same semantic freshness/frontier/performance fields, and contain no truncated Markdown marker, path, or warning.

- [ ] **Step 5: Commit**

```bash
git add scripts/fast_scan_renderer.py skills/requirements-impact-refiner/scripts/fast_scan_renderer.py tests/test_fast_scan_renderer.py tests/fixtures/fast-scan-rendered-*.md
git commit -m "feat: structure localized fast scan output"
```

### Task 3: Localize full and compact impact reports

**Files:**
- Create: `scripts/presentation_catalog.py`
- Create: installed-skill mirror
- Modify: `scripts/impact_renderer.py`
- Modify: `scripts/rir_finalize.py`
- Modify: report templates under `assets/` and `skills/requirements-impact-refiner/assets/`
- Test: `tests/test_impact_renderer_locale.py`

**Interfaces:**
- Produces: `catalog(locale) -> PresentationCatalog`; `render_markdown(state, locale="en")`; `render_compact(state, locale="en")`
- Consumes: canonical state plus previous-result and performance fields whose machine values remain English

- [ ] **Step 1: Write semantic-equivalence tests**

```python
def test_all_locales_round_trip_to_the_same_state(self):
    rendered = {
        locale: render_markdown(STATE, locale)
        for locale in ("en", "ko", "ja")
    }
    for locale, text in rendered.items():
        parsed, errors = state_from_markdown(text, locale=locale)
        self.assertEqual(errors, [], locale)
        self.assertEqual(parsed, STATE, locale)
```

- [ ] **Step 2: Run and observe unsupported locale arguments**

Run: `python3 -m unittest -q tests.test_impact_renderer_locale`

- [ ] **Step 3: Add catalog-backed headings and parsers**

Translate headings, explanatory labels, freshness states, changed-file summaries, performance labels, questions, validation summaries, and handoff guidance. Preserve IDs, evidence levels, lifecycle states, category keys in canonical JSON, provider names, paths, digests, numeric metrics, and `superpowers:after-approved-brainstorming;impact-refinement;manual-handoff-before-writing-plans` exactly.

- [ ] **Step 4: Verify compact budgets and full parser parity**

Run: `python3 -m unittest -q tests.test_impact_renderer_locale tests.test_impact_renderer tests.test_validate_impact_report tests.test_semantic_validation`

- [ ] **Step 5: Commit**

```bash
git add scripts/presentation_catalog.py scripts/impact_renderer.py scripts/rir_finalize.py skills/requirements-impact-refiner assets tests/test_impact_renderer_locale.py
git commit -m "feat: localize complete impact reports"
```

### Task 4: Revise the client catalog for Fast Scan and two-turn flow

**Files:**
- Modify: `evals/cases.json`
- Modify: `evals/claude-v05-cases.json`
- Modify: `evals/harness/catalog.py`
- Modify: `evals/harness/models.py`
- Modify: `evals/harness/adapters/codex.py`
- Modify: `evals/harness/adapters/claude.py`
- Test: `tests/test_eval_cases.py`
- Test: `tests/test_eval_harness_codex.py`
- Test: `tests/test_eval_harness_claude.py`

**Interfaces:**
- Produces: positive two-turn cases with explicit confirmation; negative one-turn cases; isolated staged fixtures
- Consumes: Fast Scan and detailed-refinement tool contracts

- [ ] **Step 1: Write catalog-shape and scheduling tests**

```python
def test_positive_cases_have_scan_and_confirmation_turns(self):
    for case in load_all():
        if case.kind == "positive":
            self.assertEqual(len(case.turns), 2)
            self.assertIn("detailed refinement", case.turns[1].prompt.lower())
        elif case.kind == "negative":
            self.assertEqual(len(case.turns), 1)
```

Add exact-repeat cases whose only tool is `rir_previous`, stale cases whose order is `rir_previous` then `rir_scan`, ambiguous-lineage cases that stop after `rir_previous`, and changed-A fixtures that require indirect C/D/Z impact or an explicit unknown frontier.

- [ ] **Step 2: Run and capture the one-turn catalog failure**

Run: `python3 -m unittest -q tests.test_eval_cases tests.test_eval_harness_codex tests.test_eval_harness_claude`

- [ ] **Step 3: Update cases and adapters**

Every positive fixture is staged inside its isolated repository before turn 1. Turn 2 says yes to detailed refinement and specifies the adapter already selected by the case. Adapters resume only the exact session ID from turn 1; they never use a global last-session shortcut. Each case gets a unique scratch root and scan-request path.

- [ ] **Step 4: Run fake-client integration tests**

Run: `python3 -m unittest -q tests.test_eval_harness_cli tests.test_eval_harness_codex tests.test_eval_harness_claude tests.test_controller_evidence`

- [ ] **Step 5: Commit**

```bash
git add evals/cases.json evals/claude-v05-cases.json evals/harness tests/test_eval_cases.py tests/test_eval_harness_codex.py tests/test_eval_harness_claude.py
git commit -m "eval: model the fast scan confirmation turn"
```

### Task 5: Add the v0.6 release-matrix controller

**Files:**
- Create: `evals/v0.6-release-cases.json`
- Create: `scripts/run-v06-release-matrix.py`
- Create: `tests/test_v06_release_matrix.py`
- Modify: `evals/harness/run.py`
- Modify: `evals/harness/reporting.py`

**Interfaces:**
- Produces: exact Codex and Claude schedules, five repetitions, first-attempt-only release gate
- Consumes: two-turn catalog, client adapters, evidence recorder, mechanical scorer

- [ ] **Step 1: Write exact-matrix tests**

```python
def test_release_matrix_has_no_retry_substitution(self):
    schedule = build_release_schedule(CASES, repetitions=5)
    self.assertEqual(len(schedule), len(CASES) * 5)
    self.assertTrue(all(slot.attempt == 1 for slot in schedule))
    self.assertEqual(len({slot.key for slot in schedule}), len(schedule))
```

- [ ] **Step 2: Run and observe the missing controller**

Run: `python3 -m unittest -q tests.test_v06_release_matrix`

- [ ] **Step 3: Implement probe, smoke, and full phases**

`--probe-only` records client/auth/plugin state. `--smoke` runs one positive, one negative, and one two-turn case per client. `--full` requires the smoke manifest, runs all selected cases five times, and refuses existing unsealed output, duplicate keys, changed payload identity, or retry replacement.

- [ ] **Step 4: Verify with fake adapters**

Run: `python3 -m unittest -q tests.test_v06_release_matrix tests.test_eval_harness_cli tests.test_eval_harness_evidence tests.test_eval_harness_scoring`

- [ ] **Step 5: Commit**

```bash
git add evals/v0.6-release-cases.json scripts/run-v06-release-matrix.py tests/test_v06_release_matrix.py evals/harness/run.py evals/harness/reporting.py
git commit -m "eval: enforce v0.6 five-run release matrix"
```

### Task 6: UX/evidence deterministic review gate

**Files:**
- Verify only: Tasks 1-5 changes

**Interfaces:**
- Consumes: locale renderers and release-matrix controller
- Produces: deterministic green candidate ready for live runs

- [ ] **Step 1: Run quality and complete deterministic tests**

Run: `.quality-venv/bin/python scripts/run-quality-gates.py`

Run: `python3 -m unittest -q tests.test_fast_scan_renderer tests.test_impact_renderer_locale tests.test_v06_release_matrix`

- [ ] **Step 2: Request independent UX, evidence, and security reviews**

UX review compares all three locales and modes. Evidence review verifies first-attempt selection and complete manifests. Security review attacks session IDs, scratch paths, transcript secrets, and quarantine boundaries.

- [ ] **Step 3: Commit review fixes**

```bash
git add -u
git commit -m "fix: close v0.6 ux and evidence review findings"
```

### Task 7: Execute and seal live Codex and Claude matrices

**Files:**
- Create at runtime: `evals/results/v0.6-release/`
- Create: `evals/results/v0.6-release/report.md`
- Create: `evals/results/v0.6-release/manifest.sha256`

**Interfaces:**
- Consumes: authenticated Codex and Claude CLIs, release-candidate payload, five-run controller
- Produces: sealed raw evidence and pass/block release decision

- [ ] **Step 1: Record environment probes**

Run: `python3 scripts/run-v06-release-matrix.py --probe-only --client codex --output evals/results/v0.6-release/codex`

Run: `python3 scripts/run-v06-release-matrix.py --probe-only --client claude --output evals/results/v0.6-release/claude`

Expected: authenticated clients, exact plugin payload digest, selected model metadata, and sealed probe manifests.

- [ ] **Step 2: Run smoke checkpoints**

Run one smoke per client. Stop and report if either smoke has a runtime, activation, tool-order, score, or evidence failure.

- [ ] **Step 3: Run five first-attempt repetitions**

Run: `python3 scripts/run-v06-release-matrix.py --full --client codex --repetitions 5 --output evals/results/v0.6-release/codex`

Run: `python3 scripts/run-v06-release-matrix.py --full --client claude --repetitions 5 --output evals/results/v0.6-release/claude`

- [ ] **Step 4: Seal and verify evidence**

Run the secret scanner, manifest verifier, score verifier, controller-evidence verifier, and adjudication validator. Any failure leaves release status blocked and prevents the release plan.

- [ ] **Step 5: Commit only verified evidence**

```bash
git add evals/results/v0.6-release
git commit -m "eval: seal v0.6 client release evidence"
```
