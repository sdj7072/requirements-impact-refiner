# Table Report Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make new RIR full reports display the existing canonical Markdown tables by default while preserving narrative display as an explicit compatibility option.

**Architecture:** Keep `render_markdown`, persisted report bytes, pointer SHA, and lineage unchanged. Add `report_layout` to resolved settings and a `render_full_view` dispatcher: new resolved states default to `table`; legacy states without the optional field and explicit `narrative` use the current reader view. Full finalize and previous-report display call the dispatcher; compact delivery remains unchanged.

**Tech Stack:** Python 3 standard library, JSON settings/schema, Markdown renderer, `unittest`.

**Spec:** `.requirements-impact-refiner/reports/RPT-008/revision-0001.md`

## Global Constraints

- Do not modify `render_markdown` output bytes or historical revision files.
- Do not change report pointer, SHA, compact-state schema version, or P1 Delta semantics.
- Preserve legacy states without `report_layout` as narrative display.
- Mirror every runtime/script/schema change into the packaged skill payload.

---

### Task 1: Resolve and validate report layout settings

**Files:**
- Modify: `scripts/resolve-settings.py`
- Modify: `skills/requirements-impact-refiner/scripts/resolve-settings.py`
- Modify: `scripts/compact_state.py`
- Modify: `skills/requirements-impact-refiner/scripts/compact_state.py`
- Modify: `schemas/compact-state.schema.json`
- Modify: packaged schema mirror if present
- Test: `tests/test_presentation_settings.py`
- Test: `tests/test_compact_state.py`

- [ ] Add failing tests for new-state default `table/default`, repository `narrative/repository`, CLI override, invalid values, optional legacy state, and paired field validation.
- [ ] Add `REPORT_LAYOUTS = ("table", "narrative")`, config allow-list support, CLI `--report-layout`, and resolved provenance fields.
- [ ] Permit optional `report_layout` plus `report_layout_source` in state/schema; require the pair when either is present.
- [ ] Run settings and compact-state modules.

### Task 2: Add a full-display layout dispatcher

**Files:**
- Modify: `scripts/impact_renderer.py`
- Modify: `skills/requirements-impact-refiner/scripts/impact_renderer.py`
- Test: `tests/test_impact_renderer.py`

- [ ] Add failing tests proving table full view equals `render_markdown`, explicit narrative equals current reader bytes, legacy missing field stays narrative, and canonical Markdown is identical across layouts.
- [ ] Implement `render_full_view(state, locale=None)` without changing either underlying renderer.
- [ ] Run renderer tests and byte fixtures.

### Task 3: Route finalize and previous-report display

**Files:**
- Modify: `scripts/rir_finalize.py`
- Modify: packaged mirror
- Modify: `scripts/rir_previous_renderer.py`
- Modify: packaged mirror
- Test: `tests/test_rir_finalize.py`
- Test: `tests/test_rir_previous.py`
- Test: `tests/test_rir_mcp_server.py`

- [ ] Add failing full-delivery tests for table output, narrative compatibility, legacy previous display, and terminal exactness.
- [ ] Extend renderer dependency contracts with `render_full_view` and route full display through it.
- [ ] Keep compact delivery on `render_compact` and persisted publication on `render_markdown`.
- [ ] Run finalize, previous, MCP, storage, and lineage tests.

### Task 4: Document, verify, push, and reinstall

**Files:**
- Modify: `README.md`, `README.ko.md`, `README.ja.md` only where presentation settings are documented.
- Test: packaging, documentation, quality, and full suite.

- [ ] Document `report_layout` default and narrative opt-in.
- [ ] Run focused tests, mirror checks, full quality gates, and diff review confirming P1 files are unchanged.
- [ ] Commit and push main, upgrade the Git marketplace snapshot, reinstall `0.6.2-dev`, and verify installed table markers.
- [ ] Run one fresh report canary showing Markdown tables in the selected final.
