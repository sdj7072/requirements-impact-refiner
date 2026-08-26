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

    def __init__(self, root, *, status="none", can_promote=True, enabled=True, available=True):
        self.root = Path(root)
        self.status = status
        self.can_promote = can_promote
        self.enabled = enabled
        self.available = available
        self.calls = []
        self.outputs = []
        self.request = "Yes, rename profile.displayName"
        self.evidence = ("path:b.py", "symbol:B", "symbol:B", "path:a.py")
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
                    },
                )
            )
            selected = self.status in {"fresh", "stale"}
            return types.SimpleNamespace(
                status=self.status,
                report_id="RPT-001" if selected else None,
                revision=2 if selected else None,
                markdown_sha256="a" * 64 if selected else None,
                created_at="2026-08-27T00:00:00Z" if selected else None,
                baseline_commit="b" * 40 if selected else None,
                changed_paths=("api/profile.py",) if self.status == "stale" else (),
                changed_count=1 if self.status == "stale" else (0 if selected else None),
                requirement_sha256="c" * 64,
                source_inventory_sha256="d" * 64 if selected else None,
                display_text=(f"previous-{self.status}" if selected else None),
                reason=("multiple safe matches" if self.status == "ambiguous" else self.status),
                elapsed_ms=1,
            )

        def scan(request):
            self.calls.append(
                (
                    "rir_scan",
                    {
                        "repo_root": str(request.repo_root),
                        "change_request": request.change_request,
                        "evidence": request.evidence,
                        "presentation": request.audience_override,
                    },
                )
            )
            return types.SimpleNamespace(
                status="complete" if self.can_promote else "partial",
                scan_id="1" * 32,
                receipt_id="2" * 32,
                receipt_sha256="3" * 64,
                display_text="scan-result",
                risk_level="medium",
                paths=(),
                frontier=(),
                candidates=(),
                elapsed_ms=2,
                cache_status="miss",
                can_promote=self.can_promote,
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

    def run(self, *, confirm_ambiguous_scan=False, confirm_detail=False):
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
            if self.status == "ambiguous" and not confirm_ambiguous_scan:
                self.outputs.append(f"{previous['reason']}; start a new Fast Scan?")
                return self
            scan = self._call(
                "rir_scan",
                {
                    "repo_root": str(self.root),
                    "change_request": self.request,
                    "evidence": list(self.evidence),
                    "presentation": "balanced",
                },
            )
            self.outputs.append(scan["display_text"])
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

@dataclass(frozen=True)
class ScanRequest:
    repo_root: object
    change_request: str
    evidence: tuple[str, ...]
    audience_override: str | None

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
        display_text=None, reason="none", elapsed_ms=1,
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

    def test_stale_previous_displays_first_then_runs_valid_ordinary_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            outcome = McpBootstrapHarness(directory, status="stale").run()

        self.assertEqual([name for name, _ in outcome.calls], ["rir_previous", "rir_scan"])
        self.assertEqual(outcome.outputs, ["previous-stale", "scan-result"])
        self.assertEqual(
            set(outcome.calls[1][1]),
            {"repo_root", "change_request", "evidence", "presentation"},
        )
        self.assertNotIn("report_id", outcome.calls[1][1])
        self.assertNotIn("revision", outcome.calls[1][1])
        self.assertNotIn("changed_paths", outcome.calls[1][1])

    def test_none_runs_ordinary_scan_after_exactly_one_previous_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            outcome = McpBootstrapHarness(directory, status="none").run()

        self.assertEqual([name for name, _ in outcome.calls], ["rir_previous", "rir_scan"])
        self.assertEqual(outcome.calls[0][1]["repository_evidence"], outcome.evidence)
        self.assertEqual(outcome.calls[1][1]["evidence"], outcome.evidence)
        self.assertEqual(outcome.calls[1][1]["change_request"], outcome.request)

    def test_ambiguous_returns_safe_reason_and_offers_only_a_new_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            stopped = McpBootstrapHarness(directory, status="ambiguous").run()
        with tempfile.TemporaryDirectory() as directory:
            scanned = McpBootstrapHarness(directory, status="ambiguous").run(
                confirm_ambiguous_scan=True
            )

        self.assertEqual([name for name, _ in stopped.calls], ["rir_previous"])
        self.assertEqual(stopped.outputs, ["multiple safe matches; start a new Fast Scan?"])
        self.assertNotIn("RPT-", stopped.outputs[0])
        self.assertEqual([name for name, _ in scanned.calls], ["rir_previous", "rir_scan"])
        self.assertNotIn("rir_begin", [name for name, _ in scanned.calls])

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

    def test_non_change_conversations_invoke_neither_lookup_nor_scan(self):
        bootstrap = BOOTSTRAP_SKILL_PATH.read_text(encoding="utf-8")
        for conversation in ("ideation", "explanation", "debugging", "code review", "status"):
            self.assertIn(conversation, bootstrap)
        self.assertIn("call neither `rir_previous` nor `rir_scan`", bootstrap)

    def test_disabled_and_unavailable_routes_make_no_tool_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            disabled = McpBootstrapHarness(directory, enabled=False).run()
        with tempfile.TemporaryDirectory() as directory:
            unavailable = McpBootstrapHarness(directory, available=False).run()

        self.assertEqual(disabled.calls, [])
        self.assertEqual(disabled.outputs, [])
        self.assertEqual(unavailable.calls, [])
        self.assertEqual(unavailable.outputs, ["previous-report bootstrap unavailable"])

    def test_mcp_previous_rejects_inputs_that_scan_cannot_forward(self):
        cases = (
            ("x" * 4097, []),
            ("界" * 1366, []),
            ("valid", ["x"] * 33),
            ("valid", ["界" * 1366]),
        )
        for request_text, evidence in cases:
            with self.subTest(request_bytes=len(request_text.encode()), rows=len(evidence)):
                with tempfile.TemporaryDirectory() as directory:
                    harness = McpBootstrapHarness(directory)
                    response = harness.module.handle(
                        {
                            "jsonrpc": "2.0",
                            "id": 99,
                            "method": "tools/call",
                            "params": {
                                "name": "rir_previous",
                                "arguments": {
                                    "repo_root": directory,
                                    "request": request_text,
                                    "repository_evidence": evidence,
                                },
                            },
                        },
                    )
                    harness._restore_controller()

                self.assertEqual(response["error"]["code"], -32602)
                self.assertEqual(harness.calls, [])

    def test_mcp_previous_and_scan_publish_identical_forwardable_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            harness = McpBootstrapHarness(directory)
            harness._restore_controller()
            previous = harness.module.PREVIOUS_SCHEMA["properties"]
            scan = harness.module.SCAN_SCHEMA["properties"]

        self.assertEqual(previous["request"], scan["change_request"])
        self.assertEqual(previous["repository_evidence"], scan["evidence"])

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

    def test_cli_previous_rejects_unforwardable_input_before_lookup(self):
        cases = (
            ("x" * 4097, ()),
            ("界" * 1366, ()),
            ("valid", ("x",) * 33),
            ("valid", ("界" * 1366,)),
        )
        for request_text, evidence in cases:
            with self.subTest(request_bytes=len(request_text.encode()), rows=len(evidence)):
                with tempfile.TemporaryDirectory() as directory:
                    previous, scan, calls = run_cli_previous_then_scan(
                        directory, request_text, evidence
                    )

                self.assertEqual(previous.returncode, 1)
                self.assertIsNone(scan)
                self.assertEqual(calls, [])

    def test_cli_forwardable_bound_validator_covers_every_rejection_branch(self):
        specification = importlib.util.spec_from_file_location(
            "_task4_cli_bounds", ROOT / "scripts/rir-controller.py"
        )
        cli = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(cli)

        cli._validate_previous_scan_bounds("x" * 4096, ["y" * 4096] * 32)
        rejected = (
            ("", []),
            (object(), []),
            ("\ud800", []),
            ("x" * 4097, []),
            ("valid", ["x"] * 33),
            ("valid", [""]),
            ("valid", [object()]),
            ("valid", ["\ud800"]),
            ("valid", ["x" * 4097]),
        )
        for request_text, evidence in rejected:
            with self.subTest(request=request_text, rows=len(evidence)):
                with self.assertRaises(ValueError):
                    cli._validate_previous_scan_bounds(request_text, evidence)

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
