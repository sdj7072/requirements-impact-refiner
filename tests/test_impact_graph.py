import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
MODULE_PATH = ROOT / "skills" / "requirements-impact-refiner" / "scripts" / "impact_graph.py"
SPEC = importlib.util.spec_from_file_location("impact_graph", MODULE_PATH)
GRAPH = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GRAPH
SPEC.loader.exec_module(GRAPH)


def fixture(name="impact-graph-receipt.json"):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ImpactGraphTest(unittest.TestCase):
    def test_receipt_requires_path_evidence_and_unknown_frontier(self):
        value = fixture()
        self.assertEqual(GRAPH.validate_receipt(value), ())
        value["paths"][0]["edges"] = ["EDGE-999"]
        self.assertIn("unknown graph edge EDGE-999", GRAPH.validate_receipt(value))

    def test_receipt_rejects_unknown_keys(self):
        value = fixture()
        value["surprise"] = True

        self.assertIn("unknown top-level key surprise", GRAPH.validate_receipt(value))

    def test_receipt_rejects_invalid_enums(self):
        value = fixture()
        value["providers"][0]["status"] = "installed"

        self.assertIn(
            "provider builtin has invalid status installed", GRAPH.validate_receipt(value)
        )

    def test_receipt_rejects_non_object_rows_and_empty_or_duplicate_providers(self):
        value = fixture()
        value["providers"] = [42]
        self.assertIn("providers row 1 must be an object", GRAPH.validate_receipt(value))

        value = fixture()
        value["settings"]["providers"] = []
        self.assertIn(
            "settings providers must be a non-empty list of unique names",
            GRAPH.validate_receipt(value),
        )
        value["settings"]["providers"] = ["auto", "auto"]
        self.assertIn(
            "settings providers must be a non-empty list of unique names",
            GRAPH.validate_receipt(value),
        )

    def test_receipt_rejects_duplicate_ids_unsafe_paths_and_unknown_references(self):
        value = fixture()
        value["nodes"][1]["id"] = "NODE-001"
        value["edges"][0]["location"] = "/etc/passwd"
        value["nodes"][0]["location"] = "../outside.py"
        value["frontier"][0]["node"] = "NODE-999"
        value["cache"]["invalidated_nodes"] = ["NODE-999"]
        errors = GRAPH.validate_receipt(value)
        self.assertIn("duplicate graph node NODE-001", errors)
        self.assertIn("edge EDGE-001 has unsafe location /etc/passwd", errors)
        self.assertIn("node NODE-001 has unsafe location ../outside.py", errors)
        self.assertIn("frontier FRONTIER-001 references unknown graph node NODE-999", errors)
        self.assertIn("cache references unknown graph node NODE-999", errors)

    def test_receipt_prevents_provider_confidence_upgrades(self):
        value = fixture()
        value["providers"][0]["confidence"] = "lexical"
        errors = GRAPH.validate_receipt(value)
        self.assertIn("node NODE-001 upgrades provider builtin confidence", errors)

    def test_receipt_reports_malformed_provider_confidence_without_crashing(self):
        value = fixture()
        value["providers"][0]["confidence"] = ["lexical"]

        errors = GRAPH.validate_receipt(value)

        self.assertIn("provider builtin has invalid confidence ['lexical']", errors)

    def test_receipt_requires_sha_inputs(self):
        value = fixture()
        del value["request_sha256"]

        self.assertIn("missing top-level key request_sha256", GRAPH.validate_receipt(value))

    def test_receipt_enforces_string_and_collection_limits(self):
        value = fixture()
        value["nodes"][0]["label"] = "x" * (GRAPH.MAX_STRING_LENGTH + 1)
        value["nodes"] *= GRAPH.MAX_NODES + 1
        errors = GRAPH.validate_receipt(value)
        self.assertIn("node NODE-001 label exceeds maximum length", errors)
        self.assertIn("nodes exceeds maximum collection size", errors)

    def test_load_and_canonical_receipt_bytes_are_strict_and_stable(self):
        value = fixture()
        canonical = GRAPH.canonical_receipt_bytes(value)
        loaded, errors = GRAPH.load_receipt_bytes(canonical)
        self.assertEqual(errors, ())
        self.assertEqual(loaded, value)
        self.assertEqual(canonical, GRAPH.canonical_receipt_bytes(copy.deepcopy(value)))
        loaded, errors = GRAPH.load_receipt_bytes(b"\xff")
        self.assertIsNone(loaded)
        self.assertIn("receipt must be UTF-8", errors)
        _, errors = GRAPH.load_receipt_bytes(b"{" + b" " * GRAPH.MAX_RECEIPT_BYTES)
        self.assertIn("receipt exceeds maximum byte size", errors)

    def test_frozen_domain_model_uses_tuple_collections(self):
        settings = GRAPH.GraphSettings(providers=["auto"])
        receipt = GRAPH.GraphReceipt(
            receipt_id="0" * 32,
            draft_id="1" * 32,
            repo_root_sha256="2" * 64,
            request_sha256="3" * 64,
            settings=settings,
            providers=[],
            nodes=[],
            edges=[],
            paths=[],
            frontier=[],
            timings_ms={"total": 0},
            budget_status="closed",
            cache={"status": "miss", "key": "4" * 64, "invalidated_nodes": []},
        )
        self.assertEqual(settings.providers, ("auto",))
        self.assertEqual(receipt.nodes, ())
        with self.assertRaises((AttributeError, TypeError)):
            settings.max_seconds = 10
        with self.assertRaises((AttributeError, TypeError)):
            receipt.cache["invalidated_nodes"].append("NODE-001")
        self.assertEqual(
            json.loads(GRAPH.canonical_receipt_bytes(receipt))["cache"]["invalidated_nodes"],
            [],
        )

    def test_canonical_receipt_rejects_a_structurally_valid_oversized_payload(self):
        value = fixture()
        value["nodes"] = [
            {
                "id": f"NODE-{index:03d}",
                "kind": "symbol",
                "label": "x" * GRAPH.MAX_STRING_LENGTH,
                "location": "api/profile.py",
                "provider": "builtin",
                "confidence": "verified-source",
                "source_sha256": "d" * 64,
                "risk_domains": ["interfaces"],
            }
            for index in range(GRAPH.MAX_NODES)
        ]
        value["edges"] = []
        value["paths"] = []
        value["frontier"] = []
        value["budget_status"] = "closed"
        self.assertEqual(GRAPH.validate_receipt(value), ())
        with self.assertRaisesRegex(ValueError, "maximum byte size"):
            GRAPH.canonical_receipt_bytes(value)


if __name__ == "__main__":
    unittest.main()
