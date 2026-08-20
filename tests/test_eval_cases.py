import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "cases.json"
REQUIRED_KEYS = {
    "id",
    "kind",
    "request",
    "repository_evidence",
    "must_detect",
    "must_not_do",
    "modes",
}
ALLOWED_KINDS = {"positive", "negative", "integration"}
REQUIRED_POSITIVE_TOPICS = {
    "authorization",
    "deletion",
    "api-contract",
    "cache",
    "payments",
    "sharing",
    "offline-sync",
    "background-retry",
}
# Canonical SHA-256 of the approved Task 1 case set. Update deliberately only
# when the evaluation contract changes through its review process.
CASES_SHA256 = "03dbedb66900e89efec45fae7d73312fe2ccb6508a67e9143af3e3c88c1c53bc"


def load_cases():
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


class EvalCaseContractTest(unittest.TestCase):
    def test_cases_match_the_approved_golden_contract(self):
        digest = hashlib.sha256(CASES_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, CASES_SHA256)

    def test_cases_have_unique_ids_and_required_fields(self):
        cases = load_cases()
        self.assertEqual(len(cases), len({case["id"] for case in cases}))
        for case in cases:
            self.assertEqual(set(case), REQUIRED_KEYS)
            self.assertIn(case["kind"], ALLOWED_KINDS)
            self.assertTrue(case["request"].strip())
            self.assertIsInstance(case["repository_evidence"], list)
            self.assertIsInstance(case["must_detect"], list)
            self.assertIsInstance(case["must_not_do"], list)
            self.assertIsInstance(case["modes"], list)

    def test_positive_cases_cover_the_release_taxonomy(self):
        topics = {
            case["id"].removeprefix("POS-")
            for case in load_cases()
            if case["kind"] == "positive"
        }
        self.assertEqual(topics, REQUIRED_POSITIVE_TOPICS)

    def test_negative_cases_protect_neighboring_workflows(self):
        negative_ids = {
            case["id"] for case in load_cases() if case["kind"] == "negative"
        }
        self.assertEqual(
            negative_ids,
            {
                "NEG-brainstorming",
                "NEG-planning",
                "NEG-debugging",
                "NEG-code-review",
                "NEG-generic-prd",
            },
        )

    def test_integration_cases_cover_formal_adapters(self):
        modes = {
            mode
            for case in load_cases()
            if case["kind"] == "integration"
            for mode in case["modes"]
        }
        self.assertEqual(
            modes,
            {"generic", "superpowers", "claude-feature-dev", "spec-kit"},
        )


if __name__ == "__main__":
    unittest.main()
