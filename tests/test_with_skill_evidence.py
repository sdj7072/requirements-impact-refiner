import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "evals" / "results" / "with-skill.md"
EVIDENCE_ROOT = ROOT / "evals" / "results" / "with-skill-raw"
EXPECTED_COUNTS = {
    "initial": 25,
    "rerun-1": 15,
    "rerun-2": 10,
    "rerun-3": 10,
    "rerun-4": 10,
    "rerun-5": 10,
    "scoring": 6,
}
EVIDENCE_MANIFEST_SHA256 = (
    "6fe00ab7e7ea3c9158c987094c77690efe673a692ab73a3945807b6ae7dde842"
)


def evidence_manifest() -> str:
    rows = []
    for path in sorted(EVIDENCE_ROOT.rglob("*.md")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{path.relative_to(EVIDENCE_ROOT).as_posix()} {digest}")
    return "\n".join(rows) + "\n"


class WithSkillEvidenceTest(unittest.TestCase):
    def test_canonical_evidence_inventory_and_checksums(self):
        for directory, expected_count in EXPECTED_COUNTS.items():
            self.assertEqual(
                len(list((EVIDENCE_ROOT / directory).glob("*.md"))),
                expected_count,
                directory,
            )
        self.assertEqual(
            hashlib.sha256(evidence_manifest().encode()).hexdigest(),
            EVIDENCE_MANIFEST_SHA256,
        )

    def test_final_report_records_adjudicated_limit(self):
        text = REPORT.read_text(encoding="utf-8")
        for required in (
            "24/25",
            "POS-payments-5",
            "Known limitation",
            "gpt-5.6-luna",
            "codex-cli 0.148.0-alpha.15",
            "Hosted model/runtime version | Unavailable",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
