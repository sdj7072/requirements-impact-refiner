import importlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "evals" / "graph-cases.json"
EXPECTED_IDS = (
    "GRAPH-api-mobile-cache-migration",
    "GRAPH-auth-role-audit-consumer",
    "GRAPH-event-retry-idempotency-side-effect",
    "GRAPH-schema-serializer-backfill-export",
    "GRAPH-config-deploy-worker-health",
    "GRAPH-negative-no-change",
)


class GraphEvalCasesTest(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(
            importlib.util.find_spec("evals.harness.graph_scoring"),
            "graph evaluation needs a strict graph catalog/scorer module",
        )
        return importlib.import_module("evals.harness.graph_scoring")

    def test_checked_in_catalog_is_exact_six_deterministic_cases(self):
        cases = self.module().load_graph_cases(CATALOG)

        self.assertEqual(tuple(case.id for case in cases), EXPECTED_IDS)
        self.assertEqual(sum(case.kind == "positive" for case in cases), 5)
        self.assertEqual(sum(case.kind == "negative" for case in cases), 1)
        for case in cases[:-1]:
            self.assertEqual(len(case.required_nodes), 4)
            self.assertEqual(case.minimum_path_distance, 3)
            self.assertTrue(case.required_edge_types)
            self.assertTrue(case.forbidden_precision)
            self.assertEqual(case.allowed_providers, ("builtin",))
            self.assertIsInstance(case.unknown_frontier_expected, bool)
            self.assertEqual(
                case.compact_output_phrases,
                ("Impact scan:", "Impact paths:"),
            )
            self.assertEqual(len(case.fixture_files), 4)
            self.assertTrue(
                all(path and not path.startswith("/") for path, _ in case.fixture_files)
            )
        negative = cases[-1]
        self.assertEqual(negative.required_nodes, ())
        self.assertEqual(negative.fixture_files, ())
        self.assertFalse(negative.controller_required)

    def test_graph_cases_convert_to_one_turn_harness_cases_without_rubric_leakage(self):
        cases = self.module().load_graph_cases(CATALOG)

        converted = tuple(case.to_case_spec() for case in cases)

        self.assertEqual(tuple(case.id for case in converted), EXPECTED_IDS)
        self.assertTrue(all(len(case.turns) == 1 for case in converted))
        self.assertTrue(all(case.modes == ("codex",) for case in converted))
        for source, case in zip(cases, converted):
            prompt = case.turns[0].prompt
            self.assertNotIn("required_nodes", prompt)
            self.assertNotIn("minimum_path_distance", prompt)
            self.assertNotIn("must_detect", prompt)
            self.assertEqual(case.kind, source.kind)

    def test_each_positive_fixture_mechanically_contains_its_distant_path(self):
        from evals.harness.adapters.codex import CodexAdapter

        path = ROOT / "skills/requirements-impact-refiner/scripts/graph_builtin.py"
        spec = importlib.util.spec_from_file_location("task7_graph_fixture_scan", path)
        scanner = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = scanner
        spec.loader.exec_module(scanner)

        class Clock:
            @staticmethod
            def monotonic():
                return 0.0

        for case in self.module().load_graph_cases(CATALOG)[:-1]:
            with self.subTest(case=case.id), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                CodexAdapter._stage_graph_fixture(case.id, root)
                result = scanner.scan_repository(
                    root,
                    tuple(scanner.ScanSeed(term, location) for term, location in case.seeds),
                    scanner.ScanLimits(),
                    Clock(),
                )
                nodes = {row.id: row for row in result.nodes}
                edges = {row.id: row for row in result.edges}
                required_locations = tuple(row.location for row in case.required_nodes)
                by_location = {row.location: row for row in result.nodes}
                for required in case.required_nodes:
                    observed = by_location[required.location]
                    self.assertEqual(observed.label, required.label)
                    self.assertEqual(observed.kind, required.kind)
                    self.assertTrue(set(required.risk_domains).issubset(observed.risk_domains))
                found = False
                for graph_path in result.paths:
                    locations = tuple(nodes[key].location for key in graph_path.nodes)
                    edge_types = tuple(edges[key].kind for key in graph_path.edges)
                    location_iter = iter(locations)
                    edge_iter = iter(edge_types)
                    if (
                        all(
                            any(value == candidate for candidate in location_iter)
                            for value in required_locations
                        )
                        and all(
                            any(value == candidate for candidate in edge_iter)
                            for value in case.required_edge_types
                        )
                        and graph_path.distance >= case.minimum_path_distance
                    ):
                        found = True
                        break
                self.assertTrue(found, case.id)
                self.assertEqual(result.frontier, ())

    def test_catalog_rejects_duplicate_ids_unsafe_fixture_paths_and_unknown_fields(self):
        module = self.module()
        raw = json.loads(CATALOG.read_text(encoding="utf-8"))
        mutations = []
        duplicated = json.loads(json.dumps(raw))
        duplicated["cases"][1]["id"] = duplicated["cases"][0]["id"]
        mutations.append(duplicated)
        traversal = json.loads(json.dumps(raw))
        traversal["cases"][0]["fixture_files"][0]["path"] = "../outside.py"
        mutations.append(traversal)
        absolute = json.loads(json.dumps(raw))
        absolute["cases"][0]["fixture_files"][0]["path"] = "/tmp/outside.py"
        mutations.append(absolute)
        unknown = json.loads(json.dumps(raw))
        unknown["cases"][0]["surprise"] = True
        mutations.append(unknown)

        for index, mutation in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "cases.json"
                path.write_text(json.dumps(mutation), encoding="utf-8")
                with self.assertRaises(module.GraphCatalogError):
                    module.load_graph_cases(path)


if __name__ == "__main__":
    unittest.main()
