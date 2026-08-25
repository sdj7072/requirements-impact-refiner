from __future__ import annotations

import hashlib
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
LINEAGE_PATH = SCRIPTS / "rir_lineage.py"


def load_module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


LINEAGE = load_module("rir_lineage_test", LINEAGE_PATH) if LINEAGE_PATH.is_file() else None


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def canonical_bytes(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def revision_two_draft():
    return {
        "report_id": "RPT-001",
        "revision": 2,
        "previous_sha256": "a" * 64,
        "request": "Let workspace members edit every project.",
        "settings": {
            "audience": "balanced",
            "audience_source": "default",
            "delivery": "compact",
            "delivery_source": "default",
        },
        "adapter": "generic",
        "prior_state": fixture("compact-state-post-decision.json"),
        "prior_key_map": {
            "invariants": {"existing-roles": "INV-001"},
            "impacts": {"member-scope": "IMP-001"},
            "decisions": {"own-workspace": "DEC-001"},
            "criteria": {"member-boundary": "AC-001"},
        },
    }


def graph_context():
    return {
        "receipt": fixture("impact-graph-receipt.json"),
        "sha256": "b" * 64,
        "impact_paths": {"member-scope": ["PATH-001"]},
        "rationales": {"member-scope": None},
    }


class RirLineageTest(unittest.TestCase):
    def lineage(self):
        self.assertIsNotNone(LINEAGE, "rir_lineage.py must be extracted")
        return LINEAGE

    def test_revision_two_preserves_ids_delta_graph_provenance_and_canonical_bytes(self):
        lineage = self.lineage()

        state, key_map = lineage.build_state(
            revision_two_draft(),
            fixture("controller-analysis-post-decision.json"),
            graph_context(),
        )

        self.assertEqual(state["report"]["revision"], 2)
        self.assertEqual(state["impacts"][0]["id"], "IMP-001")
        self.assertEqual(state["delta"]["unchanged"], ["IMP-001"])
        self.assertEqual(state["delta"]["new"], [])
        self.assertEqual(
            state["graph_paths"],
            [
                {
                    "impact": "IMP-001",
                    "paths": [
                        {
                            "id": "PATH-001",
                            "labels": ["profile.displayName", "profile.changed"],
                            "providers": ["builtin"],
                            "confidence": "lexical",
                            "locations": ["api/profile.py", "events/profile_changed.py"],
                        }
                    ],
                }
            ],
        )
        self.assertEqual(
            key_map,
            {
                "invariants": {"existing-roles": "INV-001"},
                "impacts": {"member-scope": "IMP-001"},
                "decisions": {"own-workspace": "DEC-001"},
                "criteria": {"member-boundary": "AC-001"},
            },
        )
        self.assertEqual(
            hashlib.sha256(canonical_bytes(state)).hexdigest(),
            "581e4e0a02dbfccd81d5b8eac2e3cb323770433cd05b0467610c13f5846f9bfa",
        )

    def test_public_key_allocation_mapping_and_legacy_lineage_are_stable(self):
        lineage = self.lineage()
        rows = ({"key": "kept"}, {"key": "new"})

        self.assertIs(lineage.BeginRequest, lineage.CONTRACTS.BeginRequest)
        self.assertEqual(
            lineage.allocate_ids(rows, "IMP", {"kept": "IMP-002"}),
            {"kept": "IMP-002", "new": "IMP-001"},
        )
        self.assertEqual(
            lineage.map_keys(("kept", "new"), {"kept": "IMP-002", "new": "IMP-001"}, "impact"),
            ["IMP-002", "IMP-001"],
        )
        with self.assertRaisesRegex(ValueError, "^unknown impact key missing$"):
            lineage.map_keys(("missing",), {}, "impact")
        self.assertEqual(
            lineage.legacy_key_map(fixture("compact-state-post-decision.json")),
            {
                "invariants": {"legacy-inv-001": "INV-001"},
                "impacts": {"legacy-imp-001": "IMP-001"},
                "decisions": {"legacy-dec-001": "DEC-001"},
                "criteria": {"legacy-ac-001": "AC-001"},
            },
        )

    def test_current_lineage_loads_a_published_revision_and_derives_legacy_keys(self):
        lineage = self.lineage()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            state = fixture("compact-state-post-decision.json")
            published = lineage.REPORT_STORE.publish_revision(root, canonical_bytes(state))

            current, selected, key_map = lineage.current_lineage(root)

        self.assertEqual(current, published)
        self.assertEqual(selected, state)
        self.assertEqual(key_map["impacts"], {"legacy-imp-001": "IMP-001"})

    def test_root_and_skill_lineage_resolve_local_dependencies_on_conflict_repeat_and_vacation(
        self,
    ):
        self.lineage()
        exact_names = {
            "rir_contracts",
            "rir_storage",
            "compact_state",
            "impact_report",
            "impact_renderer",
            "report_store",
        }
        prefixes = (
            "_rir_lineage_contracts_",
            "_rir_lineage_storage_",
            "_rir_lineage_compact_state_",
            "_rir_lineage_impact_report_",
            "_rir_lineage_impact_renderer_",
            "_rir_lineage_report_store_",
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
                "COMPACT_STATE": directory / "compact_state.py",
                "IMPACT_REPORT": directory / "impact_report.py",
                "IMPACT_RENDERER": directory / "impact_renderer.py",
                "REPORT_STORE": directory / "report_store.py",
            }
            for attribute, path in expected.items():
                self.assertEqual(
                    Path(getattr(module, attribute).__file__).resolve(), path.resolve()
                )
            self.assertIs(module.STORAGE.report_store, module.REPORT_STORE)
            self.assertIs(module.REPORT_STORE.compact_state, module.COMPACT_STATE)
            self.assertIs(module.REPORT_STORE.impact_renderer, module.IMPACT_RENDERER)
            self.assertIs(module.IMPACT_RENDERER.compact_state, module.COMPACT_STATE)
            self.assertIs(module.IMPACT_RENDERER.impact_report, module.IMPACT_REPORT)

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

                root_names = (
                    "lineage_collision_root_one",
                    "lineage_collision_root_two",
                    "lineage_vacated_root",
                )
                loaded_names.extend(root_names)
                root_first = load_module(root_names[0], SCRIPTS / "rir_lineage.py")
                root_repeat = load_module(root_names[1], SCRIPTS / "rir_lineage.py")
                assert_local(root_first, SCRIPTS)
                assert_local(root_repeat, SCRIPTS)
                self.assertIs(root_first.CONTRACTS, root_repeat.CONTRACTS)
                self.assertIs(root_first.STORAGE, root_repeat.STORAGE)
                self.assertIs(root_first.REPORT_STORE, root_repeat.REPORT_STORE)
                for name, conflict in conflicts.items():
                    self.assertIs(sys.modules[name], conflict)

                for name in exact_names:
                    sys.modules.pop(name, None)
                root_vacated = load_module(root_names[2], SCRIPTS / "rir_lineage.py")
                assert_local(root_vacated, SCRIPTS)
                self.assertIs(root_vacated.STORAGE, root_first.STORAGE)
                self.assertIs(root_vacated.REPORT_STORE, root_first.REPORT_STORE)

                for name, conflict in conflicts.items():
                    sys.modules[name] = conflict
                skill_names = (
                    "lineage_collision_skill_one",
                    "lineage_collision_skill_two",
                    "lineage_vacated_skill",
                )
                loaded_names.extend(skill_names)
                skill_first = load_module(skill_names[0], SKILL_SCRIPTS / "rir_lineage.py")
                skill_repeat = load_module(skill_names[1], SKILL_SCRIPTS / "rir_lineage.py")
                assert_local(skill_first, SKILL_SCRIPTS)
                assert_local(skill_repeat, SKILL_SCRIPTS)
                self.assertIs(skill_first.STORAGE, skill_repeat.STORAGE)
                self.assertIsNot(skill_first.STORAGE, root_first.STORAGE)
                self.assertIsNot(skill_first.REPORT_STORE, root_first.REPORT_STORE)

                for name in exact_names:
                    sys.modules.pop(name, None)
                skill_vacated = load_module(skill_names[2], SKILL_SCRIPTS / "rir_lineage.py")
                assert_local(skill_vacated, SKILL_SCRIPTS)
                self.assertIs(skill_vacated.STORAGE, skill_first.STORAGE)
                self.assertIs(skill_vacated.REPORT_STORE, skill_first.REPORT_STORE)
        finally:
            clear_dependencies()
            sys.modules.update(preserved)
            for name in loaded_names:
                sys.modules.pop(name, None)

    def test_selective_compact_state_alias_replacement_rebuilds_coherent_local_wiring(self):
        self.lineage()
        exact_names = {
            "rir_contracts",
            "rir_storage",
            "compact_state",
            "impact_report",
            "impact_renderer",
            "report_store",
        }
        prefixes = (
            "_rir_lineage_contracts_",
            "_rir_lineage_storage_",
            "_rir_lineage_compact_state_",
            "_rir_lineage_impact_report_",
            "_rir_lineage_impact_renderer_",
            "_rir_lineage_report_store_",
        )
        preserved = {
            name: module
            for name, module in sys.modules.items()
            if name in exact_names or name.startswith(prefixes)
        }
        module_names = ("lineage_selective_first", "lineage_selective_second")
        try:
            for name in tuple(sys.modules):
                if name in exact_names or name.startswith(prefixes):
                    sys.modules.pop(name, None)
            first = load_module(module_names[0], SCRIPTS / "rir_lineage.py")
            first_compact = first.COMPACT_STATE
            first_renderer = first.IMPACT_RENDERER
            first_report_store = first.REPORT_STORE
            first_storage = first.STORAGE

            sys.modules.pop("compact_state")
            replacement = load_module("compact_state", SCRIPTS / "compact_state.py")
            second = load_module(module_names[1], SCRIPTS / "rir_lineage.py")

            self.assertIs(second.COMPACT_STATE, replacement)
            self.assertIsNot(second.COMPACT_STATE, first_compact)
            self.assertIsNot(second.IMPACT_RENDERER, first_renderer)
            self.assertIsNot(second.REPORT_STORE, first_report_store)
            self.assertIsNot(second.STORAGE, first_storage)
            self.assertIs(second.IMPACT_RENDERER.compact_state, second.COMPACT_STATE)
            self.assertIs(second.REPORT_STORE.compact_state, second.COMPACT_STATE)
            self.assertIs(second.REPORT_STORE.impact_renderer, second.IMPACT_RENDERER)
            self.assertIs(second.STORAGE.report_store, second.REPORT_STORE)
        finally:
            for name in tuple(sys.modules):
                if name in exact_names or name.startswith(prefixes):
                    sys.modules.pop(name, None)
            sys.modules.update(preserved)
            for name in module_names:
                sys.modules.pop(name, None)


if __name__ == "__main__":
    unittest.main()
