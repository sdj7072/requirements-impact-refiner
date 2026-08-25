import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "evals" / "results" / "with-skill.md"
STATE_MACHINE_V03 = ROOT / "evals" / "results" / "state-machine-v0.3.md"
EVIDENCE_ROOT = ROOT / "evals" / "results" / "compatibility-raw"
EXPECTED_COUNTS = {
    "initial": 44,
    "rerun-1": 7,
    "rerun-2": 6,
    "rerun-3": 4,
    "scoring/initial": 2,
    "scoring/rerun-final": 2,
}
EVIDENCE_MANIFEST_SHA256 = (
    "2f7922729059b3dcb9c1d527706dfcde22559e962f489be8f062e50a695c0ffa"
)


def evidence_manifest() -> str:
    rows = []
    for path in sorted(candidate for candidate in EVIDENCE_ROOT.rglob("*") if candidate.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{path.relative_to(EVIDENCE_ROOT).as_posix()} {digest}")
    return "\n".join(rows) + "\n"


@unittest.skipUnless(
    EVIDENCE_ROOT.exists(),
    "raw evaluation evidence lives on the evidence-v031 branch",
)
class ReleaseCompatibilityEvidenceTest(unittest.TestCase):
    def test_v03_state_machine_ledger_is_bounded_and_auditable(self):
        text = STATE_MACHINE_V03.read_text(encoding="utf-8")
        self.assertIn(
            "| Case | Client/model | Repetitions | Report ID preserved | Revision/hash valid | Expected Delta | Unsupported claim rejected | Result |",
            text,
        )
        for case_id in (
            "LINEAGE-stable-blocked",
            "LINEAGE-reopened",
            "LINEAGE-no-false-resolution",
        ):
            self.assertIn(case_id, text)
        for required in (
            "one repetition",
            "not verified",
            "104/104",
            "111/111",
            "PyYAML",
            "no raw transcripts committed",
            "Exact post-change prompts and decisive output excerpts",
            "initial stable-blocked dispatcher prompt was not preserved",
            "Delta treatment is `reopened`",
            "Unsupported resolution is rejected",
        ):
            self.assertIn(required, text)

    def test_controller_corpus_is_complete_and_byte_preserved(self):
        for directory, expected_count in EXPECTED_COUNTS.items():
            self.assertEqual(
                len([path for path in (EVIDENCE_ROOT / directory).rglob("*") if path.is_file()]),
                expected_count,
                directory,
            )
        self.assertEqual(
            sum(EXPECTED_COUNTS.values()),
            len([path for path in EVIDENCE_ROOT.rglob("*") if path.is_file()]),
        )
        self.assertEqual(
            hashlib.sha256(evidence_manifest().encode()).hexdigest(),
            EVIDENCE_MANIFEST_SHA256,
        )

    def test_git_attributes_preserve_release_evidence_bytes(self):
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("evals/results/compatibility-raw/** -text", attributes)

    def test_report_records_strict_results_without_support_claim(self):
        text = REPORT.read_text(encoding="utf-8")
        for required in (
            "Codex standalone",
            "7/17",
            "0/8",
            "3/5",
            "Codex with Superpowers",
            "10/17",
            "1/8",
            "5/5",
            "4/4",
            "24/24",
            "one repetition",
            "not verified",
            "15 intentional raw whitespace findings",
            "The compatibility-raw subtree is excluded only from the whitespace gate",
            EVIDENCE_MANIFEST_SHA256,
        ):
            self.assertIn(required, text)
        self.assertIn("no skill or adapter wording changed", text.casefold())
        self.assertNotIn("Codex standalone | supported", text)
        self.assertNotIn("Codex with Superpowers | supported", text)


if __name__ == "__main__":
    unittest.main()
