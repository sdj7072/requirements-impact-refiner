import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "graph-project"
MODULE_PATH = ROOT / "skills" / "requirements-impact-refiner" / "scripts" / "graph_builtin.py"
SPEC = importlib.util.spec_from_file_location("graph_builtin", MODULE_PATH)
BUILTIN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BUILTIN
SPEC.loader.exec_module(BUILTIN)


class FakeClock:
    def __init__(self, values=(0.0,)):
        self.values = tuple(values)
        self.calls = 0

    def monotonic(self):
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        return value


def scan(root, seeds=(None,), limits=None, clock=None):
    actual_seeds = (
        (BUILTIN.ScanSeed("profile.displayName", "api/profile.py"),)
        if seeds == (None,) else seeds
    )
    return BUILTIN.scan_repository(
        root,
        actual_seeds,
        limits or BUILTIN.ScanLimits(max_seconds=30, max_files=500, max_bytes=8_000_000),
        clock or FakeClock(),
    )


class GraphBuiltinTest(unittest.TestCase):
    def test_shared_field_discovers_mobile_desktop_event_and_migration_test(self):
        result = scan(FIXTURE_ROOT)
        locations = {node.location for node in result.nodes}
        self.assertTrue({
            "api/profile.py", "mobile/user_dto.swift",
            "desktop/profile_cache.ts", "events/profile_changed.py",
            "tests/test_profile_migration.py",
        } <= locations)
        self.assertTrue(any(path.distance >= 3 for path in result.paths))
        self.assertTrue(all(edge.evidence for edge in result.edges))
        self.assertTrue(all(
            edge.confidence in {"lexical", "structural-inferred"}
            for edge in result.edges
        ))

    def test_scan_is_stable_and_deduplicates_terms_and_seeds(self):
        seeds = (
            BUILTIN.ScanSeed("profile.displayName", "api/profile.py"),
            BUILTIN.ScanSeed("profile.displayName", "api/profile.py"),
            BUILTIN.ScanSeed("displayName", "api/profile.py"),
        )
        first = scan(FIXTURE_ROOT, seeds=seeds)
        second = scan(FIXTURE_ROOT, seeds=tuple(reversed(seeds)))
        self.assertEqual(first, second)
        self.assertEqual(len({node.id for node in first.nodes}), len(first.nodes))
        self.assertEqual(len({edge.id for edge in first.edges}), len(first.edges))
        self.assertEqual(len({path.id for path in first.paths}), len(first.paths))

    def test_ignores_metadata_generated_dependencies_binary_and_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src/main.py").write_text('KEY = "profile.displayName"', encoding="utf-8")
            for directory in (".git", "vendor", "build", "generated", "node_modules"):
                target = root / directory
                target.mkdir()
                (target / "hidden.py").write_text('KEY = "profile.displayName"', encoding="utf-8")
            (root / "binary.bin").write_bytes(b"profile.displayName\x00hidden")
            (root / "invalid.py").write_bytes(b"profile.displayName\xff")

            result = scan(root, seeds=(BUILTIN.ScanSeed("profile.displayName", "src/main.py"),))
            locations = {node.location for node in result.nodes}
            self.assertEqual(locations, {"src/main.py"})
            self.assertTrue({"binary", "invalid-utf8"} <= set(result.skipped.values()))

    def test_unreadable_subtree_is_an_unknown_frontier_not_closed_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "api").mkdir()
            (root / "api/profile.py").write_text(
                'FIELD = "profile.displayName"\n', encoding="utf-8"
            )
            (root / "blocked").mkdir()
            real_scandir = BUILTIN.os.scandir

            def controlled_scandir(directory):
                if Path(directory).name == "blocked":
                    raise PermissionError("controlled unreadable subtree")
                return real_scandir(directory)

            with mock.patch.object(BUILTIN.os, "scandir", side_effect=controlled_scandir):
                result = scan(root)

            self.assertEqual(result.budget_status, "provider_limited")
            blocked = next(node for node in result.nodes if node.location == "blocked")
            self.assertTrue(any(
                item.node == blocked.id and "blocked" in item.reason
                for item in result.frontier
            ))

    def test_directory_entry_classification_error_is_unknown_frontier(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resolved = root.resolve()

            class FailingEntry:
                name = "classification-blocked"
                path = str(resolved / name)

                def is_symlink(self):
                    return False

                def is_dir(self, follow_symlinks=False):
                    raise PermissionError("controlled classification failure")

                def is_file(self, follow_symlinks=False):
                    return False

            with mock.patch.object(BUILTIN.os, "scandir", return_value=[FailingEntry()]):
                result = scan(
                    root,
                    seeds=(BUILTIN.ScanSeed("profile.displayName", None),),
                )

            self.assertEqual(result.budget_status, "provider_limited")
            blocked = next(
                node for node in result.nodes
                if node.location == "classification-blocked"
            )
            self.assertTrue(any(
                item.node == blocked.id and "classification-blocked" in item.reason
                for item in result.frontier
            ))

    def test_unknown_placeholders_never_displace_seed_under_tight_node_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "api").mkdir()
            (root / "api/profile.py").write_text(
                'FIELD = "profile.displayName"\n', encoding="utf-8"
            )
            for name in ("blocked-a", "blocked-b"):
                (root / name).mkdir()
            real_scandir = BUILTIN.os.scandir

            def controlled_scandir(directory):
                if Path(directory).name.startswith("blocked-"):
                    raise PermissionError("controlled unreadable subtree")
                return real_scandir(directory)

            with mock.patch.object(BUILTIN.os, "scandir", side_effect=controlled_scandir):
                result = scan(
                    root,
                    limits=BUILTIN.ScanLimits(max_nodes=1),
                )

            self.assertEqual(result.budget_status, "provider_limited")
            self.assertEqual([node.location for node in result.nodes], ["api/profile.py"])
            self.assertTrue(any(
                "2 unreadable directories omitted" in item.reason
                for item in result.frontier
            ))

    def test_rejects_traversal_and_root_symlinks_and_skips_file_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            source = root / "real.py"
            source.write_text('KEY = "profile.displayName"', encoding="utf-8")
            os.symlink(source, root / "linked.py")
            os.symlink(root, Path(temporary) / "repo-link")

            with self.assertRaisesRegex(ValueError, "safe repository-relative"):
                scan(root, seeds=(BUILTIN.ScanSeed("x", "../outside.py"),))
            with self.assertRaisesRegex(ValueError, "regular directory"):
                scan(Path(temporary) / "repo-link")
            result = scan(root, seeds=(BUILTIN.ScanSeed("profile.displayName", "real.py"),))
            self.assertNotIn("linked.py", {node.location for node in result.nodes})
            self.assertEqual(result.skipped["linked.py"], "symlink")

    def test_per_file_total_file_and_graph_limits_are_hard_bounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index in range(6):
                (root / f"file_{index}.py").write_text(
                    'KEY = "profile.displayName"\nSHARED = "profile.changed"\n',
                    encoding="utf-8",
                )
            oversized = root / "oversized.py"
            oversized.write_bytes(b"profile.displayName" + b"x" * 200)
            limits = BUILTIN.ScanLimits(
                max_seconds=30, max_files=3, max_bytes=300, max_file_bytes=100,
                max_nodes=2, max_edges=1, max_paths=1,
            )
            result = scan(root, seeds=(BUILTIN.ScanSeed("profile.displayName", "file_0.py"),), limits=limits)
            self.assertLessEqual(result.files_scanned, 3)
            self.assertLessEqual(result.bytes_scanned, 300)
            self.assertLessEqual(len(result.nodes), 2)
            self.assertLessEqual(len(result.edges), 1)
            self.assertLessEqual(len(result.paths), 1)
            self.assertEqual(result.skipped["oversized.py"], "oversized")
            self.assertEqual(result.budget_status, "budget_exhausted")

    def test_descriptor_growth_cannot_cross_remaining_total_byte_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "growing.py").write_text("x", encoding="utf-8")
            with mock.patch.object(
                BUILTIN, "_read_regular_file", return_value=(b"x" * 101, None)
            ):
                result = scan(
                    root,
                    seeds=(BUILTIN.ScanSeed("profile.displayName", "growing.py"),),
                    limits=BUILTIN.ScanLimits(max_bytes=100),
                )

            self.assertLessEqual(result.bytes_scanned, 100)
            self.assertEqual(result.bytes_scanned, 0)
            self.assertEqual(result.skipped["growing.py"], "byte-limit")
            self.assertEqual(result.budget_status, "budget_exhausted")

    def test_path_limit_also_bounds_frontier_expansion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index in range(6):
                (root / f"file_{index}.py").write_text(
                    'KEY = "profile.displayName"\nSHARED = "profile.changed"\n',
                    encoding="utf-8",
                )
            clock = FakeClock()
            result = scan(
                root,
                seeds=(BUILTIN.ScanSeed("profile.displayName", "file_0.py"),),
                limits=BUILTIN.ScanLimits(
                    max_seconds=30, max_files=50, max_bytes=10_000,
                    max_nodes=10, max_edges=100, max_paths=1,
                ),
                clock=clock,
            )
            self.assertEqual(len(result.paths), 1)
            self.assertLess(clock.calls, 150)

    def test_three_digit_contract_caps_edge_ids_at_999(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index in range(33):
                (root / f"file_{index:02d}.py").write_text(
                    'KEY = "profile.displayName"\n', encoding="utf-8"
                )
            result = scan(
                root,
                seeds=(BUILTIN.ScanSeed("profile.displayName", "file_00.py"),),
                limits=BUILTIN.ScanLimits(
                    max_files=100, max_bytes=100_000, max_paths=0,
                ),
            )

            self.assertEqual(len(result.edges), 999)
            self.assertEqual(result.edges[-1].id, "EDGE-999")
            self.assertNotIn("EDGE-1000", {edge.id for edge in result.edges})
            with self.assertRaisesRegex(ValueError, "three-digit"):
                BUILTIN.ScanLimits(max_edges=1_000)

    def test_empty_repository_preserves_supplied_only_seed(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = scan(
                Path(temporary),
                seeds=(BUILTIN.ScanSeed("contract.displayName", None),),
            )
            self.assertEqual(len(result.nodes), 1)
            self.assertEqual(result.nodes[0].label, "contract.displayName")
            self.assertIsNone(result.nodes[0].location)
            self.assertEqual(result.paths, ())

    def test_risk_paths_rank_authorization_before_lower_risk_domains(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "source.py").write_text('KEY = "profile.displayName"', encoding="utf-8")
            (root / "cache.py").write_text('KEY = "profile.displayName"\nCACHE = "profileCache"', encoding="utf-8")
            (root / "authorization.py").write_text('KEY = "profile.displayName"\nPERMISSION = "profile.read"', encoding="utf-8")
            result = scan(root, seeds=(BUILTIN.ScanSeed("profile.displayName", "source.py"),))
            self.assertEqual(result.paths[0].risk_domains[0], "authorization/privacy")

    def test_shared_quoted_data_is_lexical_reference_not_structural_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "api.py").write_text(
                'FIELD = "profile.displayName"\n', encoding="utf-8"
            )
            (root / "profile_cache.py").write_text(
                'CACHE_KEY = "profile.displayName"\n', encoding="utf-8"
            )
            result = scan(
                root, seeds=(BUILTIN.ScanSeed("profile.displayName", "api.py"),)
            )
            locations = {node.id: node.location for node in result.nodes}
            matching = [
                edge for edge in result.edges
                if locations[edge.source] == "api.py"
                and locations[edge.target] == "profile_cache.py"
            ]

            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0].kind, "references")
            self.assertEqual(matching[0].confidence, "lexical")

    def test_import_provenance_is_directional_from_the_source_occurrence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "consumer.py").write_text(
                "from shared_model import SharedModel\n", encoding="utf-8"
            )
            (root / "shared_model.py").write_text(
                "class SharedModel:\n    pass\n", encoding="utf-8"
            )
            result = scan(
                root, seeds=(BUILTIN.ScanSeed("SharedModel", "consumer.py"),)
            )
            locations = {node.id: node.location for node in result.nodes}
            directions = {
                (locations[edge.source], locations[edge.target]):
                (edge.kind, edge.confidence)
                for edge in result.edges
            }

            self.assertEqual(
                directions[("consumer.py", "shared_model.py")],
                ("imports", "structural-inferred"),
            )
            self.assertEqual(
                directions[("shared_model.py", "consumer.py")],
                ("references", "lexical"),
            )

    def test_deadline_stops_before_traversal_and_during_frontier_expansion(self):
        immediate = FakeClock((5.0, 5.0))
        result = scan(FIXTURE_ROOT, clock=immediate, limits=BUILTIN.ScanLimits(max_seconds=0, max_files=500, max_bytes=8_000_000))
        self.assertEqual(result.nodes, ())
        self.assertEqual(result.budget_status, "budget_exhausted")

        advancing = FakeClock((0.0,) * 12 + (31.0,))
        result = scan(FIXTURE_ROOT, clock=advancing)
        self.assertEqual(result.budget_status, "budget_exhausted")
        self.assertEqual(result.edges, ())
        self.assertEqual(result.paths, ())
        self.assertGreaterEqual(advancing.calls, 13)


if __name__ == "__main__":
    unittest.main()


class SensitiveLiteralRedactionTest(unittest.TestCase):
    """Prefixed and suffixed credential names must be redacted, because the
    longest-shared-token edge evidence actively selects for secret values."""

    REDACTED_ASSIGNMENTS = (
        'token = "abc123secretvalue"',
        'password = "hunter2hunter2"',
        'AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMIexample"',
        'GITHUB_TOKEN = "ghp_leakedsecret1234567890"',
        'ANTHROPIC_API_KEY = "sk-ant-api03-leaked"',
        'DB_PASSWORD = "hunter2hunter2"',
        'STRIPE_SECRET_KEY = "sk_live_51leaked"',
        'SLACK_BOT_TOKEN = "xoxb-1234-leaked"',
        'DJANGO_SECRET_KEY = "insecure-leaked"',
        'apiKey: "AIzaLeakedValue"',
        'clientSecret = "leaked-oauth-secret"',
        'authToken: "bearer-leaked"',
        'PASSPHRASE = "correct horse"'.replace(" horse", "-horse"),
    )

    PRESERVED_ASSIGNMENTS = (
        'tokenizer = "whitespace"',
        'keyboard_layout = "qwerty"',
        'monkeypatch = "fixture"',
    )

    def test_redacts_prefixed_and_suffixed_credential_names(self):
        for line in self.REDACTED_ASSIGNMENTS:
            with self.subTest(line=line):
                safe_text, found = BUILTIN._redact_sensitive_literals(line)
                value = line.split(None, 2)[-1].strip('"').rstrip(":")
                self.assertTrue(found, line)
                self.assertNotIn(value.strip('"'), safe_text)

    def test_preserves_non_credential_identifiers(self):
        for line in self.PRESERVED_ASSIGNMENTS:
            with self.subTest(line=line):
                safe_text, found = BUILTIN._redact_sensitive_literals(line)
                self.assertEqual(safe_text, line)
                self.assertEqual(found, frozenset())
