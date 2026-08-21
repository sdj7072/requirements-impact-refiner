import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.test_validate_impact_report import VALIDATOR, VALID_REPORT


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "skills"
    / "requirements-impact-refiner"
    / "scripts"
    / "validate-impact-report.py"
)


IMPACT_ROW = (
    "| IMP-001 | REQ-001 | interfaces | critical | accepted | verified | "
    "tests/test_exports.py | INV-001 | DEC-001 | AC-001 |"
)


def report_with_state(state, delta="new"):
    report = VALID_REPORT.replace(
        IMPACT_ROW,
        IMPACT_ROW.replace("| accepted |", f"| {state} |"),
        1,
    )
    if delta != "new":
        report = report.replace("| new | IMP-001 |", "| new | none |", 1)
        report = report.replace(
            f"| {delta} | none |", f"| {delta} | IMP-001 |", 1
        )
    if state in {"blocked", "deferred"}:
        report = report.replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            f"| IMP-001 | {state} | Waiting for evidence. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        ).replace("| Existing planning workflow |", "| Not ready |", 1)
    return report


def next_report(previous, current_body, revision=2):
    digest = hashlib.sha256(previous.encode("utf-8")).hexdigest()
    return current_body.replace(
        "| RPT-001 | 1 | none |",
        f"| RPT-001 | {revision} | {digest} |",
        1,
    )


class ReportLineageTest(unittest.TestCase):
    def parsed(self, text):
        report, errors = VALIDATOR.parse_report(text)
        self.assertEqual(errors, [])
        return report

    def test_baseline_calculates_every_impact_as_new(self):
        delta = VALIDATOR.calculate_delta(None, self.parsed(VALID_REPORT))

        self.assertEqual(delta["new"], ["IMP-001"])
        self.assertTrue(all(not ids for category, ids in delta.items() if category != "new"))

    def test_same_blocked_state_is_unchanged(self):
        previous = report_with_state("blocked")
        current = next_report(
            previous, report_with_state("blocked", delta="unchanged")
        )

        self.assertEqual(
            VALIDATOR.validate_report(
                current,
                previous_text=previous,
                previous_bytes=previous.encode("utf-8"),
            ),
            [],
        )


class ReportLineageCliTest(unittest.TestCase):
    def parsed(self, text):
        report, errors = VALIDATOR.parse_report(text)
        self.assertEqual(errors, [])
        return report

    def test_comparison_prints_expected_delta_without_modifying_reports(self):
        previous_text = VALID_REPORT
        current_text = next_report(
            previous_text, report_with_state("accepted", "unchanged")
        )
        with tempfile.TemporaryDirectory() as directory:
            previous = Path(directory) / "previous.md"
            current = Path(directory) / "current.md"
            previous.write_text(previous_text, encoding="utf-8")
            current.write_text(current_text, encoding="utf-8")
            previous_before = previous.read_bytes()
            current_before = current.read_bytes()

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--previous",
                    str(previous),
                    "--print-expected-delta",
                    str(current),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(previous.read_bytes(), previous_before)
            self.assertEqual(current.read_bytes(), current_before)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| unchanged | IMP-001 |", result.stdout)
        self.assertIn("valid impact report", result.stdout)

    def test_report_errors_return_one_and_invocation_errors_return_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = root / "previous.md"
            wrong_sha = root / "wrong-sha.md"
            previous.write_text(VALID_REPORT, encoding="utf-8")
            wrong_sha.write_text(
                next_report(
                    VALID_REPORT, report_with_state("accepted", "unchanged")
                ).replace(hashlib.sha256(VALID_REPORT.encode()).hexdigest(), "0" * 64),
                encoding="utf-8",
            )
            report_error = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--previous",
                    str(previous),
                    str(wrong_sha),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            missing_file = subprocess.run(
                [sys.executable, str(SCRIPT), str(root / "missing.md")],
                text=True,
                capture_output=True,
                check=False,
            )
            invalid_option = subprocess.run(
                [sys.executable, str(SCRIPT), "--not-a-real-option"],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(report_error.returncode, 1)
        self.assertIn(
            "Previous SHA-256 does not match predecessor bytes",
            report_error.stderr,
        )
        self.assertEqual(missing_file.returncode, 2)
        self.assertIn("cannot read report", missing_file.stderr)
        self.assertEqual(invalid_option.returncode, 2)

    def test_invalid_lifecycle_state_returns_errors_without_traceback(self):
        previous_text = VALID_REPORT
        invalid_current = next_report(
            previous_text,
            report_with_state("invalid-state", "unchanged"),
        )

        errors = VALIDATOR.validate_report(
            invalid_current,
            previous_text=previous_text,
            previous_bytes=previous_text.encode("utf-8"),
        )
        self.assertIn("invalid impact state invalid-state", errors)

        with tempfile.TemporaryDirectory() as directory:
            previous = Path(directory) / "previous.md"
            current = Path(directory) / "current.md"
            previous.write_text(previous_text, encoding="utf-8")
            current.write_text(invalid_current, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--previous",
                    str(previous),
                    "--print-expected-delta",
                    str(current),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid impact state invalid-state", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_terminal_impact_returning_active_is_reopened(self):
        previous = report_with_state("resolved")
        current = next_report(
            previous, report_with_state("refining", delta="reopened")
        )

        delta = VALIDATOR.calculate_delta(
            self.parsed(previous), self.parsed(current)
        )
        self.assertEqual(delta["reopened"], ["IMP-001"])

    def test_changed_states_use_the_current_state_category(self):
        for state in (
            "mitigated",
            "resolved",
            "accepted",
            "deferred",
            "blocked",
            "superseded",
        ):
            with self.subTest(state=state):
                previous = report_with_state("refining")
                current = next_report(
                    previous, report_with_state(state, delta=state)
                )
                delta = VALIDATOR.calculate_delta(
                    self.parsed(previous), self.parsed(current)
                )
                self.assertEqual(delta[state], ["IMP-001"])

    def test_detected_and_refining_remain_active_unchanged_categories(self):
        previous = report_with_state("detected")
        current = next_report(
            previous, report_with_state("refining", delta="unchanged")
        )

        delta = VALIDATOR.calculate_delta(
            self.parsed(previous), self.parsed(current)
        )
        self.assertEqual(delta["unchanged"], ["IMP-001"])

    def test_lineage_requires_same_id_next_revision_and_exact_sha(self):
        previous = VALID_REPORT
        valid = next_report(previous, report_with_state("accepted", "unchanged"))
        valid_parsed = self.parsed(valid)
        previous_parsed = self.parsed(previous)

        self.assertEqual(
            VALIDATOR.validate_lineage(
                previous_parsed, valid_parsed, previous.encode("utf-8")
            ),
            [],
        )
        wrong_id = valid.replace("| RPT-001 | 2 |", "| RPT-002 | 2 |", 1)
        skipped = valid.replace("| RPT-001 | 2 |", "| RPT-001 | 3 |", 1)
        uppercase_sha = valid.replace(
            hashlib.sha256(previous.encode()).hexdigest(),
            hashlib.sha256(previous.encode()).hexdigest().upper(),
            1,
        )
        wrong_sha = valid.replace(
            hashlib.sha256(previous.encode()).hexdigest(), "0" * 64, 1
        )

        self.assertIn(
            "current Report ID must match previous Report ID",
            VALIDATOR.validate_lineage(
                previous_parsed, self.parsed(wrong_id), previous.encode()
            ),
        )
        self.assertIn(
            "current revision 3 must follow previous revision 1 exactly",
            VALIDATOR.validate_lineage(
                previous_parsed, self.parsed(skipped), previous.encode()
            ),
        )
        _, uppercase_errors = VALIDATOR.parse_report(uppercase_sha)
        self.assertIn(
            "later revision requires lowercase 64-character Previous SHA-256",
            uppercase_errors,
        )
        self.assertIn(
            "Previous SHA-256 does not match predecessor bytes",
            VALIDATOR.validate_lineage(
                previous_parsed, self.parsed(wrong_sha), previous.encode()
            ),
        )

    def test_later_revision_requires_previous_report(self):
        current = next_report(
            VALID_REPORT, report_with_state("accepted", "unchanged")
        )

        self.assertIn(
            "revision 2 requires --previous",
            VALIDATOR.validate_report(current),
        )

    def test_unexplained_impact_deletion_is_rejected(self):
        previous = VALID_REPORT
        current = next_report(
            previous,
            report_with_state("accepted", "unchanged").replace(IMPACT_ROW, "", 1),
        )

        self.assertIn(
            "impact IMP-001 disappeared; retain it or mark it superseded",
            VALIDATOR.validate_report(
                current,
                previous_text=previous,
                previous_bytes=previous.encode(),
            ),
        )

    def test_authored_delta_must_equal_calculated_delta(self):
        previous = VALID_REPORT
        false_new = next_report(previous, report_with_state("accepted", "new"))

        self.assertIn(
            "impact IMP-001 is marked new but expected unchanged",
            VALIDATOR.validate_report(
                false_new,
                previous_text=previous,
                previous_bytes=previous.encode(),
            ),
        )

    def test_render_delta_is_canonical_and_complete(self):
        rendered = VALIDATOR.render_delta(
            VALIDATOR.calculate_delta(None, self.parsed(VALID_REPORT))
        )

        self.assertEqual(
            rendered,
            "\n".join(
                (
                    "| Category | Impact IDs |",
                    "| --- | --- |",
                    "| resolved | none |",
                    "| mitigated | none |",
                    "| unchanged | none |",
                    "| accepted | none |",
                    "| deferred | none |",
                    "| blocked | none |",
                    "| superseded | none |",
                    "| reopened | none |",
                    "| new | IMP-001 |",
                )
            ),
        )


if __name__ == "__main__":
    unittest.main()
