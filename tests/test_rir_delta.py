from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
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
SLOW_WORKER = ROOT / "tests" / "fixtures" / "delta-workers" / "slow_worker.py"


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
WORKER = load_module("_test_rir_delta_worker", SCRIPTS / "rir_delta_worker.py")


class FakeClock:
    def monotonic(self):
        return 0.0


def process_exists(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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
    edges = [
        {
            "id": f"EDGE-{index:03d}",
            "source": nodes[index - 1]["id"],
            "target": nodes[index]["id"],
            "kind": "references",
            "location": nodes[index]["location"],
            "evidence": f"dependency-{index}",
            "confidence": "structural-inferred",
            "provider": "builtin",
            "source_sha256": nodes[index]["source_sha256"],
        }
        for index in range(1, len(nodes))
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
        "edges": edges,
        "paths": [
            {
                "id": "PATH-001",
                "nodes": [row["id"] for row in nodes],
                "edges": [row["id"] for row in edges],
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


def graph_identity(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return value["receipt_id"], hashlib.sha256(payload).hexdigest()


def trusted_previous(
    *,
    status="stale",
    revision=2,
    changed_paths=("a.py",),
    markdown_sha256="5" * 64,
    requirement_sha256="c" * 64,
    source_inventory_sha256="d" * 64,
):
    return SimpleNamespace(
        status=status,
        report_id="RPT-001",
        revision=revision,
        markdown_sha256=markdown_sha256,
        changed_paths=tuple(changed_paths),
        changed_count=len(changed_paths),
        requirement_sha256=requirement_sha256,
        source_inventory_sha256=source_inventory_sha256,
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
        prior_graph = graph_receipt(self.root, frontier=frontier)
        receipt_id, receipt_sha256 = graph_identity(prior_graph)
        return DELTA.bind_delta_context(
            self.root,
            trusted_previous(),
            previous_state(),
            prior_graph,
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("a.py",),
            configured_max_seconds=configured_max_seconds,
            previous_graph_receipt_id=receipt_id,
            previous_graph_sha256=receipt_sha256,
        )

    def chain_context(self):
        state = previous_state()
        state["preserved_invariants"] = []
        state["criteria"] = []
        prior_graph = graph_receipt(self.root)
        receipt_id, receipt_sha256 = graph_identity(prior_graph)
        return DELTA.bind_delta_context(
            self.root,
            trusted_previous(),
            state,
            prior_graph,
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("a.py",),
            configured_max_seconds=3,
            previous_graph_receipt_id=receipt_id,
            previous_graph_sha256=receipt_sha256,
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
        prior_graph = graph_receipt(self.root)
        self.assertEqual(CONTROLLER.GRAPH.validate_receipt(prior_graph), ())
        self.assertEqual(len(prior_graph["nodes"]), 4)
        self.assertEqual(len(prior_graph["edges"]), 3)
        self.assertEqual(prior_graph["paths"][0]["distance"], 3)

        result = BUILTIN.scan_repository(
            self.root,
            tuple(BUILTIN.ScanSeed(seed.term, seed.location) for seed in seeds),
            BUILTIN.ScanLimits(max_seconds=3),
            FakeClock(),
        )

        locations = {node.location for node in result.nodes}
        self.assertTrue({"a.py", "c.py", "d.py", "z.py"} <= locations)

    def test_prior_path_requires_current_receipt_local_edge_chain(self):
        context = self.chain_context()
        current = graph_receipt(self.root)
        current["edges"] = []
        current["paths"] = []

        frontier = DELTA.surviving_frontier(context, current)
        reasons = {row["reason"] for row in frontier}

        self.assertIn("previous selected path remains unverified: PATH-001", reasons)
        for location in ("a.py", "c.py", "d.py", "z.py"):
            self.assertIn(
                f"previous selected path node remains unverified: PATH-001:{location}",
                reasons,
            )

        request = FAST_SCAN.FastScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("a.py",),
        )
        result = FAST_SCAN.execute_fast_scan(
            request,
            graph_receipt(self.root)["settings"],
            "7" * 64,
            coordinator=lambda *_args, **_kwargs: current,
            delta_context=context,
        )
        self.assertEqual(result.status, "partial")
        self.assertFalse(result.can_promote)

    def test_prior_path_rejects_missing_null_digest_and_unexpected_hash_change(self):
        context = self.chain_context()
        cases = []
        missing = graph_receipt(self.root)
        missing["nodes"] = missing["nodes"][:-1]
        missing["edges"] = missing["edges"][:-1]
        missing["paths"] = []
        cases.append(("missing", missing, "z.py"))
        null_digest = graph_receipt(self.root)
        null_digest["nodes"][1]["source_sha256"] = None
        null_digest["edges"][0]["source_sha256"] = None
        cases.append(("null-digest", null_digest, "c.py"))
        (self.root / "c.py").write_text("changed_consumer = True\n", encoding="utf-8")
        hash_changed = graph_receipt(self.root)
        cases.append(("hash-change", hash_changed, "c.py"))

        for label, current, location in cases:
            with self.subTest(label=label):
                frontier = DELTA.surviving_frontier(context, current)
                reasons = {row["reason"] for row in frontier}
                self.assertIn("previous selected path remains unverified: PATH-001", reasons)
                self.assertIn(
                    f"previous selected path node remains unverified: PATH-001:{location}",
                    reasons,
                )

    def test_prior_path_rejects_an_unverified_intervening_current_node(self):
        context = self.chain_context()
        current = graph_receipt(self.root)
        current["nodes"].append(
            {
                "id": "NODE-005",
                "kind": "symbol",
                "label": "supplied-only",
                "location": "missing.py",
                "provider": "builtin",
                "confidence": "lexical",
                "source_sha256": None,
                "risk_domains": ["regression"],
            }
        )
        current["edges"] = [
            current["edges"][0],
            {
                **current["edges"][1],
                "source": "NODE-002",
                "target": "NODE-005",
                "location": "missing.py",
                "source_sha256": None,
            },
            {
                **current["edges"][2],
                "source": "NODE-005",
                "target": "NODE-003",
                "location": "d.py",
                "source_sha256": current["nodes"][2]["source_sha256"],
            },
            {
                **current["edges"][2],
                "id": "EDGE-004",
            },
        ]
        current["paths"][0] = {
            **current["paths"][0],
            "nodes": ["NODE-001", "NODE-002", "NODE-005", "NODE-003", "NODE-004"],
            "edges": ["EDGE-001", "EDGE-002", "EDGE-003", "EDGE-004"],
            "distance": 4,
        }
        self.assertEqual(CONTROLLER.GRAPH.validate_receipt(current), ())

        frontier = DELTA.surviving_frontier(context, current)

        self.assertTrue(
            any(
                row["reason"] == "previous selected path remains unverified: PATH-001"
                for row in frontier
            )
        )

    def test_prior_path_survives_valid_chain_with_changed_requested_source(self):
        context = self.chain_context()
        (self.root / "a.py").write_text("def origin_signal(value):\n    return value + 1\n")
        current = graph_receipt(self.root)

        frontier = DELTA.surviving_frontier(context, current)

        self.assertFalse(
            any("previous selected path" in str(row.get("reason")) for row in frontier)
        )

    def test_prior_path_accepts_explicit_verified_replacement_node(self):
        context = self.chain_context()
        replacement_path = self.root / "c_v2.py"
        replacement_path.write_text("replacement_consumer = True\n", encoding="utf-8")
        current = graph_receipt(self.root)
        replacement_sha256 = hashlib.sha256(replacement_path.read_bytes()).hexdigest()
        current["nodes"][1]["location"] = "c_v2.py"
        current["nodes"][1]["source_sha256"] = replacement_sha256
        current["nodes"][1]["confidence"] = "verified-provider"
        current["edges"][0]["location"] = "c_v2.py"
        current["edges"][0]["source_sha256"] = replacement_sha256

        frontier = DELTA.surviving_frontier(context, current)

        self.assertFalse(
            any("previous selected path" in str(row.get("reason")) for row in frontier)
        )

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
        stage_events = []
        settings = {
            "audience": "technical",
            "audience_source": "request",
            "delivery": "compact",
            "delivery_source": "default",
            "delta_max_seconds": 1,
            "impact_graph": graph_receipt(self.root)["settings"],
        }

        def lookup(request):
            lookup_requests.append(request)
            stage_events.append("lookup")
            return trusted

        def execute(request, graph_settings, payload_sha256, **kwargs):
            scan_calls.append((request, graph_settings, payload_sha256, kwargs))
            stage_events.append("scan")
            return SimpleNamespace(status="partial")

        def load_artifacts(*_args, **_kwargs):
            stage_events.append("artifact")
            return (
                previous_state(),
                prior_graph,
                "bound",
                prior_graph_id,
                prior_graph_sha256,
            )

        prior_graph = graph_receipt(self.root)
        prior_graph_id, prior_graph_sha256 = graph_identity(prior_graph)

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
                    side_effect=load_artifacts,
                )
            )
            stack.enter_context(
                mock.patch.object(CONTROLLER.FAST_SCAN, "execute_fast_scan", side_effect=execute)
            )
            stack.enter_context(
                mock.patch.object(CONTROLLER, "_payload_sha256", return_value="a" * 64)
            )
            result = CONTROLLER._scan_impact_in_process(
                CONTROLLER.ScanRequest(
                    self.root,
                    "Change OriginSignal negotiation",
                    ("evidence row", "evidence row"),
                    "technical",
                    previous_report_id="RPT-001",
                    previous_revision=2,
                    changed_paths=("a.py",),
                ),
                operation_started=time.monotonic(),
                _worker_control_callback=lambda maximum: stage_events.append(f"control:{maximum}"),
                _worker_fallback_callback=lambda _fallback: stage_events.append("fallback"),
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
        self.assertEqual(scan_request.delta_max_seconds, 1)
        self.assertEqual(type(kwargs["delta_context"]).__name__, "DeltaScanContext")
        self.assertEqual(kwargs["delta_context"].previous_report_id, "RPT-001")
        self.assertEqual(stage_events[0], "control:1")
        self.assertLess(stage_events.index("artifact"), stage_events.index("fallback"))
        self.assertLess(stage_events.index("fallback"), stage_events.index("scan"))

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
                        CONTROLLER._scan_impact_in_process(
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

    def test_controller_uses_worker_only_for_delta_requests(self):
        sentinel = SimpleNamespace(status="partial")
        delta_request = CONTROLLER.ScanRequest(
            self.root,
            "Change a.py",
            (),
            "balanced",
            "RPT-001",
            2,
            ("a.py",),
        )
        with (
            mock.patch.object(CONTROLLER, "_execute_delta_worker", return_value=sentinel) as worker,
            mock.patch.object(
                CONTROLLER, "_root", side_effect=AssertionError("parent resolved repository")
            ),
            mock.patch.object(
                CONTROLLER.SETTINGS,
                "resolve",
                side_effect=AssertionError("parent loaded settings"),
            ),
            mock.patch.dict(os.environ, {"RIR_DELTA_WORKER": "1"}),
        ):
            self.assertIs(CONTROLLER.scan_impact(delta_request), sentinel)
        self.assertEqual(worker.call_count, 1)
        self.assertIs(worker.call_args.args[0], delta_request)
        self.assertEqual(worker.call_args.args[1], 3)
        self.assertIsInstance(worker.call_args.args[2], float)

        ordinary = SimpleNamespace(status="complete")
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    CONTROLLER,
                    "_execute_delta_worker",
                    side_effect=AssertionError("ordinary scans must stay in process"),
                )
            )
            stack.enter_context(
                mock.patch.object(CONTROLLER.FAST_SCAN, "execute_fast_scan", return_value=ordinary)
            )
            result = CONTROLLER.scan_impact(
                CONTROLLER.ScanRequest(self.root, "Change a.py", (), "balanced")
            )
        self.assertIs(result, ordinary)

    def test_parent_spawns_before_repository_trust_and_preflight_timeout_is_identity_free(self):
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )
        started = time.monotonic()
        with (
            mock.patch.object(
                CONTROLLER, "_root", side_effect=AssertionError("parent resolved repository")
            ),
            mock.patch.object(
                CONTROLLER.SETTINGS,
                "resolve",
                side_effect=AssertionError("parent loaded settings"),
            ),
            mock.patch.object(
                CONTROLLER,
                "lookup_previous",
                side_effect=AssertionError("parent performed previous lookup"),
            ),
            mock.patch.object(
                CONTROLLER,
                "_payload_sha256",
                side_effect=AssertionError("parent hashed payload"),
            ),
        ):
            result = CONTROLLER._execute_delta_worker(
                request,
                1,
                started,
                worker_path=SLOW_WORKER,
                worker_environment={"RIR_DELTA_TEST_SCENARIO": "lookup"},
            )

        self.assertLessEqual(round((time.monotonic() - started) * 1000), 1_125)
        self.assertIsNone(result.previous_report_id)
        self.assertIsNone(result.previous_revision)
        self.assertEqual(result.changed_paths, ())
        self.assertIsNone(result.previous_display_text)
        self.assertEqual(result.paths, ())
        self.assertIn("preflight", result.display_text)
        self.assertEqual(result.status, "partial")
        self.assertFalse(result.can_promote)

    def test_worker_filesystem_trust_failure_returns_identity_free_partial(self):
        missing_root = Path(self.temporary.name) / "missing-repository"
        request = CONTROLLER.ScanRequest(
            missing_root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )

        result = CONTROLLER._execute_delta_worker(request, 1, time.monotonic())

        self.assertEqual(result.status, "partial")
        self.assertFalse(result.can_promote)
        self.assertIsNone(result.previous_report_id)
        self.assertEqual(result.changed_paths, ())
        self.assertEqual(result.paths, ())
        self.assertIn("preflight", result.frontier[0]["reason"])

    def test_parent_rejects_syntactically_incomplete_delta_hints_before_spawn(self):
        requests = (
            CONTROLLER.ScanRequest(self.root, "Change a.py", (), "technical", "RPT-001", None, ()),
            CONTROLLER.ScanRequest(self.root, "Change a.py", (), "technical", None, 2, ("a.py",)),
            CONTROLLER.ScanRequest(
                self.root, "Change a.py", (), "technical", None, None, ("a.py",)
            ),
        )

        for request in requests:
            with self.subTest(request=request):
                with self.assertRaisesRegex(ValueError, "all-or-none"):
                    CONTROLLER._execute_delta_worker(request, 1, time.monotonic())

    def test_parent_accepts_only_supported_one_to_three_second_hard_budgets(self):
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change a.py",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )

        for invalid in (0.5, 0, 4, True):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "between one and three"):
                    CONTROLLER._execute_delta_worker(request, invalid, time.monotonic())

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

    def test_delta_context_binds_exact_prior_graph_receipt_identity(self):
        prior_graph = graph_receipt(self.root)
        receipt_id, receipt_sha256 = graph_identity(prior_graph)
        context = DELTA.bind_delta_context(
            self.root,
            trusted_previous(),
            previous_state(),
            prior_graph,
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("a.py",),
            configured_max_seconds=3,
            previous_graph_receipt_id=receipt_id,
            previous_graph_sha256=receipt_sha256,
        )
        mapping = DELTA.context_mapping(context, DELTA.derive_delta_seed_selection(context))

        self.assertEqual(context.previous_graph_receipt_id, receipt_id)
        self.assertEqual(context.previous_graph_sha256, receipt_sha256)
        self.assertEqual(mapping["previous_graph_receipt_id"], receipt_id)
        self.assertEqual(mapping["previous_graph_sha256"], receipt_sha256)

        rebound = json.loads(json.dumps(prior_graph))
        rebound["receipt_id"] = "f" * 32
        with self.assertRaisesRegex(ValueError, "exact prior graph binding"):
            DELTA.bind_delta_context(
                self.root,
                trusted_previous(),
                previous_state(),
                rebound,
                previous_report_id="RPT-001",
                previous_revision=2,
                changed_paths=("a.py",),
                configured_max_seconds=3,
                previous_graph_receipt_id=receipt_id,
                previous_graph_sha256=receipt_sha256,
            )

    def test_seed_selection_caps_max_changed_paths_with_omission_frontier(self):
        changed_paths = tuple(f"changed/{index:04d}.py" for index in range(4096))
        prior_graph = graph_receipt(self.root)
        receipt_id, receipt_sha256 = graph_identity(prior_graph)
        state = previous_state()
        state["preserved_invariants"] = []
        state["criteria"] = []
        context = DELTA.bind_delta_context(
            self.root,
            trusted_previous(changed_paths=changed_paths),
            state,
            prior_graph,
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=changed_paths,
            configured_max_seconds=3,
            previous_graph_receipt_id=receipt_id,
            previous_graph_sha256=receipt_sha256,
        )

        selection = DELTA.derive_delta_seed_selection(context)
        frontier = DELTA.surviving_frontier(context, {}, selection)

        self.assertEqual(len(selection.seeds), 512)
        self.assertEqual(selection.omitted_count, 3588)
        self.assertEqual(selection.omitted_by_source["previous-lookup"], 3584)
        self.assertEqual(selection.omitted_by_source["previous-graph-path"], 4)
        self.assertTrue(any(row.get("omitted_count") == 3588 for row in frontier))

    def test_seed_selection_caps_after_changed_path_then_511_prior_nodes(self):
        nodes = [
            {
                "id": f"NODE-{index:03d}",
                "label": f"prior-{index}",
                "location": f"prior/{index:03d}.py",
                "source_sha256": "a" * 64,
            }
            for index in range(1, 513)
        ]
        prior_graph = {
            "receipt_id": "b" * 32,
            "repo_root_sha256": hashlib.sha256(str(self.root.resolve()).encode()).hexdigest(),
            "nodes": nodes,
            "paths": [
                {
                    "id": f"PATH-{index:03d}",
                    "nodes": [nodes[index * 2]["id"], nodes[index * 2 + 1]["id"]],
                }
                for index in range(256)
            ],
            "frontier": [],
        }
        receipt_id, receipt_sha256 = graph_identity(prior_graph)
        state = previous_state()
        state["preserved_invariants"] = []
        state["criteria"] = []
        context = DELTA.bind_delta_context(
            self.root,
            trusted_previous(changed_paths=("changed.py",)),
            state,
            prior_graph,
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("changed.py",),
            configured_max_seconds=3,
            previous_graph_receipt_id=receipt_id,
            previous_graph_sha256=receipt_sha256,
        )

        selection = DELTA.derive_delta_seed_selection(context)

        self.assertEqual(selection.seeds[0].location, "changed.py")
        self.assertEqual(len(selection.seeds), 512)
        self.assertEqual(selection.omitted_count, 1)
        self.assertEqual(selection.omitted_by_source, {"previous-graph-path": 1})

    def test_graph_disabled_schema2_context_runs_partial_with_non_graph_seeds(self):
        state = previous_state()
        state["settings"] = {"impact_graph": {"enabled": False}}
        context = DELTA.bind_delta_context(
            self.root,
            trusted_previous(),
            state,
            {},
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("a.py",),
            configured_max_seconds=3,
            prior_graph_status="disabled",
            previous_graph_receipt_id=None,
            previous_graph_sha256=None,
        )

        selection = DELTA.derive_delta_seed_selection(context)
        fallback = DELTA.delta_timeout_fallback(context, 5)
        current = graph_receipt(self.root)
        result = FAST_SCAN.execute_fast_scan(
            FAST_SCAN.FastScanRequest(
                self.root,
                "Change OriginSignal negotiation",
                (),
                "technical",
                previous_report_id="RPT-001",
                previous_revision=2,
                changed_paths=("a.py",),
            ),
            current["settings"],
            "8" * 64,
            coordinator=lambda *_args, **_kwargs: current,
            delta_context=context,
        )

        self.assertEqual(context.prior_graph_status, "disabled")
        self.assertEqual(selection.seeds[0].location, "a.py")
        self.assertIn("checks/missing.py", {seed.location for seed in selection.seeds})
        self.assertTrue(
            any("prior graph disabled" in row["reason"] for row in fallback["frontier"])
        )
        self.assertEqual(result.status, "partial")
        self.assertFalse(result.can_promote)

        started = time.monotonic()
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )
        timed_out = CONTROLLER._execute_delta_worker(
            request,
            1,
            started,
            worker_path=SLOW_WORKER,
            worker_environment={"RIR_DELTA_TEST_SCENARIO": "after-fallback"},
        )
        self.assertEqual(timed_out.previous_report_id, "RPT-001")
        self.assertEqual(timed_out.status, "partial")
        self.assertFalse(timed_out.can_promote)

    def test_dense_timeout_fallback_reserves_deadline_and_origin_omission_summary(self):
        changed_paths = tuple(f"changed/{index:04d}.py" for index in range(4096))
        prior_graph = graph_receipt(self.root)
        prior_graph["nodes"] = [
            {
                "id": f"NODE-{index:03d}",
                "kind": "symbol",
                "label": f"prior-{index}",
                "location": f"prior/{index:03d}.py",
                "provider": "builtin",
                "confidence": "structural-inferred",
                "source_sha256": "a" * 64,
                "risk_domains": ["regression"],
            }
            for index in range(1, 513)
        ]
        prior_graph["edges"] = [
            {
                "id": f"EDGE-{index:03d}",
                "source": f"NODE-{index * 2 - 1:03d}",
                "target": f"NODE-{index * 2:03d}",
                "kind": "references",
                "location": f"prior/{index * 2:03d}.py",
                "evidence": f"dependency-{index}",
                "confidence": "structural-inferred",
                "provider": "builtin",
                "source_sha256": "a" * 64,
            }
            for index in range(1, 257)
        ]
        prior_graph["paths"] = [
            {
                "id": f"PATH-{index:03d}",
                "nodes": [f"NODE-{index * 2 - 1:03d}", f"NODE-{index * 2:03d}"],
                "edges": [f"EDGE-{index:03d}"],
                "distance": 1,
                "risk_domains": ["regression"],
            }
            for index in range(1, 257)
        ]
        self.assertEqual(CONTROLLER.GRAPH.validate_receipt(prior_graph), ())
        prior_graph_id, prior_graph_sha256 = graph_identity(prior_graph)
        state = previous_state()
        context = DELTA.bind_delta_context(
            self.root,
            trusted_previous(changed_paths=changed_paths),
            state,
            prior_graph,
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=changed_paths,
            configured_max_seconds=3,
            prior_graph_status="bound",
            previous_graph_receipt_id=prior_graph_id,
            previous_graph_sha256=prior_graph_sha256,
        )

        fallback = DELTA.delta_timeout_fallback(context, 3)
        frontier = fallback["frontier"]
        summary = next(
            row for row in frontier if row.get("provenance") == "delta-frontier-capacity"
        )

        self.assertEqual(len(frontier), 1024)
        self.assertEqual(frontier[0]["location"], "changed/0000.py")
        self.assertEqual(frontier[-1]["provenance"], "delta-worker-deadline")
        self.assertGreater(summary["omitted_count"], 0)
        self.assertGreater(summary["omitted_by_origin"]["previous-lookup"], 0)
        self.assertGreater(summary["omitted_by_origin"]["previous-graph-path"], 0)
        self.assertEqual(fallback["status"], "partial")
        self.assertFalse(fallback["can_promote"])

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
        payload_sha256 = "e" * 64
        repository_evidence_sha256 = "f" * 64
        context_identity = {
            "payload_sha256": payload_sha256,
            "repo_root_sha256": hashlib.sha256(str(self.root.resolve()).encode()).hexdigest(),
            "requirement_sha256": "c" * 64,
            "state_sha256": hashlib.sha256(state_payload).hexdigest(),
            "repository_evidence_sha256": repository_evidence_sha256,
            "source_inventory_available": True,
            "source_inventory_complete": True,
            "source_inventory_git_tracked_only": True,
            "source_inventory_sha256": "d" * 64,
        }
        controller = {
            "schema_version": 2,
            "draft_id": receipt["draft_id"],
            "report_id": "RPT-001",
            "revision": 2,
            "state_sha256": hashlib.sha256(state_payload).hexdigest(),
            "key_map": {},
            "graph_receipt": {
                "receipt_id": receipt["receipt_id"],
                "sha256": hashlib.sha256(receipt_payload).hexdigest(),
            },
            "analysis_sha256": "9" * 64,
            "context_identity": context_identity,
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

        schema1 = dict(controller)
        schema1["schema_version"] = 1
        schema1.pop("analysis_sha256")
        schema1.pop("context_identity")
        controller_path.write_bytes(
            json.dumps(schema1, sort_keys=True, separators=(",", ":")).encode()
        )
        with self.assertRaisesRegex(ValueError, "schema version 2"):
            DELTA.load_trusted_previous_artifacts(
                self.root,
                trusted,
                state_loader=lambda payload: (json.loads(payload), []),
                receipt_loader=lambda payload: (json.loads(payload), []),
                canonical_receipt_bytes=lambda value: json.dumps(
                    value, sort_keys=True, separators=(",", ":")
                ).encode(),
                max_receipt_bytes=4 * 1024 * 1024,
                expected_payload_sha256=payload_sha256,
                expected_repository_evidence_sha256=repository_evidence_sha256,
            )
        controller_path.write_bytes(
            json.dumps(controller, sort_keys=True, separators=(",", ":")).encode()
        )

        (
            loaded_state,
            loaded_graph,
            loaded_graph_status,
            loaded_receipt_id,
            loaded_receipt_sha256,
        ) = DELTA.load_trusted_previous_artifacts(
            self.root,
            trusted,
            state_loader=lambda payload: (json.loads(payload), []),
            receipt_loader=lambda payload: (json.loads(payload), []),
            canonical_receipt_bytes=lambda value: json.dumps(
                value, sort_keys=True, separators=(",", ":")
            ).encode(),
            max_receipt_bytes=4 * 1024 * 1024,
            expected_payload_sha256=payload_sha256,
            expected_repository_evidence_sha256=repository_evidence_sha256,
        )

        self.assertEqual(loaded_state, state)
        self.assertEqual(loaded_graph, receipt)
        self.assertEqual(loaded_graph_status, "bound")
        self.assertEqual(loaded_receipt_id, receipt["receipt_id"])
        self.assertEqual(loaded_receipt_sha256, hashlib.sha256(receipt_payload).hexdigest())

        disabled_state = previous_state()
        disabled_state["settings"] = {"impact_graph": {"enabled": False}}
        disabled_state_payload = (
            json.dumps(disabled_state, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        (report_dir / state_name).write_bytes(disabled_state_payload)
        disabled_controller = dict(controller)
        disabled_controller.pop("graph_receipt")
        disabled_controller["state_sha256"] = hashlib.sha256(disabled_state_payload).hexdigest()
        disabled_context = dict(context_identity)
        disabled_context["state_sha256"] = disabled_controller["state_sha256"]
        disabled_controller["context_identity"] = disabled_context
        controller_path.write_bytes(
            json.dumps(disabled_controller, sort_keys=True, separators=(",", ":")).encode()
        )
        disabled = DELTA.load_trusted_previous_artifacts(
            self.root,
            trusted,
            state_loader=lambda payload: (json.loads(payload), []),
            receipt_loader=lambda payload: (json.loads(payload), []),
            canonical_receipt_bytes=lambda value: json.dumps(
                value, sort_keys=True, separators=(",", ":")
            ).encode(),
            max_receipt_bytes=4 * 1024 * 1024,
            expected_payload_sha256=payload_sha256,
            expected_repository_evidence_sha256=repository_evidence_sha256,
        )
        self.assertEqual(disabled[1], {})
        self.assertEqual(disabled[2:], ("disabled", None, None))

        (report_dir / state_name).write_bytes(state_payload)
        controller_path.write_bytes(
            json.dumps(controller, sort_keys=True, separators=(",", ":")).encode()
        )

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

        (
            promoted_state,
            promoted_graph,
            promoted_graph_status,
            promoted_receipt_id,
            promoted_receipt_sha256,
        ) = DELTA.load_trusted_previous_artifacts(
            self.root,
            trusted,
            state_loader=lambda payload: (json.loads(payload), []),
            receipt_loader=lambda payload: (json.loads(payload), []),
            canonical_receipt_bytes=lambda value: json.dumps(
                value, sort_keys=True, separators=(",", ":")
            ).encode(),
            max_receipt_bytes=4 * 1024 * 1024,
            expected_payload_sha256=payload_sha256,
            expected_repository_evidence_sha256=repository_evidence_sha256,
        )
        self.assertEqual(promoted_state, state)
        self.assertEqual(promoted_graph, promoted_receipt)
        self.assertEqual(promoted_graph_status, "bound")
        self.assertEqual(promoted_receipt_id, promoted_receipt["receipt_id"])
        self.assertEqual(
            promoted_receipt_sha256, hashlib.sha256(promoted_receipt_payload).hexdigest()
        )

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
                expected_payload_sha256=payload_sha256,
                expected_repository_evidence_sha256=repository_evidence_sha256,
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

    def test_whole_call_worker_bounds_slow_preflight_and_post_fallback_stages(self):
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )
        for scenario in (
            "settings",
            "lookup",
            "artifact",
            "hash",
            "provider",
            "persist",
            "render",
        ):
            with self.subTest(scenario=scenario):
                started = time.monotonic()
                result = CONTROLLER._execute_delta_worker(
                    request,
                    1,
                    started,
                    worker_path=SLOW_WORKER,
                    worker_environment={"RIR_DELTA_TEST_SCENARIO": scenario},
                )
                actual_ms = round((time.monotonic() - started) * 1000)
                self.assertLessEqual(actual_ms, 1_125)
                self.assertGreaterEqual(result.elapsed_ms, 900)
                self.assertLessEqual(abs(result.elapsed_ms - actual_ms), 25)
                self.assertEqual(result.status, "partial")
                self.assertFalse(result.can_promote)
                if scenario in {"settings", "lookup", "artifact"}:
                    self.assertIsNone(result.previous_report_id)
                    self.assertEqual(result.changed_paths, ())
                    self.assertEqual(result.paths, ())
                    self.assertIn("preflight", result.display_text)
                else:
                    self.assertEqual(result.previous_report_id, "RPT-001")
                    self.assertEqual(result.changed_paths, ("a.py",))
                self.assertFalse(list((self.root / ".requirements-impact-refiner").rglob("*.tmp")))

    def test_complete_trusted_frame_handles_partial_overflow_garbage_and_extra_frames(self):
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )
        for scenario in ("partial-frame", "overflow", "garbage", "extra-frame"):
            with self.subTest(scenario=scenario):
                started = time.monotonic()
                result = CONTROLLER._execute_delta_worker(
                    request,
                    1,
                    started,
                    worker_path=SLOW_WORKER,
                    worker_environment={"RIR_DELTA_TEST_SCENARIO": scenario},
                )
                actual_ms = round((time.monotonic() - started) * 1000)
                self.assertLessEqual(actual_ms, 1_125)
                self.assertEqual(result.status, "partial")
                self.assertFalse(result.can_promote)
                self.assertEqual(result.previous_report_id, "RPT-001")
                self.assertEqual(result.previous_revision, 2)
                self.assertEqual(result.changed_paths, ("a.py",))

    def test_complete_authenticated_fallback_and_result_frames_return_result(self):
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )

        result = CONTROLLER._execute_delta_worker(
            request,
            1,
            time.monotonic(),
            worker_path=SLOW_WORKER,
            worker_environment={"RIR_DELTA_TEST_SCENARIO": "success"},
        )

        self.assertEqual(result.status, "complete")
        self.assertTrue(result.can_promote)
        self.assertEqual(result.previous_report_id, "RPT-001")
        self.assertEqual(result.changed_paths, ("a.py",))

    def test_precontrol_worker_is_bounded_by_one_second_and_late_control_is_rejected(self):
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )

        for scenario in ("settings", "late-control"):
            with self.subTest(scenario=scenario):
                started = time.monotonic()
                result = CONTROLLER._execute_delta_worker(
                    request,
                    3,
                    started,
                    worker_path=SLOW_WORKER,
                    worker_environment={"RIR_DELTA_TEST_SCENARIO": scenario},
                )
                actual_ms = round((time.monotonic() - started) * 1000)

                self.assertGreaterEqual(actual_ms, 900)
                self.assertLessEqual(actual_ms, 1_125)
                self.assertLessEqual(abs(result.elapsed_ms - actual_ms), 25)
                self.assertEqual(result.status, "partial")
                self.assertFalse(result.can_promote)
                self.assertIsNone(result.previous_report_id)
                self.assertEqual(result.changed_paths, ())
                self.assertIn("preflight", result.display_text)

    def test_prompt_two_and_three_second_control_frames_extend_the_deadline(self):
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )

        for scenario in ("configured-two-success", "configured-three-success"):
            with self.subTest(scenario=scenario):
                started = time.monotonic()
                result = CONTROLLER._execute_delta_worker(
                    request,
                    3,
                    started,
                    worker_path=SLOW_WORKER,
                    worker_environment={"RIR_DELTA_TEST_SCENARIO": scenario},
                )
                actual_ms = round((time.monotonic() - started) * 1000)

                self.assertGreaterEqual(actual_ms, 1_000)
                self.assertLessEqual(actual_ms, 1_500)
                self.assertLessEqual(abs(result.elapsed_ms - actual_ms), 25)
                self.assertEqual(result.status, "complete")
                self.assertTrue(result.can_promote)

    def test_worker_parser_requires_exact_control_fallback_result_order(self):
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )
        token = "a" * 32
        fallback = {
            "status": "partial",
            "scan_id": "1" * 32,
            "receipt_id": "2" * 32,
            "receipt_sha256": "3" * 64,
            "display_text": "trusted previous then fallback",
            "risk_level": "unknown",
            "paths": [],
            "frontier": [],
            "candidates": [],
            "elapsed_ms": 0,
            "cache_status": "bypassed",
            "can_promote": False,
            "previous_report_id": "RPT-001",
            "previous_revision": 2,
            "changed_paths": ["a.py"],
            "changed_count": 1,
            "previous_display_text": "trusted previous",
        }
        result = dict(fallback)
        result["status"] = "complete"
        result["can_promote"] = True

        def framed(kind, payload):
            body = json.dumps(
                {"kind": kind, "payload": payload, "token": token},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            return f"{len(body):08x}\n".encode() + body

        control = framed("control", {"effective_max_seconds": 3})
        fallback_frame = framed("trusted_fallback", fallback)
        result_frame = framed("result", result)
        valid = CONTROLLER._DeltaWorkerFrameParser(token, request)
        self.assertTrue(valid.feed(control + fallback_frame + result_frame))
        self.assertTrue(valid.complete())
        self.assertIsNotNone(valid.result)

        invalid_streams = (
            fallback_frame,
            result_frame + control + fallback_frame,
            control + result_frame,
            control + control + fallback_frame + result_frame,
            framed("control", {"effective_max_seconds": 0}) + fallback_frame + result_frame,
            framed("control", {"effective_max_seconds": 4}) + fallback_frame + result_frame,
            framed("control", {"effective_max_seconds": True}) + fallback_frame + result_frame,
        )
        for stream in invalid_streams:
            with self.subTest(prefix=stream[:32]):
                parser = CONTROLLER._DeltaWorkerFrameParser(token, request)
                self.assertFalse(parser.feed(stream))
                self.assertFalse(parser.complete())

        for incomplete in (control, control + fallback_frame):
            with self.subTest(incomplete=incomplete[:32]):
                parser = CONTROLLER._DeltaWorkerFrameParser(token, request)
                self.assertTrue(parser.feed(incomplete))
                self.assertFalse(parser.complete())

    def test_process_rejects_invalid_first_control_and_out_of_order_frames(self):
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )
        pretrust_scenarios = (
            "fallback-before-control",
            "result-before-control",
            "result-without-fallback",
            "duplicate-control",
            "invalid-control",
            "forged-control",
        )

        for scenario in pretrust_scenarios:
            with self.subTest(scenario=scenario):
                started = time.monotonic()
                result = CONTROLLER._execute_delta_worker(
                    request,
                    3,
                    started,
                    worker_path=SLOW_WORKER,
                    worker_environment={"RIR_DELTA_TEST_SCENARIO": scenario},
                )

                self.assertLessEqual(round((time.monotonic() - started) * 1000), 500)
                self.assertEqual(result.status, "partial")
                self.assertFalse(result.can_promote)
                self.assertIsNone(result.previous_report_id)
                self.assertEqual(result.changed_paths, ())

        trusted = CONTROLLER._execute_delta_worker(
            request,
            3,
            time.monotonic(),
            worker_path=SLOW_WORKER,
            worker_environment={"RIR_DELTA_TEST_SCENARIO": "control-after-fallback"},
        )
        self.assertEqual(trusted.status, "partial")
        self.assertFalse(trusted.can_promote)
        self.assertEqual(trusted.previous_report_id, "RPT-001")
        self.assertEqual(trusted.changed_paths, ("a.py",))

    def test_elapsed_includes_cleanup_without_clamping_to_worker_budget(self):
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )
        real_cleanup = CONTROLLER._cleanup_delta_worker_temps

        def delayed_cleanup(root, token, *args, **kwargs):
            cleaned = real_cleanup(root, token, *args, **kwargs)
            time.sleep(0.125)
            return cleaned

        started = time.monotonic()
        with mock.patch.object(
            CONTROLLER,
            "_cleanup_delta_worker_temps",
            side_effect=delayed_cleanup,
        ):
            result = CONTROLLER._execute_delta_worker(
                request,
                3,
                started,
                worker_path=SLOW_WORKER,
                worker_environment={"RIR_DELTA_TEST_SCENARIO": "configured-one"},
            )
        actual_ms = round((time.monotonic() - started) * 1000)

        self.assertLessEqual(abs(result.elapsed_ms - actual_ms), 25)
        self.assertGreater(result.elapsed_ms, 1_000)
        self.assertEqual(result.status, "partial")
        self.assertFalse(result.can_promote)
        self.assertEqual(result.previous_report_id, "RPT-001")

    def test_cleanup_failure_downgrades_complete_result_to_trusted_fallback(self):
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )
        real_cleanup = CONTROLLER._cleanup_delta_worker_temps

        def failed_cleanup(root, token, *args, **kwargs):
            real_cleanup(root, token, *args, **kwargs)
            return False

        with mock.patch.object(
            CONTROLLER,
            "_cleanup_delta_worker_temps",
            side_effect=failed_cleanup,
        ):
            result = CONTROLLER._execute_delta_worker(
                request,
                1,
                time.monotonic(),
                worker_path=SLOW_WORKER,
                worker_environment={"RIR_DELTA_TEST_SCENARIO": "success"},
            )

        self.assertEqual(result.status, "partial")
        self.assertFalse(result.can_promote)
        self.assertEqual(result.previous_report_id, "RPT-001")
        self.assertEqual(result.changed_paths, ("a.py",))

    def test_worker_temp_cleanup_is_nonrecursive_and_reports_unexpected_directory(self):
        worker_temp = Path(self.temporary.name) / "worker-temp"
        worker_temp.mkdir()
        input_path = worker_temp / "input.json"
        input_path.write_text("{}", encoding="ascii")
        nested = worker_temp / "unexpected"
        nested.mkdir()
        (nested / "untrusted").write_text("data", encoding="ascii")

        cleaned = CONTROLLER._cleanup_delta_worker_directory(
            worker_temp,
            input_path,
            time.monotonic() + 0.1,
        )

        self.assertFalse(cleaned)
        self.assertFalse(input_path.exists())
        self.assertTrue(nested.is_dir())

    def test_cleanup_helpers_bound_entries_deadlines_and_private_temp_shapes(self):
        missing = Path(self.temporary.name) / "missing-worker-temp"
        self.assertFalse(
            CONTROLLER._cleanup_delta_worker_directory(
                missing,
                missing / "wrong-name",
                time.monotonic() + 0.1,
            )
        )
        self.assertFalse(
            CONTROLLER._cleanup_delta_worker_directory(
                missing,
                missing / "input.json",
                time.monotonic() + 0.1,
            )
        )

        expired = Path(self.temporary.name) / "expired-worker-temp"
        expired.mkdir()
        expired_input = expired / "input.json"
        expired_input.write_text("{}", encoding="ascii")
        self.assertFalse(
            CONTROLLER._cleanup_delta_worker_directory(
                expired,
                expired_input,
                time.monotonic() - 1,
            )
        )
        self.assertFalse(expired.exists())

        direct = Path(self.temporary.name) / "direct-worker-temp"
        direct.mkdir()
        (direct / "direct-file").write_text("temporary", encoding="ascii")
        (direct / "empty-directory").mkdir()
        self.assertTrue(
            CONTROLLER._cleanup_delta_worker_directory(
                direct,
                direct / "input.json",
                time.monotonic() + 0.1,
            )
        )
        self.assertFalse(direct.exists())

        token = "b" * 32
        scans = self.root / ".requirements-impact-refiner" / "scans"
        scans.mkdir(parents=True)
        removable = scans / f".scan.{token}.payload.tmp"
        removable.write_text("partial", encoding="ascii")
        unexpected = scans / f".scan.{token}.directory.tmp"
        unexpected.mkdir()
        self.assertFalse(
            CONTROLLER._cleanup_delta_worker_temps(
                self.root,
                token,
                time.monotonic() + 0.1,
            )
        )
        self.assertFalse(removable.exists())
        self.assertTrue(unexpected.is_dir())
        self.assertFalse(
            CONTROLLER._cleanup_delta_worker_temps(
                self.root,
                token,
                time.monotonic() - 1,
            )
        )

    def test_forged_fallback_frame_is_not_retained_as_trusted(self):
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )

        result = CONTROLLER._execute_delta_worker(
            request,
            1,
            time.monotonic(),
            worker_path=SLOW_WORKER,
            worker_environment={"RIR_DELTA_TEST_SCENARIO": "forged-frame"},
        )

        self.assertIsNone(result.previous_report_id)
        self.assertEqual(result.changed_paths, ())
        self.assertIn("preflight", result.display_text)
        self.assertFalse(result.can_promote)

    def test_whole_call_timeout_kills_descendants_and_leaves_no_zombie(self):
        marker = Path(self.temporary.name) / "descendant-marker"
        child_pid_path = Path(self.temporary.name) / "descendant.pid"
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )
        started = time.monotonic()
        result = CONTROLLER._execute_delta_worker(
            request,
            1,
            started,
            worker_path=SLOW_WORKER,
            worker_environment={
                "RIR_DELTA_TEST_SCENARIO": "descendant",
                "RIR_DELTA_TEST_MARKER": str(marker),
                "RIR_DELTA_TEST_CHILD_PID": str(child_pid_path),
            },
        )
        actual_ms = round((time.monotonic() - started) * 1000)

        self.assertEqual(result.status, "partial")
        self.assertLessEqual(actual_ms, 1_125)
        self.assertTrue(child_pid_path.is_file())
        child_pid = int(child_pid_path.read_text(encoding="ascii"))
        deadline = time.monotonic() + 1.0
        while process_exists(child_pid) and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(process_exists(child_pid), "delta worker descendant survived cleanup")
        self.assertFalse(marker.exists(), "delta worker descendant executed after timeout")

    def test_authenticated_control_frame_tightens_configured_deadline_to_one_second(self):
        request = CONTROLLER.ScanRequest(
            self.root,
            "Change OriginSignal negotiation",
            (),
            "technical",
            "RPT-001",
            2,
            ("a.py",),
        )
        started = time.monotonic()

        result = CONTROLLER._execute_delta_worker(
            request,
            3,
            started,
            worker_path=SLOW_WORKER,
            worker_environment={"RIR_DELTA_TEST_SCENARIO": "configured-one"},
        )

        actual_ms = round((time.monotonic() - started) * 1000)
        self.assertGreaterEqual(actual_ms, 850)
        self.assertLessEqual(actual_ms, 1_100)
        self.assertLessEqual(abs(result.elapsed_ms - actual_ms), 100)
        self.assertEqual(result.previous_report_id, "RPT-001")
        self.assertEqual(result.status, "partial")
        self.assertFalse(result.can_promote)

    def test_worker_emits_authenticated_control_fallback_then_result_frames(self):
        input_path = Path(self.temporary.name) / "worker-input.json"
        token = "a" * 32
        parent_pid = os.getppid()
        value = {
            "schema_version": 1,
            "repo_root": str(self.root.resolve()),
            "change_request": "Change OriginSignal negotiation",
            "evidence": [],
            "audience_override": "technical",
            "previous_report_id": "RPT-001",
            "previous_revision": 2,
            "changed_paths": ["a.py"],
            "operation_started": time.monotonic(),
            "max_seconds": 3,
            "worker_token": token,
            "parent_pid": parent_pid,
        }
        payload = (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        input_path.write_bytes(payload)
        input_path.chmod(0o600)
        fallback = DELTA.delta_timeout_fallback(self.chain_context(), 1)
        final = SimpleNamespace(
            status="partial",
            scan_id="1" * 32,
            receipt_id="2" * 32,
            receipt_sha256="3" * 64,
            display_text="trusted previous then result",
            risk_level="unknown",
            paths=(),
            frontier=(),
            candidates=(),
            elapsed_ms=2,
            cache_status="miss",
            can_promote=False,
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("a.py",),
            changed_count=1,
            previous_display_text="trusted previous",
        )

        def execute(
            request,
            *,
            operation_started,
            _worker_control_callback,
            _worker_fallback_callback,
        ):
            self.assertEqual(request.previous_report_id, "RPT-001")
            self.assertIsInstance(operation_started, float)
            _worker_control_callback(2)
            _worker_fallback_callback(fallback)
            return final

        with (
            mock.patch.object(
                WORKER.rir_controller,
                "_configure_delta_worker_runtime",
            ) as configure,
            mock.patch.object(
                WORKER.rir_controller, "_scan_impact_in_process", side_effect=execute
            ),
            mock.patch.object(WORKER, "_emit") as emit,
        ):
            scan_exit = WORKER.main(
                [
                    "--input",
                    str(input_path),
                    "--sha256",
                    hashlib.sha256(payload).hexdigest(),
                    "--token",
                    token,
                    "--parent-pid",
                    str(parent_pid),
                ]
            )

        self.assertEqual(scan_exit, 0)
        configure.assert_called_once_with(token)
        self.assertEqual(
            emit.call_args_list,
            [
                mock.call("control", {"effective_max_seconds": 2}, token),
                mock.call("trusted_fallback", fallback, token),
                mock.call("result", CONTROLLER._scan_result_mapping(final), token),
            ],
        )

        with tempfile.TemporaryFile(mode="w+b") as output:
            with mock.patch.object(WORKER.sys, "stdout", output):
                WORKER._emit("trusted_fallback", fallback, token)
            output.seek(0)
            self.assertEqual(
                CONTROLLER._delta_worker_frame(output.read(), token),
                ("trusted_fallback", fallback),
            )

        with self.assertRaisesRegex(ValueError, "digest"):
            WORKER._read_input(input_path, "0" * 64)

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
        second_graph = graph_receipt(self.root)
        second_graph_id, second_graph_sha256 = graph_identity(second_graph)
        second = DELTA.bind_delta_context(
            self.root,
            trusted_previous(revision=3, changed_paths=("c.py",)),
            previous_state(revision=3),
            second_graph,
            previous_report_id="RPT-001",
            previous_revision=3,
            changed_paths=("c.py",),
            configured_max_seconds=3,
            previous_graph_receipt_id=second_graph_id,
            previous_graph_sha256=second_graph_sha256,
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
        prior_graph = graph_receipt(self.root)
        prior_graph_id, prior_graph_sha256 = graph_identity(prior_graph)
        context = DELTA.bind_delta_context(
            self.root,
            trusted_previous(),
            complete_state,
            prior_graph,
            previous_report_id="RPT-001",
            previous_revision=2,
            changed_paths=("a.py",),
            configured_max_seconds=3,
            previous_graph_receipt_id=prior_graph_id,
            previous_graph_sha256=prior_graph_sha256,
        )
        output_graph = json.loads(
            (ROOT / "tests" / "fixtures" / "impact-graph-receipt.json").read_text(encoding="utf-8")
        )
        output_graph["budget_status"] = "closed"
        output_graph["frontier"] = []
        current_graph = graph_receipt(self.root)
        output_graph["nodes"] = current_graph["nodes"]
        output_graph["edges"] = current_graph["edges"]
        output_graph["paths"] = current_graph["paths"]
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

    def test_fast_scan_schema_declares_optional_delta_context(self):
        schema = json.loads(
            (ROOT / "schemas" / "fast-impact-scan.schema.json").read_text(encoding="utf-8")
        )

        self.assertIn("delta_context", schema["properties"])
        self.assertNotIn("delta_context", schema["required"])
        delta = schema["properties"]["delta_context"]
        self.assertEqual(delta["properties"]["max_seconds"]["maximum"], 3)
        self.assertIn("previous_graph_receipt_id", delta["required"])
        self.assertIn("previous_graph_sha256", delta["required"])
        self.assertIn("omitted_seed_count", delta["required"])
        self.assertIn("omitted_seed_provenance", delta["required"])

    def test_delta_runtime_is_payload_bound_and_installed_mirrors_are_exact(self):
        self.assertIn("scripts/rir_delta.py", CONTROLLER.PAYLOAD_IDENTITY.ROOT_FILES)
        pairs = (
            ("rir_delta.py", "rir_delta.py"),
            ("rir_delta_worker.py", "rir_delta_worker.py"),
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
