import importlib
import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GraphScoringTest(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(
            importlib.util.find_spec("evals.harness.graph_scoring"),
            "graph evaluation needs deterministic receipt scoring",
        )
        return importlib.import_module("evals.harness.graph_scoring")

    def case(self):
        return self.module().load_graph_cases(
            ROOT / "evals" / "graph-cases.json"
        )[0]

    def receipt(self, case=None):
        selected = case or self.case()
        providers = ["builtin", "ast-grep"]
        nodes = []
        edges = []
        for index, required in enumerate(selected.required_nodes, start=1):
            nodes.append({
                "id": f"NODE-{index:03d}",
                "kind": required.kind,
                "label": required.label,
                "location": required.location,
                "provider": "builtin",
                "confidence": "structural-inferred" if index == 1 else "lexical",
                "source_sha256": str(index) * 64,
                "risk_domains": list(required.risk_domains),
            })
        for index, kind in enumerate(selected.required_edge_types, start=1):
            edges.append({
                "id": f"EDGE-{index:03d}",
                "source": f"NODE-{index:03d}",
                "target": f"NODE-{index + 1:03d}",
                "kind": kind,
                "location": selected.required_nodes[index].location,
                "evidence": f"fixture-link-{index}",
                "confidence": "lexical",
                "provider": "builtin",
                "source_sha256": str(index + 4) * 64,
            })
        return {
            "schema_version": 1,
            "receipt_id": "a" * 32,
            "draft_id": "b" * 32,
            "repo_root_sha256": "c" * 64,
            "request_sha256": "d" * 64,
            "settings": {"enabled": True, "max_seconds": 30, "target_seconds": 10, "providers": ["auto"], "install_policy": "never", "deep": False},
            "providers": [{"name": name, "status": "ready" if name == "builtin" else "missing", "confidence": "verified-source" if name == "builtin" else "lexical", "version": "builtin" if name == "builtin" else None, "executable_sha256": "e" * 64 if name == "builtin" else None} for name in providers],
            "nodes": nodes,
            "edges": edges,
            "paths": [{"id": "PATH-001", "nodes": [row["id"] for row in nodes], "edges": [row["id"] for row in edges], "distance": 3, "risk_domains": sorted({domain for row in nodes for domain in row["risk_domains"]})}],
            "frontier": [],
            "timings_ms": {"total": 8400},
            "budget_status": "closed",
            "cache": {"status": "miss", "key": "f" * 64, "invalidated_nodes": []},
        }

    def test_api_to_cache_case_requires_distant_path_and_provenance(self):
        module = self.module()
        case = self.case()
        receipt = self.receipt(case)
        output = "Impact scan: 8.4 s\nImpact paths: PATH-001"

        score = module.score_graph(case, receipt, output)

        self.assertTrue(score.passed, score.findings)
        self.assertGreaterEqual(score.maximum_required_distance, 3)
        self.assertEqual(score.receipt_id, "a" * 32)
        self.assertRegex(score.receipt_sha256, r"^[0-9a-f]{64}$")
        self.assertEqual(score.uncovered_high_risk_nodes, ())

    def test_scoring_rejects_each_case_contract_mutation(self):
        module = self.module()
        case = self.case()
        output = "Impact scan: 8.4 s\nImpact paths: PATH-001"
        mutations = {}
        missing_node = self.receipt(case)
        missing_node["paths"][0]["nodes"] = missing_node["paths"][0]["nodes"][:-1]
        mutations["required graph path"] = missing_node
        short = self.receipt(case)
        short["paths"][0]["distance"] = 2
        mutations["minimum distance"] = short
        wrong_edge = self.receipt(case)
        wrong_edge["edges"][0]["kind"] = "calls"
        mutations["required edge types"] = wrong_edge
        provider = self.receipt(case)
        provider["nodes"][0]["provider"] = "remote-service"
        mutations["disallowed provider"] = provider
        fabricated = self.receipt(case)
        fabricated["nodes"][0]["confidence"] = "verified-provider"
        mutations["forbidden fabricated precision"] = fabricated
        frontier = self.receipt(case)
        frontier["frontier"] = [{"id": "FRONTIER-001", "node": "NODE-004", "reason": "unexpected", "risk_domains": ["regression"]}]
        mutations["unknown frontier expectation"] = frontier
        wrong_risk = self.receipt(case)
        wrong_risk["nodes"][0]["risk_domains"] = ["functionality"]
        mutations["required node risk domains"] = wrong_risk

        for finding, receipt in mutations.items():
            with self.subTest(finding=finding):
                score = module.score_graph(case, receipt, output)
                self.assertFalse(score.passed)
                self.assertTrue(any(finding in row for row in score.findings), score.findings)

        phrase = module.score_graph(case, self.receipt(case), "Impact scan: 8.4 s")
        self.assertFalse(phrase.passed)
        self.assertTrue(any("compact output phrase" in row for row in phrase.findings))

    def test_high_risk_nodes_must_be_on_a_path_or_visible_frontier(self):
        module = self.module()
        case = self.case()
        receipt = self.receipt(case)
        receipt["nodes"].append({
            "id": "NODE-005", "kind": "permission", "label": "uncovered auth",
            "location": "auth/uncovered.py", "provider": "builtin", "confidence": "lexical",
            "source_sha256": "9" * 64, "risk_domains": ["authorization/privacy"],
        })

        uncovered = module.score_graph(
            case, receipt, "Impact scan: 8.4 s\nImpact paths: PATH-001"
        )
        receipt["frontier"] = [{"id": "FRONTIER-001", "node": "NODE-005", "reason": "bounded unknown", "risk_domains": ["authorization/privacy"]}]
        visible = module.score_graph(
            case, receipt, "Impact scan: 8.4 s\nImpact paths: PATH-001"
        )

        self.assertFalse(uncovered.passed)
        self.assertEqual(uncovered.uncovered_high_risk_nodes, ("NODE-005",))
        self.assertEqual(visible.uncovered_high_risk_nodes, ())

    def test_negative_case_requires_absent_receipt(self):
        module = self.module()
        case = module.load_graph_cases(ROOT / "evals" / "graph-cases.json")[-1]

        self.assertTrue(module.score_graph(case, None, "No repository change.").passed)
        self.assertFalse(module.score_graph(case, self.receipt(), "No repository change.").passed)


if __name__ == "__main__":
    unittest.main()
