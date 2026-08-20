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

    def test_accepts_code_formatted_enums_and_allowed_unresolved_states(self):
        report = VALID_REPORT.replace(
            "| INV-001 | Existing exports remain private. | verified | tests/test_exports.py |",
            "| INV-001 | Existing exports remain private. | `verified` | tests/test_exports.py |",
            1,
        ).replace(
            "| critical | accepted | verified |",
            "| critical | `accepted` | `verified` |",
            1,
        ).replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | `blocked` | Waiting for product input. | DEC-001 | Product |\n"
            "| IMP-001 | `deferred` | Scheduled for a later release. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        )

        self.assertEqual(VALIDATOR.validate_report(report), [])

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
