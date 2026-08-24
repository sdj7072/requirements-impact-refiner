import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = ROOT / "skills" / "requirements-impact-refiner" / "scripts"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CONTROLLER = load_module("rir_controller_bounds", SKILL_SCRIPTS / "rir_controller.py")


def big_receipt(node_count=474, path_count=64, frontier_count=40):
    nodes = [
        {
            "id": f"NODE-{i:03d}", "kind": "file",
            "label": f"module_component_label_{i}",
            "location": f"src/package{i % 12}/module_file_{i}.py",
            "provider": "builtin", "confidence": "lexical",
            "source_sha256": None,
            "risk_domains": ["operations"] if i % 3 else ["authorization/privacy"],
        }
        for i in range(node_count)
    ]
    edges = [
        {
            "id": f"EDGE-{i:03d}", "source": f"NODE-{i:03d}",
            "target": f"NODE-{(i + 1) % node_count:03d}", "kind": "references",
            "location": f"src/package{i % 12}/module_file_{i}.py",
            "evidence": "shared_token", "confidence": "lexical",
            "provider": "builtin", "source_sha256": None,
        }
        for i in range(node_count)
    ]
    paths = [
        {
            "id": f"PATH-{i:03d}",
            "nodes": [f"NODE-{i:03d}", f"NODE-{(i + 1) % node_count:03d}"],
            "edges": [f"EDGE-{i:03d}"], "distance": 1,
            "risk_domains": ["operations"],
        }
        for i in range(path_count)
    ]
    frontier = [
        {
            "id": f"FRONTIER-{i:03d}", "node": f"NODE-{i:03d}",
            "reason": "graph coverage remains incomplete",
            "risk_domains": ["operations"],
        }
        for i in range(frontier_count)
    ]
    return {
        "nodes": nodes, "edges": edges, "paths": paths, "frontier": frontier,
        "providers": [
            {"name": "builtin", "status": "ready", "confidence": "lexical",
             "version": None}
        ],
        "timings_ms": {"total": 100},
        "budget_status": "provider_limited",
    }


class CompactGraphBoundsTest(unittest.TestCase):
    """The compact delivery exists to fit a model turn: it must stay bounded
    on a large receipt and disclose exactly what it dropped."""

    def test_large_receipt_delivery_is_bounded_and_discloses_truncation(self):
        compact = CONTROLLER._compact_graph(big_receipt())
        payload = json.dumps(compact, ensure_ascii=False, sort_keys=True)

        self.assertLessEqual(len(payload.encode("utf-8")), 24_000)
        self.assertLessEqual(len(compact["nodes"]), CONTROLLER.COMPACT_MAX_NODES)
        self.assertLessEqual(len(compact["paths"]), CONTROLLER.COMPACT_MAX_PATHS)
        self.assertLessEqual(
            len(compact["frontier"]), CONTROLLER.COMPACT_MAX_FRONTIER
        )
        truncated = compact["summary"]["truncated"]
        self.assertGreater(truncated["nodes"], 0)
        self.assertGreater(truncated["paths"], 0)
        self.assertGreater(truncated["frontier"], 0)
        # true totals stay visible next to the truncation disclosure
        self.assertEqual(compact["summary"]["nodes"], 474)

    def test_small_receipt_is_delivered_whole(self):
        receipt = big_receipt(node_count=6, path_count=3, frontier_count=2)
        compact = CONTROLLER._compact_graph(receipt)

        self.assertEqual(len(compact["nodes"]), 6)
        self.assertEqual(len(compact["paths"]), 3)
        self.assertEqual(len(compact["frontier"]), 2)
        self.assertEqual(
            compact["summary"]["truncated"],
            {"nodes": 0, "paths": 0, "frontier": 0},
        )

    def test_node_cap_holds_even_when_deep_paths_demand_more(self):
        receipt = big_receipt(node_count=474, path_count=0, frontier_count=40)
        # 16 six-node chains over distinct nodes demand 96 required nodes
        receipt["paths"] = [
            {
                "id": f"PATH-{i:03d}",
                "nodes": [f"NODE-{(i * 6 + j):03d}" for j in range(6)],
                "edges": [f"EDGE-{(i * 6 + j):03d}" for j in range(5)],
                "distance": 5,
                "risk_domains": ["operations"],
            }
            for i in range(16)
        ]
        compact = CONTROLLER._compact_graph(receipt)

        self.assertLessEqual(len(compact["nodes"]), CONTROLLER.COMPACT_MAX_NODES)
        kept = {row["key"] for row in compact["nodes"]}
        for path in compact["paths"]:
            for node in path["nodes"]:
                self.assertIn(node["key"], kept)
        for row in compact["frontier"]:
            self.assertIn(row["node_key"], kept)
        payload = json.dumps(compact, ensure_ascii=False, sort_keys=True)
        self.assertLessEqual(len(payload.encode("utf-8")), 24_000)

    def test_path_and_frontier_nodes_survive_truncation(self):
        compact = CONTROLLER._compact_graph(big_receipt())
        kept = {row["key"] for row in compact["nodes"]}
        for path in compact["paths"]:
            for node in path["nodes"]:
                self.assertIn(node["key"], kept)
        for row in compact["frontier"]:
            self.assertIn(row["node_key"], kept)


if __name__ == "__main__":
    unittest.main()
