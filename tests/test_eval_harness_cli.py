import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evals.harness.catalog import load_all
from evals.harness.evidence import build_manifest, record_run, verify_manifest
from evals.harness.models import ClientProbe, CommandResult, RunResult, RunStatus
from evals.harness.run import build_parser, build_schedule, create_adapter, run_batch, run_probe
from tests.test_report_lineage import next_report, report_with_state


_USE_REQUEST_RETRY = object()


class FakeAdapter:
    """Records safe synthetic evidence without invoking an installed client."""

    def __init__(
        self,
        statuses=(),
        record_evidence=True,
        client="codex",
        version="fake 1.0",
        plugin_version="0.3.0",
        enabled_plugins=("requirements-impact-refiner", "superpowers"),
        result_metadata=(),
        available=True,
        reason=None,
        raw_final_output=None,
        raw_previous_bytes=None,
        retry_of_override=_USE_REQUEST_RETRY,
    ):
        self.statuses = list(statuses)
        self.requests = []
        self.record_evidence = record_evidence
        self.probe_calls = 0
        self.client = client
        self.version = version
        self.plugin_version = plugin_version
        self.enabled_plugins = enabled_plugins
        self.result_metadata = result_metadata
        self.available = available
        self.reason = reason
        self.raw_final_output = raw_final_output
        self.raw_previous_bytes = raw_previous_bytes
        self.retry_of_override = retry_of_override
        self.probe_results = (
            CommandResult(("fake", "--version"), 0, "fake 1.0", "", 0.0, False),
        )

    def prepare(self):
        return ClientProbe(
            client=self.client,
            available=self.available,
            version=self.version,
            authenticated=None,
            plugin_version=self.plugin_version,
            enabled_plugins=self.enabled_plugins,
            capabilities=("fake",),
            reason=self.reason,
        )

    def probe(self):
        self.probe_calls += 1
        return self.prepare()

    def execute(self, request):
        self.requests.append(request)
        status = self.statuses.pop(0) if self.statuses else RunStatus.PASS
        final_output = "synthetic final output"
        retry_of = (
            request.retry_of
            if self.retry_of_override is _USE_REQUEST_RETRY
            else self.retry_of_override
        )
        if self.record_evidence:
            raw_final = (
                final_output
                if self.raw_final_output is None
                else self.raw_final_output
            )
            artifacts = {
                "adapter.txt": "synthetic evidence",
                "metadata.json": json.dumps(
                    {
                        "attempt": request.attempt,
                        "client": request.client,
                        "retry_of": retry_of,
                    },
                    sort_keys=True,
                ),
                ("second.final.txt" if request.case.kind == "lineage" else "first.final.txt"): raw_final,
            }
            if request.case.kind == "lineage":
                artifacts["first.final.txt"] = (
                    b"synthetic predecessor"
                    if self.raw_previous_bytes is None
                    else self.raw_previous_bytes
                )
            record_run(
                request.output_root,
                request.client,
                request.case.id,
                request.repetition,
                artifacts,
                request.output_root.parent / "quarantine",
                attempt=request.attempt,
            )
        return RunResult(
            case_id=request.case.id,
            repetition=request.repetition,
            client=request.client,
            status=status,
            reason="synthetic infrastructure issue" if status is RunStatus.INFRA_ERROR else None,
            final_output=final_output,
            session_id="123e4567-e89b-12d3-a456-426614174000" if len(request.case.turns) > 1 else None,
            attempt=request.attempt,
            retry_of=retry_of,
            metadata=self.result_metadata,
        )


class LineageEvidenceAdapter(FakeAdapter):
    """Produces distinct valid lineage bytes for every case/repetition attempt."""

    def __init__(self, retry_lineage_case=None):
        super().__init__()
        self.retry_lineage_case = retry_lineage_case
        self.retried = False

    def execute(self, request):
        if (
            request.case.id == self.retry_lineage_case
            and request.attempt == 1
            and not self.retried
        ):
            self.retried = True
            self.statuses.insert(0, RunStatus.INFRA_ERROR)
            return super().execute(request)
        if request.case.kind != "lineage":
            return super().execute(request)

        self.requests.append(request)
        transition = {
            "LINEAGE-stable-blocked": ("blocked", "blocked", "unchanged"),
            "LINEAGE-reopened": ("resolved", "refining", "reopened"),
            "LINEAGE-no-false-resolution": ("refining", "refining", "unchanged"),
        }[request.case.id]
        previous_state, current_state, delta = transition
        previous = report_with_state(previous_state) + ("\n" * request.repetition)
        current = next_report(
            previous,
            report_with_state(current_state, delta),
        )
        record_run(
            request.output_root,
            request.client,
            request.case.id,
            request.repetition,
            {
                "metadata.json": json.dumps(
                    {
                        "attempt": request.attempt,
                        "client": request.client,
                        "retry_of": request.retry_of,
                    },
                    sort_keys=True,
                ),
                "first.final.txt": previous.encode("utf-8"),
                "second.final.txt": current.encode("utf-8"),
            },
            request.output_root.parent / "quarantine",
            attempt=request.attempt,
        )
        return RunResult(
            case_id=request.case.id,
            repetition=request.repetition,
            client=request.client,
            status=RunStatus.PASS,
            reason=None,
            final_output=current,
            session_id="123e4567-e89b-12d3-a456-426614174000",
            attempt=request.attempt,
            retry_of=request.retry_of,
            metadata=self.result_metadata,
        )


class EvalHarnessCliTest(unittest.TestCase):
    def test_omitted_model_is_none(self):
        """Defaulting a model would silently alter the installed composition."""
        args = build_parser().parse_args(
            ["--client", "codex", "--suite", "smoke", "--output", "out"]
        )

        self.assertIsNone(args.model)
        self.assertIsNone(args.reasoning)

    def test_expected_plugin_version_defaults_to_the_sealed_v030_contract(self):
        """Changing the default would prevent replaying the sealed 0.3.0 composition."""
        args = build_parser().parse_args(
            ["--client", "codex", "--suite", "smoke", "--output", "out"]
        )

        self.assertEqual(args.expected_plugin_version, "0.3.0")

    def test_codex_adapter_receives_the_explicit_expected_plugin_version(self):
        """Dropping the requested version at the CLI boundary would probe the wrong release."""
        args = build_parser().parse_args(
            [
                "--client", "codex", "--probe-only", "--output", "out",
                "--expected-plugin-version", "0.3.1",
            ]
        )

        with patch("evals.harness.run.CodexAdapter") as adapter_class:
            create_adapter(args)

        adapter_class.assert_called_once_with(
            timeout_seconds=300.0, expected_plugin_version="0.3.1"
        )

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

    def test_unavailable_prepare_stops_a_batch_before_creating_case_evidence(self):
        """Executing after a rejected composition would make mismatched runs appear selectable."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )
            adapter = FakeAdapter(available=False, reason="expected 0.3.1; observed 0.3.0")

            exit_code = run_batch(args, adapter)

            self.assertEqual(exit_code, 1)
            self.assertEqual(adapter.requests, [])
            self.assertFalse((output / "controller.json").exists())
            self.assertFalse((output / "raw" / "codex" / "POS-authorization").exists())

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

    def test_attempt_one_with_retry_lineage_is_rejected_before_finalization(self):
        """An initial attempt cannot claim lineage to a foreign or prior run."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )

            exit_code = run_batch(
                args,
                FakeAdapter(retry_of_override="foreign-case/99"),
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse((output / "controller.json").exists())
            self.assertFalse((output / "report.md").exists())
            self.assertFalse((output / "manifest.sha256").exists())

    def test_noncanonical_raw_retry_metadata_is_rejected_before_finalization(self):
        """Raw retry metadata cannot inherit validity from a canonical controller result."""
        class MetadataRetryAdapter(FakeAdapter):
            def execute(self, request):
                result = super().execute(request)
                attempt_path = (
                    request.output_root
                    / request.client
                    / request.case.id
                    / ("%02d" % request.repetition)
                )
                (attempt_path / "metadata.json").write_text(
                    json.dumps(
                        {
                            "attempt": request.attempt,
                            "client": request.client,
                            "retry_of": "foreign-case/99",
                        },
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
                return result

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )

            exit_code = run_batch(args, MetadataRetryAdapter())

            self.assertEqual(exit_code, 1)
            self.assertFalse((output / "controller.json").exists())
            self.assertFalse((output / "report.md").exists())
            self.assertFalse((output / "manifest.sha256").exists())

    def test_retry_rejects_noncanonical_attempt_one_raw_metadata(self):
        """Selecting attempt 2 must not hide malformed metadata in its attempt-1 backing."""
        class FirstAttemptMetadataAdapter(FakeAdapter):
            def execute(self, request):
                result = super().execute(request)
                if request.attempt == 1 and request.case.id == "POS-authorization":
                    attempt_path = (
                        request.output_root
                        / request.client
                        / request.case.id
                        / ("%02d" % request.repetition)
                    )
                    (attempt_path / "metadata.json").write_text(
                        json.dumps(
                            {
                                "attempt": 1,
                                "client": request.client,
                                "retry_of": "foreign-case/99",
                            },
                            sort_keys=True,
                        ),
                        encoding="utf-8",
                    )
                return result

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )

            exit_code = run_batch(
                args,
                FirstAttemptMetadataAdapter([RunStatus.INFRA_ERROR]),
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse((output / "controller.json").exists())
            self.assertFalse((output / "report.md").exists())
            self.assertFalse((output / "manifest.sha256").exists())

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

    def test_selected_raw_final_must_equal_the_controller_final_output(self):
        """A controller string detached from sealed final bytes cannot be scored."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )

            exit_code = run_batch(
                args, FakeAdapter(raw_final_output="different sealed bytes")
            )

        self.assertEqual(exit_code, 1)
        self.assertFalse((output / "controller.json").exists())
        self.assertFalse((output / "report.md").exists())
        self.assertFalse((output / "manifest.sha256").exists())

    def test_lineage_non_utf8_predecessor_invalidates_scoring_evidence(self):
        """Replacement decoding would sever the SHA from the exact predecessor bytes."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )

            exit_code = run_batch(
                args, FakeAdapter(raw_previous_bytes=b"\xff")
            )

        self.assertEqual(exit_code, 1)
        self.assertFalse((output / "controller.json").exists())
        self.assertFalse((output / "report.md").exists())
        self.assertFalse((output / "manifest.sha256").exists())

    def test_selected_final_symlink_invalidates_scoring_evidence(self):
        """Following a selected-output symlink could score bytes outside the attempt."""
        class SymlinkAdapter(FakeAdapter):
            def execute(self, request):
                result = super().execute(request)
                attempt_path = (
                    request.output_root
                    / request.client
                    / request.case.id
                    / ("%02d" % request.repetition)
                )
                if request.attempt != 1:
                    attempt_path = attempt_path / ("attempt-%02d" % request.attempt)
                selected = attempt_path / (
                    "second.final.txt" if request.case.kind == "lineage" else "first.final.txt"
                )
                target = attempt_path / "symlink-target.txt"
                target.write_text(result.final_output or "", encoding="utf-8")
                selected.unlink()
                selected.symlink_to(target.name)
                return result

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )

            exit_code = run_batch(args, SymlinkAdapter())

        self.assertEqual(exit_code, 1)
        self.assertFalse((output / "controller.json").exists())
        self.assertFalse((output / "report.md").exists())
        self.assertFalse((output / "manifest.sha256").exists())

    def test_raw_mutation_after_scoring_cannot_receive_a_successful_final_seal(self):
        """A manifest must not bless bytes different from those mechanically scored."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )
            mutated = False

            def mutate_before_manifest(root):
                nonlocal mutated
                if not mutated:
                    mutated = True
                    target = (
                        output / "raw" / "codex" / "POS-authorization" / "01"
                        / "first.final.txt"
                    )
                    target.write_text("changed after scoring", encoding="utf-8")
                return build_manifest(root)

            with patch(
                "evals.harness.run.build_manifest",
                side_effect=mutate_before_manifest,
            ):
                exit_code = run_batch(args, FakeAdapter())

            manifest_path = output / "manifest.sha256"
            manifest_valid = (
                manifest_path.is_file()
                and not verify_manifest(
                    output, manifest_path.read_text(encoding="utf-8")
                )
            )

        self.assertTrue(mutated)
        self.assertEqual(exit_code, 1)
        self.assertFalse(manifest_valid)

    def test_lineage_scoring_uses_selected_retry_attempt_directory(self):
        """A retry must bind both lineage turns to attempt-02, never the failed base attempt."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )

            exit_code = run_batch(
                args,
                LineageEvidenceAdapter(retry_lineage_case="LINEAGE-stable-blocked"),
            )
            ledger = json.loads((output / "controller.json").read_text(encoding="utf-8"))

        selected = next(
            row for row in ledger["runs"]
            if row["case_id"] == "LINEAGE-stable-blocked"
        )
        score = next(
            row for row in ledger["mechanical_scores"]
            if row["case_id"] == "LINEAGE-stable-blocked"
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(selected["selected_attempt"], 2)
        self.assertTrue(score["passed"], score["findings"])

    def test_smoke_to_full_lineage_scoring_isolated_by_repetition(self):
        """Every expanded repetition must use its own first-turn predecessor bytes."""
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

            self.assertEqual(run_batch(smoke, LineageEvidenceAdapter()), 0)
            self.assertEqual(run_batch(full, LineageEvidenceAdapter()), 0)
            ledger = json.loads((output / "controller.json").read_text(encoding="utf-8"))

        lineage = [
            row for row in ledger["mechanical_scores"]
            if row["case_id"].startswith("LINEAGE-")
        ]
        self.assertEqual(len(lineage), 15)
        self.assertTrue(all(row["passed"] for row in lineage), lineage)

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

            self.assertTrue((output / "raw" / "codex" / "probe-01" / "metadata.json").is_file())
            self.assertTrue((output / "probes.json").is_file())
            self.assertFalse((output / "controller.json").exists())
            self.assertEqual(verify_manifest(output, manifest), [])

    def test_probes_coexist_before_a_batch_without_claiming_batch_metadata(self):
        """Letting a probe own controller.json prevents later batch evidence from sealing."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            codex_probe = build_parser().parse_args(
                ["--client", "codex", "--probe-only", "--output", str(output)]
            )
            claude_probe = build_parser().parse_args(
                ["--client", "claude", "--probe-only", "--output", str(output)]
            )
            smoke = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )
            first = FakeAdapter(client="codex")
            second = FakeAdapter(client="claude")
            third = FakeAdapter(client="codex")
            batch = FakeAdapter(client="codex")

            self.assertEqual(run_probe(codex_probe, first), 0)
            self.assertEqual(run_probe(claude_probe, second), 0)
            self.assertEqual(run_probe(codex_probe, third), 0)
            self.assertEqual(run_batch(smoke, batch), 0)
            probes = json.loads((output / "probes.json").read_text(encoding="utf-8"))

            self.assertEqual(len(probes["probes"]), 3)
            self.assertTrue((output / "raw" / "codex" / "probe-01").is_dir())
            self.assertTrue((output / "raw" / "claude" / "probe-01").is_dir())
            self.assertTrue((output / "raw" / "codex" / "probe-02").is_dir())
            self.assertEqual(len(batch.requests), 6)

    def test_full_expansion_requires_the_exact_observed_probe_environment(self):
        """A caller label cannot prove that version or plugin inventory stayed the same."""
        mutations = {
            "client version": {"version": "fake 2.0"},
            "plugin version": {"plugin_version": "0.4.0"},
            "enabled plugin": {
                "enabled_plugins": (
                    "requirements-impact-refiner", "superpowers", "extra-plugin",
                )
            },
        }
        for name, changed in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
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
                self.assertEqual(run_batch(smoke, FakeAdapter()), 0)
                changed_adapter = FakeAdapter(**changed)

                self.assertEqual(run_batch(full, changed_adapter), 1)
                self.assertEqual(changed_adapter.requests, [])

    def test_reported_composition_comes_from_the_observed_probe_inventory(self):
        """An adapter label can omit enabled plugins and must not define report provenance."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )
            adapter = FakeAdapter(
                version="fake 9.0",
                enabled_plugins=("superpowers", "requirements-impact-refiner", "extra"),
                result_metadata=(("environment", "adapter supplied label"),),
            )

            self.assertEqual(run_batch(args, adapter), 0)
            report = (output / "report.md").read_text(encoding="utf-8")

        self.assertIn(
            "- enabled composition: codex fake 9.0 plugins=extra,requirements-impact-refiner,superpowers",
            report,
        )

    def test_missing_manifest_blocks_probe_after_a_completed_batch(self):
        """Resealing raw batch evidence after manifest loss would hide its unsealed interval."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            smoke = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )
            probe = build_parser().parse_args(
                ["--client", "codex", "--probe-only", "--output", str(output)]
            )
            self.assertEqual(run_batch(smoke, FakeAdapter()), 0)
            (output / "manifest.sha256").unlink()
            adapter = FakeAdapter()

            self.assertEqual(run_probe(probe, adapter), 1)

            self.assertEqual(adapter.probe_calls, 0)
            self.assertFalse((output / "manifest.sha256").exists())

    def test_missing_manifest_blocks_batch_after_a_probe(self):
        """A batch must not silently bless prior unsealed probe evidence."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            probe = build_parser().parse_args(
                ["--client", "codex", "--probe-only", "--output", str(output)]
            )
            smoke = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )
            self.assertEqual(run_probe(probe, FakeAdapter()), 0)
            (output / "manifest.sha256").unlink()
            adapter = FakeAdapter()

            self.assertEqual(run_batch(smoke, adapter), 1)

            self.assertEqual(adapter.requests, [])
            self.assertFalse((output / "manifest.sha256").exists())

    def test_probe_publication_error_returns_one_without_resealing_raw_probe(self):
        """A probe ledger write failure must leave raw evidence unsealed rather than report success."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--probe-only", "--output", str(output)]
            )

            with patch("evals.harness.run._write_derived", side_effect=OSError("disk full")):
                exit_code = run_probe(args, FakeAdapter())

            self.assertEqual(exit_code, 1)
            self.assertTrue((output / "raw" / "codex" / "probe-01").is_dir())
            self.assertFalse((output / "manifest.sha256").exists())

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
