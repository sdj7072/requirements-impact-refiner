from __future__ import annotations

import importlib.util
import inspect
import json
import subprocess
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

    def enable_graph(self):
        (self.root / ".requirements-impact-refiner.json").write_text(
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
        (self.root / "api").mkdir()
        (self.root / "api" / "profile.py").write_text(
            'FIELD = "profile.displayName"\n', encoding="utf-8"
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

    def test_full_finalize_defaults_to_table_view_and_keeps_canonical_artifact(self):
        finalize = self.finalize()
        draft = self.begin("모든 프로젝트의 편집 권한 영향을 검토해줘.")

        result = finalize.finalize_refinement(self.request(draft))

        self.assertEqual(result.delivery, "full")
        persisted = result.markdown_path.read_text(encoding="utf-8")
        self.assertTrue(result.display_text.startswith("# Requirements Impact Report\n"))
        self.assertTrue(any(line.startswith("|") for line in result.display_text.splitlines()))
        self.assertEqual(result.display_text, persisted.removesuffix("\n"))

    def test_full_finalize_explicit_narrative_preserves_localized_reader_view(self):
        (self.root / ".requirements-impact-refiner.json").write_text(
            json.dumps(
                {
                    "report_layout": "narrative",
                    "impact_graph": {
                        "enabled": False,
                        "max_seconds": 30,
                        "target_seconds": 10,
                        "providers": ["auto"],
                        "install_policy": "never",
                        "deep": False,
                    },
                }
            ),
            encoding="utf-8",
        )
        finalize = self.finalize()
        draft = self.begin("모든 프로젝트의 편집 권한 영향을 검토해줘.")

        result = finalize.finalize_refinement(self.request(draft))

        self.assertTrue(result.display_text.startswith("# 요구사항 영향 보고서\n"))
        self.assertFalse(any(line.startswith("|") for line in result.display_text.splitlines()))
        self.assertTrue(result.markdown_path.read_text().startswith("# Requirements Impact Report"))

    def test_graph_disabled_finalize_rejects_receipt_without_publication_or_consumption(self):
        finalize = self.finalize()
        draft = self.begin("Reject a graph receipt when graph analysis is disabled.")
        request = finalize.FinalizeRequest(
            self.root,
            draft.draft_id,
            fixture("controller-analysis-pre-decision.json"),
            "9" * 32,
        )

        with self.assertRaisesRegex(
            ValueError,
            "^graph_receipt_id is not allowed when impact graph is disabled$",
        ):
            finalize.finalize_refinement(request)

        self.assertIsNone(finalize.REPORT_STORE.load_current(self.root, draft.report_id))
        self.assertFalse(finalize.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

    def test_finalize_rejects_malformed_draft_requirement_before_publication_or_consumption(self):
        finalize = self.finalize()
        draft = self.begin("Reject malformed persisted requirement identity.")
        request = self.request(draft)
        runtime = dict(finalize.default_runtime())
        stored = runtime["load_draft"](self.root, draft.draft_id)
        state, key_map = runtime["build_state"](stored, request.analysis, None)
        malformed = dict(stored)
        malformed["request"] = 7
        runtime["load_draft"] = lambda *_args: dict(malformed)
        runtime["build_state"] = lambda *_args: (state, key_map)

        with self.assertRaisesRegex(ValueError, "^draft requirement identity is invalid$"):
            finalize.finalize_refinement(request, _runtime=runtime)

        self.assertIsNone(finalize.REPORT_STORE.load_current(self.root, draft.report_id))
        self.assertFalse(finalize.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

    def test_facade_signature_result_type_and_fault_injection_remain_stable(self):
        finalize = self.finalize()
        self.assertEqual(
            tuple(inspect.signature(CONTROLLER.finalize_refinement).parameters), ("request",)
        )
        self.assertIs(CONTROLLER.FinalizeResult, CONTROLLER.CONTRACTS.FinalizeResult)
        self.assertEqual(Path(CONTROLLER.FINALIZE.__file__).resolve(), FINALIZE_PATH.resolve())
        self.assertIs(CONTROLLER._build_state, CONTROLLER.LINEAGE.build_state)
        defaults = finalize.default_runtime()
        self.assertIs(defaults["publish_revision"], finalize.REPORT_STORE.publish_revision)
        self.assertIs(defaults["consume_draft"], finalize.STORAGE.consume_draft)
        with self.assertRaises(TypeError):
            defaults["consume_draft"] = lambda *args, **kwargs: None

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

    def test_direct_promoted_scan_finalize_executes_complete_local_fast_scan_graph(self):
        finalize = self.finalize()
        self.enable_graph()
        scan = CONTROLLER.scan_impact(
            CONTROLLER.ScanRequest(self.root, "Rename profile.displayName", (), "balanced")
        )
        draft = CONTROLLER.begin_refinement(
            CONTROLLER.BeginRequest(
                self.root,
                "Rename profile.displayName",
                (),
                "generic",
                scan_id=scan.scan_id,
            )
        )
        analysis = fixture("controller-analysis-pre-decision.json")
        analysis["impacts"][0]["graph_path_keys"] = [row["id"] for row in scan.paths]
        if not analysis["impacts"][0]["graph_path_keys"]:
            analysis["impacts"][0]["coverage_rationale"] = (
                "Fast Scan found no closed repository path."
            )
        analysis["impacts"][0]["evidence_level"] = "unknown"

        result = finalize.finalize_refinement(
            finalize.FinalizeRequest(self.root, draft.draft_id, analysis, scan.receipt_id)
        )

        self.assertEqual(result.status, "published")
        self.assertTrue(finalize.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

    def test_facade_promoted_finalize_ignores_conflicting_process_aliases(self):
        script = r"""
import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path

scripts = Path(sys.argv[1]).resolve()
fixtures = Path(sys.argv[2]).resolve()

def load(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module

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
    (root / "api" / "profile.py").write_text(
        'FIELD = "profile.displayName"\n', encoding="utf-8"
    )
    producer = load("_task5_fix_producer", scripts / "rir_controller.py")
    scan = producer.scan_impact(
        producer.ScanRequest(root, "Rename profile.displayName", (), "balanced")
    )
    draft = producer.begin_refinement(
        producer.BeginRequest(
            root,
            "Rename profile.displayName",
            (),
            "generic",
            scan_id=scan.scan_id,
        )
    )
    analysis = json.loads(
        (fixtures / "controller-analysis-pre-decision.json").read_text(encoding="utf-8")
    )
    analysis["impacts"][0]["graph_path_keys"] = [row["id"] for row in scan.paths]
    if not analysis["impacts"][0]["graph_path_keys"]:
        analysis["impacts"][0]["coverage_rationale"] = (
            "Fast Scan found no closed repository path."
        )
    analysis["impacts"][0]["evidence_level"] = "unknown"

    calls = []
    foreign_dir = root / "foreign"
    foreign_dir.mkdir()

    def forbidden(label):
        def operation(*args, **kwargs):
            calls.append(label)
            raise AssertionError(f"foreign dependency used: {label}")
        return operation

    names = (
        "compact_state",
        "fast_scan",
        "fast_scan_renderer",
        "fast_scan_store",
        "graph_builtin",
        "graph_coordinator",
        "impact_report",
        "impact_renderer",
        "payload_identity",
        "report_store",
        "rir_contracts",
        "rir_finalize",
        "rir_graph_delivery",
        "rir_lineage",
        "rir_storage",
    )
    foreign = {}
    for name in names:
        module = types.ModuleType(name)
        module.__file__ = str(foreign_dir / f"{name}.py")
        foreign[name] = module
        sys.modules[name] = module
    foreign["compact_state"].load_state_bytes = forbidden("compact_state.load_state_bytes")
    foreign["fast_scan"].FastScanResult = type("ForeignFastScanResult", (), {})
    foreign["fast_scan"].FastScanRequest = forbidden("fast_scan.FastScanRequest")
    foreign["fast_scan"].prepare_fast_scan_identity = forbidden(
        "fast_scan.prepare_fast_scan_identity"
    )
    foreign["fast_scan"].validate_fast_scan_receipt = forbidden(
        "fast_scan.validate_fast_scan_receipt"
    )
    foreign["fast_scan"].canonical_fast_scan_bytes = forbidden(
        "fast_scan.canonical_fast_scan_bytes"
    )
    foreign["fast_scan_renderer"].render_fast_scan = forbidden(
        "fast_scan_renderer.render_fast_scan"
    )
    foreign["fast_scan_store"].load_scan_receipt_bytes = forbidden(
        "fast_scan_store.load_scan_receipt_bytes"
    )
    foreign["impact_renderer"].render_compact = forbidden(
        "impact_renderer.render_compact"
    )
    foreign["impact_renderer"].render_markdown = forbidden(
        "impact_renderer.render_markdown"
    )
    foreign["payload_identity"].payload_sha256 = forbidden(
        "payload_identity.payload_sha256"
    )
    foreign["report_store"].ReportStoreError = RuntimeError
    foreign["report_store"].publish_revision = forbidden("report_store.publish_revision")

    controller = load("_task5_fix_conflict_controller", scripts / "rir_controller.py")
    for name, module in foreign.items():
        assert sys.modules[name] is module, name

    result = controller.finalize_refinement(
        controller.FinalizeRequest(root, draft.draft_id, analysis, scan.receipt_id)
    )
    assert result.status == "published"
    assert controller.FINALIZE.STORAGE.load_private_draft(root, draft.draft_id)["consumed"] is True
    assert calls == [], calls
    for name, module in foreign.items():
        assert sys.modules[name] is module, name

    runtime = controller._finalize_runtime()
    defaults = controller.FINALIZE.default_runtime()
    for key in (
        "root_path",
        "bounded_bytes",
        "load_draft",
        "report_lock",
        "load_promoted_scan_context",
        "canonical_bytes",
        "write_controller_metadata",
        "publish_revision",
        "load_state_bytes",
        "render_compact",
        "render_markdown",
        "draft_path",
        "consume_draft",
    ):
        assert runtime[key] is defaults[key], key
    assert runtime["result_type"] is controller.FinalizeResult
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(SCRIPTS), str(FIXTURES)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_malformed_same_path_coordinator_hash_fails_closed_before_finalize(self):
        finalize = self.finalize()
        delivery_path = SCRIPTS / "rir_graph_delivery.py"
        expected_hash = (
            "_rir_finalize_graph_delivery_"
            + __import__("hashlib")
            .sha256(str(delivery_path.resolve()).encode("utf-8"))
            .hexdigest()[:16]
        )
        preserved_canonical = sys.modules.get("rir_graph_delivery")
        canonical_present = "rir_graph_delivery" in sys.modules
        preserved_hash = sys.modules.get(expected_hash)
        hash_present = expected_hash in sys.modules
        module_name = "finalize_malformed_coordinator_guard"
        conflict = types.ModuleType("rir_graph_delivery")
        conflict.__file__ = str(self.root / "foreign-graph-delivery.py")
        graph = types.ModuleType("malformed_graph")
        graph.__file__ = str(SCRIPTS / "impact_graph.py")
        graph.validate_receipt = lambda value: ()
        graph.canonical_receipt_bytes = lambda value: b"{}\n"
        coordinator = types.ModuleType("malformed_coordinator")
        coordinator.__file__ = str(SCRIPTS / "graph_coordinator.py")
        coordinator.GRAPH = graph
        malformed = types.ModuleType(expected_hash)
        malformed.__file__ = str(delivery_path)
        malformed.CONTRACTS = finalize.CONTRACTS
        malformed.STORAGE = finalize.STORAGE
        malformed.GRAPH = graph
        malformed.GRAPH_COORDINATOR = coordinator
        malformed.load_graph_context = lambda *args, **kwargs: {}
        malformed.validate_graph_coverage = lambda *args, **kwargs: None
        malformed.verify_receipt_sources = lambda *args, **kwargs: None
        try:
            sys.modules["rir_graph_delivery"] = conflict
            sys.modules[expected_hash] = malformed
            with self.assertRaisesRegex(
                ImportError,
                "^finalize graph delivery sibling contract is incomplete$",
            ):
                load_module(module_name, FINALIZE_PATH)
            self.assertIs(sys.modules["rir_graph_delivery"], conflict)
        finally:
            sys.modules.pop(module_name, None)
            if canonical_present:
                sys.modules["rir_graph_delivery"] = preserved_canonical
            else:
                sys.modules.pop("rir_graph_delivery", None)
            if hash_present:
                sys.modules[expected_hash] = preserved_hash
            else:
                sys.modules.pop(expected_hash, None)

    def test_default_runtime_rejects_incomplete_same_path_fast_scan_store(self):
        finalize = self.finalize()
        store_path = SCRIPTS / "fast_scan_store.py"
        expected_hash = (
            "_rir_finalize_fast_scan_store_"
            + __import__("hashlib")
            .sha256(str(store_path.resolve()).encode("utf-8"))
            .hexdigest()[:16]
        )
        preserved_canonical = sys.modules.get("fast_scan_store")
        canonical_present = "fast_scan_store" in sys.modules
        preserved_hash = sys.modules.get(expected_hash)
        hash_present = expected_hash in sys.modules
        incomplete = types.ModuleType("fast_scan_store")
        incomplete.__file__ = str(store_path)
        incomplete.load_scan_receipt_bytes = lambda *args, **kwargs: b""
        try:
            sys.modules["fast_scan_store"] = incomplete
            sys.modules.pop(expected_hash, None)
            with self.assertRaisesRegex(
                ImportError,
                "^finalize Fast Scan store sibling contract is incomplete$",
            ):
                finalize.default_runtime()
        finally:
            if canonical_present:
                sys.modules["fast_scan_store"] = preserved_canonical
            else:
                sys.modules.pop("fast_scan_store", None)
            if hash_present:
                sys.modules[expected_hash] = preserved_hash
            else:
                sys.modules.pop(expected_hash, None)

    def test_default_runtime_rejects_missing_promoted_graph_members(self):
        finalize = self.finalize()
        coordinator = finalize.GRAPH_DELIVERY.GRAPH_COORDINATOR
        graph = coordinator.GRAPH
        builtin = coordinator.BUILTIN
        cache = coordinator.CACHE
        cases = (
            (coordinator, "SourceInventory"),
            (coordinator, "_settings"),
            (coordinator, "_seed_key"),
            (graph, "_safe_path"),
            (graph, "_validate_settings"),
            (builtin, "_read_regular_file"),
            (builtin, "_safe_graph_text"),
            (builtin, "_walk_files"),
            (cache, "_cache_directory"),
            (cache, "_read_artifact"),
            (cache, "_source_digests"),
            (cache, "_canonical_json"),
            (cache, "_normalize_receipt"),
        )

        for module, name in cases:
            with self.subTest(module=module.__name__, member=name):
                with mock.patch.object(module, name, None):
                    with self.assertRaisesRegex(
                        ImportError,
                        "^finalize graph delivery sibling contract is incomplete$",
                    ):
                        finalize.default_runtime()

    def test_default_runtime_rejects_cross_wired_promoted_graph_identities(self):
        finalize = self.finalize()
        coordinator = finalize.GRAPH_DELIVERY.GRAPH_COORDINATOR
        builtin = coordinator.BUILTIN
        cache = coordinator.CACHE
        foreign_type = type("ForeignPromotedGraphType", (), {})

        def foreign_operation(*args, **kwargs):
            return None

        cases = (
            (coordinator, "GRAPH", object()),
            (coordinator, "BUILTIN", object()),
            (coordinator, "CACHE", object()),
            (coordinator, "PROVIDERS", object()),
            (coordinator, "GraphSettings", foreign_type),
            (coordinator, "Deadline", foreign_type),
            (coordinator, "ProviderProbe", foreign_type),
            (coordinator, "ProviderQuery", foreign_type),
            (coordinator, "ProviderResult", foreign_type),
            (coordinator, "ProviderSpec", foreign_type),
            (coordinator, "ScanSeed", foreign_type),
            (coordinator, "ScanLimits", foreign_type),
            (coordinator, "discover_providers", foreign_operation),
            (coordinator, "run_provider", foreign_operation),
            (builtin, "GRAPH", object()),
            (builtin, "GraphNode", foreign_type),
            (builtin, "GraphEdge", foreign_type),
            (builtin, "GraphPath", foreign_type),
            (builtin, "FrontierEntry", foreign_type),
            (cache, "GRAPH", object()),
        )

        for module, name, replacement in cases:
            with self.subTest(module=module.__name__, member=name):
                with mock.patch.object(module, name, replacement):
                    with self.assertRaisesRegex(
                        ImportError,
                        "^finalize graph delivery sibling contract is incomplete$",
                    ):
                        finalize.default_runtime()

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
