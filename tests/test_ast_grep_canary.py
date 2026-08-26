from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "run-ast-grep-canary.py"


def load_runner():
    specification = importlib.util.spec_from_file_location("ast_grep_canary_runner", RUNNER_PATH)
    if specification is None or specification.loader is None:
        raise RuntimeError("cannot load canary runner")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


RUNNER = load_runner()


class AstGrepCanaryTests(unittest.TestCase):
    def run_canary(self, *arguments):
        return subprocess.run(
            [sys.executable, str(RUNNER_PATH), *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_canary_requires_exact_version_and_json_stream(self):
        result = subprocess.run(
            [sys.executable, "scripts/run-ast-grep-canary.py", "--print-command"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(
            result.stdout.strip(),
            "ast-grep scan --json=stream --config "
            "evals/ast-grep-canary/sgconfig.yml evals/ast-grep-canary/fixture",
        )

    def test_read_only_command_rejects_every_mutating_mode(self):
        invalid = (
            ("scan", "--rewrite", "changed"),
            ("scan", "--rewrite=changed"),
            ("scan", "--update"),
            ("scan", "--update-all"),
            ("scan", "--interactive"),
            ("scan", "--interactive=true"),
            ("scan", "-r", "changed"),
            ("scan", "-rreplacement"),
            ("scan", "-r=value"),
            ("scan", "-U"),
            ("scan", "-i"),
            ("scan", "-Ui"),
            ("scan", "-iU"),
            ("scan", "-vUi"),
            ("scan", "--", "--update-all"),
            ("scan", "--json=stream", "unexpected"),
        )
        for command in invalid:
            with self.subTest(command=command):
                with self.assertRaisesRegex(RUNNER.CanaryError, "read-only"):
                    RUNNER.validate_read_only_command(command)

    def test_read_only_command_accepts_only_exact_canary_shapes(self):
        valid = (
            ("--version",),
            RUNNER.CANARY_COMMAND,
            RUNNER.CANARY_COMMAND[1:],
            (
                "--json=stream",
                "--lang",
                "python",
                "--pattern",
                "ProfileService",
                "imports.py",
            ),
        )
        for command in valid:
            with self.subTest(command=command):
                self.assertEqual(RUNNER.validate_read_only_command(command), tuple(command))

    def test_jsonl_parser_rejects_malformed_oversized_and_deep_rows(self):
        payloads = {
            "malformed": "{not-json}\n",
            "oversized": json.dumps({"text": "x" * RUNNER.MAX_JSONL_LINE_BYTES}) + "\n",
            "deep": "[" * (RUNNER.MAX_JSON_DEPTH + 1)
            + "0"
            + "]" * (RUNNER.MAX_JSON_DEPTH + 1)
            + "\n",
        }
        for name, payload in payloads.items():
            with self.subTest(name=name):
                with self.assertRaises(RUNNER.CanaryError):
                    RUNNER.parse_jsonl(payload)

    def test_scan_projection_rejects_schema_drift_and_traversal(self):
        malformed = {
            "text": "ProfileService",
            "file": "../outside.py",
            "range": {},
        }
        with self.assertRaises(RUNNER.CanaryError):
            RUNNER.project_scan_matches((malformed,), ROOT)

    def test_source_reader_is_descriptor_anchored_and_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "nested/source.py"
            source.parent.mkdir()
            source.write_bytes(b"value = 1\n")
            self.assertEqual(RUNNER._source_bytes(root, "nested/source.py"), b"value = 1\n")

            hard_link = root / "nested/hard-link.py"
            os.link(source, hard_link)
            with self.assertRaisesRegex(RUNNER.CanaryError, "source"):
                RUNNER._source_bytes(root, "nested/source.py")

    def test_source_reader_rejects_symlink_parent_and_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            outside = Path(temporary) / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "source.py").write_text("outside\n", encoding="utf-8")
            (root / "linked-parent").symlink_to(outside, target_is_directory=True)
            (root / "linked-file.py").symlink_to(outside / "source.py")
            for relative in ("linked-parent/source.py", "linked-file.py"):
                with self.subTest(relative=relative):
                    with self.assertRaisesRegex(RUNNER.CanaryError, "source"):
                        RUNNER._source_bytes(root, relative)

    def test_source_reader_rejects_path_replacement_and_symlink_swap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.py"
            replacement = root / "replacement.py"
            source.write_text("original\n", encoding="utf-8")
            replacement.write_text("replacement\n", encoding="utf-8")

            def replace_path():
                os.replace(replacement, source)

            with self.assertRaisesRegex(RUNNER.CanaryError, "changed"):
                RUNNER._source_bytes(root, "source.py", before_read=replace_path)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.py"
            original = root / "original.py"
            outside = root / "outside.py"
            source.write_text("original\n", encoding="utf-8")
            outside.write_text("outside\n", encoding="utf-8")

            def swap_to_symlink():
                source.rename(original)
                source.symlink_to(outside)

            with self.assertRaisesRegex(RUNNER.CanaryError, "changed"):
                RUNNER._source_bytes(root, "source.py", before_read=swap_to_symlink)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "nested"
            original = root / "original-parent"
            outside = root / "outside"
            parent.mkdir()
            outside.mkdir()
            (parent / "source.py").write_text("original\n", encoding="utf-8")
            (outside / "source.py").write_text("outside\n", encoding="utf-8")

            def swap_parent_to_symlink():
                parent.rename(original)
                parent.symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(RUNNER.CanaryError, "parent changed"):
                RUNNER._source_bytes(
                    root,
                    "nested/source.py",
                    before_read=swap_parent_to_symlink,
                )

    def test_source_reader_rejects_mode_change_during_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.py"
            source.write_text("original\n", encoding="utf-8")

            with self.assertRaisesRegex(RUNNER.CanaryError, "changed"):
                RUNNER._source_bytes(
                    root,
                    "source.py",
                    before_read=lambda: source.chmod(0o600),
                )

    def test_source_reader_normalizes_read_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.py"
            source.write_text("value = 1\n", encoding="utf-8")

            def fail_read(_descriptor, _maximum):
                raise OSError("platform-specific read failure")

            with self.assertRaisesRegex(RUNNER.CanaryError, "cannot be read safely") as raised:
                RUNNER._source_bytes(root, "source.py", read_chunk=fail_read)
            self.assertNotIn("platform-specific", str(raised.exception))

    def test_bounded_process_rejects_oversized_provider_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "fake-ast-grep"
            executable.write_text(
                f"#!{sys.executable}\n"
                "import sys\n"
                f"sys.stdout.write('x' * {RUNNER.MAX_STDOUT_BYTES + 1})\n",
                encoding="utf-8",
            )
            os.chmod(executable, 0o755)
            with self.assertRaisesRegex(RUNNER.CanaryError, "stdout"):
                RUNNER.run_bounded(executable, ("--version",), ROOT)

    def make_git_repository(self, directory):
        root = Path(directory)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        tracked = root / "tracked.txt"
        tracked.write_text("original\n", encoding="utf-8")
        pointers = (
            root / ".requirements-impact-refiner/cache/graph/v1/current",
            root / ".requirements-impact-refiner/reports/RPT-001/current.json",
        )
        for pointer in pointers:
            pointer.parent.mkdir(parents=True, exist_ok=True)
            pointer.write_text("baseline\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        for pointer in pointers:
            pointer.write_text("pre-existing dirt\n", encoding="utf-8")
        return root, tracked, pointers

    def test_working_state_guard_detects_fake_provider_mutations_anywhere(self):
        def changed(root, tracked):
            tracked.write_text("provider changed tracked state\n", encoding="utf-8")

        def deleted(_root, tracked):
            tracked.unlink()

        def renamed(root, tracked):
            tracked.rename(root / "provider-renamed.txt")

        def untracked(root, _tracked):
            (root / "unrelated-provider-output.txt").write_text(
                "provider output\n", encoding="utf-8"
            )

        for name, fake_provider in (
            ("changed", changed),
            ("deleted", deleted),
            ("renamed", renamed),
            ("untracked", untracked),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root, tracked, _ = self.make_git_repository(temporary)
                with self.assertRaisesRegex(RUNNER.CanaryError, "working state"):
                    RUNNER.guard_working_state(
                        root,
                        lambda provider=fake_provider, repo=root, path=tracked: provider(
                            repo, path
                        ),
                    )

    def test_working_state_guard_preserves_existing_dirty_pointers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, _, pointers = self.make_git_repository(temporary)
            before = RUNNER.capture_working_state(root)
            result = RUNNER.guard_working_state(root, lambda: "unchanged")
            self.assertEqual(result, "unchanged")
            self.assertEqual(RUNNER.capture_working_state(root), before)
            self.assertTrue(all(path.read_text() == "pre-existing dirt\n" for path in pointers))

    def test_working_state_guard_detects_changes_to_existing_dirty_and_untracked_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, _, pointers = self.make_git_repository(temporary)
            with self.assertRaisesRegex(RUNNER.CanaryError, "working state"):
                RUNNER.guard_working_state(
                    root,
                    lambda: pointers[0].write_text("provider changed existing dirt\n"),
                )

        with tempfile.TemporaryDirectory() as temporary:
            root, _, _ = self.make_git_repository(temporary)
            untracked = root / "already-untracked.txt"
            untracked.write_text("before\n", encoding="utf-8")
            with self.assertRaisesRegex(RUNNER.CanaryError, "working state"):
                RUNNER.guard_working_state(
                    root,
                    lambda: untracked.write_text("after\n", encoding="utf-8"),
                )

    def test_working_state_contract_excludes_gitignored_paths_precisely(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, _, _ = self.make_git_repository(temporary)
            ignore = root / ".gitignore"
            ignore.write_text("provider-ignored-output\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", ".gitignore"], check=True)
            before = RUNNER.capture_working_state(root)

            result = RUNNER.guard_working_state(
                root,
                lambda: (root / "provider-ignored-output").write_text(
                    "ignored by the stated contract\n", encoding="utf-8"
                ),
            )

            self.assertIsInstance(result, int)
            self.assertEqual(RUNNER.capture_working_state(root), before)

    def test_working_state_snapshot_is_exact_bounded_porcelain_and_fails_closed(self):
        self.assertEqual(
            RUNNER.GIT_STATUS_COMMAND,
            ("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(RUNNER.CanaryError, "working state"):
                RUNNER.capture_working_state(root)

    def test_working_state_process_rejects_oversized_and_timed_out_snapshots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "fake-git"
            executable.write_text(
                f"#!{sys.executable}\n"
                "import sys\n"
                "import time\n"
                "if sys.argv[1] == 'oversized':\n"
                "    sys.stdout.write('x' * 33)\n"
                "else:\n"
                "    time.sleep(1)\n",
                encoding="utf-8",
            )
            os.chmod(executable, 0o755)
            with self.assertRaisesRegex(RUNNER.CanaryError, "output bounds"):
                RUNNER._bounded_capture(
                    (str(executable), "oversized"),
                    root,
                    stdout_limit=32,
                    stderr_limit=32,
                    timeout=1,
                )
            with self.assertRaisesRegex(RUNNER.CanaryError, "timed out"):
                RUNNER._bounded_capture(
                    (str(executable), "sleep"),
                    root,
                    stdout_limit=32,
                    stderr_limit=32,
                    timeout=0.05,
                )

    def test_cli_rejects_mutating_flags_and_missing_provider_cleanly(self):
        mutation = self.run_canary("--rewrite=changed")
        self.assertEqual(mutation.returncode, 2)
        self.assertIn("read-only", mutation.stderr)

        missing = self.run_canary("--ast-grep", str(ROOT / "missing-ast-grep"))
        self.assertEqual(missing.returncode, 2)
        self.assertIn("not found", missing.stderr)

    def test_cli_rejects_any_version_other_than_exact_0450(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "ast-grep"
            executable.write_text(
                f"#!{sys.executable}\n"
                "import sys\n"
                "if sys.argv[1:] == ['--version']:\n"
                "    print('ast-grep 0.45.1')\n",
                encoding="utf-8",
            )
            os.chmod(executable, 0o755)
            result = self.run_canary("--ast-grep", str(executable))
        self.assertEqual(result.returncode, 2)
        self.assertIn("ast-grep 0.45.0 is required", result.stderr)

    def test_real_pinned_provider_matches_literal_canary_and_adapter_receipt(self):
        configured = os.environ.get("AST_GREP_CANARY_BIN")
        executable = Path(configured) if configured else ROOT / ".quality-venv/bin/ast-grep"
        if not executable.is_file():
            discovered = shutil.which("ast-grep")
            if discovered is None:
                self.skipTest("ast-grep 0.45.0 is not installed")
            executable = Path(discovered)
        version = subprocess.run(
            [str(executable), "--version"], text=True, capture_output=True, check=False
        )
        if version.stdout.strip() != "ast-grep 0.45.0":
            self.skipTest("exact ast-grep 0.45.0 is not installed")

        summary = RUNNER.run_canary(executable)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["version"], "ast-grep 0.45.0")
        self.assertEqual(summary["matches"], 1)
        self.assertEqual(summary["adapter"], {"edges": 2, "nodes": 3, "receipts": 1})
        self.assertRegex(summary["executable_sha256"], r"^[0-9a-f]{64}$")

    def test_quality_venv_python_discovers_sibling_provider(self):
        python = ROOT / ".quality-venv/bin/python"
        provider = ROOT / ".quality-venv/bin/ast-grep"
        if not python.is_file() or not provider.is_file():
            self.skipTest("repository quality environment is not installed")
        result = subprocess.run(
            [str(python), str(RUNNER_PATH)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
