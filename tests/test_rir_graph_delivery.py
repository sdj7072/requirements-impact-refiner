import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SKILL_SCRIPTS = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"


def load_module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


CONTROLLER = load_module("rir_graph_delivery_controller_test", SCRIPTS / "rir_controller.py")
DELIVERY_PATH = SCRIPTS / "rir_graph_delivery.py"
DELIVERY = (
    load_module("rir_graph_delivery_test", DELIVERY_PATH) if DELIVERY_PATH.is_file() else None
)


EXPECTED_COMPACT = {
    "providers": [
        {
            "name": "builtin",
            "status": "ready",
            "confidence": "verified-source",
            "version": "builtin",
        }
    ],
    "nodes": [
        {
            "key": "NODE-001",
            "kind": "symbol",
            "label": "profile.displayName",
            "location": "api/profile.py",
            "confidence": "verified-source",
            "risk_domains": ["interfaces"],
        },
        {
            "key": "NODE-002",
            "kind": "event",
            "label": "profile.changed",
            "location": "events/profile_changed.py",
            "confidence": "lexical",
            "risk_domains": ["operations"],
        },
    ],
    "paths": [
        {
            "key": "PATH-001",
            "nodes": [
                {
                    "key": "NODE-001",
                    "label": "profile.displayName",
                    "location": "api/profile.py",
                },
                {
                    "key": "NODE-002",
                    "label": "profile.changed",
                    "location": "events/profile_changed.py",
                },
            ],
            "edges": [
                {
                    "key": "EDGE-001",
                    "kind": "publishes",
                    "confidence": "verified-source",
                }
            ],
            "distance": 1,
            "risk_domains": ["interfaces", "operations"],
        }
    ],
    "frontier": [
        {
            "key": "FRONTIER-001",
            "node_key": "NODE-002",
            "reason": "provider coverage ended",
            "risk_domains": ["operations"],
        }
    ],
    "summary": {
        "nodes": 2,
        "edges": 1,
        "paths": 1,
        "unknown_frontiers": 1,
        "timings_ms": {"total": 1},
        "budget_status": "provider_limited",
        "truncated": {"nodes": 0, "paths": 0, "frontier": 0},
    },
}


def graph_context(paths):
    receipt = json.loads((FIXTURES / "impact-graph-receipt.json").read_text(encoding="utf-8"))
    receipt["nodes"] = [
        {
            "id": "NODE-001",
            "kind": "symbol",
            "label": "remote.contract",
            "location": None,
            "provider": "builtin",
            "confidence": "lexical",
            "source_sha256": None,
            "risk_domains": ["interfaces"],
        },
        {
            "id": "NODE-009",
            "kind": "file",
            "label": "LICENSE",
            "location": "LICENSE",
            "provider": "builtin",
            "confidence": "lexical",
            "source_sha256": "d" * 64,
            "risk_domains": ["legal/policy"],
        },
    ]
    receipt["edges"] = (
        []
        if not paths
        else [
            {
                "id": "EDGE-001",
                "source": "NODE-001",
                "target": "NODE-009",
                "kind": "references",
                "location": "LICENSE",
                "evidence": "LICENSE",
                "confidence": "lexical",
                "provider": "builtin",
                "source_sha256": "d" * 64,
            }
        ]
    )
    receipt["paths"] = paths
    receipt["frontier"] = [
        {
            "id": "FRONTIER-001",
            "node": "NODE-001",
            "reason": "provider unavailable for supplied remote contract",
            "risk_domains": ["interfaces"],
        }
    ]
    return {"receipt": receipt, "sha256": "e" * 64}


def supplied_only_analysis():
    return {
        "impacts": [
            {
                "key": "member-scope",
                "state": "refining",
                "evidence_level": "unknown",
                "graph_path_keys": [],
            }
        ],
        "invariants": [],
    }


class RirGraphDeliveryTest(unittest.TestCase):
    def delivery(self):
        self.assertIsNotNone(DELIVERY, "rir_graph_delivery.py must be extracted")
        return DELIVERY

    def test_compact_graph_matches_facade_bytes(self):
        delivery = self.delivery()
        receipt = json.loads((FIXTURES / "impact-graph-receipt.json").read_text(encoding="utf-8"))
        expected = json.dumps(EXPECTED_COMPACT, sort_keys=True, separators=(",", ":"))
        actual = json.dumps(delivery.compact_graph(receipt), sort_keys=True, separators=(",", ":"))
        facade = json.dumps(
            CONTROLLER._compact_graph(receipt), sort_keys=True, separators=(",", ":")
        )
        self.assertEqual(actual, expected)
        self.assertEqual(facade, expected)

    def test_source_inventory_digest_is_canonical_and_order_independent(self):
        delivery = self.delivery()
        expected = "cc336537818b6173a384e0605b26450f21c56b85af2259192776102ba2691ec7"
        first = {"b.py": "2" * 64, "a.py": "1" * 64}
        second = {"a.py": "1" * 64, "b.py": "2" * 64}
        self.assertEqual(delivery.source_inventory_sha256(first), expected)
        self.assertEqual(delivery.source_inventory_sha256(second), expected)

    def test_zero_path_unknown_without_rationale_is_rejected(self):
        delivery = self.delivery()
        analysis = supplied_only_analysis()
        context = graph_context([])

        with self.assertRaisesRegex(
            ValueError,
            "^supplied-only or unknown graph coverage requires rationale and unknown evidence$",
        ):
            delivery.validate_graph_coverage(analysis, context)

    def test_uncovered_high_risk_node_is_rejected(self):
        delivery = self.delivery()
        paths = [
            {
                "id": "PATH-001",
                "nodes": ["NODE-001", "NODE-009"],
                "edges": ["EDGE-001"],
                "distance": 1,
                "risk_domains": ["interfaces", "legal/policy"],
            }
        ]
        analysis = supplied_only_analysis()
        analysis["impacts"][0]["coverage_rationale"] = "No repository path was selected."

        with self.assertRaisesRegex(ValueError, "uncovered high-risk graph node NODE-009"):
            delivery.validate_graph_coverage(analysis, graph_context(paths))

    def test_hidden_compact_path_does_not_create_impossible_coverage_requirement(self):
        delivery = self.delivery()
        receipt = graph_context([])["receipt"]
        receipt["frontier"] = []
        receipt["nodes"] = []
        receipt["edges"] = []
        receipt["paths"] = []
        for index in range(17):
            source = f"NODE-{index * 2 + 1:03d}"
            target = f"NODE-{index * 2 + 2:03d}"
            edge = f"EDGE-{index + 1:03d}"
            path = f"PATH-{index + 1:03d}"
            for identifier in (source, target):
                receipt["nodes"].append(
                    {
                        "id": identifier,
                        "kind": "file",
                        "label": identifier.lower(),
                        "location": f"src/{identifier.lower()}.py",
                        "provider": "builtin",
                        "confidence": "lexical",
                        "source_sha256": None,
                        "risk_domains": ["interfaces"],
                    }
                )
            receipt["edges"].append(
                {
                    "id": edge,
                    "source": source,
                    "target": target,
                    "kind": "references",
                    "location": f"src/path-{index + 1:03d}.py",
                    "evidence": "shared contract",
                    "confidence": "lexical",
                    "provider": "builtin",
                    "source_sha256": None,
                }
            )
            receipt["paths"].append(
                {
                    "id": path,
                    "nodes": [source, target],
                    "edges": [edge],
                    "distance": 1,
                    "risk_domains": ["interfaces"],
                }
            )
        compact = delivery.compact_graph(receipt)
        visible_paths = [row["key"] for row in compact["paths"]]
        self.assertEqual(len(visible_paths), delivery.COMPACT_MAX_PATHS)
        self.assertNotIn("PATH-017", visible_paths)
        analysis = supplied_only_analysis()
        analysis["impacts"][0]["graph_path_keys"] = visible_paths

        delivery.validate_graph_coverage(
            analysis,
            {
                "receipt": receipt,
                "sha256": "e" * 64,
                "exposed_path_ids": visible_paths,
            },
        )

    def test_hidden_compact_path_cannot_be_guessed_into_the_report(self):
        delivery = self.delivery()
        paths = [
            {
                "id": "PATH-001",
                "nodes": ["NODE-001", "NODE-009"],
                "edges": ["EDGE-001"],
                "distance": 1,
                "risk_domains": ["interfaces", "legal/policy"],
            }
        ]
        analysis = supplied_only_analysis()
        analysis["impacts"][0]["graph_path_keys"] = ["PATH-001"]

        with self.assertRaisesRegex(
            ValueError,
            "graph path key PATH-001 was not exposed to the analysis",
        ):
            delivery.validate_graph_coverage(
                analysis,
                {
                    **graph_context(paths),
                    "exposed_path_ids": [],
                },
            )

    def test_root_and_skill_delivery_resolve_only_their_own_dependency_graph(self):
        self.delivery()
        exact_names = {
            "rir_contracts",
            "rir_storage",
            "rir_graph_delivery",
            "graph_coordinator",
            "impact_graph",
            "graph_cache",
            "_rir_impact_graph",
            "_rir_graph_builtin",
            "_rir_graph_cache",
            "_rir_graph_providers",
        }
        prefixes = (
            "_rir_graph_delivery_contracts_",
            "_rir_graph_delivery_storage_",
            "_rir_graph_delivery_schema_",
            "_rir_graph_delivery_builtin_",
            "_rir_graph_delivery_cache_",
            "_rir_graph_delivery_providers_",
            "_rir_graph_delivery_coordinator_",
        )
        preserved = {
            name: module
            for name, module in sys.modules.items()
            if name in exact_names or name.startswith(prefixes)
        }
        loaded_names = []

        def clear_dependencies():
            for name in tuple(sys.modules):
                if name in exact_names or name.startswith(prefixes):
                    sys.modules.pop(name, None)

        def assert_local(module, directory):
            expected = {
                "CONTRACTS": directory / "rir_contracts.py",
                "STORAGE": directory / "rir_storage.py",
                "GRAPH_COORDINATOR": directory / "graph_coordinator.py",
                "GRAPH": directory / "impact_graph.py",
            }
            for attribute, path in expected.items():
                self.assertEqual(
                    Path(getattr(module, attribute).__file__).resolve(), path.resolve()
                )
            self.assertEqual(
                Path(module.GRAPH_COORDINATOR.CACHE.__file__).resolve(),
                (directory / "graph_cache.py").resolve(),
            )
            self.assertIs(module.GRAPH_COORDINATOR.GRAPH, module.GRAPH)
            self.assertIs(module.GRAPH_COORDINATOR.CACHE.GRAPH, module.GRAPH)

        try:
            clear_dependencies()
            with tempfile.TemporaryDirectory() as temporary:
                conflict_path = Path(temporary) / "conflict.py"
                conflict_path.write_text("value = 'conflict'\n", encoding="utf-8")
                conflicts = {}
                for name in exact_names:
                    conflict = types.ModuleType(name)
                    conflict.__file__ = str(conflict_path)
                    sys.modules[name] = conflict
                    conflicts[name] = conflict

                root_first_name = "graph_delivery_collision_root_one"
                root_repeat_name = "graph_delivery_collision_root_two"
                root_vacated_name = "graph_delivery_vacated_root"
                loaded_names.extend((root_first_name, root_repeat_name, root_vacated_name))
                root_first = load_module(root_first_name, SCRIPTS / "rir_graph_delivery.py")
                root_repeat = load_module(root_repeat_name, SCRIPTS / "rir_graph_delivery.py")
                assert_local(root_first, SCRIPTS)
                assert_local(root_repeat, SCRIPTS)
                self.assertIs(root_first.CONTRACTS, root_repeat.CONTRACTS)
                self.assertIs(root_first.STORAGE, root_repeat.STORAGE)
                self.assertIs(root_first.GRAPH_COORDINATOR, root_repeat.GRAPH_COORDINATOR)
                for name, conflict in conflicts.items():
                    self.assertIs(sys.modules[name], conflict)

                for name in exact_names:
                    sys.modules.pop(name, None)
                root_vacated = load_module(root_vacated_name, SCRIPTS / "rir_graph_delivery.py")
                assert_local(root_vacated, SCRIPTS)
                self.assertIs(root_vacated.CONTRACTS, root_first.CONTRACTS)
                self.assertIs(root_vacated.STORAGE, root_first.STORAGE)
                self.assertIs(root_vacated.GRAPH_COORDINATOR, root_first.GRAPH_COORDINATOR)

                for name, conflict in conflicts.items():
                    sys.modules[name] = conflict
                skill_first_name = "graph_delivery_collision_skill_one"
                skill_repeat_name = "graph_delivery_collision_skill_two"
                skill_vacated_name = "graph_delivery_vacated_skill"
                loaded_names.extend((skill_first_name, skill_repeat_name, skill_vacated_name))
                skill_first = load_module(skill_first_name, SKILL_SCRIPTS / "rir_graph_delivery.py")
                skill_repeat = load_module(
                    skill_repeat_name, SKILL_SCRIPTS / "rir_graph_delivery.py"
                )
                assert_local(skill_first, SKILL_SCRIPTS)
                assert_local(skill_repeat, SKILL_SCRIPTS)
                self.assertIs(skill_first.CONTRACTS, skill_repeat.CONTRACTS)
                self.assertIs(skill_first.STORAGE, skill_repeat.STORAGE)
                self.assertIs(skill_first.GRAPH_COORDINATOR, skill_repeat.GRAPH_COORDINATOR)
                self.assertIsNot(skill_first.CONTRACTS, root_first.CONTRACTS)
                self.assertIsNot(skill_first.STORAGE, root_first.STORAGE)
                self.assertIsNot(skill_first.GRAPH_COORDINATOR, root_first.GRAPH_COORDINATOR)
                for name, conflict in conflicts.items():
                    self.assertIs(sys.modules[name], conflict)

                for name in exact_names:
                    sys.modules.pop(name, None)
                skill_vacated = load_module(
                    skill_vacated_name, SKILL_SCRIPTS / "rir_graph_delivery.py"
                )
                assert_local(skill_vacated, SKILL_SCRIPTS)
                self.assertIs(skill_vacated.CONTRACTS, skill_first.CONTRACTS)
                self.assertIs(skill_vacated.STORAGE, skill_first.STORAGE)
                self.assertIs(skill_vacated.GRAPH_COORDINATOR, skill_first.GRAPH_COORDINATOR)
        finally:
            clear_dependencies()
            sys.modules.update(preserved)
            for name in loaded_names:
                sys.modules.pop(name, None)

    def test_clean_dependency_alias_vacation_reuses_established_coordinator_graph(self):
        self.delivery()
        exact_names = {
            "rir_contracts",
            "rir_storage",
            "_rir_impact_graph",
            "_rir_graph_builtin",
            "_rir_graph_cache",
            "_rir_graph_providers",
        }
        prefixes = (
            "_rir_graph_delivery_contracts_",
            "_rir_graph_delivery_storage_",
            "_rir_graph_delivery_schema_",
            "_rir_graph_delivery_builtin_",
            "_rir_graph_delivery_cache_",
            "_rir_graph_delivery_providers_",
            "_rir_graph_delivery_coordinator_",
        )
        preserved = {
            name: module
            for name, module in sys.modules.items()
            if name in exact_names or name.startswith(prefixes)
        }
        module_names = ("graph_delivery_clean_first", "graph_delivery_clean_vacated")
        try:
            for name in tuple(sys.modules):
                if name in exact_names or name.startswith(prefixes):
                    sys.modules.pop(name, None)
            first = load_module(module_names[0], SCRIPTS / "rir_graph_delivery.py")
            for name in exact_names:
                sys.modules.pop(name, None)

            second = load_module(module_names[1], SCRIPTS / "rir_graph_delivery.py")

            self.assertIs(second.GRAPH_COORDINATOR, first.GRAPH_COORDINATOR)
            self.assertIs(second.GRAPH, first.GRAPH)
            self.assertIs(second.GRAPH_COORDINATOR.CACHE, first.GRAPH_COORDINATOR.CACHE)
        finally:
            for name in tuple(sys.modules):
                if name in exact_names or name.startswith(prefixes):
                    sys.modules.pop(name, None)
            sys.modules.update(preserved)
            for name in module_names:
                sys.modules.pop(name, None)

    def test_controller_facade_uses_the_extracted_sibling_and_mirror_is_identical(self):
        delivery = self.delivery()
        for name in (
            "compact_graph",
            "source_inventory_sha256",
            "new_trace_intent",
            "validate_trace_intent",
            "load_graph_context",
            "validate_graph_coverage",
            "trace_impact",
        ):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(delivery, name, None)))
        self.assertEqual(
            Path(CONTROLLER.GRAPH_DELIVERY.__file__).resolve(), DELIVERY_PATH.resolve()
        )
        self.assertEqual(
            DELIVERY_PATH.read_bytes(),
            (SKILL_SCRIPTS / "rir_graph_delivery.py").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
