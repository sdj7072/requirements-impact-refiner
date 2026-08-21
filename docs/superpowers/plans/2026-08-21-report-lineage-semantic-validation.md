# Report Lineage and Semantic Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release Requirements Impact Refiner 0.3.0 with verifiable Markdown report lineage, deterministic transition-based Impact Delta calculation, and semantic completeness validation.

**Architecture:** Keep the distribution dependency-free and split the current monolithic validator into a reusable `impact_report.py` domain module plus the existing thin `validate-impact-report.py` CLI. The domain module parses canonical Markdown into typed data, validates one report, verifies lineage, and computes Delta; the CLI owns files, exact bytes, arguments, exit codes, and rendering. Skill instructions and templates use the same rules conceptually when a client cannot run Python.

**Tech Stack:** Python 3.11 standard library, Markdown assets, Agent Skills, Codex and Claude plugin manifests, `unittest`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-21-report-lineage-semantic-validation-design.md`

**Impact report:** `docs/superpowers/specs/2026-08-21-report-lineage-semantic-validation-impact-report.md`

## Global Constraints

- Target version is exactly `0.3.0` in both plugin manifests and both skill metadata blocks.
- The canonical history consists only of Markdown reports; do not add JSON state, a database, or an external service.
- Compute predecessor SHA-256 from exact file bytes; do not normalize line endings or rewrite reports.
- Do not automatically migrate v0.2 reports. A v0.3 chain begins with Revision 1 and `Previous SHA-256: none`.
- Preserve the existing single-report command for a Revision 1 baseline; later revisions require `--previous`.
- Preserve automatic activation exclusions and every orchestration ownership boundary.
- Keep Python code standard-library-only and compatible with Python 3.11.
- Do not modify preserved raw evaluation corpora under `evals/results/*-raw` or `evals/results/compatibility-raw`.
- English documentation remains authoritative; Korean and Japanese semantic changes ship together.
- Runtime compatibility remains `not verified` or `blocked` unless a fresh executable run proves otherwise.
- Use `superpowers:test-driven-development`, `superpowers:writing-skills`, and `skill-creator` during implementation; validate behavior, not only wording.
- Do not push, publish, or reinstall the plugin as part of this plan; those external mutations require a separate user instruction after local verification.

## File Structure

- Create `skills/requirements-impact-refiner/scripts/impact_report.py`: typed report model, Markdown parser, single-report semantic validator, lineage validator, Delta calculator, and renderer.
- Modify `skills/requirements-impact-refiner/scripts/validate-impact-report.py`: backward-compatible function re-exports plus `argparse` CLI and exact-byte file handling.
- Modify `skills/requirements-impact-refiner/assets/impact-report-pre-decision-template.md`: v0.3 Revision 1-compatible pre-decision schema.
- Modify `skills/requirements-impact-refiner/assets/impact-report-post-decision-template.md`: v0.3 post-decision schema.
- Modify `skills/requirements-impact-refiner/assets/impact-report-template.md`: baseline, comparison, and expected-Delta commands.
- Modify `skills/requirements-impact-refiner/SKILL.md`: lineage discovery, stable identity, transition rules, semantic completeness, and conceptual fallback.
- Modify `skills/requirements-impact-refiner/references/evidence-model.md`: v0.3 identity and evidence requirements.
- Modify `skills/requirements-impact-refiner/references/refinement-loop.md`: baseline and subsequent-revision flow.
- Modify `skills/using-requirements-impact-refiner/SKILL.md`: version only; preserve activation behavior verbatim.
- Modify `tests/test_validate_impact_report.py`: v0.3 canonical fixtures and single-report regression coverage.
- Create `tests/test_report_lineage.py`: lineage, transition, SHA, deletion, rendering, and comparison CLI coverage.
- Create `tests/test_semantic_validation.py`: focused semantic mutation coverage.
- Modify `tests/test_packaging.py`: v0.3 metadata, templates, Delta categories, and new script inventory.
- Modify `tests/test_documentation.py`: migration, command, transition, and multilingual parity contracts.
- Modify `.github/workflows/ci.yml`: compile both Python scripts.
- Modify `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json`: version 0.3.0 only.
- Modify `README.md`, `README.ko.md`, and `README.ja.md`: schema, commands, migration, compatibility limitations, and synchronized version.
- Modify `CONTRIBUTING.md`: v0.3 test and behavioral-evaluation procedure.
- Create `evals/v0.3-cases.json`: approved multi-turn lineage pressure scenarios.
- Create `evals/results/state-machine-v0.3.md`: bounded behavioral results and limitations; raw transcripts, if retained, go in a new byte-preserved v0.3 raw subtree.

## Impact and Acceptance Coverage

| Plan task | Closes or verifies |
| --- | --- |
| Task 1 | Baseline schema foundation for `IMP-001`, `IMP-002`, `AC-001`, and `AC-002` |
| Task 2 | Semantic completeness risk `IMP-003` and `AC-003` |
| Task 3 | Transition correctness `IMP-002` plus lineage parts of `IMP-006`, `AC-002`, and `AC-006` |
| Task 4 | CLI compatibility `IMP-001` and `AC-001` |
| Task 5 | Automatic behavior regression `IMP-007`, deferred client behavior `IMP-004`, `AC-004`, and `AC-007` |
| Task 6 | Packaging/documentation parity `IMP-005`, schema-break disclosure `IMP-006`, `AC-005`, and `AC-006` |
| Task 7 | Independent regression evidence for all seven impacts and acceptance criteria |

---

### Task 1: Typed Parser and v0.3 Baseline Contract

**Files:**
- Create: `skills/requirements-impact-refiner/scripts/impact_report.py`
- Modify: `skills/requirements-impact-refiner/scripts/validate-impact-report.py`
- Modify: `tests/test_validate_impact_report.py`

**Interfaces:**
- Consumes: canonical Markdown text.
- Produces: `ReportMetadata`, `ParsedReport`, `parse_report(text)`, and `validate_report(text, *, previous_text=None, previous_bytes=None)`; the CLI module re-exports `validate_report` and `validate_path` so existing callers keep working.
- Private boundaries: `parse_all_tables(sections) -> tuple[dict[str, list[dict[str, str]]], list[str]]`, `parse_metadata(rows) -> tuple[ReportMetadata | None, list[str]]`, `validate_structure(report) -> list[str]`, and `validate_baseline(report) -> list[str]`.

- [ ] **Step 1: Update the canonical test fixtures and write failing parser tests**

Change both phase fixtures in `tests/test_validate_impact_report.py` to this Report State schema and make their baseline Delta contain `IMP-001` only under `new`:

```markdown
## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| RPT-001 | 1 | none | post-decision |
```

Add tests that assert the parsed metadata and reject malformed baselines:

```python
def test_parses_v03_report_metadata(self):
    report, errors = VALIDATOR.parse_report(POST_DECISION_REPORT)
    self.assertEqual(errors, [])
    self.assertEqual(report.metadata.report_id, "RPT-001")
    self.assertEqual(report.metadata.revision, 1)
    self.assertEqual(report.metadata.previous_sha256, "none")
    self.assertEqual(report.metadata.phase, "post-decision")

def test_revision_one_requires_none_predecessor_and_all_impacts_new(self):
    wrong_hash = POST_DECISION_REPORT.replace("| RPT-001 | 1 | none |", "| RPT-001 | 1 | " + "a" * 64 + " |")
    wrong_delta = POST_DECISION_REPORT.replace("| new | IMP-001 |", "| unchanged | IMP-001 |").replace("| unchanged | none |", "| new | none |")
    self.assertIn("revision 1 requires Previous SHA-256 none", VALIDATOR.validate_report(wrong_hash))
    self.assertIn("revision 1 impact IMP-001 must be new", VALIDATOR.validate_report(wrong_delta))
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```bash
python3 -m unittest tests.test_validate_impact_report.ValidateImpactReportTest.test_parses_v03_report_metadata tests.test_validate_impact_report.ValidateImpactReportTest.test_revision_one_requires_none_predecessor_and_all_impacts_new -v
```

Expected: errors because `parse_report` and the four-column Report State contract do not exist.

- [ ] **Step 3: Create the domain model and move parsing behind it**

Create `impact_report.py` with these public types and signatures, then move the current constants, section parsing, table parsing, ID/reference helpers, and single-report checks into it:

```python
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Sequence

RPT_PATTERN = re.compile(r"RPT-\d{3}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

@dataclass(frozen=True)
class ReportMetadata:
    report_id: str
    revision: int
    previous_sha256: str
    phase: str

@dataclass(frozen=True)
class ParsedReport:
    text: str
    metadata: ReportMetadata | None
    sections: Mapping[str, str]
    tables: Mapping[str, Sequence[Mapping[str, str]]]

def parse_report(text: str) -> tuple[ParsedReport, list[str]]:
    sections = markdown_sections(text)
    tables, table_errors = parse_all_tables(sections)
    metadata, metadata_errors = parse_metadata(tables.get("Report State", ()))
    report = ParsedReport(text=text, metadata=metadata, sections=sections, tables=tables)
    return report, sorted(set(table_errors + metadata_errors))

def validate_report(
    text: str,
    *,
    previous_text: str | None = None,
    previous_bytes: bytes | None = None,
) -> list[str]:
    current, errors = parse_report(text)
    if errors:
        return errors
    errors.extend(validate_structure(current))
    errors.extend(validate_baseline(current) if previous_text is None else [])
    return sorted(set(errors))
```

Implement Revision 1 rules exactly: positive integer revision, canonical `RPT-###`, predecessor `none`, every ledger impact under `new`, and every other Delta category `none`. Use literal code rather than the ellipses shown in the interface sketch.

Replace `validate-impact-report.py` internals with a robust sibling import and re-exports while retaining its current CLI until Task 4:

```python
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from impact_report import parse_report, validate_report

def validate_path(path: Path) -> list[str]:
    return validate_report(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run the entire validator suite**

Run:

```bash
python3 -m unittest tests.test_validate_impact_report -v
```

Expected: all tests pass after updating old state-based Delta assertions to the Revision 1 baseline rule; all pre/post-decision, relationship, malformed-row, and unresolved-item checks remain covered.

- [ ] **Step 5: Commit the parser boundary**

```bash
git add skills/requirements-impact-refiner/scripts/impact_report.py skills/requirements-impact-refiner/scripts/validate-impact-report.py tests/test_validate_impact_report.py
git commit -m "refactor: parse versioned impact reports"
```

### Task 2: Semantic Completeness Validation

**Files:**
- Create: `tests/test_semantic_validation.py`
- Modify: `skills/requirements-impact-refiner/scripts/impact_report.py`

**Interfaces:**
- Consumes: `ParsedReport` from Task 1.
- Produces: `validate_semantics(report: ParsedReport) -> list[str]`, called by `validate_report` after structural parsing.
- Private boundaries: `validate_evidence_bases`, `validate_impact_semantics`, `validate_relationship_semantics`, `validate_scope_semantics`, and `validate_handoff_semantics`; each consumes `ParsedReport` and returns `list[str]`.

- [ ] **Step 1: Write mutation tests for every required semantic field**

Create a table-driven suite using the valid Revision 1 fixture:

```python
MUTATIONS = {
    "category": ("| interfaces | high |", "|  | high |", "impact IMP-001 requires a category"),
    "severity": ("| interfaces | high |", "| interfaces |  |", "impact IMP-001 requires severity"),
    "observable": ("| Observable result. | tests/test_exports.py |", "|  | tests/test_exports.py |", "criterion AC-001 requires a nonempty observable criterion"),
    "test": ("| Observable result. | tests/test_exports.py |", "| Observable result. |  |", "criterion AC-001 requires evidence or test"),
    "scope": ("| Export paths. | tests/test_exports.py | Other paths unknown. |", "|  |  |  |", "analysis scope requires a substantive row"),
}

def test_rejects_semantically_empty_rows(self):
    for name, (before, after, expected) in MUTATIONS.items():
        with self.subTest(name=name):
            self.assertIn(expected, validate_report(VALID_REPORT.replace(before, after, 1)))
```

Add focused tests for severity enums, taxonomy enums, evidence-level-specific basis, preserved-invariant links, all non-superseded impacts requiring acceptance criteria, unresolved rationale and owner, superseded rationale/successor, and planning readiness.

- [ ] **Step 2: Run semantic tests and confirm RED**

Run:

```bash
python3 -m unittest tests.test_semantic_validation -v
```

Expected: failures for the five known v0.2 bypasses and the newly specified relationship/readiness rules.

- [ ] **Step 3: Implement exact semantic rules**

Add canonical enums and a nonempty helper:

```python
IMPACT_CATEGORIES = {
    "functionality", "data", "interfaces", "authorization/privacy",
    "state/concurrency", "operations", "compatibility", "legal/policy",
    "regression",
}
SEVERITIES = {"critical", "high", "medium", "low"}

def present(value: str) -> bool:
    return value.strip() not in {"", "—", "none"}

def validate_semantics(report: ParsedReport) -> list[str]:
    errors: list[str] = []
    validators = (
        validate_evidence_bases,
        validate_impact_semantics,
        validate_relationship_semantics,
        validate_scope_semantics,
        validate_handoff_semantics,
    )
    for validator in validators:
        errors.extend(validator(report))
    return sorted(set(errors))
```

Require a direct citation for `verified`, an inference basis for `inferred`, and a named gap for `unknown`. Treat an acceptance target as a relationship, never resolution evidence. A post-decision report with any blocked ledger impact must use `Not ready`; deferred or accepted IDs must appear in Remaining risks.

- [ ] **Step 4: Run focused and full regression tests**

Run:

```bash
python3 -m unittest tests.test_semantic_validation tests.test_validate_impact_report -v
python3 -m unittest discover -s tests -v
```

Expected: all tests pass; no existing activation, packaging, documentation, or raw-evidence test regresses.

- [ ] **Step 5: Commit semantic validation**

```bash
git add skills/requirements-impact-refiner/scripts/impact_report.py tests/test_semantic_validation.py tests/test_validate_impact_report.py
git commit -m "feat: enforce impact report semantics"
```

### Task 3: Lineage Verification and Transition Calculator

**Files:**
- Create: `tests/test_report_lineage.py`
- Modify: `skills/requirements-impact-refiner/scripts/impact_report.py`

**Interfaces:**
- Consumes: current and previous `ParsedReport` values plus exact predecessor bytes.
- Produces: `validate_lineage(previous, current, previous_bytes)`, `calculate_delta(previous, current)`, and `render_delta(delta)`.
- Private boundary: `impact_states(report: ParsedReport) -> dict[str, str]` reads canonical ledger IDs and normalized lifecycle states.

- [ ] **Step 1: Write the transition matrix and lineage failure tests**

Use a fixture builder that hashes exact predecessor bytes and changes only the requested rows:

```python
def next_report(previous: str, current_body: str, *, revision: int = 2) -> str:
    digest = hashlib.sha256(previous.encode("utf-8")).hexdigest()
    return current_body.replace("| RPT-001 | 1 | none |", f"| RPT-001 | {revision} | {digest} |", 1)

def test_same_blocked_state_is_unchanged(self):
    previous = report_with_state("blocked", delta="new")
    current = next_report(previous, report_with_state("blocked", delta="unchanged"))
    self.assertEqual(validate_report(current, previous_text=previous, previous_bytes=previous.encode()), [])

def test_terminal_impact_returning_active_is_reopened(self):
    previous = report_with_state("resolved", delta="new")
    current = next_report(previous, report_with_state("refining", delta="reopened"))
    previous_report, previous_errors = parse_report(previous)
    current_report, current_errors = parse_report(current)
    self.assertEqual(previous_errors + current_errors, [])
    self.assertEqual(calculate_delta(previous_report, current_report)["reopened"], ["IMP-001"])
```

Add subtests for all precedence rules: new ID; terminal-to-active reopened; identical state unchanged; changed-to mitigated, resolved, accepted, deferred, blocked, and superseded. Add failures for changed Report ID, skipped revision, wrong digest, later revision without predecessor, unexplained deletion, false new, and authored/computed mismatch.

- [ ] **Step 2: Run the lineage suite and confirm RED**

Run:

```bash
python3 -m unittest tests.test_report_lineage -v
```

Expected: errors because lineage and transition APIs do not exist and `reopened` is not a Delta category.

- [ ] **Step 3: Implement deterministic lineage and Delta functions**

Add these public interfaces and use tuples sorted by numeric impact ID:

```python
DELTA_CATEGORIES = (
    "resolved", "mitigated", "unchanged", "accepted", "deferred",
    "blocked", "superseded", "reopened", "new",
)
TERMINAL_STATES = {"resolved", "accepted", "superseded"}
ACTIVE_STATES = {"detected", "refining", "mitigated", "deferred", "blocked"}

def calculate_delta(
    previous: ParsedReport | None,
    current: ParsedReport,
) -> dict[str, list[str]]:
    result = {category: [] for category in DELTA_CATEGORIES}
    previous_states = impact_states(previous) if previous else {}
    for impact_id, current_state in impact_states(current).items():
        previous_state = previous_states.get(impact_id)
        if previous_state is None:
            category = "new"
        elif previous_state in TERMINAL_STATES and current_state in ACTIVE_STATES:
            category = "reopened"
        elif previous_state == current_state:
            category = "unchanged"
        else:
            category = current_state
        result[category].append(impact_id)
    for ids in result.values():
        ids.sort(key=lambda value: int(value.removeprefix("IMP-")))
    return result

def validate_lineage(
    previous: ParsedReport,
    current: ParsedReport,
    previous_bytes: bytes,
) -> list[str]:
    errors: list[str] = []
    if current.metadata.report_id != previous.metadata.report_id:
        errors.append("current Report ID must match previous Report ID")
    if current.metadata.revision != previous.metadata.revision + 1:
        errors.append(
            f"current revision {current.metadata.revision} must follow previous revision {previous.metadata.revision} exactly"
        )
    digest = hashlib.sha256(previous_bytes).hexdigest()
    if current.metadata.previous_sha256 != digest:
        errors.append("Previous SHA-256 does not match predecessor bytes")
    missing = sorted(set(impact_states(previous)) - set(impact_states(current)))
    errors.extend(f"impact {impact_id} disappeared; retain it or mark it superseded" for impact_id in missing)
    return errors

def render_delta(delta: Mapping[str, Sequence[str]]) -> str:
    rows = ["| Category | Impact IDs |", "| --- | --- |"]
    for category in DELTA_CATEGORIES:
        ids = ", ".join(delta[category]) or "none"
        rows.append(f"| {category} | {ids} |")
    return "\n".join(rows)
```

Implement the spec's precedence literally. Reject every previous impact absent from the current ledger; do not infer an implicit supersession. Compare the authored Delta against the calculated mapping after both individual reports pass structural parsing.

- [ ] **Step 4: Run transition, semantic, and full suites**

Run:

```bash
python3 -m unittest tests.test_report_lineage tests.test_semantic_validation tests.test_validate_impact_report -v
python3 -m unittest discover -s tests -v
```

Expected: all tests pass and error output remains deterministic.

- [ ] **Step 5: Commit lineage calculation**

```bash
git add skills/requirements-impact-refiner/scripts/impact_report.py tests/test_report_lineage.py
git commit -m "feat: compare impact report revisions"
```

### Task 4: CLI and Canonical v0.3 Templates

**Files:**
- Modify: `skills/requirements-impact-refiner/scripts/validate-impact-report.py`
- Modify: `skills/requirements-impact-refiner/assets/impact-report-pre-decision-template.md`
- Modify: `skills/requirements-impact-refiner/assets/impact-report-post-decision-template.md`
- Modify: `skills/requirements-impact-refiner/assets/impact-report-template.md`
- Modify: `tests/test_report_lineage.py`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Consumes: `REPORT.md`, optional `--previous PREVIOUS.md`, optional `--print-expected-delta`.
- Produces: exit 0 plus `valid impact report`; exit 1 plus sorted report errors; exit 2 for argument or file-read errors; deterministic Markdown Delta on stdout when requested.

- [ ] **Step 1: Write subprocess tests for the complete CLI contract**

Add tests that create exact temporary files and invoke the script:

```python
result = subprocess.run(
    [sys.executable, str(SCRIPT), "--previous", str(previous), "--print-expected-delta", str(current)],
    text=True,
    capture_output=True,
    check=False,
)
self.assertEqual(result.returncode, 0)
self.assertIn("| reopened | IMP-001 |", result.stdout)
self.assertEqual(previous.read_bytes(), previous_before)
self.assertEqual(current.read_bytes(), current_before)
```

Also assert exit 2 for a missing file and invalid option, exit 1 for a wrong SHA or Delta mismatch, and standalone rejection of Revision 2.

- [ ] **Step 2: Run CLI tests and confirm RED**

Run:

```bash
python3 -m unittest tests.test_report_lineage.ReportLineageCliTest -v
```

Expected: argparse options are rejected by the old two-argument CLI.

- [ ] **Step 3: Implement the thin argparse CLI**

Use this parser and exact-byte flow:

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a requirements impact report")
    parser.add_argument("report", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--print-expected-delta", action="store_true")
    return parser

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        current_bytes = args.report.read_bytes()
        previous_bytes = args.previous.read_bytes() if args.previous else None
        current_text = current_bytes.decode("utf-8")
        previous_text = previous_bytes.decode("utf-8") if previous_bytes else None
    except (OSError, UnicodeDecodeError) as error:
        print(f"cannot read report: {error}", file=sys.stderr)
        return 2
    errors = validate_report(current_text, previous_text=previous_text, previous_bytes=previous_bytes)
    if args.print_expected_delta:
        current_report, current_errors = parse_report(current_text)
        previous_report = None
        previous_errors: list[str] = []
        if previous_text is not None:
            previous_report, previous_errors = parse_report(previous_text)
        if not current_errors and not previous_errors:
            print(render_delta(calculate_delta(previous_report, current_report)))
    if errors:
        for error in sorted(set(errors)):
            print(error, file=sys.stderr)
        return 1
    print("valid impact report")
    return 0
```

Replace the comments in the sketch with explicit calls to `parse_report`, `calculate_delta`, and `render_delta`.

- [ ] **Step 4: Upgrade both templates and the chooser**

Give both templates the four-column Report State, add `reopened` between `superseded` and `new`, use taxonomy categories and exact severity values, require substantive evidence/scope/handoff cells, and make Revision 1 list the sample impact under `new`. Add all three commands to the chooser and state that later reports require exact predecessor bytes.

Update packaging tests to require:

```python
self.assertIn("| Report ID | Revision | Previous SHA-256 | Phase |", text)
self.assertIn("| reopened |", text)
self.assertIn("--previous", chooser)
self.assertIn("--print-expected-delta", chooser)
self.assertTrue((scripts / "impact_report.py").is_file())
```

- [ ] **Step 5: Validate canonical fixtures and template schema, then run the full suite**

Run:

```bash
python3 -m unittest tests.test_validate_impact_report.ValidateImpactReportTest.test_complete_template_report_is_valid tests.test_validate_impact_report.ValidateImpactReportTest.test_template_code_formatted_identifiers_are_valid tests.test_packaging.PackagingTest.test_stage_templates_are_disjoint_and_complete -v
python3 -m unittest discover -s tests -v
```

Expected: canonical fixtures with real identifiers validate, and untouched assets pass schema/placeholder contract checks without being misrepresented as completed reports.

- [ ] **Step 6: Commit the public schema and CLI**

```bash
git add skills/requirements-impact-refiner/scripts/validate-impact-report.py skills/requirements-impact-refiner/assets tests/test_report_lineage.py tests/test_packaging.py
git commit -m "feat: expose lineage-aware report validation"
```

### Task 5: Skill Instructions and Behavioral Pressure

**Files:**
- Modify: `skills/requirements-impact-refiner/SKILL.md`
- Modify: `skills/requirements-impact-refiner/references/evidence-model.md`
- Modify: `skills/requirements-impact-refiner/references/refinement-loop.md`
- Modify: `skills/using-requirements-impact-refiner/SKILL.md`
- Create: `evals/v0.3-cases.json`
- Modify: `tests/test_eval_cases.py`
- Modify: `tests/test_integration_adapters.py`

**Interfaces:**
- Consumes: approved design, optional previous v0.3 Markdown report, repository evidence, and one selected orchestrator.
- Produces: a Revision 1 baseline or consecutive report whose authored Delta matches the deterministic comparator; no planning or implementation output.

- [ ] **Step 1: Use the writing-skills discipline to define RED pressure cases**

Add three two-turn cases to `evals/v0.3-cases.json`:

```json
{
  "cases": [
    {"id":"LINEAGE-stable-blocked","first_state":"blocked","second_state":"blocked","must_delta":"unchanged"},
    {"id":"LINEAGE-reopened","first_state":"resolved","second_state":"refining","must_delta":"reopened"},
    {"id":"LINEAGE-no-false-resolution","first_state":"refining","second_state":"resolved-without-evidence","must_reject":"unsupported resolution"}
  ]
}
```

Extend `tests/test_eval_cases.py` to require exactly these IDs and fields. Before editing the skill, run fresh independent agents against copies of the current v0.2 skill in isolated temporary directories and record whether they preserve Report ID, revision, predecessor digest, and expected transition. These are RED behavioral observations, not release evidence.

- [ ] **Step 2: Update the core skill with the minimum decision-changing guidance**

Replace current-state Delta language with concise rules:

```markdown
Before creating a report, locate the latest v0.3 report for this change. If none exists, create Revision 1 with a new stable `RPT-###`, predecessor `none`, and every impact under `new`. Otherwise preserve the Report ID, increment revision by one, hash the exact predecessor bytes, preserve every known impact ID, and compute transition Delta. Never fabricate unavailable lineage.

When Python is available, run `validate-impact-report.py --previous PREVIOUS.md CURRENT.md`. Without it, apply the same rules conceptually, disclose that deterministic validation was not run, and do not claim verification.
```

Add the transition precedence, semantic stop conditions, and report-only boundary. Keep the core entrypoint below 500 words and preserve its current description exclusions.

- [ ] **Step 3: Update supporting references without duplicating the core**

In `evidence-model.md`, add `RPT-###`, stable impact identity, reopened semantics, evidence-basis requirements, and the rule that acceptance targets are not resolution evidence. In `refinement-loop.md`, show baseline discovery, previous-report comparison, validation, decision refinement, and report handoff. Leave all four integration adapters' Entry, Ownership, Output, and Exit sequences unchanged.

Update both skills' metadata version to 0.3.0 but keep bootstrap lines 12–18 behaviorally unchanged except where the new version requires a lineage handoff phrase.

- [ ] **Step 4: Run static contracts and repeat pressure scenarios**

Run:

```bash
python3 -m unittest tests.test_eval_cases tests.test_integration_adapters tests.test_packaging -v
python3 /Users/p042890/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/requirements-impact-refiner
python3 /Users/p042890/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/using-requirements-impact-refiner
```

Then repeat each v0.3 pressure case with a fresh independent agent and the updated skill. Require all three to satisfy the defined transition/rejection contract. Record exact prompts, outputs, client/model identity when available, repetition count, and deviations for Task 7; do not tune against unrelated wording.

- [ ] **Step 5: Commit the skill behavior**

```bash
git add skills/requirements-impact-refiner/SKILL.md skills/requirements-impact-refiner/references/evidence-model.md skills/requirements-impact-refiner/references/refinement-loop.md skills/using-requirements-impact-refiner/SKILL.md evals/v0.3-cases.json tests/test_eval_cases.py tests/test_integration_adapters.py
git commit -m "feat: track impact report lineage in the skill"
```

### Task 6: Versioned Packaging and Multilingual Documentation

**Files:**
- Modify: `.codex-plugin/plugin.json`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `README.ko.md`
- Modify: `README.ja.md`
- Modify: `CONTRIBUTING.md`
- Modify: `tests/test_packaging.py`
- Modify: `tests/test_documentation.py`

**Interfaces:**
- Consumes: finalized v0.3 schema and commands.
- Produces: synchronized plugin metadata, installation/upgrade guidance, migration checklist, CI, and bounded compatibility claims.

- [ ] **Step 1: Write failing parity and release tests**

Change packaging expectations to `0.3.0`. Extend documentation tests with shared tokens and commands:

```python
for name in READMES:
    text = (ROOT / name).read_text(encoding="utf-8")
    for token in (
        "0.3.0", "RPT-###", "Previous SHA-256", "reopened",
        "--previous", "--print-expected-delta", "Revision 1",
    ):
        self.assertIn(token, text, f"{token} missing from {name}")
```

Add a test that all three documents state v0.2 is historical, migration is manual, and Claude remains not verified or blocked.

- [ ] **Step 2: Run packaging/documentation tests and confirm RED**

Run:

```bash
python3 -m unittest tests.test_packaging tests.test_documentation -v
```

Expected: failures on old versions and missing lineage/migration content.

- [ ] **Step 3: Update manifests, CI, and English authority**

Set both manifest versions to `0.3.0`. Add domain-module compilation to CI:

```yaml
- name: Compile report tools
  run: |
    python3 -m py_compile skills/requirements-impact-refiner/scripts/impact_report.py
    python3 -m py_compile skills/requirements-impact-refiner/scripts/validate-impact-report.py
```

Update README sections 2, 4, 8, and 9 with lineage identity, transition examples, exact commands, strict v0.2 transition policy, and validator limitations. Preserve all ten numbered sections and existing compatibility scores unless new evidence supersedes them.

- [ ] **Step 4: Apply equivalent Korean and Japanese updates**

Translate the new schema and migration meaning, while preserving these literal cross-language tokens: `0.3.0`, `RPT-###`, `Previous SHA-256`, `reopened`, `--previous`, `--print-expected-delta`, `Revision 1`, product names, versions, and compatibility statuses. Update `CONTRIBUTING.md` with both Python modules, lineage tests, RED/GREEN behavioral runs, and raw-evidence preservation rules.

- [ ] **Step 5: Run documentation, packaging, and full tests**

Run:

```bash
python3 -m unittest tests.test_packaging tests.test_documentation -v
python3 -m unittest discover -s tests -v
python3 -m py_compile skills/requirements-impact-refiner/scripts/impact_report.py skills/requirements-impact-refiner/scripts/validate-impact-report.py
```

Expected: all tests and compilation pass; compatibility table identity/status rows remain identical across languages.

- [ ] **Step 6: Commit release documentation**

```bash
git add .codex-plugin/plugin.json .claude-plugin/plugin.json .github/workflows/ci.yml README.md README.ko.md README.ja.md CONTRIBUTING.md tests/test_packaging.py tests/test_documentation.py
git commit -m "docs: publish the v0.3 report protocol"
```

### Task 7: Behavioral Evidence and Local Release Verification

**Files:**
- Create: `evals/results/state-machine-v0.3.md`
- Modify only if required by new raw artifacts: `.gitattributes`
- Modify only if required by tracked evidence: `tests/test_release_compatibility_evidence.py`

**Interfaces:**
- Consumes: completed v0.3 skill, fixtures, deterministic tests, and fresh-agent transcripts.
- Produces: an auditable result ledger and a locally verified release candidate; no push, publication, or installation.

- [ ] **Step 1: Preserve behavioral artifacts and write the result ledger**

Record each case with this exact evidence shape:

```markdown
| Case | Client/model | Repetitions | Report ID preserved | Revision/hash valid | Expected Delta | Unsupported claim rejected | Result |
| --- | --- | ---: | --- | --- | --- | --- | --- |
```

If raw transcripts are committed, place them under `evals/results/state-machine-v0.3-raw/`, add `-text -whitespace` attributes, create a SHA-256 manifest, and test the exact inventory. Do not edit or copy-reformat any existing raw corpus.

- [ ] **Step 2: Run final deterministic verification**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile skills/requirements-impact-refiner/scripts/impact_report.py skills/requirements-impact-refiner/scripts/validate-impact-report.py
python3 /Users/p042890/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/requirements-impact-refiner
python3 /Users/p042890/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/using-requirements-impact-refiner
git diff --check
git status --short
```

Expected: full suite, both compilations, and both quick validations pass; whitespace check is clean outside explicitly disclosed raw-byte findings; only intended evidence files are uncommitted before the final commit.

- [ ] **Step 3: Perform independent review against the spec and impact report**

Use `superpowers:requesting-code-review`. The reviewer must probe at least: headings-only reports; blank semantic fields; wrong/uppercase/normalized hashes; Revision 2 without `--previous`; disappeared impacts; duplicate IDs in one Delta cell; false `new`; stable blocked state; reopened terminal state; unresolved ownership; and activation exclusions. Fix every P0–P2 finding with TDD and rerun the full verification commands.

- [ ] **Step 4: Commit the verified evidence**

```bash
git add evals/results/state-machine-v0.3.md .gitattributes tests/test_release_compatibility_evidence.py
git commit -m "test: record v0.3 lineage behavior"
```

Stage `.gitattributes` and the evidence test only when Task 7 actually added raw artifacts; otherwise commit only the result ledger.

- [ ] **Step 5: Report local readiness without external mutation**

Report the exact final test count, quick-validator outcomes, behavioral repetition count, any blocked client paths, commit range, and clean working-tree status. State explicitly that GitHub push and local plugin upgrade were not performed and require the user's next instruction.
