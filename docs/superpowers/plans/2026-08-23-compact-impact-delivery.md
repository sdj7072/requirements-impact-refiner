# Compact Impact Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make compact, persisted, validated impact delivery the default while preserving every impact and the existing canonical Markdown/SHA lineage contract.

**Architecture:** The agent authors a compact JSON state. Standard-library Python validates the state, renders deterministic canonical Markdown, stores append-only revision artifacts behind an atomic current pointer, and renders a short chat view from the same state. Existing Markdown-only reports remain valid predecessors and `delivery: full` preserves the current inline behavior.

**Tech Stack:** Python 3 standard library, JSON Schema as a distribution contract, Markdown, `unittest`, Agent Skills, Codex/Claude plugin manifests, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-23-compact-impact-delivery-design.md`

## Global Constraints

- No new runtime dependencies; all validators, renderers, and storage tools use the Python standard library.
- `audience` remains `simple`, `balanced`, or `technical`; `delivery` is `compact` or `full` and defaults to `compact`.
- Current-request override beats repository configuration, which beats defaults, independently for audience and delivery.
- Compact delivery never omits, merges, adds, accepts, resolves, or supersedes an impact independently of canonical state.
- Canonical Markdown and exact predecessor Markdown SHA-256 remain the lineage authority.
- Existing 0.3.2 Markdown-only reports remain valid.
- Revision artifacts are append-only; only `current.json` is atomically replaced.
- File persistence stays inside `.requirements-impact-refiner/reports/`, rejects traversal and external symlinks, and never modifies `.gitignore`.
- If persistence is unavailable, return the full canonical report inline and disclose that the fast path is unavailable.
- Canonical skill resources and plugin-root fallback mirrors remain byte-identical.
- Do not begin the 85-run evaluation until the six-case installed-plugin smoke gate passes.
- Do not tag or publish a release until deterministic tests, smoke evidence, documentation, and independent review pass.

---

### Task 1: Delivery Configuration Contract

**Files:**
- Modify: `skills/requirements-impact-refiner/scripts/resolve-settings.py`
- Modify: `scripts/resolve-settings.py`
- Modify: `skills/requirements-impact-refiner/references/presentation-modes.md`
- Modify: `references/presentation-modes.md`
- Modify: `tests/test_presentation_settings.py`

**Interfaces:**
- Consumes: repository root and optional current-request audience/delivery overrides.
- Produces: `resolve(project_root: Path, audience_override: str | None, delivery_override: str | None) -> dict[str, str]` returning `audience`, `audience_source`, `delivery`, and `delivery_source`.

- [ ] **Step 1: Write failing configuration tests**

Add literal behavior cases to `tests/test_presentation_settings.py`:

```python
def test_missing_config_defaults_to_balanced_compact(self):
    with tempfile.TemporaryDirectory() as directory:
        result = self.run_resolver(directory)
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(json.loads(result.stdout), {
        "audience": "balanced",
        "audience_source": "default",
        "delivery": "compact",
        "delivery_source": "default",
    })

def test_request_overrides_each_repository_setting_independently(self):
    with tempfile.TemporaryDirectory() as directory:
        Path(directory, ".requirements-impact-refiner.json").write_text(
            '{"audience":"simple","delivery":"full"}\n', encoding="utf-8"
        )
        result = self.run_resolver(
            directory, "--audience", "technical", "--delivery", "compact"
        )
    self.assertEqual(json.loads(result.stdout), {
        "audience": "technical",
        "audience_source": "request",
        "delivery": "compact",
        "delivery_source": "request",
    })

def test_invalid_delivery_is_disclosed_and_rejected(self):
    with tempfile.TemporaryDirectory() as directory:
        Path(directory, ".requirements-impact-refiner.json").write_text(
            '{"delivery":"shortish"}\n', encoding="utf-8"
        )
        result = self.run_resolver(directory)
    self.assertEqual(result.returncode, 2)
    self.assertIn("delivery must be one of: compact, full", result.stderr)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task1-red python3 -m unittest tests.test_presentation_settings -v
```

Expected: failures because `--delivery`, delivery defaults, and independent source fields do not exist.

- [ ] **Step 3: Implement independent setting resolution**

Update the canonical resolver with these exact public constants and signature:

```python
AUDIENCES = ("simple", "balanced", "technical")
DELIVERIES = ("compact", "full")

def resolve(
    project_root: Path,
    audience_override: str | None,
    delivery_override: str | None,
) -> dict[str, str]:
    config = load_repository_config(project_root)
    audience, audience_source = resolve_value(
        "audience", audience_override, config, AUDIENCES, "balanced"
    )
    delivery, delivery_source = resolve_value(
        "delivery", delivery_override, config, DELIVERIES, "compact"
    )
    return {
        "audience": audience,
        "audience_source": audience_source,
        "delivery": delivery,
        "delivery_source": delivery_source,
    }
```

`load_repository_config()` accepts only `audience` and `delivery`. `resolve_value()` labels an override `request`, a configured value `repository`, and a default `default`. Add `--delivery` with `choices=DELIVERIES`.

- [ ] **Step 4: Refresh the fallback mirror and documentation**

Copy the canonical resolver and presentation reference byte-for-byte to their root mirrors. Document the two independent settings and preserve invalid-setting disclosure.

- [ ] **Step 5: Verify GREEN and mirror parity**

Run:

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task1-green python3 -m unittest tests.test_presentation_settings tests.test_packaging.PackagingTest.test_plugin_root_resource_fallback_mirrors_are_complete_and_identical -v
cmp skills/requirements-impact-refiner/scripts/resolve-settings.py scripts/resolve-settings.py
cmp skills/requirements-impact-refiner/references/presentation-modes.md references/presentation-modes.md
```

Expected: all tests pass and both `cmp` commands exit 0.

- [ ] **Step 6: Commit**

```sh
git add skills/requirements-impact-refiner/scripts/resolve-settings.py scripts/resolve-settings.py skills/requirements-impact-refiner/references/presentation-modes.md references/presentation-modes.md tests/test_presentation_settings.py
git commit -m "feat: add compact delivery setting"
```

---

### Task 2: Compact State Schema and Semantic Validator

**Files:**
- Create: `skills/requirements-impact-refiner/schemas/compact-state.schema.json`
- Create: `skills/requirements-impact-refiner/scripts/compact_state.py`
- Create: `schemas/compact-state.schema.json`
- Create: `scripts/compact_state.py`
- Create: `tests/fixtures/compact-state-pre-decision.json`
- Create: `tests/fixtures/compact-state-post-decision.json`
- Create: `tests/test_compact_state.py`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Consumes: decoded JSON objects.
- Produces: `validate_state(value: object) -> list[str]`, `load_state_bytes(raw: bytes) -> tuple[dict[str, object] | None, list[str]]`, and canonical enums/constants shared with the renderer.

- [ ] **Step 1: Write failing valid-state and malformed-state tests**

Create literal pre/post fixtures containing report metadata, settings, requirements, invariants, impacts, phase-specific decision data, Delta, history, criteria, unresolved items, scope, handoff, and summary fields.

Add tests:

```python
def test_complete_pre_and_post_states_are_valid(self):
    for name in ("compact-state-pre-decision.json", "compact-state-post-decision.json"):
        value = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        self.assertEqual(COMPACT.validate_state(value), [], name)

def test_every_impact_requires_exactly_one_matching_summary(self):
    value = self.fixture("compact-state-post-decision.json")
    value["summary"][0]["severity"] = "low"
    value["summary"].append(dict(value["summary"][0]))
    errors = COMPACT.validate_state(value)
    self.assertIn("summary IMP-001 severity low disagrees with impact critical", errors)
    self.assertIn("summary lists IMP-001 more than once", errors)

def test_relationships_and_phase_rules_match_markdown_contract(self):
    value = self.fixture("compact-state-pre-decision.json")
    value["impacts"][0]["decision"] = ["DEC-001"]
    value["decisions"] = [{"id": "DEC-001", "choice": "invented"}]
    errors = COMPACT.validate_state(value)
    self.assertIn("pre-decision state forbids decisions", errors)
```

Cover unknown keys, non-UTF-8 bytes, malformed IDs, enums, dangling references, duplicate definitions, missing evidence basis, future AC used as verified evidence, unresolved reconciliation, nine Delta categories, revision-1 `new`, and decision requirements for `accepted`.

- [ ] **Step 2: Run tests and verify RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task2-red python3 -m unittest tests.test_compact_state -v
```

Expected: import/file failures because the state module, schema, and fixtures do not exist.

- [ ] **Step 3: Define the distribution schema**

The schema declares `schema_version: 1`, uses `additionalProperties: false` at every object boundary, and requires these top-level keys:

```json
[
  "schema_version", "report", "settings", "original_requirement",
  "refined_requirement", "current_behavior", "preserved_invariants",
  "impacts", "decision_needed", "decisions", "delta", "history",
  "criteria", "unresolved", "scope", "handoff", "summary"
]
```

Use lowercase JSON property names and canonical string enums from the spec. The schema is a published contract; standard-library Python performs runtime validation.

- [ ] **Step 4: Implement structural and semantic validation**

In `compact_state.py`, expose literal sets from the Markdown domain module and return deterministic sorted errors. Use helpers with these signatures:

```python
def validate_structure(value: object) -> list[str]: ...
def validate_definitions(state: Mapping[str, object]) -> list[str]: ...
def validate_relationships(state: Mapping[str, object]) -> list[str]: ...
def validate_phase(state: Mapping[str, object]) -> list[str]: ...
def validate_delta(state: Mapping[str, object]) -> list[str]: ...
def validate_summary(state: Mapping[str, object]) -> list[str]: ...
def validate_state(value: object) -> list[str]:
    errors = validate_structure(value)
    if errors:
        return sorted(set(errors))
    validators = (
        validate_definitions, validate_relationships, validate_phase,
        validate_delta, validate_summary,
    )
    return sorted({error for validator in validators for error in validator(value)})
```

Do not import third-party schema libraries. The JSON schema and Python validator must agree through tests that mutate every required key and enum.

- [ ] **Step 5: Refresh mirrors and packaging inventory**

Create byte-identical root mirrors. Extend the existing mirror completeness test; do not special-case the new canonical resources as root-only files.

- [ ] **Step 6: Verify GREEN**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task2-green python3 -m unittest tests.test_compact_state tests.test_packaging -v
python3 -m json.tool skills/requirements-impact-refiner/schemas/compact-state.schema.json >/dev/null
cmp skills/requirements-impact-refiner/scripts/compact_state.py scripts/compact_state.py
cmp skills/requirements-impact-refiner/schemas/compact-state.schema.json schemas/compact-state.schema.json
```

Expected: tests and JSON parsing pass; mirrors match.

- [ ] **Step 7: Commit**

```sh
git add skills/requirements-impact-refiner/schemas/compact-state.schema.json skills/requirements-impact-refiner/scripts/compact_state.py schemas/compact-state.schema.json scripts/compact_state.py tests/fixtures/compact-state-pre-decision.json tests/fixtures/compact-state-post-decision.json tests/test_compact_state.py tests/test_packaging.py
git commit -m "feat: validate compact impact state"
```

---

### Task 3: Deterministic Markdown and Compact Renderers

**Files:**
- Create: `skills/requirements-impact-refiner/scripts/impact_renderer.py`
- Create: `skills/requirements-impact-refiner/scripts/render-impact-report.py`
- Create: `scripts/impact_renderer.py`
- Create: `scripts/render-impact-report.py`
- Create: `tests/fixtures/compact-state-post-decision.md`
- Create: `tests/test_impact_renderer.py`
- Modify: `tests/test_validate_impact_report.py`

**Interfaces:**
- Consumes: a state that passes `compact_state.validate_state()`.
- Produces: `render_markdown(state: Mapping[str, object]) -> str`, `render_compact(state: Mapping[str, object]) -> str`, `state_from_markdown(text: str) -> tuple[dict[str, object] | None, list[str]]`, and a CLI that writes neither input nor output unless `--output` is explicit.

- [ ] **Step 1: Write failing deterministic-render tests**

```python
def test_markdown_render_is_byte_deterministic_and_validator_clean(self):
    state = self.fixture("compact-state-post-decision.json")
    first = RENDERER.render_markdown(state)
    second = RENDERER.render_markdown(state)
    self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))
    self.assertEqual(first, (FIXTURES / "compact-state-post-decision.md").read_text())
    self.assertEqual(VALIDATOR.validate_report(first, require_summary=True), [])

def test_compact_render_names_every_impact_once_and_stays_bounded(self):
    state = self.fixture("compact-state-post-decision.json")
    rendered = RENDERER.render_compact(state)
    for impact in state["impacts"]:
        self.assertEqual(rendered.count(impact["id"]), 1)
    self.assertLessEqual(len(rendered.split()), 450)
    self.assertIn("Full report:", rendered)

def test_existing_markdown_converts_without_semantic_loss(self):
    markdown = (FIXTURES / "compact-state-post-decision.md").read_text()
    state, errors = RENDERER.state_from_markdown(markdown)
    self.assertEqual(errors, [])
    self.assertEqual(
        semantic_tables(RENDERER.render_markdown(state)), semantic_tables(markdown)
    )
```

Define the test helper independently of renderer implementation:

```python
def semantic_tables(text):
    parsed, errors = DOMAIN.parse_report(text)
    if errors:
        raise AssertionError(errors)
    return parsed.tables
```

Also test Markdown escaping for pipes, backticks, newlines, non-ASCII text, and stable numeric ID ordering.

- [ ] **Step 2: Run tests and verify RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task3-red python3 -m unittest tests.test_impact_renderer -v
```

Expected: renderer imports and golden fixture are missing.

- [ ] **Step 3: Implement canonical Markdown rendering**

Build sections from fixed functions rather than a user-provided section list:

```python
def render_markdown(state: Mapping[str, object]) -> str:
    errors = compact_state.validate_state(state)
    if errors:
        raise ValueError("; ".join(errors))
    sections = [
        render_report_state(state), render_summary(state),
        render_original_requirement(state), render_refined_requirement(state),
        render_current_behavior(state), render_preserved_invariants(state),
        render_impact_ledger(state), render_phase_decision(state),
        render_delta(state), render_history(state), render_criteria(state),
        render_unresolved(state), render_scope(state), render_handoff(state),
    ]
    return "# Requirements Impact Report\n\n" + "\n\n".join(sections) + "\n"
```

Escape cell content deterministically. Forbid embedded newlines in state strings at validation time or replace them with `<br>` in one documented, tested way.

- [ ] **Step 4: Implement compact rendering and compatibility conversion**

Compact rendering uses the state's summary, highest-severity remaining risks, one phase-specific decision block, validation status, and artifact paths. `state_from_markdown()` uses the existing `parse_report()` tables and rejects ambiguous duplicate sections before conversion.

- [ ] **Step 5: Implement the read-only renderer CLI**

CLI contract:

```sh
python3 render-impact-report.py STATE.json --format markdown
python3 render-impact-report.py STATE.json --format compact
python3 render-impact-report.py STATE.json --format markdown --output REPORT.md
python3 render-impact-report.py --from-markdown REPORT.md --output STATE.json
```

Exit 0 on valid render, 1 on state/report validation failure, and 2 on invocation or file-decoding errors. Do not overwrite an existing `--output` path unless `--force` is supplied.

- [ ] **Step 6: Refresh mirrors and verify GREEN**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task3-green python3 -m unittest tests.test_impact_renderer tests.test_validate_impact_report -v
cmp skills/requirements-impact-refiner/scripts/impact_renderer.py scripts/impact_renderer.py
cmp skills/requirements-impact-refiner/scripts/render-impact-report.py scripts/render-impact-report.py
```

Expected: focused tests pass and mirrors match.

- [ ] **Step 7: Commit**

```sh
git add skills/requirements-impact-refiner/scripts/impact_renderer.py skills/requirements-impact-refiner/scripts/render-impact-report.py scripts/impact_renderer.py scripts/render-impact-report.py tests/fixtures/compact-state-post-decision.md tests/test_impact_renderer.py tests/test_validate_impact_report.py
git commit -m "feat: render compact and canonical impact reports"
```

---

### Task 4: Append-Only Report Store and Exact Lineage

**Files:**
- Create: `skills/requirements-impact-refiner/scripts/report_store.py`
- Create: `skills/requirements-impact-refiner/scripts/publish-impact-report.py`
- Create: `scripts/report_store.py`
- Create: `scripts/publish-impact-report.py`
- Create: `tests/test_report_store.py`
- Modify: `tests/test_report_lineage.py`

**Interfaces:**
- Consumes: repository root, validated state bytes, rendered Markdown bytes, optional predecessor pointer.
- Produces: `publish_revision(repo_root: Path, state_bytes: bytes) -> PublishedRevision` and `load_current(repo_root: Path, report_id: str) -> CurrentRevision | None`.

- [ ] **Step 1: Write failing storage and security tests**

```python
def test_publication_is_append_only_and_pointer_is_atomic(self):
    published = STORE.publish_revision(self.root, self.state_bytes(revision=1))
    self.assertEqual(published.state_path.name, "revision-0001.json")
    self.assertEqual(published.markdown_path.name, "revision-0001.md")
    pointer = json.loads(published.pointer_path.read_text())
    self.assertEqual(pointer["revision"], 1)
    self.assertEqual(pointer["markdown_sha256"], sha256(published.markdown_path))
    with self.assertRaises(FileExistsError):
        STORE.publish_revision(self.root, self.state_bytes(revision=1))

def test_revision_two_hashes_exact_selected_markdown_bytes(self):
    first = STORE.publish_revision(self.root, self.state_bytes(revision=1))
    second_state = self.state(revision=2)
    second_state["report"]["previous_sha256"] = sha256(first.markdown_path)
    second = STORE.publish_revision(self.root, canonical_json(second_state))
    self.assertEqual(STORE.load_current(self.root, "RPT-001").revision, 2)
    self.assertTrue(first.markdown_path.exists())

def test_store_rejects_traversal_external_symlink_and_non_utf8(self):
    for report_id in ("../escape", "/tmp/escape", "RPT-001/../../escape"):
        with self.subTest(report_id=report_id):
            with self.assertRaises(ValueError):
                STORE.report_directory(self.root, report_id)
```

Test helpers use literal standard-library operations rather than store helpers:

```python
def canonical_json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
```

Add fault-injection tests that raise after state write, after Markdown write, and before pointer replacement; the prior pointer must remain valid.

- [ ] **Step 2: Run tests and verify RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task4-red python3 -m unittest tests.test_report_store -v
```

Expected: store module and CLI are missing.

- [ ] **Step 3: Implement safe append-only storage**

Use exact paths:

```python
REPORT_ROOT = Path(".requirements-impact-refiner/reports")

@dataclass(frozen=True)
class PublishedRevision:
    report_id: str
    revision: int
    state_path: Path
    markdown_path: Path
    pointer_path: Path
    markdown_sha256: str
```

Open candidate files with exclusive creation, reject symlinks using `lstat()`, fsync file contents where available, and publish `current.json` with `os.replace()` from a temporary sibling. Store only POSIX relative paths in the pointer. Verify the pointer by reopening and hashing the selected Markdown before returning success.

- [ ] **Step 4: Implement publication CLI and full-inline fallback result**

CLI contract:

```sh
python3 publish-impact-report.py --repo-root REPO STATE.json
```

On success, print canonical JSON containing `status: published`, relative artifact paths, revision, and Markdown SHA. On validation failure return 1. On unavailable/unwritable/path-unsafe storage return 2 and print `fallback: full-inline` without leaving a current pointer.

- [ ] **Step 5: Refresh mirrors and verify GREEN**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task4-green python3 -m unittest tests.test_report_store tests.test_report_lineage -v
cmp skills/requirements-impact-refiner/scripts/report_store.py scripts/report_store.py
cmp skills/requirements-impact-refiner/scripts/publish-impact-report.py scripts/publish-impact-report.py
```

- [ ] **Step 6: Commit**

```sh
git add skills/requirements-impact-refiner/scripts/report_store.py skills/requirements-impact-refiner/scripts/publish-impact-report.py scripts/report_store.py scripts/publish-impact-report.py tests/test_report_store.py tests/test_report_lineage.py
git commit -m "feat: persist append-only impact revisions"
```

---

### Task 5: Progressive Skill Routing and Compact Default

**Files:**
- Modify: `skills/requirements-impact-refiner/SKILL.md`
- Modify: `skills/using-requirements-impact-refiner/SKILL.md`
- Create: `skills/requirements-impact-refiner/references/compact-state-contract.md`
- Create: `references/compact-state-contract.md`
- Create: `skills/requirements-impact-refiner/scripts/resource_route.py`
- Create: `scripts/resource_route.py`
- Modify: `skills/requirements-impact-refiner/references/refinement-loop.md`
- Modify: `references/refinement-loop.md`
- Modify: `tests/test_integration_adapters.py`
- Modify: `tests/test_packaging.py`
- Create: `tests/test_resource_routing.py`

**Interfaces:**
- Consumes: resolved settings, repository evidence, selected adapter, optional predecessor pointer.
- Produces: agent instructions plus `resolve_route(*, predecessor: bool, evidence_ambiguity: bool, multiple_domains: bool, audience: str, delivery: str, phase: str, adapter: str) -> ResourceRoute`, routing only references required by observable predicates.

- [ ] **Step 1: Create RED skill pressure scenarios and deterministic routing tests**

Use the existing sealed 0.3.1 corpus as the no-guidance baseline: it demonstrates average 907-word outputs and unconditional multi-reference routing. Add deterministic tests for the packaged contract:

```python
def test_default_route_loads_only_compact_contract_and_selected_adapter(self):
    route = ROUTING.resolve_route(
        predecessor=False, evidence_ambiguity=False,
        multiple_domains=False, audience="balanced", delivery="compact",
        phase="pre-decision", adapter="generic",
    )
    self.assertEqual(route.references, (
        "references/compact-state-contract.md",
        "references/integration-generic.md",
    ))

def test_conditional_references_have_exact_observable_predicates(self):
    route = ROUTING.resolve_route(
        predecessor=True, evidence_ambiguity=True,
        multiple_domains=True, audience="technical", delivery="full",
        phase="post-decision", adapter="superpowers",
    )
    self.assertEqual(set(route.references), {
        "references/compact-state-contract.md",
        "references/integration-superpowers.md",
        "references/refinement-loop.md",
        "references/evidence-model.md",
        "references/impact-taxonomy.md",
        "references/presentation-modes.md",
        "assets/impact-report-post-decision-template.md",
    })
```

Implement `ResourceRoute` as a frozen dataclass with a tuple of relative paths. Reject unknown adapters, phases, audiences, and delivery values. The behavioral pressure scenario must ask a fresh agent to refine a small change and measure which resource paths it actually reads and what it returns.

- [ ] **Step 2: Run routing tests and baseline scenario to verify RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task5-red python3 -m unittest tests.test_resource_routing tests.test_packaging tests.test_integration_adapters -v
```

Expected: compact contract and predicate-based route do not exist; current core still directs unconditional reads.

- [ ] **Step 3: Rewrite the core as a concise router**

Keep `SKILL.md` under 400 words. Its resource section names only the compact contract and selected adapter as default reads, then provides exact conditional predicates for evidence, taxonomy, refinement, presentation, and full template. Its output contract states:

```text
compact: author state JSON, publish it, return render_compact output only
full: author state JSON, publish it when possible, return canonical Markdown inline
fallback: if publish reports full-inline, return canonical Markdown inline and disclose no fast path
```

Do not duplicate schema tables in `SKILL.md`; place field-level details in `compact-state-contract.md`.

- [ ] **Step 4: Update revision routing and bootstrap boundaries**

The refinement reference must read `current.json`, verify its selected Markdown digest, preserve IDs, and route only changed evidence. The bootstrap remains under 180 words and continues excluding ideation, explanation, debugging, code review, status, and already-refined execution.

- [ ] **Step 5: Run skill GREEN pressure scenario and focused tests**

Run the same small-change scenario with the updated skill. Preserve raw commands/output outside the release tree until reviewed. Verify:

- only the compact contract and one adapter are read in the default case;
- every impact appears in compact output and persisted Markdown;
- compact output is at most 450 words;
- no planning or implementation begins.

Then run:

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task5-green python3 -m unittest tests.test_resource_routing tests.test_packaging tests.test_integration_adapters -v
wc -w skills/requirements-impact-refiner/SKILL.md
```

Expected: tests pass and core skill is below 400 words.

- [ ] **Step 6: Commit**

```sh
git add skills/requirements-impact-refiner/SKILL.md skills/using-requirements-impact-refiner/SKILL.md skills/requirements-impact-refiner/references/compact-state-contract.md references/compact-state-contract.md skills/requirements-impact-refiner/scripts/resource_route.py scripts/resource_route.py skills/requirements-impact-refiner/references/refinement-loop.md references/refinement-loop.md tests/test_integration_adapters.py tests/test_packaging.py tests/test_resource_routing.py
git commit -m "perf: route compact impact analysis progressively"
```

---

### Task 6: Documentation, Version, and Public Demo

**Files:**
- Create: `docs/compact-delivery-demo.md`
- Create: `assets/compact-delivery-demo.svg`
- Modify: `README.md`
- Modify: `README.ko.md`
- Modify: `README.ja.md`
- Modify: `.codex-plugin/plugin.json`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `skills/requirements-impact-refiner/SKILL.md`
- Modify: `skills/using-requirements-impact-refiner/SKILL.md`
- Modify: `tests/test_documentation.py`
- Modify: `tests/test_distribution.py`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Consumes: implemented 0.4.0 compact behavior and verified command examples.
- Produces: synchronized public documentation, a static short demo, and consistent release identity.

- [ ] **Step 1: Write RED documentation and release-identity tests**

Update tests to require version `0.4.0`, Public Preview wording, both configuration settings, compact/full examples, fallback disclosure, demo links, and exact EN/KO/JA semantic tokens. Add an SVG sanity test for a nonempty `viewBox`, accessible `<title>`, no external resources/scripts, and dimensions suitable for README display.

```python
def test_compact_delivery_docs_are_synchronized(self):
    for name in READMES:
        text = (ROOT / name).read_text(encoding="utf-8")
        for token in (
            "0.4.0", "Public Preview", '"delivery":"compact"',
            "delivery: full", "full-inline", "compact-delivery-demo.md",
        ):
            self.assertIn(token, text, f"{token} missing from {name}")
```

- [ ] **Step 2: Run tests and verify RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task6-red python3 -m unittest tests.test_documentation tests.test_distribution tests.test_packaging -v
```

Expected: version, demo, and compact documentation failures.

- [ ] **Step 3: Create the demo and synchronized documentation**

`docs/compact-delivery-demo.md` shows one request, its compact chat response, the stored JSON/Markdown paths, and the command for full rendering. `assets/compact-delivery-demo.svg` visually shows `Request → Impact Summary → Decision → Full Report` using the existing violet/coral brand, code `<>`, cube, and connected-impact motif; keep text readable at 800px width and avoid animation.

README Quick Start documents:

```json
{"audience":"balanced","delivery":"compact"}
```

All translations retain identical commands, versions, compatibility identities/statuses, and sealed historical evidence tables. Do not relabel 0.3.1 evidence as 0.4.0 evidence.

- [ ] **Step 4: Synchronize version identity**

Set the core skill, bootstrap skill, Codex manifest, Claude manifest, and Claude marketplace entry to `0.4.0`. Do not alter historical evaluation harness defaults or sealed result metadata.

- [ ] **Step 5: Verify GREEN**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task6-green python3 -m unittest tests.test_documentation tests.test_distribution tests.test_packaging -v
python3 -m json.tool .codex-plugin/plugin.json >/dev/null
python3 -m json.tool .claude-plugin/plugin.json >/dev/null
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
```

- [ ] **Step 6: Commit**

```sh
git add docs/compact-delivery-demo.md assets/compact-delivery-demo.svg README.md README.ko.md README.ja.md .codex-plugin/plugin.json .claude-plugin/plugin.json .claude-plugin/marketplace.json skills/requirements-impact-refiner/SKILL.md skills/using-requirements-impact-refiner/SKILL.md tests/test_documentation.py tests/test_distribution.py tests/test_packaging.py
git commit -m "docs: introduce compact delivery preview"
```

---

### Task 7: Performance Budget and Smoke Evaluation Gate

**Files:**
- Create: `evals/performance-baseline-v032.json`
- Create: `evals/harness/performance.py`
- Create: `tests/test_performance_budget.py`
- Modify: `evals/harness/models.py`
- Modify: `evals/harness/evidence.py`
- Modify: `evals/harness/reporting.py`
- Modify: `evals/harness/schemas/result.schema.json`
- Modify: `tests/test_eval_harness_contract.py`
- Modify: `tests/test_eval_harness_evidence.py`
- Modify: `tests/test_eval_harness_reporting.py`

**Interfaces:**
- Consumes: exact prompt/resource/output bytes and optional client-reported token/duration data.
- Produces: immutable per-run `PerformanceObservation` rows and a smoke gate that cannot promote an incomplete or over-budget batch.

- [ ] **Step 1: Write RED performance-contract tests**

```python
def test_baseline_is_literal_and_matches_preserved_v032_measurement(self):
    baseline = json.loads(BASELINE.read_text())
    self.assertEqual(baseline["selected_path_words"], 3500)
    self.assertEqual(baseline["output_files"], 100)
    self.assertEqual(baseline["average_output_words"], 906.6)
    self.assertEqual(baseline["maximum_output_words"], 1596)

def test_smoke_gate_requires_complete_semantic_and_budget_evidence(self):
    result = evaluate_smoke_gate(observations=self.six_valid_observations())
    self.assertTrue(result.passed)
    too_large = self.six_valid_observations()
    too_large[3] = replace(too_large[3], output_words=900)
    self.assertFalse(evaluate_smoke_gate(too_large).passed)
```

Add failures for missing observations, retries, JSON/Markdown mismatch, omitted impacts, resource reduction below 50 percent, workflow boundary failures, and fabricated token counts.

- [ ] **Step 2: Run tests and verify RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task7-red python3 -m unittest tests.test_performance_budget tests.test_eval_harness_contract tests.test_eval_harness_evidence tests.test_eval_harness_reporting -v
```

- [ ] **Step 3: Implement exact byte-derived measurements**

```python
@dataclass(frozen=True)
class PerformanceObservation:
    run_id: str
    prompt_bytes: int
    routed_resource_bytes: int
    routed_resource_words: int
    output_bytes: int
    output_words: int
    duration_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    impact_ids: tuple[str, ...]
    state_markdown_match: bool
```

Word counts use Unicode whitespace splitting on exact preserved bytes decoded strictly as UTF-8. Token fields remain `None` unless the raw client event supplies them. Reports must label byte/word measures as proxies, never token counts.

- [ ] **Step 4: Implement the six-case smoke gate**

Require the exact approved six-case suite, repetition 1, selected attempt 1, pass status, matching installed 0.4.0 provenance, complete observations, zero semantic mismatches, median output words at or below 450, and median routed resource words at or below 50 percent of the literal baseline.

- [ ] **Step 5: Verify GREEN and full deterministic suite**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task7-green python3 -m unittest tests.test_performance_budget tests.test_eval_harness_contract tests.test_eval_harness_evidence tests.test_eval_harness_reporting -v
PYTHONPYCACHEPREFIX=/tmp/rir-task7-full python3 -m unittest discover -s tests -v
```

- [ ] **Step 6: Commit deterministic gate code**

```sh
git add evals/performance-baseline-v032.json evals/harness/performance.py evals/harness/models.py evals/harness/evidence.py evals/harness/reporting.py evals/harness/schemas/result.schema.json tests/test_performance_budget.py tests/test_eval_harness_contract.py tests/test_eval_harness_evidence.py tests/test_eval_harness_reporting.py
git commit -m "test: gate compact delivery performance"
```

- [ ] **Step 7: Reinstall the local 0.4.0 plugin and run the smoke batch**

After repository tests and independent review pass, update the configured marketplace snapshot, reinstall the plugin, verify exact installed version/composition, and run:

```sh
python3 -m evals.harness.run \
  --client codex \
  --suite smoke \
  --repetitions 1 \
  --model gpt-5.6-sol \
  --reasoning high \
  --expected-plugin-version 0.4.0 \
  --expected-rir-plugin-id requirements-impact-refiner@requirements-impact-refiner \
  --output evals/results/installed-v0.4-smoke
```

This is an external model-call gate. Preserve raw evidence, run the secret detector, seal a manifest, and commit only after independent evidence review. If the gate fails, stop before full evaluation and public release actions.

---

### Task 8: Full Evaluation and Public Repository Launch

**Files:**
- Create after successful execution: `evals/results/installed-v0.4/**`
- Create: `SECURITY.md`
- Create: `CODE_OF_CONDUCT.md`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/PULL_REQUEST_TEMPLATE.md`
- Modify: `README.md`
- Modify: `README.ko.md`
- Modify: `README.ja.md`
- Modify: `tests/test_documentation.py`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Consumes: a passed, independently reviewed six-case smoke gate.
- Produces: sealed 85-result evaluation evidence, honest compatibility claims, community files, GitHub metadata, tag, and Release.

- [ ] **Step 1: Run the approved 85-result evaluation only after smoke PASS**

```sh
python3 -m evals.harness.run \
  --client codex \
  --suite installed-superpowers \
  --repetitions 5 \
  --model gpt-5.6-sol \
  --reasoning high \
  --expected-plugin-version 0.4.0 \
  --expected-rir-plugin-id requirements-impact-refiner@requirements-impact-refiner \
  --output evals/results/installed-v0.4
```

Do not retry scored failures. Permit only the harness's single append-only infrastructure retry. Preserve exact raw evidence, token fields only when client-emitted, byte/word proxies, mechanical scores, human adjudication, manifest, and `not verified` unless every canonical gate passes.

- [ ] **Step 2: Independently review and seal evaluation evidence**

Require exact inventory/digest tests, raw `-text -whitespace` attributes, secret scan, installed payload identity, attempt/retry/session lineage, score/report re-rendering, and performance-gate verification. Any Critical or Important finding blocks launch until fixed and re-reviewed.

- [ ] **Step 3: Write RED community-health tests**

```python
def test_public_preview_community_files_exist(self):
    required = (
        "SECURITY.md", "CODE_OF_CONDUCT.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/PULL_REQUEST_TEMPLATE.md",
    )
    for relative in required:
        self.assertTrue((ROOT / relative).is_file(), relative)
```

Also assert SECURITY reports supported version 0.4.x and provides private reporting instructions that do not promise a nonexistent security-advisory capability.

- [ ] **Step 4: Add community files and final evidence documentation**

Use Contributor Covenant 2.1 for `CODE_OF_CONDUCT.md`. Security policy must define scope, supported versions, response expectations without SLA guarantees, and GitHub private vulnerability reporting only if repository settings confirm it is enabled; otherwise provide the maintainer's selected private channel before publication. Issue forms capture client/version/plugin version, reproduction, expected/actual result, repository sensitivity warning, and logs with secrets removed. PR template requires tests, documentation parity, evidence-claim review, and no secrets.

Update all READMEs with the exact v0.4 evidence result and performance measurements. Keep failures and blocked clients visible.

- [ ] **Step 5: Run final verification and commit**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-task8-final python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=/tmp/rir-task8-compile python3 -m compileall -q skills/requirements-impact-refiner scripts evals/harness tests
git diff --check
```

Commit only after independent branch review:

```sh
git add SECURITY.md CODE_OF_CONDUCT.md .github README.md README.ko.md README.ja.md evals/results/installed-v0.4 tests
git commit -m "release: prepare compact delivery public preview"
```

- [ ] **Step 6: Push and require green CI**

Push `main`, watch the exact resulting GitHub Actions run to completion, and stop if it fails. Confirm local HEAD equals `origin/main` after fetch.

- [ ] **Step 7: Update GitHub repository metadata**

Set description to:

```text
Repository-aware requirement impact analysis that prevents regressions before implementation planning.
```

Set homepage to `https://github.com/sdj7072/requirements-impact-refiner#readme` and topics to:

```text
requirements-engineering impact-analysis regression-testing agent-skills codex claude-code developer-tools vibe-coding
```

Upload a 1280×640 social preview derived from the established logo/demo only after visually verifying it at card size.

- [ ] **Step 8: Tag and publish GitHub Release**

Create annotated tag `v0.4.0` at the green-CI HEAD. Publish a GitHub prerelease titled `Requirements Impact Refiner v0.4.0 — Public Preview` with compact delivery behavior, configuration, measured performance, compatibility limits, install/upgrade commands, and links to sealed evidence. Read back the tag and Release; do not mark it latest stable.

---

## Plan Self-Review Record

- Spec coverage: configuration, state contract, deterministic rendering, append-only storage, progressive loading, fast revision path, failure handling, backward compatibility, performance measurement, smoke gate, full evaluation, documentation, community files, metadata, demo, tag, and Release are each mapped to Tasks 1–8.
- Placeholder scan: no deferred implementation placeholders remain; future evidence values are generated only by the explicitly gated live evaluation steps.
- Interface consistency: `compact_state.validate_state()` feeds `impact_renderer`, `impact_renderer` feeds `report_store`, `report_store` feeds compact/full delivery, and the harness observes exact persisted bytes.
- Scope: the plan changes one coherent delivery subsystem and sequences public-launch work after its evidence gates.
