import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT
    / "skills"
    / "requirements-impact-refiner"
    / "scripts"
    / "validate-impact-report.py"
)
SPEC = importlib.util.spec_from_file_location("validate_impact_report", SCRIPT_PATH)
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


EXPECTED_ERRORS = {
    "duplicate": "duplicate identifier IMP-001",
    "dangling": "unknown reference DEC-999",
    "malformed_id": "invalid identifier IMP-1",
    "state": "invalid impact state ignored",
    "evidence_level": "invalid evidence level certain",
    "missing_requirement": "impact IMP-001 requires REQ reference",
    "resolved_without_evidence": "resolved impact IMP-001 requires evidence",
    "accepted_without_decision": "accepted impact IMP-001 requires DEC reference",
    "critical_without_ac": "critical impact IMP-001 requires AC reference",
    "missing_limitations": "missing section: Analysis Scope and Limitations",
    "unresolved_accepted": "invalid impact state accepted",
}


VALID_REPORT = """# Requirements Impact Report

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| REQ-001 | Preserve existing exports while adding sharing. | Product request |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| REQ-001 | Add sharing without changing exports. | DEC-001 | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| INV-001 | Existing exports remain private. | verified | tests/test_exports.py |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| INV-001 | REQ-001 | IMP-001 | tests/test_exports.py |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IMP-001 | REQ-001 | contract | critical | accepted | verified | tests/test_exports.py | INV-001 | DEC-001 | AC-001 |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| DEC-001 | Preserve private export default. | REQ-001 | IMP-001 | Avoid regression. |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| REQ-001 | Add sharing with private defaults. | DEC-001 | — | Narrowed scope. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| AC-001 | REQ-001 | IMP-001 | INV-001 | Existing exports stay private. | tests/test_exports.py |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Export and sharing paths only. | tests/test_exports.py | Other paths remain unknown. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| REQ-001 | INV-001, IMP-001, DEC-001 | Accepted IMP-001 | AC-001 | Existing planning workflow |
"""


class ValidateImpactReportTest(unittest.TestCase):
    def test_complete_template_report_is_valid(self):
        self.assertEqual(VALIDATOR.validate_report(VALID_REPORT), [])

    def test_template_code_formatted_identifiers_are_valid(self):
        code_formatted_report = re.sub(
            r"\b(?:REQ|INV|IMP|DEC|AC)-\d{3}\b",
            lambda match: f"`{match.group(0)}`",
            VALID_REPORT,
        )
        self.assertEqual(VALIDATOR.validate_report(code_formatted_report), [])

    def test_rejects_missing_or_wrong_canonical_title(self):
        mutations = {
            "missing": VALID_REPORT.replace("# Requirements Impact Report\n\n", "", 1),
            "wrong": VALID_REPORT.replace(
                "# Requirements Impact Report", "# Requirement Review", 1
            ),
        }

        for name, report in mutations.items():
            with self.subTest(name=name):
                self.assertIn(
                    "missing canonical title: # Requirements Impact Report",
                    VALIDATOR.validate_report(report),
                )

    def test_rejects_headings_only_report(self):
        report = "# Requirements Impact Report\n\n" + "\n".join(
            f"## {name}\n" for name in sorted(VALIDATOR.REQUIRED_SECTIONS)
        )

        errors = VALIDATOR.validate_report(report)

        self.assertIn("invalid table schema in Impact Ledger", errors)
        self.assertIn("missing required requirement row", errors)
        self.assertIn("missing required impact row", errors)

    def test_rejects_missing_canonical_table_or_wrong_header(self):
        original_table = (
            "| Requirement ID | Original request | Source |\n"
            "| --- | --- | --- |\n"
            "| REQ-001 | Preserve existing exports while adding sharing. | Product request |"
        )
        mutations = {
            "missing": VALID_REPORT.replace(original_table, "No structured requirement.", 1),
            "wrong_header": VALID_REPORT.replace(
                "| Requirement ID | Original request | Source |",
                "| Requirement | Original request | Source |",
                1,
            ),
        }

        for name, report in mutations.items():
            with self.subTest(name=name):
                self.assertIn(
                    "invalid table schema in Original Requirement",
                    VALIDATOR.validate_report(report),
                )

    def test_rejects_missing_required_definition_or_impact_rows(self):
        rows = {
            "requirement": "| REQ-001 | Preserve existing exports while adding sharing. | Product request |",
            "invariant": "| INV-001 | Existing exports remain private. | verified | tests/test_exports.py |",
            "impact": (
                "| IMP-001 | REQ-001 | contract | critical | accepted | verified | "
                "tests/test_exports.py | INV-001 | DEC-001 | AC-001 |"
            ),
            "criterion": (
                "| AC-001 | REQ-001 | IMP-001 | INV-001 | Existing exports stay private. "
                "| tests/test_exports.py |"
            ),
        }

        for entity, row in rows.items():
            with self.subTest(entity=entity):
                self.assertIn(
                    f"missing required {entity} row",
                    VALIDATOR.validate_report(VALID_REPORT.replace(row, "", 1)),
                )

    def test_rejects_malformed_identifier_like_tokens_in_relationship_cells(self):
        mutations = {
            "preserved_invariant": VALID_REPORT.replace(
                "| INV-001 | REQ-001 | IMP-001 | tests/test_exports.py |",
                "| INV-001 | REQ-001 | IMP-1 | tests/test_exports.py |",
                1,
            ),
            "revision_history": VALID_REPORT.replace(
                "| REQ-001 | Add sharing with private defaults. | DEC-001 | — | Narrowed scope. |",
                "| REQ-001 | Add sharing with private defaults. | DEC-1 | — | Narrowed scope. |",
                1,
            ),
            "planning_handoff": VALID_REPORT.replace(
                "| REQ-001 | INV-001, IMP-001, DEC-001 | Accepted IMP-001 | AC-001 | Existing planning workflow |",
                "| REQ-001 | INV-1, IMP-001, DEC-001 | Accepted IMP-001 | AC-001 | Existing planning workflow |",
                1,
            ),
        }

        for name, report in mutations.items():
            with self.subTest(name=name):
                self.assertTrue(
                    any(error.startswith("invalid identifier ") for error in VALIDATOR.validate_report(report))
                )

    def test_rejects_canonical_placeholder_tokens_left_in_relationship_cells(self):
        mutations = {
            "preserved_invariant": (
                "| INV-001 | REQ-001 | IMP-001 | tests/test_exports.py |",
                "| INV-001 | REQ-001 | IMP-### | tests/test_exports.py |",
                "invalid identifier IMP-###",
            ),
            "revision_history": (
                "| REQ-001 | Add sharing with private defaults. | DEC-001 | — | Narrowed scope. |",
                "| REQ-001 | Add sharing with private defaults. | DEC-### | — | Narrowed scope. |",
                "invalid identifier DEC-###",
            ),
            "planning_handoff": (
                "| REQ-001 | INV-001, IMP-001, DEC-001 | Accepted IMP-001 | AC-001 | Existing planning workflow |",
                "| REQ-001 | INV-###, IMP-001, DEC-001 | Accepted IMP-001 | AC-001 | Existing planning workflow |",
                "invalid identifier INV-###",
            ),
        }

        for name, (old, new, expected_error) in mutations.items():
            with self.subTest(name=name):
                self.assertIn(
                    expected_error,
                    VALIDATOR.validate_report(VALID_REPORT.replace(old, new, 1)),
                )

    def test_identifier_candidate_scan_ignores_embedded_normal_prose_and_code(self):
        report = VALID_REPORT.replace(
            "Other paths remain unknown.",
            "FREQ-### prose, someIMP-###Helper, AC-001_test, and requirements-impact-refiner.",
            1,
        )

        self.assertEqual(VALIDATOR.validate_report(report), [])

    def test_rejects_malformed_table_row_instead_of_silently_skipping_it(self):
        malformed = VALID_REPORT.replace(
            "| REQ-001 | Preserve existing exports while adding sharing. | Product request |",
            "| REQ-001 | Preserve existing exports while adding sharing. | Product request | extra |",
            1,
        )

        self.assertIn(
            "malformed table row in Original Requirement: expected 3 cells, got 4",
            VALIDATOR.validate_report(malformed),
        )

    def test_rejects_each_invalid_report_contract(self):
        impact_row = (
            "| IMP-001 | REQ-001 | contract | critical | accepted | verified | "
            "tests/test_exports.py | INV-001 | DEC-001 | AC-001 |"
        )
        mutations = {
            "duplicate": VALID_REPORT.replace(impact_row, f"{impact_row}\n{impact_row}"),
            "dangling": VALID_REPORT.replace(
                "| INV-001 | DEC-001 | AC-001 |",
                "| INV-001 | DEC-999 | AC-001 |",
                1,
            ),
            "malformed_id": VALID_REPORT.replace("| IMP-001 | REQ-001 |", "| IMP-1 | REQ-001 |", 1),
            "state": VALID_REPORT.replace("| critical | accepted |", "| critical | ignored |", 1),
            "evidence_level": VALID_REPORT.replace("| accepted | verified |", "| accepted | certain |", 1),
            "missing_requirement": VALID_REPORT.replace("| IMP-001 | REQ-001 |", "| IMP-001 | — |", 1),
            "resolved_without_evidence": VALID_REPORT.replace(
                "| accepted | verified | tests/test_exports.py |",
                "| resolved | verified |  |",
                1,
            ),
            "accepted_without_decision": VALID_REPORT.replace(
                "| INV-001 | DEC-001 | AC-001 |",
                "| INV-001 |  | AC-001 |",
                1,
            ),
            "critical_without_ac": VALID_REPORT.replace(
                "| INV-001 | DEC-001 | AC-001 |",
                "| INV-001 | DEC-001 |  |",
                1,
            ),
            "missing_limitations": VALID_REPORT.replace(
                "## Analysis Scope and Limitations",
                "## Removed Scope Section",
                1,
            ),
        }

        for name, report in mutations.items():
            with self.subTest(name=name):
                self.assertIn(EXPECTED_ERRORS[name], VALIDATOR.validate_report(report))

    def test_rejects_invalid_current_behavior_evidence_level(self):
        report = VALID_REPORT.replace(
            "| INV-001 | Existing exports remain private. | verified | tests/test_exports.py |",
            "| INV-001 | Existing exports remain private. | certain | tests/test_exports.py |",
            1,
        )

        self.assertIn(EXPECTED_ERRORS["evidence_level"], VALIDATOR.validate_report(report))

    def test_rejects_invalid_unresolved_item_state(self):
        report = VALID_REPORT.replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | ignored | Still under review. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        )

        self.assertIn(EXPECTED_ERRORS["state"], VALIDATOR.validate_report(report))

    def test_accepts_code_formatted_enums_and_matching_unresolved_state(self):
        report = VALID_REPORT.replace(
            "| INV-001 | Existing exports remain private. | verified | tests/test_exports.py |",
            "| INV-001 | Existing exports remain private. | `verified` | tests/test_exports.py |",
            1,
        ).replace(
            "| critical | accepted | verified |",
            "| critical | `blocked` | `verified` |",
            1,
        ).replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | `blocked` | Waiting for product input. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        )

        self.assertEqual(VALIDATOR.validate_report(report), [])

    def test_rejects_duplicate_unresolved_impact_rows(self):
        report = VALID_REPORT.replace(
            "| critical | accepted | verified |",
            "| critical | blocked | verified |",
            1,
        ).replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | blocked | Waiting for product input. | DEC-001 | Product |\n"
            "| IMP-001 | blocked | Duplicate entry. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        )

        self.assertIn("duplicate unresolved impact IMP-001", VALIDATOR.validate_report(report))

    def test_rejects_unresolved_state_that_disagrees_with_ledger(self):
        report = VALID_REPORT.replace(
            "| critical | accepted | verified |",
            "| critical | deferred | verified |",
            1,
        ).replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | blocked | Waiting for product input. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        )

        self.assertIn(
            "unresolved impact IMP-001 state blocked disagrees with ledger state deferred",
            VALIDATOR.validate_report(report),
        )

    def test_rejects_non_unresolved_ledger_impact_listed_as_unresolved(self):
        report = VALID_REPORT.replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | blocked | Already accepted. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        )

        self.assertIn(
            "unresolved impact IMP-001 state blocked disagrees with ledger state accepted",
            VALIDATOR.validate_report(report),
        )

    def test_rejects_blocked_or_deferred_ledger_impact_missing_from_unresolved_items(self):
        report = VALID_REPORT.replace(
            "| critical | accepted | verified |",
            "| critical | blocked | verified |",
            1,
        )

        self.assertIn(
            "ledger impact IMP-001 in state blocked is missing from unresolved items",
            VALIDATOR.validate_report(report),
        )

    def test_requires_at_least_one_impact_with_requirement_relationship(self):
        report = VALID_REPORT.replace("| IMP-001 | REQ-001 |", "| IMP-001 | — |", 1)

        self.assertIn("report requires at least one impact with REQ relationship", VALIDATOR.validate_report(report))

    def test_rejects_accepted_state_in_unresolved_items(self):
        report = VALID_REPORT.replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | accepted | Already decided. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        )

        self.assertIn(
            EXPECTED_ERRORS["unresolved_accepted"],
            VALIDATOR.validate_report(report),
        )

    def test_validate_path_and_cli_report_success_and_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            valid_path = Path(temp_dir) / "valid.md"
            invalid_path = Path(temp_dir) / "invalid.md"
            valid_path.write_text(VALID_REPORT, encoding="utf-8")
            invalid_path.write_text(
                VALID_REPORT.replace("| critical | accepted |", "| critical | ignored |", 1),
                encoding="utf-8",
            )

            self.assertEqual(VALIDATOR.validate_path(valid_path), [])
            success = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), str(valid_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            failure = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), str(invalid_path)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(success.returncode, 0)
        self.assertEqual(success.stdout.strip(), "valid impact report")
        self.assertEqual(failure.returncode, 1)
        self.assertIn(EXPECTED_ERRORS["state"], failure.stderr)


if __name__ == "__main__":
    unittest.main()
