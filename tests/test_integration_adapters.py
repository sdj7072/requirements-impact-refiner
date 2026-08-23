import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "requirements-impact-refiner"
REFERENCES = SKILL_DIR / "references"
SKILL_PATH = SKILL_DIR / "SKILL.md"

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
    "superpowers:after-approved-brainstorming;impact-refinement;"
    "manual-handoff-before-writing-plans"
)


def headings(text):
    return re.findall(r"^## (.+)$", text, flags=re.MULTILINE)


class IntegrationAdapterContractTest(unittest.TestCase):
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
        self.assertIn("Before emitting any `REQ-###`, `INV-###`, `IMP-###`, `DEC-###`, `AC-###`, or canonical report", entry)
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
        text = (REFERENCES / ADAPTERS["superpowers"]["file"]).read_text(
            encoding="utf-8"
        )
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
        text = (REFERENCES / ADAPTERS["superpowers"]["file"]).read_text(
            encoding="utf-8"
        )
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
        routing = text.split("## Workflow integration\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("Read exactly one", routing)
        self.assertIn("apply its Entry before analysis", routing)
        self.assertIn("If more than one orchestrator is active, ask the user to choose one", routing)
        for name, adapter in ADAPTERS.items():
            self.assertEqual(routing.count(f"| `{name}` |"), 1)
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

    def test_skill_entrypoint_stays_below_five_hundred_words(self):
        words = SKILL_PATH.read_text(encoding="utf-8").split()
        self.assertLess(len(words), 500)


if __name__ == "__main__":
    unittest.main()
