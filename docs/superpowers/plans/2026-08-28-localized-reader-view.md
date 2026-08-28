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
