import unittest
from dataclasses import replace

from evals.harness.catalog import load_all, select_suite
from evals.harness.models import (
    Adjudication,
    CaseSpec,
    CaseTurn,
    MechanicalScore,
    RunResult,
    RunStatus,
)
from evals.harness.reporting import render_report, summarize
from evals.harness.scoring import score_mechanical, validate_adjudications
from tests.test_report_lineage import next_report, report_with_state
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


def result(
    case_id,
    status,
    output=None,
    repetition=1,
    client="codex",
    composition="Codex with Superpowers",
):
    return RunResult(
        case_id=case_id,
        repetition=repetition,
        client="codex",
        status=status,
        reason=None,
        final_output=output,
        metadata=(("environment", composition),),
    )


CANONICAL_CASES = select_suite(load_all(), "installed-superpowers")
REPORT_METADATA = {
    "client": "codex",
    "version": "0.148.0",
    "enabled_composition": "Codex with Superpowers",
    "model": "gpt-5.6-sol",
    "reasoning": "high",
    "repetitions": 5,
}
SUPERPOWERS_HANDOFF_MARKER = (
    "superpowers:after-approved-brainstorming;impact-refinement;"
    "manual-handoff-before-writing-plans"
)


def superpowers_report(workflow=SUPERPOWERS_HANDOFF_MARKER, statement=""):
    report = VALID_REPORT.replace("Existing planning workflow", workflow, 1)
    return report + ("\n" + statement if statement else "")


def complete_matrix():
    runs = []
    scores = []
    adjudications = []
    for specification in CANONICAL_CASES:
        for repetition in range(1, 6):
            rubrics = specification.must_detect + specification.must_not_do
            quotes = [
                "[%s/%02d %s]" % (specification.id, repetition, rubric)
                for rubric in rubrics
            ]
            runs.append(
                result(
                    specification.id,
                    RunStatus.PASS,
                    "\n".join(quotes) or "negative exclusion confirmed",
                    repetition,
                )
            )
            scores.append(MechanicalScore(specification.id, repetition, True, ()))
            adjudications.extend(
                Adjudication(
                    specification.id,
                    repetition,
                    rubric,
                    True,
                    quote,
                    "The quote directly supports the required rubric.",
                )
                for rubric, quote in zip(rubrics, quotes)
            )
    return tuple(runs), tuple(scores), tuple(adjudications)


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

    def test_adjudications_are_complete_unique_boolean_and_transcript_bound(self):
        """An invented or incomplete human row cannot support a verified claim."""
        runs, _, adjudications = complete_matrix()
        valid = validate_adjudications(adjudications, CANONICAL_CASES, runs)
        self.assertEqual(valid, [])

        mutations = {
            "nonboolean": replace(adjudications[0], passed="yes"),
            "invented quote": replace(adjudications[0], quote="not in transcript"),
            "unknown rubric": replace(adjudications[0], rubric="unknown rubric"),
        }
        for name, mutated in mutations.items():
            with self.subTest(name=name):
                errors = validate_adjudications(
                    (mutated,) + adjudications[1:], CANONICAL_CASES, runs
                )
                self.assertTrue(errors)

        errors = validate_adjudications(
            adjudications + (adjudications[0],), CANONICAL_CASES, runs
        )
        self.assertTrue(any("duplicate adjudication" in error for error in errors))
        errors = validate_adjudications(adjudications[1:], CANONICAL_CASES, runs)
        self.assertTrue(any("missing adjudication" in error for error in errors))

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

    def test_superpowers_case_requires_exact_structured_boundary(self):
        """Free text cannot establish the mechanically provable workflow boundary."""
        score = score_mechanical(
            case("INT-superpowers", "integration"),
            result(
                "INT-superpowers",
                RunStatus.PASS,
                "I enter after approved brainstorming and now automatically invoke writing-plans.",
            ),
        )

        self.assertFalse(score.passed)
        self.assertIn(
            "INT-superpowers requires the exact structured Planning Handoff marker",
            score.findings,
        )

    def test_superpowers_free_text_boundaries_never_replace_the_structured_marker(self):
        """Plausible prose cannot establish the exact cross-workflow ownership contract."""
        phrases = (
            "after approved brainstorming",
            "after Superpowers brainstorming",
            "brainstorming is complete",
            "brainstorming was complete",
            "brainstorming has been completed",
        )

        for phrase in phrases:
            with self.subTest(phrase=phrase):
                score = score_mechanical(
                    case("INT-superpowers", "integration"),
                    result(
                        "INT-superpowers",
                        RunStatus.PASS,
                        "%s; refinement exits before writing-plans." % phrase,
                    ),
                )
                self.assertFalse(score.passed)
                self.assertIn(
                    "INT-superpowers requires the exact structured Planning Handoff marker",
                    score.findings,
                )

    def test_superpowers_exact_structured_handoff_marker_is_the_only_mechanical_boundary(self):
        """Semantic prose remains a human judgment even when it contradicts the marker."""
        statements = (
            "",
            "This paragraph is unrelated to planning.",
            "The adapter automatically invokes writing-plans.",
            "Writing-plans is automatically launched despite the manual handoff.",
        )
        for statement in statements:
            with self.subTest(statement=statement):
                score = score_mechanical(
                    case("INT-superpowers", "integration"),
                    result(
                        "INT-superpowers",
                        RunStatus.PASS,
                        superpowers_report(statement=statement),
                    ),
                )
                self.assertTrue(score.passed, score.findings)

    def test_superpowers_missing_wrong_or_negated_marker_fails(self):
        """Only the exact cell value may satisfy the structured boundary contract."""
        workflows = (
            "",
            "superpowers",
            "not " + SUPERPOWERS_HANDOFF_MARKER,
            "selected " + SUPERPOWERS_HANDOFF_MARKER,
            SUPERPOWERS_HANDOFF_MARKER + " automatically",
        )
        for workflow in workflows:
            with self.subTest(workflow=workflow):
                score = score_mechanical(
                    case("INT-superpowers", "integration"),
                    result(
                        "INT-superpowers",
                        RunStatus.PASS,
                        superpowers_report(workflow),
                    ),
                )
                self.assertFalse(score.passed)
                self.assertIn(
                    "INT-superpowers requires the exact structured Planning Handoff marker",
                    score.findings,
                )

    def test_superpowers_rejects_future_incomplete_or_reversed_brainstorming(self):
        """A phrase about a future or incomplete gate must not count as completed entry."""
        phrases = (
            "It is false that brainstorming is complete",
            "If brainstorming is complete",
            "We are not after Superpowers brainstorming",
            "brainstorming is not complete",
            "before brainstorming is complete",
            "we will start brainstorming",
        )

        for phrase in phrases:
            with self.subTest(phrase=phrase):
                score = score_mechanical(
                    case("INT-superpowers", "integration"),
                    result(
                        "INT-superpowers",
                        RunStatus.PASS,
                        "%s; refinement exits before writing-plans." % phrase,
                    ),
                )
                self.assertFalse(score.passed)
                self.assertIn(
                    "INT-superpowers requires the exact structured Planning Handoff marker",
                    score.findings,
                )

    def test_superpowers_requires_an_affirmative_before_writing_plans_boundary(self):
        """A negated pre-planning boundary must not satisfy the ownership handoff."""
        score = score_mechanical(
            case("INT-superpowers", "integration"),
            result(
                "INT-superpowers",
                RunStatus.PASS,
                "Brainstorming is complete; refinement is not before writing-plans.",
            ),
        )

        self.assertFalse(score.passed)
        self.assertIn(
            "INT-superpowers requires the exact structured Planning Handoff marker",
            score.findings,
        )

    def test_canonical_superpowers_forbidden_workflow_requires_quoted_adjudication(self):
        """The exact marker is mechanical; every canonical forbidden action remains human-scored."""
        specification = next(
            case for case in CANONICAL_CASES if case.id == "INT-superpowers"
        )
        rubric = "invoke writing-plans automatically"
        quote = "The adapter automatically invokes writing-plans."
        rubrics = specification.must_detect + specification.must_not_do
        runs = tuple(
            result(
                "INT-superpowers",
                RunStatus.PASS,
                superpowers_report(
                    statement="\n".join(
                        [
                            "[INT-superpowers/%02d %s]" % (repetition, item)
                            for item in rubrics
                        ]
                        + [quote]
                    )
                ),
                repetition,
            )
            for repetition in range(1, 6)
        )
        rows = tuple(
            Adjudication(
                "INT-superpowers",
                repetition,
                item,
                item != rubric,
                quote
                if item == rubric
                else "[INT-superpowers/%02d %s]" % (repetition, item),
                "The quoted response contradicts the manual-handoff contract."
                if item == rubric
                else "The quote directly supports the required rubric.",
            )
            for repetition in range(1, 6)
            for item in rubrics
        )

        self.assertTrue(
            all(score_mechanical(specification, run).passed for run in runs)
        )
        self.assertEqual(validate_adjudications(rows, (specification,), runs), [])
        missing_forbidden = tuple(
            row for row in rows if row.rubric not in specification.must_not_do
        )
        missing_errors = validate_adjudications(
            missing_forbidden, (specification,), runs
        )
        self.assertEqual(
            sum("missing adjudication" in error for error in missing_errors),
            len(specification.must_not_do) * 5,
        )

        matrix_runs, matrix_scores, matrix_rows = complete_matrix()
        integration_keys = {(run.case_id, run.repetition) for run in runs}
        matrix_runs = tuple(
            run
            for run in matrix_runs
            if (run.case_id, run.repetition) not in integration_keys
        ) + runs
        matrix_rows = tuple(
            row for row in matrix_rows if row.case_id != "INT-superpowers"
        ) + rows
        rendered = render_report(
            matrix_runs, REPORT_METADATA, matrix_scores, matrix_rows
        )
        self.assertIn("status: not verified", rendered)

    def test_lineage_uses_exact_previous_bytes_for_canonical_validation(self):
        """Reconstructing predecessor bytes would break the immutable lineage digest contract."""
        previous = report_with_state("blocked")
        current = next_report(previous, report_with_state("blocked", "unchanged"))

        exact = score_mechanical(
            case("LINEAGE-stable-blocked", "lineage", "unchanged"),
            result("LINEAGE-stable-blocked", RunStatus.PASS, current),
            previous_bytes=previous.encode("utf-8"),
        )
        changed = score_mechanical(
            case("LINEAGE-stable-blocked", "lineage", "unchanged"),
            result("LINEAGE-stable-blocked", RunStatus.PASS, current),
            previous_bytes=(previous + "\n").encode("utf-8"),
        )

        self.assertTrue(exact.passed, exact.findings)
        self.assertFalse(changed.passed)
        self.assertIn(
            "Previous SHA-256 does not match predecessor bytes", changed.findings
        )

    def test_lineage_rejects_non_utf8_previous_bytes_without_replacement(self):
        """Replacement decoding could validate bytes other than the sealed predecessor."""
        previous = report_with_state("blocked")
        current = next_report(previous, report_with_state("blocked", "unchanged"))

        score = score_mechanical(
            case("LINEAGE-stable-blocked", "lineage", "unchanged"),
            result("LINEAGE-stable-blocked", RunStatus.PASS, current),
            previous_bytes=b"\xff",
        )

        self.assertFalse(score.passed)
        self.assertIn("lineage predecessor is not valid UTF-8", score.findings)

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

    def test_lineage_rejected_case_requires_active_ledger_without_rejected_delta(self):
        """Rejected is an evaluation outcome, never an authored Impact Delta category."""
        accepted = score_mechanical(
            case("LINEAGE-no-false-resolution", "lineage", "rejected"),
            result("LINEAGE-no-false-resolution", RunStatus.PASS, VALID_REPORT),
        )
        active = score_mechanical(
            case("LINEAGE-no-false-resolution", "lineage", "rejected"),
            result(
                "LINEAGE-no-false-resolution",
                RunStatus.PASS,
                VALID_REPORT.replace("| accepted | verified |", "| refining | verified |", 1),
            ),
        )

        self.assertFalse(accepted.passed)
        self.assertTrue(any("active" in finding for finding in accepted.findings))
        self.assertTrue(active.passed, active.findings)

    def test_rendering_promotes_only_complete_sealed_canonical_matrix(self):
        """Raw pass statuses and caller metadata cannot manufacture verification."""
        runs, scores, adjudications = complete_matrix()

        verified = render_report(runs, REPORT_METADATA, scores, adjudications)
        self.assertIn("status: verified", verified)

        contradictory_repetitions = render_report(
            runs,
            dict(REPORT_METADATA, repetitions=1),
            scores,
            adjudications,
        )
        self.assertIn("status: not verified", contradictory_repetitions)
        self.assertIn("repetitions: 5", contradictory_repetitions)

        mutations = {
            "empty scores": (runs, (), adjudications),
            "empty adjudications": (runs, scores, ()),
            "duplicate repetition": (runs[:-1] + (replace(runs[-1], repetition=1),), scores, adjudications),
            "wrong client": (replace(runs[0], client="claude"),) + runs[1:],
            "wrong composition": (replace(runs[0], metadata=(("environment", "Codex standalone"),)),) + runs[1:],
            "missing run": (runs[:-1], scores[:-1], adjudications),
            "partial result": (replace(runs[0], status=RunStatus.PARTIAL),) + runs[1:],
            "failed mechanical score": (runs, (replace(scores[0], passed=False),) + scores[1:], adjudications),
            "failed adjudication": (runs, scores, (replace(adjudications[0], passed=False),) + adjudications[1:]),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                if name in {"wrong client", "wrong composition", "partial result"}:
                    mutated_runs, mutated_scores, mutated_adjudications = mutation, scores, adjudications
                else:
                    mutated_runs, mutated_scores, mutated_adjudications = mutation
                rendered = render_report(
                    mutated_runs,
                    dict(REPORT_METADATA, client="codex", enabled_composition="Codex with Superpowers"),
                    mutated_scores,
                    mutated_adjudications,
                )
                self.assertIn("status: not verified", rendered)

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
