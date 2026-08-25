import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CONTROLLER = load_module("_public_type_contracts_controller", SCRIPTS / "rir_controller.py")
FAST_SCAN = load_module("_public_type_contracts_fast_scan", SCRIPTS / "fast_scan.py")


class PublicTypeContractsTest(unittest.TestCase):
    def test_public_request_types_expose_annotations(self) -> None:
        for value in (
            CONTROLLER.BeginRequest,
            CONTROLLER.TraceRequest,
            CONTROLLER.FinalizeRequest,
            FAST_SCAN.FastScanRequest,
        ):
            self.assertTrue(value.__annotations__, value.__name__)
