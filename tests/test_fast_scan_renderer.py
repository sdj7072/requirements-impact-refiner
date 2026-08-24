import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "fast_scan_renderer.py"
FIXTURE = ROOT / "tests" / "fixtures" / "impact-graph-receipt.json"

def load_renderer():
    if not MODULE.is_file():
        raise AssertionError("scripts/fast_scan_renderer.py must exist")
    name = "_fast_scan_renderer_test"
    spec = importlib.util.spec_from_file_location(name, MODULE)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value

def receipt():
    graph = json.loads(FIXTURE.read_text(encoding="utf-8"))
    graph["nodes"][0]["label"] = "<profile|name>"
    return {"status": "complete", "risk_level": "high", "graph_receipt": graph, "frontier": graph["frontier"], "candidates": [], "elapsed_ms": 17, "cache_status": "miss"}

class FastScanRendererTest(unittest.TestCase):
    def test_balanced_output_has_paths_frontier_footer_and_word_limit(self):
        text = load_renderer().render_fast_scan(receipt(), "balanced")
        self.assertIn("→", text)
        self.assertIn("Possible issue", text)
        self.assertEqual(text.count("Coverage:"), 1)
        self.assertEqual(text.count("Do you want detailed refinement?"), 1)
        self.assertLessEqual(len(text.split()), 180)

    def test_technical_output_escapes_and_preserves_provenance(self):
        text = load_renderer().render_fast_scan(receipt(), "technical")
        self.assertNotIn("<profile", text)
        self.assertIn("&lt;profile&#124;name&gt;", text)
        self.assertIn("provider", text)
        self.assertIn("confidence", text)
        self.assertLessEqual(len(text.split()), 180)

    def test_needs_input_and_partial_are_honest(self):
        renderer = load_renderer()
        needs = {"status": "needs_input", "risk_level": "unknown", "graph_receipt": {}, "frontier": [], "elapsed_ms": 1, "cache_status": "bypassed", "candidates": [{"term": "ProfileService", "location": "src/profile.py", "derivation": "repository-match"}]}
        text = renderer.render_fast_scan(needs, "simple")
        self.assertIn("more input", text.lower())
        self.assertIn("ProfileService", text)
        partial = dict(receipt())
        partial["status"] = "partial"
        text = renderer.render_fast_scan(partial, "simple")
        self.assertIn("partial", text.lower())
        self.assertIn("unknown", text.lower())

if __name__ == "__main__":
    unittest.main()


class NeedsInputQuestionTest(unittest.TestCase):
    """needs_input must end with a question, because the skill instructs the
    agent to return display_text verbatim and stop; without one the
    conversation dead-ends."""

    def test_needs_input_asks_for_a_concrete_boundary(self):
        renderer = load_renderer()
        text = renderer.render_fast_scan(
            {
                "status": "needs_input",
                "candidates": [],
                "elapsed_ms": 9,
                "cache_status": "bypassed",
            },
            "balanced",
        )
        self.assertTrue(text.rstrip().endswith("?"), text)
        self.assertIn("boundary", text)


class SafetyLinePreservationTest(unittest.TestCase):
    """The word cap must trim issue paths, never the unknown-frontier and
    partial-result warnings — those are the safety content of the render."""

    def test_frontier_and_partial_warnings_survive_truncation(self):
        renderer = load_renderer()
        nodes = [
            {"id": f"NODE-{i:03d}",
             "label": " ".join(f"segment{i}word{j}" for j in range(18)),
             "location": f"src/pkg{i}/file{i}.py"}
            for i in range(20)
        ]
        paths = [
            {"nodes": [f"NODE-{i:03d}", f"NODE-{(i + 1) % 20:03d}"],
             "edges": [], "risk_domains": ["operations"]}
            for i in range(8)
        ]
        receipt = {
            "status": "partial",
            "risk_level": "high",
            "graph_receipt": {"nodes": nodes, "edges": [], "paths": paths},
            "frontier": [{"reason": "graph coverage remains incomplete"}],
            "elapsed_ms": 100,
            "cache_status": "bypassed",
        }

        text = renderer.render_fast_scan(receipt, "balanced")

        self.assertLessEqual(len(text.split()), renderer.WORD_LIMIT)
        self.assertIn("Unknown frontier", text)
        self.assertIn("Partial result", text)
        self.assertIn("Do you want detailed refinement?", text)
