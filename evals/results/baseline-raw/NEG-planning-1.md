# Requirements Impact Refiner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, reviewable pipeline that turns approved requirements and their approved impact report into a normalized implementation backlog, preserving traceability and surfacing unresolved decisions without inventing scope.

**Architecture:** A small domain pipeline will parse the approved inputs, normalize requirement and impact records, derive coding tasks, validate traceability and completeness, and serialize a stable report. Pure transformation functions will remain separate from file/CLI adapters so the core can be tested without I/O. The pipeline will fail closed on malformed input and will represent ambiguity explicitly rather than silently selecting an interpretation.

**Tech Stack:** Use the repository's existing language, test runner, formatter, and serialization conventions. Do not add a runtime dependency when an existing standard-library or repository utility already provides the needed behavior.

**Spec:** The approved requirements specification and its approved impact report supplied with this task; the impact report is authoritative for affected components and is not to be regenerated or rewritten by this feature.

## Global Constraints

- Treat the approved impact report as read-only input and preserve its identifiers verbatim.
- Every generated coding task must link to at least one requirement identifier and, when an affected component is present, to the corresponding impact-report identifier.
- Do not infer new product scope, alter approved requirement intent, or hide unresolved assumptions.
- Output must be deterministic: identical inputs produce byte-for-byte equivalent normalized output.
- Invalid input is a user-visible validation error with a non-zero CLI exit status; partial output must not be published.
- Generated tasks must be independently testable and contain implementation, test, and verification acceptance criteria.

---

### Task 1: Define the domain contracts and validation errors

**Files:**
- Create: `src/requirements_impact_refiner/domain.py`
- Create: `src/requirements_impact_refiner/errors.py`
- Test: `tests/unit/test_domain.py`

**Interfaces:**
- Produces immutable records `Requirement(id: str, title: str, description: str, acceptance_criteria: tuple[str, ...])`, `Impact(id: str, requirement_id: str, component: str, change_type: str, rationale: str)`, `CodingTask(id: str, title: str, requirement_ids: tuple[str, ...], impact_ids: tuple[str, ...], files: tuple[str, ...], interfaces: tuple[str, ...], steps: tuple[str, ...], acceptance_criteria: tuple[str, ...])`, and `RefinementResult(tasks: tuple[CodingTask, ...], unresolved: tuple[str, ...], warnings: tuple[str, ...])`.
- Produces `InputValidationError` with a stable `code` and human-readable `message`.
- `validate_requirement`, `validate_impact`, and `validate_task` return `None` or raise `InputValidationError`.

- [ ] **Step 1: Write the failing tests for required fields, identifier format, and immutable records**

```python
def test_requirement_requires_nonempty_id_and_title():
    with pytest.raises(InputValidationError, match="requirement.id"):
        Requirement(id="", title="A", description="d", acceptance_criteria=("c",))


def test_impact_must_reference_a_requirement():
    impact = Impact(id="IMP-1", requirement_id="REQ-1", component="api", change_type="modify", rationale="r")
    with pytest.raises(InputValidationError, match="requirement_id"):
        validate_impact(impact, known_requirement_ids=set())
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest tests/unit/test_domain.py -q`

Expected: FAIL because the domain records and validators do not yet exist.

- [ ] **Step 3: Implement the records and stable validation errors**

Use frozen records, trim only transport-level whitespace, reject empty identifiers/titles/components, reject duplicate acceptance criteria, and report the first stable validation code in field order. Keep validation free of filesystem or CLI concerns.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `pytest tests/unit/test_domain.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirements_impact_refiner/domain.py src/requirements_impact_refiner/errors.py tests/unit/test_domain.py
git commit -m "feat: define impact refinement domain contracts"
```

### Task 2: Parse approved requirements and impact-report inputs

**Files:**
- Create: `src/requirements_impact_refiner/io.py`
- Test: `tests/unit/test_io.py`
- Test: `tests/fixtures/approved_requirements.json`
- Test: `tests/fixtures/approved_impact_report.json`

**Interfaces:**
- `load_requirements(path: Path) -> tuple[Requirement, ...]`.
- `load_impacts(path: Path) -> tuple[Impact, ...]`.
- `load_json_document(path: Path) -> Mapping[str, object]`.
- Producers preserve source identifiers and raise `InputValidationError` for missing files, invalid JSON, wrong top-level shape, duplicate IDs, orphan impacts, or unapproved impact-report status.

- [ ] **Step 1: Write failing parser tests for valid fixtures and each rejection case**

```python
def test_load_impacts_preserves_approved_ids(tmp_path):
    path = tmp_path / "impact.json"
    path.write_text(json.dumps({"status": "approved", "impacts": [{"id": "IMP-1", "requirement_id": "REQ-1", "component": "api", "change_type": "modify", "rationale": "r"}]}))
    assert load_impacts(path)[0].id == "IMP-1"


def test_load_impacts_rejects_unapproved_report(tmp_path):
    path = tmp_path / "impact.json"
    path.write_text(json.dumps({"status": "draft", "impacts": []}))
    with pytest.raises(InputValidationError, match="approved"):
        load_impacts(path)
```

- [ ] **Step 2: Run the parser tests to verify they fail**

Run: `pytest tests/unit/test_io.py -q`

Expected: FAIL because the loader functions do not yet exist.

- [ ] **Step 3: Implement strict parsing and cross-document validation**

Read UTF-8 JSON, validate the approved status before consuming impacts, construct domain records in input order, reject duplicate IDs, and verify every `Impact.requirement_id` is in the requirements set. Never rewrite or save the input report.

- [ ] **Step 4: Run the parser tests to verify they pass**

Run: `pytest tests/unit/test_io.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirements_impact_refiner/io.py tests/unit/test_io.py tests/fixtures/approved_requirements.json tests/fixtures/approved_impact_report.json
git commit -m "feat: parse approved requirements and impact reports"
```

### Task 3: Refine impacts into deterministic coding tasks

**Files:**
- Create: `src/requirements_impact_refiner/refine.py`
- Test: `tests/unit/test_refine.py`

**Interfaces:**
- `refine(requirements: Sequence[Requirement], impacts: Sequence[Impact]) -> RefinementResult`.
- `group_impacts_by_component(impacts: Sequence[Impact]) -> Mapping[str, tuple[Impact, ...]]`.
- `make_task_id(requirement_ids: Sequence[str], component: str, ordinal: int) -> str`.
- Producers create one or more tasks per affected component/change cluster, include all source IDs, and add unresolved entries for impacts lacking enough information to specify a file, interface, or observable behavior.

- [ ] **Step 1: Write failing tests for grouping, stable IDs, task decomposition, and unresolved assumptions**

```python
def test_refine_is_deterministic_and_traceable(requirements, impacts):
    first = refine(requirements, impacts)
    second = refine(tuple(reversed(requirements)), tuple(reversed(impacts)))
    assert first == second
    assert first.tasks[0].requirement_ids
    assert first.tasks[0].impact_ids


def test_refine_surfaces_missing_file_mapping(requirements):
    impacts = (Impact("IMP-1", "REQ-1", "api", "modify", "r"),)
    result = refine(requirements, impacts)
    assert any("file" in item.lower() for item in result.unresolved)
```

- [ ] **Step 2: Run the refinement tests to verify they fail**

Run: `pytest tests/unit/test_refine.py -q`

Expected: FAIL because refinement functions do not yet exist.

- [ ] **Step 3: Implement canonical sorting and task generation**

Sort requirements and impacts by stable IDs, group by normalized component and change type, derive IDs from canonical source IDs, and generate task text from source acceptance criteria plus the affected component/rationale. Keep every unresolved assumption in a stable, deduplicated list; do not fabricate paths or APIs.

- [ ] **Step 4: Run the refinement tests to verify they pass**

Run: `pytest tests/unit/test_refine.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirements_impact_refiner/refine.py tests/unit/test_refine.py
git commit -m "feat: refine approved impacts into coding tasks"
```

### Task 4: Render, validate, and expose the command-line workflow

**Files:**
- Create: `src/requirements_impact_refiner/render.py`
- Create: `src/requirements_impact_refiner/cli.py`
- Modify: `pyproject.toml` (or the repository's existing package entry-point file)
- Test: `tests/integration/test_cli.py`

**Interfaces:**
- `render_markdown(result: RefinementResult) -> str`.
- `render_json(result: RefinementResult) -> str`.
- `validate_result(result: RefinementResult) -> None`.
- CLI command `requirements-impact-refiner --requirements PATH --impact-report PATH --format markdown|json --output PATH`.
- Exit codes: `0` success, `2` input/validation error, `1` unexpected failure.

- [ ] **Step 1: Write failing integration tests for both formats, traceability, and atomic output behavior**

```python
def test_cli_writes_markdown_and_keeps_unresolved_section(tmp_path):
    output = tmp_path / "tasks.md"
    result = runner.invoke(app, ["--requirements", str(REQUIREMENTS), "--impact-report", str(IMPACTS), "--format", "markdown", "--output", str(output)])
    assert result.exit_code == 0
    text = output.read_text()
    assert "Implementation Plan" in text
    assert "Unresolved" in text


def test_cli_does_not_replace_output_on_validation_error(tmp_path):
    output = tmp_path / "tasks.json"
    output.write_text("sentinel")
    result = runner.invoke(app, ["--requirements", str(REQUIREMENTS), "--impact-report", str(UNAPPROVED), "--format", "json", "--output", str(output)])
    assert result.exit_code == 2
    assert output.read_text() == "sentinel"
```

- [ ] **Step 2: Run the integration tests to verify they fail**

Run: `pytest tests/integration/test_cli.py -q`

Expected: FAIL because rendering and the CLI entry point do not yet exist.

- [ ] **Step 3: Implement result validation, renderers, and atomic CLI writes**

Validate that each task has source IDs, steps, and acceptance criteria; render IDs and unresolved items in stable order; write to a temporary sibling file and replace the destination only after the complete result validates. Print concise errors to stderr and avoid leaking stack traces for expected input errors.

- [ ] **Step 4: Register the command and run integration tests**

Run: `pytest tests/integration/test_cli.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirements_impact_refiner/render.py src/requirements_impact_refiner/cli.py pyproject.toml tests/integration/test_cli.py
git commit -m "feat: expose deterministic impact-refinement CLI"
```

### Task 5: Add end-to-end regression coverage and documentation

**Files:**
- Create: `tests/e2e/test_approved_report_workflow.py`
- Modify: `README.md` (or the repository's existing user documentation file)
- Create: `docs/requirements-impact-refiner.md`

**Interfaces:**
- The documented command and output schema are the public contract for downstream coding-task consumers.
- The end-to-end fixture must use the approved impact report without edits and assert stable output across repeated runs.

- [ ] **Step 1: Write the end-to-end regression test**

```python
def test_approved_workflow_is_reproducible(tmp_path):
    first = run_refiner(REQUIREMENTS, APPROVED_IMPACT_REPORT, tmp_path / "first.json", "json")
    second = run_refiner(REQUIREMENTS, APPROVED_IMPACT_REPORT, tmp_path / "second.json", "json")
    assert first == second
    assert all(task["requirement_ids"] for task in first["tasks"])
    assert all(task["impact_ids"] for task in first["tasks"])
```

- [ ] **Step 2: Run the end-to-end test to verify it fails or exposes missing contract details**

Run: `pytest tests/e2e/test_approved_report_workflow.py -q`

Expected: FAIL until the complete pipeline and public output contract are available.

- [ ] **Step 3: Document input schema, output schema, validation errors, unresolved-item handling, and examples**

Document that the impact report must have an approved status, list the required fields, show both command formats, explain that unresolved items require human review, and state that generated output is a plan/backlog artifact rather than an approval mechanism.

- [ ] **Step 4: Run the full verification suite and formatting/type checks**

Run: `pytest -q`

Expected: PASS with all unit, integration, and end-to-end tests green.

Run the repository's existing formatter and type checker using their configured commands; expected result is no changed files and no diagnostics.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_approved_report_workflow.py README.md docs/requirements-impact-refiner.md
git commit -m "docs: document and regression-test impact refinement workflow"
```

## Self-review checklist

- Approved-report immutability is enforced in Task 2 and covered in Task 4/5.
- Requirement/impact traceability is modeled in Task 1, generated in Task 3, validated in Task 4, and asserted in Task 5.
- Determinism is specified in Task 3 and asserted in Task 5.
- Malformed or unapproved input cannot publish partial output; this is tested in Task 4.
- No task asks an implementer to invent file paths, APIs, or product scope when the approved inputs do not provide them; those cases become explicit unresolved items.
