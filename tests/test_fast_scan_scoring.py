import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "evals/harness/fast_scan_scoring.py"


def load():
    if not MODULE.is_file():
        raise AssertionError("fast_scan_scoring.py must exist")
    spec = importlib.util.spec_from_file_location("fast_scan_scoring_test", MODULE)
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


class FastScanScoringTest(unittest.TestCase):
    def test_positive_requires_seed_path_time_words_and_one_scan_call(self):
        module = load()
        case = module.load_fast_scan_cases()[0]
        result = {
            "status": "complete",
            "elapsed_ms": 17,
            "display_text": "Fast impact scan " * 20,
            "seeds": [{"term": case.required_seeds[0][0], "location": case.required_seeds[0][1]}],
            "maximum_path_distance": 3,
            "controller_calls": ["rir_scan"],
            "uncovered_high_risk_nodes": [],
        }
        self.assertTrue(module.score_fast_scan(case, result).passed)
        result["controller_calls"] = ["rir_scan", "rir_begin"]
        self.assertFalse(module.score_fast_scan(case, result).passed)

    def test_negative_requires_zero_controller_calls(self):
        module = load()
        case = module.load_fast_scan_cases()[-1]
        self.assertTrue(
            module.score_fast_scan(
                case,
                {
                    "status": "not_applicable",
                    "controller_calls": [],
                    "display_text": "",
                    "elapsed_ms": None,
                    "seeds": [],
                    "maximum_path_distance": 0,
                    "uncovered_high_risk_nodes": [],
                },
            ).passed
        )

    def test_malformed_path_distance_is_scored_as_missing_evidence(self):
        module = load()
        case = module.load_fast_scan_cases()[0]

        score = module.score_fast_scan(
            case,
            {
                "status": "complete",
                "elapsed_ms": 17,
                "display_text": "Fast impact scan",
                "seeds": [
                    {"term": case.required_seeds[0][0], "location": case.required_seeds[0][1]}
                ],
                "maximum_path_distance": "three",
                "controller_calls": ["rir_scan"],
                "uncovered_high_risk_nodes": [],
            },
        )

        self.assertFalse(score.passed)
        self.assertIn("required distant path is missing", score.findings)


if __name__ == "__main__":
    unittest.main()
