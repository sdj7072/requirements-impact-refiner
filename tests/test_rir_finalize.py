from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SKILL_SCRIPTS = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
FINALIZE_PATH = SCRIPTS / "rir_finalize.py"


def load_module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


CONTROLLER = load_module("rir_finalize_controller_test", SCRIPTS / "rir_controller.py")
FINALIZE = load_module("rir_finalize_test", FINALIZE_PATH) if FINALIZE_PATH.is_file() else None


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class RirFinalizeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / ".requirements-impact-refiner.json").write_text(
            json.dumps(
                {
                    "impact_graph": {
                        "enabled": False,
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

    def tearDown(self):
        self.temporary.cleanup()

    def finalize(self):
        self.assertIsNotNone(FINALIZE, "rir_finalize.py must be extracted")
        return FINALIZE

    def begin(self, request="Let workspace members edit every project."):
        return CONTROLLER.begin_refinement(
            CONTROLLER.BeginRequest(
                repo_root=self.root,
                request=request,
                repository_evidence=(
                    "authorizeProjectEdit permits owner and admin",
                    "workspace invitations default to member",
                ),
                adapter="generic",
            )
        )

    def request(self, draft):
        return CONTROLLER.FinalizeRequest(
            self.root,
            draft.draft_id,
            fixture("controller-analysis-pre-decision.json"),
        )

    def test_extracted_finalize_matches_sealed_canonical_markdown_digest_and_result_type(self):
        finalize = self.finalize()
        draft = self.begin()

        result = finalize.finalize_refinement(self.request(draft))

        self.assertEqual(
            result.markdown_sha256,
            "0245b2f3a7af219a62e9887121e6459e467fa737a4502b35f3e343107569d39e",
        )
        self.assertIs(type(result), finalize.CONTRACTS.FinalizeResult)
        self.assertTrue(CONTROLLER.load_draft(self.root, draft.draft_id)["consumed"])

    def test_facade_signature_result_type_and_fault_injection_remain_stable(self):
        finalize = self.finalize()
        self.assertEqual(
            tuple(inspect.signature(CONTROLLER.finalize_refinement).parameters), ("request",)
        )
        self.assertIs(CONTROLLER.FinalizeResult, CONTROLLER.CONTRACTS.FinalizeResult)
        self.assertEqual(Path(CONTROLLER.FINALIZE.__file__).resolve(), FINALIZE_PATH.resolve())
        self.assertIs(CONTROLLER._build_state, CONTROLLER.LINEAGE.build_state)

        draft = self.begin("Fault injection remains facade-owned.")
        request = self.request(draft)
        with mock.patch.object(
            CONTROLLER, "_consume", side_effect=ValueError("injected consume failure")
        ):
            with self.assertRaisesRegex(ValueError, "^injected consume failure$"):
                CONTROLLER.finalize_refinement(request)

        result = CONTROLLER.finalize_refinement(request)
        self.assertIs(type(result), CONTROLLER.FinalizeResult)
        self.assertEqual((result.report_id, result.revision), ("RPT-001", 1))
        self.assertIsNotNone(finalize)

    def test_root_and_skill_finalize_resolve_local_dependencies_on_conflict_repeat_and_vacation(
        self,
    ):
        self.finalize()
        exact_names = {
            "rir_contracts",
            "rir_storage",
            "rir_lineage",
            "rir_graph_delivery",
            "compact_state",
            "impact_report",
            "impact_renderer",
            "report_store",
        }
        prefixes = (
            "_rir_finalize_lineage_",
            "_rir_finalize_graph_delivery_",
            "_rir_lineage_",
            "_rir_graph_delivery_",
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
                "LINEAGE": directory / "rir_lineage.py",
                "GRAPH_DELIVERY": directory / "rir_graph_delivery.py",
                "COMPACT_STATE": directory / "compact_state.py",
                "IMPACT_RENDERER": directory / "impact_renderer.py",
                "REPORT_STORE": directory / "report_store.py",
            }
            for attribute, path in expected.items():
                self.assertEqual(
                    Path(getattr(module, attribute).__file__).resolve(), path.resolve()
                )
            self.assertIs(module.CONTRACTS, module.LINEAGE.CONTRACTS)
            self.assertIs(module.STORAGE, module.LINEAGE.STORAGE)
            self.assertIs(module.REPORT_STORE, module.LINEAGE.REPORT_STORE)
            self.assertIs(module.GRAPH_DELIVERY.CONTRACTS, module.CONTRACTS)
            self.assertIs(module.GRAPH_DELIVERY.STORAGE, module.STORAGE)

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
                    "finalize_collision_root_one",
                    "finalize_collision_root_two",
                    "finalize_vacated_root",
                )
                loaded_names.extend(root_names)
                root_first = load_module(root_names[0], SCRIPTS / "rir_finalize.py")
                root_repeat = load_module(root_names[1], SCRIPTS / "rir_finalize.py")
                assert_local(root_first, SCRIPTS)
                assert_local(root_repeat, SCRIPTS)
                self.assertIs(root_first.LINEAGE, root_repeat.LINEAGE)
                self.assertIs(root_first.GRAPH_DELIVERY, root_repeat.GRAPH_DELIVERY)
                for name, conflict in conflicts.items():
                    self.assertIs(sys.modules[name], conflict)

                for name in exact_names:
                    sys.modules.pop(name, None)
                root_vacated = load_module(root_names[2], SCRIPTS / "rir_finalize.py")
                assert_local(root_vacated, SCRIPTS)
                self.assertIs(root_vacated.LINEAGE, root_first.LINEAGE)
                self.assertIs(root_vacated.GRAPH_DELIVERY, root_first.GRAPH_DELIVERY)

                for name, conflict in conflicts.items():
                    sys.modules[name] = conflict
                skill_names = (
                    "finalize_collision_skill_one",
                    "finalize_collision_skill_two",
                    "finalize_vacated_skill",
                )
                loaded_names.extend(skill_names)
                skill_first = load_module(skill_names[0], SKILL_SCRIPTS / "rir_finalize.py")
                skill_repeat = load_module(skill_names[1], SKILL_SCRIPTS / "rir_finalize.py")
                assert_local(skill_first, SKILL_SCRIPTS)
                assert_local(skill_repeat, SKILL_SCRIPTS)
                self.assertIs(skill_first.LINEAGE, skill_repeat.LINEAGE)
                self.assertIs(skill_first.GRAPH_DELIVERY, skill_repeat.GRAPH_DELIVERY)
                self.assertIsNot(skill_first.LINEAGE, root_first.LINEAGE)

                for name in exact_names:
                    sys.modules.pop(name, None)
                skill_vacated = load_module(skill_names[2], SKILL_SCRIPTS / "rir_finalize.py")
                assert_local(skill_vacated, SKILL_SCRIPTS)
                self.assertIs(skill_vacated.LINEAGE, skill_first.LINEAGE)
                self.assertIs(skill_vacated.GRAPH_DELIVERY, skill_first.GRAPH_DELIVERY)
        finally:
            clear_dependencies()
            sys.modules.update(preserved)
            for name in loaded_names:
                sys.modules.pop(name, None)

    def test_root_and_skill_finalize_payloads_are_byte_identical(self):
        self.finalize()
        self.assertEqual(
            FINALIZE_PATH.read_bytes(),
            (SKILL_SCRIPTS / "rir_finalize.py").read_bytes(),
        )
        self.assertEqual(
            (SCRIPTS / "rir_lineage.py").read_bytes(),
            (SKILL_SCRIPTS / "rir_lineage.py").read_bytes(),
        )

    def test_selective_storage_alias_replacement_rebuilds_finalize_graph_wiring(self):
        self.finalize()
        exact_names = {
            "rir_contracts",
            "rir_storage",
            "rir_lineage",
            "rir_graph_delivery",
            "compact_state",
            "impact_report",
            "impact_renderer",
            "report_store",
            "_rir_impact_graph",
            "_rir_graph_builtin",
            "_rir_graph_cache",
            "_rir_graph_providers",
        }
        prefixes = (
            "_rir_finalize_lineage_",
            "_rir_finalize_graph_delivery_",
            "_rir_lineage_",
            "_rir_graph_delivery_",
        )
        preserved = {
            name: module
            for name, module in sys.modules.items()
            if name in exact_names or name.startswith(prefixes)
        }
        module_names = ("finalize_selective_first", "finalize_selective_second")
        try:
            for name in tuple(sys.modules):
                if name in exact_names or name.startswith(prefixes):
                    sys.modules.pop(name, None)
            first = load_module(module_names[0], SCRIPTS / "rir_finalize.py")
            first_storage = first.STORAGE
            first_delivery = first.GRAPH_DELIVERY

            sys.modules.pop("rir_lineage")
            sys.modules.pop("rir_storage")
            replacement_storage = load_module("rir_storage", SCRIPTS / "rir_storage.py")
            second = load_module(module_names[1], SCRIPTS / "rir_finalize.py")

            self.assertIs(second.STORAGE, replacement_storage)
            self.assertIsNot(second.STORAGE, first_storage)
            self.assertIsNot(second.GRAPH_DELIVERY, first_delivery)
            self.assertIs(second.GRAPH_DELIVERY.CONTRACTS, second.CONTRACTS)
            self.assertIs(second.GRAPH_DELIVERY.STORAGE, second.STORAGE)
        finally:
            for name in tuple(sys.modules):
                if name in exact_names or name.startswith(prefixes):
                    sys.modules.pop(name, None)
            sys.modules.update(preserved)
            for name in module_names:
                sys.modules.pop(name, None)


if __name__ == "__main__":
    unittest.main()
