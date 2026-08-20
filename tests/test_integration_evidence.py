import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "evals" / "results" / "with-skill.md"
EVIDENCE_ROOT = ROOT / "evals" / "results" / "integration-raw"
EXPECTED_COUNTS = {
    "baseline": 4,
    "initial": 30,
    "rerun-1": 15,
    "scoring": 3,
}
EVIDENCE_MANIFEST_SHA256 = (
    "9740064ebd3eb60cae7d95917db99195e765dd84c28d600303c1c6cc0ebbf1fc"
)


def evidence_manifest() -> str:
    rows = []
    for path in sorted(EVIDENCE_ROOT.rglob("*.md")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{path.relative_to(EVIDENCE_ROOT).as_posix()} {digest}")
    return "\n".join(rows) + "\n"


class IntegrationEvidenceTest(unittest.TestCase):
    def test_canonical_integration_inventory_and_checksums(self):
        for directory, expected_count in EXPECTED_COUNTS.items():
            self.assertEqual(
                len(list((EVIDENCE_ROOT / directory).glob("*.md"))),
                expected_count,
                directory,
            )
        self.assertEqual(
            sum(EXPECTED_COUNTS.values()),
            len(list(EVIDENCE_ROOT.rglob("*.md"))),
        )
        self.assertEqual(
            hashlib.sha256(evidence_manifest().encode()).hexdigest(),
            EVIDENCE_MANIFEST_SHA256,
        )

    def test_git_attributes_preserve_integration_evidence_bytes(self):
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("evals/results/integration-raw/** -text", attributes)

    def test_final_report_records_integration_progression_and_environment(self):
        text = REPORT.read_text(encoding="utf-8")
        for required in (
            "2/4",
            "25/30",
            "15/15",
            "30/30",
            "gpt-5.6-luna",
            "codex-cli 0.148.0-alpha.15",
            "Hosted model/runtime version | Unavailable",
            "integration-raw",
            EVIDENCE_MANIFEST_SHA256,
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
