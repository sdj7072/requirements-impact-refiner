import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "fast_scan.py"
SCHEMA_PATH = ROOT / "schemas" / "fast-impact-scan.schema.json"


def load_fast_scan():
    if not MODULE_PATH.is_file():
        raise AssertionError("scripts/fast_scan.py must exist")
    name = "_fast_scan_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeDeadline:
    def __init__(self, expired=False):
        self._expired = expired

    def expired(self):
        return self._expired


class FastScanTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def receipt(self):
        return {
            "schema_version": 1,
            "status": "needs_input",
            "scan_id": "0" * 32,
            "receipt_id": "1" * 32,
            "repo_root_sha256": "2" * 64,
            "request_sha256": "3" * 64,
            "payload_sha256": "4" * 64,
            "settings": {
                "enabled": True,
                "max_seconds": 30,
                "target_seconds": 10,
                "providers": ["builtin"],
                "install_policy": "never",
                "deep": False,
            },
            "source_inventory": {
                "digests": {},
                "complete": False,
                "reason": "no-seed",
            },
            "seeds": [],
            "graph_receipt": {},
            "risk_level": "unknown",
            "frontier": [],
            "candidates": [
                {
                    "term": "profile.displayName",
                    "location": "api/profile.py",
                    "derivation": "repository-match",
                }
            ],
            "elapsed_ms": 0,
            "cache_status": "bypassed",
            "can_promote": False,
            "created_at": "2026-08-24T00:00:00Z",
        }

    def test_derives_file_symbol_and_evidence_seeds(self):
        fast_scan = load_fast_scan()
        self.write("api/profile.py", 'FIELD = "profile.displayName"\n')
        self.write(
            "mobile/profile_decoder.swift",
            'let field = "profile.displayName"\n',
        )

        seeds = fast_scan.derive_seeds(
            self.root,
            "Rename profile.displayName in api/profile.py",
            ("mobile/profile_decoder.swift reads profile.displayName",),
            FakeDeadline(),
        )

        self.assertEqual(
            [(row.term, row.location) for row in seeds],
            [
                ("profile.displayName", "api/profile.py"),
                ("profile.displayName", "mobile/profile_decoder.swift"),
            ],
        )
        self.assertEqual(seeds[0].derivation, "request-path-symbol")
        self.assertRegex(seeds[0].source_sha256, r"^[0-9a-f]{64}$")

    def test_distinctive_symbol_search_is_stable_and_bounded(self):
        fast_scan = load_fast_scan()
        self.write("z/second.py", "OrderService.process()\n")
        self.write("a/first.py", "OrderService.process()\n")
        self.write("a/other.py", "unrelated()\n")

        seeds = fast_scan.derive_seeds(
            self.root,
            "Change OrderService.process",
            (),
            FakeDeadline(),
            maximum=1,
        )

        self.assertEqual(
            [(row.term, row.location) for row in seeds],
            [("OrderService.process", "a/first.py")],
        )
        self.assertEqual(seeds[0].derivation, "repository-match")

    def test_unmatched_language_and_expired_deadline_return_no_seeds(self):
        fast_scan = load_fast_scan()
        self.write("app.py", "def run(): pass\n")

        self.assertEqual(
            fast_scan.derive_seeds(
                self.root, "make the experience nicer", (), FakeDeadline()
            ),
            (),
        )
        self.assertEqual(
            fast_scan.derive_seeds(
                self.root, "Change run", (), FakeDeadline(expired=True)
            ),
            (),
        )

    def test_derivation_excludes_control_evidence_binary_and_symlink_files(self):
        fast_scan = load_fast_scan()
        self.write("src/profile.py", 'FIELD = "profile.displayName"\n')
        self.write(
            ".requirements-impact-refiner/private.py",
            'FIELD = "profile.displayName"\n',
        )
        self.write(
            "evals/results/run/raw.py",
            'FIELD = "profile.displayName"\n',
        )
        binary = self.root / "src/binary.dat"
        binary.write_bytes(b"\x00profile.displayName")
        outside = Path(self.temporary.name).parent / "outside-fast-scan.py"
        outside.write_text('FIELD = "profile.displayName"\n', encoding="utf-8")
        (self.root / "linked.py").symlink_to(outside)
        self.addCleanup(lambda: outside.unlink(missing_ok=True))

        seeds = fast_scan.derive_seeds(
            self.root,
            "Change profile.displayName",
            (),
            FakeDeadline(),
        )

        self.assertEqual(
            [(row.term, row.location) for row in seeds],
            [("profile.displayName", "src/profile.py")],
        )

    def test_explicit_path_with_symlinked_parent_is_not_repository_backed(self):
        fast_scan = load_fast_scan()
        outside_context = tempfile.TemporaryDirectory()
        self.addCleanup(outside_context.cleanup)
        outside_directory = Path(outside_context.name)
        (outside_directory / "profile.py").write_text(
            'FIELD = "profile.displayName"\n', encoding="utf-8"
        )
        (self.root / "linked").symlink_to(outside_directory, target_is_directory=True)

        seeds = fast_scan.derive_seeds(
            self.root,
            "Change profile.displayName",
            ("linked/profile.py reads profile.displayName",),
            FakeDeadline(),
        )

        self.assertEqual(seeds, ())

    def test_explicit_file_path_without_symbol_is_a_path_boundary_seed(self):
        fast_scan = load_fast_scan()
        self.write("api/profile.py", "def publish_profile(): pass\n")

        seeds = fast_scan.derive_seeds(
            self.root,
            "Change api/profile.py",
            (),
            FakeDeadline(),
        )

        self.assertEqual(
            [(row.term, row.location, row.derivation) for row in seeds],
            [("api/profile.py", "api/profile.py", "request-path-only")],
        )

    def test_request_evidence_and_maximum_bounds_are_enforced(self):
        fast_scan = load_fast_scan()
        with self.assertRaisesRegex(ValueError, "4 KiB"):
            fast_scan.derive_seeds(
                self.root, "x" * 4097, (), FakeDeadline()
            )
        with self.assertRaisesRegex(ValueError, "32"):
            fast_scan.derive_seeds(
                self.root, "Change field.name", tuple("row" for _ in range(33)),
                FakeDeadline(),
            )
        with self.assertRaisesRegex(ValueError, "maximum"):
            fast_scan.derive_seeds(
                self.root, "Change field.name", (), FakeDeadline(), maximum=0
            )
        with self.assertRaisesRegex(ValueError, "credential"):
            fast_scan.derive_seeds(
                self.root,
                "Change auth.token",
                ("API_TOKEN=secret-value",),
                FakeDeadline(),
            )

    def test_receipt_validation_is_exact_and_status_aware(self):
        fast_scan = load_fast_scan()
        value = self.receipt()
        self.assertEqual(fast_scan.validate_fast_scan_receipt(value), ())

        invalid = copy.deepcopy(value)
        invalid["surprise"] = True
        invalid["can_promote"] = True
        invalid["candidates"] *= 4
        errors = fast_scan.validate_fast_scan_receipt(invalid)
        self.assertIn("unknown top-level key surprise", errors)
        self.assertIn("needs_input scan cannot be promoted", errors)
        self.assertIn("candidates exceeds maximum collection size", errors)

        inconsistent = self.receipt()
        inconsistent["source_inventory"] = {
            "digests": {}, "complete": False, "reason": None,
        }
        self.assertIn(
            "incomplete source_inventory requires a reason",
            fast_scan.validate_fast_scan_receipt(inconsistent),
        )

        complete = copy.deepcopy(value)
        complete["status"] = "complete"
        complete["can_promote"] = True
        complete["candidates"] = []
        complete["source_inventory"] = {
            "digests": {"api/profile.py": "5" * 64},
            "complete": True,
            "reason": None,
        }
        complete["graph_receipt"] = {"receipt_id": "6" * 32}
        complete["risk_level"] = "high"
        complete["cache_status"] = "miss"
        self.assertEqual(fast_scan.validate_fast_scan_receipt(complete), ())

    def test_canonical_receipt_bytes_are_stable_utf8_and_no_terminal_newline(self):
        fast_scan = load_fast_scan()
        value = self.receipt()

        first = fast_scan.canonical_fast_scan_bytes(value)
        second = fast_scan.canonical_fast_scan_bytes(copy.deepcopy(value))

        self.assertEqual(first, second)
        self.assertFalse(first.endswith(b"\n"))
        self.assertEqual(json.loads(first), value)
        invalid = copy.deepcopy(value)
        invalid["status"] = "complete"
        with self.assertRaisesRegex(ValueError, "invalid fast scan receipt"):
            fast_scan.canonical_fast_scan_bytes(invalid)

    def test_domain_values_are_immutable_and_schema_matches_contract(self):
        fast_scan = load_fast_scan()
        seed = fast_scan.DerivedSeed(
            "profile.displayName", "api/profile.py",
            "request-path-symbol", "a" * 64,
        )
        with self.assertRaises((AttributeError, TypeError)):
            seed.term = "changed"

        if not SCHEMA_PATH.is_file():
            self.fail("schemas/fast-impact-scan.schema.json must exist")
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        expected = {
            "schema_version", "status", "scan_id", "receipt_id",
            "repo_root_sha256", "request_sha256", "payload_sha256",
            "settings", "source_inventory", "seeds", "graph_receipt",
            "risk_level", "frontier", "candidates", "elapsed_ms",
            "cache_status", "can_promote", "created_at",
        }
        self.assertEqual(set(schema["required"]), expected)
        self.assertEqual(set(schema["properties"]), expected)
        self.assertFalse(schema["additionalProperties"])

    def test_execute_calls_graph_once_persists_and_renders(self):
        fast_scan = load_fast_scan()
        self.write("api/profile.py", 'FIELD = "profile.displayName"\n')
        graph = json.loads(
            (ROOT / "tests/fixtures/impact-graph-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        graph["budget_status"] = "closed"
        graph["frontier"] = []
        calls = []

        def coordinator(*args, **kwargs):
            calls.append((args, kwargs))
            return graph

        result = fast_scan.execute_fast_scan(
            fast_scan.FastScanRequest(
                self.root, "Rename profile.displayName", (), "balanced"
            ),
            graph["settings"],
            payload_sha256="a" * 64,
            coordinator=coordinator,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.status, "complete")
        self.assertTrue(result.can_promote)
        self.assertLessEqual(len(result.display_text.split()), 180)
        self.assertTrue(
            (self.root / ".requirements-impact-refiner/scans" /
             (result.scan_id + ".json")).is_file()
        )

    def test_execute_needs_input_without_graph_call(self):
        fast_scan = load_fast_scan()

        def coordinator(*args, **kwargs):
            self.fail("coordinator must not run without a trustworthy seed")

        result = fast_scan.execute_fast_scan(
            fast_scan.FastScanRequest(self.root, "make it nicer", (), "simple"),
            {
                "enabled": True, "max_seconds": 30, "target_seconds": 10,
                "providers": ["builtin"], "install_policy": "never",
                "deep": False,
            },
            payload_sha256="a" * 64,
            coordinator=coordinator,
        )
        self.assertEqual(result.status, "needs_input")
        self.assertFalse(result.can_promote)

    def test_execute_reuses_exact_scan_and_source_mutation_invalidates_it(self):
        fast_scan = load_fast_scan()
        source = self.write("api/profile.py", 'FIELD = "profile.displayName"\n')
        graph = json.loads(
            (ROOT / "tests/fixtures/impact-graph-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        graph["budget_status"] = "closed"
        graph["frontier"] = []
        calls = []

        def coordinator(*args, **kwargs):
            calls.append(1)
            value = copy.deepcopy(graph)
            value["receipt_id"] = ("%032x" % len(calls))
            return value

        request = fast_scan.FastScanRequest(
            self.root, "Rename profile.displayName", (), "balanced"
        )
        first = fast_scan.execute_fast_scan(
            request, graph["settings"], "a" * 64, coordinator=coordinator
        )
        second = fast_scan.execute_fast_scan(
            request, graph["settings"], "a" * 64, coordinator=coordinator
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(second.scan_id, first.scan_id)
        self.assertEqual(second.cache_status, "hit")

        source.write_text('FIELD = "profile.displayName"\n# changed\n', encoding="utf-8")
        third = fast_scan.execute_fast_scan(
            request, graph["settings"], "a" * 64, coordinator=coordinator
        )
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(third.scan_id, first.scan_id)


if __name__ == "__main__":
    unittest.main()


class CredentialShapedEvidenceTest(unittest.TestCase):
    """Prefixed credential names must be rejected as evidence, matching the
    graph scanner's redaction coverage."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_fast_scan()

    def test_rejects_prefixed_credential_assignments(self):
        for row in (
            'GITHUB_TOKEN = "ghp_leaked"',
            'DB_PASSWORD: "hunter2"',
            'STRIPE_SECRET_KEY = "sk_live_leaked"',
            'apiKey: "AIzaLeaked"',
            'githubToken = "ghp_camel"',
            'stripeSecretKey = "sk_live"',
            'GITHUB_TOKEN := "walrus"',
            'tokenProd = "suffix"',
        ):
            with self.subTest(row=row):
                self.assertIsNotNone(self.module._SECRET.search(row), row)

    def test_accepts_non_credential_identifiers(self):
        for row in ('tokenizer = "whitespace"', 'keyboard_layout = "qwerty"'):
            with self.subTest(row=row):
                self.assertIsNone(self.module._SECRET.search(row), row)


class IgnoredDirectoryParityTest(unittest.TestCase):
    """The inventory walker must skip the same dependency and build
    directories as the graph scanner, so scan identity is not bound to
    node_modules churn and dependency files are never hashed."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_inventory_skips_dependency_and_build_directories(self):
        fast_scan = load_fast_scan()
        self.write("src/app.py", 'VALUE = "kept"\n')
        self.write("node_modules/pkg/package.json", '{"token": "npm_leaked"}\n')
        self.write(".venv/lib/site.py", "SITE = 1\n")
        self.write("dist/bundle.js", "var bundled = 1;\n")
        self.write("vendor/lib.rb", "VENDORED = 1\n")

        inventory = fast_scan._inventory(self.root, FakeDeadline())

        self.assertEqual(sorted(inventory.digests), ["src/app.py"])


class PromotionReachabilityTest(unittest.TestCase):
    """A scan whose built-in engine closed its bounded coverage must be
    promotable even when no optional external provider is installed;
    otherwise the documented rir_begin promotion path is unreachable on
    every default install."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        (self.root / "api").mkdir()
        (self.root / "api" / "profile.py").write_text(
            'FIELD = "profile.displayName"\n', encoding="utf-8"
        )

    def run_scan(self, graph):
        fast_scan = load_fast_scan()
        return fast_scan.execute_fast_scan(
            fast_scan.FastScanRequest(
                self.root, "Rename profile.displayName", (), "balanced"
            ),
            graph["settings"],
            payload_sha256="a" * 64,
            coordinator=lambda *args, **kwargs: graph,
        )

    def load_graph(self):
        return json.loads(
            (ROOT / "tests/fixtures/impact-graph-receipt.json").read_text(
                encoding="utf-8"
            )
        )

    def test_missing_providers_alone_do_not_block_promotion(self):
        graph = self.load_graph()
        self.assertEqual(graph["budget_status"], "provider_limited")
        for row in graph["frontier"]:
            row["reason"] = "provider unavailable; built-in fallback used: scip"

        result = self.run_scan(graph)

        self.assertEqual(result.status, "complete")
        self.assertTrue(result.can_promote)

    def test_provider_limited_with_coverage_gap_stays_partial(self):
        graph = self.load_graph()
        self.assertEqual(graph["budget_status"], "provider_limited")
        graph["frontier"][0]["reason"] = "graph coverage remains incomplete"

        result = self.run_scan(graph)

        self.assertEqual(result.status, "partial")
        self.assertFalse(result.can_promote)

    def test_budget_exhausted_scan_stays_partial(self):
        fast_scan = load_fast_scan()
        graph = json.loads(
            (ROOT / "tests/fixtures/impact-graph-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        graph["budget_status"] = "budget_exhausted"

        result = fast_scan.execute_fast_scan(
            fast_scan.FastScanRequest(
                self.root, "Rename profile.displayName", (), "balanced"
            ),
            graph["settings"],
            payload_sha256="a" * 64,
            coordinator=lambda *args, **kwargs: graph,
        )

        self.assertEqual(result.status, "partial")
        self.assertFalse(result.can_promote)
