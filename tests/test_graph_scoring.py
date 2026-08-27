import hashlib
import importlib
import importlib.util
import tempfile
import unittest
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
        return self.module().load_graph_cases(ROOT / "evals" / "graph-cases.json")[0]

    def receipt(self, case=None):
        selected = case or self.case()
        providers = ["builtin"]
        nodes = []
        edges = []
        for index, required in enumerate(selected.required_nodes, start=1):
            nodes.append(
                {
                    "id": f"NODE-{index:03d}",
                    "kind": required.kind,
                    "label": required.label,
                    "location": required.location,
                    "provider": "builtin",
                    "confidence": "structural-inferred" if index == 1 else "lexical",
                    "source_sha256": str(index) * 64,
                    "risk_domains": list(required.risk_domains),
                }
            )
        for index, kind in enumerate(selected.required_edge_types, start=1):
            edges.append(
                {
                    "id": f"EDGE-{index:03d}",
                    "source": f"NODE-{index:03d}",
                    "target": f"NODE-{index + 1:03d}",
                    "kind": kind,
                    "location": selected.required_nodes[index].location,
                    "evidence": f"fixture-link-{index}",
                    "confidence": "lexical",
                    "provider": "builtin",
                    "source_sha256": str(index + 4) * 64,
                }
            )
        return {
            "schema_version": 1,
            "receipt_id": "a" * 32,
            "draft_id": "b" * 32,
            "repo_root_sha256": "c" * 64,
            "request_sha256": "d" * 64,
            "settings": {
                "enabled": True,
                "max_seconds": 30,
                "target_seconds": 10,
                "providers": ["builtin"],
                "install_policy": "never",
                "deep": False,
            },
            "providers": [
                {
                    "name": name,
                    "status": "ready",
                    "confidence": "structural-inferred",
                    "version": "builtin-v1",
                    "executable_sha256": None,
                }
                for name in providers
            ],
            "nodes": nodes,
            "edges": edges,
            "paths": [
                {
                    "id": "PATH-001",
                    "nodes": [row["id"] for row in nodes],
                    "edges": [row["id"] for row in edges],
                    "distance": 3,
                    "risk_domains": sorted(
                        {domain for row in nodes for domain in row["risk_domains"]}
                    ),
                }
            ],
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

    def test_scoring_reuses_the_packaged_receipt_validator_and_exact_dialect(self):
        module = self.module()
        receipt = self.receipt()
        production_bytes = module.GRAPH_CONTRACT.canonical_receipt_bytes(receipt)

        score = module.score_graph(
            self.case(),
            receipt,
            "Impact scan: 8.4 s\nImpact paths: PATH-001",
        )

        self.assertIs(
            module.canonical_receipt_bytes,
            module.GRAPH_CONTRACT.canonical_receipt_bytes,
        )
        self.assertFalse(production_bytes.endswith(b"\n"))
        self.assertEqual(
            score.receipt_sha256,
            hashlib.sha256(production_bytes).hexdigest(),
        )

    def test_actual_builtin_coordinator_receipt_scores_in_production_dialect(self):
        module = self.module()
        case = self.case()
        from evals.harness.adapters.codex import CodexAdapter
        from tests.test_graph_coordinator import COORDINATOR, FakeClock, NeverRunner

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            CodexAdapter._stage_graph_fixture(case.id, root)
            receipt = COORDINATOR.trace_impact(
                root,
                {"draft_id": "1" * 32, "request": case.request},
                tuple(COORDINATOR.ScanSeed(term, location) for term, location in case.seeds),
                COORDINATOR.GraphSettings(
                    providers=("builtin",), max_seconds=30, target_seconds=10
                ),
                clock=FakeClock(),
                runner=NeverRunner(),
            )
            payload = COORDINATOR.GRAPH.canonical_receipt_bytes(receipt)
            mapping, errors = module.GRAPH_CONTRACT.load_receipt_bytes(payload)

        self.assertEqual(errors, ())
        score = module.score_graph(
            case,
            mapping,
            "Impact scan: 0.0 s\nImpact paths: distant",
        )
        self.assertTrue(score.passed, score.findings)
        self.assertEqual(score.receipt_sha256, hashlib.sha256(payload).hexdigest())

    def test_production_invalid_receipts_never_reach_graph_scoring(self):
        module = self.module()
        output = "Impact scan: 8.4 s\nImpact paths: PATH-001"
        mutations = {}
        unknown = self.receipt()
        unknown["unexpected"] = True
        mutations["unknown-key"] = unknown
        disconnected = self.receipt()
        disconnected["edges"][0]["source"] = "NODE-004"
        mutations["disconnected"] = disconnected
        missing_provider = self.receipt()
        missing_provider["providers"] = []
        mutations["missing-provider"] = missing_provider

        for name, receipt in mutations.items():
            with self.subTest(name=name):
                self.assertTrue(module.GRAPH_CONTRACT.validate_receipt(receipt))
                score = module.score_graph(self.case(), receipt, output)
                self.assertFalse(score.passed)
                self.assertTrue(
                    any("production receipt validation" in row for row in score.findings),
                    score.findings,
                )

    def test_builtin_suite_rejects_optional_provider_settings_and_inventory(self):
        module = self.module()
        receipt = self.receipt()
        receipt["settings"]["providers"] = ["ast-grep", "builtin"]
        receipt["providers"].insert(
            0,
            {
                "name": "ast-grep",
                "status": "missing",
                "confidence": "lexical",
                "version": None,
                "executable_sha256": None,
            },
        )

        self.assertEqual(module.GRAPH_CONTRACT.validate_receipt(receipt), ())
        score = module.score_graph(
            self.case(),
            receipt,
            "Impact scan: 8.4 s\nImpact paths: PATH-001",
        )
        self.assertFalse(score.passed)
        self.assertTrue(any("provider policy" in row for row in score.findings))

    def test_required_node_is_one_exact_label_kind_location_and_risk_record(self):
        module = self.module()
        case = self.case()
        output = "Impact scan: 8.4 s\nImpact paths: PATH-001"
        wrong_label = self.receipt(case)
        wrong_label["nodes"][0]["label"] = "wrong.profile.label"

        split = self.receipt(case)
        exact = split["nodes"][0]
        exact["label"] = "wrong.profile.label"
        exact["risk_domains"] = ["functionality"]
        split_node = {
            **exact,
            "id": "NODE-005",
            "kind": "file",
            "label": case.required_nodes[0].label,
            "risk_domains": list(case.required_nodes[0].risk_domains),
        }
        split["nodes"].insert(1, split_node)
        split["edges"].insert(
            0,
            {
                "id": "EDGE-004",
                "source": "NODE-001",
                "target": "NODE-005",
                "kind": "references",
                "location": exact["location"],
                "evidence": "split semantics",
                "confidence": "lexical",
                "provider": "builtin",
                "source_sha256": "9" * 64,
            },
        )
        split["edges"][1]["source"] = "NODE-005"
        split["paths"][0] = {
            **split["paths"][0],
            "nodes": ["NODE-001", "NODE-005", "NODE-002", "NODE-003", "NODE-004"],
            "edges": ["EDGE-004", "EDGE-001", "EDGE-002", "EDGE-003"],
            "distance": 4,
        }

        for name, receipt in (("wrong-label", wrong_label), ("split-node", split)):
            with self.subTest(name=name):
                self.assertEqual(module.GRAPH_CONTRACT.validate_receipt(receipt), ())
                score = module.score_graph(case, receipt, output)
                self.assertFalse(score.passed)
                self.assertTrue(any("required node identity" in row for row in score.findings))

    def test_scoring_rejects_each_case_contract_mutation(self):
        module = self.module()
        case = self.case()
        output = "Impact scan: 8.4 s\nImpact paths: PATH-001"
        mutations = {}
        missing_node = self.receipt(case)
        missing_node["paths"][0]["nodes"] = missing_node["paths"][0]["nodes"][:-1]
        mutations["missing-node"] = ("production receipt validation", missing_node)
        short = self.receipt(case)
        short["paths"][0]["distance"] = 2
        mutations["short-distance"] = ("production receipt validation", short)
        wrong_edge = self.receipt(case)
        wrong_edge["edges"][0]["kind"] = "calls"
        mutations["wrong-edge"] = ("required edge types", wrong_edge)
        provider = self.receipt(case)
        provider["nodes"][0]["provider"] = "remote-service"
        mutations["unknown-provider"] = ("production receipt validation", provider)
        fabricated = self.receipt(case)
        fabricated["nodes"][0]["confidence"] = "verified-provider"
        mutations["confidence-upgrade"] = ("production receipt validation", fabricated)
        frontier = self.receipt(case)
        frontier["frontier"] = [
            {
                "id": "FRONTIER-001",
                "node": "NODE-004",
                "reason": "unexpected",
                "risk_domains": ["regression"],
            }
        ]
        mutations["unexpected-frontier"] = ("unknown frontier expectation", frontier)
        wrong_risk = self.receipt(case)
        wrong_risk["nodes"][0]["risk_domains"] = ["functionality"]
        mutations["wrong-risk"] = ("required node identity", wrong_risk)

        for name, (finding, receipt) in mutations.items():
            with self.subTest(name=name):
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
        receipt["nodes"].append(
            {
                "id": "NODE-005",
                "kind": "permission",
                "label": "uncovered auth",
                "location": "auth/uncovered.py",
                "provider": "builtin",
                "confidence": "lexical",
                "source_sha256": "9" * 64,
                "risk_domains": ["authorization/privacy"],
            }
        )

        uncovered = module.score_graph(case, receipt, "Impact scan: 8.4 s\nImpact paths: PATH-001")
        receipt["frontier"] = [
            {
                "id": "FRONTIER-001",
                "node": "NODE-005",
                "reason": "bounded unknown",
                "risk_domains": ["authorization/privacy"],
            }
        ]
        visible = module.score_graph(case, receipt, "Impact scan: 8.4 s\nImpact paths: PATH-001")

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
