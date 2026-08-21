import unittest

from evals.harness.models import Adjudication, CaseSpec, CaseTurn, RunResult, RunStatus
from evals.harness.reporting import render_report, summarize
from evals.harness.scoring import score_mechanical, validate_adjudications
from tests.test_validate_impact_report import PRE_DECISION_REPORT, VALID_REPORT


def case(case_id, kind="positive", transition=None):
    return CaseSpec(
        id=case_id,
        kind=kind,
        turns=(CaseTurn("Evaluate the requirement.", ("src/example.py",)),),
        must_detect=("relevant impact",),
        must_not_do=("write implementation plan",),
        modes=("superpowers",),
        expected_transition=transition,
    )


def result(case_id, status, output=None, repetition=1):
    return RunResult(
        case_id=case_id,
        repetition=repetition,
        client="codex",
        status=status,
        reason=None,
        final_output=output,
    )


class EvalHarnessScoringTest(unittest.TestCase):
    def test_nonpass_statuses_never_count_as_pass(self):
        """Counting partial or blocked output as strict pass would inflate the claim."""
        results_with_every_status = (
            result("POS-one", RunStatus.PASS),
            result("POS-two", RunStatus.PARTIAL),
            result("POS-three", RunStatus.FAIL),
            result("POS-four", RunStatus.BLOCKED),
            result("POS-five", RunStatus.INFRA_ERROR),
            result("POS-six", RunStatus.INVALID_EVIDENCE),
        )

        summary = summarize(results_with_every_status)

        self.assertEqual(summary["strict_passes"], 1)
        self.assertEqual(summary["partial"], 1)
        self.assertEqual(summary["blocked"], 1)
        self.assertEqual(summary["total"], 6)

    def test_adjudication_requires_quote_and_rationale(self):
        """A human conclusion without traceable evidence must remain incomplete."""
        row = Adjudication("POS-authorization", 1, "authorization impact", False, "", "")

        self.assertEqual(
            validate_adjudications([row]),
            ["POS-authorization/01 authorization impact requires quote and rationale"],
        )

    def test_complete_adjudication_keeps_human_judgment_separate(self):
        """A quoted human failure must not rewrite a mechanical result."""
        row = Adjudication(
            "POS-authorization",
            1,
            "authorization impact",
            False,
            "The owner role remains distinct.",
            "The response omits the invitation scope.",
        )

        self.assertEqual(validate_adjudications([row]), [])

    def test_positive_output_uses_the_canonical_report_validator(self):
        """A structurally invalid impact report must fail mechanical scoring."""
        invalid = VALID_REPORT.replace("| IMP-001 |", "| IMP-1 |", 1)

        score = score_mechanical(
            case("POS-example"), result("POS-example", RunStatus.PASS, invalid)
        )

        self.assertFalse(score.passed)
        self.assertIn("invalid identifier IMP-1", score.findings)

    def test_negative_case_rejects_refinement_identifiers_or_workflow(self):
        """A negative prompt must not be credited after activating refinement."""
        score = score_mechanical(
            case("NEG-example", "negative"),
            result(
                "NEG-example",
                RunStatus.PASS,
                "I created RPT-001 and will begin impact refinement.",
            ),
        )

        self.assertFalse(score.passed)
        self.assertTrue(any("refinement" in finding for finding in score.findings))

    def test_superpowers_case_requires_exact_boundary_and_no_automatic_planning(self):
        """A generic planning handoff would blur Superpowers' ownership boundary."""
        score = score_mechanical(
            case("INT-superpowers", "integration"),
            result(
                "INT-superpowers",
                RunStatus.PASS,
                "I enter after approved brainstorming and now automatically invoke writing-plans.",
            ),
        )

        self.assertFalse(score.passed)
        self.assertIn("INT-superpowers requires exit before writing-plans", score.findings)
        self.assertIn("INT-superpowers forbids automatic writing-plans", score.findings)

    def test_lineage_rejected_case_cannot_resolve_an_unsupported_impact(self):
        """An unsupported resolution must fail the rejection lineage contract."""
        score = score_mechanical(
            case("LINEAGE-no-false-resolution", "lineage", "rejected"),
            result(
                "LINEAGE-no-false-resolution",
                RunStatus.PASS,
                VALID_REPORT.replace("| accepted |", "| resolved |", 1),
            ),
        )

        self.assertFalse(score.passed)
        self.assertTrue(any("resolution" in finding for finding in score.findings))

    def test_rendering_promotes_only_complete_codex_superpowers_matrix(self):
        """A near-complete or differently composed matrix must remain not verified."""
        results = tuple(
            result("POS-%02d" % index, RunStatus.PASS, repetition=index)
            for index in range(1, 86)
        )
        metadata = {
            "client": "codex",
            "version": "0.148.0",
            "enabled_composition": "Codex with Superpowers",
            "model": "gpt-5.6-sol",
            "reasoning": "high",
            "repetitions": 5,
        }

        verified = render_report(results, metadata)
        not_verified = render_report(results[:-1], metadata)
        standalone = render_report(
            results,
            dict(metadata, enabled_composition="Codex standalone"),
        )

        self.assertIn("status: verified", verified)
        self.assertIn("status: not verified", not_verified)
        self.assertIn("status: not verified", standalone)
        self.assertIn("model: gpt-5.6-sol", verified)
        self.assertIn("reasoning: high", verified)

    def test_rendering_requires_all_environment_metadata(self):
        """Omitting run-local provenance makes the result unreportable."""
        with self.assertRaisesRegex(ValueError, "reasoning"):
            render_report(
                (result("POS-one", RunStatus.PASS),),
                {
                    "client": "codex",
                    "version": "0.148.0",
                    "enabled_composition": "Codex with Superpowers",
                    "model": "gpt-5.6-sol",
                    "repetitions": 1,
                },
            )


if __name__ == "__main__":
    unittest.main()
