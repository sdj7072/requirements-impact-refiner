import hashlib
import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "skills" / "requirements-impact-refiner" / "scripts" / "graph_coordinator.py"
)
SPEC = importlib.util.spec_from_file_location("graph_coordinator", MODULE_PATH)
COORDINATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = COORDINATOR
SPEC.loader.exec_module(COORDINATOR)


class FakeClock:
    def __init__(self, current=0.0):
        self.current = current

    def monotonic(self):
        return self.current

    def advance(self, seconds):
        self.current += seconds

    def advance_to(self, current):
        self.current = current


class NeverRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        raise AssertionError("provider process should not run")


class FakeAdapter:
    def __init__(self, result, calls, *, advance=0):
        self.result = result
        self.calls = calls
        self.advance = advance

    def probe(self, spec, root, deadline, runner):
        self.calls.append(("probe", spec.name))
        return COORDINATOR.ProviderProbe(
            spec.name, "ready", "verified-provider", spec.executable,
            "1.0", "a" * 64,
        )

    def query(self, probe, seeds, deadline, runner):
        self.calls.append(("query", probe.name, tuple(seed.term for seed in seeds)))
        if self.advance:
            deadline.clock.advance(self.advance)
        return self.result


def candidate_result(provider, *, edge_kind="references", status="ready", nodes=None):
    values = nodes or (
        {
            "key": "source", "kind": "api_field", "label": "profile.displayName",
            "location": "api/profile.py", "confidence": "verified-provider",
            "source_sha256": "a" * 64, "risk_domains": ("interfaces",),
        },
        {
            "key": "target", "kind": "cache", "label": "profile-cache",
            "location": "desktop/profile_cache.ts", "confidence": "verified-provider",
            "source_sha256": "b" * 64, "risk_domains": ("data",),
        },
    )
    return COORDINATOR.ProviderResult(
        provider, status, "verified-provider", values,
        ({
            "source": "source", "target": "target", "kind": edge_kind,
            "location": "desktop/profile_cache.ts", "evidence": "provider relationship",
            "confidence": "verified-provider", "source_sha256": "b" * 64,
        },) if status == "ready" and nodes is None else (),
        raw_receipt_sha256=("c" * 64,),
    )


class GraphCoordinatorTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        (self.root / "api").mkdir()
        (self.root / "desktop").mkdir()
        (self.root / "api/profile.py").write_text(
            'FIELD = "profile.displayName"\n', encoding="utf-8"
        )
        (self.root / "desktop/profile_cache.ts").write_text(
            'const key = "profile.displayName";\n', encoding="utf-8"
        )
        self.draft = {"draft_id": "1" * 32, "request": "rename display name"}
        self.seeds = (COORDINATOR.ScanSeed("profile.displayName", "api/profile.py"),)
        self.settings = COORDINATOR.GraphSettings(
            providers=("builtin",), max_seconds=30, target_seconds=10,
        )
        self.clock = FakeClock()
        self.runner = NeverRunner()

    def test_coordinator_stops_closed_frontier_without_spending_30_seconds(self):
        receipt = COORDINATOR.trace_impact(
            self.root, self.draft, self.seeds, self.settings,
            clock=self.clock, runner=self.runner,
        )
        self.assertEqual(receipt.budget_status, "closed")
        self.assertLess(receipt.timings_ms["total"], 10_000)
        self.assertEqual(self.runner.calls, [])

    def test_coordinator_reuses_supplied_shared_deadline(self):
        deadline = COORDINATOR.Deadline(self.clock, 30)
        self.clock.advance(5)

        receipt = COORDINATOR.trace_impact(
            self.root, self.draft, self.seeds, self.settings,
            clock=self.clock, runner=self.runner, deadline=deadline,
        )

        self.assertGreaterEqual(receipt.timings_ms["total"], 5_000)

    def test_budget_exhaustion_preserves_high_risk_frontier_without_scheduling_work(self):
        self.clock.advance_to(30.0)
        clock = FakeClock(30.0)
        deadline = COORDINATOR.Deadline(clock, 0)
        with mock.patch.object(COORDINATOR, "Deadline", return_value=deadline):
            receipt = COORDINATOR.trace_impact(
                self.root, self.draft,
                (COORDINATOR.ScanSeed("authorization.profile", "api/profile.py"),),
                self.settings, clock=clock, runner=self.runner,
            )
        self.assertEqual(receipt.budget_status, "budget_exhausted")
        self.assertTrue(receipt.frontier)
        self.assertIn("authorization/privacy", receipt.frontier[0].risk_domains)
        self.assertEqual(self.runner.calls, [])

    def test_pre_scan_inventory_explicitly_reports_deadline_and_collection_limits(self):
        expired = COORDINATOR.Deadline(self.clock, 0)
        deadline_inventory = COORDINATOR._collect_source_digests(
            self.root, expired
        )
        self.assertFalse(deadline_inventory.complete)
        self.assertEqual(deadline_inventory.reason, "deadline")
        self.assertEqual(dict(deadline_inventory.digests), {})

        limited_root = Path(self.temporary.name) / "limited"
        limited_root.mkdir()
        for index in range(501):
            (limited_root / f"source_{index:03d}.py").write_text(
                f'VALUE = "profile.displayName-{index}"\n', encoding="utf-8"
            )
        limited_inventory = COORDINATOR._collect_source_digests(
            limited_root, COORDINATOR.Deadline(self.clock, 30)
        )
        self.assertFalse(limited_inventory.complete)
        self.assertEqual(limited_inventory.reason, "collection-limit")
        self.assertEqual(len(limited_inventory.digests), 500)

    def test_no_workspace_preserves_supplied_only_evidence(self):
        missing = self.root / "missing"
        receipt = COORDINATOR.trace_impact(
            missing, self.draft,
            (COORDINATOR.ScanSeed("profile.displayName", None),), self.settings,
            clock=self.clock, runner=self.runner,
        )
        self.assertEqual(receipt.budget_status, "no_workspace")
        self.assertEqual(receipt.nodes[0].location, None)
        self.assertIn("supplied-only", receipt.frontier[0].reason)
        self.assertFalse((missing / ".requirements-impact-refiner").exists())

    def test_supplied_only_seed_in_workspace_stays_unknown(self):
        receipt = COORDINATOR.trace_impact(
            self.root, self.draft,
            (COORDINATOR.ScanSeed("remote.contract", None),), self.settings,
            clock=self.clock, runner=self.runner,
        )
        self.assertEqual(receipt.budget_status, "provider_limited")
        self.assertTrue(any("supplied-only" in item.reason for item in receipt.frontier))

    def test_cache_miss_hit_and_partial_are_reported_without_losing_invalidated_frontier(self):
        first = COORDINATOR.trace_impact(
            self.root, self.draft, self.seeds, self.settings,
            clock=self.clock, runner=self.runner,
        )
        self.assertEqual(first.cache["status"], "miss")
        self.assertNotEqual(first.cache["key"], "0" * 64)

        second = COORDINATOR.trace_impact(
            self.root, self.draft, self.seeds, self.settings,
            clock=self.clock, runner=self.runner,
        )
        self.assertEqual(second.cache["status"], "hit")
        self.assertEqual(second.cache["key"], first.cache["key"])

        (self.root / "desktop/profile_cache.ts").write_text(
            'const key = "profile.displayName";\nconst v = 2;\n', encoding="utf-8"
        )
        third = COORDINATOR.trace_impact(
            self.root, self.draft, self.seeds, self.settings,
            clock=self.clock, runner=self.runner,
        )
        self.assertEqual(third.cache["status"], "partial")
        self.assertTrue(third.cache["invalidated_nodes"])

    def test_cache_never_returns_another_draft_or_different_seed_graph(self):
        (self.root / "billing.py").write_text(
            'FIELD = "billing.invoiceTotal"\n', encoding="utf-8"
        )
        first = COORDINATOR.trace_impact(
            self.root, self.draft, self.seeds, self.settings,
            clock=self.clock, runner=self.runner,
        )
        second_draft = {"draft_id": "2" * 32, "request": "rename invoice total"}
        second = COORDINATOR.trace_impact(
            self.root, second_draft,
            (COORDINATOR.ScanSeed("billing.invoiceTotal", "billing.py"),),
            self.settings, clock=self.clock, runner=self.runner,
        )

        self.assertEqual(first.cache["status"], "miss")
        self.assertEqual(second.cache["status"], "miss")
        self.assertEqual(second.draft_id, "2" * 32)
        self.assertNotEqual(second.request_sha256, first.request_sha256)
        self.assertTrue(any(node.location == "billing.py" for node in second.nodes))

    def test_closed_cache_hit_returns_before_builtin_graph_expansion(self):
        COORDINATOR.trace_impact(
            self.root, self.draft, self.seeds, self.settings,
            clock=self.clock, runner=self.runner,
        )
        with mock.patch.object(
            COORDINATOR.BUILTIN, "scan_repository",
            side_effect=AssertionError("closed cache hit must precede graph expansion"),
        ):
            cached = COORDINATOR.trace_impact(
                self.root, self.draft, self.seeds, self.settings,
                clock=self.clock, runner=self.runner,
            )
        self.assertEqual(cached.cache["status"], "hit")

    def test_precise_provider_identity_reuses_cache_without_repeating_query(self):
        calls = []
        probe = COORDINATOR.ProviderProbe(
            "codegraph", "ready", "verified-provider", Path("/bin/codegraph"),
            "generic", "a" * 64,
        )
        adapter = FakeAdapter(candidate_result("codegraph"), calls)
        settings = COORDINATOR.GraphSettings(
            providers=("codegraph",), max_seconds=30, target_seconds=10,
        )
        with mock.patch.object(COORDINATOR, "discover_providers", return_value=(probe,)), \
             mock.patch.object(COORDINATOR, "ADAPTERS", {"codegraph": adapter}):
            first = COORDINATOR.trace_impact(
                self.root, self.draft, self.seeds, settings,
                clock=self.clock, runner=self.runner,
            )
            second = COORDINATOR.trace_impact(
                self.root, self.draft, self.seeds, settings,
                clock=self.clock, runner=self.runner,
            )
        self.assertEqual(first.cache["status"], "miss")
        self.assertEqual(second.cache["status"], "hit")
        self.assertEqual(
            [item[0] for item in calls].count("query"), 1,
        )

    def test_closed_cache_returns_before_adapter_specific_probe(self):
        calls = []
        probe = COORDINATOR.ProviderProbe(
            "codegraph", "ready", "verified-provider", Path("/bin/codegraph"),
            "generic", "a" * 64,
        )
        settings = COORDINATOR.GraphSettings(
            providers=("codegraph",), max_seconds=30, target_seconds=10,
        )
        with mock.patch.object(COORDINATOR, "discover_providers", return_value=(probe,)), \
             mock.patch.object(
                 COORDINATOR, "ADAPTERS",
                 {"codegraph": FakeAdapter(candidate_result("codegraph"), calls)},
             ):
            first = COORDINATOR.trace_impact(
                self.root, self.draft, self.seeds, settings,
                clock=self.clock, runner=self.runner,
            )

        class FailingSlowProbe:
            def probe(inner_self, spec, root, deadline, runner):
                calls.append(("unexpected-probe", spec.name))
                deadline.clock.advance(30)
                raise RuntimeError("closed cache must return before this probe")

        with mock.patch.object(COORDINATOR, "discover_providers", return_value=(probe,)), \
             mock.patch.object(
                 COORDINATOR, "ADAPTERS", {"codegraph": FailingSlowProbe()},
             ):
            second = COORDINATOR.trace_impact(
                self.root, self.draft, self.seeds, settings,
                clock=self.clock, runner=self.runner,
            )

        self.assertEqual(first.cache["status"], "miss")
        self.assertEqual(second.cache["status"], "hit")
        self.assertFalse(any(item[0] == "unexpected-probe" for item in calls))

    def test_provider_priority_is_deterministic_and_high_risk_seeds_run_first(self):
        calls = []
        probes = (
            COORDINATOR.ProviderProbe("ast-grep", "ready", "verified-provider", Path("/bin/sg")),
            COORDINATOR.ProviderProbe("scip", "ready", "verified-provider", Path("/bin/scip")),
            COORDINATOR.ProviderProbe("codegraph", "ready", "verified-provider", Path("/bin/codegraph")),
        )
        adapters = {
            name: FakeAdapter(candidate_result(name), calls)
            for name in ("codegraph", "scip", "ast-grep")
        }
        seeds = (
            COORDINATOR.ScanSeed("cosmetic.label", "desktop/profile_cache.ts"),
            COORDINATOR.ScanSeed("authorization.profile", "api/profile.py"),
        )
        settings = COORDINATOR.GraphSettings(
            providers=("codegraph", "scip", "ast-grep"), max_seconds=30,
            target_seconds=10,
        )
        with mock.patch.object(COORDINATOR, "discover_providers", return_value=probes), \
             mock.patch.object(COORDINATOR, "ADAPTERS", adapters):
            COORDINATOR.trace_impact(
                self.root, self.draft, seeds, settings,
                clock=self.clock, runner=self.runner,
            )
        self.assertEqual([call[1] for call in calls if call[0] == "query"], [
            "codegraph", "scip", "ast-grep",
        ])
        self.assertTrue(all(
            call[2][0] == "authorization.profile"
            for call in calls if call[0] == "query"
        ))

    def test_all_ruled_risk_domains_are_emitted_and_legal_schedules_before_functionality(self):
        cases = {
            "license.policy": ("legal/policy",),
            "state.lock.race": ("state/concurrency",),
            "regression.test": ("regression",),
            "backward.compatibility": ("compatibility",),
            "cosmetic.label": ("functionality",),
        }
        for term, expected in cases.items():
            with self.subTest(term=term):
                self.assertEqual(
                    COORDINATOR._risk_domains(COORDINATOR.ScanSeed(term, None)),
                    expected,
                )

        ordered = sorted(
            (
                COORDINATOR.ScanSeed("cosmetic.label", None),
                COORDINATOR.ScanSeed("license.policy", None),
            ),
            key=COORDINATOR._seed_key,
        )
        self.assertEqual(ordered[0].term, "license.policy")

    def test_precise_provider_query_precedes_builtin_structural_expansion(self):
        events = []
        probe = COORDINATOR.ProviderProbe(
            "codegraph", "ready", "verified-provider", Path("/bin/codegraph")
        )
        adapter = FakeAdapter(candidate_result("codegraph"), events)
        real_scan = COORDINATOR.BUILTIN.scan_repository

        def ordered_scan(*args, **kwargs):
            events.append(("builtin", "builtin"))
            return real_scan(*args, **kwargs)

        settings = COORDINATOR.GraphSettings(
            providers=("codegraph",), max_seconds=30, target_seconds=10,
        )
        with mock.patch.object(COORDINATOR, "discover_providers", return_value=(probe,)), \
             mock.patch.object(COORDINATOR, "ADAPTERS", {"codegraph": adapter}), \
             mock.patch.object(COORDINATOR.BUILTIN, "scan_repository", side_effect=ordered_scan):
            COORDINATOR.trace_impact(
                self.root, self.draft, self.seeds, settings,
                clock=self.clock, runner=self.runner,
            )
        names = [item[0] for item in events]
        self.assertLess(names.index("query"), names.index("builtin"))

    def test_explicit_joern_discovery_receives_exact_deep_setting(self):
        seen = []
        def discover(root, requested, deadline, **kwargs):
            seen.append((requested, kwargs.get("deep")))
            return (COORDINATOR.ProviderProbe(
                "joern", "unsupported", detail="Joern requires deep mode",
                repo_root=root,
            ),)
        for deep in (False, True):
            settings = COORDINATOR.GraphSettings(
                providers=("joern",), max_seconds=30, target_seconds=10, deep=deep,
            )
            with mock.patch.object(COORDINATOR, "discover_providers", side_effect=discover):
                COORDINATOR.trace_impact(
                    self.root, {"draft_id": ("2" if deep else "3") * 32},
                    self.seeds, settings, clock=self.clock, runner=self.runner,
                )
        self.assertEqual(seen, [(("joern",), False), (("joern",), True)])

    def test_provider_disagreement_preserves_both_observations_and_unknown_frontier(self):
        calls = []
        probes = (
            COORDINATOR.ProviderProbe("codegraph", "ready", "verified-provider", Path("/bin/codegraph")),
            COORDINATOR.ProviderProbe("ast-grep", "ready", "structural-inferred", Path("/bin/sg")),
        )
        adapters = {
            "codegraph": FakeAdapter(candidate_result("codegraph", edge_kind="references"), calls),
            "ast-grep": FakeAdapter(candidate_result("ast-grep", edge_kind="writes"), calls),
        }
        settings = COORDINATOR.GraphSettings(
            providers=("codegraph", "ast-grep"), max_seconds=30, target_seconds=10,
        )
        with mock.patch.object(COORDINATOR, "discover_providers", return_value=probes), \
             mock.patch.object(COORDINATOR, "ADAPTERS", adapters):
            receipt = COORDINATOR.trace_impact(
                self.root, self.draft, self.seeds, settings,
                clock=self.clock, runner=self.runner,
            )
        self.assertTrue({"references", "writes"} <= {edge.kind for edge in receipt.edges})
        provider_edge_ids = {
            edge.id for edge in receipt.edges
            if edge.provider in {"codegraph", "ast-grep"}
        }
        self.assertTrue(provider_edge_ids <= {
            edge_id for path in receipt.paths for edge_id in path.edges
        })
        self.assertTrue(any("disagreement" in item.reason for item in receipt.frontier))
        self.assertEqual(receipt.budget_status, "provider_limited")

    def test_provider_edges_form_ranked_transitive_paths(self):
        nodes = (
            {
                "key": "a", "kind": "api_field", "label": "profile.displayName",
                "location": "api/profile.py", "confidence": "verified-provider",
                "source_sha256": "a" * 64, "risk_domains": ("interfaces",),
            },
            {
                "key": "b", "kind": "event", "label": "profile.changed",
                "location": "api/profile.py", "confidence": "verified-provider",
                "source_sha256": "a" * 64, "risk_domains": ("interfaces",),
            },
            {
                "key": "c", "kind": "cache", "label": "profile-cache",
                "location": "desktop/profile_cache.ts", "confidence": "verified-provider",
                "source_sha256": "b" * 64, "risk_domains": ("data",),
            },
        )
        edges = (
            {
                "source": "a", "target": "b", "kind": "publishes",
                "location": "api/profile.py", "evidence": "publisher",
                "confidence": "verified-provider", "source_sha256": "a" * 64,
            },
            {
                "source": "b", "target": "c", "kind": "caches",
                "location": "desktop/profile_cache.ts", "evidence": "consumer",
                "confidence": "verified-provider", "source_sha256": "b" * 64,
            },
        )
        result = COORDINATOR.ProviderResult(
            "codegraph", "ready", "verified-provider", nodes, edges,
            raw_receipt_sha256=("c" * 64,),
        )
        calls = []
        probe = COORDINATOR.ProviderProbe(
            "codegraph", "ready", "verified-provider", Path("/bin/codegraph")
        )
        settings = COORDINATOR.GraphSettings(
            providers=("codegraph",), max_seconds=30, target_seconds=10,
        )
        with mock.patch.object(COORDINATOR, "discover_providers", return_value=(probe,)), \
             mock.patch.object(
                 COORDINATOR, "ADAPTERS",
                 {"codegraph": FakeAdapter(result, calls)},
             ):
            receipt = COORDINATOR.trace_impact(
                self.root, self.draft, self.seeds, settings,
                clock=self.clock, runner=self.runner,
            )
        self.assertTrue(any(
            path.distance == 2 and "data" in path.risk_domains
            for path in receipt.paths
        ))

    def test_provider_failure_falls_back_to_builtin_and_preserves_status(self):
        calls = []
        probe = COORDINATOR.ProviderProbe(
            "scip", "ready", "verified-provider", Path("/bin/scip")
        )
        adapter = FakeAdapter(candidate_result("scip", status="failed"), calls)
        settings = COORDINATOR.GraphSettings(
            providers=("scip",), max_seconds=30, target_seconds=10,
        )
        with mock.patch.object(COORDINATOR, "discover_providers", return_value=(probe,)), \
             mock.patch.object(COORDINATOR, "ADAPTERS", {"scip": adapter}):
            receipt = COORDINATOR.trace_impact(
                self.root, self.draft, self.seeds, settings,
                clock=self.clock, runner=self.runner,
            )
        self.assertEqual(next(item for item in receipt.providers if item.name == "scip").status, "failed")
        self.assertTrue(any(item.name == "builtin" for item in receipt.providers))
        self.assertTrue(receipt.nodes)

    def test_malformed_provider_candidates_fail_that_provider_without_escaping_root(self):
        calls = []
        probe = COORDINATOR.ProviderProbe(
            "codegraph", "ready", "verified-provider", Path("/bin/codegraph")
        )
        malformed = candidate_result("codegraph", nodes=({
            "key": "escape", "kind": "file", "label": "outside",
            "location": "../outside.py", "confidence": "verified-provider",
            "source_sha256": "a" * 64, "risk_domains": ("functionality",),
        },))
        settings = COORDINATOR.GraphSettings(
            providers=("codegraph",), max_seconds=30, target_seconds=10,
        )
        with mock.patch.object(COORDINATOR, "discover_providers", return_value=(probe,)), \
             mock.patch.object(
                 COORDINATOR, "ADAPTERS",
                 {"codegraph": FakeAdapter(malformed, calls)},
             ):
            receipt = COORDINATOR.trace_impact(
                self.root, self.draft, self.seeds, settings,
                clock=self.clock, runner=self.runner,
            )
        status = next(item for item in receipt.providers if item.name == "codegraph")
        self.assertEqual(status.status, "failed")
        self.assertNotIn("../outside.py", {item.location for item in receipt.nodes})

    def test_deadline_stops_later_providers_and_preserves_frontier(self):
        calls = []
        probes = tuple(
            COORDINATOR.ProviderProbe(name, "ready", "verified-provider", Path("/bin") / name)
            for name in ("codegraph", "scip")
        )
        adapters = {
            "codegraph": FakeAdapter(candidate_result("codegraph"), calls, advance=30),
            "scip": FakeAdapter(candidate_result("scip"), calls),
        }
        settings = COORDINATOR.GraphSettings(
            providers=("codegraph", "scip"), max_seconds=30, target_seconds=10,
        )
        with mock.patch.object(COORDINATOR, "discover_providers", return_value=probes), \
             mock.patch.object(COORDINATOR, "ADAPTERS", adapters):
            receipt = COORDINATOR.trace_impact(
                self.root, self.draft, self.seeds, settings,
                clock=self.clock, runner=self.runner,
            )
        self.assertFalse(any(
            call[0] == "query" and call[1] == "scip" for call in calls
        ))
        self.assertEqual(receipt.budget_status, "budget_exhausted")
        self.assertTrue(receipt.frontier)

    def test_provider_output_is_compacted_to_receipt_contract_limits(self):
        nodes = tuple({
            "key": f"n-{index}", "kind": "file", "label": f"node-{index}",
            "location": "api/profile.py", "confidence": "verified-provider",
            "source_sha256": "a" * 64, "risk_domains": ("functionality",),
        } for index in range(800))
        calls = []
        probe = COORDINATOR.ProviderProbe(
            "codegraph", "ready", "verified-provider", Path("/bin/codegraph")
        )
        adapter = FakeAdapter(candidate_result("codegraph", nodes=nodes), calls)
        settings = COORDINATOR.GraphSettings(
            providers=("codegraph",), max_seconds=30, target_seconds=10,
        )
        with mock.patch.object(COORDINATOR, "discover_providers", return_value=(probe,)), \
             mock.patch.object(COORDINATOR, "ADAPTERS", {"codegraph": adapter}):
            receipt = COORDINATOR.trace_impact(
                self.root, self.draft, self.seeds, settings,
                clock=self.clock, runner=self.runner,
            )
        self.assertLessEqual(len(receipt.nodes), COORDINATOR.GRAPH.MAX_NODES)
        self.assertLessEqual(
            len(COORDINATOR.GRAPH.canonical_receipt_bytes(receipt)),
            COORDINATOR.GRAPH.MAX_RECEIPT_BYTES,
        )

    def test_receipt_is_atomic_private_and_digest_verified_after_reopen(self):
        receipt = COORDINATOR.trace_impact(
            self.root, self.draft, self.seeds, self.settings,
            clock=self.clock, runner=self.runner,
        )
        path = self.root / ".requirements-impact-refiner/graph" / ("1" * 32 + ".json")
        payload = path.read_bytes()
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(payload, COORDINATOR.GRAPH.canonical_receipt_bytes(receipt))
        self.assertEqual(
            hashlib.sha256(payload).hexdigest(), COORDINATOR.receipt_sha256(path)
        )
        self.assertEqual(list(path.parent.glob(".*.tmp")), [])

    def test_receipt_path_symlink_is_rejected(self):
        graph_dir = self.root / ".requirements-impact-refiner/graph"
        graph_dir.mkdir(parents=True)
        outside = Path(self.temporary.name) / "outside"
        outside.write_text("safe", encoding="utf-8")
        os.symlink(outside, graph_dir / ("1" * 32 + ".json"))
        with self.assertRaisesRegex(ValueError, "symlink"):
            COORDINATOR.trace_impact(
                self.root, self.draft, self.seeds, self.settings,
                clock=self.clock, runner=self.runner,
            )
        self.assertEqual(outside.read_text(encoding="utf-8"), "safe")


if __name__ == "__main__":
    unittest.main()


class LimitedMergeDisclosureTest(unittest.TestCase):
    """Merge compaction or provider disagreement must leave a visible
    non-provider frontier entry: downstream promotion treats a frontier made
    solely of provider-unavailable disclosures as complete coverage."""

    def test_limited_merge_appends_coverage_frontier(self):
        import tempfile
        from pathlib import Path as _Path

        original = COORDINATOR._merge_provider_results

        def limited_merge(base, results):
            nodes, edges, paths, frontier, _ = original(base, results)
            return nodes, edges, paths, frontier, True

        COORDINATOR._merge_provider_results = limited_merge
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = _Path(temporary)
                (root / "api.py").write_text(
                    'FIELD = "profile.displayName"\n', encoding="utf-8"
                )
                receipt = COORDINATOR.trace_impact(
                    root,
                    {"draft_id": "DRAFT-001", "request_sha256": "0" * 64,
                     "request": "Rename profile.displayName"},
                    (COORDINATOR.ScanSeed("profile.displayName", "api.py"),),
                    {"enabled": True, "max_seconds": 30, "target_seconds": 10,
                     "providers": ["auto"], "install_policy": "never",
                     "deep": False},
                )
        finally:
            COORDINATOR._merge_provider_results = original

        reasons = [row.reason for row in receipt.frontier]
        self.assertTrue(
            any(reason.startswith("provider unavailable") for reason in reasons),
            reasons,
        )
        self.assertEqual(receipt.budget_status, "provider_limited")
        self.assertTrue(
            any(not reason.startswith("provider unavailable") for reason in reasons),
            reasons,
        )


class SeedRiskTokenizationTest(unittest.TestCase):
    """Seed risk keywords must match whole identifier tokens: author.name,
    statement.value, and rapid.value are not authorization, concurrency, or
    interface risks."""

    def test_substring_fragments_do_not_classify(self):
        cases = {
            "author.name": "authorization/privacy",
            "statement.value": "state/concurrency",
            "rapid.value": "interfaces",
            "contest.entry": "regression",
        }
        for term, forbidden in cases.items():
            with self.subTest(term=term):
                domains = COORDINATOR._risk_domains(
                    COORDINATOR.ScanSeed(term, "src/module.py")
                )
                self.assertNotIn(forbidden, domains, domains)

    def test_true_signals_still_classify(self):
        self.assertIn(
            "authorization/privacy",
            COORDINATOR._risk_domains(
                COORDINATOR.ScanSeed("authorization.workspace_edit", "auth/authorize.py")
            ),
        )
        self.assertIn(
            "interfaces",
            COORDINATOR._risk_domains(
                COORDINATOR.ScanSeed("profile.displayName", "api/profile.py")
            ),
        )
        self.assertIn(
            "data",
            COORDINATOR._risk_domains(
                COORDINATOR.ScanSeed("cache.invalidate", "cache/store.py")
            ),
        )
        self.assertIn(
            "state/concurrency",
            COORDINATOR._risk_domains(
                COORDINATOR.ScanSeed("lock.acquire", "sync/mutex.py")
            ),
        )
