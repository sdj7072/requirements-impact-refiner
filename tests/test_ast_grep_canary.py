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
        for flag in ("--rewrite=x", "--update-all", "-U", "--interactive", "-i"):
            with self.subTest(flag=flag):
                with self.assertRaisesRegex(RUNNER.CanaryError, "read-only"):
                    RUNNER.validate_read_only_command(("ast-grep", "scan", flag, "."))

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
