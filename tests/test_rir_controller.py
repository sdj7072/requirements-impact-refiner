import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CONTROLLER = load_module("rir_controller", SCRIPTS / "rir_controller.py")


class SimulatedProcessInterruption(BaseException):
    pass


class RirControllerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".requirements-impact-refiner.json").write_text(
            json.dumps(
                {
                    "delivery": "compact",
                    "impact_graph": {
                        "enabled": False,
                        "max_seconds": 30,
                        "target_seconds": 10,
                        "providers": ["builtin"],
                        "install_policy": "never",
                        "deep": False,
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def request(self, **changes):
        values = {
            "repo_root": self.root,
            "request": "Let workspace members edit every project.",
            "repository_evidence": (
                "authorizeProjectEdit permits owner and admin",
                "workspace invitations default to member",
            ),
            "adapter": "generic",
        }
        values.update(changes)
        return CONTROLLER.BeginRequest(**values)

    def finalize(self, draft, analysis, receipt=None):
        return CONTROLLER.FinalizeRequest(
            repo_root=self.root,
            draft_id=draft.draft_id,
            analysis=analysis,
            graph_receipt_id=(None if receipt is None else receipt.receipt_id),
        )

    def fixture(self, name):
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def enable_builtin_graph(self):
        (self.root / ".requirements-impact-refiner.json").write_text(
            json.dumps(
                {
                    "delivery": "compact",
                    "impact_graph": {
                        "enabled": True,
                        "max_seconds": 30,
                        "target_seconds": 10,
                        "providers": ["builtin"],
                        "install_policy": "never",
                        "deep": False,
                    },
                }
            ),
            encoding="utf-8",
        )
        (self.root / "api").mkdir(exist_ok=True)
        (self.root / "desktop").mkdir(exist_ok=True)
        (self.root / "api/profile.py").write_text(
            'FIELD = "profile.displayName"\n', encoding="utf-8"
        )
        (self.root / "desktop/profile_cache.ts").write_text(
            'const key = "profile.displayName";\n', encoding="utf-8"
        )

    def graph_context_with_high_risk_license(self, paths):
        receipt = self.fixture("impact-graph-receipt.json")
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
                "id": "NODE-018",
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
                    "target": "NODE-018",
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
        receipt["budget_status"] = "provider_limited"
        payload = CONTROLLER.GRAPH.canonical_receipt_bytes(receipt)
        validated, errors = CONTROLLER.GRAPH.load_receipt_bytes(payload)
        self.assertEqual(errors, ())
        self.assertIsNotNone(validated)
        return {"receipt": validated, "sha256": "e" * 64}

    def test_trace_persists_private_receipt_bound_to_draft(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request())

        traced = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                draft.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )

        self.assertRegex(traced.receipt_id, r"^[0-9a-f]{32}$")
        self.assertEqual(traced.receipt_path.stat().st_mode & 0o777, 0o600)
        self.assertRegex(traced.receipt_sha256, r"^[0-9a-f]{64}$")
        self.assertEqual(traced.budget_status, "closed")
        self.assertTrue(traced.compact_graph["paths"])
        stored = CONTROLLER.load_draft(self.root, draft.draft_id)
        self.assertEqual(stored["graph_receipt"]["receipt_id"], traced.receipt_id)
        self.assertEqual(stored["graph_receipt"]["sha256"], traced.receipt_sha256)
        self.assertEqual(traced.request_sha256, stored["graph_receipt"]["request_sha256"])
        self.assertEqual(
            traced.seeds,
            (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
        )

    def test_fast_scan_promotes_and_finalizes_without_graph_rerun(self):
        self.enable_builtin_graph()
        scan = CONTROLLER.scan_impact(
            CONTROLLER.ScanRequest(self.root, "Rename profile.displayName", (), "balanced")
        )
        with mock.patch.object(
            CONTROLLER.GRAPH_COORDINATOR,
            "trace_impact",
            side_effect=AssertionError("promotion must not rerun graph"),
        ):
            draft = CONTROLLER.begin_refinement(
                CONTROLLER.BeginRequest(
                    self.root,
                    "Rename profile.displayName",
                    (),
                    "generic",
                    scan_id=scan.scan_id,
                )
            )
            analysis = self.fixture("controller-analysis-pre-decision.json")
            analysis["impacts"][0]["graph_path_keys"] = [row["id"] for row in scan.paths]
            if not analysis["impacts"][0]["graph_path_keys"]:
                analysis["impacts"][0]["coverage_rationale"] = (
                    "Fast Scan found no closed repository path."
                )
            analysis["impacts"][0]["evidence_level"] = "unknown"
            result = CONTROLLER.finalize_refinement(
                CONTROLLER.FinalizeRequest(self.root, draft.draft_id, analysis, scan.receipt_id)
            )

        self.assertEqual(result.status, "published")
        stored = CONTROLLER.load_draft(self.root, draft.draft_id)
        self.assertEqual(stored["promoted_scan"]["scan_id"], scan.scan_id)
        self.assertEqual(draft.scan_id, scan.scan_id)
        self.assertEqual(draft.graph_receipt_id, scan.receipt_id)

    def test_fast_scan_promotion_rejects_wrong_request_and_source_mutation(self):
        self.enable_builtin_graph()
        scan = CONTROLLER.scan_impact(
            CONTROLLER.ScanRequest(self.root, "Rename profile.displayName", (), "balanced")
        )
        with self.assertRaisesRegex(ValueError, "request|identity"):
            CONTROLLER.begin_refinement(
                CONTROLLER.BeginRequest(
                    self.root,
                    "Different request",
                    (),
                    "generic",
                    scan_id=scan.scan_id,
                )
            )
        (self.root / "api/profile.py").write_text('FIELD = "profile.changed"\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale|source|identity"):
            CONTROLLER.begin_refinement(
                CONTROLLER.BeginRequest(
                    self.root,
                    "Rename profile.displayName",
                    (),
                    "generic",
                    scan_id=scan.scan_id,
                )
            )

    def test_pristine_root_and_skill_scan_and_promote_ignore_foreign_fast_scan_graph(self):
        script = r"""
import importlib.util
import json
import re
import sys
import tempfile
import types
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
directories = (repo / "scripts", repo / "skills/requirements-impact-refiner/scripts")

def load(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module

calls = []
foreign = {}
for name in (
    "fast_scan",
    "fast_scan_renderer",
    "fast_scan_store",
    "graph_builtin",
    "graph_coordinator",
    "payload_identity",
    "rir_delta",
):
    module = types.ModuleType(name)
    module.__file__ = f"/tmp/foreign-{name}.py"
    foreign[name] = module

foreign["fast_scan_renderer"].WORD_LIMIT = 180
foreign["fast_scan_renderer"].AUDIENCES = {"simple", "balanced", "technical"}
foreign["fast_scan_renderer"].LOCALES = {"en", "ko", "ja"}
foreign["fast_scan_renderer"].render_fast_scan = lambda *a, **k: calls.append("renderer")
foreign["fast_scan_store"]._ID = re.compile(r"[0-9a-f]{32}")
foreign["fast_scan_store"]._MAX = 1
foreign["fast_scan_store"]._MAX_JSON_DEPTH = 1
foreign["fast_scan_store"].publish_scan_receipt = lambda *a, **k: calls.append("publish")
foreign["fast_scan_store"].load_scan_receipt_bytes = lambda *a, **k: calls.append("load")
for name in ("DerivedSeed", "FastScanRequest", "FastScanReceipt", "FastScanResult", "PreparedFastScan"):
    setattr(foreign["fast_scan"], name, type(f"Foreign{name}", (), {}))
for name in (
    "derive_seeds",
    "execute_fast_scan",
    "prepare_fast_scan_identity",
    "validate_fast_scan_receipt",
    "canonical_fast_scan_bytes",
):
    setattr(foreign["fast_scan"], name, lambda *a, _name=name, **k: calls.append(_name))
foreign["payload_identity"].ROOT_FILES = ("scripts/rir_controller.py",)
foreign["payload_identity"].functional_paths = lambda *a, **k: calls.append("paths")
foreign["payload_identity"].payload_sha256 = lambda *a, **k: calls.append("payload")
foreign["graph_builtin"].GRAPH = object()
foreign["graph_coordinator"].GRAPH = object()
foreign["graph_coordinator"].BUILTIN = foreign["graph_builtin"]
foreign["graph_coordinator"].CACHE = object()
foreign["graph_coordinator"].PROVIDERS = object()
sys.modules.update(foreign)

controllers = []
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary).resolve()
    (root / ".requirements-impact-refiner.json").write_text(
        json.dumps(
            {
                "impact_graph": {
                    "enabled": True,
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
    (root / "api").mkdir()
    (root / "api/profile.py").write_text(
        'FIELD = "profile.displayName"\n', encoding="utf-8"
    )
    for index, directory in enumerate(directories, start=1):
        controller = load(f"pristine_fast_scan_controller_{index}", directory / "rir_controller.py")
        controllers.append(controller)
        assert Path(controller.FAST_SCAN.__file__).resolve() == (directory / "fast_scan.py").resolve()
        assert Path(controller.FAST_SCAN_STORE.__file__).resolve() == (directory / "fast_scan_store.py").resolve()
        assert Path(controller.FAST_SCAN_RENDERER.__file__).resolve() == (directory / "fast_scan_renderer.py").resolve()
        assert Path(controller.PAYLOAD_IDENTITY.__file__).resolve() == (directory / "payload_identity.py").resolve()
        assert Path(controller.DELTA.__file__).resolve() == (directory / "rir_delta.py").resolve()
        assert controller.FAST_SCAN.fast_scan_renderer is controller.FAST_SCAN_RENDERER
        assert controller.FAST_SCAN.fast_scan_store is controller.FAST_SCAN_STORE
        assert controller.FAST_SCAN.graph_builtin is controller.GRAPH_COORDINATOR.BUILTIN
        assert controller.FAST_SCAN.graph_coordinator is controller.GRAPH_COORDINATOR
        assert controller.ScanResult is controller.FAST_SCAN.FastScanResult
        assert controller._payload_sha256() == controller.PAYLOAD_IDENTITY.payload_sha256(repo)
        scan = controller.scan_impact(
            controller.ScanRequest(root, "Rename profile.displayName", (), "balanced")
        )
        assert type(scan) is controller.ScanResult
        draft = controller.begin_refinement(
            controller.BeginRequest(
                root,
                "Rename profile.displayName",
                (),
                "generic",
                scan_id=scan.scan_id,
            )
        )
        stored = controller.load_draft(root, draft.draft_id)
        assert stored["promoted_scan"]["scan_id"] == scan.scan_id
        for name, sentinel in foreign.items():
            assert sys.modules[name] is sentinel, name

assert controllers[0].FAST_SCAN is not controllers[1].FAST_SCAN
assert controllers[0].FAST_SCAN_STORE is not controllers[1].FAST_SCAN_STORE
assert controllers[0].GRAPH_COORDINATOR is not controllers[1].GRAPH_COORDINATOR
assert controllers[0].DELTA is not controllers[1].DELTA
assert calls == [], calls
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(ROOT)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_controller_fast_scan_conflict_vacation_and_repeat_reuse_local_graph(self):
        exact_names = {
            "fast_scan",
            "fast_scan_renderer",
            "fast_scan_store",
            "graph_builtin",
            "graph_coordinator",
            "payload_identity",
        }
        prefixes = (
            "_rir_controller_fast_scan_",
            "_rir_controller_payload_identity_",
        )
        controller_names = (
            "rir_controller_fast_scan_conflict",
            "rir_controller_fast_scan_vacated",
        )
        preserved = {
            name: module
            for name, module in sys.modules.items()
            if name in exact_names or name.startswith(prefixes)
        }
        foreign = {}
        try:
            for name in tuple(sys.modules):
                if name in exact_names or name.startswith(prefixes):
                    sys.modules.pop(name, None)
            for name in exact_names:
                sentinel = type(sys)(name)
                sentinel.__file__ = str(self.root / f"foreign-{name}.py")
                foreign[name] = sentinel
                sys.modules[name] = sentinel

            first = load_module(controller_names[0], SCRIPTS / "rir_controller.py")

            self.assertEqual(
                Path(first.FAST_SCAN.__file__).resolve(),
                (SCRIPTS / "fast_scan.py").resolve(),
            )
            self.assertEqual(
                Path(first.FAST_SCAN_STORE.__file__).resolve(),
                (SCRIPTS / "fast_scan_store.py").resolve(),
            )
            self.assertEqual(
                Path(first.FAST_SCAN_RENDERER.__file__).resolve(),
                (SCRIPTS / "fast_scan_renderer.py").resolve(),
            )
            self.assertEqual(
                Path(first.PAYLOAD_IDENTITY.__file__).resolve(),
                (SCRIPTS / "payload_identity.py").resolve(),
            )
            self.assertIs(first.FAST_SCAN.graph_coordinator, first.GRAPH_COORDINATOR)
            self.assertIs(first.FAST_SCAN.graph_builtin, first.GRAPH_COORDINATOR.BUILTIN)
            for name, sentinel in foreign.items():
                self.assertIs(sys.modules[name], sentinel)

            for name in exact_names:
                sys.modules.pop(name)
            repeated = load_module(controller_names[1], SCRIPTS / "rir_controller.py")
            self.assertIs(repeated.FAST_SCAN, first.FAST_SCAN)
            self.assertIs(repeated.FAST_SCAN_STORE, first.FAST_SCAN_STORE)
            self.assertIs(repeated.FAST_SCAN_RENDERER, first.FAST_SCAN_RENDERER)
            self.assertIs(repeated.PAYLOAD_IDENTITY, first.PAYLOAD_IDENTITY)
            self.assertIs(sys.modules["fast_scan"], first.FAST_SCAN)
            self.assertIs(sys.modules["fast_scan_store"], first.FAST_SCAN_STORE)
            self.assertIs(sys.modules["fast_scan_renderer"], first.FAST_SCAN_RENDERER)
            self.assertIs(sys.modules["payload_identity"], first.PAYLOAD_IDENTITY)
        finally:
            for name in tuple(sys.modules):
                if name in exact_names or name.startswith(prefixes) or name in controller_names:
                    sys.modules.pop(name, None)
            sys.modules.update(preserved)

    def test_controller_sibling_loader_rewires_repeats_and_fails_closed(self):
        module_names = {
            "controller_loader_dependency",
            "controller_loader_rewire_fixture",
            "controller_loader_direct_fixture",
            "controller_loader_broken_fixture",
            "controller_loader_invalid_fixture",
            "controller_loader_hashed_fixture",
            "controller_loader_unsafe_hash_fixture",
            "controller_loader_same_path_invalid",
            "controller_loader_valid_foreign_hash",
            "controller_loader_invalid_foreign_hash",
        }
        prefixes = (
            "_controller_loader_rewire_",
            "_controller_loader_direct_",
            "_controller_loader_broken_",
            "_controller_loader_invalid_",
            "_controller_loader_hashed_",
            "_controller_loader_unsafe_hash_",
            "_controller_loader_same_path_invalid_",
            "_controller_loader_valid_foreign_hash_",
            "_controller_loader_invalid_foreign_hash_",
        )
        preserved = {
            name: module
            for name, module in sys.modules.items()
            if name in module_names or name.startswith(prefixes)
        }

        def dependency(name, marker):
            module = type(sys)(name)
            module.__file__ = str(self.root / f"{name}.py")
            module.marker = marker
            return module

        try:
            for name in tuple(sys.modules):
                if name in module_names or name.startswith(prefixes):
                    sys.modules.pop(name, None)
            fixture_root = self.root.resolve()
            target = fixture_root / "target.py"
            target.write_text(
                "import controller_loader_dependency as dependency\nmarker = dependency.marker\n",
                encoding="utf-8",
            )
            broken = fixture_root / "broken.py"
            broken.write_text("raise RuntimeError('broken fixture')\n", encoding="utf-8")
            invalid = fixture_root / "invalid.py"
            invalid.write_text("marker = 'wrong'\n", encoding="utf-8")
            linked = fixture_root / "linked.py"
            linked.symlink_to(target)
            expected = target.resolve()

            foreign_dependency = dependency("controller_loader_dependency", "foreign")
            sys.modules["controller_loader_dependency"] = foreign_dependency
            foreign_target = dependency("controller_loader_rewire_fixture", "foreign")
            sys.modules["controller_loader_rewire_fixture"] = foreign_target
            first_dependency = dependency("first_dependency", "first")
            second_dependency = dependency("second_dependency", "second")

            with mock.patch.object(CONTROLLER, "SCRIPT_DIR", fixture_root):
                first = CONTROLLER._load_controller_sibling(
                    "target.py",
                    "controller_loader_rewire_fixture",
                    "_controller_loader_rewire_",
                    lambda value: getattr(value, "marker", None) == "first",
                    "loader fixture",
                    aliases={"controller_loader_dependency": first_dependency},
                    rewire_validator=lambda value: hasattr(value, "marker"),
                )
                self.assertEqual(first.marker, "first")
                self.assertIs(sys.modules["controller_loader_rewire_fixture"], foreign_target)
                self.assertIs(sys.modules["controller_loader_dependency"], foreign_dependency)

                rewired = CONTROLLER._load_controller_sibling(
                    "target.py",
                    "controller_loader_rewire_fixture",
                    "_controller_loader_rewire_",
                    lambda value: getattr(value, "marker", None) == "second",
                    "loader fixture",
                    aliases={"controller_loader_dependency": second_dependency},
                    rewire_validator=lambda value: hasattr(value, "marker"),
                )
                repeated = CONTROLLER._load_controller_sibling(
                    "target.py",
                    "controller_loader_rewire_fixture",
                    "_controller_loader_rewire_",
                    lambda value: getattr(value, "marker", None) == "second",
                    "loader fixture",
                    aliases={"controller_loader_dependency": second_dependency},
                    rewire_validator=lambda value: hasattr(value, "marker"),
                )
                self.assertEqual(rewired.marker, "second")
                self.assertIs(repeated, rewired)
                self.assertIs(sys.modules["controller_loader_dependency"], foreign_dependency)

                direct = CONTROLLER._execute_controller_sibling(
                    "controller_loader_direct_fixture",
                    target,
                    lambda value: getattr(value, "marker", None) == "first",
                    "loader fixture",
                    aliases={"controller_loader_dependency": first_dependency},
                )
                self.assertEqual(direct.marker, "first")
                reloaded = CONTROLLER._load_controller_sibling(
                    "target.py",
                    "controller_loader_direct_fixture",
                    "_controller_loader_direct_",
                    lambda value: getattr(value, "marker", None) == "second",
                    "loader fixture",
                    aliases={"controller_loader_dependency": second_dependency},
                    rewire_validator=lambda value: hasattr(value, "marker"),
                )
                self.assertEqual(reloaded.marker, "second")
                self.assertIs(
                    CONTROLLER._load_controller_sibling(
                        "target.py",
                        "controller_loader_direct_fixture",
                        "_controller_loader_direct_",
                        lambda value: getattr(value, "marker", None) == "second",
                        "loader fixture",
                        aliases={"controller_loader_dependency": second_dependency},
                        rewire_validator=lambda value: hasattr(value, "marker"),
                    ),
                    reloaded,
                )

                CONTROLLER._execute_controller_sibling(
                    "controller_loader_same_path_invalid",
                    target,
                    lambda value: getattr(value, "marker", None) == "first",
                    "loader fixture",
                    aliases={"controller_loader_dependency": first_dependency},
                )
                with self.assertRaisesRegex(
                    ImportError, "controller loader fixture sibling contract is incomplete"
                ):
                    CONTROLLER._load_controller_sibling(
                        "target.py",
                        "controller_loader_same_path_invalid",
                        "_controller_loader_same_path_invalid_",
                        lambda value: getattr(value, "marker", None) == "second",
                        "loader fixture",
                    )

                with self.assertRaisesRegex(
                    ImportError, "cannot load fixed controller loader fixture sibling"
                ):
                    CONTROLLER._load_controller_sibling(
                        "broken.py",
                        "controller_loader_broken_fixture",
                        "_controller_loader_broken_",
                        lambda value: True,
                        "loader fixture",
                    )
                with self.assertRaisesRegex(
                    ImportError, "controller loader fixture sibling contract is incomplete"
                ):
                    CONTROLLER._load_controller_sibling(
                        "invalid.py",
                        "controller_loader_invalid_fixture",
                        "_controller_loader_invalid_",
                        lambda value: getattr(value, "marker", None) == "valid",
                        "loader fixture",
                    )

                valid_foreign_hash = (
                    "_controller_loader_valid_foreign_hash_"
                    + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
                )
                sys.modules[valid_foreign_hash] = first
                sys.modules["controller_loader_valid_foreign_hash"] = dependency(
                    "controller_loader_valid_foreign_hash", "foreign"
                )
                self.assertIs(
                    CONTROLLER._load_controller_sibling(
                        "target.py",
                        "controller_loader_valid_foreign_hash",
                        "_controller_loader_valid_foreign_hash_",
                        lambda value: getattr(value, "marker", None) == "first",
                        "loader fixture",
                    ),
                    first,
                )

                invalid_foreign_hash = (
                    "_controller_loader_invalid_foreign_hash_"
                    + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
                )
                invalid_foreign = dependency(invalid_foreign_hash, "wrong")
                invalid_foreign.__file__ = str(expected)
                sys.modules[invalid_foreign_hash] = invalid_foreign
                sys.modules["controller_loader_invalid_foreign_hash"] = dependency(
                    "controller_loader_invalid_foreign_hash", "foreign"
                )
                with self.assertRaisesRegex(
                    ImportError, "controller loader fixture sibling contract is incomplete"
                ):
                    CONTROLLER._load_controller_sibling(
                        "target.py",
                        "controller_loader_invalid_foreign_hash",
                        "_controller_loader_invalid_foreign_hash_",
                        lambda value: getattr(value, "marker", None) == "valid",
                        "loader fixture",
                    )
                with self.assertRaisesRegex(
                    ImportError, "controller loader fixture sibling is unsafe"
                ):
                    CONTROLLER._load_controller_sibling(
                        "linked.py",
                        "controller_loader_invalid_fixture",
                        "_controller_loader_invalid_",
                        lambda value: True,
                        "loader fixture",
                    )

                valid_hash = (
                    "_controller_loader_hashed_"
                    + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
                )
                invalid_hash = dependency(valid_hash, "wrong")
                invalid_hash.__file__ = str(expected)
                sys.modules[valid_hash] = invalid_hash
                with self.assertRaisesRegex(
                    ImportError, "controller loader fixture sibling contract is incomplete"
                ):
                    CONTROLLER._load_controller_sibling(
                        "target.py",
                        "controller_loader_hashed_fixture",
                        "_controller_loader_hashed_",
                        lambda value: getattr(value, "marker", None) == "valid",
                        "loader fixture",
                    )

                unsafe_hash_name = (
                    "_controller_loader_unsafe_hash_"
                    + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
                )
                sys.modules[unsafe_hash_name] = dependency(unsafe_hash_name, "valid")
                sys.modules["controller_loader_unsafe_hash_fixture"] = dependency(
                    "controller_loader_unsafe_hash_fixture", "foreign"
                )
                with self.assertRaisesRegex(
                    ImportError, "controller loader fixture sibling is unsafe"
                ):
                    CONTROLLER._load_controller_sibling(
                        "target.py",
                        "controller_loader_unsafe_hash_fixture",
                        "_controller_loader_unsafe_hash_",
                        lambda value: getattr(value, "marker", None) == "valid",
                        "loader fixture",
                    )
        finally:
            for name in tuple(sys.modules):
                if name in module_names or name.startswith(prefixes):
                    sys.modules.pop(name, None)
            sys.modules.update(preserved)

    def test_controller_fast_scan_graph_rejects_unsafe_local_and_expected_hash_modules(self):
        script = r"""
import hashlib
import importlib.util
import shutil
import sys
import tempfile
import types
from pathlib import Path

source = Path(sys.argv[1]).resolve()

def load(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module

def clear():
    for name in tuple(sys.modules):
        if name in {
            "fast_scan", "fast_scan_renderer", "fast_scan_store", "graph_builtin",
            "graph_coordinator", "payload_identity", "rir_controller", "rir_contracts",
            "rir_storage", "rir_graph_delivery", "rir_lineage", "rir_finalize",
        } or name.startswith("_rir_") or name.startswith("unsafe_fast_scan_"):
            sys.modules.pop(name, None)

with tempfile.TemporaryDirectory() as temporary:
    copied = Path(temporary) / "scripts"
    shutil.copytree(source, copied)
    (copied / "fast_scan.py").unlink()
    (copied / "fast_scan.py").symlink_to(source / "fast_scan.py")
    try:
        load("unsafe_fast_scan_symlink", copied / "rir_controller.py")
    except ImportError as error:
        assert str(error) == "controller Fast Scan sibling is unsafe", error
    else:
        raise AssertionError("symlinked local Fast Scan was accepted")

clear()
with tempfile.TemporaryDirectory() as temporary:
    copied = Path(temporary) / "scripts"
    shutil.copytree(source, copied)
    (copied / "fast_scan.py").write_text("class FastScanResult: pass\n", encoding="utf-8")
    try:
        load("unsafe_fast_scan_incomplete", copied / "rir_controller.py")
    except ImportError as error:
        assert str(error) == "controller Fast Scan sibling contract is incomplete", error
    else:
        raise AssertionError("incomplete local Fast Scan was accepted")

clear()
foreign = types.ModuleType("fast_scan_store")
foreign.__file__ = "/tmp/foreign-fast-scan-store.py"
sys.modules["fast_scan_store"] = foreign
expected = (source / "fast_scan_store.py").resolve()
hashed_name = "_rir_controller_fast_scan_store_" + hashlib.sha256(
    str(expected).encode("utf-8")
).hexdigest()[:16]
invalid = types.ModuleType(hashed_name)
invalid.__file__ = str(expected)
sys.modules[hashed_name] = invalid
try:
    load("unsafe_fast_scan_hash", source / "rir_controller.py")
except ImportError as error:
    assert str(error) == "controller Fast Scan store sibling contract is incomplete", error
else:
    raise AssertionError("invalid expected Fast Scan store hash was accepted")
assert sys.modules["fast_scan_store"] is foreign
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(SCRIPTS)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_legacy_begin_has_no_promoted_scan_identity(self):
        draft = CONTROLLER.begin_refinement(self.request())
        self.assertIsNone(draft.scan_id)
        self.assertIsNone(draft.graph_receipt_id)
        self.assertNotIn("promoted_scan", CONTROLLER.load_draft(self.root, draft.draft_id))

    def test_trace_uses_coordinator_normalized_seed_identity(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request())

        traced = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                draft.draft_id,
                (
                    CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),
                    CONTROLLER.TraceSeed("authorization.profile", "api/profile.py"),
                ),
            )
        )

        stored = CONTROLLER.load_draft(self.root, draft.draft_id)
        self.assertEqual(
            [row["term"] for row in stored["graph_receipt"]["seeds"]],
            ["authorization.profile", "profile.displayName"],
        )
        self.assertEqual(
            tuple(seed.term for seed in traced.seeds),
            ("authorization.profile", "profile.displayName"),
        )
        self.assertEqual(traced.request_sha256, stored["graph_receipt"]["request_sha256"])
        self.assertRegex(traced.receipt_id, r"^[0-9a-f]{32}$")

    def test_trace_rejects_wrong_root_unknown_and_consumed_drafts(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request())
        other = self.root / "other"
        other.mkdir()
        with self.assertRaisesRegex(ValueError, "draft"):
            CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    other,
                    draft.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
                )
            )
        with self.assertRaisesRegex(ValueError, "draft"):
            CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    "0" * 32,
                    (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
                )
            )
        stored = CONTROLLER.load_draft(self.root, draft.draft_id)
        stored["consumed"] = True
        CONTROLLER._replace_private_draft(self.root, draft.draft_id, stored)
        with self.assertRaisesRegex(ValueError, "consumed"):
            CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    draft.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
                )
            )

    def test_trace_rejects_duplicate_or_preexisting_receipt(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request())
        request = CONTROLLER.TraceRequest(
            self.root,
            draft.draft_id,
            (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
        )
        first = CONTROLLER.trace_impact(request)
        first_bytes = first.receipt_path.read_bytes()

        repeated = CONTROLLER.trace_impact(request)

        self.assertEqual(repeated.receipt_id, first.receipt_id)
        self.assertEqual(repeated.receipt_sha256, first.receipt_sha256)
        self.assertEqual(repeated.receipt_path.read_bytes(), first_bytes)
        with self.assertRaisesRegex(ValueError, "different trace request"):
            CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    draft.draft_id,
                    (CONTROLLER.TraceSeed("different.seed", None),),
                )
            )

        second = CONTROLLER.begin_refinement(self.request(request="Another request"))
        graph_dir = self.root / ".requirements-impact-refiner" / "graph"
        graph_dir.mkdir(parents=True, exist_ok=True)
        (graph_dir / f"{second.draft_id}.json").write_text("replacement", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "graph receipt"):
            CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    second.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
                )
            )
        self.assertEqual(
            (graph_dir / f"{second.draft_id}.json").read_text(encoding="utf-8"),
            "replacement",
        )

    def test_trace_rejects_disabled_graph_unsafe_root_and_unsafe_seed(self):
        (self.root / ".requirements-impact-refiner.json").write_text(
            json.dumps(
                {
                    "delivery": "compact",
                    "impact_graph": {
                        "enabled": False,
                        "max_seconds": 30,
                        "target_seconds": 10,
                        "providers": ["builtin"],
                        "install_policy": "never",
                        "deep": False,
                    },
                }
            ),
            encoding="utf-8",
        )
        draft = CONTROLLER.begin_refinement(self.request())
        with self.assertRaisesRegex(ValueError, "disabled"):
            CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    draft.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", None),),
                )
            )

        linked = self.root.parent / (self.root.name + "-link")
        os.symlink(self.root, linked)
        self.addCleanup(linked.unlink)
        with self.assertRaisesRegex(ValueError, "symlink is unsafe"):
            CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    linked,
                    draft.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", None),),
                )
            )

        self.enable_builtin_graph()
        safe_draft = CONTROLLER.begin_refinement(self.request(request="Safe draft"))
        with self.assertRaisesRegex(ValueError, "safe repository-relative path"):
            CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    safe_draft.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", "../outside.py"),),
                )
            )

    def test_trace_rejects_malformed_persisted_graph_settings(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request(request="Malformed graph settings"))
        stored = CONTROLLER.load_draft(self.root, draft.draft_id)
        stored["settings"]["impact_graph"]["max_seconds"] = "30"
        draft.draft_path.write_bytes(CONTROLLER._canonical_bytes(stored))

        with self.assertRaisesRegex(
            ValueError,
            "invalid graph settings: settings max_seconds must be a positive integer",
        ):
            CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    draft.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
                )
            )

    def test_receipt_payload_guard_rejects_valid_dataclass_receipt(self):
        settings = CONTROLLER.GRAPH.GraphSettings()
        receipt = CONTROLLER.GRAPH.GraphReceipt(
            "0" * 32,
            "1" * 32,
            "2" * 64,
            "3" * 64,
            settings,
            (
                CONTROLLER.GRAPH.ProviderStatus(
                    "builtin", "ready", "verified-source", "builtin-v1", None
                ),
            ),
            (),
            (),
            (),
            (),
            {"total": 0},
            "closed",
            {"status": "miss", "key": "0" * 64, "invalidated_nodes": []},
        )
        self.assertEqual(CONTROLLER.GRAPH.validate_receipt(receipt), ())
        self.assertFalse(CONTROLLER._is_receipt_payload(receipt))

    def test_finalize_rejects_nonmapping_draft_settings_with_stable_error(self):
        for index, malformed in enumerate((None, "not-settings")):
            with self.subTest(malformed=malformed):
                draft = CONTROLLER.begin_refinement(
                    self.request(request=f"Malformed settings {index}")
                )
                stored = CONTROLLER.load_draft(self.root, draft.draft_id)
                stored["settings"] = malformed
                draft.draft_path.write_bytes(CONTROLLER._canonical_bytes(stored))

                with self.assertRaisesRegex(ValueError, "^draft graph settings are invalid$"):
                    CONTROLLER.finalize_refinement(
                        CONTROLLER.FinalizeRequest(
                            self.root,
                            draft.draft_id,
                            self.fixture("controller-analysis-pre-decision.json"),
                        )
                    )

    def test_incomplete_graph_coordinator_sibling_fails_closed(self):
        script = r"""
import hashlib
import importlib.util
import sys
import types
from pathlib import Path

path = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(path.parent))
module_name = (
    "_rir_controller_graph_coordinator_"
    + hashlib.sha256(str(path.with_name("graph_coordinator.py")).encode("utf-8")).hexdigest()[:16]
)
sys.modules[module_name] = types.ModuleType(module_name)
spec = importlib.util.spec_from_file_location("_controller_guard", path)
module = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(module)
except ImportError as error:
    if str(error) != "graph coordinator sibling contract is incomplete":
        raise AssertionError(str(error))
else:
    raise AssertionError("incomplete graph coordinator sibling was accepted")
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(SCRIPTS / "rir_controller.py")],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_trace_rejects_oversized_or_excessive_seeds_before_scanning(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request())
        with mock.patch.object(
            CONTROLLER.GRAPH_COORDINATOR,
            "trace_impact",
            side_effect=AssertionError("scanner must not run"),
        ):
            with self.assertRaisesRegex(ValueError, "256 KiB"):
                CONTROLLER.trace_impact(
                    CONTROLLER.TraceRequest(
                        self.root,
                        draft.draft_id,
                        tuple(
                            CONTROLLER.TraceSeed(f"{index:03d}-" + "x" * (4096 - 4), None)
                            for index in range(128)
                        ),
                    )
                )
            with self.assertRaisesRegex(ValueError, "between 1 and 128"):
                CONTROLLER.trace_impact(
                    CONTROLLER.TraceRequest(
                        self.root,
                        draft.draft_id,
                        tuple(CONTROLLER.TraceSeed(f"seed-{index}", None) for index in range(129)),
                    )
                )

    def test_trace_publication_failure_does_not_bind_draft_and_retry_succeeds(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request())
        request = CONTROLLER.TraceRequest(
            self.root,
            draft.draft_id,
            (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
        )
        with mock.patch.object(
            CONTROLLER.GRAPH_COORDINATOR,
            "_persist_receipt",
            side_effect=ValueError("injected receipt publication failure"),
        ):
            with self.assertRaisesRegex(ValueError, "publication failure"):
                CONTROLLER.trace_impact(request)

        self.assertIsNone(CONTROLLER.load_draft(self.root, draft.draft_id).get("graph_receipt"))
        self.assertIsInstance(
            CONTROLLER.load_draft(self.root, draft.draft_id).get("graph_trace_intent"),
            dict,
        )
        traced = CONTROLLER.trace_impact(request)
        self.assertTrue(traced.receipt_path.is_file())
        self.assertNotIn("graph_trace_intent", CONTROLLER.load_draft(self.root, draft.draft_id))

    def test_trace_retry_recovers_exact_receipt_after_draft_binding_failure(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request(request="Recover binding"))
        request = CONTROLLER.TraceRequest(
            self.root,
            draft.draft_id,
            (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
        )
        with mock.patch.object(
            CONTROLLER,
            "_bind_trace_receipt",
            side_effect=ValueError("injected binding failure"),
        ):
            with self.assertRaisesRegex(ValueError, "injected binding failure"):
                CONTROLLER.trace_impact(request)

        receipt_path = self.root / ".requirements-impact-refiner/graph" / f"{draft.draft_id}.json"
        published_bytes = receipt_path.read_bytes()
        self.assertIsNone(CONTROLLER.load_draft(self.root, draft.draft_id).get("graph_receipt"))
        self.assertIsInstance(
            CONTROLLER.load_draft(self.root, draft.draft_id).get("graph_trace_intent"),
            dict,
        )
        with mock.patch.object(
            CONTROLLER.GRAPH_COORDINATOR,
            "trace_impact",
            side_effect=AssertionError("retry must recover without republishing"),
        ):
            recovered = CONTROLLER.trace_impact(request)

        self.assertEqual(receipt_path.read_bytes(), published_bytes)
        self.assertEqual(
            CONTROLLER.load_draft(self.root, draft.draft_id)["graph_receipt"]["receipt_id"],
            recovered.receipt_id,
        )
        self.assertNotIn("graph_trace_intent", CONTROLLER.load_draft(self.root, draft.draft_id))

    def test_trace_bind_cas_recovers_from_every_interruption_phase(self):
        phases = (
            "after-quarantine-rename",
            "after-replacement-publication",
            "before-quarantine-cleanup",
            "after-quarantine-cleanup",
        )
        for phase in phases:
            with self.subTest(phase=phase):
                self.enable_builtin_graph()
                draft = CONTROLLER.begin_refinement(
                    self.request(request=f"Durable binding {phase}")
                )
                request = CONTROLLER.TraceRequest(
                    self.root,
                    draft.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
                )
                with mock.patch.object(
                    CONTROLLER,
                    "_bind_trace_receipt",
                    side_effect=ValueError("stop before binding"),
                ):
                    with self.assertRaisesRegex(ValueError, "stop before binding"):
                        CONTROLLER.trace_impact(request)

                receipt_path = (
                    self.root / ".requirements-impact-refiner/graph" / f"{draft.draft_id}.json"
                )
                published = receipt_path.read_bytes()
                filename = f"{draft.draft_id}.json"
                real_rename = CONTROLLER._rename_noreplace
                real_link = CONTROLLER.os.link
                real_unlink = CONTROLLER.os.unlink
                interrupted = False

                def interrupting_rename(
                    directory_fd,
                    source,
                    destination,
                    real_rename=real_rename,
                    phase=phase,
                    filename=filename,
                ):
                    nonlocal interrupted
                    result = real_rename(directory_fd, source, destination)
                    if (
                        not interrupted
                        and phase == "after-quarantine-rename"
                        and source == filename
                        and str(destination).endswith(".quarantine")
                    ):
                        interrupted = True
                        raise SimulatedProcessInterruption(phase)
                    return result

                def interrupting_link(
                    source,
                    destination,
                    real_link=real_link,
                    phase=phase,
                    filename=filename,
                    **kwargs,
                ):
                    nonlocal interrupted
                    result = real_link(source, destination, **kwargs)
                    if (
                        not interrupted
                        and phase == "after-replacement-publication"
                        and str(source).endswith(".new")
                        and destination == filename
                    ):
                        interrupted = True
                        raise SimulatedProcessInterruption(phase)
                    return result

                def interrupting_unlink(path, real_unlink=real_unlink, phase=phase, **kwargs):
                    nonlocal interrupted
                    is_quarantine = str(path).endswith(".quarantine") or str(path).endswith(
                        ".quarantine.removing"
                    )
                    if not interrupted and phase == "before-quarantine-cleanup" and is_quarantine:
                        interrupted = True
                        raise SimulatedProcessInterruption(phase)
                    result = real_unlink(path, **kwargs)
                    if not interrupted and phase == "after-quarantine-cleanup" and is_quarantine:
                        interrupted = True
                        raise SimulatedProcessInterruption(phase)
                    return result

                with (
                    mock.patch.object(
                        CONTROLLER.GRAPH_COORDINATOR,
                        "trace_impact",
                        side_effect=AssertionError("binding recovery must not republish"),
                    ),
                    mock.patch.object(
                        CONTROLLER.STORAGE, "_rename_noreplace", side_effect=interrupting_rename
                    ),
                    mock.patch.object(CONTROLLER.os, "link", side_effect=interrupting_link),
                    mock.patch.object(CONTROLLER.os, "unlink", side_effect=interrupting_unlink),
                ):
                    with self.assertRaises(SimulatedProcessInterruption):
                        CONTROLLER.trace_impact(request)

                self.assertTrue(interrupted)
                with mock.patch.object(
                    CONTROLLER.GRAPH_COORDINATOR,
                    "trace_impact",
                    side_effect=AssertionError("binding recovery must not republish"),
                ):
                    recovered = CONTROLLER.trace_impact(request)

                self.assertEqual(receipt_path.read_bytes(), published)
                stored = CONTROLLER.load_draft(self.root, draft.draft_id)
                self.assertEqual(stored["graph_receipt"]["receipt_id"], recovered.receipt_id)
                self.assertNotIn("graph_trace_intent", stored)
                draft_path = self.root / ".requirements-impact-refiner/drafts" / filename
                metadata = draft_path.stat()
                self.assertEqual(metadata.st_mode & 0o777, 0o600)
                self.assertEqual(metadata.st_nlink, 1)
                transaction_artifacts = sorted(
                    path.name
                    for path in draft_path.parent.iterdir()
                    if path.name.startswith(f".{draft.draft_id}.")
                )
                self.assertEqual(transaction_artifacts, [])

    def test_trace_bind_cleanup_recovers_from_every_durable_artifact_boundary(self):
        component_kinds = (
            "replacement",
            "quarantine",
            "anchor",
            "commit",
            "swap",
            "manifest",
            "cleanup-marker",
        )
        phases = (
            ("cleanup-marker", "persist"),
            *tuple(
                (kind, boundary)
                for kind in component_kinds
                for boundary in ("quarantine", "removal")
            ),
        )
        for target_kind, boundary in phases:
            phase = f"after-{target_kind}-{boundary}"
            with self.subTest(target_kind=target_kind, boundary=boundary):
                self.enable_builtin_graph()
                draft = CONTROLLER.begin_refinement(
                    self.request(request=f"Cleanup boundary {phase}")
                )
                request = CONTROLLER.TraceRequest(
                    self.root,
                    draft.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
                )
                with mock.patch.object(
                    CONTROLLER,
                    "_bind_trace_receipt",
                    side_effect=ValueError("stop before binding"),
                ):
                    with self.assertRaisesRegex(ValueError, "stop before binding"):
                        CONTROLLER.trace_impact(request)

                receipt_path = (
                    self.root / ".requirements-impact-refiner/graph" / f"{draft.draft_id}.json"
                )
                published = receipt_path.read_bytes()
                real_write_component = CONTROLLER._write_private_transaction_component
                real_rename = CONTROLLER._rename_noreplace
                real_unlink = CONTROLLER.os.unlink
                interrupted = False

                def component_kind(name, draft=draft):
                    selected = str(name)
                    if selected.endswith(".removing"):
                        selected = selected[: -len(".removing")]
                    fixed = {
                        f".{draft.draft_id}.transaction": "manifest",
                        f".{draft.draft_id}.cleanup": "cleanup-marker",
                    }
                    if selected in fixed:
                        return fixed[selected]
                    for suffix, kind in (
                        (".new", "replacement"),
                        (".quarantine", "quarantine"),
                        (".anchor", "anchor"),
                        (".commit", "commit"),
                        (".swap", "swap"),
                    ):
                        if selected.startswith(f".{draft.draft_id}.") and selected.endswith(suffix):
                            return kind
                    return None

                def interrupting_write(
                    directory_fd,
                    name,
                    payload,
                    label,
                    real_write_component=real_write_component,
                    boundary=boundary,
                    target_kind=target_kind,
                    phase=phase,
                ):
                    nonlocal interrupted
                    result = real_write_component(directory_fd, name, payload, label)
                    if (
                        not interrupted
                        and boundary == "persist"
                        and target_kind == "cleanup-marker"
                        and component_kind(name) == "cleanup-marker"
                    ):
                        interrupted = True
                        CONTROLLER.os.close(result[0])
                        raise SimulatedProcessInterruption(phase)
                    return result

                def interrupting_rename(
                    directory_fd,
                    source,
                    destination,
                    real_rename=real_rename,
                    boundary=boundary,
                    target_kind=target_kind,
                    phase=phase,
                ):
                    nonlocal interrupted
                    result = real_rename(directory_fd, source, destination)
                    if (
                        not interrupted
                        and boundary == "quarantine"
                        and target_kind == component_kind(source)
                        and str(destination).endswith(".removing")
                    ):
                        interrupted = True
                        raise SimulatedProcessInterruption(phase)
                    return result

                def interrupting_unlink(
                    path,
                    real_unlink=real_unlink,
                    boundary=boundary,
                    target_kind=target_kind,
                    phase=phase,
                    **kwargs,
                ):
                    nonlocal interrupted
                    result = real_unlink(path, **kwargs)
                    if (
                        not interrupted
                        and boundary == "removal"
                        and target_kind == component_kind(path)
                    ):
                        interrupted = True
                        raise SimulatedProcessInterruption(phase)
                    return result

                with (
                    mock.patch.object(
                        CONTROLLER.GRAPH_COORDINATOR,
                        "trace_impact",
                        side_effect=AssertionError("cleanup recovery must not republish"),
                    ),
                    mock.patch.object(
                        CONTROLLER.STORAGE,
                        "_write_private_transaction_component",
                        side_effect=interrupting_write,
                    ),
                    mock.patch.object(
                        CONTROLLER.STORAGE, "_rename_noreplace", side_effect=interrupting_rename
                    ),
                    mock.patch.object(CONTROLLER.os, "unlink", side_effect=interrupting_unlink),
                ):
                    with self.assertRaises(SimulatedProcessInterruption):
                        CONTROLLER.trace_impact(request)

                self.assertTrue(interrupted)
                draft_directory = self.root / ".requirements-impact-refiner/drafts"
                interrupted_artifacts = [
                    path.name
                    for path in draft_directory.iterdir()
                    if path.name.startswith(f".{draft.draft_id}.")
                ]
                interrupted_kinds = {component_kind(name) for name in interrupted_artifacts}
                canonical_during_cleanup = json.loads(
                    (draft_directory / f"{draft.draft_id}.json").read_text(encoding="utf-8")
                )
                self.assertIn("graph_receipt", canonical_during_cleanup)
                if boundary == "removal":
                    self.assertNotIn(target_kind, interrupted_kinds)
                if target_kind == "commit" and boundary == "removal":
                    self.assertIn("swap", interrupted_kinds)
                    self.assertIn("manifest", interrupted_kinds)
                    self.assertIn("cleanup-marker", interrupted_kinds)
                if target_kind == "swap" and boundary == "removal":
                    self.assertNotIn("commit", interrupted_kinds)
                    self.assertIn("manifest", interrupted_kinds)
                    self.assertIn("cleanup-marker", interrupted_kinds)
                if target_kind == "manifest" and boundary == "removal":
                    self.assertEqual(interrupted_kinds, {"cleanup-marker"})
                if target_kind == "cleanup-marker" and boundary == "removal":
                    self.assertEqual(interrupted_artifacts, [])
                with mock.patch.object(
                    CONTROLLER.GRAPH_COORDINATOR,
                    "trace_impact",
                    side_effect=AssertionError("cleanup recovery must not republish"),
                ):
                    recovered = CONTROLLER.trace_impact(request)

                self.assertEqual(receipt_path.read_bytes(), published)
                stored = CONTROLLER.load_draft(self.root, draft.draft_id)
                self.assertEqual(stored["graph_receipt"]["receipt_id"], recovered.receipt_id)
                self.assertNotIn("graph_trace_intent", stored)
                draft_path = (
                    self.root / ".requirements-impact-refiner/drafts" / f"{draft.draft_id}.json"
                )
                self.assertEqual(
                    sorted(
                        path.name
                        for path in draft_path.parent.iterdir()
                        if path.name.startswith(f".{draft.draft_id}.")
                    ),
                    [],
                )

    def test_draft_cleanup_marker_recovery_rejects_cross_draft_and_symlink_state(self):
        for marker_kind in ("cross-draft", "symlink"):
            with self.subTest(marker_kind=marker_kind):
                draft = CONTROLLER.begin_refinement(
                    self.request(request=f"Foreign cleanup marker {marker_kind}")
                )
                draft_path = (
                    self.root / ".requirements-impact-refiner/drafts" / f"{draft.draft_id}.json"
                )
                marker_path = draft_path.parent / f".{draft.draft_id}.cleanup"
                canonical = draft_path.read_bytes()
                metadata = draft_path.stat()
                marker = {
                    "draft_id": "f" * 32,
                    "kind": "draft-transaction-cleanup",
                    "manifest_sha256": "a" * 64,
                    "replacement_dev": metadata.st_dev,
                    "replacement_ino": metadata.st_ino,
                    "replacement_sha256": hashlib.sha256(canonical).hexdigest(),
                    "repo_root_sha256": hashlib.sha256(str(self.root).encode("utf-8")).hexdigest(),
                    "schema_version": 1,
                    "transaction_id": "b" * 32,
                }
                marker_bytes = json.dumps(
                    marker,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
                outside = self.root / f"cleanup-marker-{marker_kind}"
                outside.write_bytes(marker_bytes)
                if marker_kind == "cross-draft":
                    marker_path.write_bytes(marker_bytes)
                    marker_path.chmod(0o600)
                else:
                    os.symlink(outside, marker_path)

                with self.assertRaisesRegex(ValueError, "cleanup|transaction.*unsafe|identity"):
                    CONTROLLER._recover_private_draft_transaction(self.root, draft.draft_id)

                self.assertEqual(draft_path.read_bytes(), canonical)
                if marker_kind == "cross-draft":
                    self.assertEqual(marker_path.read_bytes(), marker_bytes)
                else:
                    self.assertTrue(marker_path.is_symlink())
                    self.assertEqual(outside.read_bytes(), marker_bytes)

    def test_pre_manifest_transaction_cleanup_preserves_late_replacements(self):
        for target_kind in ("replacement", "anchor"):
            for replacement_kind in ("regular", "symlink"):
                with self.subTest(
                    target_kind=target_kind,
                    replacement_kind=replacement_kind,
                ):
                    draft = CONTROLLER.begin_refinement(
                        self.request(request=(f"Pre-manifest {target_kind} {replacement_kind}"))
                    )
                    expected = CONTROLLER.load_draft(self.root, draft.draft_id)
                    replacement = dict(expected)
                    replacement["graph_trace_intent"] = {"intent_id": "c" * 32}
                    token = "d" * 32
                    suffix = "new" if target_kind == "replacement" else "anchor"
                    target_name = f".{draft.draft_id}.{token}.{suffix}"
                    target_path = self.root / ".requirements-impact-refiner/drafts" / target_name
                    outside = self.root / (f"pre-manifest-{target_kind}-{replacement_kind}")
                    outside.write_bytes(b"outside-safe")
                    foreign = f"foreign-{target_kind}-{replacement_kind}".encode()
                    real_write = CONTROLLER._write_private_transaction_component
                    real_rename = CONTROLLER._rename_noreplace
                    real_unlink = CONTROLLER.os.unlink
                    inserted = {"value": False}

                    def fail_manifest(directory_fd, name, payload, label, real_write=real_write):
                        if label == "draft transaction manifest":
                            raise ValueError("injected manifest failure")
                        return real_write(directory_fd, name, payload, label)

                    def install(
                        directory_fd,
                        real_unlink=real_unlink,
                        target_name=target_name,
                        replacement_kind=replacement_kind,
                        outside=outside,
                        foreign=foreign,
                        inserted=inserted,
                    ):
                        real_unlink(target_name, dir_fd=directory_fd)
                        self._install_cleanup_replacement(
                            replacement_kind,
                            target_name,
                            directory_fd,
                            outside,
                            foreign,
                        )
                        inserted["value"] = True

                    def replacing_rename(
                        directory_fd,
                        source,
                        destination,
                        target_name=target_name,
                        real_rename=real_rename,
                        inserted=inserted,
                    ):
                        if (
                            not inserted["value"]
                            and source == target_name
                            and str(destination).endswith(".removing")
                        ):
                            install(directory_fd)
                        return real_rename(directory_fd, source, destination)

                    def replacing_unlink(
                        path,
                        real_unlink=real_unlink,
                        target_name=target_name,
                        inserted=inserted,
                        **kwargs,
                    ):
                        if not inserted["value"] and path == target_name:
                            install(kwargs["dir_fd"])
                        return real_unlink(path, **kwargs)

                    with (
                        mock.patch.object(CONTROLLER.secrets, "token_hex", return_value=token),
                        mock.patch.object(
                            CONTROLLER.STORAGE,
                            "_write_private_transaction_component",
                            side_effect=fail_manifest,
                        ),
                        mock.patch.object(
                            CONTROLLER.STORAGE, "_rename_noreplace", side_effect=replacing_rename
                        ),
                        mock.patch.object(CONTROLLER.os, "unlink", side_effect=replacing_unlink),
                    ):
                        with self.assertRaisesRegex(ValueError, "manifest|cleanup|uncertain"):
                            CONTROLLER._cas_replace_private_draft(
                                Path(str(expected["repo_root"])),
                                draft.draft_id,
                                expected,
                                replacement,
                            )

                    self.assertTrue(inserted)
                    if replacement_kind == "regular":
                        self.assertEqual(target_path.read_bytes(), foreign)
                    else:
                        self.assertTrue(target_path.is_symlink())
                        self.assertEqual(outside.read_bytes(), b"outside-safe")
                    self.assertEqual(CONTROLLER.load_draft(self.root, draft.draft_id), expected)

    def _assert_durable_cas_quarantine_destination_is_no_clobber(self, replacement_kind):
        draft = CONTROLLER.begin_refinement(
            self.request(request=f"CAS quarantine destination {replacement_kind}")
        )
        expected = CONTROLLER.load_draft(self.root, draft.draft_id)
        replacement = dict(expected)
        replacement["graph_trace_intent"] = {"intent_id": "c" * 32}
        token = "d" * 32
        destination_name = f".{draft.draft_id}.{token}.quarantine"
        draft_directory = self.root / ".requirements-impact-refiner/drafts"
        destination = draft_directory / destination_name
        canonical = draft_directory / f"{draft.draft_id}.json"
        outside = self.root / f"cas-quarantine-outside-{replacement_kind}"
        outside.write_bytes(b"outside-safe")
        foreign = f"cas-quarantine-foreign-{replacement_kind}".encode()
        real_claim = CONTROLLER._rename_noreplace
        inserted = False

        def race_claim(directory_fd, source, selected):
            nonlocal inserted
            if source == f"{draft.draft_id}.json" and selected == destination_name:
                self._install_cleanup_replacement(
                    replacement_kind,
                    destination_name,
                    directory_fd,
                    outside,
                    foreign,
                )
                inserted = True
            return real_claim(directory_fd, source, selected)

        with (
            mock.patch.object(CONTROLLER.secrets, "token_hex", return_value=token),
            mock.patch.object(CONTROLLER.STORAGE, "_rename_noreplace", side_effect=race_claim),
        ):
            with self.assertRaisesRegex(ValueError, "compare-and-swap|quarantine|uncertain"):
                CONTROLLER._cas_replace_private_draft(
                    Path(str(expected["repo_root"])),
                    draft.draft_id,
                    expected,
                    replacement,
                )

        self.assertTrue(inserted)
        self.assertEqual(canonical.read_bytes(), CONTROLLER._canonical_bytes(expected))
        self.assertTrue((draft_directory / f".{draft.draft_id}.transaction").exists())
        if replacement_kind == "regular":
            self.assertEqual(destination.read_bytes(), foreign)
        else:
            self.assertTrue(destination.is_symlink())
            self.assertEqual(outside.read_bytes(), b"outside-safe")

    def test_durable_cas_quarantine_does_not_clobber_late_regular_destination(self):
        self._assert_durable_cas_quarantine_destination_is_no_clobber("regular")

    def test_durable_cas_quarantine_does_not_clobber_late_symlink_destination(self):
        self._assert_durable_cas_quarantine_destination_is_no_clobber("symlink")

    def test_trace_intent_write_failure_cannot_publish_and_retry_is_fresh(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request(request="Intent write fault"))
        request = CONTROLLER.TraceRequest(
            self.root,
            draft.draft_id,
            (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
        )
        with (
            mock.patch.object(
                CONTROLLER,
                "_cas_replace_private_draft",
                side_effect=ValueError("injected intent write failure"),
            ),
            mock.patch.object(
                CONTROLLER.GRAPH_COORDINATOR,
                "trace_impact",
                side_effect=AssertionError("publication must not run before intent"),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "intent write failure"):
                CONTROLLER.trace_impact(request)

        receipt_path = self.root / ".requirements-impact-refiner/graph" / f"{draft.draft_id}.json"
        self.assertFalse(receipt_path.exists())
        self.assertNotIn("graph_trace_intent", CONTROLLER.load_draft(self.root, draft.draft_id))
        self.assertRegex(CONTROLLER.trace_impact(request).receipt_id, r"^[0-9a-f]{32}$")

    def test_trace_rejects_cross_draft_transaction_intent(self):
        self.enable_builtin_graph()
        first = CONTROLLER.begin_refinement(self.request(request="First intent"))
        first_request = CONTROLLER.TraceRequest(
            self.root,
            first.draft_id,
            (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
        )
        with mock.patch.object(
            CONTROLLER.GRAPH_COORDINATOR,
            "_persist_receipt",
            side_effect=ValueError("stop after intent"),
        ):
            with self.assertRaisesRegex(ValueError, "stop after intent"):
                CONTROLLER.trace_impact(first_request)
        first_intent = CONTROLLER.load_draft(self.root, first.draft_id)["graph_trace_intent"]
        second = CONTROLLER.begin_refinement(self.request(request="Second intent"))
        second_stored = CONTROLLER.load_draft(self.root, second.draft_id)
        second_stored["graph_trace_intent"] = first_intent
        CONTROLLER._replace_private_draft(self.root, second.draft_id, second_stored)

        with self.assertRaisesRegex(ValueError, "trace intent identity"):
            CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    second.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
                )
            )

        self.assertFalse(
            (self.root / ".requirements-impact-refiner/graph" / f"{second.draft_id}.json").exists()
        )

    def test_trace_rejects_internally_valid_receipt_without_controller_intent(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request(request="Unmarked artifact"))
        stored = CONTROLLER.load_draft(self.root, draft.draft_id)
        graph_settings = stored["settings"]["impact_graph"]
        seeds = (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),)
        CONTROLLER.GRAPH_COORDINATOR.trace_impact(
            self.root,
            CONTROLLER._graph_draft_identity(stored),
            seeds,
            graph_settings,
        )

        with self.assertRaisesRegex(ValueError, "pre-publication trace intent"):
            CONTROLLER.trace_impact(CONTROLLER.TraceRequest(self.root, draft.draft_id, seeds))

        self.assertIsNone(CONTROLLER.load_draft(self.root, draft.draft_id).get("graph_receipt"))

    def test_trace_stale_crash_artifact_is_cleaned_before_fresh_retry(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request(request="Stale recovery"))
        request = CONTROLLER.TraceRequest(
            self.root,
            draft.draft_id,
            (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
        )
        with mock.patch.object(
            CONTROLLER,
            "_bind_trace_receipt",
            side_effect=ValueError("injected post-persist bind failure"),
        ):
            with self.assertRaisesRegex(ValueError, "post-persist bind failure"):
                CONTROLLER.trace_impact(request)
        receipt_path = self.root / ".requirements-impact-refiner/graph" / f"{draft.draft_id}.json"
        self.assertTrue(receipt_path.is_file())
        (self.root / "desktop/new_consumer.py").write_text(
            'FIELD = "profile.displayName"\n', encoding="utf-8"
        )

        with self.assertRaisesRegex(ValueError, "recovery source inventory is stale"):
            CONTROLLER.trace_impact(request)

        self.assertFalse(receipt_path.exists())
        self.assertIsNone(CONTROLLER.load_draft(self.root, draft.draft_id).get("graph_receipt"))
        fresh = CONTROLLER.trace_impact(request)
        self.assertTrue(
            any(
                node["location"] == "desktop/new_consumer.py"
                for node in fresh.compact_graph["nodes"]
            )
        )

    def _trace_with_pre_bind_draft_mutation(self, request_text, mutate):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request(request=request_text))
        request = CONTROLLER.TraceRequest(
            self.root,
            draft.draft_id,
            (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
        )
        real_bind = CONTROLLER._bind_trace_receipt

        def racing_bind(*args, **kwargs):
            current = CONTROLLER.load_draft(self.root, draft.draft_id)
            mutate(current, request)
            return real_bind(*args, **kwargs)

        with mock.patch.object(CONTROLLER, "_bind_trace_receipt", side_effect=racing_bind):
            with self.assertRaisesRegex(
                ValueError, "trace transaction changed before receipt binding"
            ):
                CONTROLLER.trace_impact(request)
        return draft

    def test_bind_fails_cas_when_trace_intent_is_removed(self):
        def remove(current, request):
            current.pop("graph_trace_intent", None)
            CONTROLLER._replace_private_draft(self.root, current["draft_id"], current)

        draft = self._trace_with_pre_bind_draft_mutation("Removed bind intent", remove)

        stored = CONTROLLER.load_draft(self.root, draft.draft_id)
        self.assertNotIn("graph_trace_intent", stored)
        self.assertIsNone(stored.get("graph_receipt"))

    def test_bind_fails_cas_when_trace_intent_is_replaced(self):
        def replace(current, request):
            replacement = dict(current["graph_trace_intent"])
            replacement["intent_id"] = "0" * 32
            current["graph_trace_intent"] = replacement
            CONTROLLER._replace_private_draft(self.root, current["draft_id"], current)

        draft = self._trace_with_pre_bind_draft_mutation("Replaced bind intent", replace)

        stored = CONTROLLER.load_draft(self.root, draft.draft_id)
        self.assertEqual(stored["graph_trace_intent"]["intent_id"], "0" * 32)
        self.assertIsNone(stored.get("graph_receipt"))

    def test_bind_fails_cas_for_competing_valid_same_draft_transaction(self):
        competing = {}

        def replace_with_valid(current, request):
            settings = current["settings"]["impact_graph"]
            inventory = CONTROLLER.GRAPH_COORDINATOR._collect_source_digests(
                self.root,
                CONTROLLER.GRAPH_COORDINATOR.Deadline(CONTROLLER.time, 30),
            )
            replacement = CONTROLLER._new_trace_intent(
                self.root, current, request.seeds, settings, inventory
            )
            competing.update(replacement)
            current["graph_trace_intent"] = replacement
            CONTROLLER._replace_private_draft(self.root, current["draft_id"], current)

        draft = self._trace_with_pre_bind_draft_mutation(
            "Competing bind intent", replace_with_valid
        )

        stored = CONTROLLER.load_draft(self.root, draft.draft_id)
        self.assertEqual(stored["graph_trace_intent"], competing)
        self.assertIsNone(stored.get("graph_receipt"))

    def _private_cleanup_receipt(self, draft_id, payload=b"exact-receipt"):
        graph_dir = self.root / ".requirements-impact-refiner/graph"
        graph_dir.mkdir(parents=True, exist_ok=True)
        path = graph_dir / f"{draft_id}.json"
        path.write_bytes(payload)
        path.chmod(0o600)
        return graph_dir, path, payload

    def _install_cleanup_replacement(self, replacement_kind, name, directory_fd, outside, payload):
        if replacement_kind == "regular":
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_fd,
            )
            try:
                os.write(descriptor, payload)
            finally:
                os.close(descriptor)
        else:
            os.symlink(outside, name, dir_fd=directory_fd)

    def test_stale_cleanup_preserves_regular_replacement_after_preflight_read(self):
        draft_id = "a" * 32
        graph_dir, path, expected = self._private_cleanup_receipt(draft_id)
        saved = graph_dir / "saved-exact.json"
        foreign = b"foreign-draft-receipt"
        real_read = CONTROLLER._read_bound_receipt_bytes

        def swap_after_read(root, selected):
            payload = real_read(root, selected)
            path.rename(saved)
            path.write_bytes(foreign)
            path.chmod(0o600)
            return payload

        with mock.patch.object(
            CONTROLLER, "_read_bound_receipt_bytes", side_effect=swap_after_read
        ):
            with self.assertRaisesRegex(ValueError, "cleanup.*changed|uncertain"):
                CONTROLLER._remove_exact_trace_receipt(self.root, draft_id, expected)

        self.assertEqual(path.read_bytes(), foreign)
        self.assertEqual(saved.read_bytes(), expected)

    def test_stale_cleanup_preserves_symlink_and_outside_target(self):
        draft_id = "b" * 32
        graph_dir, path, expected = self._private_cleanup_receipt(draft_id)
        saved = graph_dir / "saved-symlink-exact.json"
        outside = self.root / "outside-receipt"
        outside.write_text("outside-safe", encoding="utf-8")
        real_read = CONTROLLER._read_bound_receipt_bytes

        def swap_after_read(root, selected):
            payload = real_read(root, selected)
            path.rename(saved)
            os.symlink(outside, path)
            return payload

        with mock.patch.object(
            CONTROLLER, "_read_bound_receipt_bytes", side_effect=swap_after_read
        ):
            with self.assertRaisesRegex(ValueError, "cleanup.*unsafe|uncertain|changed"):
                CONTROLLER._remove_exact_trace_receipt(self.root, draft_id, expected)

        self.assertTrue(path.is_symlink())
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside-safe")
        self.assertEqual(saved.read_bytes(), expected)

    def test_stale_cleanup_quarantine_revalidates_opened_inode(self):
        draft_id = "c" * 32
        graph_dir, path, expected = self._private_cleanup_receipt(draft_id)
        saved = graph_dir / "saved-opened-exact.json"
        foreign = b"foreign-after-open"
        real_rename = CONTROLLER._rename_noreplace
        real_path_rename = CONTROLLER.os.rename
        swapped = False

        def swap_before_quarantine(directory_fd, source, destination):
            nonlocal swapped
            if source == f"{draft_id}.json" and not swapped:
                swapped = True
                real_path_rename(
                    source,
                    saved.name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                )
                descriptor = os.open(
                    source,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=directory_fd,
                )
                try:
                    os.write(descriptor, foreign)
                finally:
                    os.close(descriptor)
            return real_rename(directory_fd, source, destination)

        with mock.patch.object(CONTROLLER, "_rename_noreplace", side_effect=swap_before_quarantine):
            with self.assertRaisesRegex(ValueError, "cleanup.*changed|uncertain"):
                CONTROLLER._remove_exact_trace_receipt(self.root, draft_id, expected)

        self.assertEqual(path.read_bytes(), foreign)
        self.assertEqual(saved.read_bytes(), expected)

    def _assert_stale_receipt_quarantine_destination_is_no_clobber(self, replacement_kind):
        draft_id = ("8" if replacement_kind == "regular" else "9") * 32
        graph_dir, receipt, expected = self._private_cleanup_receipt(
            draft_id, payload=f"stale-exact-{replacement_kind}".encode()
        )
        cleanup_id = "e" * 32
        destination_name = f".{draft_id}.{cleanup_id}.stale"
        destination = graph_dir / destination_name
        outside = self.root / f"stale-destination-outside-{replacement_kind}"
        outside.write_bytes(b"outside-safe")
        foreign = f"stale-destination-foreign-{replacement_kind}".encode()
        real_claim = CONTROLLER._rename_noreplace
        inserted = False
        committed = False

        def race_claim(directory_fd, source, selected):
            nonlocal inserted
            if source == f"{draft_id}.json" and selected == destination_name:
                self._install_cleanup_replacement(
                    replacement_kind,
                    destination_name,
                    directory_fd,
                    outside,
                    foreign,
                )
                inserted = True
            return real_claim(directory_fd, source, selected)

        def commit():
            nonlocal committed
            committed = True

        with (
            mock.patch.object(CONTROLLER.secrets, "token_hex", return_value=cleanup_id),
            mock.patch.object(CONTROLLER, "_rename_noreplace", side_effect=race_claim),
        ):
            with self.assertRaisesRegex(ValueError, "cleanup|quarantine|unsafe"):
                CONTROLLER._remove_exact_trace_receipt(self.root, draft_id, expected, commit=commit)

        self.assertTrue(inserted)
        self.assertFalse(committed)
        self.assertEqual(receipt.read_bytes(), expected)
        if replacement_kind == "regular":
            self.assertEqual(destination.read_bytes(), foreign)
        else:
            self.assertTrue(destination.is_symlink())
            self.assertEqual(outside.read_bytes(), b"outside-safe")

    def test_stale_receipt_quarantine_does_not_clobber_late_regular_destination(self):
        self._assert_stale_receipt_quarantine_destination_is_no_clobber("regular")

    def test_stale_receipt_quarantine_does_not_clobber_late_symlink_destination(self):
        self._assert_stale_receipt_quarantine_destination_is_no_clobber("symlink")

    def test_stale_cleanup_guard_mutation_preserves_regular_and_symlink_replacements(self):
        for index, replacement_kind in enumerate(("regular", "symlink")):
            with self.subTest(replacement_kind=replacement_kind):
                draft_id = str(index + 4) * 32
                _graph_dir, path, expected = self._private_cleanup_receipt(
                    draft_id, payload=f"exact-{replacement_kind}".encode()
                )
                outside = self.root / f"guard-outside-{replacement_kind}"
                outside.write_bytes(b"outside-safe")
                foreign = f"foreign-{replacement_kind}".encode()
                real_rename = CONTROLLER._rename_noreplace
                real_unlink = CONTROLLER.os.unlink
                inserted = {"value": False}
                committed = False
                filename = f"{draft_id}.json"

                def install(
                    directory_fd,
                    real_unlink=real_unlink,
                    filename=filename,
                    replacement_kind=replacement_kind,
                    outside=outside,
                    foreign=foreign,
                    inserted=inserted,
                ):
                    real_unlink(filename, dir_fd=directory_fd)
                    self._install_cleanup_replacement(
                        replacement_kind,
                        filename,
                        directory_fd,
                        outside,
                        foreign,
                    )
                    inserted["value"] = True

                def replacing_rename(
                    directory_fd,
                    source,
                    destination,
                    filename=filename,
                    real_rename=real_rename,
                    inserted=inserted,
                ):
                    if (
                        not inserted["value"]
                        and source == filename
                        and str(destination).endswith(".removing")
                    ):
                        install(directory_fd)
                    return real_rename(directory_fd, source, destination)

                def replacing_unlink(
                    selected,
                    real_unlink=real_unlink,
                    filename=filename,
                    inserted=inserted,
                    **kwargs,
                ):
                    if not inserted["value"] and selected == filename:
                        install(kwargs["dir_fd"])
                    return real_unlink(selected, **kwargs)

                def mark_committed():
                    nonlocal committed
                    committed = True

                with (
                    mock.patch.object(
                        CONTROLLER.STORAGE, "_rename_noreplace", side_effect=replacing_rename
                    ),
                    mock.patch.object(CONTROLLER.os, "unlink", side_effect=replacing_unlink),
                ):
                    with self.assertRaisesRegex(
                        ValueError, "cleanup.*changed|cleanup.*replacement|uncertain"
                    ):
                        CONTROLLER._remove_exact_trace_receipt(
                            self.root,
                            draft_id,
                            expected,
                            commit=mark_committed,
                        )

                self.assertTrue(inserted)
                self.assertFalse(committed)
                if replacement_kind == "regular":
                    self.assertEqual(path.read_bytes(), foreign)
                else:
                    self.assertTrue(path.is_symlink())
                    self.assertEqual(outside.read_bytes(), b"outside-safe")

    def test_stale_cleanup_recovery_mutation_preserves_regular_and_symlink_replacements(self):
        for index, replacement_kind in enumerate(("regular", "symlink")):
            with self.subTest(replacement_kind=replacement_kind):
                draft_id = str(index + 6) * 32
                _graph_dir, path, expected = self._private_cleanup_receipt(
                    draft_id,
                    payload=f"recover-{replacement_kind}".encode(),
                )
                intent = {"draft_id": draft_id, "transaction_id": "e" * 32}
                outside = self.root / f"recovery-outside-{replacement_kind}"
                outside.write_bytes(b"outside-safe")
                foreign = f"recovery-foreign-{replacement_kind}".encode()
                real_unlink = CONTROLLER.os.unlink
                real_rename = CONTROLLER._rename_noreplace
                interrupted = False

                def interrupt_stale_quarantine(selected, real_unlink=real_unlink, **kwargs):
                    nonlocal interrupted
                    if not interrupted and str(selected).endswith(".stale"):
                        interrupted = True
                        raise SimulatedProcessInterruption("recovery guard prepared")
                    return real_unlink(selected, **kwargs)

                def interrupt_stale_quarantine_rename(
                    directory_fd, source, destination, real_rename=real_rename
                ):
                    nonlocal interrupted
                    if (
                        not interrupted
                        and str(source).endswith(".stale")
                        and str(destination).endswith(".removing")
                    ):
                        interrupted = True
                        raise SimulatedProcessInterruption("recovery guard prepared")
                    return real_rename(directory_fd, source, destination)

                with (
                    mock.patch.object(
                        CONTROLLER.os,
                        "unlink",
                        side_effect=interrupt_stale_quarantine,
                    ),
                    mock.patch.object(
                        CONTROLLER.STORAGE,
                        "_rename_noreplace",
                        side_effect=interrupt_stale_quarantine_rename,
                    ),
                ):
                    with self.assertRaises(SimulatedProcessInterruption):
                        CONTROLLER._remove_exact_trace_receipt(
                            self.root,
                            draft_id,
                            expected,
                            guard_intent_sha256=(CONTROLLER._trace_intent_sha256(intent)),
                        )

                self.assertTrue(interrupted)
                inserted = {"value": False}
                filename = f"{draft_id}.json"

                def install(
                    directory_fd,
                    real_unlink=real_unlink,
                    filename=filename,
                    replacement_kind=replacement_kind,
                    outside=outside,
                    foreign=foreign,
                    inserted=inserted,
                ):
                    real_unlink(filename, dir_fd=directory_fd)
                    self._install_cleanup_replacement(
                        replacement_kind,
                        filename,
                        directory_fd,
                        outside,
                        foreign,
                    )
                    inserted["value"] = True

                def replacing_rename(
                    directory_fd,
                    source,
                    destination,
                    filename=filename,
                    real_rename=real_rename,
                    inserted=inserted,
                ):
                    if (
                        not inserted["value"]
                        and source == filename
                        and str(destination).endswith(".removing")
                    ):
                        install(directory_fd)
                    return real_rename(directory_fd, source, destination)

                def replacing_unlink(
                    selected,
                    real_unlink=real_unlink,
                    filename=filename,
                    inserted=inserted,
                    **kwargs,
                ):
                    if not inserted["value"] and selected == filename:
                        install(kwargs["dir_fd"])
                    return real_unlink(selected, **kwargs)

                with (
                    mock.patch.object(
                        CONTROLLER.STORAGE, "_rename_noreplace", side_effect=replacing_rename
                    ),
                    mock.patch.object(CONTROLLER.os, "unlink", side_effect=replacing_unlink),
                ):
                    with self.assertRaisesRegex(
                        ValueError, "cleanup.*changed|cleanup.*replacement|uncertain"
                    ):
                        CONTROLLER._recover_stale_cleanup_guard(self.root, draft_id, intent)

                self.assertTrue(inserted)
                if replacement_kind == "regular":
                    self.assertEqual(path.read_bytes(), foreign)
                else:
                    self.assertTrue(path.is_symlink())
                    self.assertEqual(outside.read_bytes(), b"outside-safe")

    def test_transaction_unlink_helper_preserves_exact_mutation_replacements(self):
        for index, replacement_kind in enumerate(("regular", "symlink")):
            with self.subTest(replacement_kind=replacement_kind):
                directory = self.root / f"component-{replacement_kind}"
                directory.mkdir()
                name = f"component-{index}.phase"
                exact = b"exact-transaction-component"
                selected = directory / name
                selected.write_bytes(exact)
                selected.chmod(0o600)
                outside = self.root / f"component-outside-{replacement_kind}"
                outside.write_bytes(b"outside-safe")
                foreign = f"component-foreign-{replacement_kind}".encode()
                flags = os.O_RDONLY | os.O_DIRECTORY
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                directory_fd = os.open(directory, flags)
                component = CONTROLLER._open_optional_transaction_component(
                    directory_fd, name, 1024, "test transaction component"
                )
                self.assertIsNotNone(component)
                real_rename = CONTROLLER._rename_noreplace
                real_unlink = CONTROLLER.os.unlink
                inserted = {"value": False}

                def install(
                    real_unlink=real_unlink,
                    name=name,
                    directory_fd=directory_fd,
                    replacement_kind=replacement_kind,
                    outside=outside,
                    foreign=foreign,
                    inserted=inserted,
                ):
                    real_unlink(name, dir_fd=directory_fd)
                    self._install_cleanup_replacement(
                        replacement_kind,
                        name,
                        directory_fd,
                        outside,
                        foreign,
                    )
                    inserted["value"] = True

                def replacing_rename(
                    directory_fd,
                    source,
                    destination,
                    name=name,
                    real_rename=real_rename,
                    inserted=inserted,
                ):
                    if (
                        not inserted["value"]
                        and source == name
                        and str(destination).endswith(".removing")
                    ):
                        install()
                    return real_rename(directory_fd, source, destination)

                def replacing_unlink(
                    path, real_unlink=real_unlink, name=name, inserted=inserted, **kwargs
                ):
                    if not inserted["value"] and path == name:
                        install()
                    return real_unlink(path, **kwargs)

                try:
                    with (
                        mock.patch.object(
                            CONTROLLER.STORAGE, "_rename_noreplace", side_effect=replacing_rename
                        ),
                        mock.patch.object(CONTROLLER.os, "unlink", side_effect=replacing_unlink),
                    ):
                        with self.assertRaisesRegex(ValueError, "changed|replacement|uncertain"):
                            CONTROLLER._unlink_transaction_component(
                                directory_fd,
                                name,
                                component,
                                exact,
                                1024,
                                "test transaction component",
                            )
                finally:
                    os.close(component[0])
                    os.close(directory_fd)

                self.assertTrue(inserted)
                if replacement_kind == "regular":
                    self.assertEqual(selected.read_bytes(), foreign)
                else:
                    self.assertTrue(selected.is_symlink())
                    self.assertEqual(outside.read_bytes(), b"outside-safe")

    def test_noreplace_quarantine_claim_preserves_regular_destination(self):
        directory = self.root / "noreplace-regular"
        directory.mkdir()
        source = directory / "source.phase"
        destination = directory / "source.phase.removing"
        source.write_bytes(b"exact-source")
        destination.write_bytes(b"foreign-destination")
        flags = os.O_RDONLY | os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        directory_fd = os.open(directory, flags)
        try:
            self.assertTrue(
                hasattr(CONTROLLER, "_rename_noreplace"),
                "cleanup needs an exclusive no-clobber quarantine claim",
            )
            with self.assertRaises(FileExistsError):
                CONTROLLER._rename_noreplace(directory_fd, source.name, destination.name)
        finally:
            os.close(directory_fd)

        self.assertEqual(source.read_bytes(), b"exact-source")
        self.assertEqual(destination.read_bytes(), b"foreign-destination")

    def test_noreplace_quarantine_claim_preserves_symlink_destination(self):
        directory = self.root / "noreplace-symlink"
        directory.mkdir()
        source = directory / "source.phase"
        destination = directory / "source.phase.removing"
        outside = self.root / "noreplace-outside"
        source.write_bytes(b"exact-source")
        outside.write_bytes(b"outside-safe")
        os.symlink(outside, destination)
        flags = os.O_RDONLY | os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        directory_fd = os.open(directory, flags)
        try:
            self.assertTrue(
                hasattr(CONTROLLER, "_rename_noreplace"),
                "cleanup needs an exclusive no-clobber quarantine claim",
            )
            with self.assertRaises(FileExistsError):
                CONTROLLER._rename_noreplace(directory_fd, source.name, destination.name)
        finally:
            os.close(directory_fd)

        self.assertEqual(source.read_bytes(), b"exact-source")
        self.assertTrue(destination.is_symlink())
        self.assertEqual(outside.read_bytes(), b"outside-safe")

    def test_noreplace_quarantine_claim_fails_closed_when_platform_is_unsupported(self):
        directory = self.root / "noreplace-unsupported"
        directory.mkdir()
        source = directory / "source.phase"
        destination = directory / "source.phase.removing"
        source.write_bytes(b"exact-source")
        flags = os.O_RDONLY | os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        directory_fd = os.open(directory, flags)
        try:
            with mock.patch.object(CONTROLLER.sys, "platform", "unsupported"):
                with self.assertRaisesRegex(OSError, "unavailable"):
                    CONTROLLER._rename_noreplace(directory_fd, source.name, destination.name)
        finally:
            os.close(directory_fd)

        self.assertEqual(source.read_bytes(), b"exact-source")
        self.assertFalse(destination.exists())

    def _assert_quarantine_destination_race_is_no_clobber(self, replacement_kind):
        directory = self.root / f"quarantine-race-{replacement_kind}"
        directory.mkdir()
        name = "component.phase"
        removing_name = f"{name}.removing"
        selected = directory / name
        destination = directory / removing_name
        outside = self.root / f"quarantine-race-outside-{replacement_kind}"
        exact = b"exact-transaction-component"
        foreign = f"foreign-destination-{replacement_kind}".encode()
        selected.write_bytes(exact)
        selected.chmod(0o600)
        outside.write_bytes(b"outside-safe")
        flags = os.O_RDONLY | os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        directory_fd = os.open(directory, flags)
        component = CONTROLLER._open_optional_transaction_component(
            directory_fd, name, 1024, "test transaction component"
        )
        self.assertIsNotNone(component)
        real_claim = CONTROLLER._rename_noreplace
        inserted = False

        def insert_at_destination_window(claim_fd, source, destination_name):
            nonlocal inserted
            self.assertEqual(claim_fd, directory_fd)
            self.assertEqual(source, name)
            self.assertEqual(destination_name, removing_name)
            self._install_cleanup_replacement(
                replacement_kind,
                removing_name,
                directory_fd,
                outside,
                foreign,
            )
            inserted = True
            return real_claim(claim_fd, source, destination_name)

        try:
            with mock.patch.object(
                CONTROLLER.STORAGE,
                "_rename_noreplace",
                side_effect=insert_at_destination_window,
            ):
                with self.assertRaisesRegex(ValueError, "quarantined|already exists|uncertain"):
                    CONTROLLER._unlink_transaction_component(
                        directory_fd,
                        name,
                        component,
                        exact,
                        1024,
                        "test transaction component",
                    )
        finally:
            os.close(component[0])
            os.close(directory_fd)

        self.assertTrue(inserted)
        self.assertEqual(selected.read_bytes(), exact)
        if replacement_kind == "regular":
            self.assertEqual(destination.read_bytes(), foreign)
        else:
            self.assertTrue(destination.is_symlink())
            self.assertEqual(outside.read_bytes(), b"outside-safe")

    def test_transaction_quarantine_does_not_clobber_late_regular_destination(self):
        self._assert_quarantine_destination_race_is_no_clobber("regular")

    def test_transaction_quarantine_does_not_clobber_late_symlink_destination(self):
        self._assert_quarantine_destination_race_is_no_clobber("symlink")

    def test_transaction_component_write_failure_preserves_cleanup_replacement(self):
        for index, replacement_kind in enumerate(("regular", "symlink")):
            with self.subTest(replacement_kind=replacement_kind):
                directory = self.root / f"write-component-{replacement_kind}"
                directory.mkdir()
                name = f"write-component-{index}.phase"
                exact = b"exact-write-component"
                selected = directory / name
                outside = self.root / f"write-outside-{replacement_kind}"
                outside.write_bytes(b"outside-safe")
                foreign = f"write-foreign-{replacement_kind}".encode()
                flags = os.O_RDONLY | os.O_DIRECTORY
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                directory_fd = os.open(directory, flags)
                real_rename = CONTROLLER._rename_noreplace
                real_unlink = CONTROLLER.os.unlink
                inserted = {"value": False}

                def install(
                    real_unlink=real_unlink,
                    name=name,
                    directory_fd=directory_fd,
                    replacement_kind=replacement_kind,
                    outside=outside,
                    foreign=foreign,
                    inserted=inserted,
                ):
                    real_unlink(name, dir_fd=directory_fd)
                    self._install_cleanup_replacement(
                        replacement_kind,
                        name,
                        directory_fd,
                        outside,
                        foreign,
                    )
                    inserted["value"] = True

                def replacing_rename(
                    directory_fd,
                    source,
                    destination,
                    name=name,
                    real_rename=real_rename,
                    inserted=inserted,
                ):
                    if (
                        not inserted["value"]
                        and source == name
                        and str(destination).endswith(".removing")
                    ):
                        install()
                    return real_rename(directory_fd, source, destination)

                def replacing_unlink(
                    path, real_unlink=real_unlink, name=name, inserted=inserted, **kwargs
                ):
                    if not inserted["value"] and path == name:
                        install()
                    return real_unlink(path, **kwargs)

                try:
                    with (
                        mock.patch.object(
                            CONTROLLER.os,
                            "fsync",
                            side_effect=OSError("injected component fsync failure"),
                        ),
                        mock.patch.object(
                            CONTROLLER.STORAGE, "_rename_noreplace", side_effect=replacing_rename
                        ),
                        mock.patch.object(CONTROLLER.os, "unlink", side_effect=replacing_unlink),
                    ):
                        with self.assertRaisesRegex(ValueError, "persist|cleanup|uncertain"):
                            CONTROLLER._write_private_transaction_component(
                                directory_fd,
                                name,
                                exact,
                                "test write component",
                            )
                finally:
                    os.close(directory_fd)

                self.assertTrue(inserted)
                if replacement_kind == "regular":
                    self.assertEqual(selected.read_bytes(), foreign)
                else:
                    self.assertTrue(selected.is_symlink())
                    self.assertEqual(outside.read_bytes(), b"outside-safe")

    def test_stale_cleanup_late_replacements_preserve_intent_and_recover(self):
        for replacement_kind in ("regular", "symlink"):
            with self.subTest(replacement_kind=replacement_kind):
                self.enable_builtin_graph()
                draft = CONTROLLER.begin_refinement(
                    self.request(request=f"Late cleanup {replacement_kind}")
                )
                request = CONTROLLER.TraceRequest(
                    self.root,
                    draft.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
                )
                with mock.patch.object(
                    CONTROLLER,
                    "_bind_trace_receipt",
                    side_effect=ValueError("stop after receipt publication"),
                ):
                    with self.assertRaisesRegex(ValueError, "stop after receipt publication"):
                        CONTROLLER.trace_impact(request)

                stored = CONTROLLER.load_draft(self.root, draft.draft_id)
                intent = stored["graph_trace_intent"]
                receipt_path = (
                    self.root / ".requirements-impact-refiner/graph" / f"{draft.draft_id}.json"
                )
                (self.root / "desktop" / f"late_{replacement_kind}.py").write_text(
                    'FIELD = "profile.displayName"\n', encoding="utf-8"
                )
                outside = self.root / f"outside-{replacement_kind}"
                outside.write_bytes(b"outside-safe")
                foreign = b"foreign-late-receipt"
                real_unlink = CONTROLLER.os.unlink
                real_rename = CONTROLLER._rename_noreplace
                inserted = {"value": False}

                def insert_receipt_replacement(
                    directory_fd,
                    draft=draft,
                    replacement_kind=replacement_kind,
                    foreign=foreign,
                    outside=outside,
                    inserted=inserted,
                ):
                    inserted["value"] = True
                    try:
                        os.unlink(
                            f"{draft.draft_id}.json",
                            dir_fd=directory_fd,
                        )
                    except FileNotFoundError:
                        pass
                    if replacement_kind == "regular":
                        descriptor = os.open(
                            f"{draft.draft_id}.json",
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=directory_fd,
                        )
                        try:
                            os.write(descriptor, foreign)
                        finally:
                            os.close(descriptor)
                    else:
                        os.symlink(
                            outside,
                            f"{draft.draft_id}.json",
                            dir_fd=directory_fd,
                        )

                def insert_at_late_window(
                    path, real_unlink=real_unlink, inserted=inserted, **kwargs
                ):
                    if not inserted["value"] and str(path).endswith(".stale"):
                        insert_receipt_replacement(kwargs["dir_fd"])
                    return real_unlink(path, **kwargs)

                def insert_at_late_rename(
                    directory_fd, source, destination, real_rename=real_rename, inserted=inserted
                ):
                    result = real_rename(directory_fd, source, destination)
                    if (
                        not inserted["value"]
                        and str(source).endswith(".stale")
                        and str(destination).endswith(".removing")
                    ):
                        insert_receipt_replacement(directory_fd)
                    return result

                with (
                    mock.patch.object(CONTROLLER.os, "unlink", side_effect=insert_at_late_window),
                    mock.patch.object(
                        CONTROLLER.STORAGE, "_rename_noreplace", side_effect=insert_at_late_rename
                    ),
                ):
                    with self.assertRaisesRegex(
                        ValueError, "cleanup.*replacement|cleanup.*uncertain"
                    ):
                        CONTROLLER.trace_impact(request)

                self.assertTrue(inserted)
                after_race = CONTROLLER.load_draft(self.root, draft.draft_id)
                self.assertEqual(after_race["graph_trace_intent"], intent)
                self.assertNotIn("graph_receipt", after_race)
                if replacement_kind == "regular":
                    self.assertEqual(receipt_path.read_bytes(), foreign)
                else:
                    self.assertTrue(receipt_path.is_symlink())
                    self.assertEqual(outside.read_bytes(), b"outside-safe")

                receipt_path.unlink()
                with self.assertRaisesRegex(ValueError, "trace intent source inventory is stale"):
                    CONTROLLER.trace_impact(request)
                self.assertNotIn(
                    "graph_trace_intent",
                    CONTROLLER.load_draft(self.root, draft.draft_id),
                )
                fresh = CONTROLLER.trace_impact(request)
                self.assertTrue(
                    any(
                        node["location"] == f"desktop/late_{replacement_kind}.py"
                        for node in fresh.compact_graph["nodes"]
                    )
                )

    def test_stale_cleanup_guard_interruption_recovers_before_receipt_loading(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request(request="Interrupted stale cleanup guard"))
        request = CONTROLLER.TraceRequest(
            self.root,
            draft.draft_id,
            (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
        )
        with mock.patch.object(
            CONTROLLER,
            "_bind_trace_receipt",
            side_effect=ValueError("stop after receipt publication"),
        ):
            with self.assertRaisesRegex(ValueError, "stop after receipt publication"):
                CONTROLLER.trace_impact(request)
        intent = CONTROLLER.load_draft(self.root, draft.draft_id)["graph_trace_intent"]
        (self.root / "desktop/interrupted_cleanup.py").write_text(
            'FIELD = "profile.displayName"\n', encoding="utf-8"
        )
        real_unlink = CONTROLLER.os.unlink
        real_rename = CONTROLLER._rename_noreplace
        interrupted = False

        def interrupt_before_quarantine_cleanup(path, **kwargs):
            nonlocal interrupted
            if not interrupted and str(path).endswith(".stale"):
                interrupted = True
                raise SimulatedProcessInterruption("stale-cleanup-guard")
            return real_unlink(path, **kwargs)

        def interrupt_before_quarantine_rename(directory_fd, source, destination):
            nonlocal interrupted
            if (
                not interrupted
                and str(source).endswith(".stale")
                and str(destination).endswith(".removing")
            ):
                interrupted = True
                raise SimulatedProcessInterruption("stale-cleanup-guard")
            return real_rename(directory_fd, source, destination)

        with (
            mock.patch.object(
                CONTROLLER.os,
                "unlink",
                side_effect=interrupt_before_quarantine_cleanup,
            ),
            mock.patch.object(
                CONTROLLER.STORAGE,
                "_rename_noreplace",
                side_effect=interrupt_before_quarantine_rename,
            ),
        ):
            with self.assertRaises(SimulatedProcessInterruption):
                CONTROLLER.trace_impact(request)

        self.assertTrue(interrupted)
        self.assertEqual(
            CONTROLLER.load_draft(self.root, draft.draft_id)["graph_trace_intent"],
            intent,
        )
        with mock.patch.object(
            CONTROLLER.GRAPH_COORDINATOR,
            "trace_impact",
            side_effect=AssertionError("guard recovery must not republish"),
        ):
            with self.assertRaisesRegex(ValueError, "trace intent source inventory is stale"):
                CONTROLLER.trace_impact(request)
        self.assertNotIn(
            "graph_trace_intent",
            CONTROLLER.load_draft(self.root, draft.draft_id),
        )
        graph_dir = self.root / ".requirements-impact-refiner/graph"
        self.assertEqual(
            sorted(path.name for path in graph_dir.iterdir() if draft.draft_id in path.name),
            [],
        )
        fresh = CONTROLLER.trace_impact(request)
        self.assertTrue(
            any(
                node["location"] == "desktop/interrupted_cleanup.py"
                for node in fresh.compact_graph["nodes"]
            )
        )

    def test_trace_preserves_deadline_and_provider_failure_statuses(self):
        self.enable_builtin_graph()
        deadline_draft = CONTROLLER.begin_refinement(self.request())

        class FakeClock:
            current = 0.0

            def monotonic(self):
                return self.current

        clock = FakeClock()
        real_lock = CONTROLLER._report_lock

        @contextmanager
        def expire_after_lock(root, report_id, deadline=None):
            with real_lock(root, report_id, deadline=deadline):
                clock.current = 30.0
                yield

        with (
            mock.patch.object(CONTROLLER, "time", clock),
            mock.patch.object(CONTROLLER, "_report_lock", side_effect=expire_after_lock),
        ):
            deadline = CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    deadline_draft.draft_id,
                    (CONTROLLER.TraceSeed("authorization.profile", "api/profile.py"),),
                )
            )
        self.assertEqual(deadline.budget_status, "budget_exhausted")
        self.assertTrue(deadline.compact_graph["frontier"])

        config = json.loads(
            (self.root / ".requirements-impact-refiner.json").read_text(encoding="utf-8")
        )
        config["impact_graph"]["providers"] = ["scip"]
        (self.root / ".requirements-impact-refiner.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        provider_draft = CONTROLLER.begin_refinement(self.request(request="Provider fallback"))
        probe = CONTROLLER.GRAPH_COORDINATOR.ProviderProbe(
            "scip", "ready", "verified-provider", Path("/bin/scip")
        )

        class FailingAdapter:
            def probe(self, *args, **kwargs):
                raise ValueError("injected provider failure")

        with (
            mock.patch.object(
                CONTROLLER.GRAPH_COORDINATOR,
                "discover_providers",
                return_value=(probe,),
            ),
            mock.patch.object(CONTROLLER.GRAPH_COORDINATOR, "ADAPTERS", {"scip": FailingAdapter()}),
        ):
            provider = CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    provider_draft.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
                )
            )
        statuses = {row["name"]: row["status"] for row in provider.compact_graph["providers"]}
        self.assertEqual(statuses["scip"], "failed")
        self.assertIn("builtin", statuses)

    @unittest.skipIf(CONTROLLER.fcntl is None, "requires POSIX flock")
    def test_trace_lock_wait_uses_graph_deadline_and_released_lock_can_retry(self):
        self.enable_builtin_graph()
        config_path = self.root / ".requirements-impact-refiner.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["impact_graph"]["max_seconds"] = 1
        config["impact_graph"]["target_seconds"] = 1
        config_path.write_text(json.dumps(config), encoding="utf-8")
        draft = CONTROLLER.begin_refinement(self.request(request="Bound lock wait"))
        request = CONTROLLER.TraceRequest(
            self.root,
            draft.draft_id,
            (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
        )
        report_dir = self.root / ".requirements-impact-refiner/reports" / draft.report_id
        report_dir.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(report_dir / ".controller.lock", os.O_RDWR | os.O_CREAT, 0o600)
        CONTROLLER.fcntl.flock(descriptor, CONTROLLER.fcntl.LOCK_EX)

        def release():
            time.sleep(1.25)
            CONTROLLER.fcntl.flock(descriptor, CONTROLLER.fcntl.LOCK_UN)
            os.close(descriptor)

        releaser = threading.Thread(target=release)
        releaser.start()
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, "deadline exhausted waiting for controller lock"):
            CONTROLLER.trace_impact(request)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 1.2)
        releaser.join(timeout=2)

        recovered = CONTROLLER.trace_impact(request)
        self.assertRegex(recovered.receipt_id, r"^[0-9a-f]{32}$")

    def test_budget_exhausted_pre_scan_inventory_remains_finalizable_with_frontier(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request(request="Budget frontier"))

        class FakeClock:
            current = 0.0

            def monotonic(self):
                return self.current

        clock = FakeClock()
        real_lock = CONTROLLER._report_lock

        @contextmanager
        def expire_after_lock(root, report_id, deadline=None):
            with real_lock(root, report_id, deadline=deadline):
                clock.current = 30.0
                yield

        with (
            mock.patch.object(CONTROLLER, "time", clock),
            mock.patch.object(CONTROLLER, "_report_lock", side_effect=expire_after_lock),
        ):
            receipt = CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    draft.draft_id,
                    (CONTROLLER.TraceSeed("authorization.profile", "api/profile.py"),),
                )
            )
        self.assertEqual(receipt.budget_status, "budget_exhausted")
        self.assertTrue(receipt.compact_graph["frontier"])
        self.assertTrue(
            any(
                "source inventory incomplete" in row["reason"]
                for row in receipt.compact_graph["frontier"]
            )
        )
        binding = CONTROLLER.load_draft(self.root, draft.draft_id)["graph_receipt"]
        self.assertFalse(binding["source_inventory_complete"])
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = []
        analysis["impacts"][0]["coverage_rationale"] = (
            "Unknown because the shared graph deadline exhausted before scanning."
        )
        analysis["impacts"][0]["evidence_level"] = "unknown"

        result = CONTROLLER.finalize_refinement(self.finalize(draft, analysis, receipt))

        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        coverage = next(row for row in state["scope"] if row["boundary"] == "Impact graph coverage")
        self.assertIn("unknown frontiers", coverage["evidence"])
        self.assertIn("budget_exhausted", coverage["confidence"])

    def test_collection_limited_inventory_finalizes_with_frontier(self):
        self.enable_builtin_graph()
        bulk = self.root / "bulk"
        bulk.mkdir()
        for index in range(501):
            (bulk / f"source_{index:03d}.py").write_text(
                f'VALUE = "unrelated-{index}"\n', encoding="utf-8"
            )
        draft = CONTROLLER.begin_refinement(self.request(request="Limited inventory"))
        receipt = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                draft.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )
        binding = CONTROLLER.load_draft(self.root, draft.draft_id)["graph_receipt"]
        self.assertFalse(binding["source_inventory_complete"])
        self.assertEqual(binding["source_inventory_reason"], "collection-limit")
        self.assertNotEqual(receipt.budget_status, "closed")
        self.assertTrue(
            any(
                "source inventory incomplete" in row["reason"]
                for row in receipt.compact_graph["frontier"]
            )
        )
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = [
            row["key"] for row in receipt.compact_graph["paths"]
        ]
        if not analysis["impacts"][0]["graph_path_keys"]:
            analysis["impacts"][0]["coverage_rationale"] = (
                "Unknown because inventory collection reached its bound."
            )
        analysis["impacts"][0]["evidence_level"] = "unknown"

        result = CONTROLLER.finalize_refinement(self.finalize(draft, analysis, receipt))

        self.assertEqual(result.status, "published")

    def test_collection_limited_inventory_rejects_captured_source_mutation(self):
        self.enable_builtin_graph()
        bulk = self.root / "bulk"
        bulk.mkdir()
        for index in range(501):
            (bulk / f"source_{index:03d}.py").write_text(
                f'VALUE = "unrelated-{index}"\n', encoding="utf-8"
            )
        draft = CONTROLLER.begin_refinement(self.request(request="Limited mutation"))
        receipt = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                draft.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = [
            row["key"] for row in receipt.compact_graph["paths"]
        ]
        if not analysis["impacts"][0]["graph_path_keys"]:
            analysis["impacts"][0]["coverage_rationale"] = "Unknown bounded inventory."
        analysis["impacts"][0]["evidence_level"] = "unknown"
        (self.root / "api/profile.py").write_text('FIELD = "profile.changed"\n', encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "stale"):
            CONTROLLER.finalize_refinement(self.finalize(draft, analysis, receipt))

    def test_finalize_rejects_uncovered_high_risk_graph_node(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request())
        receipt = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                draft.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = []
        analysis["impacts"][0]["coverage_rationale"] = (
            "Unknown supplied evidence does not cover repository graph nodes."
        )
        analysis["impacts"][0]["evidence_level"] = "unknown"

        with self.assertRaisesRegex(ValueError, "uncovered high-risk graph node"):
            CONTROLLER.finalize_refinement(
                CONTROLLER.FinalizeRequest(
                    repo_root=self.root,
                    draft_id=draft.draft_id,
                    analysis=analysis,
                    graph_receipt_id=receipt.receipt_id,
                )
            )

    def test_finalize_accepts_supplied_only_zero_path_coverage_with_unrelated_license(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(
            self.request(request="Honor remote.contract supplied by the user.")
        )
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = []
        analysis["impacts"][0]["coverage_rationale"] = (
            "Supplied remote contract evidence remains unknown without a repository path."
        )
        analysis["impacts"][0]["evidence_level"] = "unknown"
        context = self.graph_context_with_high_risk_license([])

        with mock.patch.object(CONTROLLER, "_load_graph_context", return_value=context):
            result = CONTROLLER.finalize_refinement(
                CONTROLLER.FinalizeRequest(
                    repo_root=self.root,
                    draft_id=draft.draft_id,
                    analysis=analysis,
                    graph_receipt_id=context["receipt"]["receipt_id"],
                )
            )

        self.assertEqual(result.status, "published")

    def test_graph_coverage_rejects_unselected_high_risk_node_on_available_path(self):
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = []
        analysis["impacts"][0]["coverage_rationale"] = (
            "Supplied remote contract evidence remains unknown without a selected path."
        )
        analysis["impacts"][0]["evidence_level"] = "unknown"
        context = self.graph_context_with_high_risk_license(
            [
                {
                    "id": "PATH-001",
                    "nodes": ["NODE-001", "NODE-018"],
                    "edges": ["EDGE-001"],
                    "distance": 1,
                    "risk_domains": ["interfaces", "legal/policy"],
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "uncovered high-risk graph node NODE-018"):
            CONTROLLER._validate_graph_coverage(analysis, context)

    def test_finalize_accepts_valid_paths_and_injects_receipt_bound_scope(self):
        self.enable_builtin_graph()
        fixture_root = FIXTURES / "graph-project"
        for source in fixture_root.rglob("*"):
            if source.is_file():
                destination = self.root / source.relative_to(fixture_root)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
        draft = CONTROLLER.begin_refinement(self.request())
        receipt = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                draft.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = [
            row["key"] for row in receipt.compact_graph["paths"]
        ]
        analysis["impacts"][0]["evidence_level"] = "unknown"
        self.assertTrue(any(row["distance"] >= 3 for row in receipt.compact_graph["paths"]))

        result = CONTROLLER.finalize_refinement(self.finalize(draft, analysis, receipt))

        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        path_scope = next(
            row for row in state["scope"] if row["boundary"] == "Graph paths for IMP-001"
        )
        coverage = next(row for row in state["scope"] if row["boundary"] == "Impact graph coverage")
        self.assertIn("PATH-", path_scope["evidence"])
        self.assertIn("profile.displayName", path_scope["evidence"])
        self.assertIn("Impact scan:", coverage["evidence"])
        self.assertIn("builtin", coverage["evidence"])
        self.assertIn("nodes /", coverage["evidence"])
        self.assertIn(receipt.receipt_id, coverage["confidence"])
        self.assertIn(receipt.receipt_sha256, coverage["confidence"])
        self.assertIn("graph_paths", state)
        self.assertEqual(state["graph_paths"][0]["impact"], "IMP-001")
        self.assertTrue(state["graph_paths"][0]["paths"][0]["labels"])
        self.assertTrue(state["graph_paths"][0]["paths"][0]["providers"])
        self.assertIn("PATH-", result.display_text)
        metadata = json.loads(
            result.state_path.with_name("revision-0001.controller.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            metadata["graph_receipt"],
            {"receipt_id": receipt.receipt_id, "sha256": receipt.receipt_sha256},
        )

    def test_public_flow_preserves_structured_long_mixed_provider_paths(self):
        self.enable_builtin_graph()
        (self.root / "events").mkdir()
        (self.root / "events/profile.py").write_text("EVENT = True\n", encoding="utf-8")
        config = json.loads((self.root / ".requirements-impact-refiner.json").read_text())
        config["impact_graph"]["providers"] = ["codegraph", "scip"]
        (self.root / ".requirements-impact-refiner.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        draft = CONTROLLER.begin_refinement(self.request(audience_override="technical"))
        special_label = "<profile || `wire|field`> " + "long-label " * 40

        def fake_trace(root, graph_draft, seeds, graph_settings, **kwargs):
            settings = CONTROLLER.GRAPH_COORDINATOR._settings(graph_settings)
            providers = (
                CONTROLLER.GRAPH.ProviderStatus("codegraph", "ready", "verified-provider"),
                CONTROLLER.GRAPH.ProviderStatus("scip", "ready", "verified-provider"),
            )
            request_sha = CONTROLLER.GRAPH_COORDINATOR._request_sha256(graph_draft, seeds, settings)
            receipt_id = CONTROLLER.GRAPH_COORDINATOR._trace_identity(
                root, graph_draft["draft_id"], request_sha, seeds, settings, providers
            )

            def digest(path):
                return hashlib.sha256((root / path).read_bytes()).hexdigest()

            receipt = CONTROLLER.GRAPH.GraphReceipt(
                receipt_id,
                graph_draft["draft_id"],
                hashlib.sha256(str(root).encode()).hexdigest(),
                request_sha,
                settings,
                providers,
                (
                    CONTROLLER.GRAPH.GraphNode(
                        "NODE-001",
                        "api_field",
                        special_label,
                        "api/profile.py",
                        "codegraph",
                        "verified-provider",
                        digest("api/profile.py"),
                        ("interfaces",),
                    ),
                    CONTROLLER.GRAPH.GraphNode(
                        "NODE-002",
                        "cache",
                        "desktop cache",
                        "desktop/profile_cache.ts",
                        "scip",
                        "verified-provider",
                        digest("desktop/profile_cache.ts"),
                        ("data",),
                    ),
                    CONTROLLER.GRAPH.GraphNode(
                        "NODE-003",
                        "event",
                        "event consumer",
                        "events/profile.py",
                        "codegraph",
                        "verified-provider",
                        digest("events/profile.py"),
                        ("operations",),
                    ),
                ),
                (
                    CONTROLLER.GRAPH.GraphEdge(
                        "EDGE-001",
                        "NODE-001",
                        "NODE-002",
                        "references",
                        "desktop/profile_cache.ts",
                        "wire",
                        "verified-provider",
                        "scip",
                        digest("desktop/profile_cache.ts"),
                    ),
                    CONTROLLER.GRAPH.GraphEdge(
                        "EDGE-002",
                        "NODE-001",
                        "NODE-003",
                        "publishes",
                        "events/profile.py",
                        "wire",
                        "verified-provider",
                        "codegraph",
                        digest("events/profile.py"),
                    ),
                ),
                (
                    CONTROLLER.GRAPH.GraphPath(
                        "PATH-001",
                        ("NODE-001", "NODE-002"),
                        ("EDGE-001",),
                        1,
                        ("interfaces", "data"),
                    ),
                    CONTROLLER.GRAPH.GraphPath(
                        "PATH-002",
                        ("NODE-001", "NODE-003"),
                        ("EDGE-002",),
                        1,
                        ("interfaces", "operations"),
                    ),
                ),
                (),
                {"total": 8400},
                "closed",
                {"status": "miss", "key": "0" * 64, "invalidated_nodes": []},
            )
            published = CONTROLLER.GRAPH_COORDINATOR.CACHE.publish(
                root, receipt, kwargs["source_inventory"].digests
            )
            receipt = replace(
                receipt, cache={"status": "miss", "key": published.key, "invalidated_nodes": []}
            )
            CONTROLLER.GRAPH_COORDINATOR._persist_receipt(root, receipt)
            return receipt

        with mock.patch.object(
            CONTROLLER.GRAPH_COORDINATOR, "trace_impact", side_effect=fake_trace
        ):
            receipt = CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    draft.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
                )
            )
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = ["PATH-001", "PATH-002"]
        analysis["impacts"][0]["evidence_level"] = "unknown"
        result = CONTROLLER.finalize_refinement(self.finalize(draft, analysis, receipt))
        reloaded_state, reload_errors = CONTROLLER.compact_state.load_state_bytes(
            result.state_path.read_bytes()
        )
        self.assertEqual(reload_errors, [])
        self.assertIsNotNone(reloaded_state)
        expected_first_path = {
            "id": "PATH-001",
            "labels": [special_label, "desktop cache"],
            "providers": ["codegraph", "scip"],
            "confidence": "verified-provider",
            "locations": ["api/profile.py", "desktop/profile_cache.ts"],
        }
        expected_second_path = {
            "id": "PATH-002",
            "labels": [special_label, "event consumer"],
            "providers": ["codegraph"],
            "confidence": "verified-provider",
            "locations": ["api/profile.py", "events/profile.py"],
        }
        self.assertEqual(
            reloaded_state["graph_paths"],
            [
                {
                    "impact": "IMP-001",
                    "paths": [expected_first_path, expected_second_path],
                }
            ],
        )
        self.assertEqual(
            reloaded_state["graph_paths"][0]["paths"][1],
            expected_second_path,
        )

        rendered_reload = CONTROLLER.impact_renderer.render_compact(reloaded_state).removesuffix(
            "\n"
        )
        self.assertEqual(rendered_reload, result.display_text)
        displayed_path_lines = [
            line for line in rendered_reload.splitlines() if line.startswith("- `IMP-001`:")
        ]
        self.assertEqual(len(displayed_path_lines), 1)
        displayed_path = displayed_path_lines[0]
        self.assertIn(
            "PATH-001: &lt;profile &#124;&#124; &#96;wire&#124;field&#96;&gt;",
            displayed_path,
        )
        self.assertIn(
            "provider codegraph + scip; confidence verified-provider; "
            "location api/profile.py + desktop/profile_cache.ts",
            displayed_path,
        )
        self.assertNotIn("<profile", rendered_reload)
        self.assertNotIn("`wire|field`", rendered_reload)
        self.assertNotRegex(rendered_reload, r"<[^>\n]+>")
        for line in rendered_reload.splitlines():
            if line.startswith("|"):
                self.assertEqual(line.count("|"), 5, line)
        self.assertLessEqual(len(rendered_reload.split()), 450)

    def test_finalize_accepts_supplied_only_unknown_with_rationale_and_frontier(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(
            self.request(request="Honor remote.contract supplied by the user.")
        )
        receipt = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                draft.draft_id,
                (CONTROLLER.TraceSeed("remote.contract", None),),
            )
        )
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = []
        analysis["impacts"][0]["coverage_rationale"] = (
            "Supplied-only contract evidence remains unknown until a repository source is mounted."
        )
        analysis["impacts"][0]["evidence_level"] = "unknown"

        result = CONTROLLER.finalize_refinement(self.finalize(draft, analysis, receipt))

        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        path_scope = next(
            row for row in state["scope"] if row["boundary"] == "Graph paths for IMP-001"
        )
        coverage = next(row for row in state["scope"] if row["boundary"] == "Impact graph coverage")
        self.assertIn("Supplied-only", path_scope["evidence"])
        self.assertIn("unknown frontiers", coverage["evidence"])
        self.assertIn("FRONTIER-", coverage["confidence"])

    def test_finalize_rejects_invalid_and_unknown_graph_path_keys(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request())
        receipt = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                draft.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["evidence_level"] = "unknown"
        for key, message in (("../PATH-001", "invalid"), ("PATH-999", "unknown")):
            with self.subTest(key=key):
                analysis["impacts"][0]["graph_path_keys"] = [key]
                with self.assertRaisesRegex(ValueError, f"{message} graph path key"):
                    CONTROLLER.finalize_refinement(self.finalize(draft, analysis, receipt))

    def test_finalize_rejects_confidence_upgrade_and_lexical_only_resolution(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request())
        receipt = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                draft.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = [
            row["key"] for row in receipt.compact_graph["paths"]
        ]
        analysis["impacts"][0]["evidence_level"] = "verified"
        with self.assertRaisesRegex(ValueError, "upgrades graph path evidence"):
            CONTROLLER.finalize_refinement(self.finalize(draft, analysis, receipt))

        analysis["impacts"][0]["evidence_level"] = "unknown"
        analysis["impacts"][0]["state"] = "resolved"
        with self.assertRaisesRegex(ValueError, "solely on lexical"):
            CONTROLLER.finalize_refinement(self.finalize(draft, analysis, receipt))

    def test_finalize_rejects_missing_mismatched_tampered_and_stale_receipts(self):
        self.enable_builtin_graph()
        missing = CONTROLLER.begin_refinement(self.request(request="Missing receipt"))
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = []
        analysis["impacts"][0]["coverage_rationale"] = "Unknown until traced."
        analysis["impacts"][0]["evidence_level"] = "unknown"
        with self.assertRaisesRegex(ValueError, "graph receipt is required"):
            CONTROLLER.finalize_refinement(self.finalize(missing, analysis))

        mismatch = CONTROLLER.begin_refinement(self.request(request="Mismatch"))
        CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                mismatch.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )
        with self.assertRaisesRegex(ValueError, "does not match selected"):
            CONTROLLER.finalize_refinement(
                CONTROLLER.FinalizeRequest(self.root, mismatch.draft_id, analysis, "0" * 32)
            )

        tampered = CONTROLLER.begin_refinement(self.request(request="Tampered"))
        tampered_receipt = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                tampered.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )
        tampered_receipt.receipt_path.write_bytes(
            tampered_receipt.receipt_path.read_bytes() + b"\n"
        )
        with self.assertRaisesRegex(ValueError, "canonical|tampered"):
            CONTROLLER.finalize_refinement(self.finalize(tampered, analysis, tampered_receipt))

        stale = CONTROLLER.begin_refinement(self.request(request="Stale"))
        stale_receipt = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                stale.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )
        (self.root / "api/profile.py").write_text('FIELD = "profile.renamed"\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale"):
            CONTROLLER.finalize_refinement(self.finalize(stale, analysis, stale_receipt))

    def test_finalize_rejects_new_relevant_source_outside_receipt_inventory(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request(request="Inventory drift"))
        receipt = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                draft.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = [
            row["key"] for row in receipt.compact_graph["paths"]
        ]
        analysis["impacts"][0]["evidence_level"] = "unknown"
        (self.root / "desktop/new_consumer.py").write_text(
            'FIELD = "profile.displayName"\n', encoding="utf-8"
        )

        with self.assertRaisesRegex(ValueError, "source inventory is stale"):
            CONTROLLER.finalize_refinement(self.finalize(draft, analysis, receipt))

        self.assertFalse(
            (self.root / ".requirements-impact-refiner/reports/RPT-001/current.json").exists()
        )

    def test_finalize_rejects_inventory_digest_rebound_away_from_receipt_cache(self):
        self.enable_builtin_graph()
        draft = CONTROLLER.begin_refinement(self.request(request="Rebound inventory"))
        receipt = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                draft.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = [
            row["key"] for row in receipt.compact_graph["paths"]
        ]
        analysis["impacts"][0]["evidence_level"] = "unknown"
        (self.root / "desktop/new_consumer.py").write_text(
            'FIELD = "profile.displayName"\n', encoding="utf-8"
        )
        current = CONTROLLER.GRAPH_COORDINATOR._collect_source_digests(
            self.root,
            CONTROLLER.GRAPH_COORDINATOR.Deadline(CONTROLLER.time, 30),
        )
        rebound = hashlib.sha256(
            json.dumps(
                dict(current.digests), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        stored = CONTROLLER.load_draft(self.root, draft.draft_id)
        stored["graph_receipt"]["source_inventory_sha256"] = rebound
        CONTROLLER._replace_private_draft(self.root, draft.draft_id, stored)

        with self.assertRaisesRegex(
            ValueError, "trace intent request|inventory cache does not match binding"
        ):
            CONTROLLER.finalize_refinement(self.finalize(draft, analysis, receipt))

    def test_finalize_rejects_deleted_and_renamed_unmapped_inventory_sources(self):
        self.enable_builtin_graph()
        support = self.root / "desktop/support.py"
        support.write_text("SUPPORT = True\n", encoding="utf-8")

        def traced(request_text):
            draft = CONTROLLER.begin_refinement(self.request(request=request_text))
            receipt = CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    draft.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
                )
            )
            analysis = self.fixture("controller-analysis-pre-decision.json")
            analysis["impacts"][0]["graph_path_keys"] = [
                row["key"] for row in receipt.compact_graph["paths"]
            ]
            analysis["impacts"][0]["evidence_level"] = "unknown"
            return draft, receipt, analysis

        deleted_draft, deleted_receipt, deleted_analysis = traced("Deleted inventory")
        support.unlink()
        with self.assertRaisesRegex(ValueError, "source inventory is stale"):
            CONTROLLER.finalize_refinement(
                self.finalize(deleted_draft, deleted_analysis, deleted_receipt)
            )

        support.write_text("SUPPORT = True\n", encoding="utf-8")
        renamed_draft, renamed_receipt, renamed_analysis = traced("Renamed inventory")
        support.rename(self.root / "desktop/support_renamed.py")
        with self.assertRaisesRegex(ValueError, "source inventory is stale"):
            CONTROLLER.finalize_refinement(
                self.finalize(renamed_draft, renamed_analysis, renamed_receipt)
            )

    def test_finalize_recomputes_exact_draft_request_and_receipt_identities(self):
        self.enable_builtin_graph()
        request_draft = CONTROLLER.begin_refinement(self.request(request="Exact request"))
        request_receipt = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                request_draft.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = [
            row["key"] for row in request_receipt.compact_graph["paths"]
        ]
        analysis["impacts"][0]["evidence_level"] = "unknown"
        stored = CONTROLLER.load_draft(self.root, request_draft.draft_id)
        stored["request"] = "Replaced request"
        CONTROLLER._replace_private_draft(self.root, request_draft.draft_id, stored)
        with self.assertRaisesRegex(ValueError, "identity"):
            CONTROLLER.finalize_refinement(self.finalize(request_draft, analysis, request_receipt))

        forged_draft = CONTROLLER.begin_refinement(self.request(request="Forged ID"))
        forged_receipt = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                forged_draft.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )
        receipt_value = json.loads(forged_receipt.receipt_path.read_text(encoding="utf-8"))
        receipt_value["receipt_id"] = "0" * 32
        forged_payload = CONTROLLER.GRAPH.canonical_receipt_bytes(receipt_value)
        forged_receipt.receipt_path.write_bytes(forged_payload)
        forged_binding = CONTROLLER.load_draft(self.root, forged_draft.draft_id)
        forged_binding["graph_receipt"]["receipt_id"] = "0" * 32
        forged_binding["graph_receipt"]["sha256"] = CONTROLLER.hashlib.sha256(
            forged_payload
        ).hexdigest()
        CONTROLLER._replace_private_draft(self.root, forged_draft.draft_id, forged_binding)
        with self.assertRaisesRegex(ValueError, "identity"):
            CONTROLLER.finalize_refinement(
                CONTROLLER.FinalizeRequest(self.root, forged_draft.draft_id, analysis, "0" * 32)
            )

    def test_graph_disabled_finalize_remains_backward_compatible(self):
        draft = CONTROLLER.begin_refinement(self.request())

        result = CONTROLLER.finalize_refinement(
            self.finalize(draft, self.fixture("controller-analysis-pre-decision.json"))
        )

        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        self.assertFalse(state["settings"]["impact_graph"]["enabled"])
        self.assertFalse(any(row["boundary"] == "Impact graph coverage" for row in state["scope"]))

    def test_begin_creates_repository_bound_private_draft(self):
        result = CONTROLLER.begin_refinement(self.request())

        self.assertRegex(result.draft_id, r"^[0-9a-f]{32}$")
        self.assertEqual(result.report_id, "RPT-001")
        self.assertEqual(result.revision, 1)
        self.assertEqual(result.previous_sha256, "none")
        self.assertEqual(result.settings["delivery"], "compact")
        self.assertEqual(result.draft_path.stat().st_mode & 0o777, 0o600)
        stored = json.loads(result.draft_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["repo_root"], str(self.root.resolve()))
        self.assertFalse(stored["consumed"])

    def test_begin_allocates_new_report_for_unrelated_requirement(self):
        state = self.fixture("compact-state-post-decision.json")
        CONTROLLER.report_store.publish_revision(self.root, CONTROLLER._canonical_bytes(state))

        result = CONTROLLER.begin_refinement(
            self.request(request="Introduce an unrelated audit export requirement.")
        )

        self.assertEqual(result.report_id, "RPT-002")
        self.assertEqual(result.revision, 1)
        self.assertEqual(result.previous_sha256, "none")
        self.assertIsNone(result.prior_state)
        self.assertIsNone(result.prior_key_map)

    def test_begin_migrates_valid_precontroller_report_lineage(self):
        state = self.fixture("compact-state-pre-decision.json")
        CONTROLLER.report_store.publish_revision(self.root, CONTROLLER._canonical_bytes(state))

        result = CONTROLLER.begin_refinement(
            self.request(request=state["original_requirement"]["request"])
        )

        self.assertEqual(result.report_id, "RPT-001")
        self.assertEqual(result.revision, 2)
        self.assertEqual(
            result.prior_key_map["impacts"],
            {"legacy-imp-001": "IMP-001"},
        )

    def test_begin_reads_public_v05_schema1_completed_lineage_key_map(self):
        state = self.fixture("compact-state-pre-decision.json")
        published = CONTROLLER.report_store.publish_revision(
            self.root, CONTROLLER._canonical_bytes(state)
        )
        key_map = CONTROLLER._legacy_key_map(state)
        key_map["impacts"] = {"public-v05-impact": "IMP-001"}
        metadata = {
            "schema_version": 1,
            "draft_id": "a" * 32,
            "report_id": "RPT-001",
            "revision": 1,
            "state_sha256": CONTROLLER.hashlib.sha256(
                published.state_path.read_bytes()
            ).hexdigest(),
            "key_map": key_map,
        }
        metadata_path = published.state_path.with_name("revision-0001.controller.json")
        metadata_path.write_bytes(CONTROLLER._canonical_bytes(metadata))
        metadata_path.chmod(0o600)

        result = CONTROLLER.begin_refinement(
            self.request(request=state["original_requirement"]["request"])
        )

        self.assertEqual(result.revision, 2)
        self.assertEqual(result.prior_key_map["impacts"], {"public-v05-impact": "IMP-001"})

    def test_begin_creates_private_draft_without_post_creation_chmod_window(self):
        with mock.patch.object(
            CONTROLLER.os,
            "chmod",
            side_effect=AssertionError("post-create chmod"),
        ):
            result = CONTROLLER.begin_refinement(self.request())

        self.assertEqual(result.draft_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result.draft_path.parent.stat().st_mode & 0o777, 0o700)

    def test_invalid_graph_configuration_falls_back_and_finalizes_with_warning(self):
        (self.root / ".requirements-impact-refiner.json").write_text(
            '{"impact_graph":{"max_seconds":31}}\n', encoding="utf-8"
        )
        (self.root / "api").mkdir()
        (self.root / "desktop").mkdir()
        (self.root / "api/profile.py").write_text(
            'FIELD = "profile.displayName"\n', encoding="utf-8"
        )
        (self.root / "desktop/profile_cache.ts").write_text(
            'const key = "profile.displayName";\n', encoding="utf-8"
        )
        draft = CONTROLLER.begin_refinement(self.request())
        with mock.patch.object(CONTROLLER.GRAPH_COORDINATOR, "discover_providers", return_value=()):
            receipt = CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    draft.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
                )
            )
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = [
            row["key"] for row in receipt.compact_graph["paths"]
        ]
        analysis["impacts"][0]["evidence_level"] = "unknown"
        result = CONTROLLER.finalize_refinement(self.finalize(draft, analysis, receipt))

        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["settings"]["impact_graph"]["max_seconds"], 30)
        self.assertIn("invalid impact_graph configuration", state["settings"]["warnings"][0])

    def test_begin_rejects_oversized_request_and_non_directory_root(self):
        with self.assertRaisesRegex(ValueError, "256 KiB"):
            CONTROLLER.begin_refinement(self.request(request="x" * (256 * 1024 + 1)))
        file_root = self.root / "file"
        file_root.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "repository root"):
            CONTROLLER.begin_refinement(self.request(repo_root=file_root))

    def test_predecision_finalize_allocates_ids_and_embeds_question(self):
        draft = CONTROLLER.begin_refinement(self.request())
        result = CONTROLLER.finalize_refinement(
            self.finalize(draft, self.fixture("controller-analysis-pre-decision.json"))
        )

        self.assertEqual(result.status, "published")
        self.assertIn("IMP-001", result.display_text)
        self.assertIn("Decision needed", result.display_text)
        self.assertEqual(result.revision, 1)
        self.assertTrue(result.state_path.is_file())
        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["impacts"][0]["id"], "IMP-001")
        self.assertEqual(state["criteria"][0]["id"], "AC-001")
        self.assertEqual(state["current_behavior"][0]["id"], "INV-001")

    def test_superpowers_adapter_gets_exact_controller_owned_handoff_marker(self):
        draft = CONTROLLER.begin_refinement(self.request(adapter="superpowers"))

        result = CONTROLLER.finalize_refinement(
            self.finalize(draft, self.fixture("controller-analysis-pre-decision.json"))
        )
        state = json.loads(result.state_path.read_text(encoding="utf-8"))

        self.assertEqual(
            state["handoff"]["workflow"],
            "superpowers:after-approved-brainstorming;impact-refinement;manual-handoff-before-writing-plans",
        )

    def test_blocked_impact_forces_not_ready_before_validation(self):
        draft = CONTROLLER.begin_refinement(self.request())
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["workflow"] = "Ready for planning"

        result = CONTROLLER.finalize_refinement(self.finalize(draft, analysis))
        state = json.loads(result.state_path.read_text(encoding="utf-8"))

        self.assertEqual(state["handoff"]["workflow"], "Not ready")

    def test_postdecision_finalize_allocates_decision_and_consumes_draft(self):
        draft = CONTROLLER.begin_refinement(self.request())
        result = CONTROLLER.finalize_refinement(
            self.finalize(draft, self.fixture("controller-analysis-post-decision.json"))
        )

        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["decisions"][0]["id"], "DEC-001")
        self.assertEqual(state["impacts"][0]["decisions"], ["DEC-001"])
        stored = json.loads(draft.draft_path.read_text(encoding="utf-8"))
        self.assertTrue(stored["consumed"])
        with self.assertRaisesRegex(ValueError, "consumed"):
            CONTROLLER.finalize_refinement(
                self.finalize(draft, self.fixture("controller-analysis-post-decision.json"))
            )

    def test_finalize_retry_completes_consumption_after_post_publish_failure(self):
        draft = CONTROLLER.begin_refinement(self.request())
        request = self.finalize(draft, self.fixture("controller-analysis-pre-decision.json"))
        real_consume = CONTROLLER._consume
        with mock.patch.object(
            CONTROLLER,
            "_consume",
            side_effect=ValueError("injected consume failure"),
        ):
            with self.assertRaisesRegex(ValueError, "injected consume failure"):
                CONTROLLER.finalize_refinement(request)

        with mock.patch.object(CONTROLLER, "_consume", wraps=real_consume) as consume:
            result = CONTROLLER.finalize_refinement(request)

        self.assertEqual((result.report_id, result.revision), ("RPT-001", 1))
        self.assertEqual(consume.call_count, 1)
        self.assertTrue(CONTROLLER.load_draft(self.root, draft.draft_id)["consumed"])

    def test_controller_metadata_is_never_exposed_partially_and_retry_succeeds(self):
        draft = CONTROLLER.begin_refinement(self.request())
        request = self.finalize(draft, self.fixture("controller-analysis-pre-decision.json"))
        with mock.patch.object(CONTROLLER.os, "link", side_effect=OSError("injected link failure")):
            with self.assertRaisesRegex(ValueError, "cannot write controller lineage"):
                CONTROLLER.finalize_refinement(request)
        metadata = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        self.assertFalse(metadata.exists())

        result = CONTROLLER.finalize_refinement(request)

        self.assertEqual(result.revision, 1)
        self.assertTrue(metadata.is_file())

    def test_same_draft_can_replace_unpublished_controller_metadata(self):
        draft = {
            "draft_id": "0" * 32,
            "report_id": "RPT-001",
            "revision": 1,
        }
        CONTROLLER._write_controller_metadata(
            self.root, draft, b"first\n", {"impacts": {"a": "IMP-001"}}
        )

        CONTROLLER._write_controller_metadata(
            self.root, draft, b"corrected\n", {"impacts": {"a": "IMP-001"}}
        )

        path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            stored["state_sha256"],
            CONTROLLER.hashlib.sha256(b"corrected\n").hexdigest(),
        )

    def test_finalize_calculates_delta_and_rejects_model_ids(self):
        draft = CONTROLLER.begin_refinement(self.request())
        analysis = self.fixture("controller-analysis-post-decision.json")
        analysis["impacts"][0]["id"] = "IMP-999"

        with self.assertRaisesRegex(ValueError, "unknown impact key id"):
            CONTROLLER.finalize_refinement(self.finalize(draft, analysis))

    def test_finalize_rejects_wrong_root_unknown_draft_and_oversized_input(self):
        draft = CONTROLLER.begin_refinement(self.request())
        other = self.root / "other"
        other.mkdir()
        request = CONTROLLER.FinalizeRequest(
            repo_root=other,
            draft_id=draft.draft_id,
            analysis=self.fixture("controller-analysis-pre-decision.json"),
        )
        with self.assertRaisesRegex(ValueError, "draft"):
            CONTROLLER.finalize_refinement(request)
        with self.assertRaisesRegex(ValueError, "draft ID"):
            CONTROLLER.load_draft(self.root, "not-a-draft")
        huge = self.fixture("controller-analysis-pre-decision.json")
        huge["refined_requirement"] = "x" * (2 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "2 MiB"):
            CONTROLLER.finalize_refinement(self.finalize(draft, huge))

    def test_finalize_rejects_schema_collection_overflow(self):
        draft = CONTROLLER.begin_refinement(self.request())
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["scope"] = analysis["scope"] * 129

        with self.assertRaisesRegex(ValueError, "scope has too many rows"):
            CONTROLLER.finalize_refinement(self.finalize(draft, analysis))

    def test_revision_preserves_ids_hashes_predecessor_and_calculates_reopened(self):
        first_draft = CONTROLLER.begin_refinement(self.request())
        first = CONTROLLER.finalize_refinement(
            self.finalize(
                first_draft,
                self.fixture("controller-analysis-post-decision.json"),
            )
        )
        second_draft = CONTROLLER.begin_refinement(self.request())
        analysis = self.fixture("controller-analysis-post-decision.json")
        analysis["impacts"][0]["state"] = "detected"
        analysis["impacts"][0]["decision_keys"] = []
        analysis["decisions"][0]["accepted_impact_keys"] = []

        second = CONTROLLER.finalize_refinement(self.finalize(second_draft, analysis))
        state = json.loads(second.state_path.read_text(encoding="utf-8"))

        self.assertEqual(second_draft.report_id, "RPT-001")
        self.assertEqual(second_draft.revision, 2)
        self.assertEqual(second_draft.previous_sha256, first.markdown_sha256)
        self.assertEqual(state["impacts"][0]["id"], "IMP-001")
        self.assertEqual(state["delta"]["reopened"], ["IMP-001"])
        self.assertEqual(state["delta"]["new"], [])

    def test_revision_rejects_silent_impact_key_deletion(self):
        first_draft = CONTROLLER.begin_refinement(self.request())
        CONTROLLER.finalize_refinement(
            self.finalize(
                first_draft,
                self.fixture("controller-analysis-post-decision.json"),
            )
        )
        second_draft = CONTROLLER.begin_refinement(self.request())
        analysis = self.fixture("controller-analysis-post-decision.json")
        analysis["impacts"] = []

        with self.assertRaisesRegex(ValueError, "impact key disappeared"):
            CONTROLLER.finalize_refinement(self.finalize(second_draft, analysis))

    def test_predecision_revision_freezes_prior_decision_link_in_history(self):
        first_draft = CONTROLLER.begin_refinement(self.request())
        CONTROLLER.finalize_refinement(
            self.finalize(
                first_draft,
                self.fixture("controller-analysis-post-decision.json"),
            )
        )
        second_draft = CONTROLLER.begin_refinement(self.request())
        analysis = self.fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["key"] = "member-scope"
        analysis["criteria"][0]["impact_key"] = "member-scope"
        analysis["decision_needed"]["options"][0]["impact_keys"] = ["member-scope"]
        analysis["decision_needed"]["options"][1]["impact_keys"] = ["member-scope"]

        second = CONTROLLER.finalize_refinement(self.finalize(second_draft, analysis))
        state = json.loads(second.state_path.read_text(encoding="utf-8"))

        self.assertEqual(state["report"]["phase"], "pre-decision")
        self.assertEqual(state["history"][0]["decision"], None)
        self.assertIn("prior immutable revision", state["history"][0]["summary"])
        self.assertNotIn("DEC-001", state["history"][0]["summary"])
        self.assertEqual(state["delta"]["reopened"], ["IMP-001"])


if __name__ == "__main__":
    unittest.main()
