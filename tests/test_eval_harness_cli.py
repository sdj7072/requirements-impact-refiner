import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evals.harness.catalog import load_all
from evals.harness.controller_evidence import analyze_controller_trace
from evals.harness.evidence import build_manifest, record_run, verify_manifest
from evals.harness.graph_scoring import (
    GraphScore,
    canonical_receipt_bytes,
    compact_graph,
    load_graph_cases,
)
from evals.harness.models import (
    ClientProbe,
    CommandResult,
    MechanicalScore,
    RunResult,
    RunStatus,
)
from evals.harness.performance import (
    GraphPerformanceObservation,
    GraphSmokeGateResult,
    PerformanceObservation,
    SmokeGateResult,
)
from evals.harness.run import (
    ScheduledRun,
    _graph_observation,
    _graph_state_parity,
    _score_selected_attempt,
    _smoke_observation,
    build_parser,
    build_schedule,
    create_adapter,
    run_batch,
    run_probe,
)
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
        enabled_plugins=(
            "requirements-impact-refiner@requirements-impact-refiner",
            "superpowers@openai-curated",
        ),
        result_metadata=None,
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
        self.probe_results = (CommandResult(("fake", "--version"), 0, "fake 1.0", "", 0.0, False),)

    def run_metadata(self, request):
        if self.result_metadata is not None:
            return self.result_metadata
        plugins = tuple(sorted(self.enabled_plugins))
        composition = "{} {} plugins={}".format(
            self.client,
            self.version,
            ",".join(plugins),
        )
        return (
            ("environment", "Codex with Superpowers"),
            ("client_version", self.version),
            ("plugin_version", self.plugin_version),
            ("enabled_composition", composition),
            ("enabled_plugins", ",".join(plugins)),
            ("model", request.model or "omitted"),
            ("reasoning", request.reasoning or "omitted"),
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
            raw_final = final_output if self.raw_final_output is None else self.raw_final_output
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
                (
                    "second.final.txt" if request.case.kind == "lineage" else "first.final.txt"
                ): raw_final,
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
            session_id="123e4567-e89b-12d3-a456-426614174000"
            if len(request.case.turns) > 1
            else None,
            attempt=request.attempt,
            retry_of=retry_of,
            metadata=self.run_metadata(request),
        )


def controller_observation(raw_root, client, slot, result, score):
    expected = 0 if slot.case.kind == "negative" else len(slot.case.turns)
    return PerformanceObservation(
        case_id=slot.case.id,
        repetition=slot.repetition,
        status=result.status,
        attempt=result.attempt,
        retry_of=result.retry_of,
        prompt_bytes=10,
        routed_resource_bytes=10,
        routed_resource_words=10,
        output_bytes=10,
        output_words=10,
        duration_ms=1,
        input_tokens=None,
        output_tokens=None,
        impact_ids=() if slot.case.kind == "negative" else ("IMP-001",),
        state_markdown_match=True,
        workflow_boundary_passed=True,
        controller_begin_calls=expected,
        controller_finalize_calls=expected,
        controller_draft_ids_match=True,
        controller_finalize_succeeded=True,
        controller_display_text_exact_match=True,
        controller_display_text_presentation_equivalent=True,
        controller_display_comparison="codex-markdown-v1",
    )


def graph_observation(raw_root, client, slot, result, score):
    negative = slot.case.id == "GRAPH-negative-no-change"
    observation = GraphPerformanceObservation(
        case_id=slot.case.id,
        repetition=slot.repetition,
        status=result.status,
        mechanical_passed=True,
        graph_passed=True,
        attempt=result.attempt,
        retry_of=result.retry_of,
        graph_duration_ms=None if negative else 8,
        output_words=10,
        routed_resource_words=10,
        receipt_state_provider_parity=True,
        uncovered_high_risk_nodes=(),
        controller_begin_calls=0 if negative else 1,
        controller_trace_calls=0 if negative else 1,
        controller_finalize_calls=0 if negative else 1,
        controller_evidence_valid=True,
        duplicate_or_error_calls=False,
        input_tokens=None,
        output_tokens=None,
    )
    graph_score = GraphScore(
        case_id=slot.case.id,
        passed=True,
        findings=(),
        maximum_required_distance=0 if negative else 3,
        receipt_id=None if negative else "a" * 32,
        receipt_sha256=None if negative else "b" * 64,
        providers=() if negative else ("builtin",),
        uncovered_high_risk_nodes=(),
        matched_path_ids=() if negative else ("PATH-001",),
    )
    return observation, graph_score, ()


class LineageEvidenceAdapter(FakeAdapter):
    """Produces distinct valid lineage bytes for every case/repetition attempt."""

    def __init__(self, retry_lineage_case=None):
        super().__init__()
        self.retry_lineage_case = retry_lineage_case
        self.retried = False

    def execute(self, request):
        if request.case.id == self.retry_lineage_case and request.attempt == 1 and not self.retried:
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
            metadata=self.run_metadata(request),
        )


class EvalHarnessCliTest(unittest.TestCase):
    def test_real_smoke_observation_returns_complete_negative_row(self):
        case = next(case for case in load_all() if case.id == "NEG-debugging")
        slot = ScheduledRun(case, 1)
        controller = analyze_controller_trace(
            ('{"type":"item.completed","item":{"type":"agent_message","text":"debug"}}',),
            "debug response",
            expected_turns=0,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "raw"
            record_run(
                raw,
                "codex",
                case.id,
                1,
                {
                    "metadata.json": json.dumps(
                        {
                            "attempt": 1,
                            "client": "codex",
                            "retry_of": None,
                            "execution_commands": [{"elapsed_seconds": 0.125}],
                        }
                    ),
                    "first.prompt.txt": "debug prompt",
                    "first.jsonl": '{"type":"item.completed","item":{"type":"agent_message"}}\n',
                    "first.final.txt": "debug response",
                    "controller-evidence.json": controller.to_json(),
                },
                root / "quarantine",
            )
            result = RunResult(
                case.id,
                1,
                "codex",
                RunStatus.PASS,
                None,
                final_output="debug response",
            )
            score = MechanicalScore(case.id, 1, True, ())

            observation = _smoke_observation(raw, "codex", slot, result, score)

        self.assertIsInstance(observation, PerformanceObservation)
        self.assertEqual(observation.duration_ms, 125)
        self.assertEqual(observation.controller_begin_calls, 0)
        self.assertTrue(observation.state_markdown_match)

    def test_smoke_observation_rejects_malformed_compact_state_impacts(self):
        case = next(case for case in load_all() if case.id == "POS-authorization")
        slot = ScheduledRun(case, 1)
        result = RunResult(case.id, 1, "codex", RunStatus.PASS, None, final_output="IMP-001")
        score = MechanicalScore(case.id, 1, True, ())
        pointer = json.dumps({"state": "revision-0001.json"}).encode("utf-8")
        common_payloads = {
            "smoke prompt": b"prompt",
            "smoke JSONL": b'{"type":"agent_message"}\n',
            "smoke final output": b"IMP-001",
            "smoke controller evidence": b"{}",
            "smoke metadata": b'{"execution_commands":[]}',
            "smoke current pointer": pointer,
        }

        for state in (None, {"impacts": "IMP-001"}, {"impacts": [{"id": 1}]}):
            with self.subTest(state=state):
                state_payload = json.dumps(state).encode("utf-8")

                def selected_file(raw_root, path, label, state_payload=state_payload):
                    payload = (
                        state_payload if label == "smoke compact state" else common_payloads[label]
                    )
                    return payload, hashlib.sha256(payload).hexdigest(), path.as_posix()

                with tempfile.TemporaryDirectory() as temporary:
                    raw = Path(temporary) / "raw"
                    (raw / "codex" / case.id / "01" / "workspace-reports" / "RPT-001").mkdir(
                        parents=True
                    )
                    with (
                        patch(
                            "evals.harness.run._captured_canonical_report",
                            return_value=(b"report", None, ()),
                        ),
                        patch(
                            "evals.harness.run._read_selected_file",
                            side_effect=selected_file,
                        ),
                        self.assertRaisesRegex(
                            ValueError, "smoke compact state impacts are invalid"
                        ),
                    ):
                        _smoke_observation(raw, "codex", slot, result, score)

    def test_v04_smoke_treats_none_observation_as_extraction_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                [
                    "--client",
                    "codex",
                    "--suite",
                    "smoke",
                    "--expected-plugin-version",
                    "0.4.0",
                    "--output",
                    str(output),
                ]
            )
            with patch("evals.harness.run._smoke_observation", return_value=None):
                exit_code = run_batch(args, FakeAdapter(plugin_version="0.4.0"))

            payload = json.loads((output / "performance.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["observations"], [])
        self.assertTrue(
            any("performance evidence invalid" in error for error in payload["gate"]["errors"])
        )

    def test_graph_smoke_parser_and_schedule_use_exact_checked_in_six(self):
        args = build_parser().parse_args(
            ["--client", "codex", "--suite", "graph-smoke", "--output", "out"]
        )
        cases = tuple(case.to_case_spec() for case in load_graph_cases())

        schedule = build_schedule(cases, args.suite, 1)

        self.assertEqual(
            tuple(slot.case.id for slot in schedule),
            tuple(case.id for case in load_graph_cases()),
        )
        self.assertTrue(all(slot.repetition == 1 for slot in schedule))

    def test_graph_smoke_never_retries_an_infrastructure_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = build_parser().parse_args(
                [
                    "--client",
                    "codex",
                    "--suite",
                    "graph-smoke",
                    "--expected-plugin-version",
                    "0.4.0",
                    "--output",
                    str(Path(temporary) / "output"),
                ]
            )
            adapter = FakeAdapter(
                statuses=(RunStatus.INFRA_ERROR,) * 6,
                plugin_version="0.4.0",
            )

            self.assertEqual(run_batch(args, adapter), 1)

        self.assertEqual(len(adapter.requests), 6)
        self.assertTrue(all(request.attempt == 1 for request in adapter.requests))
        self.assertTrue(all(request.retry_of is None for request in adapter.requests))

    def test_graph_smoke_persists_graph_scores_and_its_dedicated_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                [
                    "--client",
                    "codex",
                    "--suite",
                    "graph-smoke",
                    "--expected-plugin-version",
                    "0.4.0",
                    "--output",
                    str(output),
                ]
            )
            rejected = GraphSmokeGateResult(
                passed=False,
                errors=("injected graph gate failure",),
                median_graph_duration_ms=8,
                median_output_words=10,
                median_routed_resource_words=10,
            )
            with (
                patch(
                    "evals.harness.run._graph_observation",
                    side_effect=graph_observation,
                ),
                patch(
                    "evals.harness.run.evaluate_graph_smoke",
                    return_value=rejected,
                ) as gate,
            ):
                exit_code = run_batch(args, FakeAdapter(plugin_version="0.4.0"))

            scores = json.loads((output / "graph-scores.json").read_text(encoding="utf-8"))
            performance = json.loads((output / "performance.json").read_text(encoding="utf-8"))
            controller = json.loads((output / "controller.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        gate.assert_called_once()
        self.assertEqual(len(scores["scores"]), 6)
        self.assertEqual(len(performance["observations"]), 6)
        self.assertIn("injected graph gate failure", performance["gate"]["errors"])
        self.assertFalse(controller["graph_smoke_gate"]["passed"])

    def test_graph_observation_binds_exact_raw_trace_receipt_and_digest(self):
        from tests.test_graph_scoring import GraphScoringTest

        graph_case = load_graph_cases()[0]
        case = graph_case.to_case_spec()
        receipt = GraphScoringTest().receipt(graph_case)
        receipt_bytes = canonical_receipt_bytes(receipt)
        receipt_digest = hashlib.sha256(receipt_bytes).hexdigest()
        compact_digest = hashlib.sha256(
            json.dumps(compact_graph(receipt), sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        controller = {
            "valid": True,
            "begin_calls": 1,
            "trace_calls": 1,
            "finalize_calls": 1,
            "draft_ids": [receipt["draft_id"]],
            "receipt_ids": [receipt["receipt_id"]],
            "receipt_paths": [f".requirements-impact-refiner/graph/{receipt['draft_id']}.json"],
            "receipt_sha256": [receipt_digest],
            "trace_compact_graph_sha256": [compact_digest],
            "trace_request_sha256": [receipt["request_sha256"]],
            "trace_seeds": [
                [{"term": term, "location": location} for term, location in graph_case.seeds]
            ],
            "duplicate_or_error_calls": False,
        }
        graph_policy = {
            "schema_version": 1,
            "settings": receipt["settings"],
            "provider_inventory": ["builtin"],
            "seeds": [{"term": term, "location": location} for term, location in graph_case.seeds],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "raw"
            record_run(
                raw,
                "codex",
                case.id,
                1,
                {
                    "metadata.json": json.dumps(
                        {
                            "attempt": 1,
                            "client": "codex",
                            "retry_of": None,
                            "graph_policy": graph_policy,
                        }
                    ),
                    "first.final.txt": "Impact scan: 8.4 s\nImpact paths: PATH-001",
                    "first.jsonl": '{"type":"turn.completed"}\n',
                    "controller-evidence.json": json.dumps(controller),
                    f"workspace-graph/{receipt['draft_id']}.json": receipt_bytes,
                },
                root / "quarantine",
            )
            result = RunResult(
                case.id,
                1,
                "codex",
                RunStatus.PASS,
                None,
                final_output="Impact scan: 8.4 s\nImpact paths: PATH-001",
            )
            mechanical = MechanicalScore(case.id, 1, True, ())
            with patch("evals.harness.run._graph_state_parity", return_value=True):
                observation, score, digests = _graph_observation(
                    raw, "codex", ScheduledRun(case, 1), result, mechanical
                )

            self.assertTrue(score.passed, score.findings)
            self.assertTrue(observation.receipt_state_provider_parity)
            self.assertEqual(observation.graph_duration_ms, 8400)
            self.assertTrue(
                any(
                    path.endswith(f"workspace-graph/{receipt['draft_id']}.json")
                    for path, _ in digests
                )
            )

            controller_path = raw / "codex" / case.id / "01" / "controller-evidence.json"
            controller["trace_seeds"] = [
                [
                    {
                        "term": "totally.unrelated.seed",
                        "location": graph_case.seeds[0][1],
                    }
                ]
            ]
            controller_path.write_text(json.dumps(controller), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "catalog seeds"):
                _graph_observation(raw, "codex", ScheduledRun(case, 1), result, mechanical)
            controller["trace_seeds"] = [
                [{"term": term, "location": location} for term, location in graph_case.seeds]
            ]

            controller["trace_request_sha256"] = ["0" * 64]
            controller_path.write_text(json.dumps(controller), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "request identity"):
                _graph_observation(raw, "codex", ScheduledRun(case, 1), result, mechanical)
            controller["trace_request_sha256"] = [receipt["request_sha256"]]

            metadata_path = raw / "codex" / case.id / "01" / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["graph_policy"]["provider_inventory"] = ["ast-grep"]
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            controller_path.write_text(json.dumps(controller), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "run policy"):
                _graph_observation(raw, "codex", ScheduledRun(case, 1), result, mechanical)
            metadata["graph_policy"] = graph_policy
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            controller["receipt_sha256"] = ["0" * 64]
            controller_path.write_text(json.dumps(controller), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest disagrees"):
                _graph_observation(raw, "codex", ScheduledRun(case, 1), result, mechanical)

    def test_graph_state_parity_allows_same_exact_receipt_path_for_two_impacts(self):
        from tests.test_graph_scoring import GraphScoringTest

        graph_case = load_graph_cases()[0]
        receipt = GraphScoringTest().receipt(graph_case)
        score = (
            GraphScoringTest()
            .module()
            .score_graph(
                graph_case,
                receipt,
                "Impact scan: 8.4 s\nImpact paths: PATH-001",
            )
        )
        structured = {
            "id": "PATH-001",
            "labels": [row["label"] for row in receipt["nodes"]],
            "providers": ["builtin"],
            "confidence": "lexical",
            "locations": [row["location"] for row in receipt["nodes"]],
        }
        digest = hashlib.sha256(canonical_receipt_bytes(receipt)).hexdigest()
        state = {
            "scope": [
                {
                    "boundary": "Impact graph coverage",
                    "confidence": f"closed; receipt {receipt['receipt_id']}; sha256 {digest}; frontier none",
                }
            ],
            "graph_paths": [
                {"impact": "IMP-001", "paths": [structured]},
                {"impact": "IMP-002", "paths": [structured]},
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            attempt = Path(temporary)
            report = attempt / "workspace-reports/RPT-001"
            report.mkdir(parents=True)

            def selected_file(raw_root, path, label):
                if path.name == "current.json":
                    payload = b'{"state":"revision-0001.json"}'
                else:
                    payload = json.dumps(state).encode("utf-8")
                return payload, hashlib.sha256(payload).hexdigest(), path.as_posix()

            with (
                patch(
                    "evals.harness.run._captured_canonical_report",
                    return_value=(b"markdown", None, ()),
                ),
                patch(
                    "evals.harness.run._read_selected_file",
                    side_effect=selected_file,
                ),
            ):
                self.assertTrue(_graph_state_parity(attempt, attempt, receipt, digest, score))

    def test_graph_scoring_digest_binding_rejects_receipt_mutation_before_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                [
                    "--client",
                    "codex",
                    "--suite",
                    "graph-smoke",
                    "--expected-plugin-version",
                    "0.4.0",
                    "--output",
                    str(output),
                ]
            )

            def mutate_after_scoring(raw_root, client, slot, result, score):
                observation, graph_score, _ = graph_observation(
                    raw_root, client, slot, result, score
                )
                metadata = raw_root / client / slot.case.id / "01" / "metadata.json"
                original = metadata.read_bytes()
                digest = hashlib.sha256(original).hexdigest()
                metadata.write_bytes(original + b" ")
                relative = "raw/" + metadata.relative_to(raw_root).as_posix()
                return observation, graph_score, ((relative, digest),)

            with patch(
                "evals.harness.run._graph_observation",
                side_effect=mutate_after_scoring,
            ):
                exit_code = run_batch(args, FakeAdapter(plugin_version="0.4.0"))

        self.assertEqual(exit_code, 1)

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

    def test_expected_rir_plugin_id_defaults_to_the_canonical_identity(self):
        """A display name or evaluation alias must never be an implicit gate."""
        args = build_parser().parse_args(
            ["--client", "codex", "--suite", "smoke", "--output", "out"]
        )

        self.assertEqual(
            getattr(args, "expected_rir_plugin_id", None),
            "requirements-impact-refiner@requirements-impact-refiner",
        )

    def test_codex_adapter_receives_the_explicit_expected_plugin_version(self):
        """Dropping the requested version at the CLI boundary would probe the wrong release."""
        args = build_parser().parse_args(
            [
                "--client",
                "codex",
                "--probe-only",
                "--output",
                "out",
                "--expected-plugin-version",
                "0.3.1",
            ]
        )

        with patch("evals.harness.run.CodexAdapter") as adapter_class:
            create_adapter(args)

        adapter_class.assert_called_once_with(
            timeout_seconds=300.0,
            expected_plugin_version="0.3.1",
            expected_rir_plugin_id=("requirements-impact-refiner@requirements-impact-refiner"),
        )

    def test_codex_adapter_receives_an_explicit_evaluation_alias_id(self):
        """The CLI must pass an approved alias without normalizing its identity."""
        alias_id = "requirements-impact-refiner@requirements-impact-refiner-v031-eval"
        args = build_parser().parse_args(
            [
                "--client",
                "codex",
                "--probe-only",
                "--output",
                "out",
                "--expected-rir-plugin-id",
                alias_id,
            ]
        )

        with patch("evals.harness.run.CodexAdapter") as adapter_class:
            create_adapter(args)

        adapter_class.assert_called_once_with(
            timeout_seconds=300.0,
            expected_plugin_version="0.3.0",
            expected_rir_plugin_id=alias_id,
        )

    def test_probe_only_allows_omitting_suite_but_batches_do_not(self):
        """Making suite optional for a behavior batch would make its coverage ambiguous."""
        probe = build_parser().parse_args(["--client", "codex", "--probe-only", "--output", "out"])

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
                    "--client",
                    "claude",
                    "--suite",
                    "smoke",
                    "--model",
                    "opus",
                    "--output",
                    "out",
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

            exit_code = run_batch(args, FakeAdapter(raw_final_output="different sealed bytes"))

        self.assertEqual(exit_code, 1)
        self.assertFalse((output / "controller.json").exists())
        self.assertFalse((output / "report.md").exists())
        self.assertFalse((output / "manifest.sha256").exists())

    def test_compact_final_is_scored_against_captured_canonical_markdown(self):
        case = next(case for case in load_all() if case.id == "POS-authorization")
        compact = "## Change Impact Summary\n\nValidation: passed\n"
        canonical = (
            Path(__file__).parent / "fixtures" / "compact-state-post-decision.md"
        ).read_text(encoding="utf-8")
        state = (Path(__file__).parent / "fixtures" / "compact-state-post-decision.json").read_text(
            encoding="utf-8"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "raw"
            pointer = json.dumps(
                {
                    "schema_version": 1,
                    "report_id": "RPT-001",
                    "revision": 1,
                    "state": "revision-0001.json",
                    "markdown": "revision-0001.md",
                    "markdown_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                },
                sort_keys=True,
            )
            record_run(
                raw,
                "codex",
                case.id,
                1,
                {
                    "metadata.json": json.dumps(
                        {"attempt": 1, "client": "codex", "retry_of": None},
                        sort_keys=True,
                    ),
                    "first.final.txt": compact,
                    "workspace-reports/RPT-001/current.json": pointer,
                    "workspace-reports/RPT-001/revision-0001.json": state,
                    "workspace-reports/RPT-001/revision-0001.md": canonical,
                },
                root / "quarantine",
            )
            result = RunResult(
                case.id,
                1,
                "codex",
                RunStatus.PASS,
                None,
                final_output=compact,
            )

            score, trusted, digests = _score_selected_attempt(
                raw, "codex", ScheduledRun(case, 1), result
            )

        self.assertTrue(trusted)
        self.assertTrue(score.passed, score.findings)
        self.assertTrue(
            any(path.endswith("workspace-reports/RPT-001/revision-0001.md") for path, _ in digests)
        )

    def test_v04_scoring_rejects_controller_evidence_detached_from_jsonl(self):
        case = next(case for case in load_all() if case.id == "POS-authorization")
        compact = "## Change Impact Summary\n\nValidation: passed\n"
        canonical = (
            Path(__file__).parent / "fixtures" / "compact-state-post-decision.md"
        ).read_text(encoding="utf-8")
        state = (Path(__file__).parent / "fixtures" / "compact-state-post-decision.json").read_text(
            encoding="utf-8"
        )
        pointer = json.dumps(
            {
                "schema_version": 1,
                "report_id": "RPT-001",
                "revision": 1,
                "state": "revision-0001.json",
                "markdown": "revision-0001.md",
                "markdown_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            },
            sort_keys=True,
        )
        draft = "0" * 32
        receipt = "f" * 32
        events = (
            {
                "type": "item.completed",
                "item": {
                    "id": "begin",
                    "type": "mcp_tool_call",
                    "server": "requirements-impact-refiner",
                    "tool": "rir_begin",
                    "arguments": {},
                    "result": {
                        "structured_content": {
                            "draft_id": draft,
                            "installed_payload_sha256": "0" * 64,
                        }
                    },
                    "error": None,
                    "status": "completed",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "trace",
                    "type": "mcp_tool_call",
                    "server": "requirements-impact-refiner",
                    "tool": "rir_trace_impact",
                    "arguments": {"draft_id": draft, "seeds": []},
                    "result": {
                        "structured_content": {
                            "receipt_id": receipt,
                            "receipt_path": f".requirements-impact-refiner/graph/{draft}.json",
                            "receipt_sha256": "a" * 64,
                            "compact_graph": {},
                            "budget_status": "closed",
                            "request_sha256": "c" * 64,
                            "seeds": [],
                        }
                    },
                    "error": None,
                    "status": "completed",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "finalize",
                    "type": "mcp_tool_call",
                    "server": "requirements-impact-refiner",
                    "tool": "rir_finalize",
                    "arguments": {"draft_id": draft, "graph_receipt_id": receipt},
                    "result": {
                        "structured_content": {"status": "published", "display_text": compact}
                    },
                    "error": None,
                    "status": "completed",
                },
            },
        )
        jsonl = "\n".join(json.dumps(event) for event in events) + "\n"
        controller = analyze_controller_trace((jsonl,), compact, expected_turns=1)
        self.assertTrue(controller.valid)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "raw"
            record_run(
                raw,
                "codex",
                case.id,
                1,
                {
                    "metadata.json": json.dumps(
                        {
                            "attempt": 1,
                            "client": "codex",
                            "retry_of": None,
                            "plugin_version": "0.4.0",
                        }
                    ),
                    "first.final.txt": compact,
                    "first.jsonl": jsonl,
                    "controller-evidence.json": controller.to_json(),
                    "workspace-reports/RPT-001/current.json": pointer,
                    "workspace-reports/RPT-001/revision-0001.json": state,
                    "workspace-reports/RPT-001/revision-0001.md": canonical,
                },
                root / "quarantine",
            )
            result = RunResult(case.id, 1, "codex", RunStatus.PASS, None, final_output=compact)

            score, trusted, _ = _score_selected_attempt(raw, "codex", ScheduledRun(case, 1), result)

        self.assertFalse(trusted)
        self.assertIn("installed controller payload", score.findings[0])

    def test_tampered_compact_state_cannot_claim_markdown_parity(self):
        case = next(case for case in load_all() if case.id == "POS-authorization")
        compact = "## Change Impact Summary\n\n`IMP-001`\n"
        canonical = (
            Path(__file__).parent / "fixtures" / "compact-state-post-decision.md"
        ).read_text(encoding="utf-8")
        state = json.loads(
            (Path(__file__).parent / "fixtures" / "compact-state-post-decision.json").read_text(
                encoding="utf-8"
            )
        )
        state["summary"][0]["possible_issue"] = "tampered summary"
        pointer = json.dumps(
            {
                "schema_version": 1,
                "report_id": "RPT-001",
                "revision": 1,
                "state": "revision-0001.json",
                "markdown": "revision-0001.md",
                "markdown_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            },
            sort_keys=True,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "raw"
            record_run(
                raw,
                "codex",
                case.id,
                1,
                {
                    "metadata.json": json.dumps(
                        {"attempt": 1, "client": "codex", "retry_of": None}
                    ),
                    "first.final.txt": compact,
                    "workspace-reports/RPT-001/current.json": pointer,
                    "workspace-reports/RPT-001/revision-0001.json": json.dumps(
                        state, sort_keys=True
                    ),
                    "workspace-reports/RPT-001/revision-0001.md": canonical,
                },
                root / "quarantine",
            )
            result = RunResult(case.id, 1, "codex", RunStatus.PASS, None, final_output=compact)

            score, trusted, _ = _score_selected_attempt(raw, "codex", ScheduledRun(case, 1), result)

        self.assertFalse(trusted)
        self.assertIn("state and canonical Markdown disagree", score.findings[0])

    def test_lineage_non_utf8_predecessor_invalidates_scoring_evidence(self):
        """Replacement decoding would sever the SHA from the exact predecessor bytes."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                ["--client", "codex", "--suite", "smoke", "--output", str(output)]
            )

            exit_code = run_batch(args, FakeAdapter(raw_previous_bytes=b"\xff"))

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
                        output / "raw" / "codex" / "POS-authorization" / "01" / "first.final.txt"
                    )
                    target.write_text("changed after scoring", encoding="utf-8")
                return build_manifest(root)

            with patch(
                "evals.harness.run.build_manifest",
                side_effect=mutate_before_manifest,
            ):
                exit_code = run_batch(args, FakeAdapter())

            manifest_path = output / "manifest.sha256"
            manifest_valid = manifest_path.is_file() and not verify_manifest(
                output, manifest_path.read_text(encoding="utf-8")
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

        selected = next(row for row in ledger["runs"] if row["case_id"] == "LINEAGE-stable-blocked")
        score = next(
            row for row in ledger["mechanical_scores"] if row["case_id"] == "LINEAGE-stable-blocked"
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
                    "--client",
                    "codex",
                    "--suite",
                    "installed-superpowers",
                    "--repetitions",
                    "5",
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(run_batch(smoke, LineageEvidenceAdapter()), 0)
            self.assertEqual(run_batch(full, LineageEvidenceAdapter()), 0)
            ledger = json.loads((output / "controller.json").read_text(encoding="utf-8"))

        lineage = [
            row for row in ledger["mechanical_scores"] if row["case_id"].startswith("LINEAGE-")
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
                    "--client",
                    "codex",
                    "--suite",
                    "installed-superpowers",
                    "--repetitions",
                    "5",
                    "--output",
                    str(output),
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
            {
                (slot.case.id, slot.repetition)
                for slot in build_schedule(load_all(), "installed-superpowers", 5)
            },
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
                    "--client",
                    "codex",
                    "--suite",
                    "installed-superpowers",
                    "--repetitions",
                    "5",
                    "--model",
                    "two",
                    "--output",
                    str(output),
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
                    "requirements-impact-refiner",
                    "superpowers",
                    "extra-plugin",
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
                        "--client",
                        "codex",
                        "--suite",
                        "installed-superpowers",
                        "--repetitions",
                        "5",
                        "--output",
                        str(output),
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

    def test_v04_smoke_invokes_and_persists_the_performance_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            args = build_parser().parse_args(
                [
                    "--client",
                    "codex",
                    "--suite",
                    "smoke",
                    "--expected-plugin-version",
                    "0.4.0",
                    "--output",
                    str(output),
                ]
            )
            rejected = SmokeGateResult(
                passed=False,
                errors=("injected budget failure",),
                median_output_words=10,
                median_routed_resource_words=10,
            )
            with (
                patch(
                    "evals.harness.run._smoke_observation",
                    side_effect=controller_observation,
                ),
                patch(
                    "evals.harness.run.evaluate_smoke_gate",
                    return_value=rejected,
                ) as gate,
            ):
                exit_code = run_batch(args, FakeAdapter(plugin_version="0.4.0"))

            payload = json.loads((output / "performance.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        gate.assert_called_once()
        self.assertEqual(len(payload["observations"]), 6)
        self.assertFalse(payload["gate"]["passed"])
        self.assertIn("injected budget failure", payload["gate"]["errors"])


if __name__ == "__main__":
    unittest.main()
