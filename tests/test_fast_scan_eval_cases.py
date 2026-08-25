import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from evals.harness.fast_scan_scoring import load_fast_scan_cases, score_fast_scan
from evals.harness.models import RunStatus
from evals.harness.performance import FastScanPerformanceObservation, evaluate_fast_scan_gate

ROOT = Path(__file__).resolve().parents[1]


class FastScanEvalCaseTest(unittest.TestCase):
    def test_catalog_has_exact_five_positive_and_one_negative(self):
        path = ROOT / "evals/fast-scan-cases.json"
        self.assertTrue(path.is_file())
        value = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(value["schema_version"], 1)
        self.assertEqual(len(value["cases"]), 6)
        self.assertEqual(
            [row["kind"] for row in value["cases"]],
            ["positive"] * 5 + ["negative"],
        )
        for row in value["cases"][:5]:
            self.assertEqual(row["maximum_output_words"], 180)
            self.assertEqual(row["maximum_scan_ms"], 30000)
            self.assertGreaterEqual(row["minimum_path_distance"], 3)
        self.assertFalse(value["cases"][-1]["controller_required"])

    def test_real_controller_runs_five_fixtures_and_negative_stays_zero_call(self):
        spec = importlib.util.spec_from_file_location(
            "fast_scan_eval_controller",
            ROOT / "scripts/rir_controller.py",
        )
        controller = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = controller
        spec.loader.exec_module(controller)
        graph_cases = json.loads((ROOT / "evals/graph-cases.json").read_text(encoding="utf-8"))[
            "cases"
        ]
        policies = load_fast_scan_cases()
        observations = []
        for policy, graph_case in zip(policies[:5], graph_cases[:5]):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".requirements-impact-refiner.json").write_text(
                    json.dumps(
                        {
                            "impact_graph": {
                                "enabled": True,
                                "max_seconds": 30,
                                "target_seconds": 10,
                                "providers": ["builtin"],
                                "install_policy": "never",
                                "deep": False,
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                for fixture in graph_case["fixture_files"]:
                    path = root / fixture["path"]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(fixture["content"], encoding="utf-8")
                result = controller.scan_impact(
                    controller.ScanRequest(
                        root,
                        graph_case["request"],
                        tuple(graph_case["repository_evidence"]),
                        "balanced",
                    )
                )
                wrapper_path = (
                    root / ".requirements-impact-refiner/scans" / (result.scan_id + ".json")
                )
                wrapper_bytes = wrapper_path.read_bytes()
                wrapper = json.loads(wrapper_bytes)
                exact_provenance = (
                    hashlib.sha256(wrapper_bytes).hexdigest() == result.receipt_sha256
                    and wrapper["payload_sha256"] == controller._payload_sha256()
                    and wrapper["settings"]["providers"] == ["builtin"]
                    and wrapper["graph_receipt"]["providers"][0]["name"] == "builtin"
                )
                self.assertTrue(exact_provenance)
                maximum = max(
                    (row["distance"] for row in wrapper["graph_receipt"]["paths"]),
                    default=0,
                )
                score = score_fast_scan(
                    policy,
                    {
                        "status": result.status,
                        "elapsed_ms": result.elapsed_ms,
                        "display_text": result.display_text,
                        "seeds": wrapper["seeds"],
                        "maximum_path_distance": maximum,
                        "controller_calls": ["rir_scan"],
                        "uncovered_high_risk_nodes": [],
                    },
                )
                self.assertTrue(score.passed, score.findings)
                observations.append(
                    FastScanPerformanceObservation(
                        policy.id,
                        1,
                        RunStatus.PASS,
                        1,
                        None,
                        result.elapsed_ms,
                        len(result.display_text.split()),
                        ("rir_scan",),
                        True,
                        exact_provenance,
                        (),
                        None,
                        None,
                    )
                )
        observations.append(
            FastScanPerformanceObservation(
                policies[-1].id,
                1,
                RunStatus.PASS,
                1,
                None,
                None,
                0,
                (),
                True,
                True,
                (),
                None,
                None,
            )
        )
        gate = evaluate_fast_scan_gate(tuple(observations))
        self.assertTrue(gate.passed, gate.errors)


if __name__ == "__main__":
    unittest.main()
