import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "requirements-impact-refiner" / "scripts" / "rir-controller.py"
FIXTURES = ROOT / "tests" / "fixtures"


class RirControllerCliTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.write_graph_config(False)
        self.begin_path = self.root / "begin.json"
        self.analysis_path = self.root / "analysis.json"
        self.seeds_path = self.root / "seeds.json"
        self.begin_path.write_text(
            json.dumps(
                {
                    "request": "Let workspace members edit every project.",
                    "repository_evidence": ["authorizeProjectEdit permits owner and admin"],
                    "adapter": "generic",
                }
            ),
            encoding="utf-8",
        )
        self.analysis_path.write_bytes(
            (FIXTURES / "controller-analysis-pre-decision.json").read_bytes()
        )
        self.seeds_path.write_text(
            json.dumps(
                {
                    "seeds": [
                        {"term": "profile.displayName", "location": "api/profile.py"}
                    ]
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def write_graph_config(self, enabled):
        (self.root / ".requirements-impact-refiner.json").write_text(
            json.dumps(
                {
                    "impact_graph": {
                        "enabled": enabled,
                        "max_seconds": 30,
                        "target_seconds": 10,
                        "providers": ["builtin"],
                        "install_policy": "never",
                        "deep": False,
                    }
                }
            ),
            encoding="utf-8",
        )

    def enable_graph_sources(self):
        self.write_graph_config(True)
        (self.root / "api").mkdir(exist_ok=True)
        (self.root / "desktop").mkdir(exist_ok=True)
        (self.root / "api/profile.py").write_text(
            'FIELD = "profile.displayName"\n', encoding="utf-8"
        )
        (self.root / "desktop/profile_cache.ts").write_text(
            'const key = "profile.displayName";\n', encoding="utf-8"
        )

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(CLI), *map(str, arguments)],
            text=True,
            capture_output=True,
            check=False,
        )

    def begin(self, *extra):
        return self.run_cli(
            "begin", "--repo-root", self.root, "--input", self.begin_path, *extra
        )

    def test_begin_emits_structured_draft_metadata(self):
        result = self.begin()

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertRegex(payload["draft_id"], r"^[0-9a-f]{32}$")
        self.assertEqual(payload["report_id"], "RPT-001")
        self.assertEqual(payload["revision"], 1)
        self.assertEqual(payload["delivery"], "compact")

    def test_finalize_stdout_is_renderer_output_only(self):
        begin = json.loads(self.begin().stdout)

        result = self.run_cli(
            "finalize",
            "--repo-root",
            self.root,
            "--draft-id",
            begin["draft_id"],
            "--input",
            self.analysis_path,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("## Change Impact Summary\n"))
        self.assertIn("`IMP-001`", result.stdout)
        self.assertIn("**Decision needed:**", result.stdout)
        self.assertNotIn('"status": "published"', result.stdout)

    def test_invalid_finalize_has_no_display_stdout(self):
        begin = json.loads(self.begin().stdout)
        invalid = json.loads(self.analysis_path.read_text(encoding="utf-8"))
        invalid["impacts"][0]["id"] = "IMP-999"
        self.analysis_path.write_text(json.dumps(invalid), encoding="utf-8")

        result = self.run_cli(
            "finalize", "--repo-root", self.root, "--draft-id", begin["draft_id"],
            "--input", self.analysis_path,
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("unknown impact key id", result.stderr)

    def test_full_delivery_returns_canonical_markdown(self):
        begin_payload = json.loads(self.begin_path.read_text(encoding="utf-8"))
        begin_payload["delivery_override"] = "full"
        self.begin_path.write_text(json.dumps(begin_payload), encoding="utf-8")
        begin = json.loads(self.begin().stdout)

        result = self.run_cli(
            "finalize", "--repo-root", self.root, "--draft-id", begin["draft_id"],
            "--input", self.analysis_path,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("# Requirements Impact Report\n"))

    def test_io_and_invocation_errors_return_two(self):
        missing = self.run_cli(
            "begin", "--repo-root", self.root, "--input", self.root / "missing.json"
        )
        malformed = self.root / "malformed.json"
        malformed.write_bytes(b"\xff")
        bad = self.run_cli(
            "begin", "--repo-root", self.root, "--input", malformed
        )

        self.assertEqual(missing.returncode, 2)
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(missing.stdout, "")
        self.assertEqual(bad.stdout, "")

    def test_begin_rejects_wrong_evidence_type_before_tuple_conversion(self):
        payload = json.loads(self.begin_path.read_text(encoding="utf-8"))
        payload["repository_evidence"] = {"bad": "shape"}
        self.begin_path.write_text(json.dumps(payload), encoding="utf-8")

        result = self.begin()

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("repository_evidence", result.stderr)

    def test_input_size_is_rejected_before_unbounded_json_parse(self):
        self.begin_path.write_bytes(b"{" + b" " * (256 * 1024))

        result = self.begin()

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("256 KiB", result.stderr)

    def test_deep_json_returns_bounded_error_without_traceback(self):
        self.begin_path.write_text("[" * 1500 + "0" + "]" * 1500, encoding="utf-8")

        result = self.begin()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("cannot read input", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_trace_uses_controller_and_prints_canonical_compact_metadata(self):
        self.enable_graph_sources()
        begin = json.loads(self.begin().stdout)

        traced = self.run_cli(
            "trace",
            "--repo-root",
            self.root,
            "--draft-id",
            begin["draft_id"],
            "--input",
            self.seeds_path,
        )

        self.assertEqual(traced.returncode, 0, traced.stderr)
        payload = json.loads(traced.stdout)
        self.assertEqual(
            set(payload),
            {
                "receipt_id", "receipt_path", "receipt_sha256",
                "compact_graph", "budget_status",
            },
        )
        self.assertRegex(payload["receipt_id"], r"^[0-9a-f]{32}$")
        self.assertRegex(payload["receipt_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(payload["compact_graph"]["paths"])
        analysis = json.loads(self.analysis_path.read_text(encoding="utf-8"))
        analysis["impacts"][0]["graph_path_keys"] = [
            row["key"] for row in payload["compact_graph"]["paths"]
        ]
        analysis["impacts"][0]["evidence_level"] = "unknown"
        self.analysis_path.write_text(json.dumps(analysis), encoding="utf-8")

        finalized = self.run_cli(
            "finalize",
            "--repo-root",
            self.root,
            "--draft-id",
            begin["draft_id"],
            "--graph-receipt-id",
            payload["receipt_id"],
            "--input",
            self.analysis_path,
        )

        self.assertEqual(finalized.returncode, 0, finalized.stderr)
        self.assertTrue(finalized.stdout.startswith("## Change Impact Summary\n"))

    def test_trace_validation_and_io_failures_preserve_cli_exit_contracts(self):
        self.enable_graph_sources()
        begin = json.loads(self.begin().stdout)
        invalid = {"seeds": [{"term": "displayName", "location": "../outside.py"}]}
        self.seeds_path.write_text(json.dumps(invalid), encoding="utf-8")

        validation = self.run_cli(
            "trace", "--repo-root", self.root, "--draft-id", begin["draft_id"],
            "--input", self.seeds_path,
        )
        missing = self.run_cli(
            "trace", "--repo-root", self.root, "--draft-id", begin["draft_id"],
            "--input", self.root / "missing-seeds.json",
        )
        invocation = self.run_cli("trace", "--repo-root", self.root)

        self.assertEqual(validation.returncode, 1)
        self.assertIn("safe repository-relative path", validation.stderr)
        self.assertEqual(missing.returncode, 2)
        self.assertEqual(invocation.returncode, 2)
        self.assertEqual(validation.stdout, "")
        self.assertEqual(missing.stdout, "")
        self.assertEqual(invocation.stdout, "")

    def test_trace_rejects_deep_and_oversized_json_without_traceback(self):
        self.enable_graph_sources()
        begin = json.loads(self.begin().stdout)
        self.seeds_path.write_text(
            "[" * 1500 + "0" + "]" * 1500, encoding="utf-8"
        )
        deep = self.run_cli(
            "trace", "--repo-root", self.root, "--draft-id", begin["draft_id"],
            "--input", self.seeds_path,
        )
        self.seeds_path.write_bytes(b"{" + b" " * (256 * 1024))
        oversized = self.run_cli(
            "trace", "--repo-root", self.root, "--draft-id", begin["draft_id"],
            "--input", self.seeds_path,
        )

        self.assertEqual(deep.returncode, 2)
        self.assertEqual(oversized.returncode, 1)
        self.assertEqual(deep.stdout, "")
        self.assertEqual(oversized.stdout, "")
        self.assertNotIn("Traceback", deep.stderr + oversized.stderr)


if __name__ == "__main__":
    unittest.main()
