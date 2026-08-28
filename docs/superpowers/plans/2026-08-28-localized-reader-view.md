# Localized Reader View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a complete, localized, vertically structured reader view without changing canonical report rendering.

**Architecture:** `impact_renderer.py` gains a separate `render_reader_view(state, locale)` boundary that consumes the validated canonical state. It renders every state section and row as headings plus labeled lines, while `render_markdown` remains byte-compatible for storage, parsing, validation, and lineage.

**Tech Stack:** Python 3, `unittest`, existing `compact_state.State` validation.

**Spec:** `.requirements-impact-refiner/reports/RPT-002/revision-0001.md`

## Global Constraints

- Human-facing headings and labels use the requested locale; Korean is supported in this increment and unsupported locales fall back to English.
- IDs, code/symbol text, paths, enum values, SHA-256 values, and workflow markers remain unchanged.
- The reader view contains every canonical section and every row; it is not a compact summary.
- The reader view uses no Markdown tables.
- `render_markdown` output remains byte-identical for the existing fixture.
- Root and packaged skill renderer files remain byte-identical.

---

### Task 1: Complete localized reader-view renderer

**Files:**
- Modify: `tests/test_impact_renderer.py`
- Modify: `scripts/impact_renderer.py`
- Modify: `skills/requirements-impact-refiner/scripts/impact_renderer.py`

**Interfaces:**
- Consumes: `render_reader_view(state: Mapping[str, object], locale: str = "en") -> str`
- Produces: A validated, complete reader-view Markdown string with localized human labels and preserved machine literals.

- [x] **Step 1: Write the failing Korean reader-view test**

```python
def test_reader_view_localizes_labels_preserves_literals_and_avoids_tables(self):
    state = self.fixture()
    rendered = RENDERER.render_reader_view(state, "ko")

    self.assertTrue(rendered.startswith("# 요구사항 영향 보고서\n"))
    self.assertIn("## 보고서 상태", rendered)
    self.assertIn("### 영향 IMP-001", rendered)
    self.assertIn("- 심각도: critical", rendered)
    self.assertIn("superpowers:after-approved-brainstorming", rendered)
    self.assertNotIn("| ---", rendered)
    self.assertEqual(rendered.count("### 영향 "), len(state["summary"]))
```

- [x] **Step 2: Run the test and confirm the missing API failure**

Run: `python3 -m unittest tests/test_impact_renderer.py -k test_reader_view_localizes_labels_preserves_literals_and_avoids_tables`

Expected: FAIL because `impact_renderer` has no `render_reader_view` attribute.

- [x] **Step 3: Implement the minimal complete renderer**

Add locale label dictionaries, a label lookup with English fallback, scalar/list formatting helpers, and `render_reader_view`. Build the output from all canonical state collections in this exact order: report, summary, original requirement, refined requirement, current behavior, preserved invariants, impacts, decision, delta, history, criteria, unresolved, scope, handoff. Use headings and `- label: value` lines only; never call `_table`.

- [x] **Step 4: Run the focused reader-view test**

Run: `python3 -m unittest tests/test_impact_renderer.py -k test_reader_view_localizes_labels_preserves_literals_and_avoids_tables`

Expected: PASS.

- [x] **Step 5: Add completeness and canonical-regression tests**

```python
def test_reader_view_contains_every_canonical_item(self):
    state = self.fixture()
    rendered = RENDERER.render_reader_view(state, "ko")
    for collection in ("summary", "current_behavior", "impacts", "criteria", "scope"):
        for row in state[collection]:
            identifier = row.get("id") or row.get("impact_id")
            if identifier:
                self.assertIn(identifier, rendered)

def test_reader_view_does_not_change_canonical_markdown(self):
    state = self.fixture()
    RENDERER.render_reader_view(state, "ko")
    self.assertEqual(
        RENDERER.render_markdown(state),
        (FIXTURES / "compact-state-post-decision.md").read_text(encoding="utf-8"),
    )
```

- [x] **Step 6: Run renderer and distribution regression tests**

Run: `python3 -m unittest tests/test_impact_renderer.py tests/test_packaging.py`

Expected: PASS with root and packaged renderer parity intact.

- [x] **Step 7: Review and stage for a user-requested commit**

Run: `git diff --check && git status --short`

Expected: only this plan, the two renderer mirrors, and renderer tests are changed. Do not commit until the user requests it.

### Task 2: Connect newly finalized full reports

**Files:**
- Modify: `tests/test_rir_finalize.py`
- Modify: `tests/fixtures/rir-controller-facade-v05.json`
- Modify: `scripts/impact_renderer.py`
- Modify: `scripts/rir_finalize.py`
- Modify: `skills/requirements-impact-refiner/scripts/impact_renderer.py`
- Modify: `skills/requirements-impact-refiner/scripts/rir_finalize.py`

**Interfaces:**
- Consumes: `render_reader_view(state: Mapping[str, object], locale: str | None = None) -> str`
- Produces: Full-delivery `FinalizeResult.display_text` in the original request language while retaining canonical Markdown at `FinalizeResult.markdown_path`.

- [x] **Step 1: Write the failing finalize boundary test**

```python
def test_full_finalize_returns_localized_reader_view_and_keeps_canonical_artifact(self):
    finalize = self.finalize()
    draft = self.begin("모든 프로젝트의 편집 권한 영향을 검토해줘.")

    result = finalize.finalize_refinement(self.request(draft))

    self.assertEqual(result.delivery, "full")
    self.assertTrue(result.display_text.startswith("# 요구사항 영향 보고서\n"))
    self.assertFalse(any(line.startswith("|") for line in result.display_text.splitlines()))
    self.assertTrue(result.markdown_path.read_text(encoding="utf-8").startswith(
        "# Requirements Impact Report\n"
    ))
```

- [x] **Step 2: Run the test and confirm canonical display is still returned**

Run: `python3 -m unittest tests/test_rir_finalize.py -k test_full_finalize_returns_localized_reader_view_and_keeps_canonical_artifact`

Expected: FAIL because `display_text` starts with the canonical English report title.

- [x] **Step 3: Add request-locale detection and the finalize runtime operation**

Change `render_reader_view` so omitted locale is derived from `state["original_requirement"]["request"]`, recognizing Hangul as `ko` and otherwise falling back to `en`. Add `render_reader_view` to the finalize renderer contract, dependency validation, runtime key allowlist, default runtime, and full-delivery display branch. Keep compact delivery and `publish_revision` unchanged.

- [x] **Step 4: Synchronize packaged skill mirrors**

Copy the two root implementation files to their existing packaged mirrors and verify each pair with `cmp -s`.

- [x] **Step 5: Run focused and full regression verification**

Run: `python3 -m unittest tests/test_impact_renderer.py tests/test_rir_finalize.py tests/test_packaging.py`

Expected: PASS.

Run: `.quality-venv/bin/python scripts/run-quality-gates.py`

Expected: all quality checks and the full test suite pass.
