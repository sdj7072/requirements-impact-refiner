import hashlib
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "graph-project"
MODULE_PATH = ROOT / "scripts" / "graph_builtin.py"
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
        (BUILTIN.ScanSeed("profile.displayName", "api/profile.py"),) if seeds == (None,) else seeds
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
        expected = {
            "api/profile.py",
            "mobile/user_dto.swift",
            "desktop/profile_cache.ts",
            "events/profile_changed.py",
            "tests/test_profile_migration.py",
        }
        self.assertTrue(expected <= locations)
        by_id = {node.id: node.location for node in result.nodes}
        destinations = {by_id[path.nodes[-1]] for path in result.paths}
        self.assertTrue(expected - {"api/profile.py"} <= destinations)
        self.assertTrue(all(edge.evidence for edge in result.edges))
        self.assertTrue(
            all(edge.confidence in {"lexical", "structural-inferred"} for edge in result.edges)
        )

    def test_dense_filename_seed_graph_uses_distinct_file_labels_and_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            locations = ["docs/POLICY.md"] + [f"module_{index}.py" for index in range(7)]
            (root / "docs").mkdir()
            for location in locations:
                path = root / location
                path.write_text(
                    'POLICY = "POLICY.md"\nAUTH = "authorization"\n',
                    encoding="utf-8",
                )
            seeds = tuple(BUILTIN.ScanSeed("POLICY.md", location) for location in locations)

            result = scan(root, seeds=seeds)

            self.assertEqual({node.location for node in result.nodes}, set(locations))
            self.assertEqual(len(result.paths), len(result.nodes) - 1)
            self.assertNotEqual(result.budget_status, "budget_exhausted")

    def test_real_transitive_chain_keeps_the_shortest_long_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.py").write_text('A = "alphabridgeone"\n', encoding="utf-8")
            (root / "b.py").write_text(
                'A = "alphabridgeone"\nB = "betabridgetwo"\n', encoding="utf-8"
            )
            (root / "c.py").write_text(
                'B = "betabridgetwo"\nC = "gammabridgethree"\n', encoding="utf-8"
            )
            (root / "d.py").write_text('C = "gammabridgethree"\n', encoding="utf-8")

            result = scan(root, seeds=(BUILTIN.ScanSeed("alphabridgeone", "a.py"),))

            self.assertTrue(any(path.distance == 3 for path in result.paths))

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

    def test_explicit_generated_seed_keeps_its_digest_outside_default_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated = root / "generated"
            generated.mkdir()
            source = generated / "api.py"
            source.write_text("def generated_api():\n    return True\n", encoding="utf-8")

            result = scan(
                root,
                seeds=(BUILTIN.ScanSeed("generated_api", "generated/api.py"),),
            )

            node = next(row for row in result.nodes if row.location == "generated/api.py")
            self.assertEqual(node.source_sha256, hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertNotIn("generated/api.py", result.source_digests)

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
            self.assertTrue(
                any(
                    item.node == blocked.id and "blocked" in item.reason for item in result.frontier
                )
            )

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
                node for node in result.nodes if node.location == "classification-blocked"
            )
            self.assertTrue(
                any(
                    item.node == blocked.id and "classification-blocked" in item.reason
                    for item in result.frontier
                )
            )

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
            self.assertTrue(
                any("2 unreadable directories omitted" in item.reason for item in result.frontier)
            )

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
                max_seconds=30,
                max_files=3,
                max_bytes=300,
                max_file_bytes=100,
                max_nodes=2,
                max_edges=1,
                max_paths=1,
            )
            result = scan(
                root, seeds=(BUILTIN.ScanSeed("profile.displayName", "file_0.py"),), limits=limits
            )
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
            with mock.patch.object(BUILTIN, "_read_regular_file", return_value=(b"x" * 101, None)):
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
                    max_seconds=30,
                    max_files=50,
                    max_bytes=10_000,
                    max_nodes=10,
                    max_edges=100,
                    max_paths=1,
                ),
                clock=clock,
            )
            self.assertEqual(len(result.paths), 1)
            self.assertLess(clock.calls, 150)
            self.assertTrue(any("path capacity exhausted" in row.reason for row in result.frontier))

    def test_exact_path_capacity_is_not_reported_as_exhausted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.py").write_text('KEY = "sharedboundary"\n', encoding="utf-8")
            (root / "b.py").write_text('KEY = "sharedboundary"\n', encoding="utf-8")

            result = scan(
                root,
                seeds=(BUILTIN.ScanSeed("sharedboundary", "a.py"),),
                limits=BUILTIN.ScanLimits(max_paths=1),
            )

            self.assertEqual(len(result.paths), 1)
            self.assertEqual(result.budget_status, "closed")
            self.assertEqual(result.frontier, ())

    def test_zero_path_capacity_is_closed_when_no_path_exists(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "isolated.py").write_text('KEY = "isolatedboundary"\n', encoding="utf-8")

            result = scan(
                root,
                seeds=(BUILTIN.ScanSeed("isolatedboundary", "isolated.py"),),
                limits=BUILTIN.ScanLimits(max_paths=0),
            )

            self.assertEqual(result.budget_status, "closed")
            self.assertEqual(result.frontier, ())

    def test_resource_truncation_is_not_masked_by_path_capacity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("a.py", "b.py", "c.py"):
                (root / name).write_text('KEY = "sharedboundary"\n', encoding="utf-8")

            result = scan(
                root,
                seeds=(BUILTIN.ScanSeed("sharedboundary", "a.py"),),
                limits=BUILTIN.ScanLimits(max_nodes=2, max_paths=1),
            )

            self.assertEqual(result.budget_status, "budget_exhausted")
            reasons = [row.reason for row in result.frontier]
            self.assertTrue(any("resource capacity exhausted" in row for row in reasons))
            self.assertFalse(any("path capacity exhausted" in row for row in reasons))

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
                    max_files=100,
                    max_bytes=100_000,
                    max_paths=0,
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
            (root / "cache.py").write_text(
                'KEY = "profile.displayName"\nCACHE = "profileCache"', encoding="utf-8"
            )
            (root / "authorization.py").write_text(
                'KEY = "profile.displayName"\nPERMISSION = "profile.read"', encoding="utf-8"
            )
            result = scan(root, seeds=(BUILTIN.ScanSeed("profile.displayName", "source.py"),))
            self.assertEqual(result.paths[0].risk_domains[0], "authorization/privacy")

    def test_shared_quoted_data_is_lexical_reference_not_structural_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "api.py").write_text('FIELD = "profile.displayName"\n', encoding="utf-8")
            (root / "profile_cache.py").write_text(
                'CACHE_KEY = "profile.displayName"\n', encoding="utf-8"
            )
            result = scan(root, seeds=(BUILTIN.ScanSeed("profile.displayName", "api.py"),))
            locations = {node.id: node.location for node in result.nodes}
            matching = [
                edge
                for edge in result.edges
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
            result = scan(root, seeds=(BUILTIN.ScanSeed("SharedModel", "consumer.py"),))
            locations = {node.id: node.location for node in result.nodes}
            directions = {
                (locations[edge.source], locations[edge.target]): (edge.kind, edge.confidence)
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
        result = scan(
            FIXTURE_ROOT,
            clock=immediate,
            limits=BUILTIN.ScanLimits(max_seconds=0, max_files=500, max_bytes=8_000_000),
        )
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
        'githubToken = "ghp_camelcase_leak"',
        'stripeSecretKey = "sk_live_camel"',
        'GitHubToken = "ghp_pascal_leak"',
        'tokenProd = "camel_suffix_leak"',
        'GITHUB_TOKEN := "walrus_leak"',
    )

    WRAPPED_ASSIGNMENTS = (
        ('token := []byte("real-secret-value")', "real-secret-value"),
        ('password = map[string]string{"k": "real-secret-value"}', "real-secret-value"),
        ('API_KEY = os.getenv("FALLBACK", "real-secret-value")', "real-secret-value"),
        ('token = "first-secret" + "second-secret"', "second-secret"),
    )

    def test_wrapped_assignment_literals_are_redacted(self):
        for line, secret in self.WRAPPED_ASSIGNMENTS:
            with self.subTest(line=line):
                safe_text, found = BUILTIN._redact_sensitive_literals(line)
                self.assertNotIn(secret, safe_text, safe_text)
                self.assertTrue(found)

    def test_multiline_raw_and_escaped_assignment_values_are_redacted(self):
        cases = (
            ('token := []byte(\n  "multiline-secret"\n)', "multiline-secret"),
            ("token := []byte(`raw-secret-value`)", "raw-secret-value"),
            ('token := []byte("abc\\"escaped-secret")', "escaped-secret"),
        )
        for source, secret in cases:
            with self.subTest(source=source):
                safe_text, found = BUILTIN._redact_sensitive_literals(source)
                self.assertNotIn(secret, safe_text, safe_text)
                self.assertTrue(found)

    def test_raw_credential_value_never_reaches_edge_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret = "ULTRASECRET123456789"
            (root / "a.go").write_text(f"token := []byte(`{secret}`)\n", encoding="utf-8")
            (root / "b.go").write_text(f'const Linked = "{secret}"\n', encoding="utf-8")

            result = scan(root, seeds=(BUILTIN.ScanSeed("token", "a.go"),))

            self.assertTrue(all(secret not in edge.evidence for edge in result.edges))

    def test_yaml_block_credential_value_never_reaches_edge_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret = "ULTRASECRET123456789"
            (root / "config.yml").write_text(
                f"token: |\n  {secret}\n  shared_boundary\nname: visible\n",
                encoding="utf-8",
            )
            (root / "consumer.py").write_text(f'VALUE = "{secret}"\n', encoding="utf-8")

            result = scan(root, seeds=(BUILTIN.ScanSeed("token", "config.yml"),))

            self.assertTrue(all(secret not in edge.evidence for edge in result.edges))

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


class EdgeKindClassificationTest(unittest.TestCase):
    """Test-path detection must match whole path segments, and an imports
    edge must plausibly resolve to its target, because structural-inferred
    is the confidence tier that unlocks inferred evidence downstream."""

    def edge_kinds(self, files, seed_term, seed_location):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative, content in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            result = scan(root, seeds=(BUILTIN.ScanSeed(seed_term, seed_location),))
            locations = {node.id: node.location for node in result.nodes}
            return {
                (locations[edge.source], locations[edge.target]): (edge.kind, edge.confidence)
                for edge in result.edges
            }

    def test_test_substring_in_filename_is_not_a_test_path(self):
        directions = self.edge_kinds(
            {
                "results_latest.py": 'MARKER = "shared_marker_token"\n',
                "contest_rules.py": 'VALUE = "shared_marker_token"\n',
            },
            "shared_marker_token",
            "results_latest.py",
        )
        self.assertEqual(
            directions[("results_latest.py", "contest_rules.py")],
            ("references", "lexical"),
        )

    def test_resolving_test_edge_is_structural(self):
        directions = self.edge_kinds(
            {
                "auth.py": 'VALUE = "auth"\n',
                "tests/test_auth.py": 'TARGET = "auth"\n',
            },
            "auth",
            "auth.py",
        )
        self.assertEqual(
            directions[("auth.py", "tests/test_auth.py")],
            ("tests", "structural-inferred"),
        )

    def test_coincidental_test_edge_stays_lexical(self):
        directions = self.edge_kinds(
            {
                "billing.py": 'HELPER = "shared_marker_token"\n',
                "tests/test_auth.py": 'CHECK = "shared_marker_token"\n',
            },
            "shared_marker_token",
            "billing.py",
        )
        self.assertEqual(
            directions[("billing.py", "tests/test_auth.py")],
            ("tests", "lexical"),
        )

    def test_imported_member_name_does_not_link_unrelated_module_file(self):
        directions = self.edge_kinds(
            {
                "consumer.py": ("from helpers import auth\nvalue = auth()\n"),
                "helpers.py": "def auth():\n    return True\n",
                "auth.py": 'UNRELATED = "auth"\n',
            },
            "auth",
            "consumer.py",
        )
        self.assertEqual(
            directions[("consumer.py", "helpers.py")],
            ("imports", "structural-inferred"),
        )
        self.assertEqual(
            directions[("consumer.py", "auth.py")],
            ("references", "lexical"),
        )

    def test_javascript_imported_binding_does_not_link_unrelated_file(self):
        directions = self.edge_kinds(
            {
                "consumer.ts": (
                    'import { auth } from "./helpers";\nconst value = "shared_boundary";\n'
                ),
                "helpers.ts": 'export const helper = "shared_boundary";\n',
                "auth.ts": 'export const unrelated = "shared_boundary";\n',
            },
            "shared_boundary",
            "consumer.ts",
        )
        self.assertEqual(
            directions[("consumer.ts", "helpers.ts")],
            ("imports", "structural-inferred"),
        )
        self.assertEqual(
            directions[("consumer.ts", "auth.ts")],
            ("references", "lexical"),
        )

    def test_module_suffix_does_not_earn_structural_import_confidence(self):
        directions = self.edge_kinds(
            {
                "consumer.py": ('import oauth\nVALUE = "shared_boundary"\n'),
                "auth.py": 'UNRELATED = "shared_boundary"\n',
            },
            "shared_boundary",
            "consumer.py",
        )
        self.assertEqual(
            directions[("consumer.py", "auth.py")],
            ("references", "lexical"),
        )

    def test_only_leaf_module_segment_earns_structural_confidence(self):
        directions = self.edge_kinds(
            {
                "consumer.ts": (
                    'import { helper } from "./auth/helpers";\nconst value = "shared_boundary";\n'
                ),
                "auth.ts": 'export const unrelated = "shared_boundary";\n',
                "helpers.ts": 'export const helper = "shared_boundary";\n',
            },
            "shared_boundary",
            "consumer.ts",
        )
        self.assertEqual(
            directions[("consumer.ts", "auth.ts")],
            ("references", "lexical"),
        )
        self.assertEqual(
            directions[("consumer.ts", "helpers.ts")],
            ("imports", "structural-inferred"),
        )

    def test_multiline_javascript_import_resolves_module_specifier(self):
        directions = self.edge_kinds(
            {
                "consumer.ts": (
                    'import {\n  helper,\n  other\n} from "./helpers";\n'
                    'const value = "shared_boundary";\n'
                ),
                "helpers.ts": 'export const helper = "shared_boundary";\n',
            },
            "shared_boundary",
            "consumer.ts",
        )
        self.assertEqual(
            directions[("consumer.ts", "helpers.ts")],
            ("imports", "structural-inferred"),
        )

    def test_javascript_comment_cannot_hijack_module_specifier(self):
        directions = self.edge_kinds(
            {
                "consumer.ts": (
                    'import {\n  helper // from "./auth"\n'
                    '} from "./helpers";\n'
                    'const value = "shared_boundary";\n'
                ),
                "auth.ts": 'export const unrelated = "shared_boundary";\n',
                "helpers.ts": 'export const helper = "shared_boundary";\n',
            },
            "shared_boundary",
            "consumer.ts",
        )
        self.assertEqual(
            directions[("consumer.ts", "auth.ts")],
            ("references", "lexical"),
        )
        self.assertEqual(
            directions[("consumer.ts", "helpers.ts")],
            ("imports", "structural-inferred"),
        )

    def test_template_literal_cannot_invent_an_import_statement(self):
        directions = self.edge_kinds(
            {
                "consumer.ts": (
                    "const template = `\n"
                    'import { fake } from "./auth";\n'
                    "`;\n"
                    'import { helper } from "./helpers";\n'
                    'const value = "shared_boundary";\n'
                ),
                "auth.ts": 'export const unrelated = "shared_boundary";\n',
                "helpers.ts": 'export const helper = "shared_boundary";\n',
            },
            "shared_boundary",
            "consumer.ts",
        )
        self.assertEqual(
            directions[("consumer.ts", "auth.ts")],
            ("references", "lexical"),
        )
        self.assertEqual(
            directions[("consumer.ts", "helpers.ts")],
            ("imports", "structural-inferred"),
        )

    def test_unreadable_only_repository_gets_synthetic_frontier(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            blocked = root / "blocked.py"
            blocked.write_text("HIDDEN = 1\n", encoding="utf-8")
            blocked.chmod(0o000)
            try:
                result = scan(root, seeds=())
            finally:
                blocked.chmod(0o644)

            self.assertEqual(result.budget_status, "provider_limited")
            self.assertTrue(result.nodes)
            self.assertTrue(result.frontier)
            self.assertIn("unreadable source", result.frontier[0].reason)

    def test_import_resolution_rejects_substring_collisions(self):
        module = BUILTIN
        self.assertTrue(module._import_resolves_to_target("pkg/shared_model.py", "sharedmodel"))
        self.assertTrue(module._import_resolves_to_target("pkg/auth_service.py", "auth"))
        self.assertFalse(
            module._import_resolves_to_target("pkg/app_config_loader.py", "config_loader_x")
        )
        self.assertFalse(module._import_resolves_to_target("pkg/reconfigure.py", "config"))

    def test_import_taint_requires_target_resolution(self):
        directions = self.edge_kinds(
            {
                "consumer.py": ("from shared_model import SharedModel\nvalue = SharedModel()\n"),
                "shared_model.py": "class SharedModel:\n    pass\n",
                "narrative_docs.py": ('NOTE = "SharedModel is documented elsewhere"\n'),
            },
            "SharedModel",
            "consumer.py",
        )
        self.assertEqual(
            directions[("consumer.py", "shared_model.py")],
            ("imports", "structural-inferred"),
        )
        self.assertEqual(
            directions[("consumer.py", "narrative_docs.py")],
            ("references", "lexical"),
        )


class SymlinkedParentTraversalTest(unittest.TestCase):
    """The reader must refuse paths whose parent components are symlinks,
    otherwise a directory swapped for a symlink between the walk check and
    the read lands out-of-repo content in the receipt."""

    def test_refuses_file_behind_symlinked_parent_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "repo"
            outside = base / "outside"
            repo.mkdir()
            outside.mkdir()
            (outside / "secret.py").write_text('LEAKED = "outside-the-repo"\n', encoding="utf-8")
            (repo / "linkdir").symlink_to(outside)

            payload, reason = BUILTIN._read_regular_file(repo, "linkdir/secret.py", 1 << 20)

            self.assertIsNone(payload)
            self.assertEqual(reason, "unsafe-file")

    def test_still_reads_regular_files_through_real_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / "pkg").mkdir()
            (repo / "pkg" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")

            payload, reason = BUILTIN._read_regular_file(repo, "pkg/module.py", 1 << 20)

            self.assertIsNone(reason)
            self.assertEqual(payload, b"VALUE = 1\n")


class ImportEdgeProvenanceTest(unittest.TestCase):
    """An imports edge is evidenced by the import statement, which lives in
    the source file — its provenance must record the source, not the target."""

    def test_import_edge_records_source_location_and_digest(self):
        import hashlib as _hashlib

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            consumer = "from shared_model import SharedModel\nvalue = SharedModel()\n"
            (root / "consumer.py").write_text(consumer, encoding="utf-8")
            (root / "shared_model.py").write_text(
                "class SharedModel:\n    pass\n", encoding="utf-8"
            )
            result = scan(root, seeds=(BUILTIN.ScanSeed("SharedModel", "consumer.py"),))
            locations = {node.id: node.location for node in result.nodes}
            import_edges = [
                edge
                for edge in result.edges
                if edge.kind == "imports" and locations[edge.source] == "consumer.py"
            ]
            self.assertTrue(import_edges)
            expected = _hashlib.sha256(consumer.encode("utf-8")).hexdigest()
            for edge in import_edges:
                self.assertEqual(edge.location, "consumer.py")
                self.assertEqual(edge.source_sha256, expected)


class RiskDomainTokenizationTest(unittest.TestCase):
    """Risk keywords must match whole identifier tokens: an npm author field
    or a JSX role attribute must not classify a file as an authorization
    risk and escalate the scan to critical."""

    def domains(self, location, text=""):
        return BUILTIN._risk_domains(location, text)

    def test_author_and_role_attribute_are_not_authorization(self):
        self.assertNotIn("authorization/privacy", self.domains("src/greet.py", "# author: alice"))
        self.assertNotIn(
            "authorization/privacy",
            self.domains("package.json", '{"author": "Alice", "license": "MIT"}'),
        )
        self.assertNotIn(
            "authorization/privacy",
            self.domains("src/button.jsx", '<div role="button" tokenizer="x">'),
        )

    def test_true_authorization_signals_still_match(self):
        self.assertIn("authorization/privacy", self.domains("auth/authorize.py"))
        self.assertIn(
            "authorization/privacy", self.domains("src/session.py", "OAUTH_TOKEN = load()")
        )
        self.assertIn(
            "authorization/privacy", self.domains("src/roles.py", "DEFAULT_ROLE = 'member'")
        )

    def test_substring_families_do_not_leak(self):
        self.assertNotIn("interfaces", self.domains("src/rapid.py", "rapidity = 1"))
        self.assertNotIn(
            "state/concurrency", self.domains("src/statement.py", "statement = parse()")
        )


class PythonAstStructureTest(unittest.TestCase):
    """Python files get genuine structural analysis from the stdlib ast
    module: real import edges without token co-occurrence, def/use reference
    edges at structural confidence, and honest lexical fallback for string
    mentions and unparseable sources."""

    def edge_map(self, files, seed_term, seed_location):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative, content in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            result = scan(root, seeds=(BUILTIN.ScanSeed(seed_term, seed_location),))
            locations = {node.id: node.location for node in result.nodes}
            return {
                (locations[edge.source], locations[edge.target]): (edge.kind, edge.confidence)
                for edge in result.edges
            }

    def test_import_edge_exists_without_any_shared_token(self):
        directions = self.edge_map(
            {
                "app.py": "import blobstore\nvalue = 1\n",
                "blobstore.py": "class Storage:\n    pass\n",
            },
            "Storage",
            "app.py",
        )
        self.assertEqual(
            directions.get(("app.py", "blobstore.py")),
            ("imports", "structural-inferred"),
        )

    def test_use_of_defined_name_is_structural_reference(self):
        directions = self.edge_map(
            {
                "runner.py": "result = parse_config()\n",
                "loader.py": "def parse_config():\n    return {}\n",
            },
            "parse_config",
            "runner.py",
        )
        self.assertEqual(
            directions.get(("runner.py", "loader.py")),
            ("references", "structural-inferred"),
        )

    def test_string_mention_of_name_stays_lexical(self):
        directions = self.edge_map(
            {
                "runner.py": "result = parse_config()\n",
                "notes.py": 'DOC = "call parse_config for setup"\n',
            },
            "parse_config",
            "runner.py",
        )
        self.assertEqual(
            directions.get(("runner.py", "notes.py")),
            ("references", "lexical"),
        )

    def test_unparseable_python_falls_back_to_lexical(self):
        directions = self.edge_map(
            {
                "runner.py": "result = parse_config()\n",
                "broken.py": "def broken(:\n    parse_config\n",
            },
            "parse_config",
            "runner.py",
        )
        self.assertEqual(
            directions.get(("runner.py", "broken.py")),
            ("references", "lexical"),
        )


class StructuralEdgeSurvivalTest(unittest.TestCase):
    """When the edge cap bites, structural edges must survive ahead of
    lexical co-occurrence noise — otherwise a large repository silently
    loses exactly the evidence the scan exists to find."""

    def test_import_edge_survives_lexical_flood(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for i in range(46):
                (root / f"noise_{i:02d}.py").write_text(
                    'SHARED = "common_marker_token"\n', encoding="utf-8"
                )
            (root / "app.py").write_text(
                'import blobstore\nSHARED = "common_marker_token"\n',
                encoding="utf-8",
            )
            (root / "blobstore.py").write_text("class Storage:\n    pass\n", encoding="utf-8")
            result = scan(root, seeds=(BUILTIN.ScanSeed("Storage", "app.py"),))
            locations = {node.id: node.location for node in result.nodes}
            kinds = {
                (locations[edge.source], locations[edge.target]): edge.kind for edge in result.edges
            }
            self.assertGreaterEqual(len(result.edges), 999)
            self.assertEqual(kinds.get(("app.py", "blobstore.py")), "imports")


class JavaScriptStructureTest(unittest.TestCase):
    """JS/TS files get structural signals from masked-source analysis:
    import edges may only land on script-family files, exported names act
    as definitions, and comment/string mentions never earn structure."""

    def edge_map(self, files, seed_term, seed_location):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative, content in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            result = scan(root, seeds=(BUILTIN.ScanSeed(seed_term, seed_location),))
            locations = {node.id: node.location for node in result.nodes}
            return {
                (locations[edge.source], locations[edge.target]): (edge.kind, edge.confidence)
                for edge in result.edges
            }

    def test_js_import_cannot_land_on_a_document(self):
        directions = self.edge_map(
            {
                "app.ts": 'import { helper } from "./billing";\nconst v = helper();\n',
                "billing.ts": "export function helper() { return 1; }\n",
                "docs/billing-notes.md": "# billing notes\nhelper docs here\n",
            },
            "helper",
            "app.ts",
        )
        self.assertEqual(
            directions.get(("app.ts", "billing.ts")),
            ("imports", "structural-inferred"),
        )
        self.assertEqual(
            directions.get(("app.ts", "docs/billing-notes.md"), ("references", "lexical"))[1],
            "lexical",
        )

    def test_use_of_exported_name_is_structural(self):
        directions = self.edge_map(
            {
                "page.js": "const total = computeInvoiceTotal(cart);\n",
                "invoice.js": "export function computeInvoiceTotal(cart) { return 0; }\n",
            },
            "computeInvoiceTotal",
            "page.js",
        )
        self.assertEqual(
            directions.get(("page.js", "invoice.js")),
            ("references", "structural-inferred"),
        )

    def test_comment_mention_of_export_stays_lexical(self):
        directions = self.edge_map(
            {
                "page.js": "// computeInvoiceTotal is documented elsewhere\nconst other_shared_token = 1;\n",
                "invoice.js": "export function computeInvoiceTotal(cart) { return 0; }\nconst other_shared_token = 2;\n",
            },
            "other_shared_token",
            "page.js",
        )
        self.assertEqual(
            directions.get(("page.js", "invoice.js")),
            ("references", "lexical"),
        )


class WorktreeExclusionTest(unittest.TestCase):
    """git worktree checkouts under .worktrees duplicate the entire tree;
    scanning them floods the graph with copies of every file (observed on a
    real repository: every impact path pointed into .worktrees)."""

    def test_worktree_copies_are_not_scanned(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "api").mkdir()
            (root / "api" / "profile.py").write_text(
                'FIELD = "profile.displayName"\n', encoding="utf-8"
            )
            shadow = root / ".worktrees" / "feature-x" / "api"
            shadow.mkdir(parents=True)
            (shadow / "profile.py").write_text(
                'FIELD = "profile.displayName"\n', encoding="utf-8"
            )
            result = scan(
                root,
                seeds=(BUILTIN.ScanSeed("profile.displayName", "api/profile.py"),),
            )
            locations = {node.location for node in result.nodes}
            self.assertTrue(
                all(".worktrees" not in (loc or "") for loc in locations),
                locations,
            )
