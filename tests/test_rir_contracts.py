import dataclasses
import importlib.util
import json
import pickle
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
CONTRACT_NAMES = (
    "BeginRequest",
    "DraftResult",
    "ScanRequest",
    "TraceRequest",
    "TraceResult",
    "FinalizeRequest",
    "FinalizeResult",
)


def load_module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


CONTRACTS = load_module("rir_contracts", SCRIPTS / "rir_contracts.py")
CONTROLLER = load_module("rir_controller_contract_test", SCRIPTS / "rir_controller.py")


class RirContractsTest(unittest.TestCase):
    def fixture(self, name):
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def test_facade_reexports_contract_types_and_helpers(self):
        for name in CONTRACT_NAMES:
            with self.subTest(name=name):
                self.assertIs(getattr(CONTROLLER, name), getattr(CONTRACTS, name))
        for facade_name, contract_name in (
            ("canonical_bytes", "canonical_bytes"),
            ("bounded_bytes", "bounded_bytes"),
            ("validate_analysis", "validate_analysis"),
            ("_canonical_bytes", "canonical_bytes"),
            ("_bounded", "bounded_bytes"),
            ("_validate_analysis", "validate_analysis"),
        ):
            with self.subTest(name=facade_name):
                self.assertIs(getattr(CONTROLLER, facade_name), getattr(CONTRACTS, contract_name))

    def test_facades_resolve_their_own_sibling_despite_conflicting_global_alias(self):
        prefix = "_rir_controller_contracts_"
        preserved = {
            name: module
            for name, module in sys.modules.items()
            if name == "rir_contracts" or name.startswith(prefix)
        }
        controller_names = ("collision_root_controller", "collision_skill_controller")
        try:
            for name in preserved:
                sys.modules.pop(name, None)
            with tempfile.TemporaryDirectory() as temporary:
                conflict_path = Path(temporary) / "rir_contracts.py"
                conflict_path.write_text(
                    "\n".join(
                        (
                            "MAX_BEGIN_BYTES = 1",
                            "MAX_FINALIZE_BYTES = 1",
                            "MAX_STRING_BYTES = 1",
                            "MAX_TRACE_BYTES = 1",
                            *(f"class {name}: pass" for name in CONTRACT_NAMES),
                            "def _local_key(value, label): return 'conflict'",
                            "def bounded_bytes(value, maximum, label): return b'conflict'",
                            "def canonical_bytes(value): return b'conflict'",
                            "def validate_analysis(analysis): return None",
                        )
                    )
                    + "\n",
                    encoding="utf-8",
                )
                conflict = load_module("rir_contracts", conflict_path)
                root_facade = load_module(controller_names[0], SCRIPTS / "rir_controller.py")
                skill_scripts = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
                skill_facade = load_module(controller_names[1], skill_scripts / "rir_controller.py")

                self.assertIs(sys.modules["rir_contracts"], conflict)
                for facade, expected_path in (
                    (root_facade, SCRIPTS / "rir_contracts.py"),
                    (skill_facade, skill_scripts / "rir_contracts.py"),
                ):
                    with self.subTest(path=expected_path):
                        self.assertEqual(
                            Path(facade.CONTRACTS.__file__).resolve(), expected_path.resolve()
                        )
                        for name in CONTRACT_NAMES:
                            self.assertIs(getattr(facade, name), getattr(facade.CONTRACTS, name))
                        for facade_name, contract_name in (
                            ("canonical_bytes", "canonical_bytes"),
                            ("bounded_bytes", "bounded_bytes"),
                            ("validate_analysis", "validate_analysis"),
                            ("_canonical_bytes", "canonical_bytes"),
                            ("_bounded", "bounded_bytes"),
                            ("_validate_analysis", "validate_analysis"),
                        ):
                            self.assertIs(
                                getattr(facade, facade_name),
                                getattr(facade.CONTRACTS, contract_name),
                            )
                self.assertIsNot(root_facade.BeginRequest, conflict.BeginRequest)
                self.assertIsNot(skill_facade.BeginRequest, conflict.BeginRequest)
                self.assertIsNot(root_facade.BeginRequest, skill_facade.BeginRequest)
                for facade in (root_facade, skill_facade):
                    request = facade.BeginRequest(Path(temporary), "change", (), "generic")
                    restored = pickle.loads(pickle.dumps(request))
                    self.assertIs(type(restored), facade.BeginRequest)
                    self.assertEqual(restored, request)
        finally:
            for name in tuple(sys.modules):
                if name == "rir_contracts" or name.startswith(prefix):
                    sys.modules.pop(name, None)
            sys.modules.update(preserved)
            for name in controller_names:
                sys.modules.pop(name, None)

    def test_preloaded_correct_sibling_is_reused_without_duplicate_contract_identity(self):
        prefix = "_rir_controller_contracts_"
        preserved = {
            name: module
            for name, module in sys.modules.items()
            if name == "rir_contracts" or name.startswith(prefix)
        }
        controller_names = ("reuse_root_controller_one", "reuse_root_controller_two")
        try:
            for name in preserved:
                sys.modules.pop(name, None)
            preloaded = load_module("rir_contracts", SCRIPTS / "rir_contracts.py")
            first = load_module(controller_names[0], SCRIPTS / "rir_controller.py")
            second = load_module(controller_names[1], SCRIPTS / "rir_controller.py")

            self.assertIs(first.CONTRACTS, preloaded)
            self.assertIs(second.CONTRACTS, preloaded)
            self.assertIs(first.BeginRequest, preloaded.BeginRequest)
            self.assertIs(second.BeginRequest, preloaded.BeginRequest)
            registered = {
                id(module)
                for name, module in sys.modules.items()
                if (name == "rir_contracts" or name.startswith(prefix))
                and Path(getattr(module, "__file__", "/missing")).resolve()
                == (SCRIPTS / "rir_contracts.py").resolve()
            }
            self.assertEqual(registered, {id(preloaded)})
        finally:
            for name in tuple(sys.modules):
                if name == "rir_contracts" or name.startswith(prefix):
                    sys.modules.pop(name, None)
            sys.modules.update(preserved)
            for name in controller_names:
                sys.modules.pop(name, None)

    def test_local_contract_sibling_fails_closed_when_incomplete_or_unsafe(self):
        prefix = "_rir_controller_contracts_"
        preserved = {
            name: module
            for name, module in sys.modules.items()
            if name == "rir_contracts" or name.startswith(prefix)
        }
        try:
            for name in preserved:
                sys.modules.pop(name, None)
            with tempfile.TemporaryDirectory() as temporary:
                temporary_root = Path(temporary)
                controller_path = temporary_root / "rir_controller.py"
                controller_path.write_bytes((SCRIPTS / "rir_controller.py").read_bytes())
                contract_path = temporary_root / "rir_contracts.py"
                contract_path.write_text("BeginRequest = object\n", encoding="utf-8")
                with self.assertRaisesRegex(
                    ImportError, "controller contracts sibling contract is incomplete"
                ):
                    load_module("incomplete_contract_controller", controller_path)

                contract_path.unlink()
                contract_path.symlink_to(SCRIPTS / "rir_contracts.py")
                with self.assertRaisesRegex(ImportError, "controller contracts sibling is unsafe"):
                    load_module("unsafe_contract_controller", controller_path)
        finally:
            for name in tuple(sys.modules):
                if name == "rir_contracts" or name.startswith(prefix):
                    sys.modules.pop(name, None)
            sys.modules.update(preserved)
            sys.modules.pop("incomplete_contract_controller", None)
            sys.modules.pop("unsafe_contract_controller", None)

    def test_contract_dataclasses_keep_field_order_defaults_and_frozen_semantics(self):
        fixture = self.fixture("rir-controller-facade-v05.json")["public_dataclasses"]
        for name in CONTRACT_NAMES:
            with self.subTest(name=name):
                contract = getattr(CONTRACTS, name)
                fields = dataclasses.fields(contract)
                self.assertEqual(
                    [field.name for field in fields], [row[0] for row in fixture[name]["fields"]]
                )
                self.assertEqual(
                    [
                        None if field.default is dataclasses.MISSING else field.default
                        for field in fields
                    ],
                    [None if row[1] == "<missing>" else row[1] for row in fixture[name]["fields"]],
                )
                self.assertTrue(contract.__dataclass_params__.frozen)
                value = object.__new__(contract)
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    value.contract_mutation = True

    def test_canonical_and_bounded_bytes_match_controller_contract(self):
        value = {"z": "한글", "a": [2, 1]}
        expected = b'{"a":[2,1],"z":"\xed\x95\x9c\xea\xb8\x80"}\n'
        self.assertEqual(CONTRACTS.canonical_bytes(value), expected)
        self.assertEqual(CONTRACTS.bounded_bytes(value, 256 * 1024, "begin input"), expected)
        with self.assertRaisesRegex(ValueError, "begin input exceeds 256 KiB"):
            CONTRACTS.bounded_bytes("x" * (256 * 1024), 256 * 1024, "begin input")
        with self.assertRaisesRegex(
            ValueError, "finalize input contains a string larger than 64 KiB"
        ):
            CONTRACTS.bounded_bytes("x" * (64 * 1024 + 1), 2 * 1024 * 1024, "finalize input")

    def test_analysis_validation_accepts_fixture_and_preserves_exact_error(self):
        valid = self.fixture("controller-analysis-post-decision.json")
        CONTRACTS.validate_analysis(valid)
        invalid = dict(valid)
        invalid["decision_needed"] = {
            "question": "Choose",
            "options": [
                {"option": "A", "impact_keys": [], "tradeoff": "A"},
                {"option": "B", "impact_keys": [], "tradeoff": "B"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "post-decision analysis requires decisions only"):
            CONTRACTS.validate_analysis(invalid)


if __name__ == "__main__":
    unittest.main()
