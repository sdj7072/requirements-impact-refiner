import unittest

from tests.test_validate_impact_report import PRE_DECISION_REPORT, VALIDATOR, VALID_REPORT
from tests.test_report_lineage import report_with_state


SUPERPOWERS_HANDOFF_MARKER = (
    "superpowers:after-approved-brainstorming;impact-refinement;"
    "manual-handoff-before-writing-plans"
)


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

    def test_resolution_requires_evidence_beyond_future_acceptance_target(self):
        report = VALID_REPORT.replace(
            "| critical | accepted | verified | tests/test_exports.py |",
            "| critical | resolved | verified | AC-001 |",
            1,
        )

        self.assert_rejected(
            report,
            "resolved impact IMP-001 requires resolution evidence beyond future acceptance criteria",
        )

    def test_localized_evidence_bases_are_substantive(self):
        for evidence in ("저장소경로와기호", "呼び出し関係からの推論"):
            with self.subTest(evidence=evidence):
                report = VALID_REPORT.replace("tests/test_exports.py", evidence)
                self.assertEqual(VALIDATOR.validate_report(report), [])

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

    def test_superpowers_marker_is_the_only_named_blocked_or_predecision_exception(self):
        """The structured boundary marker may coexist with not-ready state elsewhere."""
        predecision = PRE_DECISION_REPORT.replace(
            "| Not ready |", "| %s |" % SUPERPOWERS_HANDOFF_MARKER, 1
        )
        blocked = report_with_state("blocked").replace(
            "| Not ready |", "| %s |" % SUPERPOWERS_HANDOFF_MARKER, 1
        )

        self.assertEqual(VALIDATOR.validate_report(predecision), [])
        self.assertEqual(VALIDATOR.validate_report(blocked), [])

        arbitrary = PRE_DECISION_REPORT.replace(
            "| Not ready |", "| superpowers |", 1
        )
        self.assert_rejected(
            arbitrary, "pre-decision Planning Handoff workflow must be Not ready"
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

    def test_required_option_decision_and_revision_fields_are_nonempty(self):
        mutations = {
            "pre-decision option requires a nonempty trade-off": PRE_DECISION_REPORT.replace(
                "| Which sharing mechanism should be used? | Expiring signed URLs | IMP-001 | Simple expiry, limited revocation. |",
                "| Which sharing mechanism should be used? | Expiring signed URLs | IMP-001 |  |",
                1,
            ),
            "recorded decision DEC-001 requires a requirement revision": VALID_REPORT.replace(
                "| DEC-001 | Preserve private export default. | REQ-001 | IMP-001 | Avoid regression. |",
                "| DEC-001 | Preserve private export default. |  | IMP-001 | Avoid regression. |",
                1,
            ),
            "recorded decision DEC-001 requires accepted impacts or none": VALID_REPORT.replace(
                "| DEC-001 | Preserve private export default. | REQ-001 | IMP-001 | Avoid regression. |",
                "| DEC-001 | Preserve private export default. | REQ-001 |  | Avoid regression. |",
                1,
            ),
            "requirement history REQ-001 requires a change summary": VALID_REPORT.replace(
                "| REQ-001 | Add sharing with private defaults. | DEC-001 | — | Narrowed scope. |",
                "| REQ-001 | Add sharing with private defaults. | DEC-001 | — |  |",
                1,
            ),
        }

        for expected, report in mutations.items():
            with self.subTest(expected=expected):
                self.assert_rejected(report, expected)


if __name__ == "__main__":
    unittest.main()
