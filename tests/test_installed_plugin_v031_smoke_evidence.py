import hashlib
import json
import re
import subprocess
import unittest
import uuid
from pathlib import Path

from evals.harness.catalog import load_all, select_suite
from evals.harness.evidence import find_potential_secrets, verify_manifest
from evals.harness.scoring import _planning_handoff_workflow


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "evals" / "results" / "installed-v0.3.1"
RAW_ROOT = RESULT_ROOT / "raw"

EXPECTED_MANIFEST_SHA256 = (
    "fe4ab995cee882e95df1fe1c6e07542512cd216aaa44d47809fdd0252add05da"
)
FINAL_CASE_IDS = tuple(
    case.id for case in select_suite(load_all(), "installed-superpowers")
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
    "requirements-impact-refiner@requirements-impact-refiner-v031-eval",
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


def raw_path(case_id, repetition, turn):
    return RAW_ROOT / "codex" / case_id / f"{repetition:02d}" / f"{turn}.jsonl"


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

    def test_final_batch_provenance_and_runtime_inventory_are_exact(self):
        """Catch a client, model, alias, selection, or retry-history regression."""
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
        self.assertEqual(probes["claude"]["version"], "2.1.228 (Claude Code)")
        self.assertEqual(probes["claude"]["plugin_version"], "0.3.1")
        self.assertEqual(
            tuple(probes["claude"]["enabled_plugins"]),
            ("requirements-impact-refiner@requirements-impact-refiner",),
        )

        identity = controller["identity"]
        self.assertEqual(controller["suite"], "installed-superpowers")
        self.assertEqual(controller["repetitions"], 5)
        self.assertEqual(identity["version"], "codex-cli 0.148.0-alpha.21")
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
        expected_keys = {(case_id, repetition) for case_id in FINAL_CASE_IDS for repetition in range(1, 6)}
        self.assertEqual(len(FINAL_CASE_IDS), 17)
        self.assertEqual(len(selected), 85)
        self.assertEqual(
            {(row["case_id"], row["repetition"]) for row in selected},
            expected_keys,
        )
        self.assertTrue(all(row["selected_attempt"] == 1 for row in selected))
        self.assertTrue(all(row["result"]["status"] == "pass" for row in selected))

        attempts = controller["attempts"]
        self.assertEqual(len(attempts), 85)
        self.assertEqual(
            {(row["case_id"], row["repetition"]) for row in attempts},
            expected_keys,
        )
        for attempt in attempts:
            result = attempt["result"]
            self.assertEqual(attempt["attempt"], 1)
            self.assertEqual(result["attempt"], 1)
            self.assertIsNone(attempt["retry_of"])
            self.assertIsNone(result["retry_of"])
            self.assertEqual(result["status"], "pass")
            self.assertFalse(result["command"]["timed_out"])

    def test_mechanical_score_human_adjudication_and_report_preserve_the_one_blocker(self):
        """Catch a false verified claim or a changed sole mechanical failure."""
        controller = load_json(RESULT_ROOT / "controller.json")
        scores = load_json(RESULT_ROOT / "scores.json")
        self.assertEqual(len(scores), 85)
        self.assertEqual(
            {(row["case_id"], row["repetition"]) for row in scores},
            {(case_id, repetition) for case_id in FINAL_CASE_IDS for repetition in range(1, 6)},
        )
        failed = [row for row in scores if not row["passed"]]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["case_id"], "POS-cache")
        self.assertEqual(failed[0]["repetition"], 2)
        self.assertEqual(
            failed[0]["findings"],
            [
                "impact delta references unknown impact IMP-002",
                "malformed table row in Impact Ledger: expected 10 cells, got 9",
                "unknown reference IMP-002",
            ],
        )
        self.assertEqual(controller["mechanical_scores"], scores)

        adjudications = load_json(RESULT_ROOT / "adjudication.json")
        expected_adjudications = {
            (case.id, repetition, rubric)
            for case in select_suite(load_all(), "installed-superpowers")
            for repetition in range(1, 6)
            for rubric in (*case.must_detect, *case.must_not_do)
        }
        self.assertEqual(len(adjudications), 400)
        self.assertEqual(
            {(row["case_id"], row["repetition"], row["rubric"]) for row in adjudications},
            expected_adjudications,
        )
        self.assertTrue(all(row["passed"] for row in adjudications))
        selected_outputs = {
            (row["case_id"], row["repetition"]): row["result"]["final_output"]
            for row in controller["runs"]
        }
        self.assertTrue(
            all(
                row["quote"] and row["quote"] in selected_outputs[(row["case_id"], row["repetition"])]
                for row in adjudications
            )
        )

        report = (RESULT_ROOT / "report.md").read_text(encoding="utf-8")
        for line in (
            "- status: not verified",
            "- strict score: 84/85",
            "- adjudications: 400",
            "- verification blockers: 1",
        ):
            self.assertIn(line, report)
        self.assertNotIn("- status: verified", report)

    def test_lineage_turns_bind_controller_output_sessions_prompts_and_predecessor_bytes(self):
        """Catch a cross-case session, resume prompt, raw-final, or byte-lineage swap."""
        controller = load_json(RESULT_ROOT / "controller.json")
        selected = {
            (row["case_id"], row["repetition"]): row["result"]
            for row in controller["runs"]
        }
        session_ids = []

        for case_id in LINEAGE_CASE_IDS:
            for repetition in range(1, 6):
                result = selected[(case_id, repetition)]
                case_root = RAW_ROOT / "codex" / case_id / f"{repetition:02d}"
                metadata = load_json(case_root / "metadata.json")
                first_final = (case_root / "first.final.txt").read_bytes()
                second_final = (case_root / "second.final.txt").read_text(encoding="utf-8")
                second_prompt = (case_root / "second.prompt.txt").read_text(encoding="utf-8")
                session_id = result["session_id"]

                self.assertEqual(str(uuid.UUID(session_id)), session_id)
                session_ids.append(session_id)
                self.assertEqual(thread_started_ids(raw_path(case_id, repetition, "first")), (session_id,))
                self.assertEqual(thread_started_ids(raw_path(case_id, repetition, "second")), (session_id,))
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
        selected = {
            (row["case_id"], row["repetition"]): row["result"]
            for row in controller["runs"]
        }
        for case_id in set(FINAL_CASE_IDS) - set(LINEAGE_CASE_IDS):
            for repetition in range(1, 6):
                raw_final = (
                    RAW_ROOT / "codex" / case_id / f"{repetition:02d}" / "first.final.txt"
                ).read_text(encoding="utf-8")
                self.assertEqual(selected[(case_id, repetition)]["final_output"], raw_final)
        for repetition in range(1, 6):
            self.assertEqual(
                _planning_handoff_workflow(selected[("INT-superpowers", repetition)]["final_output"]),
                SUPERPOWERS_HANDOFF_MARKER,
            )


if __name__ == "__main__":
    unittest.main()
