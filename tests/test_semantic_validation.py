import unittest

from tests.test_validate_impact_report import VALIDATOR, VALID_REPORT


class SemanticValidationTest(unittest.TestCase):
    def assert_rejected(self, report, expected):
        self.assertIn(expected, VALIDATOR.validate_report(report))

    def test_rejects_missing_or_unknown_impact_classification(self):
        missing_category = VALID_REPORT.replace(
            "| interfaces | critical |", "|  | critical |", 1
        )
        unknown_category = VALID_REPORT.replace(
            "| interfaces | critical |", "| contract | critical |", 1
        )
        missing_severity = VALID_REPORT.replace(
            "| interfaces | critical |", "| interfaces |  |", 1
        )

        self.assert_rejected(
            missing_category, "impact IMP-001 requires a category"
        )
        self.assert_rejected(
            unknown_category, "impact IMP-001 has invalid category contract"
        )
        self.assert_rejected(
            missing_severity, "impact IMP-001 requires severity"
        )

    def test_rejects_empty_behavior_and_evidence_basis(self):
        empty_behavior = VALID_REPORT.replace(
            "| INV-001 | Existing exports remain private. | verified | tests/test_exports.py |",
            "| INV-001 |  | verified | tests/test_exports.py |",
            1,
        )
        empty_verified_evidence = VALID_REPORT.replace(
            "| INV-001 | Existing exports remain private. | verified | tests/test_exports.py |",
            "| INV-001 | Existing exports remain private. | verified |  |",
            1,
        )

        self.assert_rejected(
            empty_behavior, "invariant INV-001 requires a current behavior"
        )
        self.assert_rejected(
            empty_verified_evidence,
            "invariant INV-001 evidence level verified requires an evidence basis",
        )

    def test_rejects_empty_preserved_invariant_content(self):
        report = VALID_REPORT.replace(
            "| INV-001 | REQ-001 | IMP-001 | tests/test_exports.py |",
            "| INV-001 |  | IMP-001 | tests/test_exports.py |",
            1,
        )

        self.assert_rejected(
            report, "preserved invariant INV-001 requires a requirement link"
        )

    def test_every_active_impact_requires_acceptance_criteria(self):
        report = VALID_REPORT.replace(
            "| interfaces | critical | accepted | verified | tests/test_exports.py | INV-001 | DEC-001 | AC-001 |",
            "| interfaces | high | accepted | verified | tests/test_exports.py | INV-001 | DEC-001 | none |",
            1,
        )

        self.assert_rejected(
            report, "impact IMP-001 requires acceptance criteria"
        )

    def test_rejects_empty_acceptance_observation_or_test(self):
        empty_observation = VALID_REPORT.replace(
            "| AC-001 | REQ-001 | IMP-001 | INV-001 | Existing exports stay private. | tests/test_exports.py |",
            "| AC-001 | REQ-001 | IMP-001 | INV-001 |  | tests/test_exports.py |",
            1,
        )
        empty_test = VALID_REPORT.replace(
            "| AC-001 | REQ-001 | IMP-001 | INV-001 | Existing exports stay private. | tests/test_exports.py |",
            "| AC-001 | REQ-001 | IMP-001 | INV-001 | Existing exports stay private. |  |",
            1,
        )

        self.assert_rejected(
            empty_observation,
            "criterion AC-001 requires a nonempty observable criterion",
        )
        self.assert_rejected(
            empty_test, "criterion AC-001 requires evidence or test"
        )

    def test_rejects_empty_analysis_scope(self):
        report = VALID_REPORT.replace(
            "| Export and sharing paths only. | tests/test_exports.py | Other paths remain unknown. |",
            "|  |  |  |",
            1,
        )

        self.assert_rejected(report, "analysis scope requires a substantive row")

    def test_unresolved_impact_requires_rationale_and_owner(self):
        report = VALID_REPORT.replace(
            "| critical | accepted | verified |",
            "| critical | blocked | verified |",
            1,
        ).replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | blocked |  | DEC-001 |  |\n\n"
            "## Analysis Scope and Limitations",
            1,
        )

        errors = VALIDATOR.validate_report(report)
        self.assertIn("unresolved impact IMP-001 requires a rationale", errors)
        self.assertIn("unresolved impact IMP-001 requires a next owner", errors)

    def test_blocked_impact_keeps_planning_handoff_not_ready(self):
        report = VALID_REPORT.replace(
            "| critical | accepted | verified |",
            "| critical | blocked | verified |",
            1,
        ).replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | blocked | Waiting for product input. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        )

        self.assert_rejected(
            report, "blocked impacts require Planning Handoff workflow Not ready"
        )

    def test_accepted_and_deferred_impacts_remain_named_risks(self):
        report = VALID_REPORT.replace("| Accepted IMP-001 |", "| none |", 1)

        self.assert_rejected(
            report, "remaining risks must name accepted impact IMP-001"
        )

    def test_planning_handoff_requires_every_field(self):
        report = VALID_REPORT.replace(
            "| Existing planning workflow |", "|  |", 1
        )

        self.assert_rejected(
            report, "Planning Handoff requires Selected planning workflow"
        )


if __name__ == "__main__":
    unittest.main()
