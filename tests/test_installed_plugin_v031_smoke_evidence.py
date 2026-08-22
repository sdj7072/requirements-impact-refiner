import hashlib
import json
import re
import subprocess
import unittest
import uuid
from pathlib import Path

from evals.harness.evidence import find_potential_secrets, verify_manifest
from evals.harness.scoring import _planning_handoff_workflow


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "evals" / "results" / "installed-v0.3.1"
RAW_ROOT = RESULT_ROOT / "raw"

EXPECTED_MANIFEST_SHA256 = (
    "57384994fda74ce7e566ce79d3a03e408121e837d7ed97759cf621188a574c5e"
)
SMOKE_CASE_IDS = frozenset(
    (
        "POS-authorization",
        "NEG-debugging",
        "INT-superpowers",
        "LINEAGE-stable-blocked",
        "LINEAGE-reopened",
        "LINEAGE-no-false-resolution",
    )
)
LINEAGE_CASE_IDS = (
    "LINEAGE-stable-blocked",
    "LINEAGE-reopened",
    "LINEAGE-no-false-resolution",
)
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
SUPERPOWERS_HANDOFF_MARKER = (
    "superpowers:after-approved-brainstorming;impact-refinement;"
    "manual-handoff-before-writing-plans"
)
PREDECESSOR_ARTIFACT_NOTE = (
    "The exact predecessor report bytes are available in `first.final.txt` "
    "in the current working directory."
)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def raw_path(case_id, turn):
    return RAW_ROOT / "codex" / case_id / "01" / f"{turn}.jsonl"


def thread_started_ids(path):
    return tuple(
        event["thread_id"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for event in (json.loads(line),)
        if event.get("type") == "thread.started"
    )


def report_previous_sha(report):
    match = re.search(
        r"^\|\s*`RPT-001`\s*\|\s*2\s*\|\s*`?([0-9a-f]{64})`?\s*\|",
        report,
        re.MULTILINE,
    )
    if match is None:
        raise AssertionError("Revision 2 Report State row is missing")
    return match.group(1)


class InstalledPluginV031SmokeEvidenceTest(unittest.TestCase):
    def test_manifest_and_raw_transcripts_are_sealed_safe_and_byte_preserved(self):
        """Pin all final v0.3.1 bytes, including Git's raw-transcript treatment."""
        manifest = (RESULT_ROOT / "manifest.sha256").read_text(encoding="utf-8")
        self.assertEqual(
            hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
            EXPECTED_MANIFEST_SHA256,
        )
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

    def test_final_smoke_provenance_and_runtime_inventory_are_exact(self):
        """Catch changes to client composition, model, selection, or retry history."""
        controller = load_json(RESULT_ROOT / "controller.json")
        probes = {
            row["client"]: row["probe"]
            for row in load_json(RESULT_ROOT / "probes.json")["probes"]
        }

        self.assertEqual(set(probes), {"codex", "claude"})
        for client in ("codex", "claude"):
            self.assertTrue(probes[client]["available"])
            self.assertEqual(probes[client]["plugin_version"], "0.3.1")
        self.assertIn("superpowers@openai-curated", probes["codex"]["enabled_plugins"])
        self.assertIn(
            "requirements-impact-refiner@requirements-impact-refiner",
            probes["codex"]["enabled_plugins"],
        )

        identity = controller["identity"]
        self.assertEqual(controller["suite"], "smoke")
        self.assertEqual(controller["repetitions"], 1)
        self.assertEqual(identity["model"], "gpt-5.6-sol")
        self.assertEqual(identity["reasoning"], "high")
        self.assertEqual(identity["plugin_version"], "0.3.1")
        self.assertEqual(
            tuple(identity["enabled_plugins"]), EXPECTED_CODEX_ENABLED_PLUGINS
        )
        self.assertEqual(
            tuple(sorted(probes["codex"]["enabled_plugins"])),
            EXPECTED_CODEX_ENABLED_PLUGINS,
        )
        self.assertEqual(
            identity["enabled_composition"],
            "codex %s plugins=%s"
            % (identity["version"], ",".join(EXPECTED_CODEX_ENABLED_PLUGINS)),
        )

        selected = controller["runs"]
        self.assertEqual(len(selected), 6)
        self.assertEqual(
            {(row["case_id"], row["repetition"]) for row in selected},
            {(case_id, 1) for case_id in SMOKE_CASE_IDS},
        )
        self.assertTrue(all(row["selected_attempt"] == 1 for row in selected))
        self.assertTrue(all(row["result"]["status"] == "pass" for row in selected))

        attempts = controller["attempts"]
        self.assertEqual(len(attempts), 6)
        self.assertEqual(
            {(row["case_id"], row["repetition"]) for row in attempts},
            {(case_id, 1) for case_id in SMOKE_CASE_IDS},
        )
        for attempt in attempts:
            result = attempt["result"]
            self.assertEqual(attempt["attempt"], 1)
            self.assertEqual(result["attempt"], 1)
            self.assertIsNone(attempt["retry_of"])
            self.assertIsNone(result["retry_of"])
            self.assertEqual(result["status"], "pass")
            self.assertFalse(result["command"]["timed_out"])

    def test_mechanical_score_report_and_required_human_adjudication_boundary(self):
        """Pin 6/6 deterministic success without promoting absent human review."""
        controller = load_json(RESULT_ROOT / "controller.json")
        scores = controller["mechanical_scores"]
        self.assertEqual(len(scores), 6)
        self.assertEqual(
            {(row["case_id"], row["repetition"]) for row in scores},
            {(case_id, 1) for case_id in SMOKE_CASE_IDS},
        )
        self.assertTrue(all(row["passed"] and not row["findings"] for row in scores))

        report = (RESULT_ROOT / "report.md").read_text(encoding="utf-8")
        for line in (
            "- status: not verified",
            "- strict score: 6/6",
            "- adjudications: 0",
            "- verification blockers: 4",
        ):
            self.assertIn(line, report)
        self.assertNotIn("- status: verified", report)
        self.assertEqual(controller.get("adjudications", []), [])

    def test_lineage_turns_bind_controller_output_sessions_prompts_and_predecessor_bytes(self):
        """Catch a cross-case session, resume prompt, raw-final, or byte-lineage swap."""
        controller = load_json(RESULT_ROOT / "controller.json")
        selected = {row["case_id"]: row["result"] for row in controller["runs"]}
        session_ids = []

        for case_id in LINEAGE_CASE_IDS:
            result = selected[case_id]
            case_root = RAW_ROOT / "codex" / case_id / "01"
            metadata = load_json(case_root / "metadata.json")
            first_final = (case_root / "first.final.txt").read_bytes()
            second_final = (case_root / "second.final.txt").read_text(encoding="utf-8")
            second_prompt = (case_root / "second.prompt.txt").read_text(encoding="utf-8")
            session_id = result["session_id"]

            self.assertEqual(str(uuid.UUID(session_id)), session_id)
            session_ids.append(session_id)
            self.assertEqual(thread_started_ids(raw_path(case_id, "first")), (session_id,))
            self.assertEqual(thread_started_ids(raw_path(case_id, "second")), (session_id,))
            self.assertEqual(result["final_output"], second_final)
            self.assertEqual(report_previous_sha(second_final), hashlib.sha256(first_final).hexdigest())

            resume_argv = metadata["execution_commands"][1]["argv"]
            self.assertEqual(resume_argv[-2], session_id)
            self.assertEqual(resume_argv[-1], second_prompt)
            self.assertEqual(second_prompt.count(PREDECESSOR_ARTIFACT_NOTE), 1)
            self.assertIn("--skip-git-repo-check", resume_argv)

        self.assertEqual(len(session_ids), len(set(session_ids)))

    def test_non_lineage_and_integration_raw_final_bindings_are_exact(self):
        """Catch substitution of a selected final transcript outside lineage cases."""
        controller = load_json(RESULT_ROOT / "controller.json")
        selected = {row["case_id"]: row["result"] for row in controller["runs"]}
        for case_id in SMOKE_CASE_IDS - set(LINEAGE_CASE_IDS):
            raw_final = (
                RAW_ROOT / "codex" / case_id / "01" / "first.final.txt"
            ).read_text(encoding="utf-8")
            self.assertEqual(selected[case_id]["final_output"], raw_final)
        self.assertEqual(
            _planning_handoff_workflow(selected["INT-superpowers"]["final_output"]),
            SUPERPOWERS_HANDOFF_MARKER,
        )


if __name__ == "__main__":
    unittest.main()
