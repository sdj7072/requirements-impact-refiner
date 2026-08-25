# v0.6 Quality Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repeatable lint, format, type, coverage, and security gates without adding a runtime dependency to the plugin.

**Architecture:** Python 3.9/3.11/3.13 continue to run the standard-library test matrix. A separate Python 3.13 quality job installs pinned development tools, and `scripts/run-quality-gates.py` is the single local/CI entry point.

**Tech Stack:** Python standard library runtime; Ruff 0.16.3; Mypy 2.3.1; Coverage 7.15.4; Bandit 1.9.4; GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-25-v0.6-production-readiness-design.md`

**Pinned tool sources:** [Ruff 0.16.3](https://pypi.org/project/ruff/0.16.3/), [Mypy 2.3.1](https://pypi.org/project/mypy/2.3.1/), [Coverage 7.15.4](https://pypi.org/project/coverage/7.15.4/), [Bandit 1.9.4](https://pypi.org/project/bandit/1.9.4/).

## Global Constraints

- Default plugin execution remains network-free and standard-library-only.
- Development packages never enter `.codex-plugin`, `.claude-plugin`, `.mcp.json`, or `skills/` runtime imports.
- Python 3.9, 3.11, and 3.13 tests remain mandatory.
- The quality job runs on Python 3.13 and pins every tool version exactly.
- Root scripts and `skills/requirements-impact-refiner/scripts/` mirrors remain byte-identical.
- Every task ends with the full standard-library suite green.

---

### Task 1: Pin and validate the development toolchain

**Files:**
- Create: `requirements-quality.txt`
- Create: `pyproject.toml`
- Create: `tests/test_quality_configuration.py`

**Interfaces:**
- Consumes: existing Python source roots `scripts/`, `skills/requirements-impact-refiner/scripts/`, `evals/harness/`, `tests/`
- Produces: exact tool pins and shared configuration read by local and CI commands

- [ ] **Step 1: Write the failing configuration test**

```python
class QualityConfigurationTest(unittest.TestCase):
    def test_quality_requirements_are_exactly_pinned(self):
        rows = Path("requirements-quality.txt").read_text().splitlines()
        self.assertEqual(rows, [
            "bandit==1.9.4",
            "coverage==7.15.4",
            "mypy==2.3.1",
            "ruff==0.16.3",
        ])

    def test_runtime_payload_does_not_import_quality_tools(self):
        forbidden = ("bandit", "coverage", "mypy", "ruff")
        for path in payload_identity.functional_paths(Path.cwd()):
            if path.suffix == ".py":
                text = path.read_text(encoding="utf-8")
                self.assertFalse(any(f"import {name}" in text for name in forbidden), path)
```

- [ ] **Step 2: Run the test and observe the missing files**

Run: `python3 -m unittest -q tests.test_quality_configuration`

Expected: FAIL because `requirements-quality.txt` and `pyproject.toml` do not exist.

- [ ] **Step 3: Add exact pins and tool configuration**

```text
bandit==1.9.4
coverage==7.15.4
mypy==2.3.1
ruff==0.16.3
```

Configure Ruff for Python 3.9 syntax, line length 100, stable rules `E`, `F`, `I`, `B`, `UP`, `RUF`, and no preview rules. Configure Mypy with `python_version = "3.9"`, `check_untyped_defs = true`, `warn_unused_ignores = true`, and `no_implicit_optional = true`. Configure Coverage with branch measurement, source roots, test omission, and `fail_under = 80`. Configure Bandit to scan shipped scripts and the harness while excluding tests and preserved raw evidence.

- [ ] **Step 4: Run the configuration test**

Run: `python3 -m unittest -q tests.test_quality_configuration`

Expected: PASS.

- [ ] **Step 5: Commit the toolchain contract**

```bash
git add requirements-quality.txt pyproject.toml tests/test_quality_configuration.py
git commit -m "build: pin v0.6 quality toolchain"
```

### Task 2: Establish the Ruff baseline

**Files:**
- Modify: `scripts/*.py`
- Modify: `skills/requirements-impact-refiner/scripts/*.py`
- Modify: `evals/harness/**/*.py`
- Modify: `tests/**/*.py`

**Interfaces:**
- Consumes: Ruff configuration from Task 1
- Produces: source that passes `ruff check` and `ruff format --check`

- [ ] **Step 1: Install the pinned tools in an isolated environment**

Run: `python3.13 -m venv .quality-venv && .quality-venv/bin/pip install -r requirements-quality.txt`

Expected: Ruff reports version `0.16.3`.

- [ ] **Step 2: Record the red lint and format output**

Run: `.quality-venv/bin/ruff check scripts skills/requirements-impact-refiner/scripts evals/harness tests`

Run: `.quality-venv/bin/ruff format --check scripts skills/requirements-impact-refiner/scripts evals/harness tests`

Expected: at least one command exits non-zero on the pre-gate tree.

- [ ] **Step 3: Apply deterministic fixes**

Run: `.quality-venv/bin/ruff check --fix scripts skills/requirements-impact-refiner/scripts evals/harness tests`

Run: `.quality-venv/bin/ruff format scripts skills/requirements-impact-refiner/scripts evals/harness tests`

Review every semantic diff; do not accept a fix that changes canonical bytes, regular expressions, shell arguments, or error strings without a focused regression test.

- [ ] **Step 4: Verify formatting, mirrors, and tests**

Run: `.quality-venv/bin/ruff check scripts skills/requirements-impact-refiner/scripts evals/harness tests`

Run: `.quality-venv/bin/ruff format --check scripts skills/requirements-impact-refiner/scripts evals/harness tests`

Run: `python3 -m unittest discover -s tests -q`

Expected: all commands pass and mirror tests remain green.

- [ ] **Step 5: Commit the Ruff baseline**

```bash
git add scripts skills/requirements-impact-refiner/scripts evals/harness tests
git commit -m "style: establish ruff baseline"
```

### Task 3: Make shipped modules type-checkable

**Files:**
- Modify: `scripts/*.py`
- Modify: `skills/requirements-impact-refiner/scripts/*.py`
- Modify: `evals/harness/**/*.py`
- Create: `tests/test_public_type_contracts.py`

**Interfaces:**
- Consumes: existing public controller, graph, renderer, and harness APIs
- Produces: Mypy-clean shipped modules with no file-level ignore and stable public annotations

- [ ] **Step 1: Add runtime-neutral public annotation tests**

```python
class PublicTypeContractsTest(unittest.TestCase):
    def test_public_request_types_expose_annotations(self):
        for value in (
            CONTROLLER.BeginRequest,
            CONTROLLER.TraceRequest,
            CONTROLLER.FinalizeRequest,
            FAST_SCAN.FastScanRequest,
        ):
            self.assertTrue(value.__annotations__, value.__name__)
```

- [ ] **Step 2: Run Mypy and preserve the complete error list**

Run: `.quality-venv/bin/mypy scripts evals/harness`

Expected: non-zero with concrete missing or incompatible annotations.

- [ ] **Step 3: Annotate boundaries before internals**

Add exact parameter and return types to public dataclasses, facade functions, adapter protocols, renderer entry points, and persisted mapping boundaries. Use `Mapping[str, object]`, immutable tuples, dataclasses, and narrow helper protocols; do not replace errors with `Any` merely to silence Mypy. Mirror each shipped change.

- [ ] **Step 4: Resolve remaining internal errors in bounded batches**

Run after each file group:

```bash
.quality-venv/bin/mypy scripts/fast_scan.py scripts/fast_scan_renderer.py scripts/impact_renderer.py
.quality-venv/bin/mypy scripts/graph_*.py
.quality-venv/bin/mypy scripts/rir_controller.py scripts/rir_mcp_server.py
.quality-venv/bin/mypy evals/harness
```

Expected: each batch reaches zero errors before the next begins.

- [ ] **Step 5: Verify tests and commit**

Run: `.quality-venv/bin/mypy scripts evals/harness`

Run: `python3 -m unittest discover -s tests -q`

```bash
git add scripts skills/requirements-impact-refiner/scripts evals/harness tests/test_public_type_contracts.py
git commit -m "refactor: type shipped python boundaries"
```

### Task 4: Enforce measured coverage and static security

**Files:**
- Create: `scripts/run-quality-gates.py`
- Create: `tests/test_quality_runner.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: pinned tools and current test suite
- Produces: `python3 scripts/run-quality-gates.py` with stable exit codes and no source mutation

- [ ] **Step 1: Write the failing runner test**

```python
class QualityRunnerTest(unittest.TestCase):
    def test_check_mode_contains_every_gate(self):
        result = subprocess.run(
            [sys.executable, "scripts/run-quality-gates.py", "--print-commands"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(result.stdout.splitlines(), [
            "ruff check scripts skills/requirements-impact-refiner/scripts evals/harness tests",
            "ruff format --check scripts skills/requirements-impact-refiner/scripts evals/harness tests",
            "mypy scripts evals/harness",
            "coverage run --branch -m unittest discover -s tests -q",
            "coverage report --fail-under=80",
            "bandit -q -r scripts skills/requirements-impact-refiner/scripts evals/harness -x tests,evals/results",
        ])
```

- [ ] **Step 2: Run the test**

Run: `python3 -m unittest -q tests.test_quality_runner`

Expected: FAIL because the runner is missing.

- [ ] **Step 3: Implement the runner**

Use `argparse` and `subprocess.run(check=True)` with the literal command vectors from the test. `--print-commands` prints without executing. Normal mode verifies the installed tool versions before executing the gates in order and returns the first non-zero status.

- [ ] **Step 4: Run the complete local gate**

Run: `.quality-venv/bin/python scripts/run-quality-gates.py`

Expected: all gates pass, coverage is at least 80 percent, and Bandit reports no unresolved medium-or-higher issue.

- [ ] **Step 5: Commit the quality runner**

```bash
git add scripts/run-quality-gates.py tests/test_quality_runner.py pyproject.toml
git commit -m "build: enforce local quality gates"
```

### Task 5: Split test and quality CI jobs

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `README.ko.md`
- Modify: `README.ja.md`
- Modify: `CONTRIBUTING.md`
- Modify: `tests/test_documentation.py`

**Interfaces:**
- Consumes: `scripts/run-quality-gates.py`
- Produces: independent `test` matrix and Python 3.13 `quality` job

- [ ] **Step 1: Add a failing workflow/documentation test**

```python
def test_ci_has_test_matrix_and_quality_job(self):
    workflow = Path(".github/workflows/ci.yml").read_text()
    self.assertIn('python-version: ["3.9", "3.11", "3.13"]', workflow)
    self.assertIn("quality:", workflow)
    self.assertIn("pip install -r requirements-quality.txt", workflow)
    self.assertIn("python scripts/run-quality-gates.py", workflow)
```

- [ ] **Step 2: Run the workflow test**

Run: `python3 -m unittest -q tests.test_documentation`

Expected: FAIL because the quality job is absent.

- [ ] **Step 3: Add the quality job and documentation**

The test matrix keeps standard-library tests and compilation. The quality job uses Python 3.13, installs `requirements-quality.txt`, and invokes the runner. Document the same local commands in all three READMEs and contribution guidance.

- [ ] **Step 4: Verify locally and inspect remote CI**

Run: `.quality-venv/bin/python scripts/run-quality-gates.py`

Run: `python3 -m unittest discover -s tests -q`

After push, require every matrix leg and the quality job to succeed on the same commit.

- [ ] **Step 5: Commit the CI gate**

```bash
git add .github/workflows/ci.yml README.md README.ko.md README.ja.md CONTRIBUTING.md tests/test_documentation.py
git commit -m "ci: enforce v0.6 quality gates"
```

### Task 6: Quality-foundation review gate

**Files:**
- Verify only: all files changed by Tasks 1-5

**Interfaces:**
- Consumes: complete quality foundation
- Produces: reviewed green commit eligible for the controller/graph plan

- [ ] **Step 1: Run all local gates from a clean checkout**

Run: `.quality-venv/bin/python scripts/run-quality-gates.py`

Run: `git diff --check`

- [ ] **Step 2: Request an independent code review**

The reviewer checks runtime dependency isolation, type-ignore use, coverage exclusions, Bandit suppressions, mirror parity, and CI/local command parity. Critical or Important findings block the next plan.

- [ ] **Step 3: Commit review fixes separately**

```bash
git add -u
git commit -m "fix: close quality-foundation review findings"
```
