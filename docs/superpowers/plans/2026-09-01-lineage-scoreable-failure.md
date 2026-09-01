# Lineage Scoreable Failure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve strict evidence-integrity checks while treating a valid lineage report that remains at revision 1 as a mechanically scoreable behavior failure.

**Architecture:** Keep canonical pointer, state, Markdown, UTF-8, and digest validation inside `_captured_canonical_report`. Move the “did not publish a new revision” outcome into normal mechanical scoring as an explicit finding; a compact `first.final.txt` is continuity evidence, not a canonical predecessor when persisted report state exists.

**Tech Stack:** Python 3, `unittest`, existing evaluation harness.

**Spec:** `.requirements-impact-refiner/reports/RPT-006/revision-0001.md`

## Global Constraints

- Do not modify any file under `evals/results/installed-v0.6.2-full-85/raw/`.
- Invalid pointer schemas, state/Markdown mismatches, digest mismatches, unsafe paths, and invalid UTF-8 remain invalid scoring evidence.
- Resume the sealed 85-run batch without executing new model turns.

---

### Task 1: Score missing lineage revision as behavior failure

**Files:**
- Modify: `evals/harness/run.py`
- Test: `tests/test_eval_harness_cli.py`

**Interfaces:**
- Consumes: `_captured_canonical_report(raw_root, attempt_path, lineage)` and `score_mechanical(case, result, previous_bytes)`.
- Produces: `_score_selected_attempt(...) -> (MechanicalScore, True, digests)` for a structurally valid revision-1 lineage artifact.

- [ ] **Step 1: Write the failing regression test**

Add a test that records valid revision-1 canonical report files for a lineage case plus immutable `first.final.txt` and `second.final.txt`, then asserts that `_score_selected_attempt` returns trusted evidence and a failed mechanical score.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python3 -m unittest tests.test_eval_harness_cli.EvalHarnessCliTests.test_lineage_revision_one_is_a_scoreable_behavior_failure -v`

Expected: FAIL because `trusted` is currently `False` with `captured lineage report did not publish a new revision`.

- [ ] **Step 3: Implement the minimal classification change**

Remove the revision-count exception from `_captured_canonical_report`. In `_score_selected_attempt`, when a lineage capture has no canonical predecessor, score the valid revision-1 canonical Markdown without predecessor bytes and append the explicit `captured lineage report did not publish a new revision` finding.

- [ ] **Step 4: Verify GREEN and integrity regressions**

Run the focused test, then `python3 -m unittest tests.test_eval_harness_cli -v`.

Expected: PASS. Existing tampered-state, symlink, detached-output, and non-UTF-8 predecessor tests remain green.

- [ ] **Step 5: Resume and verify the complete batch**

Run the existing `installed-superpowers` command against `evals/results/installed-v0.6.2-full-85`, then verify 85 runs, 85 mechanical scores, `report.md`, and zero manifest issues. Confirm raw file digests are unchanged from the pre-change manifest.
