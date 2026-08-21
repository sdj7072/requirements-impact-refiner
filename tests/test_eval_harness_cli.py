import json
import tempfile
import unittest
from pathlib import Path

from evals.harness.catalog import load_all
from evals.harness.evidence import record_run, verify_manifest
from evals.harness.models import ClientProbe, CommandResult, RunResult, RunStatus
from evals.harness.run import build_parser, build_schedule, run_batch, run_probe


class FakeAdapter:
    """Records safe synthetic evidence without invoking an installed client."""

    def __init__(self, statuses=(), record_evidence=True):
        self.statuses = list(statuses)
        self.requests = []
        self.record_evidence = record_evidence
        self.probe_results = (
            CommandResult(("fake", "--version"), 0, "fake 1.0", "", 0.0, False),
        )

    def prepare(self):
        return ClientProbe(
            client="codex",
            available=True,
            version="fake 1.0",
            authenticated=None,
            plugin_version="0.3.0",
            enabled_plugins=("requirements-impact-refiner", "superpowers"),
            capabilities=("fake",),
        )

    def probe(self):
        return self.prepare()

    def execute(self, request):
        self.requests.append(request)
        if self.record_evidence:
            record_run(
                request.output_root,
                request.client,
                request.case.id,
                request.repetition,
                {"adapter.txt": "synthetic evidence"},
                request.output_root.parent / "quarantine",
                attempt=request.attempt,
            )
        status = self.statuses.pop(0) if self.statuses else RunStatus.PASS
        return RunResult(
            case_id=request.case.id,
            repetition=request.repetition,
            client=request.client,
            status=status,
            reason="synthetic infrastructure issue" if status is RunStatus.INFRA_ERROR else None,
            final_output="synthetic final output",
            session_id="123e4567-e89b-12d3-a456-426614174000" if len(request.case.turns) > 1 else None,
            attempt=request.attempt,
            retry_of=request.retry_of,
        )


class EvalHarnessCliTest(unittest.TestCase):
    def test_omitted_model_is_none(self):
        """Defaulting a model would silently alter the installed composition."""
        args = build_parser().parse_args(
            ["--client", "codex", "--suite", "smoke", "--output", "out"]
        )

        self.assertIsNone(args.model)
        self.assertIsNone(args.reasoning)

    def test_probe_only_allows_omitting_suite_but_batches_do_not(self):
        """Making suite optional for a behavior batch would make its coverage ambiguous."""
        probe = build_parser().parse_args(
            ["--client", "codex", "--probe-only", "--output", "out"]
        )

        self.assertIsNone(probe.suite)
        with self.assertRaises(SystemExit) as error:
            build_parser().parse_args(["--client", "codex", "--output", "out"])
        self.assertEqual(error.exception.code, 2)

    def test_schedule_sizes(self):
        """Dropping canonical cases or repetitions would under-sample the suite."""
        self.assertEqual(len(build_schedule(load_all(), "smoke", 1)), 6)
        self.assertEqual(len(build_schedule(load_all(), "installed-superpowers", 5)), 85)

    def test_schedule_keeps_each_case_canonical_before_its_repetitions(self):
        """Interleaving case order would make same-case retries and comparisons unstable."""
        scheduled = build_schedule(load_all(), "smoke", 2)

        self.assertEqual(
            [(slot.case.id, slot.repetition) for slot in scheduled[:4]],
            [
                ("POS-authorization", 1),
                ("POS-authorization", 2),
                ("NEG-debugging", 1),
                ("NEG-debugging", 2),
            ],
        )

    def test_claude_rejects_behavioral_model_options(self):
        """Accepting model options for Claude would blur its structural-only boundary."""
        with self.assertRaises(SystemExit) as error:
            build_parser().parse_args(
                [
                    "--client", "claude", "--suite", "smoke", "--model", "opus",
                    "--output", "out",
                ]
            )

        self.assertEqual(error.exception.code, 2)

    def test_infrastructure_error_has_a_single_append_only_retry(self):
        """Reusing the completed run ID would overwrite evidence from the failed attempt."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )
            adapter = FakeAdapter([RunStatus.INFRA_ERROR])

            exit_code = run_batch(args, adapter)
            ledger = json.loads((output / "controller.json").read_text(encoding="utf-8"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(adapter.requests), 7)
            self.assertEqual(adapter.requests[0].repetition, 1)
            self.assertEqual(adapter.requests[1].repetition, 1)
            self.assertEqual(adapter.requests[1].attempt, 2)
            self.assertEqual(adapter.requests[1].retry_of, "POS-authorization/01")
            self.assertEqual(len(ledger["attempts"]), 7)
            self.assertEqual(ledger["attempts"][0]["attempt"], 1)
            self.assertEqual(ledger["attempts"][1]["attempt"], 2)
            self.assertEqual(ledger["attempts"][1]["retry_of"], "POS-authorization/01")
            manifest = (output / "manifest.sha256").read_text(encoding="utf-8")
            self.assertEqual(verify_manifest(output, manifest), [])

    def test_non_infrastructure_outcomes_are_not_retried(self):
        """Retrying a scored outcome would bias the batch toward a later answer."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )
            adapter = FakeAdapter([RunStatus.PASS, RunStatus.PARTIAL, RunStatus.FAIL])

            exit_code = run_batch(args, adapter)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(adapter.requests), 6)

    def test_existing_completed_run_is_a_noop_without_overwriting_raw_evidence(self):
        """Re-executing a sealed final would overwrite its immutable evidence directory."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )
            first = FakeAdapter()
            second = FakeAdapter()

            self.assertEqual(run_batch(args, first), 0)
            self.assertEqual(run_batch(args, second), 0)

        self.assertEqual(second.requests, [])

    def test_batch_records_mechanical_scores_and_an_unverified_report(self):
        """Omitting score rows would leave completed evidence without an auditable assessment."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )

            self.assertEqual(run_batch(args, FakeAdapter()), 0)
            ledger = json.loads((output / "controller.json").read_text(encoding="utf-8"))
            report = (output / "report.md").read_text(encoding="utf-8")

        self.assertEqual(len(ledger["mechanical_scores"]), 6)
        self.assertIn("- status: not verified", report)

    def test_smoke_batch_expands_to_the_missing_full_matrix_slots(self):
        """Treating smoke finals as foreign would rerun six sealed final keys."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            smoke = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )
            full = build_parser().parse_args(
                [
                    "--client", "codex", "--suite", "installed-superpowers",
                    "--repetitions", "5", "--output", str(output),
                ]
            )
            smoke_adapter = FakeAdapter()
            full_adapter = FakeAdapter()

            self.assertEqual(run_batch(smoke, smoke_adapter), 0)
            self.assertEqual(run_batch(full, full_adapter), 0)
            ledger = json.loads((output / "controller.json").read_text(encoding="utf-8"))

        self.assertEqual(len(smoke_adapter.requests), 6)
        self.assertEqual(len(full_adapter.requests), 79)
        self.assertEqual(
            {(row["case_id"], row["repetition"]) for row in ledger["runs"]},
            {(slot.case.id, slot.repetition) for slot in build_schedule(load_all(), "installed-superpowers", 5)},
        )

    def test_full_expansion_rejects_an_incompatible_existing_batch(self):
        """Combining different model provenance would make one matrix untraceable."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            smoke = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--model", "one", "--output", str(output)]
            )
            incompatible = build_parser().parse_args(
                [
                    "--client", "codex", "--suite", "installed-superpowers",
                    "--repetitions", "5", "--model", "two", "--output", str(output),
                ]
            )
            self.assertEqual(run_batch(smoke, FakeAdapter()), 0)
            adapter = FakeAdapter()

            self.assertEqual(run_batch(incompatible, adapter), 1)

        self.assertEqual(adapter.requests, [])

    def test_batch_uses_raw_evidence_layout(self):
        """Writing adapter evidence beside summaries would mingle raw and derived artifacts."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )

            self.assertEqual(run_batch(args, FakeAdapter()), 0)

            self.assertTrue((output / "raw" / "codex" / "POS-authorization" / "01").is_dir())

    def test_probe_only_persists_raw_probe_evidence_and_manifest(self):
        """Printing a probe alone leaves no reproducible structural evidence."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--probe-only", "--output", str(output)]
            )

            self.assertEqual(run_probe(args, FakeAdapter()), 0)
            manifest = (output / "manifest.sha256").read_text(encoding="utf-8")

            self.assertTrue((output / "raw" / "codex" / "probe" / "01" / "metadata.json").is_file())
            self.assertTrue((output / "controller.json").is_file())
            self.assertEqual(verify_manifest(output, manifest), [])

    def test_missing_safe_evidence_makes_the_batch_invalid(self):
        """A result without a recorded artifact cannot support an exit-zero batch."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )

            self.assertEqual(run_batch(args, FakeAdapter(record_evidence=False)), 1)

    def test_invalid_evidence_status_never_gets_a_completed_exit_code(self):
        """A sealed artifact with an invalid-evidence result remains a controller failure."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )

            self.assertEqual(run_batch(args, FakeAdapter([RunStatus.INVALID_EVIDENCE])), 1)


if __name__ == "__main__":
    unittest.main()
