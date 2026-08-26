from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "delta-cdz-project"


def load_module(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ImportError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


DELTA = load_module("_test_rir_delta", SCRIPTS / "rir_delta.py")
FAST_SCAN = load_module("_test_rir_delta_fast_scan", SCRIPTS / "fast_scan.py")
BUILTIN = load_module("_test_rir_delta_graph_builtin", SCRIPTS / "graph_builtin.py")
CONTROLLER = load_module("_test_rir_delta_controller", SCRIPTS / "rir_controller.py")
MCP = load_module("_test_rir_delta_mcp", SCRIPTS / "rir_mcp_server.py")
CLI = load_module("_test_rir_delta_cli", SCRIPTS / "rir-controller.py")


class FakeClock:
    def monotonic(self):
        return 0.0


def graph_receipt(root: Path, *, frontier=(), budget_status="closed"):
    locations = ("a.py", "c.py", "d.py", "z.py")
    nodes = [
        {
            "id": f"NODE-{index:03d}",
            "kind": "symbol",
            "label": location.removesuffix(".py"),
            "location": location,
            "provider": "builtin",
            "confidence": "structural-inferred",
            "source_sha256": hashlib.sha256((root / location).read_bytes()).hexdigest(),
            "risk_domains": ["regression"],
        }
        for index, location in enumerate(locations, start=1)
    ]
    return {
        "schema_version": 1,
        "receipt_id": "1" * 32,
        "draft_id": "2" * 32,
        "repo_root_sha256": hashlib.sha256(str(root.resolve()).encode()).hexdigest(),
        "request_sha256": "3" * 64,
        "settings": {
            "enabled": True,
            "max_seconds": 30,
            "target_seconds": 10,
            "providers": ["builtin"],
            "install_policy": "never",
            "deep": False,
        },
        "providers": [
            {
                "name": "builtin",
                "status": "ready",
                "confidence": "structural-inferred",
                "version": "builtin-v1",
                "executable_sha256": None,
            }
        ],
        "nodes": nodes,
        "edges": [],
        "paths": [
            {
                "id": "PATH-001",
                "nodes": [row["id"] for row in nodes],
                "edges": [],
                "distance": 3,
                "risk_domains": ["regression"],
            }
        ],
        "frontier": list(frontier),
        "timings_ms": {"total": 1},
        "budget_status": budget_status,
        "cache": {"status": "miss", "key": "4" * 64, "invalidated_nodes": []},
    }


def previous_state(report_id="RPT-001", revision=2):
    return {
        "report": {"id": report_id, "revision": revision},
        "preserved_invariants": [
            {"id": "INV-001", "evidence": "d.py protects the projection"},
            {"id": "INV-002", "evidence": "checks/missing.py remains unknown"},
        ],
        "criteria": [
            {"id": "AC-001", "evidence": "z.py verifies the archive"},
            {"id": "AC-002", "evidence": "checks/criterion.py"},
        ],
    }


def trusted_previous(
    *, status="stale", revision=2, changed_paths=("a.py",), markdown_sha256="5" * 64
):
    return SimpleNamespace(
        status=status,
        report_id="RPT-001",
        revision=revision,
        markdown_sha256=markdown_sha256,
        changed_paths=tuple(changed_paths),
        changed_count=len(changed_paths),
        display_text="## Previous impact\n\nTrusted previous revision.",
    )


class DeltaScanTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repository"
        shutil.copytree(FIXTURE, self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def context(self, *, configured_max_seconds=9, frontier=()):
        return DELTA.bind_delta_context(
            self.root,
            trusted_previous(),
            previous_state(),
            graph_receipt(self.root, frontier=frontier),
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("a.py",),
            configured_max_seconds=configured_max_seconds,
        )

    def test_changed_path_then_all_prior_path_nodes_then_state_evidence_are_stable(self):
        context = self.context()

        seeds = DELTA.derive_delta_seeds(context, changed_paths=("a.py",))

        self.assertEqual(
            tuple(seed.location for seed in seeds),
            (
                "a.py",
                "c.py",
                "d.py",
                "z.py",
                "checks/missing.py",
                "checks/criterion.py",
            ),
        )
        self.assertEqual(
            tuple(seed.derivation.split(":", 1)[0] for seed in seeds),
            (
                "trusted-changed-path",
                "previous-graph-path",
                "previous-graph-path",
                "previous-graph-path",
                "preserved-invariant-evidence",
                "criterion-evidence",
            ),
        )
        self.assertEqual(len({seed.location for seed in seeds}), len(seeds))
        self.assertEqual(seeds[0].provenance["additional"][0]["source"], "previous-graph-path")
        self.assertEqual(
            seeds[2].provenance["additional"][0]["source"],
            "preserved-invariant-evidence",
        )
        self.assertEqual(seeds[3].provenance["additional"][0]["source"], "criterion-evidence")
        self.assertEqual(context.max_seconds, 3)

    def test_indirect_c_d_z_without_request_text_remain_seeded_graph_nodes(self):
        for location in ("c.py", "d.py", "z.py"):
            consumer = (self.root / location).read_text(encoding="utf-8")
            self.assertNotIn("OriginSignal", consumer)
            self.assertNotIn("negotiation", consumer)
        seeds = DELTA.derive_delta_seeds(self.context())

        result = BUILTIN.scan_repository(
            self.root,
            tuple(BUILTIN.ScanSeed(seed.term, seed.location) for seed in seeds),
            BUILTIN.ScanLimits(max_seconds=3),
            FakeClock(),
        )

        locations = {node.location for node in result.nodes}
        self.assertTrue({"a.py", "c.py", "d.py", "z.py"} <= locations)

    def test_generated_directories_do_not_consume_inventory_unless_explicit(self):
        generated = {
            ".mypy_cache/3.9/a.meta.json",
            ".quality-venv/lib/a.py",
            ".requirements-impact-refiner/scans/a.json",
            "evals/results/run/a.py",
            "pkg/__pycache__/a.py",
            "build/a.py",
            "dist/a.py",
            "node_modules/pkg/a.js",
        }
        for relative in generated:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("GENERATED = True\n", encoding="utf-8")

        inventory = DELTA.collect_sources(self.root, explicit_seeds=())

        self.assertTrue(generated.isdisjoint(inventory.digests))
        explicit = DELTA.DeltaSeed(
            ".mypy_cache/3.9/a.meta.json",
            ".mypy_cache/3.9/a.meta.json",
            "request-path-only",
            None,
            {"source": "request"},
        )
        targeted = DELTA.collect_sources(self.root, explicit_seeds=(explicit,))
        self.assertIn(".mypy_cache/3.9/a.meta.json", targeted.digests)
        self.assertTrue((generated - {explicit.location}).isdisjoint(targeted.digests))

    def test_generated_directories_are_excluded_before_builtin_file_budget(self):
        generated = self.root / ".mypy_cache" / "3.9" / "a.meta.json"
        generated.parent.mkdir(parents=True)
        generated.write_text('{"origin_signal": true}\n', encoding="utf-8")

        result = BUILTIN.scan_repository(
            self.root,
            (BUILTIN.ScanSeed("origin_signal", "a.py"),),
            BUILTIN.ScanLimits(max_seconds=3, max_files=5),
            FakeClock(),
        )

        self.assertNotIn(".mypy_cache/3.9/a.meta.json", result.source_digests)
        self.assertIn("a.py", {node.location for node in result.nodes})

    def test_only_exact_stale_lookup_hints_can_bind_prior_state(self):
        good = trusted_previous()
        cases = (
            (trusted_previous(status="fresh"), "RPT-001", 2, ("a.py",)),
            (good, "RPT-999", 2, ("a.py",)),
            (good, "RPT-001", 3, ("a.py",)),
            (good, "RPT-001", 2, ("foreign.py",)),
        )
        for result, report_id, revision, paths in cases:
            with self.subTest(status=result.status, report_id=report_id, revision=revision):
                with self.assertRaisesRegex(ValueError, "trusted stale"):
                    DELTA.bind_delta_context(
                        self.root,
                        result,
                        previous_state(),
                        graph_receipt(self.root),
                        previous_report_id=report_id,
                        previous_revision=revision,
                        changed_paths=paths,
                        configured_max_seconds=3,
                    )

    def test_controller_relooks_up_exact_identity_before_admitting_delta_seeds(self):
        trusted = trusted_previous()
        lookup_requests = []
        scan_calls = []
        settings = {
            "audience": "technical",
            "audience_source": "request",
            "delivery": "compact",
            "delivery_source": "default",
            "delta_max_seconds": 9,
            "impact_graph": graph_receipt(self.root)["settings"],
        }

        def lookup(request):
            lookup_requests.append(request)
            return trusted

        def execute(request, graph_settings, payload_sha256, **kwargs):
            scan_calls.append((request, graph_settings, payload_sha256, kwargs))
            return SimpleNamespace(status="partial")

        with ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(CONTROLLER, "lookup_previous", side_effect=lookup)
            )
            stack.enter_context(
                mock.patch.object(CONTROLLER.SETTINGS, "resolve", return_value=settings)
            )
            stack.enter_context(
                mock.patch.object(
                    CONTROLLER.DELTA,
                    "load_trusted_previous_artifacts",
                    return_value=(previous_state(), graph_receipt(self.root)),
                )
            )
            stack.enter_context(
                mock.patch.object(CONTROLLER.FAST_SCAN, "execute_fast_scan", side_effect=execute)
            )
            stack.enter_context(
                mock.patch.object(CONTROLLER, "_payload_sha256", return_value="a" * 64)
            )
            result = CONTROLLER.scan_impact(
                CONTROLLER.ScanRequest(
                    self.root,
                    "Change OriginSignal negotiation",
                    ("evidence row", "evidence row"),
                    "technical",
                    previous_report_id="RPT-001",
                    previous_revision=2,
                    changed_paths=("a.py",),
                )
            )

        self.assertEqual(result.status, "partial")
        self.assertGreaterEqual(len(lookup_requests), 1)
        for request in lookup_requests:
            self.assertEqual(request.repo_root, self.root.resolve())
            self.assertEqual(request.request, "Change OriginSignal negotiation")
            self.assertEqual(request.repository_evidence, ("evidence row", "evidence row"))
            self.assertEqual(request.report_id, "RPT-001")
        self.assertEqual(len(scan_calls), 1)
        scan_request, _settings, _payload, kwargs = scan_calls[0]
        self.assertEqual(scan_request.previous_report_id, "RPT-001")
        self.assertEqual(scan_request.previous_revision, 2)
        self.assertEqual(scan_request.changed_paths, ("a.py",))
        self.assertEqual(scan_request.delta_max_seconds, 9)
        self.assertEqual(type(kwargs["delta_context"]).__name__, "DeltaScanContext")
        self.assertEqual(kwargs["delta_context"].previous_report_id, "RPT-001")

    def test_controller_rejects_fresh_or_mismatched_hints_without_scanning(self):
        settings = {
            "audience": "balanced",
            "audience_source": "default",
            "delivery": "compact",
            "delivery_source": "default",
            "delta_max_seconds": 3,
            "impact_graph": graph_receipt(self.root)["settings"],
        }
        for result in (
            trusted_previous(status="fresh"),
            trusted_previous(changed_paths=("c.py",)),
        ):
            with self.subTest(status=result.status, changed_paths=result.changed_paths):
                with ExitStack() as stack:
                    stack.enter_context(
                        mock.patch.object(CONTROLLER, "lookup_previous", return_value=result)
                    )
                    stack.enter_context(
                        mock.patch.object(CONTROLLER.SETTINGS, "resolve", return_value=settings)
                    )
                    stack.enter_context(
                        mock.patch.object(
                            CONTROLLER.FAST_SCAN,
                            "execute_fast_scan",
                            side_effect=AssertionError("forged delta must not scan"),
                        )
                    )
                    with self.assertRaisesRegex(ValueError, "trusted stale"):
                        CONTROLLER.scan_impact(
                            CONTROLLER.ScanRequest(
                                self.root,
                                "Change OriginSignal negotiation",
                                (),
                                None,
                                previous_report_id="RPT-001",
                                previous_revision=2,
                                changed_paths=("a.py",),
                            )
                        )

    def test_mcp_scan_accepts_delta_hints_and_returns_previous_summary(self):
        arguments = {
            "repo_root": str(self.root),
            "change_request": "Change OriginSignal negotiation",
            "evidence": ["a.py"],
            "presentation": "technical",
            "previous_report_id": "RPT-001",
            "previous_revision": 2,
            "changed_paths": ["a.py"],
        }
        self.assertTrue(MCP._is_scan_arguments(arguments))
        for field in ("previous_report_id", "previous_revision", "changed_paths"):
            self.assertIn(field, MCP.SCAN_SCHEMA["properties"])
        result = SimpleNamespace(
            status="partial",
            scan_id="1" * 32,
            receipt_id="2" * 32,
            receipt_sha256="3" * 64,
            display_text="previous then partial",
            risk_level="high",
            paths=(),
            frontier=(),
            candidates=(),
            elapsed_ms=3,
            cache_status="miss",
            can_promote=False,
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("a.py",),
            changed_count=1,
            previous_display_text="previous",
        )
        with mock.patch.object(MCP.rir_controller, "scan_impact", return_value=result) as scan:
            response = MCP._scan(arguments)

        scan_request = scan.call_args.args[0]
        self.assertEqual(scan_request.previous_report_id, "RPT-001")
        self.assertEqual(scan_request.previous_revision, 2)
        self.assertEqual(scan_request.changed_paths, ("a.py",))
        structured = response["structuredContent"]
        self.assertEqual(structured["previous_report_id"], "RPT-001")
        self.assertEqual(structured["previous_revision"], 2)
        self.assertEqual(structured["changed_paths"], ["a.py"])
        self.assertEqual(structured["changed_count"], 1)

    def test_cli_scan_accepts_delta_hints_and_preserves_duplicate_evidence(self):
        input_path = self.root / "scan.json"
        input_path.write_text(
            json.dumps(
                {
                    "change_request": "Change OriginSignal negotiation",
                    "evidence": ["same", "same"],
                    "presentation": "technical",
                    "previous_report_id": "RPT-001",
                    "previous_revision": 2,
                    "changed_paths": ["a.py"],
                }
            ),
            encoding="utf-8",
        )
        args = SimpleNamespace(repo_root=self.root, input=input_path, json=True)
        result = SimpleNamespace(
            status="partial",
            scan_id="1" * 32,
            receipt_id="2" * 32,
            receipt_sha256="3" * 64,
            display_text="previous then partial",
            risk_level="high",
            paths=(),
            frontier=(),
            candidates=(),
            elapsed_ms=3,
            cache_status="miss",
            can_promote=False,
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("a.py",),
            changed_count=1,
            previous_display_text="previous",
        )
        output = io.StringIO()
        with mock.patch.object(CLI.rir_controller, "scan_impact", return_value=result) as scan:
            with redirect_stdout(output):
                exit_code = CLI._scan(args)

        self.assertEqual(exit_code, 0)
        request = scan.call_args.args[0]
        self.assertEqual(request.evidence, ("same", "same"))
        self.assertEqual(request.previous_report_id, "RPT-001")
        self.assertEqual(request.previous_revision, 2)
        self.assertEqual(request.changed_paths, ("a.py",))
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["previous_report_id"], "RPT-001")
        self.assertEqual(payload["changed_paths"], ["a.py"])

    def test_foreign_state_and_graph_cannot_contribute_seeds(self):
        foreign_state = previous_state(report_id="RPT-777")
        with self.assertRaisesRegex(ValueError, "state identity"):
            DELTA.bind_delta_context(
                self.root,
                trusted_previous(),
                foreign_state,
                graph_receipt(self.root),
                previous_report_id="RPT-001",
                previous_revision=2,
                changed_paths=("a.py",),
                configured_max_seconds=3,
            )

    def test_trusted_artifact_loader_binds_current_state_and_private_graph(self):
        report_dir = self.root / ".requirements-impact-refiner" / "reports" / "RPT-001"
        graph_dir = self.root / ".requirements-impact-refiner" / "graph"
        report_dir.mkdir(parents=True)
        graph_dir.mkdir(parents=True)
        state = previous_state()
        state_payload = (json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n").encode()
        markdown_payload = b"trusted previous markdown\n"
        receipt = graph_receipt(self.root)
        receipt_payload = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        state_name = "revision-0002.json"
        markdown_name = "revision-0002.md"
        (report_dir / state_name).write_bytes(state_payload)
        (report_dir / markdown_name).write_bytes(markdown_payload)
        pointer = {
            "schema_version": 1,
            "report_id": "RPT-001",
            "revision": 2,
            "state": state_name,
            "markdown": markdown_name,
            "markdown_sha256": hashlib.sha256(markdown_payload).hexdigest(),
        }
        pointer_payload = (
            json.dumps(pointer, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        (report_dir / "current.json").write_bytes(pointer_payload)
        controller = {
            "schema_version": 1,
            "draft_id": receipt["draft_id"],
            "report_id": "RPT-001",
            "revision": 2,
            "state_sha256": hashlib.sha256(state_payload).hexdigest(),
            "key_map": {},
            "graph_receipt": {
                "receipt_id": receipt["receipt_id"],
                "sha256": hashlib.sha256(receipt_payload).hexdigest(),
            },
        }
        controller_path = report_dir / "revision-0002.controller.json"
        controller_path.write_bytes(
            json.dumps(controller, sort_keys=True, separators=(",", ":")).encode()
        )
        controller_path.chmod(0o600)
        graph_path = graph_dir / f"{receipt['draft_id']}.json"
        graph_path.write_bytes(receipt_payload)
        graph_path.chmod(0o600)
        trusted = trusted_previous(markdown_sha256=pointer["markdown_sha256"])

        loaded_state, loaded_graph = DELTA.load_trusted_previous_artifacts(
            self.root,
            trusted,
            state_loader=lambda payload: (json.loads(payload), []),
            receipt_loader=lambda payload: (json.loads(payload), []),
            canonical_receipt_bytes=lambda value: json.dumps(
                value, sort_keys=True, separators=(",", ":")
            ).encode(),
            max_receipt_bytes=4 * 1024 * 1024,
        )

        self.assertEqual(loaded_state, state)
        self.assertEqual(loaded_graph, receipt)

        graph_path.unlink()
        scan_id = "9" * 32
        promoted_receipt = json.loads(json.dumps(receipt))
        promoted_receipt["draft_id"] = scan_id
        promoted_receipt_payload = json.dumps(
            promoted_receipt, sort_keys=True, separators=(",", ":")
        ).encode()
        controller["graph_receipt"] = {
            "receipt_id": promoted_receipt["receipt_id"],
            "sha256": hashlib.sha256(promoted_receipt_payload).hexdigest(),
        }
        controller_path.write_bytes(
            json.dumps(controller, sort_keys=True, separators=(",", ":")).encode()
        )
        controller_path.chmod(0o600)
        wrapper = {"scan_id": scan_id, "graph_receipt": promoted_receipt}
        wrapper_payload = json.dumps(wrapper, sort_keys=True, separators=(",", ":")).encode()
        promoted = {
            "scan_id": scan_id,
            "sha256": hashlib.sha256(wrapper_payload).hexdigest(),
            "receipt_id": promoted_receipt["receipt_id"],
            "receipt_sha256": hashlib.sha256(promoted_receipt_payload).hexdigest(),
        }
        drafts_dir = self.root / ".requirements-impact-refiner" / "drafts"
        scans_dir = self.root / ".requirements-impact-refiner" / "scans"
        drafts_dir.mkdir()
        scans_dir.mkdir()
        draft_path = drafts_dir / f"{receipt['draft_id']}.json"
        draft_path.write_bytes(
            (
                json.dumps(
                    {
                        "draft_id": receipt["draft_id"],
                        "repo_root": str(self.root.resolve()),
                        "report_id": "RPT-001",
                        "revision": 2,
                        "promoted_scan": promoted,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode()
        )
        draft_path.chmod(0o600)
        scan_path = scans_dir / f"{scan_id}.json"
        scan_path.write_bytes(wrapper_payload)
        scan_path.chmod(0o600)

        promoted_state, promoted_graph = DELTA.load_trusted_previous_artifacts(
            self.root,
            trusted,
            state_loader=lambda payload: (json.loads(payload), []),
            receipt_loader=lambda payload: (json.loads(payload), []),
            canonical_receipt_bytes=lambda value: json.dumps(
                value, sort_keys=True, separators=(",", ":")
            ).encode(),
            max_receipt_bytes=4 * 1024 * 1024,
        )
        self.assertEqual(promoted_state, state)
        self.assertEqual(promoted_graph, promoted_receipt)

        outside = Path(self.temporary.name) / "foreign-graph.json"
        outside.write_bytes(receipt_payload)
        graph_path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "graph artifact"):
            DELTA.load_trusted_previous_artifacts(
                self.root,
                trusted,
                state_loader=lambda payload: (json.loads(payload), []),
                receipt_loader=lambda payload: (json.loads(payload), []),
                canonical_receipt_bytes=lambda value: json.dumps(
                    value, sort_keys=True, separators=(",", ":")
                ).encode(),
                max_receipt_bytes=4 * 1024 * 1024,
            )
        foreign_graph = graph_receipt(self.root)
        foreign_graph["repo_root_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "graph identity"):
            DELTA.bind_delta_context(
                self.root,
                trusted_previous(),
                previous_state(),
                foreign_graph,
                previous_report_id="RPT-001",
                previous_revision=2,
                changed_paths=("a.py",),
                configured_max_seconds=3,
            )

    def test_configured_delta_budget_is_positive_and_hard_capped(self):
        self.assertEqual(self.context(configured_max_seconds=30).max_seconds, 3)
        self.assertEqual(self.context(configured_max_seconds=2).max_seconds, 2)
        for invalid in (0, -1, True, "3"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "delta_max_seconds"):
                    self.context(configured_max_seconds=invalid)

    def test_settings_publish_default_and_repository_delta_budget(self):
        default = CONTROLLER.SETTINGS.resolve(self.root, None, None)
        self.assertNotIn("delta_max_seconds", default)
        self.assertEqual(CONTROLLER.SETTINGS.resolve_delta_max_seconds(self.root), 3)

        (self.root / ".requirements-impact-refiner.json").write_text(
            '{"delta_max_seconds":9}\n', encoding="utf-8"
        )
        configured = CONTROLLER.SETTINGS.resolve_delta_max_seconds(self.root)
        self.assertEqual(configured, 9)

        (self.root / ".requirements-impact-refiner.json").write_text(
            '{"delta_max_seconds":0}\n', encoding="utf-8"
        )
        invalid = CONTROLLER.SETTINGS.resolve(self.root, None, None)
        self.assertEqual(CONTROLLER.SETTINGS.resolve_delta_max_seconds(self.root), 3)
        self.assertIn("invalid delta_max_seconds", invalid["warnings"][-1])

    def test_delta_timeout_keeps_previous_identity_and_all_surviving_frontier(self):
        prior_frontier = (
            {
                "id": "FRONTIER-001",
                "node": "NODE-004",
                "reason": "archive consumer remains unknown",
                "risk_domains": ["regression"],
            },
        )
        context = self.context(frontier=prior_frontier)
        captured = []

        def coordinator(_root, _draft, _seeds, settings, **_kwargs):
            captured.append(settings.max_seconds)
            return graph_receipt(
                self.root,
                frontier=(
                    {
                        "id": "FRONTIER-002",
                        "node": "NODE-001",
                        "reason": "shared graph deadline exhausted",
                        "risk_domains": ["regression"],
                    },
                ),
                budget_status="budget_exhausted",
            )

        result = FAST_SCAN.execute_fast_scan(
            FAST_SCAN.FastScanRequest(
                self.root,
                "Change OriginSignal negotiation",
                (),
                "technical",
                previous_report_id="RPT-001",
                previous_revision=2,
                changed_paths=("a.py",),
                delta_max_seconds=9,
            ),
            graph_receipt(self.root)["settings"],
            "a" * 64,
            coordinator=coordinator,
            delta_context=context,
        )

        self.assertEqual(captured, [3])
        self.assertEqual(result.status, "partial")
        self.assertFalse(result.can_promote)
        self.assertEqual(result.previous_report_id, "RPT-001")
        self.assertEqual(result.previous_revision, 2)
        self.assertEqual(result.changed_paths, ("a.py",))
        self.assertTrue(result.display_text.startswith(context.previous_display_text))
        reasons = {str(row["reason"]) for row in result.frontier}
        self.assertIn("archive consumer remains unknown", reasons)
        self.assertIn("shared graph deadline exhausted", reasons)
        self.assertIn("previous evidence remains unverified: checks/missing.py", reasons)
        self.assertLessEqual(result.elapsed_ms, 3_000)

    def test_ordinary_scan_keeps_existing_budget_and_hints_without_context_fail_closed(self):
        captured = []

        def coordinator(_root, _draft, _seeds, settings, **_kwargs):
            captured.append(settings.max_seconds)
            return graph_receipt(self.root)

        ordinary = FAST_SCAN.execute_fast_scan(
            FAST_SCAN.FastScanRequest(self.root, "Change a.py", (), "simple"),
            graph_receipt(self.root)["settings"],
            "b" * 64,
            coordinator=coordinator,
        )
        self.assertEqual(captured, [30])
        self.assertEqual(ordinary.status, "complete")

        with self.assertRaisesRegex(ValueError, "trusted delta context"):
            FAST_SCAN.execute_fast_scan(
                FAST_SCAN.FastScanRequest(
                    self.root,
                    "Change a.py",
                    (),
                    "simple",
                    previous_report_id="RPT-001",
                    previous_revision=2,
                    changed_paths=("a.py",),
                ),
                graph_receipt(self.root)["settings"],
                "c" * 64,
                coordinator=lambda *_args, **_kwargs: self.fail("must not scan forged hints"),
            )

    def test_delta_identity_and_cache_include_previous_revision_and_changed_paths(self):
        first = self.context()
        second = DELTA.bind_delta_context(
            self.root,
            trusted_previous(revision=3, changed_paths=("c.py",)),
            previous_state(revision=3),
            graph_receipt(self.root),
            previous_report_id="RPT-001",
            previous_revision=3,
            changed_paths=("c.py",),
            configured_max_seconds=3,
        )
        first_request = FAST_SCAN.FastScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("a.py",),
        )
        second_request = FAST_SCAN.FastScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            previous_report_id="RPT-001",
            previous_revision=3,
            changed_paths=("c.py",),
        )

        first_identity = FAST_SCAN.prepare_fast_scan_identity(
            first_request, graph_receipt(self.root)["settings"], "d" * 64, first
        )
        second_identity = FAST_SCAN.prepare_fast_scan_identity(
            second_request, graph_receipt(self.root)["settings"], "d" * 64, second
        )

        self.assertNotEqual(first_identity.scan_id, second_identity.scan_id)
        self.assertNotEqual(first_identity.request_sha256, second_identity.request_sha256)

    def test_exact_delta_identity_reuses_cache_without_graph_work(self):
        context = self.context()
        calls = []

        def coordinator(*_args, **_kwargs):
            calls.append("graph")
            return graph_receipt(self.root, budget_status="budget_exhausted")

        request = FAST_SCAN.FastScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("a.py",),
            delta_max_seconds=3,
        )
        first = FAST_SCAN.execute_fast_scan(
            request,
            graph_receipt(self.root)["settings"],
            "e" * 64,
            coordinator=coordinator,
            delta_context=context,
        )
        second = FAST_SCAN.execute_fast_scan(
            request,
            graph_receipt(self.root)["settings"],
            "e" * 64,
            coordinator=lambda *_args, **_kwargs: self.fail("cache hit must skip graph work"),
            delta_context=context,
        )

        self.assertEqual(calls, ["graph"])
        self.assertEqual(first.scan_id, second.scan_id)
        self.assertEqual(second.cache_status, "hit")
        self.assertEqual(second.previous_report_id, "RPT-001")
        self.assertEqual(second.changed_paths, ("a.py",))
        self.assertLessEqual(second.elapsed_ms, 3_000)

    def test_complete_delta_receipt_can_be_revalidated_for_promotion(self):
        complete_state = previous_state()
        complete_state["preserved_invariants"] = [complete_state["preserved_invariants"][0]]
        complete_state["criteria"] = [complete_state["criteria"][0]]
        context = DELTA.bind_delta_context(
            self.root,
            trusted_previous(),
            complete_state,
            graph_receipt(self.root),
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("a.py",),
            configured_max_seconds=3,
        )
        output_graph = json.loads(
            (ROOT / "tests" / "fixtures" / "impact-graph-receipt.json").read_text(encoding="utf-8")
        )
        output_graph["budget_status"] = "closed"
        output_graph["frontier"] = []
        output_graph["nodes"] = graph_receipt(self.root)["nodes"]
        output_graph["edges"] = []
        output_graph["paths"] = []
        settings = {
            "audience": "technical",
            "audience_source": "request",
            "delivery": "compact",
            "delivery_source": "default",
            "delta_max_seconds": 3,
            "impact_graph": output_graph["settings"],
        }
        scan_request = CONTROLLER.FAST_SCAN.FastScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("a.py",),
        )
        scan = CONTROLLER.FAST_SCAN.execute_fast_scan(
            scan_request,
            output_graph["settings"],
            "a" * 64,
            coordinator=lambda *_args, **_kwargs: output_graph,
            delta_context=context,
        )
        self.assertEqual(scan.status, "complete")
        self.assertTrue(scan.can_promote)

        begin_request = SimpleNamespace(
            scan_id=scan.scan_id,
            request="Change OriginSignal negotiation",
            repository_evidence=(),
        )
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(CONTROLLER, "_trusted_delta_context", return_value=context)
            )
            stack.enter_context(
                mock.patch.object(CONTROLLER, "_payload_sha256", return_value="a" * 64)
            )
            promoted = CONTROLLER._promoted_scan(self.root.resolve(), begin_request, settings)

        self.assertEqual(promoted["scan_id"], scan.scan_id)
        self.assertEqual(promoted["receipt_id"], output_graph["receipt_id"])

    def test_c_d_z_delta_scan_p95_is_below_three_seconds(self):
        context = self.context()
        observations = []
        for _ in range(25):
            started = time.perf_counter()
            seeds = DELTA.derive_delta_seeds(context)
            BUILTIN.scan_repository(
                self.root,
                tuple(BUILTIN.ScanSeed(seed.term, seed.location) for seed in seeds),
                BUILTIN.ScanLimits(max_seconds=3),
                FakeClock(),
            )
            observations.append(time.perf_counter() - started)
        observations.sort()
        p95 = observations[int(len(observations) * 0.95) - 1]
        self.assertLessEqual(p95, 3.0)

    def test_fast_scan_schema_declares_optional_delta_context(self):
        schema = json.loads(
            (ROOT / "schemas" / "fast-impact-scan.schema.json").read_text(encoding="utf-8")
        )

        self.assertIn("delta_context", schema["properties"])
        self.assertNotIn("delta_context", schema["required"])
        delta = schema["properties"]["delta_context"]
        self.assertEqual(delta["properties"]["max_seconds"]["maximum"], 3)

    def test_delta_runtime_is_payload_bound_and_installed_mirrors_are_exact(self):
        self.assertIn("scripts/rir_delta.py", CONTROLLER.PAYLOAD_IDENTITY.ROOT_FILES)
        pairs = (
            ("rir_delta.py", "rir_delta.py"),
            ("fast_scan.py", "fast_scan.py"),
            ("graph_builtin.py", "graph_builtin.py"),
            ("resolve-settings.py", "resolve-settings.py"),
            ("rir_contracts.py", "rir_contracts.py"),
            ("rir_controller.py", "rir_controller.py"),
            ("rir-controller.py", "rir-controller.py"),
            ("payload_identity.py", "payload_identity.py"),
        )
        installed = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
        for root_name, installed_name in pairs:
            with self.subTest(root_name=root_name):
                self.assertEqual(
                    (SCRIPTS / root_name).read_bytes(),
                    (installed / installed_name).read_bytes(),
                )
        self.assertEqual(
            (ROOT / "schemas" / "fast-impact-scan.schema.json").read_bytes(),
            (
                ROOT
                / "skills"
                / "requirements-impact-refiner"
                / "schemas"
                / "fast-impact-scan.schema.json"
            ).read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
