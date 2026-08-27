import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "requirements-impact-refiner"
REFERENCES = SKILL_DIR / "references"
SKILL_PATH = SKILL_DIR / "SKILL.md"
BOOTSTRAP_SKILL_PATH = ROOT / "skills" / "using-requirements-impact-refiner" / "SKILL.md"
PREVIOUS_REFERENCE_PATH = REFERENCES / "previous-report.md"

ADAPTERS = {
    "generic": {
        "file": "integration-generic.md",
        "entry": "after the request is concrete enough for repository inspection",
        "exit": "hand the report to the user's chosen planning method",
    },
    "superpowers": {
        "file": "integration-superpowers.md",
        "entry": "after `brainstorming` design approval",
        "exit": "before `writing-plans`",
    },
    "claude-feature-dev": {
        "file": "integration-claude-feature-dev.md",
        "entry": "after Phase 3 clarification",
        "exit": "before Phase 4 architecture design",
    },
    "spec-kit": {
        "file": "integration-spec-kit.md",
        "entry": "after `speckit.specify` or `speckit.clarify`",
        "exit": "before `speckit.plan`",
    },
}

OWNERSHIP_CLAUSES = (
    "The adapter does not repeat general clarification already completed.",
    "The impact refiner asks only evidence-gap or impact-resolution questions.",
    "The external workflow is not automatically invoked.",
    "If more than one orchestrator is active, ask the user to choose one before continuing.",
)
SUPERPOWERS_HANDOFF_MARKER = (
    "superpowers:after-approved-brainstorming;impact-refinement;manual-handoff-before-writing-plans"
)


class McpBootstrapHarness:
    """Exercise the documented host route through the real MCP handle."""

    def __init__(
        self,
        root,
        *,
        status="none",
        scan_status="complete",
        can_promote=True,
        enabled=True,
        available=True,
        request_text="Yes, rename profile.displayName",
        evidence=("path:b.py", "symbol:B", "symbol:B", "path:a.py"),
    ):
        self.root = Path(root)
        self.status = status
        self.scan_status = scan_status
        self.can_promote = can_promote
        self.enabled = enabled
        self.available = available
        self.calls = []
        self.outputs = []
        self.request = request_text
        self.evidence = tuple(evidence)
        self._identifier = 0
        specification = importlib.util.spec_from_file_location(
            f"_task4_mcp_{id(self)}", ROOT / "scripts" / "rir_mcp_server.py"
        )
        self.module = importlib.util.module_from_spec(specification)
        sys.modules[specification.name] = self.module
        specification.loader.exec_module(self.module)
        self._controller_functions = {
            name: getattr(self.module.rir_controller, name)
            for name in (
                "lookup_previous",
                "scan_impact",
                "begin_refinement",
                "trace_impact",
                "finalize_refinement",
            )
        }
        self._install_controller_fakes()

    def _install_controller_fakes(self):
        def previous(request):
            self.calls.append(
                (
                    "rir_previous",
                    {
                        "repo_root": str(request.repo_root),
                        "request": request.request,
                        "repository_evidence": request.repository_evidence,
                        "report_id": request.report_id,
                    },
                )
            )
            selected_from_ambiguity = self.status == "ambiguous" and request.report_id in {
                "RPT-001",
                "RPT-002",
            }
            invalid_selection = self.status == "ambiguous" and request.report_id not in {
                None,
                "RPT-001",
                "RPT-002",
            }
            effective_status = (
                "fresh"
                if selected_from_ambiguity
                else ("none" if invalid_selection else self.status)
            )
            selected = effective_status in {"fresh", "stale"}
            return types.SimpleNamespace(
                status=effective_status,
                report_id=(request.report_id or "RPT-001") if selected else None,
                revision=2 if selected else None,
                markdown_sha256="a" * 64 if selected else None,
                created_at="2026-08-27T00:00:00Z" if selected else None,
                baseline_commit="b" * 40 if selected else None,
                changed_paths=("api/profile.py",) if effective_status == "stale" else (),
                changed_count=1 if effective_status == "stale" else (0 if selected else None),
                requirement_sha256="c" * 64,
                source_inventory_sha256="d" * 64 if selected else None,
                display_text=(f"previous-{effective_status}" if selected else None),
                reason=(
                    "multiple safe matches" if effective_status == "ambiguous" else effective_status
                ),
                elapsed_ms=1,
                candidates=(
                    tuple(
                        types.SimpleNamespace(
                            report_id=f"RPT-{number:03d}",
                            revision=number,
                            created_at="2026-08-25T12:34:56Z",
                        )
                        for number in (1, 2)
                    )
                    if effective_status == "ambiguous"
                    else ()
                ),
            )

        def scan(request):
            delta = request.previous_report_id is not None
            self.calls.append(
                (
                    "rir_scan",
                    {
                        "repo_root": str(request.repo_root),
                        "change_request": request.change_request,
                        "evidence": request.evidence,
                        "presentation": request.audience_override,
                        **(
                            {
                                "previous_report_id": request.previous_report_id,
                                "previous_revision": request.previous_revision,
                                "changed_paths": request.changed_paths,
                            }
                            if delta
                            else {}
                        ),
                    },
                )
            )
            return types.SimpleNamespace(
                status=self.scan_status,
                scan_id="1" * 32,
                receipt_id="2" * 32,
                receipt_sha256="3" * 64,
                display_text=(
                    "scan-needs-input-question"
                    if self.scan_status == "needs_input"
                    else "scan-result"
                ),
                risk_level="medium",
                paths=(),
                frontier=(),
                candidates=(),
                elapsed_ms=2,
                cache_status="miss",
                can_promote=self.can_promote,
                previous_report_id=request.previous_report_id,
                previous_revision=request.previous_revision,
                changed_paths=request.changed_paths,
                changed_count=1 if delta else None,
                previous_display_text="previous-stale" if delta else None,
            )

        def begin(request):
            self.calls.append(
                (
                    "rir_begin",
                    {
                        "request": request.request,
                        "repository_evidence": request.repository_evidence,
                        "adapter": request.adapter,
                        "scan_id": request.scan_id,
                    },
                )
            )
            draft_path = self.root / "draft.json"
            draft_path.write_text("{}", encoding="utf-8")
            return types.SimpleNamespace(
                draft_id="4" * 32,
                draft_path=draft_path,
                report_id="RPT-001",
                revision=1,
                previous_sha256="none",
                settings={"impact_graph": {"enabled": True}},
                prior_state=None,
                prior_key_map=None,
                scan_id=request.scan_id,
                graph_receipt_id="2" * 32 if request.scan_id else None,
            )

        def trace(request):
            self.calls.append(("rir_trace_impact", {"draft_id": request.draft_id}))
            receipt_path = self.root / "receipt.json"
            receipt_path.write_text("{}", encoding="utf-8")
            return types.SimpleNamespace(
                receipt_id="5" * 32,
                receipt_path=receipt_path,
                receipt_sha256="6" * 64,
                compact_graph={},
                budget_status="complete",
                request_sha256="7" * 64,
                seeds=request.seeds,
            )

        def finalize(request):
            self.calls.append(
                (
                    "rir_finalize",
                    {
                        "draft_id": request.draft_id,
                        "graph_receipt_id": request.graph_receipt_id,
                    },
                )
            )
            state_path = self.root / "state.json"
            markdown_path = self.root / "report.md"
            state_path.write_text("{}", encoding="utf-8")
            markdown_path.write_text("report", encoding="utf-8")
            return types.SimpleNamespace(
                status="published",
                report_id="RPT-001",
                revision=1,
                delivery="compact",
                display_text="final-result",
                state_path=state_path,
                markdown_path=markdown_path,
                markdown_sha256="8" * 64,
            )

        self.module.rir_controller.lookup_previous = previous
        self.module.rir_controller.scan_impact = scan
        self.module.rir_controller.begin_refinement = begin
        self.module.rir_controller.trace_impact = trace
        self.module.rir_controller.finalize_refinement = finalize

    def _restore_controller(self):
        for name, function in self._controller_functions.items():
            setattr(self.module.rir_controller, name, function)

    def _call(self, name, arguments):
        self._identifier += 1
        response = self.module.handle(
            {
                "jsonrpc": "2.0",
                "id": self._identifier,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        if "error" in response:
            raise AssertionError(response["error"])
        return response["result"]["structuredContent"]

    def _scan_forwardable(self):
        return (
            len(self.request.encode("utf-8")) <= 4096
            and len(self.evidence) <= 32
            and all(len(row.encode("utf-8")) <= 4096 for row in self.evidence)
        )

    def _shorten_instruction(self):
        if any("\uac00" <= character <= "\ud7a3" for character in self.request):
            return (
                "요청은 4 KiB 이하, 근거는 행당 4 KiB 이하로 32개까지 줄인 뒤 다시 시도해 주세요."
            )
        if any("\u3040" <= character <= "\u30ff" for character in self.request):
            return (
                "リクエストを4 KiB以下、根拠を1行4 KiB以下で32件までに短縮して再試行してください。"
            )
        return "Shorten the request to 4 KiB and evidence to 32 rows of 4 KiB, then retry."

    def run(self, *, selected_report_id=None, confirm_detail=False):
        try:
            if not self.enabled:
                return self
            if not self.available:
                self.outputs.append("previous-report bootstrap unavailable")
                return self
            previous = self._call(
                "rir_previous",
                {
                    "repo_root": str(self.root),
                    "request": self.request,
                    "repository_evidence": list(self.evidence),
                },
            )
            if previous["display_text"] is not None:
                self.outputs.append(previous["display_text"])
            if self.status == "fresh":
                return self
            if self.status == "ambiguous":
                self.outputs.append(
                    f"{previous['reason']}; choose "
                    + ", ".join(candidate["report_id"] for candidate in previous["candidates"])
                )
                if selected_report_id is None:
                    return self
                previous = self._call(
                    "rir_previous",
                    {
                        "repo_root": str(self.root),
                        "request": self.request,
                        "repository_evidence": list(self.evidence),
                        "report_id": selected_report_id,
                    },
                )
                if previous["display_text"] is not None:
                    self.outputs.append(previous["display_text"])
                if previous["status"] in {"fresh", "none"}:
                    return self
            if not self._scan_forwardable():
                self.outputs.append(self._shorten_instruction())
                return self
            scan_arguments = {
                "repo_root": str(self.root),
                "change_request": self.request,
                "evidence": list(self.evidence),
                "presentation": "balanced",
            }
            if previous["status"] == "stale":
                scan_arguments.update(
                    {
                        "previous_report_id": previous["report_id"],
                        "previous_revision": previous["revision"],
                        "changed_paths": previous["changed_paths"],
                    }
                )
            scan = self._call("rir_scan", scan_arguments)
            self.outputs.append(scan["display_text"])
            if scan["status"] == "needs_input":
                return self
            if not confirm_detail:
                return self
            begin_arguments = {
                "repo_root": str(self.root),
                "request": self.request,
                "repository_evidence": list(self.evidence),
                "adapter": "generic",
            }
            if scan["status"] == "complete" and scan["can_promote"]:
                begin_arguments["scan_id"] = scan["scan_id"]
            begin = self._call("rir_begin", begin_arguments)
            receipt_id = begin["graph_receipt_id"]
            if receipt_id is None:
                traced = self._call(
                    "rir_trace_impact",
                    {
                        "repo_root": str(self.root),
                        "draft_id": begin["draft_id"],
                        "seeds": [{"term": "profile.displayName", "location": "api/profile.py"}],
                    },
                )
                receipt_id = traced["receipt_id"]
            analysis = json.loads(
                (ROOT / "tests/fixtures/controller-analysis-pre-decision.json").read_text()
            )
            finalized = self._call(
                "rir_finalize",
                {
                    "repo_root": str(self.root),
                    "draft_id": begin["draft_id"],
                    "graph_receipt_id": receipt_id,
                    "analysis": analysis,
                },
            )
            self.outputs.append(finalized["display_text"])
            return self
        finally:
            self._restore_controller()


def run_cli_previous_then_scan(root, request_text, evidence):
    root = Path(root)
    client = root / "client"
    client.mkdir()
    shutil.copyfile(ROOT / "scripts/rir-controller.py", client / "rir-controller.py")
    (client / "rir_controller.py").write_text(
        """
from __future__ import annotations

import json
import os
import types
from dataclasses import dataclass

MAX_BEGIN_BYTES = 256 * 1024
MAX_TRACE_BYTES = 256 * 1024
MAX_FINALIZE_BYTES = 2 * 1024 * 1024

@dataclass(frozen=True)
class PreviousLookupRequest:
    repo_root: object
    request: str
    repository_evidence: tuple[str, ...]
    report_id: str | None = None

@dataclass(frozen=True)
class ScanRequest:
    repo_root: object
    change_request: str
    evidence: tuple[str, ...]
    audience_override: str | None
    previous_report_id: str | None = None
    previous_revision: int | None = None
    changed_paths: tuple[str, ...] = ()

def _log(tool, payload):
    with open(os.environ["RIR_TEST_LOG"], "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"tool": tool, **payload}) + "\\n")

def lookup_previous(request):
    _log("rir_previous", {
        "request": request.request,
        "repository_evidence": list(request.repository_evidence),
    })
    return types.SimpleNamespace(
        status="none", report_id=None, revision=None, markdown_sha256=None,
        created_at=None, baseline_commit=None, changed_paths=(), changed_count=None,
        requirement_sha256="a" * 64, source_inventory_sha256=None,
        display_text=None, reason="none", elapsed_ms=1, candidates=(),
    )

def scan_impact(request):
    _log("rir_scan", {
        "change_request": request.change_request,
        "evidence": list(request.evidence),
        "presentation": request.audience_override,
    })
    return types.SimpleNamespace(
        status="complete", scan_id="1" * 32, receipt_id="2" * 32,
        receipt_sha256="3" * 64, display_text="scan-result", risk_level="low",
        paths=(), frontier=(), candidates=(), elapsed_ms=1, cache_status="miss",
        can_promote=True,
    )
""".lstrip(),
        encoding="utf-8",
    )
    previous_input = root / "previous.json"
    scan_input = root / "scan.json"
    log_path = root / "calls.jsonl"
    previous_input.write_text(
        json.dumps({"request": request_text, "repository_evidence": list(evidence)}),
        encoding="utf-8",
    )
    scan_input.write_text(
        json.dumps(
            {
                "change_request": request_text,
                "evidence": list(evidence),
                "presentation": "balanced",
            }
        ),
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment["RIR_TEST_LOG"] = str(log_path)
    previous = subprocess.run(
        [
            sys.executable,
            str(client / "rir-controller.py"),
            "previous",
            "--repo-root",
            str(root),
            "--input",
            str(previous_input),
        ],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    scan = None
    if previous.returncode == 0:
        scan = subprocess.run(
            [
                sys.executable,
                str(client / "rir-controller.py"),
                "scan",
                "--repo-root",
                str(root),
                "--input",
                str(scan_input),
                "--json",
            ],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
    calls = (
        [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        if log_path.exists()
        else []
    )
    return previous, scan, calls


def headings(text):
    return re.findall(r"^## (.+)$", text, flags=re.MULTILINE)


class IntegrationAdapterContractTest(unittest.TestCase):
    def test_fresh_previous_returns_renderer_text_and_stops_without_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            outcome = McpBootstrapHarness(directory, status="fresh").run()

        self.assertEqual([name for name, _ in outcome.calls], ["rir_previous"])
        self.assertEqual(outcome.outputs, ["previous-fresh"])

    def test_stale_previous_displays_first_then_runs_valid_delta_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            outcome = McpBootstrapHarness(directory, status="stale").run()

        self.assertEqual([name for name, _ in outcome.calls], ["rir_previous", "rir_scan"])
        self.assertEqual(outcome.outputs, ["previous-stale", "scan-result"])
        self.assertEqual(
            set(outcome.calls[1][1]),
            {
                "repo_root",
                "change_request",
                "evidence",
                "presentation",
                "previous_report_id",
                "previous_revision",
                "changed_paths",
            },
        )
        self.assertEqual(outcome.calls[1][1]["previous_report_id"], "RPT-001")
        self.assertEqual(outcome.calls[1][1]["previous_revision"], 2)
        self.assertEqual(outcome.calls[1][1]["changed_paths"], ("api/profile.py",))

    def test_none_runs_ordinary_scan_after_exactly_one_previous_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            outcome = McpBootstrapHarness(directory, status="none").run()

        self.assertEqual([name for name, _ in outcome.calls], ["rir_previous", "rir_scan"])
        self.assertEqual(outcome.calls[0][1]["repository_evidence"], outcome.evidence)
        self.assertEqual(outcome.calls[1][1]["evidence"], outcome.evidence)
        self.assertEqual(outcome.calls[1][1]["change_request"], outcome.request)

    def test_ambiguous_exposes_safe_candidates_and_resolves_with_second_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            stopped = McpBootstrapHarness(directory, status="ambiguous").run()
        with tempfile.TemporaryDirectory() as directory:
            selected = McpBootstrapHarness(directory, status="ambiguous").run(
                selected_report_id="RPT-002"
            )
        with tempfile.TemporaryDirectory() as directory:
            invalid = McpBootstrapHarness(directory, status="ambiguous").run(
                selected_report_id="RPT-999"
            )

        self.assertEqual([name for name, _ in stopped.calls], ["rir_previous"])
        self.assertEqual(
            stopped.outputs,
            ["multiple safe matches; choose RPT-001, RPT-002"],
        )
        self.assertEqual([name for name, _ in selected.calls], ["rir_previous", "rir_previous"])
        self.assertEqual(selected.calls[1][1]["report_id"], "RPT-002")
        self.assertEqual(selected.outputs[-1], "previous-fresh")
        self.assertEqual([name for name, _ in invalid.calls], ["rir_previous", "rir_previous"])
        self.assertIsNone(invalid.calls[0][1]["report_id"])
        self.assertNotIn("previous-fresh", invalid.outputs)

    def test_promoted_scan_confirmation_skips_trace_and_uses_begin_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            first_turn = McpBootstrapHarness(directory, status="none", can_promote=True).run()
        with tempfile.TemporaryDirectory() as directory:
            detailed = McpBootstrapHarness(directory, status="none", can_promote=True).run(
                confirm_detail=True
            )

        self.assertEqual(
            [name for name, _ in first_turn.calls],
            ["rir_previous", "rir_scan"],
        )
        self.assertEqual(
            [name for name, _ in detailed.calls],
            ["rir_previous", "rir_scan", "rir_begin", "rir_finalize"],
        )
        self.assertEqual(detailed.calls[2][1]["scan_id"], "1" * 32)
        self.assertEqual(detailed.calls[3][1]["graph_receipt_id"], "2" * 32)

    def test_nonpromotable_scan_confirmation_traces_exactly_once(self):
        with tempfile.TemporaryDirectory() as directory:
            outcome = McpBootstrapHarness(directory, status="none", can_promote=False).run(
                confirm_detail=True
            )

        self.assertEqual(
            [name for name, _ in outcome.calls],
            ["rir_previous", "rir_scan", "rir_begin", "rir_trace_impact", "rir_finalize"],
        )
        self.assertIsNone(outcome.calls[2][1]["scan_id"])
        self.assertEqual(outcome.calls[4][1]["graph_receipt_id"], "5" * 32)

    def test_wide_fresh_lookup_returns_but_stale_and_none_stop_before_invalid_scan(self):
        request_text = "x" * 5000
        for status, expected_outputs in (
            ("fresh", ["previous-fresh"]),
            (
                "stale",
                [
                    "previous-stale",
                    "Shorten the request to 4 KiB and evidence to 32 rows of 4 KiB, then retry.",
                ],
            ),
            (
                "none",
                ["Shorten the request to 4 KiB and evidence to 32 rows of 4 KiB, then retry."],
            ),
        ):
            with self.subTest(status=status):
                with tempfile.TemporaryDirectory() as directory:
                    outcome = McpBootstrapHarness(
                        directory, status=status, request_text=request_text
                    ).run()

                self.assertEqual([name for name, _ in outcome.calls], ["rir_previous"])
                self.assertEqual(outcome.outputs, expected_outputs)

        with tempfile.TemporaryDirectory() as directory:
            korean = McpBootstrapHarness(
                directory,
                status="none",
                request_text="가" * 1500,
            ).run()
        self.assertEqual(
            korean.outputs,
            ["요청은 4 KiB 이하, 근거는 행당 4 KiB 이하로 32개까지 줄인 뒤 다시 시도해 주세요."],
        )
        self.assertLessEqual(len(korean.outputs[0].encode("utf-8")), 256)

    def test_needs_input_stops_then_corrected_boundary_restarts_previous_and_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            first_turn = McpBootstrapHarness(
                directory,
                status="none",
                scan_status="needs_input",
                can_promote=False,
            ).run(confirm_detail=True)
        with tempfile.TemporaryDirectory() as directory:
            corrected = McpBootstrapHarness(
                directory,
                status="none",
                request_text="Rename api/profile.py displayName",
                evidence=("api/profile.py",),
            ).run()

        self.assertEqual(
            [name for name, _ in first_turn.calls],
            ["rir_previous", "rir_scan"],
        )
        self.assertEqual(first_turn.outputs, ["scan-needs-input-question"])
        self.assertEqual(
            [name for name, _ in corrected.calls],
            ["rir_previous", "rir_scan"],
        )
        self.assertEqual(corrected.calls[0][1]["request"], "Rename api/profile.py displayName")
        self.assertNotIn("rir_begin", [name for name, _ in corrected.calls])

        reference = PREVIOUS_REFERENCE_PATH.read_text(encoding="utf-8")
        self.assertIn("needs_input", reference)
        self.assertIn("restart", reference.lower())

    def test_non_change_conversations_invoke_neither_lookup_nor_scan(self):
        bootstrap = BOOTSTRAP_SKILL_PATH.read_text(encoding="utf-8")
        for conversation in ("ideation", "explanation", "debugging", "code review", "status"):
            self.assertIn(conversation, bootstrap)
        self.assertIn("call neither `rir_previous` nor `rir_scan`", bootstrap)

    def test_bootstrap_confirmation_rule_is_explicitly_flow_specific(self):
        bootstrap = BOOTSTRAP_SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "Report flow enters detailed refinement immediately after a non-`needs_input` scan; "
            "ask flow enters it only after a later explicit yes",
            bootstrap,
        )
        self.assertNotIn(
            "Only a later explicit yes to a non-`needs_input` scan's refinement question "
            "enters detailed refinement",
            bootstrap,
        )

    def test_disabled_and_unavailable_routes_make_no_tool_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            disabled = McpBootstrapHarness(directory, enabled=False).run()
        with tempfile.TemporaryDirectory() as directory:
            unavailable = McpBootstrapHarness(directory, available=False).run()

        self.assertEqual(disabled.calls, [])
        self.assertEqual(disabled.outputs, [])
        self.assertEqual(unavailable.calls, [])
        self.assertEqual(unavailable.outputs, ["previous-report bootstrap unavailable"])

    def test_mcp_previous_keeps_wider_lookup_bounds_than_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            harness = McpBootstrapHarness(directory)
            harness._restore_controller()
            previous = harness.module.PREVIOUS_SCHEMA["properties"]
            scan = harness.module.SCAN_SCHEMA["properties"]

        self.assertEqual(previous["request"]["maxLength"], 262144)
        self.assertEqual(previous["repository_evidence"]["maxItems"], 128)
        self.assertEqual(scan["change_request"]["maxLength"], 4096)
        self.assertEqual(scan["evidence"]["maxItems"], 32)

    def test_cli_previous_then_scan_preserves_exact_forwardable_payload(self):
        evidence = ("path:b.py", "symbol:B", "symbol:B", "path:a.py")
        with tempfile.TemporaryDirectory() as directory:
            previous, scan, calls = run_cli_previous_then_scan(
                directory, "Rename profile.displayName", evidence
            )

        self.assertEqual(previous.returncode, 0, previous.stderr)
        self.assertIsNotNone(scan)
        self.assertEqual(scan.returncode, 0, scan.stderr)
        self.assertEqual(
            calls,
            [
                {
                    "tool": "rir_previous",
                    "request": "Rename profile.displayName",
                    "repository_evidence": list(evidence),
                },
                {
                    "tool": "rir_scan",
                    "change_request": "Rename profile.displayName",
                    "evidence": list(evidence),
                    "presentation": "balanced",
                },
            ],
        )

    def test_core_reads_previous_reference_before_invoking_lookup(self):
        text = SKILL_PATH.read_text(encoding="utf-8")

        self.assertLess(text.index("references/previous-report.md"), text.index("`rir_previous`"))

    def test_each_adapter_has_exactly_the_four_contract_sections(self):
        for adapter in ADAPTERS.values():
            text = (REFERENCES / adapter["file"]).read_text(encoding="utf-8")
            self.assertEqual(headings(text), ["Entry", "Ownership", "Output", "Exit"])

    def test_each_adapter_preserves_external_workflow_ownership(self):
        for adapter in ADAPTERS.values():
            text = (REFERENCES / adapter["file"]).read_text(encoding="utf-8")
            ownership = text.split("## Ownership\n", 1)[1].split("\n## Output", 1)[0]
            for clause in OWNERSHIP_CLAUSES:
                self.assertIn(clause, ownership)

    def test_each_adapter_declares_its_exact_entry_and_exit_sequence(self):
        for name, adapter in ADAPTERS.items():
            text = (REFERENCES / adapter["file"]).read_text(encoding="utf-8")
            entry = text.split("## Entry\n", 1)[1].split("\n## Ownership", 1)[0]
            exit_section = text.split("## Exit\n", 1)[1]
            self.assertIn(adapter["entry"], entry, name)
            self.assertIn(adapter["exit"], exit_section, name)

    def test_generic_entry_rejects_approval_without_inspectable_inputs(self):
        text = (REFERENCES / ADAPTERS["generic"]["file"]).read_text(encoding="utf-8")
        entry = text.split("## Entry\n", 1)[1].split("\n## Ownership", 1)[0]
        self.assertIn("Approval alone is not sufficient.", entry)
        self.assertIn("substantive change request", entry)
        self.assertIn("affected repository scope or evidence target", entry)
        self.assertIn(
            "Before emitting any `REQ-###`, `INV-###`, `IMP-###`, `DEC-###`, `AC-###`, or canonical report",
            entry,
        )
        self.assertIn("do not start impact refinement", entry)
        self.assertIn("state that the entry gate is not met", entry)
        self.assertIn("ask only for the missing requirement text or scope", entry)
        self.assertIn("not broad product ideation", entry)

    def test_generic_entry_accepts_concrete_supplied_repository_evidence(self):
        text = (REFERENCES / ADAPTERS["generic"]["file"]).read_text(encoding="utf-8")
        entry = text.split("## Entry\n", 1)[1].split("\n## Ownership", 1)[0]

        self.assertIn("concrete supplied `repository_evidence`", entry.lower())
        self.assertIn("do not demand a mounted repository", entry)
        self.assertIn("explicit requested mechanics as already selected", entry)

    def test_superpowers_missing_design_content_becomes_a_blocked_report(self):
        text = (REFERENCES / ADAPTERS["superpowers"]["file"]).read_text(encoding="utf-8")
        entry = text.split("## Entry\n", 1)[1].split("\n## Ownership", 1)[0]

        self.assertIn("approval state is known", entry)
        self.assertIn("blocked impact report", entry)
        self.assertIn(SUPERPOWERS_HANDOFF_MARKER, text)

    def test_each_adapter_returns_the_canonical_report_without_planning(self):
        for adapter in ADAPTERS.values():
            text = (REFERENCES / adapter["file"]).read_text(encoding="utf-8")
            output = text.split("## Output\n", 1)[1].split("\n## Exit", 1)[0]
            self.assertIn("canonical impact report", output)
            self.assertIn("Planning Handoff", output)
            self.assertIn("not an implementation plan", output)

    def test_superpowers_adapter_requires_the_exact_structured_handoff_marker(self):
        """Packaged guidance must emit the marker consumed by mechanical scoring."""
        text = (REFERENCES / ADAPTERS["superpowers"]["file"]).read_text(encoding="utf-8")
        output = text.split("## Output\n", 1)[1].split("\n## Exit", 1)[0]

        self.assertIn(SUPERPOWERS_HANDOFF_MARKER, output)
        self.assertIn("exactly", output)
        self.assertIn("readiness", output.lower())
        self.assertEqual(
            text.encode("utf-8"),
            (ROOT / "references" / "integration-superpowers.md").read_bytes(),
        )

    def test_skill_routes_to_exactly_one_adapter_after_selection(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        routing = text.split("## Detailed refinement\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("After yes", routing)
        self.assertIn("exactly one adapter", routing)
        for name, adapter in ADAPTERS.items():
            self.assertEqual(routing.count(f"[{name}]"), 1)
            self.assertEqual(routing.count(f"(references/{adapter['file']})"), 1)

    def test_skill_activation_excludes_code_review_without_excluding_all_review(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "not ideation, debugging, code review, or generic PRDs",
            text,
        )
        self.assertNotIn(
            "not ideation, debugging, review, or generic PRDs",
            text,
        )

    def test_skill_entrypoint_stays_below_three_hundred_forty_words(self):
        words = SKILL_PATH.read_text(encoding="utf-8").split()
        self.assertLess(len(words), 180)


if __name__ == "__main__":
    unittest.main()
