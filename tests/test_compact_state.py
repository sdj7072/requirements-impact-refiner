import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
MODULE_PATH = (
    ROOT / "skills" / "requirements-impact-refiner" / "scripts" / "compact_state.py"
)
SPEC = importlib.util.spec_from_file_location("compact_state", MODULE_PATH)
COMPACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPACT)


class CompactStateTest(unittest.TestCase):
    def fixture(self, name="compact-state-post-decision.json"):
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def test_complete_pre_and_post_states_are_valid(self):
        for name in (
            "compact-state-pre-decision.json",
            "compact-state-post-decision.json",
        ):
            with self.subTest(name=name):
                self.assertEqual(COMPACT.validate_state(self.fixture(name)), [])

    def test_every_impact_requires_exactly_one_matching_summary(self):
        value = self.fixture()
        value["summary"][0]["severity"] = "low"
        value["summary"].append(copy.deepcopy(value["summary"][0]))

        errors = COMPACT.validate_state(value)

        self.assertIn(
            "summary IMP-001 severity low disagrees with impact critical", errors
        )
        self.assertIn("summary lists IMP-001 more than once", errors)

    def test_phase_rules_reject_predecision_decisions(self):
        value = self.fixture("compact-state-pre-decision.json")
        value["impacts"][0]["decisions"] = ["DEC-001"]
        value["decisions"] = [
            {
                "id": "DEC-001",
                "choice": "Invented choice",
                "requirement": "REQ-001",
                "accepted_impacts": [],
                "rationale": "Not selected by the user.",
            }
        ]

        self.assertIn(
            "pre-decision state forbids decisions", COMPACT.validate_state(value)
        )

    def test_structure_rejects_unknown_and_missing_keys(self):
        value = self.fixture()
        value["surprise"] = True
        del value["scope"]

        errors = COMPACT.validate_state(value)

        self.assertIn("unknown top-level key surprise", errors)
        self.assertIn("missing top-level key scope", errors)

    def test_relationships_reject_unknown_ids(self):
        value = self.fixture()
        value["impacts"][0]["criteria"] = ["AC-999"]

        self.assertIn(
            "impact IMP-001 references unknown criterion AC-999",
            COMPACT.validate_state(value),
        )

    def test_delta_requires_every_impact_exactly_once(self):
        value = self.fixture()
        value["delta"]["accepted"] = ["IMP-001"]

        self.assertIn(
            "delta lists IMP-001 more than once", COMPACT.validate_state(value)
        )

    def test_accepted_impact_requires_a_decision(self):
        value = self.fixture()
        value["impacts"][0]["decisions"] = []

        self.assertIn(
            "accepted impact IMP-001 requires a decision",
            COMPACT.validate_state(value),
        )

    def test_blocked_impact_requires_one_matching_unresolved_row(self):
        value = self.fixture("compact-state-pre-decision.json")
        value["impacts"][0]["state"] = "blocked"
        value["summary"][0]["status"] = "blocked"
        value["delta"]["new"] = []
        value["delta"]["blocked"] = ["IMP-001"]

        self.assertIn(
            "blocked impact IMP-001 is missing from unresolved items",
            COMPACT.validate_state(value),
        )

    def test_evidence_requires_more_than_a_future_acceptance_target(self):
        value = self.fixture()
        value["current_behavior"][0]["evidence"] = "AC-001"

        self.assertIn(
            "invariant INV-001 verified evidence requires a current basis",
            COMPACT.validate_state(value),
        )

    def test_load_state_bytes_rejects_non_utf8_and_non_object(self):
        value, errors = COMPACT.load_state_bytes(b"\xff")
        self.assertIsNone(value)
        self.assertIn("state must be UTF-8", errors)

        value, errors = COMPACT.load_state_bytes(b"[]")
        self.assertIsNone(value)
        self.assertIn("state must contain a JSON object", errors)

    def test_decision_and_option_relationships_are_substantive(self):
        post = self.fixture()
        post["decisions"][0]["rationale"] = ""
        self.assertIn(
            "decision DEC-001 requires choice and rationale",
            COMPACT.validate_state(post),
        )

        pre = self.fixture("compact-state-pre-decision.json")
        pre["decision_needed"]["options"][0]["impacts"] = ["IMP-999"]
        self.assertIn(
            "decision option references unknown impact IMP-999",
            COMPACT.validate_state(pre),
        )

    def test_scope_and_handoff_must_remain_substantive_and_reconciled(self):
        value = self.fixture()
        value["scope"][0]["confidence"] = ""
        value["handoff"]["remaining_risks"] = []

        errors = COMPACT.validate_state(value)

        self.assertIn("scope row requires boundary, evidence, and confidence", errors)
        self.assertIn("handoff remaining risks must name accepted impact IMP-001", errors)


if __name__ == "__main__":
    unittest.main()
