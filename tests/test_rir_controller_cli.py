import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "rir-controller.py"
FIXTURES = ROOT / "tests" / "fixtures"


class RirControllerCliTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        temporary_root = Path(self.temporary.name)
        self.root = temporary_root / "repo"
        self.root.mkdir()
        input_root = temporary_root / "inputs"
        input_root.mkdir()
        self.write_graph_config(False)
        self.begin_path = input_root / "begin.json"
        self.analysis_path = input_root / "analysis.json"
        self.seeds_path = input_root / "seeds.json"
        self.scan_path = input_root / "scan.json"
        self.previous_path = input_root / "previous.json"
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
            json.dumps({"seeds": [{"term": "profile.displayName", "location": "api/profile.py"}]}),
            encoding="utf-8",
        )
        self.scan_path.write_text(
            json.dumps(
                {
                    "change_request": "Rename profile.displayName",
                    "evidence": [],
                    "presentation": "balanced",
                }
            ),
            encoding="utf-8",
        )
        self.previous_path.write_text(
            json.dumps(
                {
                    "request": "Let workspace members edit every project.",
                    "repository_evidence": ["authorizeProjectEdit permits owner and admin"],
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
                    "delivery": "compact",
                    "impact_graph": {
                        "enabled": enabled,
                        "max_seconds": 30,
                        "target_seconds": 10,
                        "providers": ["builtin"],
                        "install_policy": "never",
                        "deep": False,
                    },
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
        return self.run_cli("begin", "--repo-root", self.root, "--input", self.begin_path, *extra)

    def previous(self, *extra):
        return self.run_cli(
            "previous", "--repo-root", self.root, "--input", self.previous_path, *extra
        )

    def test_begin_emits_structured_draft_metadata(self):
        result = self.begin()

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertRegex(payload["draft_id"], r"^[0-9a-f]{32}$")
        self.assertEqual(payload["report_id"], "RPT-001")
        self.assertEqual(payload["revision"], 1)
        self.assertEqual(payload["delivery"], "compact")

    def test_previous_cli_returns_renderer_neutral_canonical_json(self):
        begin = json.loads(self.begin().stdout)
        finalized = self.run_cli(
            "finalize",
            "--repo-root",
            self.root,
            "--draft-id",
            begin["draft_id"],
            "--input",
            self.analysis_path,
        )
        self.assertEqual(finalized.returncode, 0, finalized.stderr)

        result = self.previous()

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "stale")
        self.assertEqual(
            set(payload),
            {
                "status",
                "report_id",
                "revision",
                "markdown_sha256",
                "created_at",
                "baseline_commit",
                "changed_paths",
                "changed_count",
                "requirement_sha256",
                "source_inventory_sha256",
                "display_text",
                "reason",
                "elapsed_ms",
                "candidates",
                "performance_metrics",
            },
        )
        self.assertIsNone(payload["performance_metrics"]["actual_input_tokens"])
        self.assertEqual(
            payload["performance_metrics"]["previous_lookup"]["elapsed_ms"],
            payload["elapsed_ms"],
        )
        self.assertTrue(payload["display_text"].startswith("## Previous Impact Report\n"))
        self.assertIn("# Requirements Impact Report\n", payload["display_text"])
        self.assertFalse(any(line.startswith("|") for line in payload["display_text"].splitlines()))
        self.assertEqual(
            result.stdout,
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        )

    def test_previous_cli_none_and_malformed_inputs_disclose_no_body(self):
        none = self.previous()
        self.assertEqual(none.returncode, 0, none.stderr)
        payload = json.loads(none.stdout)
        self.assertEqual(payload["status"], "none")
        for field in (
            "report_id",
            "revision",
            "markdown_sha256",
            "created_at",
            "baseline_commit",
            "source_inventory_sha256",
            "display_text",
        ):
            self.assertIsNone(payload[field], field)
        self.assertEqual(payload["changed_paths"], [])
        self.assertIsNone(payload["changed_count"])
        self.assertEqual(payload["candidates"], [])

        for value, expected in (
            ({"request": "x", "repository_evidence": [], "surprise": True}, "unknown"),
            ({"request": "x"}, "missing"),
            ({"request": "x", "repository_evidence": {}}, "array"),
        ):
            with self.subTest(value=value):
                self.previous_path.write_text(json.dumps(value), encoding="utf-8")
                invalid = self.previous()
                self.assertEqual(invalid.returncode, 1)
                self.assertEqual(invalid.stdout, "")
                self.assertIn(expected, invalid.stderr)
                self.assertNotIn("Traceback", invalid.stderr)

    def test_previous_cli_keeps_wide_lookup_and_accepts_report_id_input_or_flag(self):
        wide = {
            "request": "x" * 5000,
            "repository_evidence": ["e" * 5000],
            "report_id": "RPT-002",
        }
        self.previous_path.write_text(json.dumps(wide), encoding="utf-8")

        from_input = self.previous()
        self.assertEqual(from_input.returncode, 0, from_input.stderr)
        self.assertEqual(json.loads(from_input.stdout)["status"], "none")

        wide.pop("report_id")
        self.previous_path.write_text(json.dumps(wide), encoding="utf-8")
        from_flag = self.previous("--report-id", "RPT-002")
        self.assertEqual(from_flag.returncode, 0, from_flag.stderr)
        self.assertEqual(json.loads(from_flag.stdout)["status"], "none")

    def test_scan_text_json_and_begin_promotion(self):
        self.enable_graph_sources()
        text_result = self.run_cli("scan", "--repo-root", self.root, "--input", self.scan_path)
        self.assertEqual(text_result.returncode, 0, text_result.stderr)
        self.assertIn("## Fast impact scan", text_result.stdout)

        json_result = self.run_cli(
            "scan",
            "--repo-root",
            self.root,
            "--input",
            self.scan_path,
            "--json",
        )
        payload = json.loads(json_result.stdout)
        self.assertRegex(payload["scan_id"], r"^[0-9a-f]{32}$")
        self.assertTrue(payload["display_text"].startswith("## Fast impact scan"))
        self.assertIn("Coverage:", payload["display_text"])
        self.assertEqual(payload["cache_status"], "hit")

        self.begin_path.write_text(
            json.dumps(
                {
                    "request": "Rename profile.displayName",
                    "repository_evidence": [],
                    "adapter": "generic",
                }
            ),
            encoding="utf-8",
        )

        begin_value = json.loads(self.begin("--scan-id", payload["scan_id"]).stdout)
        self.assertEqual(begin_value["scan_id"], payload["scan_id"])
        self.assertEqual(begin_value["graph_receipt_id"], payload["receipt_id"])

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
            "finalize",
            "--repo-root",
            self.root,
            "--draft-id",
            begin["draft_id"],
            "--input",
            self.analysis_path,
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
            "finalize",
            "--repo-root",
            self.root,
            "--draft-id",
            begin["draft_id"],
            "--input",
            self.analysis_path,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("# Requirements Impact Report\n"))

    def test_io_and_invocation_errors_return_two(self):
        missing = self.run_cli(
            "begin", "--repo-root", self.root, "--input", self.root / "missing.json"
        )
        malformed = self.root / "malformed.json"
        malformed.write_bytes(b"\xff")
        bad = self.run_cli("begin", "--repo-root", self.root, "--input", malformed)

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
                "receipt_id",
                "receipt_path",
                "receipt_sha256",
                "compact_graph",
                "budget_status",
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
            "trace",
            "--repo-root",
            self.root,
            "--draft-id",
            begin["draft_id"],
            "--input",
            self.seeds_path,
        )
        missing = self.run_cli(
            "trace",
            "--repo-root",
            self.root,
            "--draft-id",
            begin["draft_id"],
            "--input",
            self.root / "missing-seeds.json",
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
        self.seeds_path.write_text("[" * 1500 + "0" + "]" * 1500, encoding="utf-8")
        deep = self.run_cli(
            "trace",
            "--repo-root",
            self.root,
            "--draft-id",
            begin["draft_id"],
            "--input",
            self.seeds_path,
        )
        self.seeds_path.write_bytes(b"{" + b" " * (256 * 1024))
        oversized = self.run_cli(
            "trace",
            "--repo-root",
            self.root,
            "--draft-id",
            begin["draft_id"],
            "--input",
            self.seeds_path,
        )

        self.assertEqual(deep.returncode, 2)
        self.assertEqual(oversized.returncode, 1)
        self.assertEqual(deep.stdout, "")
        self.assertEqual(oversized.stdout, "")
        self.assertNotIn("Traceback", deep.stderr + oversized.stderr)

    @unittest.skipIf(fcntl is None, "requires POSIX flock")
    @unittest.skipIf(
        os.environ.get("RIR_COVERAGE_RUN") == "1",
        "timing contract runs uninstrumented in the CI test matrix",
    )
    def test_trace_held_lock_returns_bounded_validation_error(self):
        self.enable_graph_sources()
        config_path = self.root / ".requirements-impact-refiner.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["impact_graph"]["max_seconds"] = 1
        config["impact_graph"]["target_seconds"] = 1
        config_path.write_text(json.dumps(config), encoding="utf-8")
        begin = json.loads(self.begin().stdout)
        report_dir = self.root / ".requirements-impact-refiner/reports" / begin["report_id"]
        report_dir.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(report_dir / ".controller.lock", os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)

        def release():
            time.sleep(1.25)
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

        releaser = threading.Thread(target=release)
        releaser.start()
        started = time.monotonic()
        result = self.run_cli(
            "trace",
            "--repo-root",
            self.root,
            "--draft-id",
            begin["draft_id"],
            "--input",
            self.seeds_path,
        )
        elapsed = time.monotonic() - started
        releaser.join(timeout=2)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("deadline exhausted waiting for controller lock", result.stderr)
        self.assertLess(elapsed, 1.5)


if __name__ == "__main__":
    unittest.main()
