import re
import unittest
from dataclasses import dataclass
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


@dataclass(frozen=True)
class BootstrapOutcome:
    calls: tuple[str, ...]
    display: str
    asks_question: bool
    exposes_previous_body: bool
    scan_fields: tuple[str, ...]
    previous_evidence: tuple[str, ...] = ()
    scan_evidence: tuple[str, ...] = ()
    manual_invention: bool = False


def _contract_rows(text, heading):
    section = text.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in section.splitlines():
        if not line.startswith("|") or set(line.replace("|", "").replace(" ", "")) <= {"-"}:
            continue
        rows.append(tuple(cell.strip().strip("`") for cell in line.strip("|").split("|")))
    return {row[0]: row[1:] for row in rows[1:]}


def run_bootstrap_fixture(
    *,
    previous_status="none",
    conversation="concrete-change",
    original_request_says_yes=False,
    followup_reply=None,
    availability="mcp",
    repository_evidence=("first", "duplicate", "duplicate", "last"),
):
    """Execute the skill's tables as a deterministic tool-order fixture."""
    bootstrap = BOOTSTRAP_SKILL_PATH.read_text(encoding="utf-8")
    core = SKILL_PATH.read_text(encoding="utf-8")
    tool_order = re.findall(
        r"`(rir_(?:previous|scan|begin|trace_impact|finalize))`", bootstrap + "\n" + core
    )
    if not tool_order:
        return BootstrapOutcome((), "none", False, False, (), (), (), False)

    # Preserve the pre-v0.6 behavior as an observable RED result: the first
    # declared tool was rir_scan and no status-specific previous route existed.
    if tool_order[0] != "rir_previous":
        return BootstrapOutcome((tool_order[0],), "scan", False, False, (), (), (), False)

    contract = PREVIOUS_REFERENCE_PATH.read_text(encoding="utf-8")
    activation = _contract_rows(contract, "Activation contract")
    availability_rows = _contract_rows(contract, "Availability contract")
    statuses = _contract_rows(contract, "Status contract")
    confirmations = _contract_rows(contract, "Confirmation contract")

    if activation[conversation][0] == "stop":
        return BootstrapOutcome((), "none", False, False, (), (), (), False)
    if availability_rows[availability][0] == "stop-with-disclosure":
        return BootstrapOutcome((), "disclosure", False, False, (), (), (), False)

    display, next_action, raw_fields, question, body = statuses[previous_status]
    calls = ["rir_previous"]
    scan_fields = ()
    if next_action == "rir_scan":
        calls.append(next_action)
        scan_fields = tuple(field for field in raw_fields.split(",") if field != "none")

    # A "yes" embedded in the change request predates the rendered question;
    # the confirmation table deliberately gives it no detailed tool sequence.
    confirmation_key = "original-request-yes" if original_request_says_yes else "no-followup"
    if followup_reply == "yes" and "rir_scan" in calls:
        confirmation_key = "explicit-yes-after-scan"
    detailed = confirmations[confirmation_key][0]
    if detailed != "none":
        calls.extend(tool for tool in detailed.split(",") if tool)

    return BootstrapOutcome(
        tuple(calls),
        display,
        question == "yes",
        body == "yes",
        scan_fields,
        tuple(repository_evidence),
        tuple(repository_evidence) if "repository_evidence" in scan_fields else (),
        False,
    )


def headings(text):
    return re.findall(r"^## (.+)$", text, flags=re.MULTILINE)


class IntegrationAdapterContractTest(unittest.TestCase):
    def test_fresh_previous_returns_renderer_text_and_stops_without_scan(self):
        outcome = run_bootstrap_fixture(previous_status="fresh")

        self.assertEqual(outcome.calls, ("rir_previous",))
        self.assertEqual(outcome.display, "display_text")
        self.assertTrue(outcome.exposes_previous_body)

    def test_stale_previous_displays_first_then_scans_selected_revision(self):
        outcome = run_bootstrap_fixture(previous_status="stale")

        self.assertEqual(outcome.calls, ("rir_previous", "rir_scan"))
        self.assertEqual(outcome.display, "display_text-before-scan")
        self.assertEqual(outcome.scan_fields, ("report_id", "revision", "changed_paths"))

    def test_none_runs_ordinary_scan_after_exactly_one_previous_lookup(self):
        evidence = ("path:b.py", "symbol:B", "symbol:B", "path:a.py")
        outcome = run_bootstrap_fixture(previous_status="none", repository_evidence=evidence)

        self.assertEqual(outcome.calls, ("rir_previous", "rir_scan"))
        self.assertEqual(outcome.scan_fields, ("request", "repository_evidence"))
        self.assertEqual(outcome.calls.count("rir_previous"), 1)
        self.assertEqual(outcome.calls.count("rir_scan"), 1)
        self.assertEqual(outcome.previous_evidence, evidence)
        self.assertEqual(outcome.scan_evidence, evidence)

    def test_ambiguous_asks_for_discriminator_without_scan_or_report_body(self):
        outcome = run_bootstrap_fixture(previous_status="ambiguous")

        self.assertEqual(outcome.calls, ("rir_previous",))
        self.assertEqual(outcome.display, "candidates-and-question")
        self.assertTrue(outcome.asks_question)
        self.assertFalse(outcome.exposes_previous_body)

    def test_only_explicit_followup_yes_after_scan_starts_detailed_tools(self):
        first_turn = run_bootstrap_fixture(previous_status="none", original_request_says_yes=True)
        second_turn = run_bootstrap_fixture(previous_status="none", followup_reply="yes")

        self.assertEqual(first_turn.calls, ("rir_previous", "rir_scan"))
        self.assertEqual(
            second_turn.calls,
            ("rir_previous", "rir_scan", "rir_begin", "rir_trace_impact", "rir_finalize"),
        )

    def test_non_change_conversations_invoke_neither_lookup_nor_scan(self):
        for conversation in ("ideation", "explanation", "debugging", "code-review", "status"):
            with self.subTest(conversation=conversation):
                self.assertEqual(run_bootstrap_fixture(conversation=conversation).calls, ())

    def test_unavailable_surfaces_do_not_trigger_manual_report_invention(self):
        outcome = run_bootstrap_fixture(availability="unavailable")

        self.assertEqual(outcome.calls, ())
        self.assertEqual(outcome.display, "disclosure")
        self.assertFalse(outcome.exposes_previous_body)
        self.assertFalse(outcome.manual_invention)

    def test_plugin_disable_switch_stops_before_lookup(self):
        outcome = run_bootstrap_fixture(availability="plugin-disabled")

        self.assertEqual(outcome.calls, ())
        self.assertFalse(outcome.manual_invention)

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
