from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "evals" / "corpora" / "catalog.json"
EXPECTED_PATH = ROOT / "evals" / "corpora" / "expected-relationships.json"
FETCHER_PATH = ROOT / "scripts" / "fetch-graph-corpora.py"
SCORER_PATH = ROOT / "scripts" / "score-graph-corpora.py"


def load_script(path: Path, name: str):
    if not path.is_file():
        return None
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


class GraphCorpusCatalogTests(unittest.TestCase):
    def test_corpus_catalog_is_pinned_and_licensed(self):
        self.assertTrue(CATALOG_PATH.is_file(), "the public-corpus catalog is missing")
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        catalog = payload["corpora"]

        self.assertEqual(catalog[0]["commit"], "68e7ea7228ca144c52e4d1d282cc09da59f7771f")
        self.assertEqual(catalog[0]["license"], "BSD-3-Clause")
        self.assertEqual(catalog[1]["commit"], "7c318bd1aa4b4affab29761f15a9604323fe2a3b")
        self.assertEqual(catalog[1]["license"], "MIT")

        for row in catalog:
            with self.subTest(corpus=row["id"]):
                preserved = CATALOG_PATH.parent / row["preserved_license"]
                payload = preserved.read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), row["license_sha256"])
                self.assertEqual(row["repository"], row["provenance"]["repository"])
                self.assertEqual(row["commit"], row["provenance"]["commit"])
                self.assertEqual(row["license_path"], row["provenance"]["license_path"])

    def test_fetcher_refuses_a_destination_inside_the_repository(self):
        self.assertTrue(FETCHER_PATH.is_file(), "the explicit corpus fetcher is missing")
        fetcher = load_script(FETCHER_PATH, "fetch_graph_corpora_for_test")
        assert fetcher is not None
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            destination = Path(temporary) / "corpora"
            with self.assertRaisesRegex(fetcher.CorpusError, "outside the repository"):
                fetcher.validate_destination(
                    destination,
                    ROOT,
                    approved_destination=destination,
                )


class GraphCorpusFetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fetcher = load_script(FETCHER_PATH, "fetch_graph_corpora_fetch_tests")
        if cls.fetcher is None:
            raise unittest.SkipTest("the explicit corpus fetcher is missing")

    def git(self, *arguments, cwd=None):
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

    def make_repository(self, root: Path, *, symlink: bool = False):
        remote = root / "remote"
        remote.mkdir()
        self.git("init", "-q", cwd=remote)
        self.git("config", "user.email", "corpus@example.invalid", cwd=remote)
        self.git("config", "user.name", "Corpus Fixture", cwd=remote)
        license_bytes = b"fixture license\n"
        (remote / "LICENSE.txt").write_bytes(license_bytes)
        (remote / "module.py").write_text("def public_symbol():\n    return 1\n", encoding="utf-8")
        if symlink:
            (remote / "linked.py").symlink_to("module.py")
        self.git("add", ".", cwd=remote)
        self.git("commit", "-q", "-m", "fixture", cwd=remote)
        commit = self.git("rev-parse", "HEAD", cwd=remote)

        metadata = root / "metadata"
        licenses = metadata / "LICENSES"
        licenses.mkdir(parents=True)
        (licenses / "fixture.txt").write_bytes(license_bytes)
        catalog = {
            "schema_version": 1,
            "corpora": [
                {
                    "id": "fixture",
                    "checkout": "fixture",
                    "repository": remote.resolve().as_uri(),
                    "commit": commit,
                    "license": "MIT",
                    "license_path": "LICENSE.txt",
                    "license_sha256": hashlib.sha256(license_bytes).hexdigest(),
                    "preserved_license": "LICENSES/fixture.txt",
                    "provenance": {
                        "repository": remote.resolve().as_uri(),
                        "commit": commit,
                        "license_path": "LICENSE.txt",
                    },
                }
            ],
        }
        catalog_path = metadata / "catalog.json"
        catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
        return remote, commit, catalog_path

    def fetch_fixture(self, root: Path, *, symlink: bool = False):
        remote, commit, catalog_path = self.make_repository(root, symlink=symlink)
        destination = root / "destination"
        summary = self.fetcher.fetch_corpora(
            catalog_path,
            destination,
            repository_root=ROOT,
            approved_destination=destination,
            allow_local_repositories=True,
        )
        return remote, commit, catalog_path, destination, summary

    def test_fetches_one_detached_clean_exact_commit_with_license_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            remote, commit, catalog_path, destination, summary = self.fetch_fixture(root)
            checkout = destination / "fixture"

            self.assertEqual(summary["destination"], str(destination.resolve()))
            self.assertEqual(summary["corpora"][0]["commit"], commit)
            self.assertEqual(
                summary["corpora"][0]["license_sha256"],
                hashlib.sha256(b"fixture license\n").hexdigest(),
            )
            self.assertEqual(self.git("rev-parse", "HEAD", cwd=checkout), commit)
            self.assertEqual(
                self.git("remote", "get-url", "origin", cwd=checkout), remote.resolve().as_uri()
            )
            self.assertEqual(
                self.git("status", "--porcelain=v1", "--untracked-files=all", cwd=checkout), ""
            )
            self.assertEqual(self.git("rev-list", "--count", "HEAD", cwd=checkout), "1")
            self.assertEqual((checkout / "LICENSE.txt").read_bytes(), b"fixture license\n")
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)

            verified = self.fetcher.verify_corpora(
                catalog_path,
                destination,
                repository_root=ROOT,
                approved_destination=destination,
                allow_local_repositories=True,
            )
            self.assertEqual(verified, summary)

    def test_verifier_rejects_remote_head_and_dirty_checkout_drift(self):
        mutations = (
            lambda checkout: self.git("remote", "set-url", "origin", "file:///wrong", cwd=checkout),
            lambda checkout: self.git("checkout", "-q", "HEAD^0", cwd=checkout),
            lambda checkout: (checkout / "module.py").write_text("changed\n", encoding="utf-8"),
        )
        findings = ("remote URL", "detached HEAD", "clean")
        for mutate, finding in zip(mutations, findings):
            with self.subTest(finding=finding), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                _, _, catalog_path, destination, _ = self.fetch_fixture(root)
                checkout = destination / "fixture"
                if finding == "detached HEAD":
                    self.git("checkout", "-q", "-b", "unexpected", cwd=checkout)
                else:
                    mutate(checkout)
                with self.assertRaisesRegex(self.fetcher.CorpusError, finding):
                    self.fetcher.verify_corpora(
                        catalog_path,
                        destination,
                        repository_root=ROOT,
                        approved_destination=destination,
                        allow_local_repositories=True,
                    )

    def test_fetch_rejects_symlinked_corpus_and_removes_partial_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, _, catalog_path = self.make_repository(root, symlink=True)
            destination = root / "destination"
            with self.assertRaisesRegex(self.fetcher.CorpusError, "symlink"):
                self.fetcher.fetch_corpora(
                    catalog_path,
                    destination,
                    repository_root=ROOT,
                    approved_destination=destination,
                    allow_local_repositories=True,
                )
            self.assertFalse(os.path.lexists(destination))

    def test_license_mismatch_reports_actual_and_expected_digests(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, _, catalog_path = self.make_repository(root)
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            preserved = catalog_path.parent / catalog["corpora"][0]["preserved_license"]
            expected_bytes = b"different preserved license\n"
            preserved.write_bytes(expected_bytes)
            expected_digest = hashlib.sha256(expected_bytes).hexdigest()
            actual_digest = hashlib.sha256(b"fixture license\n").hexdigest()
            catalog["corpora"][0]["license_sha256"] = expected_digest
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

            destination = root / "destination"
            with self.assertRaisesRegex(
                self.fetcher.CorpusError,
                f"expected {expected_digest}, got {actual_digest}",
            ):
                self.fetcher.fetch_corpora(
                    catalog_path,
                    destination,
                    repository_root=ROOT,
                    approved_destination=destination,
                    allow_local_repositories=True,
                )
            self.assertFalse(os.path.lexists(destination))

    def test_destination_rejects_symlink_parent_and_any_git_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            real = root / "real"
            real.mkdir()
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(self.fetcher.CorpusError, "symlink"):
                self.fetcher.validate_destination(
                    alias / "corpora",
                    ROOT,
                    approved_destination=alias / "corpora",
                )

            repository = root / "unrelated-repository"
            repository.mkdir()
            self.git("init", "-q", cwd=repository)
            with self.assertRaisesRegex(self.fetcher.CorpusError, "Git repository"):
                self.fetcher.validate_destination(
                    repository / "corpora",
                    ROOT,
                    approved_destination=repository / "corpora",
                )

    def test_bounded_command_rejects_output_overflow_and_timeout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            executable = root / "fake-git"
            executable.write_text(
                f"#!{sys.executable}\n"
                "import sys\n"
                "import time\n"
                "if sys.argv[1] == 'overflow':\n"
                "    sys.stdout.write('x' * 33)\n"
                "else:\n"
                "    time.sleep(1)\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            with self.assertRaisesRegex(self.fetcher.CorpusError, "output bound"):
                self.fetcher.run_bounded(
                    (str(executable), "overflow"),
                    root,
                    timeout=1,
                    stdout_limit=32,
                    stderr_limit=32,
                )
            with self.assertRaisesRegex(self.fetcher.CorpusError, "timed out"):
                self.fetcher.run_bounded(
                    (str(executable), "sleep"),
                    root,
                    timeout=0.05,
                    stdout_limit=32,
                    stderr_limit=32,
                )

    def test_catalog_loader_rejects_provenance_digest_and_url_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, _, catalog_path = self.make_repository(root)
            baseline = json.loads(catalog_path.read_text(encoding="utf-8"))
            mutations = {
                "unknown or missing": lambda row: row.update({"unexpected": True}),
                "provenance": lambda row: row["provenance"].update({"commit": "0" * 40}),
                "digest": lambda row: row.update({"license_sha256": "0" * 64}),
                "exact GitHub": lambda row: row.update(
                    {"repository": "https://example.invalid/repository.git"}
                ),
            }
            for finding, mutate in mutations.items():
                with self.subTest(finding=finding):
                    payload = json.loads(json.dumps(baseline))
                    mutate(payload["corpora"][0])
                    selected = catalog_path.parent / f"{finding.split()[0]}.json"
                    selected.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(self.fetcher.CorpusError, finding):
                        self.fetcher.load_catalog(
                            selected,
                            allow_local_repositories=True,
                        )

    def test_fetch_cli_rejects_repository_destination_without_network(self):
        fetcher = load_script(FETCHER_PATH, "fetch_graph_corpora_cli_test")
        assert fetcher is not None
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status = fetcher.main(["--destination", str(ROOT / "forbidden-corpora")])
        self.assertEqual(status, 2)
        self.assertIn("outside the repository", stderr.getvalue())


class GraphCorpusExpectationTests(unittest.TestCase):
    def test_expected_relationships_are_literal_and_independently_curated(self):
        self.assertTrue(EXPECTED_PATH.is_file(), "the curated relationship catalog is missing")
        payload = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["corpora"]

        self.assertEqual(
            payload["gates"],
            {
                "minimum_precision": 0.9,
                "minimum_recall": 0.8,
                "maximum_median_seconds": 10,
                "maximum_hard_seconds": 30,
                "maximum_compact_bytes": 24_000,
                "allow_undisclosed_high_risk_miss": False,
            },
        )
        self.assertEqual(payload["curation"]["method"], "manual-pinned-source-review")
        self.assertFalse(payload["curation"]["engine_output_used"])
        self.assertEqual(
            [(row["id"], row["commit"]) for row in payload["corpora"]],
            [(row["id"], row["commit"]) for row in catalog],
        )
        relationships = [
            (corpus["id"], relationship)
            for corpus in payload["corpora"]
            for relationship in corpus["relationships"]
        ]
        self.assertEqual(len(relationships), 3)
        self.assertTrue(all(row["evidence"] and row["term"] for _, row in relationships))
        self.assertTrue(
            any(
                corpus_id == "pallets-click" and row["high_risk"]
                for corpus_id, row in relationships
            )
        )
        self.assertTrue(
            all(not corpus["disclosed_high_risk_misses"] for corpus in payload["corpora"])
        )


class GraphCorpusScoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scorer = load_script(SCORER_PATH, "score_graph_corpora_tests")

    def require_scorer(self):
        self.assertTrue(SCORER_PATH.is_file(), "the graph corpus scorer is missing")
        self.assertIsNotNone(self.scorer)
        return self.scorer

    def test_fake_score_is_deterministic_and_reports_literal_metrics(self):
        scorer = self.require_scorer()
        expected = {
            ("fixture", "builtin", "source.py", "target.py"): True,
            ("fixture", "ast-grep", "source.py", "target.py"): True,
        }
        negatives = {
            ("fixture", "builtin", "source.py", "negative.py"),
            ("fixture", "ast-grep", "source.py", "negative.py"),
        }
        observations = (
            scorer.EngineObservation(
                "fixture",
                "builtin",
                (("source.py", "target.py"), ("other.py", "frontier.py")),
                2,
                9000,
                "builtin-v1",
                None,
            ),
            scorer.EngineObservation(
                "fixture",
                "ast-grep",
                (("source.py", "target.py"),),
                4,
                10_000,
                "ast-grep 0.45.0",
                "a" * 64,
            ),
        )

        first, first_bytes = scorer.score_observations(expected, negatives, set(), observations)
        second, second_bytes = scorer.score_observations(expected, negatives, set(), observations)

        self.assertEqual(first, second)
        self.assertEqual(first_bytes, second_bytes)
        self.assertFalse(first_bytes.endswith(b"\n"))
        self.assertEqual(first["aggregate"]["true_positive"], 2)
        self.assertEqual(first["aggregate"]["false_positive"], 0)
        self.assertEqual(first["aggregate"]["false_negative"], 0)
        self.assertEqual(first["aggregate"]["precision"], 1.0)
        self.assertEqual(first["aggregate"]["recall"], 1.0)
        self.assertEqual(first["aggregate"]["unknown_frontier"], 7)
        self.assertEqual(first["aggregate"]["median_duration_ms"], 9500)
        self.assertEqual(first["aggregate"]["hard_duration_ms"], 10_000)
        self.assertEqual(first["aggregate"]["compact_bytes"], len(first_bytes))
        self.assertLessEqual(len(first_bytes), 24_000)
        self.assertTrue(first["passed"])

    def test_literal_gate_function_rejects_every_boundary_violation(self):
        scorer = self.require_scorer()
        cases = {
            "precision": (0.899999, 1.0, (), (1000,), 1000, "precision"),
            "recall": (1.0, 0.799999, (), (1000,), 1000, "recall"),
            "high-risk": (1.0, 1.0, ("fixture:builtin:a.py->b.py",), (1000,), 1000, "high_risk"),
            "median": (1.0, 1.0, (), (10_001,), 1000, "median_duration"),
            "hard": (1.0, 1.0, (), (0, 0, 30_001), 1000, "hard_duration"),
            "compact": (1.0, 1.0, (), (1000,), 24_001, "compact_bytes"),
        }
        for name, (precision, recall, misses, durations, compact, failed_gate) in cases.items():
            with self.subTest(name=name):
                gates = scorer.evaluate_gates(
                    precision,
                    recall,
                    misses,
                    durations,
                    compact,
                )
                self.assertFalse(gates[failed_gate])
                self.assertFalse(gates["passed"])

        boundary = scorer.evaluate_gates(0.9, 0.8, (), (0, 10_000, 30_000), 24_000)
        self.assertTrue(boundary["passed"])

    def test_observation_and_score_shapes_fail_closed(self):
        scorer = self.require_scorer()
        valid = ["fixture", "builtin", (("a.py", "b.py"),), 0, 1, "builtin-v1", None]
        mutations = {
            "corpus": (0, ""),
            "provider": (1, "remote"),
            "predictions": (2, (("only-one",),)),
            "frontier-type": (3, True),
            "frontier-negative": (3, -1),
            "duration-type": (4, True),
            "duration-negative": (4, -1),
            "version": (5, ""),
            "digest": (6, "x" * 64),
        }
        for name, (index, value) in mutations.items():
            with self.subTest(name=name):
                arguments = list(valid)
                arguments[index] = value
                with self.assertRaises(ValueError):
                    scorer.EngineObservation(*arguments)

        observation = scorer.EngineObservation(*valid)
        expected = {("fixture", "builtin", "a.py", "b.py"): False}
        with self.assertRaisesRegex(scorer.CorpusScoreError, "overlap"):
            scorer.score_observations(
                expected,
                {("fixture", "builtin", "a.py", "b.py")},
                set(),
                (observation,),
            )
        with self.assertRaisesRegex(scorer.CorpusScoreError, "cover"):
            scorer.score_observations(expected, set(), set(), ())

        unavailable = SimpleNamespace(status="failed", nodes=(), edges=(), frontier=())
        projected = scorer.project_ast_grep_result(
            "fixture",
            unavailable,
            5,
            "ast-grep 0.45.0",
            "d" * 64,
        )
        self.assertEqual(projected.predictions, ())
        self.assertEqual(projected.frontier_count, 1)

    def test_score_cli_rejects_repository_destination_without_running_provider(self):
        scorer = self.require_scorer()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status = scorer.main(["--corpora", str(ROOT)])
        self.assertEqual(status, 2)
        self.assertIn("outside the repository", stderr.getvalue())

    def test_guard_detects_any_fake_engine_corpus_mutation(self):
        scorer = self.require_scorer()
        fetcher = load_script(FETCHER_PATH, "fetch_graph_corpora_guard_test")
        assert fetcher is not None
        helper = GraphCorpusFetchTests(methodName="runTest")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, _, catalog_path = helper.make_repository(root)
            destination = root / "destination"
            fetcher.fetch_corpora(
                catalog_path,
                destination,
                repository_root=ROOT,
                approved_destination=destination,
                allow_local_repositories=True,
            )

            def mutate():
                (destination / "fixture/module.py").write_text("mutated\n", encoding="utf-8")
                return "untrusted engine result"

            with self.assertRaisesRegex(scorer.CorpusScoreError, "changed corpus checkout"):
                scorer.guard_verified_corpora(
                    catalog_path,
                    destination,
                    mutate,
                    repository_root=ROOT,
                    approved_destination=destination,
                    allow_local_repositories=True,
                )

    def test_expectation_loader_expands_provider_pairs_and_rejects_engine_generation(self):
        scorer = self.require_scorer()
        specifications = scorer.FETCHER.load_catalog(CATALOG_PATH)
        loaded = scorer.load_expectations(EXPECTED_PATH, specifications)

        self.assertEqual(len(loaded.corpora), 2)
        self.assertEqual(len(loaded.expected), 6)
        self.assertEqual(len(loaded.negatives), 6)
        self.assertEqual(loaded.disclosed_high_risk_misses, frozenset())
        self.assertTrue(
            loaded.expected[
                (
                    "pallets-click",
                    "ast-grep",
                    "src/click/core.py",
                    "src/click/parser.py",
                )
            ]
        )

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "expected.json"
            payload = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
            payload["curation"]["engine_output_used"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(scorer.CorpusScoreError, "independently curated"):
                scorer.load_expectations(path, specifications)

            payload = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
            payload["corpora"][0]["scope"] = None
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(scorer.CorpusScoreError, "list fields"):
                scorer.load_expectations(path, specifications)

    def test_provider_projection_keeps_structural_pairs_and_counts_unknown_frontier(self):
        scorer = self.require_scorer()
        nodes = (
            SimpleNamespace(id="N1", location="source.py"),
            SimpleNamespace(id="N2", location="target.py"),
            SimpleNamespace(id="N3", location="negative.py"),
            SimpleNamespace(id="N4", location="unknown.py"),
        )
        builtin = SimpleNamespace(
            nodes=nodes,
            edges=(
                SimpleNamespace(
                    source="N1",
                    target="N2",
                    kind="imports",
                    confidence="structural-inferred",
                ),
                SimpleNamespace(source="N1", target="N3", kind="references", confidence="lexical"),
                SimpleNamespace(
                    source="N1",
                    target="N3",
                    kind="references",
                    confidence="structural-inferred",
                ),
                SimpleNamespace(
                    source="N1",
                    target="N4",
                    kind="imports",
                    confidence="structural-inferred",
                ),
            ),
            frontier=(SimpleNamespace(id="F1"),),
            budget_status="closed",
        )
        built_observation = scorer.project_builtin_result("fixture", builtin, 123)
        self.assertEqual(
            built_observation.predictions,
            (("source.py", "target.py"), ("source.py", "unknown.py")),
        )
        self.assertEqual(built_observation.frontier_count, 3)

        ast_grep = SimpleNamespace(
            status="ready",
            nodes=(
                {"key": "seed", "location": "source.py"},
                {"key": "target", "location": "target.py"},
                {"key": "self", "location": "source.py"},
            ),
            edges=(
                {"source": "seed", "target": "target"},
                {"source": "seed", "target": "self"},
            ),
            frontier=(),
        )
        ast_observation = scorer.project_ast_grep_result(
            "fixture",
            ast_grep,
            456,
            "ast-grep 0.45.0",
            "b" * 64,
        )
        self.assertEqual(ast_observation.predictions, (("source.py", "target.py"),))
        self.assertEqual(ast_observation.frontier_count, 1)

    def test_real_engines_find_a_local_two_file_relationship(self):
        scorer = self.require_scorer()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "source.py").write_text(
                "from target import Target\n\nvalue = Target()\n",
                encoding="utf-8",
            )
            (root / "target.py").write_text("class Target:\n    pass\n", encoding="utf-8")
            (root / "unrelated.py").write_text("value = 1\n", encoding="utf-8")
            corpus = scorer.CorpusCase(
                "fixture",
                "f" * 40,
                ("source.py", "target.py", "unrelated.py"),
                (scorer.Seed("Target", "source.py"),),
                (),
                (scorer.RelationshipQuery("Target", "source.py", "target.py"),),
            )

            with self.assertRaisesRegex(scorer.CorpusScoreError, "ast-grep executable"):
                scorer.run_ast_grep(corpus, root, root / "missing-ast-grep")

            builtin = scorer.run_builtin(corpus, root)
            self.assertIn(("source.py", "target.py"), builtin.predictions)
            self.assertLessEqual(builtin.duration_ms, 30_000)

            executable = ROOT / ".quality-venv/bin/ast-grep"
            if not executable.is_file():
                self.skipTest("pinned ast-grep 0.45.0 is not installed")
            version = subprocess.run(
                [str(executable), "--version"],
                text=True,
                capture_output=True,
                check=False,
            )
            if version.stdout.strip() != "ast-grep 0.45.0":
                self.skipTest("pinned ast-grep 0.45.0 is not installed")
            ast_grep = scorer.run_ast_grep(corpus, root, executable)
            self.assertIn(("source.py", "target.py"), ast_grep.predictions)
            self.assertEqual(ast_grep.version, "ast-grep 0.45.0")
            self.assertRegex(ast_grep.executable_sha256, r"^[0-9a-f]{64}$")
            self.assertLessEqual(ast_grep.duration_ms, 30_000)

    def make_local_expectations(self, root: Path, commit: str) -> Path:
        payload = {
            "schema_version": 1,
            "curation": {
                "method": "manual-pinned-source-review",
                "engine_output_used": False,
                "source_basis": "Local fixture source was read before fake engine output.",
                "reviewed_commits": [commit],
            },
            "gates": {
                "minimum_precision": 0.9,
                "minimum_recall": 0.8,
                "maximum_median_seconds": 10,
                "maximum_hard_seconds": 30,
                "maximum_compact_bytes": 24_000,
                "allow_undisclosed_high_risk_miss": False,
            },
            "corpora": [
                {
                    "id": "fixture",
                    "commit": commit,
                    "scope": ["LICENSE.txt", "module.py"],
                    "seeds": [{"term": "public_symbol", "location": "module.py"}],
                    "relationships": [
                        {
                            "source": "module.py",
                            "target": "LICENSE.txt",
                            "term": "public_symbol",
                            "providers": ["builtin", "ast-grep"],
                            "high_risk": True,
                            "risk_domains": ["interfaces"],
                            "evidence": "def public_symbol():",
                        }
                    ],
                    "negative_relationships": [],
                    "disclosed_high_risk_misses": [],
                }
            ],
        }
        path = root / "expected.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_run_evaluation_binds_evidence_and_scores_fake_local_engines(self):
        scorer = self.require_scorer()
        fetcher = load_script(FETCHER_PATH, "fetch_graph_corpora_evaluation_test")
        assert fetcher is not None
        helper = GraphCorpusFetchTests(methodName="runTest")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, commit, catalog_path = helper.make_repository(root)
            destination = root / "destination"
            fetcher.fetch_corpora(
                catalog_path,
                destination,
                repository_root=ROOT,
                approved_destination=destination,
                allow_local_repositories=True,
            )
            expected_path = self.make_local_expectations(root, commit)

            def builtin(case, _checkout):
                return scorer.EngineObservation(
                    case.id,
                    "builtin",
                    (("module.py", "LICENSE.txt"),),
                    0,
                    100,
                    "builtin-v1",
                    None,
                )

            def ast_grep(case, _checkout, _executable):
                return scorer.EngineObservation(
                    case.id,
                    "ast-grep",
                    (("module.py", "LICENSE.txt"),),
                    1,
                    200,
                    "ast-grep 0.45.0",
                    "c" * 64,
                )

            report, report_bytes = scorer.run_evaluation(
                catalog_path,
                expected_path,
                destination,
                Path("/unused/fake-ast-grep"),
                repository_root=ROOT,
                approved_destination=destination,
                allow_local_repositories=True,
                builtin_runner=builtin,
                ast_grep_runner=ast_grep,
            )
            self.assertTrue(report["passed"])
            self.assertEqual(
                report["provenance"]["catalog_sha256"],
                hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                report["provenance"]["expectations_sha256"],
                hashlib.sha256(expected_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(report["aggregate"]["unknown_frontier"], 1)
            self.assertEqual(len(report_bytes), report["aggregate"]["compact_bytes"])

            payload = json.loads(expected_path.read_text(encoding="utf-8"))
            payload["corpora"][0]["relationships"][0]["evidence"] = "not in pinned source"
            expected_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(scorer.CorpusScoreError, "curated evidence"):
                scorer.run_evaluation(
                    catalog_path,
                    expected_path,
                    destination,
                    Path("/unused/fake-ast-grep"),
                    repository_root=ROOT,
                    approved_destination=destination,
                    allow_local_repositories=True,
                    builtin_runner=builtin,
                    ast_grep_runner=ast_grep,
                )


if __name__ == "__main__":
    unittest.main()
