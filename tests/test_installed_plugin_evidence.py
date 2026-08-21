import json
import subprocess
import unittest
import uuid
from pathlib import Path

from evals.harness.evidence import find_potential_secrets, verify_manifest


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "evals" / "results" / "installed-v0.3"
RAW_ROOT = RESULT_ROOT / "raw"

SMOKE_CASE_IDS = {
    "POS-authorization",
    "NEG-debugging",
    "INT-superpowers",
    "LINEAGE-stable-blocked",
    "LINEAGE-reopened",
    "LINEAGE-no-false-resolution",
}
LINEAGE_CASE_IDS = {
    "LINEAGE-stable-blocked",
    "LINEAGE-reopened",
    "LINEAGE-no-false-resolution",
}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class InstalledPluginEvidenceTest(unittest.TestCase):
    def test_smoke_evidence_is_sealed_safe_and_byte_preserved(self):
        """Catch a modified transcript, manifest, or Git conversion of sealed raw smoke evidence."""
        manifest = (RESULT_ROOT / "manifest.sha256").read_text(encoding="utf-8")
        self.assertEqual(verify_manifest(RESULT_ROOT, manifest), [])

        findings = {}
        for path in RESULT_ROOT.rglob("*"):
            if path.is_file():
                detected = find_potential_secrets(
                    path.read_text(encoding="utf-8", errors="replace")
                )
                if detected:
                    findings[path.relative_to(RESULT_ROOT).as_posix()] = detected
        self.assertEqual(findings, {})

        raw_paths = sorted(
            path.relative_to(ROOT).as_posix()
            for path in RAW_ROOT.rglob("*")
            if path.is_file()
        )
        checked = subprocess.run(
            ["git", "check-attr", "text", "whitespace", "--stdin"],
            cwd=ROOT,
            input="\n".join(raw_paths) + "\n",
            text=True,
            capture_output=True,
            check=True,
        )
        attributes = {}
        for line in checked.stdout.splitlines():
            path, attribute, value = line.rsplit(": ", 2)
            attributes.setdefault(path, {})[attribute] = value
        self.assertEqual(set(attributes), set(raw_paths))
        for path in raw_paths:
            self.assertEqual(attributes[path]["text"], "unset", path)
            self.assertEqual(attributes[path]["whitespace"], "unset", path)

    def test_smoke_inventory_identity_retries_sessions_and_bounded_score(self):
        """Catch promotion or selection drift in the approved six-case smoke checkpoint."""
        controller = load_json(RESULT_ROOT / "controller.json")
        probes = load_json(RESULT_ROOT / "probes.json")["probes"]
        probe_by_client = {row["client"]: row["probe"] for row in probes}

        self.assertEqual(set(probe_by_client), {"codex", "claude"})
        self.assertEqual(probe_by_client["codex"]["version"], "codex-cli 0.148.0-alpha.21")
        self.assertEqual(probe_by_client["claude"]["version"], "2.1.228 (Claude Code)")
        self.assertEqual(probe_by_client["codex"]["plugin_version"], "0.3.0")
        self.assertEqual(probe_by_client["claude"]["plugin_version"], "0.3.0")
        self.assertIn(
            "superpowers@openai-curated", probe_by_client["codex"]["enabled_plugins"]
        )

        identity = controller["identity"]
        self.assertEqual(controller["suite"], "smoke")
        self.assertEqual(controller["repetitions"], 1)
        self.assertEqual(identity["model"], "gpt-5.6-sol")
        self.assertEqual(identity["reasoning"], "high")
        self.assertEqual(identity["plugin_version"], "0.3.0")
        self.assertIn("superpowers@openai-curated", identity["enabled_plugins"])

        selected = controller["runs"]
        selected_ids = {(row["case_id"], row["repetition"]) for row in selected}
        self.assertEqual(selected_ids, {(case_id, 1) for case_id in SMOKE_CASE_IDS})
        self.assertEqual(len(selected), 6)
        self.assertTrue(all(row["result"]["status"] == "pass" for row in selected))

        attempts = controller["attempts"]
        self.assertEqual(len(attempts), 7)
        integration_attempts = [
            row for row in attempts if row["case_id"] == "INT-superpowers"
        ]
        self.assertEqual(
            [(row["attempt"], row["result"]["status"]) for row in integration_attempts],
            [(1, "infra_error"), (2, "pass")],
        )
        self.assertTrue(integration_attempts[0]["result"]["command"]["timed_out"])
        self.assertEqual(integration_attempts[1]["result"]["retry_of"], "INT-superpowers/01")
        self.assertEqual(
            next(row for row in selected if row["case_id"] == "INT-superpowers")[
                "selected_attempt"
            ],
            2,
        )

        for row in selected:
            session_id = row["result"]["session_id"]
            if row["case_id"] in LINEAGE_CASE_IDS:
                self.assertIsInstance(session_id, str)
                self.assertEqual(str(uuid.UUID(session_id)), session_id)
            else:
                self.assertIsNone(session_id)

        scores = controller["mechanical_scores"]
        self.assertEqual(len(scores), 6)
        self.assertEqual(sum(row["passed"] for row in scores), 1)
        report = (RESULT_ROOT / "report.md").read_text(encoding="utf-8")
        self.assertIn("- status: not verified", report)
        self.assertIn("- strict score: 1/6", report)


if __name__ == "__main__":
    unittest.main()
