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
from unittest import mock

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
        self.assertEqual(
            catalog[0]["candidate_rule"],
            {
                "root": "src/click",
                "pattern": "*.py",
                "recursive": False,
                "maximum_files": 64,
            },
        )
        self.assertEqual(
            catalog[1]["candidate_rule"],
            {
                "root": ".",
                "pattern": "*.js",
                "recursive": False,
                "maximum_files": 16,
            },
        )

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

    def make_repository(self, root: Path, *, symlink: bool = False, gitlink: bool = False):
        remote = root / "remote"
        remote.mkdir()
        self.git("init", "-q", cwd=remote)
        self.git("config", "user.email", "corpus@example.invalid", cwd=remote)
        self.git("config", "user.name", "Corpus Fixture", cwd=remote)
        license_bytes = b"fixture license\n"
        (remote / "LICENSE.txt").write_bytes(license_bytes)
        (remote / "module.py").write_text(
            "from target import public_symbol\n\nvalue = public_symbol()\n",
            encoding="utf-8",
        )
        (remote / "target.py").write_text(
            "def public_symbol():\n    return 1\n",
            encoding="utf-8",
        )
        if symlink:
            (remote / "linked.py").symlink_to("module.py")
        self.git("add", ".", cwd=remote)
        self.git("commit", "-q", "-m", "fixture", cwd=remote)
        commit = self.git("rev-parse", "HEAD", cwd=remote)
        if gitlink:
            self.git(
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{commit},nested-repository",
                cwd=remote,
            )
            self.git("commit", "-q", "-m", "add gitlink", cwd=remote)
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
                    "candidate_rule": {
                        "root": ".",
                        "pattern": "*.py",
                        "recursive": False,
                        "maximum_files": 16,
                    },
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
                allow_local_repositories=True,
            )
            self.assertEqual(verified, summary)

    def test_verifier_rejects_remote_head_and_dirty_checkout_drift(self):
        mutations = (
            lambda checkout: self.git("remote", "set-url", "origin", "file:///wrong", cwd=checkout),
            lambda checkout: self.git("checkout", "-q", "HEAD^0", cwd=checkout),
            lambda checkout: (checkout / "module.py").write_text("changed\n", encoding="utf-8"),
        )
        findings = ("remote URL", "detached HEAD", "blob identity")
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
                        allow_local_repositories=True,
                    )

    def test_fetch_rejects_symlinked_corpus_and_removes_partial_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, _, catalog_path = self.make_repository(root, symlink=True)
            destination = root / "destination"
            with self.assertRaisesRegex(self.fetcher.CorpusError, "tree mode"):
                self.fetcher.fetch_corpora(
                    catalog_path,
                    destination,
                    repository_root=ROOT,
                    allow_local_repositories=True,
                )
            self.assertFalse(os.path.lexists(destination))

    def test_fetch_rejects_gitlink_tree_mode_and_removes_partial_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, _, catalog_path = self.make_repository(root, gitlink=True)
            destination = root / "destination"
            with self.assertRaisesRegex(self.fetcher.CorpusError, "tree mode"):
                self.fetcher.fetch_corpora(
                    catalog_path,
                    destination,
                    repository_root=ROOT,
                    allow_local_repositories=True,
                )
            self.assertFalse(os.path.lexists(destination))

    def test_verifier_rejects_ignored_poison_and_index_visibility_flags(self):
        mutations = ("ignored", "skip-worktree", "assume-unchanged", "hidden-mode")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                _, _, catalog_path, destination, _ = self.fetch_fixture(root)
                checkout = destination / "fixture"
                if mutation == "ignored":
                    (checkout / ".git/info/exclude").write_text("ignored-poison.txt\n")
                    (checkout / "ignored-poison.txt").write_text("poison\n", encoding="utf-8")
                    self.assertEqual(
                        self.git("status", "--porcelain=v1", "--untracked-files=all", cwd=checkout),
                        "",
                    )
                    finding = "worktree path set"
                elif mutation == "skip-worktree":
                    self.git("update-index", "--skip-worktree", "module.py", cwd=checkout)
                    finding = "index flags"
                elif mutation == "assume-unchanged":
                    self.git("update-index", "--assume-unchanged", "module.py", cwd=checkout)
                    finding = "index flags"
                else:
                    self.git("config", "core.filemode", "false", cwd=checkout)
                    (checkout / "module.py").chmod(0o755)
                    self.assertEqual(
                        self.git("status", "--porcelain=v1", "--untracked-files=all", cwd=checkout),
                        "",
                    )
                    finding = "worktree mode"
                with self.assertRaisesRegex(self.fetcher.CorpusError, finding):
                    self.fetcher.verify_corpora(
                        catalog_path,
                        destination,
                        repository_root=ROOT,
                        allow_local_repositories=True,
                    )

    def test_verifier_disables_repository_local_fsmonitor_and_hooks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, _, catalog_path, destination, summary = self.fetch_fixture(root)
            checkout = destination / "fixture"
            marker = root / "local-helper-ran"
            helper = root / "local-helper"
            helper.write_text(
                f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\n",
                encoding="utf-8",
            )
            helper.chmod(0o755)
            hooks = root / "hooks"
            hooks.mkdir()
            self.git("config", "core.fsmonitor", str(helper), cwd=checkout)
            self.git("config", "core.hooksPath", str(hooks), cwd=checkout)
            self.git("config", "status.showUntrackedFiles", "no", cwd=checkout)

            verified = self.fetcher.verify_corpora(
                catalog_path,
                destination,
                repository_root=ROOT,
                allow_local_repositories=True,
            )

            self.assertEqual(verified, summary)
            self.assertFalse(marker.exists())

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
                )

            repository = root / "unrelated-repository"
            repository.mkdir()
            self.git("init", "-q", cwd=repository)
            with self.assertRaisesRegex(self.fetcher.CorpusError, "Git repository"):
                self.fetcher.validate_destination(
                    repository / "corpora",
                    ROOT,
                )

    def test_destination_accepts_portable_absolute_temporary_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            private_root = Path(temporary).resolve()
            candidates = (
                private_root / "portable-corpora",
                Path("/tmp/rir-v06-portable-destination-test"),
            )
            for candidate in candidates:
                with self.subTest(candidate=candidate):
                    self.assertFalse(os.path.lexists(candidate))
                    self.assertEqual(
                        self.fetcher.validate_destination(candidate, ROOT),
                        candidate.resolve(strict=False),
                    )

    def test_descriptor_cleanup_survives_parent_child_and_cleanup_rename_swaps(self):
        def make_paths(root: Path):
            parent = root / "parent"
            parent.mkdir()
            attacker = root / "attacker"
            attacker.mkdir()
            return parent, attacker, parent / "corpora"

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            parent, attacker, destination = make_paths(root)
            handle = self.fetcher._create_destination(destination, ROOT)
            moved_parent = root / "moved-parent"
            parent.rename(moved_parent)
            parent.symlink_to(attacker, target_is_directory=True)

            self.fetcher._cleanup_destination(handle)

            self.assertFalse((moved_parent / "corpora").exists())
            self.assertTrue(parent.is_symlink())
            self.assertEqual(tuple(attacker.iterdir()), ())

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            parent, attacker, destination = make_paths(root)
            handle = self.fetcher._create_destination(destination, ROOT)
            moved_child = parent / "moved-corpora"
            destination.rename(moved_child)
            destination.symlink_to(attacker, target_is_directory=True)

            self.fetcher._cleanup_destination(handle)

            self.assertFalse(moved_child.exists())
            self.assertTrue(destination.is_symlink())
            self.assertEqual(tuple(attacker.iterdir()), ())

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            parent, attacker, destination = make_paths(root)
            handle = self.fetcher._create_destination(destination, ROOT)

            def race(_handle, retained_name):
                retained = parent / retained_name
                moved = parent / "cleanup-race-moved"
                retained.rename(moved)
                retained.symlink_to(attacker, target_is_directory=True)

            self.fetcher._cleanup_destination(handle, before_root_remove=race)

            self.assertFalse((parent / "cleanup-race-moved").exists())
            self.assertTrue(destination.is_symlink())
            self.assertEqual(tuple(attacker.iterdir()), ())

    def test_fetch_uses_held_child_descriptor_when_destination_name_is_swapped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, _, catalog_path = self.make_repository(root)
            destination = root / "destination"
            moved = root / "moved-destination"
            attacker = root / "attacker"
            attacker.mkdir()

            def swap(_handle):
                destination.rename(moved)
                destination.symlink_to(attacker, target_is_directory=True)

            with self.assertRaisesRegex(self.fetcher.CorpusError, "destination identity"):
                self.fetcher.fetch_corpora(
                    catalog_path,
                    destination,
                    repository_root=ROOT,
                    allow_local_repositories=True,
                    after_destination_open=swap,
                )

            self.assertFalse(moved.exists())
            self.assertTrue(destination.is_symlink())
            self.assertEqual(tuple(attacker.iterdir()), ())

    def test_descriptor_and_process_failure_paths_fail_closed(self):
        with mock.patch.object(self.fetcher.os, "O_DIRECTORY", 0):
            with self.assertRaisesRegex(self.fetcher.CorpusError, "unsupported"):
                self.fetcher._directory_flags()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            destination = root / "corpora"
            handle = self.fetcher._create_destination(destination, ROOT)
            self.fetcher._verify_destination_handle(handle)
            self.fetcher._close_destination(handle)
            self.fetcher._close_destination(handle)
            with self.assertRaisesRegex(self.fetcher.CorpusError, "closed"):
                self.fetcher._verify_destination_handle(handle)
            with self.assertRaisesRegex(self.fetcher.CorpusError, "closed"):
                self.fetcher._cleanup_destination(handle)
            destination.rmdir()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            destination = root / "corpora"
            handle = self.fetcher._create_destination(destination, ROOT)
            self.fetcher._close_destination(handle)
            destination.chmod(0o755)
            with self.assertRaisesRegex(self.fetcher.CorpusError, "identity changed"):
                self.fetcher._open_destination(destination, ROOT)
            destination.rmdir()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            destination = root / "corpora"
            handle = self.fetcher._create_destination(destination, ROOT)
            os.mkfifo(destination / "unsupported-pipe")
            with self.assertRaisesRegex(self.fetcher.CorpusError, "unsupported entry"):
                self.fetcher._cleanup_destination(handle)
            (destination / "unsupported-pipe").unlink()
            destination.rmdir()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            parent = root / "parent"
            parent.mkdir()
            destination = parent / "corpora"
            moved_parent = root / "other-parent"
            moved_parent.mkdir()
            moved = moved_parent / "moved-corpora"
            handle = self.fetcher._create_destination(destination, ROOT)
            destination.rename(moved)
            with self.assertRaisesRegex(self.fetcher.CorpusError, "locate"):
                self.fetcher._cleanup_destination(handle)
            moved.rmdir()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            destination = root / "corpora"
            handle = self.fetcher._create_destination(destination, ROOT)

            def fail_cleanup(_handle, _name):
                raise RuntimeError("injected cleanup failure")

            with self.assertRaisesRegex(self.fetcher.CorpusError, "cleanup failed"):
                self.fetcher._cleanup_destination(
                    handle,
                    before_root_remove=fail_cleanup,
                )
            destination.rmdir()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            cwd_file = root / "not-a-directory"
            cwd_file.write_text("x", encoding="utf-8")
            invalid_calls = (
                ((), root, 1),
                (("missing",), root, 0),
                (("missing",), cwd_file, 1),
            )
            for command, cwd, timeout in invalid_calls:
                with self.subTest(command=command, timeout=timeout):
                    with self.assertRaises(self.fetcher.CorpusError):
                        self.fetcher.run_bounded(
                            command,
                            cwd,
                            timeout=timeout,
                            stdout_limit=1,
                            stderr_limit=1,
                        )

            non_executable = root / "git"
            non_executable.write_text("not executable", encoding="utf-8")
            with self.assertRaisesRegex(self.fetcher.CorpusError, "unavailable"):
                self.fetcher._find_git(root / "missing-git")
            with self.assertRaisesRegex(self.fetcher.CorpusError, "not executable"):
                self.fetcher._find_git(non_executable)
            linked = root / "linked-git"
            linked.symlink_to(non_executable)
            with self.assertRaisesRegex(self.fetcher.CorpusError, "non-symlink"):
                self.fetcher._find_git(linked)

            with self.assertRaisesRegex(self.fetcher.CorpusError, "not a regular directory"):
                self.fetcher._verify_checkout(
                    SimpleNamespace(id="fixture"),
                    root / "missing-checkout",
                    Path("/usr/bin/git"),
                    allow_local=True,
                )

        with mock.patch.object(Path, "is_dir", return_value=False):
            with self.assertRaisesRegex(self.fetcher.CorpusError, "unavailable"):
                self.fetcher._fd_path(999)

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

    def test_git_metadata_and_blob_parsers_fail_closed_on_malformed_evidence(self):
        git = Path("/usr/bin/git")
        oid = "0" * 40
        head_cases = {
            "malformed": b"bad\0",
            "tree mode": f"120000 blob {oid}\tlink\0".encode(),
            "object identity": b"100644 blob invalid\tfile\0",
            "must not be empty": b"",
        }
        for finding, output in head_cases.items():
            with (
                self.subTest(head=finding),
                mock.patch.object(self.fetcher, "_git", return_value=output),
            ):
                with self.assertRaisesRegex(self.fetcher.CorpusError, finding):
                    self.fetcher._head_tree(git, ROOT, allow_local=True)

        with self.assertRaisesRegex(self.fetcher.CorpusError, "not UTF-8"):
            self.fetcher._decode_tree_path(b"\xff", "fixture")
        with self.assertRaisesRegex(self.fetcher.CorpusError, "malformed"):
            self.fetcher._nul_records(b"missing terminator", "fixture")

        tree = {"file": ("100644", oid)}
        valid_stage = f"100644 {oid} 0\tfile\0".encode()
        index_cases = {
            "stage": (b"bad\0",),
            "exactly match": (f"100644 {oid} 0\tother\0".encode(),),
            "flags output": (valid_stage, b"bad\0"),
            "flags path set": (valid_stage, b"H other\0"),
        }
        for finding, outputs in index_cases.items():
            with (
                self.subTest(index=finding),
                mock.patch.object(self.fetcher, "_git", side_effect=outputs),
            ):
                with self.assertRaisesRegex(self.fetcher.CorpusError, finding):
                    self.fetcher._verify_index(git, ROOT, tree, allow_local=True)

        files = {"file": ("100644", b"payload")}
        with mock.patch.object(self.fetcher, "_git", return_value=b"md5\n"):
            with self.assertRaisesRegex(self.fetcher.CorpusError, "object format"):
                self.fetcher._verify_blob_bytes(git, ROOT, tree, files, allow_local=True)

        digest = hashlib.sha1(b"blob 7\0payload").hexdigest()
        exact_tree = {"file": ("100644", digest)}
        with mock.patch.object(
            self.fetcher,
            "_git",
            side_effect=(b"sha1\n", b"different"),
        ):
            with self.assertRaisesRegex(self.fetcher.CorpusError, "bytes differ"):
                self.fetcher._verify_blob_bytes(git, ROOT, exact_tree, files, allow_local=True)

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
                "require_zero_provider_disagreement": True,
            },
        )
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["curation"]["method"], "manual-pinned-source-review")
        self.assertFalse(payload["curation"]["engine_output_used"])
        self.assertEqual(
            [(row["id"], row["commit"]) for row in payload["corpora"]],
            [(row["id"], row["commit"]) for row in catalog],
        )
        sources = [
            (corpus["id"], source) for corpus in payload["corpora"] for source in corpus["sources"]
        ]
        relationships = [
            (corpus_id, source["path"], relationship)
            for corpus_id, source in sources
            for relationship in source["internal_imports"]
        ]
        self.assertEqual(len(sources), 2)
        self.assertEqual(len(relationships), 2)
        self.assertEqual(
            {
                (corpus_id, source, row["module"], row["target"])
                for corpus_id, source, row in relationships
            },
            {
                (
                    "pallets-click",
                    "src/click/globals.py",
                    ".core",
                    "src/click/core.py",
                ),
                (
                    "sindresorhus-slugify",
                    "index.js",
                    "./overridable-replacements.js",
                    "overridable-replacements.js",
                ),
            },
        )
        self.assertEqual(
            {source["path"]: source["sha256"] for _, source in sources},
            {
                "src/click/globals.py": "80cf8d87a0383341c1fd2824685e4ce2770618c0c773f7e51d7bbdfe88781845",
                "index.js": "300268f98ec858deb36237a7bff5adf5045191e22fcba578e2373af592fc0216",
            },
        )
        self.assertTrue(
            any(
                corpus_id == "pallets-click" and row["high_risk"]
                for corpus_id, _source, row in relationships
            )
        )
        self.assertTrue(
            all(
                corpus["disclosed_high_risk_misses"] == {"builtin": [], "ast-grep": []}
                for corpus in payload["corpora"]
            )
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
            ("fixture", "source.py", "target.py"): True,
            ("fixture", "source.py", "second.py"): False,
        }
        observations = (
            scorer.EngineObservation(
                "fixture",
                "builtin",
                (("source.py", "target.py"), ("source.py", "second.py")),
                2,
                9000,
                "builtin-v1",
                None,
                scope_inventory_complete=True,
            ),
            scorer.EngineObservation(
                "fixture",
                "ast-grep",
                (("source.py", "target.py"), ("source.py", "second.py")),
                4,
                10_000,
                "ast-grep 0.45.0",
                "a" * 64,
                scope_inventory_complete=True,
            ),
        )

        disclosures = {"builtin": set(), "ast-grep": set()}
        first, first_bytes = scorer.score_observations(expected, observations, disclosures)
        second, second_bytes = scorer.score_observations(expected, observations, disclosures)

        self.assertEqual(first, second)
        self.assertEqual(first_bytes, second_bytes)
        self.assertFalse(first_bytes.endswith(b"\n"))
        self.assertNotIn("aggregate", first)
        for provider in ("builtin", "ast-grep"):
            with self.subTest(provider=provider):
                metrics = first["providers"][provider]
                self.assertEqual(metrics["true_positive"], 2)
                self.assertEqual(metrics["false_positive"], 0)
                self.assertEqual(metrics["false_negative"], 0)
                self.assertEqual(metrics["precision"], 1.0)
                self.assertEqual(metrics["recall"], 1.0)
                self.assertTrue(metrics["passed"])
        self.assertEqual(first["providers"]["builtin"]["unknown_frontier"], 2)
        self.assertEqual(first["providers"]["ast-grep"]["unknown_frontier"], 4)
        self.assertEqual(first["disagreement"], {"count": 0, "edges": [], "passed": True})
        self.assertEqual(first["performance"]["median_duration_ms"], 9500)
        self.assertEqual(first["performance"]["hard_duration_ms"], 10_000)
        self.assertEqual(first["compact_bytes"], len(first_bytes))
        self.assertLessEqual(len(first_bytes), 24_000)
        self.assertTrue(first["passed"])

    def test_provider_failure_and_captured_target_mutation_cannot_be_micro_averaged_away(self):
        scorer = self.require_scorer()
        expected = {
            ("fixture", "source.py", "target.py"): True,
            ("fixture", "source.py", "second.py"): False,
        }
        observations = (
            scorer.EngineObservation(
                "fixture",
                "builtin",
                (("source.py", "target.py"), ("source.py", "second.py")),
                0,
                10,
                "builtin-v1",
                None,
                scope_inventory_complete=True,
            ),
            scorer.EngineObservation(
                "fixture",
                "ast-grep",
                (("source.py", "second.py"), ("source.py", "mutated.py")),
                0,
                20,
                "ast-grep 0.45.0",
                "a" * 64,
                scope_inventory_complete=True,
            ),
        )

        report, _ = scorer.score_observations(
            expected,
            observations,
            {"builtin": set(), "ast-grep": set()},
        )

        self.assertTrue(report["providers"]["builtin"]["passed"])
        ast_grep = report["providers"]["ast-grep"]
        self.assertEqual(ast_grep["true_positive"], 1)
        self.assertEqual(ast_grep["false_positive"], 1)
        self.assertEqual(ast_grep["false_negative"], 1)
        self.assertEqual(ast_grep["precision"], 0.5)
        self.assertEqual(ast_grep["recall"], 0.5)
        self.assertFalse(ast_grep["passed"])
        self.assertEqual(report["disagreement"]["count"], 2)
        self.assertFalse(report["disagreement"]["passed"])
        self.assertFalse(report["passed"])

    def test_zero_disagreement_is_required_for_ast_grep_support_claim(self):
        scorer = self.require_scorer()
        expected = {("fixture", "source.py", f"target-{index}.py"): False for index in range(10)}
        all_predictions = tuple((key[1], key[2]) for key in sorted(expected))
        observations = (
            scorer.EngineObservation(
                "fixture",
                "builtin",
                all_predictions,
                0,
                10,
                "builtin-v1",
                None,
                scope_inventory_complete=True,
            ),
            scorer.EngineObservation(
                "fixture",
                "ast-grep",
                all_predictions[:-1],
                0,
                20,
                "ast-grep 0.45.0",
                "a" * 64,
                scope_inventory_complete=True,
            ),
        )

        report, _ = scorer.score_observations(
            expected,
            observations,
            {"builtin": set(), "ast-grep": set()},
        )

        ast_grep = report["providers"]["ast-grep"]
        self.assertEqual(ast_grep["precision"], 1.0)
        self.assertEqual(ast_grep["recall"], 0.9)
        self.assertTrue(ast_grep["gates"]["precision"])
        self.assertTrue(ast_grep["gates"]["recall"])
        self.assertFalse(ast_grep["gates"]["disagreement"])
        self.assertFalse(ast_grep["passed"])
        self.assertFalse(report["passed"])

    def test_literal_gate_function_rejects_every_boundary_violation(self):
        scorer = self.require_scorer()
        provider_cases = {
            "precision": (0.899999, 1.0, (), True, "precision"),
            "recall": (1.0, 0.799999, (), True, "recall"),
            "high-risk": (1.0, 1.0, ("fixture:a.py->b.py",), True, "high_risk"),
            "inventory": (1.0, 1.0, (), False, "scope_inventory"),
        }
        for name, (precision, recall, misses, inventory, failed_gate) in provider_cases.items():
            with self.subTest(name=name):
                gates = scorer.evaluate_provider_gates(precision, recall, misses, inventory)
                self.assertFalse(gates[failed_gate])
                self.assertFalse(gates["passed"])

        release_cases = {
            "provider": (False, 0, (1000,), 1000, "providers"),
            "disagreement": (True, 1, (1000,), 1000, "disagreement"),
            "median": (True, 0, (10_001,), 1000, "median_duration"),
            "hard": (True, 0, (0, 0, 30_001), 1000, "hard_duration"),
            "compact": (True, 0, (1000,), 24_001, "compact_bytes"),
        }
        for name, (
            providers,
            disagreement,
            durations,
            compact,
            failed_gate,
        ) in release_cases.items():
            with self.subTest(name=name):
                gates = scorer.evaluate_release_gates(providers, disagreement, durations, compact)
                self.assertFalse(gates[failed_gate])
                self.assertFalse(gates["passed"])

        provider_boundary = scorer.evaluate_provider_gates(0.9, 0.8, (), True)
        self.assertTrue(provider_boundary["passed"])
        boundary = scorer.evaluate_release_gates(True, 0, (0, 10_000, 30_000), 24_000)
        self.assertTrue(boundary["passed"])

    def test_observation_and_score_shapes_fail_closed(self):
        scorer = self.require_scorer()
        self.assertEqual(
            scorer._normalize_captured_module("typing as t", "python-import"),
            "typing",
        )
        with self.assertRaisesRegex(scorer.CorpusScoreError, "multi-module"):
            scorer._normalize_captured_module("os, sys", "python-import")
        with self.assertRaisesRegex(scorer.CorpusScoreError, "JavaScript"):
            scorer._normalize_captured_module("not-quoted", "javascript-from")
        with self.assertRaisesRegex(scorer.CorpusScoreError, "unknown"):
            scorer._normalize_captured_module("value", "unsupported")
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
        self.assertFalse(observation.scope_inventory_complete)
        expected = {("fixture", "a.py", "b.py"): False}
        with self.assertRaisesRegex(scorer.CorpusScoreError, "cover"):
            scorer.score_observations(
                expected,
                (observation,),
                {"builtin": set(), "ast-grep": set()},
            )
        incomplete = scorer.EngineObservation(
            "fixture",
            "ast-grep",
            (("a.py", "b.py"),),
            0,
            1,
            "ast-grep 0.45.0",
            "d" * 64,
            scope_inventory_complete=False,
        )
        complete = scorer.EngineObservation(*valid, scope_inventory_complete=True)
        report, _ = scorer.score_observations(
            expected,
            (complete, incomplete),
            {"builtin": set(), "ast-grep": set()},
        )
        self.assertFalse(report["providers"]["ast-grep"]["gates"]["scope_inventory"])

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
                    allow_local_repositories=True,
                )

    def test_expectation_loader_preserves_complete_source_labels_and_rejects_engine_generation(
        self,
    ):
        scorer = self.require_scorer()
        specifications = scorer.FETCHER.load_catalog(CATALOG_PATH)
        loaded = scorer.load_expectations(EXPECTED_PATH, specifications)

        self.assertEqual(len(loaded.corpora), 2)
        self.assertEqual(len(loaded.expected), 2)
        self.assertEqual(
            loaded.corpora[0].candidate_rule,
            scorer.FETCHER.CandidateRule("src/click", "*.py", False, 64),
        )
        self.assertEqual(
            loaded.disclosed_high_risk_misses,
            {"builtin": frozenset(), "ast-grep": frozenset()},
        )
        self.assertTrue(
            loaded.expected[
                (
                    "pallets-click",
                    "src/click/globals.py",
                    "src/click/core.py",
                )
            ]
        )
        self.assertEqual(
            loaded.labelled_modules[("pallets-click", "src/click/globals.py")],
            frozenset(
                {
                    ".core",
                    "__future__",
                    "threading",
                    "typing",
                }
            ),
        )

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "expected.json"
            payload = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
            payload["curation"]["engine_output_used"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(scorer.CorpusScoreError, "independently curated"):
                scorer.load_expectations(path, specifications)

            payload = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
            payload["corpora"][0]["sources"] = None
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(scorer.CorpusScoreError, "list fields"):
                scorer.load_expectations(path, specifications)

    def test_provider_projection_keeps_structural_pairs_and_counts_unknown_frontier(self):
        scorer = self.require_scorer()
        nodes = (
            SimpleNamespace(id="N1", location="source.py"),
            SimpleNamespace(id="N2", location="target.py"),
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
            ),
            frontier=(),
            budget_status="closed",
            source_digests={"source.py": "a" * 64, "target.py": "b" * 64},
            skipped={},
        )
        shadow_manifest = (("source.py", "a" * 64), ("target.py", "b" * 64))
        built_observation = scorer.project_builtin_result(
            "fixture",
            ("source.py",),
            builtin,
            123,
            shadow_manifest,
        )
        self.assertEqual(
            built_observation.predictions,
            (("source.py", "target.py"),),
        )
        self.assertEqual(built_observation.frontier_count, 0)
        self.assertTrue(built_observation.scope_inventory_complete)
        self.assertEqual(built_observation.scope_manifest, shadow_manifest)

        closure_mutations = {
            "budget": {"budget_status": "budget_exhausted"},
            "digest": {"source_digests": {"target.py": "b" * 64}},
            "skip": {"skipped": {"source.py": "oversized"}},
            "frontier": {"frontier": (SimpleNamespace(node="N1", reason="omitted"),)},
        }
        for name, mutation in closure_mutations.items():
            with self.subTest(closure=name):
                result = SimpleNamespace(**{**vars(builtin), **mutation})
                observation = scorer.project_builtin_result(
                    "fixture",
                    ("source.py",),
                    result,
                    123,
                    shadow_manifest,
                )
                self.assertEqual(observation.predictions, built_observation.predictions)
                self.assertFalse(observation.scope_inventory_complete)

        repository_files = frozenset(
            {"source.js", "target.js", "other.js", "pkg/core.py", "pkg/source.py"}
        )
        self.assertEqual(
            scorer.resolve_import_target(
                "source.js", "./target.js", "javascript", repository_files
            ),
            "target.js",
        )
        self.assertEqual(
            scorer.resolve_import_target("pkg/source.py", ".core", "python", repository_files),
            "pkg/core.py",
        )
        self.assertIsNone(
            scorer.resolve_import_target(
                "source.js", "external-package", "javascript", repository_files
            )
        )

    def test_real_engines_discover_scoped_imports_without_expected_targets(self):
        scorer = self.require_scorer()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source.js"
            original_source = (
                "import externalValue from 'external-package';\n"
                "import targetValue from './target.js';\n"
            )
            source.write_text(original_source, encoding="utf-8")
            (root / "target.js").write_text("export default 1;\n", encoding="utf-8")
            (root / "other.js").write_text("export default 2;\n", encoding="utf-8")
            scope = scorer.SourceScope(
                "source.js",
                "javascript",
                hashlib.sha256(original_source.encode()).hexdigest(),
                (
                    scorer.ImportLabel(
                        "./target.js",
                        "target.js",
                        True,
                        ("interfaces",),
                    ),
                ),
                ("external-package",),
            )
            candidate_rule = scorer.FETCHER.CandidateRule(".", "*.js", False, 16)
            corpus = scorer.CorpusCase(
                "fixture",
                "f" * 40,
                (scope,),
                candidate_rule,
            )

            excluded_case = scorer.CorpusCase(
                "fixture",
                "f" * 40,
                (scope,),
                candidate_rule,
            )
            with self.assertRaisesRegex(scorer.CorpusScoreError, "candidate rule excludes"):
                scorer.prepare_candidate_case(
                    excluded_case,
                    frozenset({"source.js", "other.js"}),
                )

            with self.assertRaisesRegex(scorer.CorpusScoreError, "ast-grep executable"):
                scorer.run_ast_grep(corpus, root, root / "missing-ast-grep")

            builtin = scorer.run_builtin(corpus, root)
            self.assertEqual(builtin.predictions, (("source.js", "target.js"),))
            self.assertTrue(builtin.scope_inventory_complete)
            self.assertEqual(
                dict(builtin.scope_manifest),
                {
                    "other.js": hashlib.sha256(b"export default 2;\n").hexdigest(),
                    "source.js": hashlib.sha256(original_source.encode()).hexdigest(),
                    "target.js": hashlib.sha256(b"export default 1;\n").hexdigest(),
                },
            )
            self.assertIsNone(builtin.detail)
            self.assertEqual(len(builtin.scope_manifest), 3)
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
            self.assertEqual(ast_grep.predictions, (("source.js", "target.js"),))
            self.assertEqual(
                ast_grep.discovered_modules,
                (("source.js", "./target.js"), ("source.js", "external-package")),
            )
            self.assertTrue(ast_grep.scope_inventory_complete)
            self.assertEqual(ast_grep.version, "ast-grep 0.45.0")
            self.assertRegex(ast_grep.executable_sha256, r"^[0-9a-f]{64}$")
            self.assertLessEqual(ast_grep.duration_ms, 30_000)

            decoy_source = original_source + "import otherValue from './other.js';\n"
            source.write_text(decoy_source, encoding="utf-8")
            decoy_scope = scorer.SourceScope(
                "source.js",
                "javascript",
                hashlib.sha256(decoy_source.encode()).hexdigest(),
                scope.internal_imports,
                (*scope.external_imports, "./other.js"),
            )
            decoy_builtin = scorer.run_builtin(
                scorer.CorpusCase(
                    "fixture",
                    "f" * 40,
                    (decoy_scope,),
                    candidate_rule,
                ),
                root,
            )
            self.assertEqual(
                decoy_builtin.predictions,
                (("source.js", "other.js"), ("source.js", "target.js")),
            )
            decoy_report, _ = scorer.score_observations(
                {("fixture", "source.js", "target.js"): True},
                (decoy_builtin, ast_grep),
                {"builtin": set(), "ast-grep": set()},
            )
            self.assertEqual(decoy_report["providers"]["builtin"]["false_positive"], 1)
            self.assertEqual(decoy_report["providers"]["builtin"]["precision"], 0.5)
            self.assertFalse(decoy_report["providers"]["builtin"]["passed"])
            self.assertFalse(decoy_report["passed"])
            source.write_text(original_source, encoding="utf-8")

            package = root / "pkg"
            package.mkdir()
            python_source_text = "from __future__ import annotations\nfrom .target import Target\n"
            (package / "source.py").write_text(python_source_text, encoding="utf-8")
            (package / "target.py").write_text("class Target:\n    pass\n", encoding="utf-8")
            python_scope = scorer.SourceScope(
                "pkg/source.py",
                "python",
                hashlib.sha256(python_source_text.encode()).hexdigest(),
                (
                    scorer.ImportLabel(
                        ".target",
                        "pkg/target.py",
                        False,
                        ("functionality",),
                    ),
                ),
                ("__future__",),
            )
            python_observation = scorer.run_ast_grep(
                scorer.CorpusCase(
                    "python-fixture",
                    "e" * 40,
                    (python_scope,),
                    scorer.FETCHER.CandidateRule("pkg", "*.py", False, 16),
                ),
                root,
                executable,
            )
            self.assertEqual(
                python_observation.discovered_modules,
                (("pkg/source.py", ".target"), ("pkg/source.py", "__future__")),
            )
            self.assertTrue(python_observation.scope_inventory_complete)

            external_dropped = original_source.replace(
                "import externalValue from 'external-package';\n", ""
            )
            source.write_text(external_dropped, encoding="utf-8")
            dropped_scope = scorer.SourceScope(
                "source.js",
                "javascript",
                hashlib.sha256(external_dropped.encode()).hexdigest(),
                scope.internal_imports,
                scope.external_imports,
            )
            dropped_observation = scorer.run_ast_grep(
                scorer.CorpusCase(
                    "fixture",
                    "f" * 40,
                    (dropped_scope,),
                    candidate_rule,
                ),
                root,
                executable,
            )
            self.assertEqual(
                dropped_observation.predictions,
                (("source.js", "target.js"),),
            )
            self.assertFalse(dropped_observation.scope_inventory_complete)

            mutated_source = original_source.replace("./target.js", "./other.js")
            source.write_text(mutated_source, encoding="utf-8")
            mutated_scope = scorer.SourceScope(
                "source.js",
                "javascript",
                hashlib.sha256(mutated_source.encode()).hexdigest(),
                scope.internal_imports,
                scope.external_imports,
            )
            mutated_ast_grep = scorer.run_ast_grep(
                scorer.CorpusCase(
                    "fixture",
                    "f" * 40,
                    (mutated_scope,),
                    candidate_rule,
                ),
                root,
                executable,
            )
            self.assertEqual(
                mutated_ast_grep.predictions,
                (("source.js", "other.js"),),
            )
            report, _ = scorer.score_observations(
                {("fixture", "source.js", "target.js"): True},
                (builtin, mutated_ast_grep),
                {"builtin": set(), "ast-grep": set()},
            )
            self.assertEqual(report["providers"]["ast-grep"]["false_positive"], 1)
            self.assertEqual(report["providers"]["ast-grep"]["false_negative"], 1)
            self.assertFalse(report["passed"])

    def make_local_expectations(self, root: Path, commit: str) -> Path:
        source_sha256 = hashlib.sha256(
            b"from target import public_symbol\n\nvalue = public_symbol()\n"
        ).hexdigest()
        payload = {
            "schema_version": 2,
            "curation": {
                "method": "manual-pinned-source-review",
                "engine_output_used": False,
                "scope_policy": "Every internal import from the listed fixture source is labelled.",
                "reviewed_commits": [commit],
                "reviewed_license_sha256": [hashlib.sha256(b"fixture license\n").hexdigest()],
            },
            "gates": {
                "minimum_precision": 0.9,
                "minimum_recall": 0.8,
                "maximum_median_seconds": 10,
                "maximum_hard_seconds": 30,
                "maximum_compact_bytes": 24_000,
                "allow_undisclosed_high_risk_miss": False,
                "require_zero_provider_disagreement": True,
            },
            "corpora": [
                {
                    "id": "fixture",
                    "commit": commit,
                    "sources": [
                        {
                            "path": "module.py",
                            "language": "python",
                            "sha256": source_sha256,
                            "internal_imports": [
                                {
                                    "module": "target",
                                    "target": "target.py",
                                    "high_risk": True,
                                    "risk_domains": ["interfaces"],
                                }
                            ],
                            "external_imports": [],
                        }
                    ],
                    "disclosed_high_risk_misses": {"builtin": [], "ast-grep": []},
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
                allow_local_repositories=True,
            )
            expected_path = self.make_local_expectations(root, commit)

            def builtin(case, _checkout):
                return scorer.EngineObservation(
                    case.id,
                    "builtin",
                    (("module.py", "target.py"),),
                    0,
                    100,
                    "builtin-v1",
                    None,
                    scope_inventory_complete=True,
                )

            def ast_grep(case, _checkout, _executable):
                return scorer.EngineObservation(
                    case.id,
                    "ast-grep",
                    (("module.py", "target.py"),),
                    1,
                    200,
                    "ast-grep 0.45.0",
                    "c" * 64,
                    scope_inventory_complete=True,
                )

            report, report_bytes = scorer.run_evaluation(
                catalog_path,
                expected_path,
                destination,
                Path("/unused/fake-ast-grep"),
                repository_root=ROOT,
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
            self.assertEqual(report["providers"]["ast-grep"]["unknown_frontier"], 1)
            self.assertEqual(len(report_bytes), report["compact_bytes"])
            self.assertEqual(report["disagreement"]["count"], 0)

            payload = json.loads(expected_path.read_text(encoding="utf-8"))
            payload["corpora"][0]["sources"][0]["sha256"] = "0" * 64
            expected_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(scorer.CorpusScoreError, "source digest"):
                scorer.run_evaluation(
                    catalog_path,
                    expected_path,
                    destination,
                    Path("/unused/fake-ast-grep"),
                    repository_root=ROOT,
                    allow_local_repositories=True,
                    builtin_runner=builtin,
                    ast_grep_runner=ast_grep,
                )


if __name__ == "__main__":
    unittest.main()
