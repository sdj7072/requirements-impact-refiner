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


@unittest.skipUnless(
    EVIDENCE_ROOT.exists(),
    "raw evaluation evidence lives on the evidence-v031 branch",
)
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

    def test_final_report_discloses_raw_whitespace_exception(self):
        text = REPORT.read_text(encoding="utf-8")
        for required in (
            "Full `git diff --check 3e4476d..366508e` reports exactly four intentional EOF blank-line findings",
            "integration-raw/initial/INT-generic-3.md:67",
            "integration-raw/initial/INT-generic-4.md:66",
            "integration-raw/initial/INT-spec-kit-2.md:75",
            "integration-raw/rerun-1/NEG-brainstorming-2.md:67",
            "excluded solely to preserve the raw evidence bytes",
            "The non-raw portion of that diff check passes.",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
