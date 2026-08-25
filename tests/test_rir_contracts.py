import dataclasses
import importlib.util
import json
import sys
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
