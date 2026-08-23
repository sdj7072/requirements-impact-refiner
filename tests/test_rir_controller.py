import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CONTROLLER = load_module("rir_controller", SCRIPTS / "rir_controller.py")


class RirControllerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def request(self, **changes):
        values = {
            "repo_root": self.root,
            "request": "Let workspace members edit every project.",
            "repository_evidence": (
                "authorizeProjectEdit permits owner and admin",
                "workspace invitations default to member",
            ),
            "adapter": "generic",
        }
        values.update(changes)
        return CONTROLLER.BeginRequest(**values)

    def finalize(self, draft, analysis):
        return CONTROLLER.FinalizeRequest(
            repo_root=self.root,
            draft_id=draft.draft_id,
            analysis=analysis,
        )

    def fixture(self, name):
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def test_begin_creates_repository_bound_private_draft(self):
        result = CONTROLLER.begin_refinement(self.request())

        self.assertRegex(result.draft_id, r"^[0-9a-f]{32}$")
        self.assertEqual(result.report_id, "RPT-001")
        self.assertEqual(result.revision, 1)
        self.assertEqual(result.previous_sha256, "none")
        self.assertEqual(result.settings["delivery"], "compact")
        self.assertEqual(result.draft_path.stat().st_mode & 0o777, 0o600)
        stored = json.loads(result.draft_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["repo_root"], str(self.root.resolve()))
        self.assertFalse(stored["consumed"])

    def test_begin_rejects_oversized_request_and_non_directory_root(self):
        with self.assertRaisesRegex(ValueError, "256 KiB"):
            CONTROLLER.begin_refinement(
                self.request(request="x" * (256 * 1024 + 1))
            )
        file_root = self.root / "file"
        file_root.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "repository root"):
            CONTROLLER.begin_refinement(self.request(repo_root=file_root))

    def test_predecision_finalize_allocates_ids_and_embeds_question(self):
        draft = CONTROLLER.begin_refinement(self.request())
        result = CONTROLLER.finalize_refinement(
            self.finalize(
                draft, self.fixture("controller-analysis-pre-decision.json")
            )
        )

        self.assertEqual(result.status, "published")
        self.assertIn("IMP-001", result.display_text)
        self.assertIn("Decision needed", result.display_text)
        self.assertEqual(result.revision, 1)
        self.assertTrue(result.state_path.is_file())
        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["impacts"][0]["id"], "IMP-001")
        self.assertEqual(state["criteria"][0]["id"], "AC-001")
        self.assertEqual(state["current_behavior"][0]["id"], "INV-001")

    def test_postdecision_finalize_allocates_decision_and_consumes_draft(self):
        draft = CONTROLLER.begin_refinement(self.request())
        result = CONTROLLER.finalize_refinement(
            self.finalize(
                draft, self.fixture("controller-analysis-post-decision.json")
            )
        )

        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["decisions"][0]["id"], "DEC-001")
        self.assertEqual(state["impacts"][0]["decisions"], ["DEC-001"])
        stored = json.loads(draft.draft_path.read_text(encoding="utf-8"))
        self.assertTrue(stored["consumed"])
        with self.assertRaisesRegex(ValueError, "consumed"):
            CONTROLLER.finalize_refinement(
                self.finalize(
                    draft, self.fixture("controller-analysis-post-decision.json")
                )
            )

    def test_finalize_calculates_delta_and_rejects_model_ids(self):
        draft = CONTROLLER.begin_refinement(self.request())
        analysis = self.fixture("controller-analysis-post-decision.json")
        analysis["impacts"][0]["id"] = "IMP-999"

        with self.assertRaisesRegex(ValueError, "unknown impact key id"):
            CONTROLLER.finalize_refinement(self.finalize(draft, analysis))

    def test_finalize_rejects_wrong_root_unknown_draft_and_oversized_input(self):
        draft = CONTROLLER.begin_refinement(self.request())
        other = self.root / "other"
        other.mkdir()
        request = CONTROLLER.FinalizeRequest(
            repo_root=other,
            draft_id=draft.draft_id,
            analysis=self.fixture("controller-analysis-pre-decision.json"),
        )
        with self.assertRaisesRegex(ValueError, "draft"):
            CONTROLLER.finalize_refinement(request)
        with self.assertRaisesRegex(ValueError, "draft ID"):
            CONTROLLER.load_draft(self.root, "not-a-draft")
        huge = self.fixture("controller-analysis-pre-decision.json")
        huge["refined_requirement"] = "x" * (2 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "2 MiB"):
            CONTROLLER.finalize_refinement(self.finalize(draft, huge))

    def test_revision_preserves_ids_hashes_predecessor_and_calculates_reopened(self):
        first_draft = CONTROLLER.begin_refinement(self.request())
        first = CONTROLLER.finalize_refinement(
            self.finalize(
                first_draft,
                self.fixture("controller-analysis-post-decision.json"),
            )
        )
        second_draft = CONTROLLER.begin_refinement(self.request())
        analysis = self.fixture("controller-analysis-post-decision.json")
        analysis["impacts"][0]["state"] = "detected"
        analysis["impacts"][0]["decision_keys"] = []
        analysis["decisions"][0]["accepted_impact_keys"] = []

        second = CONTROLLER.finalize_refinement(
            self.finalize(second_draft, analysis)
        )
        state = json.loads(second.state_path.read_text(encoding="utf-8"))

        self.assertEqual(second_draft.report_id, "RPT-001")
        self.assertEqual(second_draft.revision, 2)
        self.assertEqual(second_draft.previous_sha256, first.markdown_sha256)
        self.assertEqual(state["impacts"][0]["id"], "IMP-001")
        self.assertEqual(state["delta"]["reopened"], ["IMP-001"])
        self.assertEqual(state["delta"]["new"], [])

    def test_revision_rejects_silent_impact_key_deletion(self):
        first_draft = CONTROLLER.begin_refinement(self.request())
        CONTROLLER.finalize_refinement(
            self.finalize(
                first_draft,
                self.fixture("controller-analysis-post-decision.json"),
            )
        )
        second_draft = CONTROLLER.begin_refinement(self.request())
        analysis = self.fixture("controller-analysis-post-decision.json")
        analysis["impacts"] = []

        with self.assertRaisesRegex(ValueError, "impact key disappeared"):
            CONTROLLER.finalize_refinement(self.finalize(second_draft, analysis))


if __name__ == "__main__":
    unittest.main()
