import hashlib
import json
import os
import re
import subprocess
import unittest
import uuid
from pathlib import Path

from evals.harness.catalog import load_all, select_suite
from evals.harness.evidence import find_potential_secrets, verify_manifest
from evals.harness.models import Adjudication, MechanicalScore, RunResult, RunStatus
from evals.harness.reporting import render_report
from evals.harness.scoring import _planning_handoff_workflow, validate_adjudications


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "evals" / "results" / "installed-v0.3.1"
RAW_ROOT = RESULT_ROOT / "raw"
INSTALLED_PAYLOAD = RESULT_ROOT / "installed-payload.json"
INSTALLED_CACHE_ROOT = Path(
    "/Users/p042890/.codex/plugins/cache/requirements-impact-refiner-v031-eval/"
    "requirements-impact-refiner/0.3.1"
)
PAYLOAD_SOURCE = "/private/tmp/rir-v031-eval-marketplace"
PAYLOAD_ALIAS = "requirements-impact-refiner@requirements-impact-refiner-v031-eval"
CANONICAL_RELEASE_COMMIT = "d92ad185ebbb722cd30fc0c720a86e411bec3462"

EXPECTED_MANIFEST_SHA256 = (
    "8e195a0cd5584dd56980917ae97ca284e8ef1653570742bdb1838079ec99d88d"
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


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_functional_payload_file(path):
    """Exclude interpreter caches created while the test suite is running."""
    return (
        path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    )


def functional_payload_inventory(root):
    """Return the declared functional plugin payload, never its alias wrapper."""
    root = Path(root)
    paths = set()
    for directory in (".codex-plugin", "skills", "references", "assets"):
        paths.update(
            path
            for path in (root / directory).rglob("*")
            if is_functional_payload_file(path)
        )
    paths.add(root / ".claude-plugin" / "plugin.json")
    for name in ("install-agent-skill.py", "impact_report.py", "validate-impact-report.py"):
        paths.add(root / "scripts" / name)
    return [
        {"path": path.relative_to(root).as_posix(), "sha256": sha256(path)}
        for path in sorted(paths)
    ]


def functional_payload_paths(root):
    return [row["path"] for row in functional_payload_inventory(root)]


def commit_payload_inventory(commit, paths):
    """Read every functional payload byte from the pinned commit, not a host cache."""
    rows = []
    for relative in paths:
        shown = subprocess.run(
            ["git", "show", f"{commit}:{relative}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        rows.append(
            {"path": relative, "sha256": hashlib.sha256(shown.stdout).hexdigest()}
        )
    return rows


def optional_installed_cache_inventory(payload, verify_cache):
    """Read the host cache only after an explicit local verification opt-in."""
    if not verify_cache:
        return None
    cache_root = Path(payload["installed_cache_root"])
    if not cache_root.is_dir():
        raise FileNotFoundError(cache_root)
    return functional_payload_inventory(cache_root)


def inventory_digest(rows):
    return hashlib.sha256(
        "".join(f"{row['path']} {row['sha256']}\n" for row in rows).encode("utf-8")
    ).hexdigest()


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
    def test_functional_payload_ignores_runtime_python_cache_files(self):
        """Running tests must not mutate the declared plugin payload inventory."""
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "skills" / "example" / "scripts" / "tool.py"
            cache = source.parent / "__pycache__" / "tool.cpython-311.pyc"
            source.parent.mkdir(parents=True)
            cache.parent.mkdir()
            source.write_bytes(b"source")
            cache.write_bytes(b"generated")

            self.assertTrue(is_functional_payload_file(source))
            self.assertFalse(is_functional_payload_file(cache))

    def test_installed_alias_payload_is_sealed_and_matches_the_canonical_release_bytes(self):
        """Catch an alias cache that evaluates different functional bytes than v0.3.1."""
        commit_present = subprocess.run(
            ["git", "cat-file", "-e", f"{CANONICAL_RELEASE_COMMIT}^{{commit}}"],
            cwd=ROOT,
            capture_output=True,
        )
        if commit_present.returncode != 0:
            self.skipTest(
                "canonical release commit unavailable in this clone "
                "(shallow or partial checkout); sealed-byte comparison "
                "requires full history"
            )
        payload = load_json(INSTALLED_PAYLOAD)
        paths = [row["path"] for row in payload["inventory"]]
        basis_inventory = commit_payload_inventory(CANONICAL_RELEASE_COMMIT, paths)

        self.assertEqual(payload["source_type"], "local")
        self.assertEqual(payload["source"], PAYLOAD_SOURCE)
        self.assertEqual(payload["alias_id"], PAYLOAD_ALIAS)
        self.assertEqual(payload["canonical_release"], "0.3.1")
        self.assertEqual(payload["canonical_commit_basis"], CANONICAL_RELEASE_COMMIT)
        self.assertEqual(
            payload["excluded_alias_wrapper"],
            {
                "path": ".agents/plugins/marketplace.json",
                "reason": "top-level marketplace name intentionally differs for isolated local evaluation",
            },
        )
        self.assertEqual(len(paths), 31)
        self.assertEqual(payload["inventory"], basis_inventory)
        self.assertEqual(payload["inventory_sha256"], inventory_digest(basis_inventory))
        self.assertEqual(
            payload["installed_cache_comparison"],
            {"files_compared": 31, "mismatches": []},
        )
        installed_inventory = optional_installed_cache_inventory(
            payload, os.environ.get("RIR_VERIFY_INSTALLED_CACHE") == "1"
        )
        if installed_inventory is not None:
            self.assertEqual(payload["inventory"], installed_inventory)

    def test_installed_cache_verification_is_opt_in_and_portable_when_absent(self):
        """Catch a default test path that reads a developer-local installed cache."""
        payload = {"installed_cache_root": "/definitely-absent-rir-cache"}
        self.assertIsNone(optional_installed_cache_inventory(payload, False))
        with self.assertRaises(FileNotFoundError):
            optional_installed_cache_inventory(payload, True)

    def test_manifest_and_raw_transcripts_are_sealed_safe_and_byte_preserved(self):
        """Pin all final v0.3.1 bytes, including Git's raw-transcript treatment."""
        manifest = (RESULT_ROOT / "manifest.sha256").read_text(encoding="utf-8")
        self.assertEqual(
            hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
            EXPECTED_MANIFEST_SHA256,
        )
        self.assertEqual(verify_manifest(RESULT_ROOT, manifest), [])

        rows = manifest.splitlines()
        for name, mutated in (
            ("reversed", "\n".join(reversed(rows)) + "\n"),
            ("missing-final-newline", manifest[:-1]),
        ):
            with self.subTest(manifest_mutation=name):
                self.assertIn(
                    "manifest is not the canonical sorted POSIX representation",
                    verify_manifest(RESULT_ROOT, mutated),
                )

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
            identity["catalog_sha256"],
            "160db9762d93c70ce89bb4141152fe3dcf4f105ee9ef814f7cd5f4710b2a81dd",
        )
        self.assertEqual(
            identity["harness_sha256"],
            "4eb5e9dd11f07770d961e1c70201ae0ed0aa60dd65b770af0728f274972a9ca0",
        )
        self.assertEqual(
            identity["skills_sha256"],
            "ed337f8d828e5476dad94a38b3ad032243c5060e5027d14ecf4f337271ea3d93",
        )
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
        identity = controller["identity"]
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
        self.assertTrue(all(type(row["passed"]) is bool for row in adjudications))
        self.assertTrue(all(row["passed"] for row in adjudications))
        self.assertTrue(all(isinstance(row["quote"], str) and row["quote"].strip() for row in adjudications))
        self.assertTrue(all(isinstance(row["rationale"], str) and row["rationale"].strip() for row in adjudications))
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
        typed_adjudications = tuple(Adjudication(**row) for row in adjudications)
        typed_runs = tuple(
            RunResult(
                case_id=row["case_id"],
                repetition=row["repetition"],
                client=row["result"]["client"],
                status=RunStatus(row["result"]["status"]),
                reason=row["result"]["reason"],
                final_output=row["result"]["final_output"],
                session_id=row["result"]["session_id"],
                metadata=tuple(tuple(pair) for pair in row["result"]["metadata"]),
                attempt=row["result"]["attempt"],
                retry_of=row["result"]["retry_of"],
            )
            for row in controller["runs"]
        )
        self.assertEqual(
            validate_adjudications(
                typed_adjudications,
                select_suite(load_all(), "installed-superpowers"),
                typed_runs,
            ),
            [],
        )

        all_pass_scores = tuple(
            MechanicalScore(row["case_id"], row["repetition"], True, ())
            for row in scores
        )
        legacy_render = render_report(
            typed_runs,
            {
                "client": identity["client"],
                "version": identity["version"],
                "plugin_version": identity["plugin_version"],
                "enabled_composition": identity["enabled_composition"],
                "enabled_plugins": tuple(identity["enabled_plugins"]),
                "model": identity["model"],
                "reasoning": identity["reasoning"],
                "repetitions": controller["repetitions"],
            },
            all_pass_scores,
            typed_adjudications,
        )
        self.assertIn("- status: not verified", legacy_render)

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
