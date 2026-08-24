import json
import unittest
from dataclasses import replace
from pathlib import Path


from evals.harness.models import RunStatus
from evals.harness.performance import (
    GraphPerformanceObservation,
    PerformanceObservation,
    evaluate_graph_smoke,
    evaluate_smoke_gate,
)


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "evals" / "performance-baseline-v032.json"
SMOKE_IDS = (
    "POS-authorization",
    "NEG-debugging",
    "INT-superpowers",
    "LINEAGE-stable-blocked",
    "LINEAGE-reopened",
    "LINEAGE-no-false-resolution",
)
GRAPH_IDS = (
    "GRAPH-api-mobile-cache-migration",
    "GRAPH-auth-role-audit-consumer",
    "GRAPH-event-retry-idempotency-side-effect",
    "GRAPH-schema-serializer-backfill-export",
    "GRAPH-config-deploy-worker-health",
    "GRAPH-negative-no-change",
)


class PerformanceBudgetTest(unittest.TestCase):
    def observation(self, case_id):
        impact_ids = () if case_id == "NEG-debugging" else ("IMP-001",)
        return PerformanceObservation(
            case_id=case_id,
            repetition=1,
            status=RunStatus.PASS,
            attempt=1,
            retry_of=None,
            prompt_bytes=1200,
            routed_resource_bytes=9000,
            routed_resource_words=1574,
            output_bytes=1800,
            output_words=280,
            duration_ms=12000,
            input_tokens=None,
            output_tokens=None,
            impact_ids=impact_ids,
            state_markdown_match=True,
            workflow_boundary_passed=True,
            controller_begin_calls=0 if case_id == "NEG-debugging" else (2 if case_id.startswith("LINEAGE-") else 1),
            controller_finalize_calls=0 if case_id == "NEG-debugging" else (2 if case_id.startswith("LINEAGE-") else 1),
            controller_draft_ids_match=True,
            controller_finalize_succeeded=True,
            controller_display_text_exact_match=True,
            controller_display_text_presentation_equivalent=True,
            controller_display_comparison="codex-markdown-v1",
        )

    def six_valid_observations(self):
        return tuple(self.observation(case_id) for case_id in SMOKE_IDS)

    def graph_observation(self, case_id):
        negative = case_id == "GRAPH-negative-no-change"
        return GraphPerformanceObservation(
            case_id=case_id,
            repetition=1,
            status=RunStatus.PASS,
            mechanical_passed=True,
            graph_passed=True,
            attempt=1,
            retry_of=None,
            graph_duration_ms=None if negative else 8400,
            output_words=280,
            routed_resource_words=1574,
            receipt_state_provider_parity=True,
            uncovered_high_risk_nodes=(),
            controller_begin_calls=0 if negative else 1,
            controller_trace_calls=0 if negative else 1,
            controller_finalize_calls=0 if negative else 1,
            controller_evidence_valid=True,
            duplicate_or_error_calls=False,
            input_tokens=None,
            output_tokens=None,
        )

    def six_graph_rows(self):
        return tuple(self.graph_observation(case_id) for case_id in GRAPH_IDS)

    def test_baseline_is_literal_and_matches_preserved_measurement(self):
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(baseline["selected_path_words"], 3500)
        self.assertEqual(baseline["output_files"], 100)
        self.assertEqual(baseline["average_output_words"], 906.6)
        self.assertEqual(baseline["maximum_output_words"], 1596)

    def test_smoke_gate_accepts_complete_semantic_and_budget_evidence(self):
        result = evaluate_smoke_gate(self.six_valid_observations())

        self.assertTrue(result.passed)
        self.assertEqual(result.errors, ())
        self.assertEqual(result.median_output_words, 280)
        self.assertEqual(result.median_routed_resource_words, 1574)

    def test_smoke_gate_rejects_incomplete_duplicate_or_retried_matrix(self):
        missing = self.six_valid_observations()[:-1]
        duplicate = self.six_valid_observations()[:-1] + (missing[0],)
        retried = list(self.six_valid_observations())
        retried[0] = replace(retried[0], attempt=2, retry_of="attempt-01")

        self.assertIn("smoke observations do not cover the exact six cases", evaluate_smoke_gate(missing).errors)
        self.assertIn("smoke observations contain duplicate case/repetition rows", evaluate_smoke_gate(duplicate).errors)
        self.assertIn("smoke observations must select attempt 1 without retry", evaluate_smoke_gate(retried).errors)

    def test_smoke_gate_rejects_budget_semantic_and_workflow_failures(self):
        too_large = list(self.six_valid_observations())
        for index in (0, 1, 2, 3):
            too_large[index] = replace(too_large[index], output_words=900)
        too_many_resources = list(self.six_valid_observations())
        for index in (0, 1, 2, 3):
            too_many_resources[index] = replace(
                too_many_resources[index], routed_resource_words=2200
            )
        mismatch = list(self.six_valid_observations())
        mismatch[0] = replace(mismatch[0], state_markdown_match=False)
        workflow = list(self.six_valid_observations())
        workflow[2] = replace(workflow[2], workflow_boundary_passed=False)
        skipped_controller = list(self.six_valid_observations())
        skipped_controller[0] = replace(skipped_controller[0], controller_begin_calls=0)
        rewritten_output = list(self.six_valid_observations())
        rewritten_output[2] = replace(
            rewritten_output[2],
            controller_display_text_presentation_equivalent=False,
        )

        self.assertIn("median compact output exceeds 450 words", evaluate_smoke_gate(too_large).errors)
        self.assertIn("median routed resources do not reduce baseline by 50 percent", evaluate_smoke_gate(too_many_resources).errors)
        self.assertIn("state, Markdown, and compact impacts disagree", evaluate_smoke_gate(mismatch).errors)
        self.assertIn("workflow ownership boundary failed", evaluate_smoke_gate(workflow).errors)
        self.assertIn("controller call count or order failed", evaluate_smoke_gate(skipped_controller).errors)
        self.assertIn("controller display text differs from final output", evaluate_smoke_gate(rewritten_output).errors)

    def test_token_fields_must_be_both_client_reported_or_both_absent(self):
        partial = list(self.six_valid_observations())
        partial[0] = replace(partial[0], input_tokens=100)

        self.assertIn(
            "token usage must be complete or absent",
            evaluate_smoke_gate(partial).errors,
        )

    def test_graph_smoke_requires_target_and_ceiling(self):
        result = evaluate_graph_smoke(self.six_graph_rows())
        self.assertTrue(result.passed, result.errors)
        self.assertEqual(result.median_graph_duration_ms, 8400)

        slow = replace(self.six_graph_rows()[0], graph_duration_ms=30_001)
        over_target = tuple(
            replace(row, graph_duration_ms=10_001)
            if row.graph_duration_ms is not None else row
            for row in self.six_graph_rows()
        )

        self.assertIn(
            "graph duration exceeds 30 seconds",
            evaluate_graph_smoke((slow,) + self.six_graph_rows()[1:]).errors,
        )
        self.assertIn(
            "median graph duration exceeds 10 seconds",
            evaluate_graph_smoke(over_target).errors,
        )

    def test_graph_smoke_gates_exact_matrix_attempt_runtime_mechanics_and_provenance(self):
        valid = self.six_graph_rows()
        mutations = {
            "graph observations do not cover the exact six cases": valid[:-1],
            "graph observations contain duplicate case/repetition rows": valid[:-1] + (valid[0],),
            "graph observations must select attempt 1 without retry": (replace(valid[0], attempt=2, retry_of="retry"),) + valid[1:],
            "every graph runtime result must pass": (replace(valid[0], status=RunStatus.FAIL),) + valid[1:],
            "every graph mechanical score must pass": (replace(valid[0], mechanical_passed=False),) + valid[1:],
            "every graph coverage score must pass": (replace(valid[0], graph_passed=False),) + valid[1:],
            "receipt, state, and provider provenance disagree": (replace(valid[0], receipt_state_provider_parity=False),) + valid[1:],
            "graph smoke contains uncovered high-risk nodes": (replace(valid[0], uncovered_high_risk_nodes=("NODE-999",)),) + valid[1:],
            "controller graph call count or order failed": (replace(valid[0], controller_trace_calls=0),) + valid[1:],
            "controller graph evidence contains duplicate or error calls": (replace(valid[0], duplicate_or_error_calls=True),) + valid[1:],
        }
        for finding, rows in mutations.items():
            with self.subTest(finding=finding):
                self.assertIn(finding, evaluate_graph_smoke(rows).errors)

    def test_graph_smoke_gates_output_and_routed_guidance_but_tokens_are_informational(self):
        rows = self.six_graph_rows()
        too_verbose = tuple(
            replace(row, output_words=451) for row in rows
        )
        too_many_resources = tuple(
            replace(row, routed_resource_words=1751) for row in rows
        )
        partial_tokens = (replace(rows[0], input_tokens=100),) + rows[1:]

        self.assertIn(
            "median graph compact output exceeds 450 words",
            evaluate_graph_smoke(too_verbose).errors,
        )
        self.assertIn(
            "median graph routed guidance does not reduce baseline by 50 percent",
            evaluate_graph_smoke(too_many_resources).errors,
        )
        self.assertTrue(evaluate_graph_smoke(partial_tokens).passed)


if __name__ == "__main__":
    unittest.main()
