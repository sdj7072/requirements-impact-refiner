# Git Index Output Fail-Soft Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow final impact-report publication when a valid large Git metadata stream exceeds the current byte bound, without weakening malformed-output fail-closed behavior.

**Architecture:** Introduce a narrow `GitOutputLimitExceeded` subtype at the bounded Git reader. `probe_git_baseline` converts only that subtype to an unverified baseline result; every other `UnsafeGitOutput` continues to propagate.

**Tech Stack:** Python 3, standard library `unittest`, existing report-context and finalize runtime.

**Spec:** `.requirements-impact-refiner/reports/RPT-003/revision-0001.md`

## Global Constraints

- Keep `MAX_GIT_OUTPUT_BYTES` at 256 KiB in this increment.
- Do not modify `rir_previous.py` or redesign Git output streaming.
- Never record `baseline_clean=true` or `source_inventory_git_tracked_only=true` after an output-limit event.
- Preserve fail-closed behavior for malformed, unsafe, non-UTF-8, hidden, or structurally invalid Git output.
- Root and packaged `rir_report_context.py` files must remain byte-identical.
- Existing uncommitted report-delivery changes are outside this task and must remain untouched.

---

### Task 1: Typed output-limit degradation

**Files:**
- Modify: `tests/test_rir_report_context.py`
- Modify: `scripts/rir_report_context.py`
- Modify: `skills/requirements-impact-refiner/scripts/rir_report_context.py`

**Interfaces:**
- Produces: `GitOutputLimitExceeded(UnsafeGitOutput)`.
- Changes: `probe_git_baseline(root)` returns `(commit, False)` for that subtype only.
- Preserves: all other `UnsafeGitOutput` exceptions propagate.

- [x] **Step 1: Write the failing finalize-boundary test**

```python
def test_git_output_limit_publishes_unverified_context_without_false_clean(self):
    self.configure_graph(False)
    draft = self.begin("Large Git index still publishes a report.")
    request = self.finalize_request(draft)

    with mock.patch.object(
        CONTEXT,
        "_capture_repository_git_state",
        side_effect=CONTEXT.GitOutputLimitExceeded("bounded Git output exceeded"),
    ):
        result = FINALIZE.finalize_refinement(request)

    context = CONTEXT.load_report_context(self.root, result.report_id, result.revision)
    self.assertEqual(result.status, "published")
    self.assertIsNotNone(context.baseline_commit)
    self.assertFalse(context.baseline_clean)
    self.assertFalse(context.source_inventory_git_tracked_only)
```

- [x] **Step 2: Run the focused test and confirm the typed exception is missing**

Run: `python3 -m unittest tests/test_rir_report_context.py -k test_git_output_limit_publishes_unverified_context_without_false_clean`

Expected: ERROR because `GitOutputLimitExceeded` does not exist.

- [x] **Step 3: Implement the minimal typed branch**

Define `GitOutputLimitExceeded` as a direct subclass of `UnsafeGitOutput`. Raise it only when `_run_git` receives more than `maximum_output` bytes. Catch it before the general `UnsafeGitOutput` branch in `probe_git_baseline` and return `(commit, False)`.

- [x] **Step 4: Run security and publication regression tests**

Run: `python3 -m unittest tests/test_rir_report_context.py -k 'git_output_limit or unsafe_git_output or publishes_unavailable_context'`

Expected: the new publication test and existing unsafe fail-closed tests pass.

- [x] **Step 5: Synchronize the packaged mirror and run full verification**

Copy the root report-context module to its packaged mirror and verify with `cmp -s`.

Run: `python3 -m unittest tests/test_rir_report_context.py tests/test_rir_finalize.py tests/test_packaging.py`

Run: `.quality-venv/bin/python scripts/run-quality-gates.py`

Expected: all checks pass.

- [x] **Step 6: Review without committing**

Run: `git diff --check && git status --short`

Expected: this task changes only the new plan, the two report-context mirrors, and report-context tests in addition to the pre-existing uncommitted delivery files. Do not commit until requested.

### Task 2: Dedicated Git index output bound

**Files:**
- Modify: `tests/test_rir_report_context.py`
- Modify: `tests/test_rir_previous.py`
- Modify: `scripts/rir_report_context.py`
- Modify: `scripts/rir_previous.py`
- Modify: `skills/requirements-impact-refiner/scripts/rir_report_context.py`
- Modify: `skills/requirements-impact-refiner/scripts/rir_previous.py`

**Interfaces:**
- Produces: `MAX_GIT_INDEX_OUTPUT_BYTES = 4 * 1024 * 1024` in both Git-proof modules.
- Changes: report-context `ls-files -v/-s` and previous-report `ls-files -s -v` use the dedicated bound.
- Preserves: all other Git commands and control files remain limited by `MAX_GIT_OUTPUT_BYTES = 256 * 1024`.

- [x] **Step 1: Write failing report-context index-bound test**

Provide `_capture_repository_git_state` with valid synthetic Git responses whose index and index-flags payloads exceed 256 KiB but are below 4 MiB. The dependency raises `GitOutputLimitExceeded` unless the call supplies the dedicated index bound. Assert capture succeeds and retains both payloads.

- [x] **Step 2: Write failing previous-lookup index-bound test**

Provide `_index_flags_snapshot` with a valid synthetic index-flags payload above 256 KiB. Its Git runner rejects a maximum below the payload size. Assert the snapshot returns the complete payload.

- [x] **Step 3: Run both tests and confirm the dedicated bound is missing**

Run each new test independently with `python3 -m unittest ... -k TEST_NAME`.

Expected: ERROR from the existing 256 KiB Git output limit or missing runner parameter.

- [x] **Step 4: Implement the dedicated bound only at index call sites**

Add the 4 MiB constant. Pass it to report-context index/index-flags `_git_bytes` calls. Extend previous `_run_git_command` with a keyword-only `maximum_output` defaulting to 256 KiB, use that value in its bounded read, and pass 4 MiB only from `_index_flags_snapshot`.

- [x] **Step 5: Synchronize mirrors and run focused verification**

Run: `python3 -m unittest tests/test_rir_report_context.py tests/test_rir_previous.py tests/test_packaging.py`

Expected: all tests pass and both root/mirror pairs are byte-identical.

- [x] **Step 6: Run full verification and review without committing**

Run: `.quality-venv/bin/python scripts/run-quality-gates.py`

Run: `git diff --check && git status --short`

Expected: all gates pass; no unrelated files beyond the pre-existing delivery changes and these two scoped tasks are modified.
