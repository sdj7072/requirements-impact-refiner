import hashlib
import json
import subprocess
import unittest
import uuid
from pathlib import Path

from evals.harness.evidence import find_potential_secrets, verify_manifest
from tests.test_integration_adapters import run_bootstrap_fixture

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
EXPECTED_MANIFEST_SHA256 = "a88f024d2631428555ae9368d1eee883794993913c93ff8ec11fe105caa53d1d"
EXPECTED_LINEAGE_CASE_IDS = (
    "LINEAGE-stable-blocked",
    "LINEAGE-reopened",
    "LINEAGE-no-false-resolution",
)
# Controller provenance is canonicalized in ascending plugin-ID order. The
# observed probe may preserve client order, so it is sorted before exact match.
EXPECTED_CODEX_ENABLED_PLUGINS = (
    "browser@openai-bundled",
    "chrome@openai-bundled",
    "codex-app-tools@openai-bundled",
    "computer-use@openai-bundled",
    "documents@openai-primary-runtime",
    "google-calendar@openai-curated",
    "pdf@openai-primary-runtime",
    "presentations@openai-primary-runtime",
    "requirements-impact-refiner@requirements-impact-refiner",
    "sites@openai-bundled",
    "slack@openai-curated",
    "spreadsheets@openai-primary-runtime",
    "superpowers@openai-curated",
    "template-creator@openai-primary-runtime",
    "visualize@openai-bundled",
)


class InstalledBootstrapBehaviorTest(unittest.TestCase):
    def test_packaged_bootstrap_has_previous_first_status_and_two_turn_routes(self):
        fresh = run_bootstrap_fixture(previous_status="fresh")
        stale = run_bootstrap_fixture(previous_status="stale")
        ambiguous = run_bootstrap_fixture(previous_status="ambiguous")
        detailed = run_bootstrap_fixture(previous_status="stale", followup_reply="yes")

        self.assertEqual(fresh.calls, ("rir_previous",))
        self.assertEqual(stale.calls, ("rir_previous", "rir_scan"))
        self.assertEqual(ambiguous.calls, ("rir_previous",))
        self.assertEqual(
            detailed.calls,
            ("rir_previous", "rir_scan", "rir_begin", "rir_trace_impact", "rir_finalize"),
        )

    def test_root_and_packaged_previous_report_contracts_are_exact_mirrors(self):
        self.assertEqual(
            (ROOT / "references" / "previous-report.md").read_bytes(),
            (
                ROOT
                / "skills"
                / "requirements-impact-refiner"
                / "references"
                / "previous-report.md"
            ).read_bytes(),
        )


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def thread_started_ids(path):
    events = (
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    return tuple(event["thread_id"] for event in events if event.get("type") == "thread.started")


@unittest.skipUnless(
    RAW_ROOT.exists(),
    "raw evaluation evidence lives on the evidence-v031 branch",
)
class InstalledPluginEvidenceTest(unittest.TestCase):
    def test_manifest_digest_pins_the_sealed_inventory_after_regeneration(self):
        """Catch a regenerated manifest even when it matches altered raw files."""
        manifest_bytes = (RESULT_ROOT / "manifest.sha256").read_bytes()
        digest = hashlib.sha256(manifest_bytes).hexdigest()
        self.assertEqual(digest, EXPECTED_MANIFEST_SHA256)
        self.assertNotEqual(
            hashlib.sha256(manifest_bytes + b"regenerated-row\n").hexdigest(),
            EXPECTED_MANIFEST_SHA256,
        )

    def test_lineage_sessions_are_distinct_and_match_both_raw_turns(self):
        """Catch a reused or mismatched persisted UUID across lineage runs."""
        selected = load_json(RESULT_ROOT / "controller.json")["runs"]
        lineage = [row for row in selected if row["case_id"] in LINEAGE_CASE_IDS]
        self.assertEqual(tuple(row["case_id"] for row in lineage), EXPECTED_LINEAGE_CASE_IDS)
        selected_sessions = [row["result"]["session_id"] for row in lineage]
        self.assertEqual(len(selected_sessions), len(set(selected_sessions)))
        for row in lineage:
            selected_session = row["result"]["session_id"]
            for turn in ("first", "second"):
                raw_path = RAW_ROOT / "codex" / row["case_id"] / "01" / (turn + ".jsonl")
                self.assertEqual(thread_started_ids(raw_path), (selected_session,))

    def test_codex_composition_is_exact_and_matches_the_observed_probe(self):
        """Catch a changed enabled-plugin set or an identity/probe provenance mismatch."""
        controller = load_json(RESULT_ROOT / "controller.json")
        identity = controller["identity"]
        probes = load_json(RESULT_ROOT / "probes.json")["probes"]
        codex_probe = next(row["probe"] for row in probes if row["client"] == "codex")
        self.assertEqual(tuple(identity["enabled_plugins"]), EXPECTED_CODEX_ENABLED_PLUGINS)
        self.assertEqual(
            tuple(sorted(codex_probe["enabled_plugins"])),
            EXPECTED_CODEX_ENABLED_PLUGINS,
        )
        self.assertIn(
            "requirements-impact-refiner@requirements-impact-refiner", identity["enabled_plugins"]
        )
        self.assertIn("superpowers@openai-curated", identity["enabled_plugins"])
        self.assertEqual(
            identity["enabled_composition"],
            "codex {} plugins={}".format(
                identity["version"], ",".join(EXPECTED_CODEX_ENABLED_PLUGINS)
            ),
        )

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
            path.relative_to(ROOT).as_posix() for path in RAW_ROOT.rglob("*") if path.is_file()
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
        self.assertIn("superpowers@openai-curated", probe_by_client["codex"]["enabled_plugins"])

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
        integration_attempts = [row for row in attempts if row["case_id"] == "INT-superpowers"]
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
