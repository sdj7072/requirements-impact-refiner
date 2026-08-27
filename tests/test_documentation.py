import json
import re
import shlex
import tempfile
import unittest
from pathlib import Path

from evals.harness.catalog import load_all, select_suite
from evals.harness.run import build_parser
from tests.test_integration_adapters import McpBootstrapHarness

ROOT = Path(__file__).resolve().parents[1]
READMES = ["README.md", "README.ko.md", "README.ja.md"]
LANGUAGE_TARGETS = {"README.md", "README.ko.md", "README.ja.md"}
SKILL_ROOT = ROOT / "skills" / "requirements-impact-refiner"
SEALED_V031_EVIDENCE = {
    "release": "0.3.1",
    "composition": "Codex with Superpowers",
    "Codex client": "codex-cli 0.148.0-alpha.21",
    "RIR plugin": "requirements-impact-refiner@requirements-impact-refiner-v031-eval",
    "model / reasoning": "gpt-5.6-sol / high",
    "runtime outcomes": "85/85 pass; 85 attempt 1 selections; no retries",
    "mechanical score": "84/85; one failure: POS-cache repetition 2",
    "adjudication": "400/400 passed; model-scored, quote-bound to sealed outputs, no independent human sign-off",
    "release status": "not verified; one mechanical verification blocker",
    "Claude probe": "2.1.228 (Claude Code) / RIR 0.3.1; structural-only, behavioral compatibility remains blocked",
}
PRE_LIVE_COMPATIBILITY = {
    "Codex standalone behavioral harness": "not verified",
    "Codex with Superpowers": "not verified",
    "Codex skill quick validator": "blocked",
    "Codex plugin validator": "blocked",
    "Claude Code standalone": "blocked",
    "Claude Code with Superpowers": "not verified",
    "Claude Code with `feature-dev`": "blocked",
    "Claude Code with Spec Kit": "blocked",
    "Generic Agent Skills-compatible harness": "blocked",
}


def headings(path):
    text = path.read_text(encoding="utf-8")
    return [
        re.sub(r"^#+\s+", "", line).strip() for line in text.splitlines() if line.startswith("## ")
    ]


def compatibility_identity_rows(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if re.match(r"^## 6\.", line))
    header = next(
        index
        for index in range(start + 1, len(lines))
        if lines[index].startswith("| Environment | Version | Status |")
    )
    rows = []
    for line in lines[header + 2 :]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows.append(tuple(cells[:3]))
    return rows


def markdown_table(path, header):
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index(header)
    rows = {}
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows[cells[0].strip("`")] = cells[1].strip("`")
    return rows


def shell_blocks(path):
    return re.findall(r"```sh\n(.*?)\n```", path.read_text(encoding="utf-8"), re.DOTALL)


def harness_commands(path):
    commands = []
    for block in shell_blocks(path):
        for line in block.splitlines():
            parts = shlex.split(line)
            if parts[:3] == ["python3", "-m", "evals.harness.run"]:
                commands.append(parts[3:])
    return commands


class DocumentationTest(unittest.TestCase):
    def test_release_installs_are_tag_pinned_and_main_is_development_only(self):
        release_add = (
            "codex plugin marketplace add sdj7072/requirements-impact-refiner "
            "--ref requirements-impact-refiner--v0.6.0"
        )
        development_add = (
            "codex plugin marketplace add sdj7072/requirements-impact-refiner --ref main"
        )
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            commands = [line for block in shell_blocks(ROOT / name) for line in block.splitlines()]
            self.assertGreaterEqual(commands.count(release_add), 2, name)
            self.assertEqual(commands.count(development_add), 1, name)
            development_offset = text.index(development_add)
            self.assertIn("development-only", text[development_offset - 300 : development_offset])
            self.assertIn(
                "codex plugin marketplace remove requirements-impact-refiner", commands, name
            )
            claude_release_add = (
                "/plugin marketplace add sdj7072/requirements-impact-refiner"
                "@requirements-impact-refiner--v0.6.0"
            )
            claude_development_add = (
                "/plugin marketplace add sdj7072/requirements-impact-refiner@main"
            )
            self.assertGreaterEqual(text.count(claude_release_add), 2, name)
            self.assertEqual(text.count(claude_development_add), 1, name)
            development_offset = text.index(claude_development_add)
            self.assertIn("development-only", text[development_offset - 300 : development_offset])
            self.assertIn("/plugin marketplace remove requirements-impact-refiner", text, name)
            self.assertNotIn("/plugin marketplace update requirements-impact-refiner", text, name)

    def test_ci_has_separate_runtime_matrix_and_python_313_quality_job(self):
        """Catch CI changes that drop the dedicated pinned-tool quality gate."""
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

        test_job = re.search(r"(?ms)^  test:\n(?P<body>.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", workflow)
        self.assertIsNotNone(test_job, "CI must retain a separate test job")
        self.assertRegex(
            test_job.group("body"),
            r'python-version:\s*\[\s*["\']3\.9["\']\s*,\s*["\']3\.11["\']\s*,\s*["\']3\.13["\']\s*\]',
        )
        self.assertIn("python3 -m unittest discover -s tests -v", test_job.group("body"))
        self.assertIn("python3 -m py_compile scripts/*.py", test_job.group("body"))
        self.assertIn("Check unfinished markers", test_job.group("body"))

        quality_job = re.search(
            r"(?ms)^  quality:\n(?P<body>.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", workflow
        )
        self.assertIsNotNone(quality_job, "CI must keep quality independent from the test matrix")
        self.assertNotIn("matrix:", quality_job.group("body"))
        self.assertNotIn("needs:", quality_job.group("body"))
        self.assertRegex(quality_job.group("body"), r'python-version:\s*["\']3\.13["\']')
        self.assertIn("pip install -r requirements-quality.txt", quality_job.group("body"))
        self.assertIn("python scripts/run-quality-gates.py", quality_job.group("body"))

        provider_job = re.search(
            r"(?ms)^  provider-canary:\n(?P<body>.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)",
            workflow,
        )
        self.assertIsNotNone(provider_job, "CI must run the pinned provider canary independently")
        self.assertNotIn("matrix:", provider_job.group("body"))
        self.assertNotIn("needs:", provider_job.group("body"))
        self.assertRegex(provider_job.group("body"), r'python-version:\s*["\']3\.13["\']')
        self.assertIn("pip install -r requirements-provider-canary.txt", provider_job.group("body"))
        self.assertIn("python scripts/run-ast-grep-canary.py", provider_job.group("body"))
        self.assertNotIn("requirements-quality.txt", provider_job.group("body"))
        self.assertRegex(workflow, r"(?ms)^permissions:\n  contents: read$")

    def test_quality_workflow_is_documented_for_local_python_313(self):
        """Keep the CI and local quality contract usable in every public language."""
        mypy_relations = {
            "README.md": "`mypy==1.18.2` runs in the Python 3.13 quality job while checking Python 3.9 source compatibility.",
            "README.ko.md": "`mypy==1.18.2`는 Python 3.13 품질 작업에서 실행되며 Python 3.9 소스 호환성을 검사합니다.",
            "README.ja.md": "`mypy==1.18.2` は Python 3.13 の品質ジョブで実行され、Python 3.9 のソース互換性を検査します。",
            "CONTRIBUTING.md": "`mypy==1.18.2` runs in the Python 3.13 quality job while checking Python 3.9 source compatibility.",
        }
        required = (
            "3.9",
            "3.11",
            "3.13",
            "requirements-quality.txt",
            "python3.13 -m venv .quality-venv",
            ".quality-venv/bin/pip install -r requirements-quality.txt",
            ".quality-venv/bin/python scripts/run-quality-gates.py",
            "bandit==1.9.4",
            "coverage==7.15.4",
            "mypy==1.18.2",
            "ruff==0.16.3",
            "80%",
            "-ll",
        )
        for name in (*READMES, "CONTRIBUTING.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            for token in required:
                self.assertIn(token, text, f"{token} missing from {name}")
            self.assertIn(
                mypy_relations[name], text, f"Mypy runtime/target relation missing from {name}"
            )
            self.assertRegex(text, r"(?:root|루트|ルート).{0,120}`scripts`.{0,120}`evals/harness`")
            self.assertRegex(
                text,
                r"(?:medium|중간|中)[\s\S]{0,120}-ll|-ll[\s\S]{0,120}(?:medium|중간|中)",
            )

    def test_core_skill_is_a_short_previous_first_report_recipe(self):
        core = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertLess(len(core.split()), 180)
        with tempfile.TemporaryDirectory() as directory:
            fresh = McpBootstrapHarness(directory, status="fresh").run()
        with tempfile.TemporaryDirectory() as directory:
            stale = McpBootstrapHarness(directory, status="stale").run()
        self.assertEqual([name for name, _ in fresh.calls], ["rir_previous"])
        self.assertEqual([name for name, _ in stale.calls], ["rir_previous", "rir_scan"])
        self.assertIn("references/previous-report.md", core)
        self.assertIn("references/fast-scan.md", core)
        self.assertIn("scripts/rir-controller.py previous", core)
        self.assertIn("full-inline", core)
        route = core.split("## Default bootstrap\n", 1)[1].split("\n## ", 1)[0]
        self.assertEqual(route.count("`rir_previous`"), 1)
        self.assertIn("Report flow: hide scan `display_text` and continue.", route)
        self.assertIn("Ask flow: return scan `display_text` and stop.", route)
        self.assertIn("immediately (report)", core)

    def test_graph_workflow_and_limits_are_synchronized_in_public_docs(self):
        required = (
            "rir_scan",
            "180 words",
            "rir_trace_impact",
            "10s",
            "30s",
            "detect-only",
            "no automatic install or network",
            "unknown frontiers",
            "Deep",
            "297.159",
        )
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            for token in required:
                self.assertIn(token, text, f"{token} missing from {name}")
        resolved_race_status = {
            "README.md": "exclusive-quarantine race is closed by deterministic no-clobber and interruption-recovery tests",
            "README.ko.md": "exclusive-quarantine race는 deterministic no-clobber 및 interruption-recovery 테스트로 해결됐습니다",
            "README.ja.md": "exclusive-quarantine race は deterministic no-clobber および interruption-recovery テストによって解決済みです",
        }
        for name, status in resolved_race_status.items():
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(status, text, f"resolved race status missing from {name}")

    def test_graph_cli_and_settings_are_identical_in_all_languages(self):
        canonical = (ROOT / "README.md").read_text(encoding="utf-8")
        graph_setting = re.findall(r'\{"impact_graph":.*\}', canonical)[0]
        commands = next(
            block
            for block in re.findall(r"```sh\n(.*?)\n```", canonical, re.DOTALL)
            if "trace --repo-root REPO" in block and "--graph-receipt-id RECEIPT_ID" in block
        )
        self.assertEqual(
            json.loads(graph_setting),
            {
                "impact_graph": {
                    "enabled": True,
                    "max_seconds": 30,
                    "target_seconds": 10,
                    "providers": ["auto"],
                    "install_policy": "never",
                    "deep": False,
                }
            },
        )
        for name in READMES[1:]:
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(graph_setting, text)
            self.assertIn(commands, text)

    def test_public_docs_describe_controller_mcp_and_cli_enforcement(self):
        forbidden = {
            "README.md": ("does not add MCP servers", "does not ship an MCP server"),
            "README.ko.md": ("MCP 서버, hook", "MCP 서버나 전용"),
            "README.ja.md": ("MCP server、hook", "MCP server や専用"),
        }
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            for token in (".mcp.json", "rir_begin", "rir_finalize", "MCP", "CLI"):
                self.assertIn(token, text, f"{token} missing from {name}")
            for obsolete in forbidden[name]:
                self.assertNotIn(obsolete, text, name)

    def test_top_descriptions_identify_the_current_development_version(self):
        for name in READMES:
            description = (ROOT / name).read_text(encoding="utf-8").splitlines()[4]
            self.assertIn("`0.6.1-dev`", description, name)
            self.assertNotIn("`0.6.0`", description, name)
            self.assertNotIn("`0.3.0`", description, name)

    def test_presentation_modes_and_repository_setting_are_documented(self):
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            for token in (
                ".requirements-impact-refiner.json",
                "simple",
                "balanced",
                "technical",
                '"delivery":"compact"',
                "delivery: full",
                "full-inline",
                "Change Impact Summary",
                "--require-summary",
                "Public Preview",
                "compact-delivery-demo.md",
            ):
                self.assertIn(token, text, f"{token} missing from {name}")

    def test_v03_lineage_and_migration_contract_is_synchronized(self):
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            for token in (
                "0.3.0",
                "RPT-###",
                "Previous SHA-256",
                "reopened",
                "--previous",
                "--print-expected-delta",
                "Revision 1",
            ):
                self.assertIn(token, text, f"{token} missing from {name}")
            self.assertRegex(text, r"v?0\.2(?:\.0)?.{0,80}(historical|과거|履歴)")
            self.assertRegex(text, r"(manual|수동|手動).{0,80}(migration|마이그레이션|移行)")
            self.assertRegex(text, r"Claude Code.{0,160}(`not verified`|`blocked`)")

    def test_future_acceptance_criterion_examples_are_not_verified_findings(self):
        for path in (SKILL_ROOT / "references").glob("*.md"):
            header = None
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.startswith("|"):
                    header = None
                    continue
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if "ID" in cells and "Level" in cells:
                    header = cells
                    continue
                if header and re.fullmatch(r"`?AC-\d{3}`?", cells[0]):
                    level = cells[header.index("Level")].strip("`").lower()
                    self.assertNotEqual(
                        level,
                        "verified",
                        f"future target is labelled as current proof in {path}",
                    )

    def test_all_languages_exist_and_link_to_each_other(self):
        for name in READMES:
            path = ROOT / name
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            linked = set(re.findall(r"README(?:\.ko|\.ja)?\.md", text))
            self.assertEqual(linked, LANGUAGE_TARGETS)

    def test_all_languages_have_ten_numbered_sections(self):
        for name in READMES:
            numbered = [h for h in headings(ROOT / name) if re.match(r"\d+\.", h)]
            self.assertEqual(len(numbered), 10, name)

    def test_compatibility_terms_exist_in_every_language(self):
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            for term in ("Codex", "Claude Code", "Superpowers", "Spec Kit"):
                self.assertIn(term, text, f"{term} missing from {name}")

    def test_compatibility_identity_and_status_rows_match_in_every_language(self):
        canonical = compatibility_identity_rows(ROOT / "README.md")
        self.assertEqual(len(canonical), 9)
        self.assertEqual(
            {environment: status.strip("`") for environment, _, status in canonical},
            PRE_LIVE_COMPATIBILITY,
        )
        for name in READMES[1:]:
            self.assertEqual(
                compatibility_identity_rows(ROOT / name),
                canonical,
                name,
            )

    def test_sealed_v031_evidence_is_structured_and_synchronized(self):
        canonical = markdown_table(ROOT / "README.md", "| Evidence key | Sealed value |")
        self.assertEqual(canonical, SEALED_V031_EVIDENCE)
        for name in READMES[1:]:
            self.assertEqual(
                markdown_table(ROOT / name, "| Evidence key | Sealed value |"),
                canonical,
                name,
            )

    def test_readmes_replace_obsolete_pre_live_claims_with_final_v031_evidence(self):
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            for required in (
                "84/85",
                "85/85",
                "400/400",
                "requirements-impact-refiner@requirements-impact-refiner-v031-eval",
                "codex-cli 0.148.0-alpha.21",
                "gpt-5.6-sol",
                "not verified",
                "structural-only",
                "adjudication.json",
                "report.md",
                "isolated local evaluation-only marketplace",
                "not a public install ID or support claim",
            ):
                self.assertIn(required, text, f"{required} missing from {name}")
            self.assertNotIn("10/17", text, name)
            self.assertNotIn("No all-17-times-five rerun was performed", text, name)

    def test_runbook_commands_are_parseable_and_cover_the_approved_batch(self):
        commands = harness_commands(ROOT / "evals/runbook.md")
        parsed = [build_parser().parse_args(command) for command in commands]
        self.assertEqual(len(parsed), 4)
        self.assertTrue(parsed[0].probe_only)
        self.assertEqual(parsed[1].suite, "smoke")
        self.assertEqual(parsed[1].repetitions, 1)
        self.assertEqual(parsed[2].suite, "installed-superpowers")
        self.assertEqual(parsed[2].repetitions, 5)
        self.assertEqual(parsed[2].model, "gpt-5.6-sol")
        self.assertEqual(parsed[2].reasoning, "high")
        self.assertEqual(
            len(select_suite(load_all(), parsed[2].suite)) * parsed[2].repetitions,
            85,
        )
        self.assertEqual(parsed[3].suite, "smoke")
        self.assertEqual(parsed[3].expected_plugin_version, "0.3.1")
        self.assertEqual(
            parsed[3].expected_rir_plugin_id,
            "requirements-impact-refiner@requirements-impact-refiner-v031-eval",
        )
        self.assertEqual(parsed[3].output.as_posix(), "evals/results/installed-v0.3.1")

    def test_runbook_records_exact_predecessor_handoff_without_rubric_disclosure(self):
        text = (ROOT / "evals/runbook.md").read_text(encoding="utf-8")

        self.assertIn("`current.json`", text)
        self.assertIn("canonical Markdown", text)
        self.assertIn("exact bytes", text)
        self.assertIn("does not expose a hidden rubric", text)

    def test_license_and_contributing_exist(self):
        self.assertIn("MIT License", (ROOT / "LICENSE").read_text(encoding="utf-8"))
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("README.ko.md", contributing)
        self.assertIn("README.ja.md", contributing)


if __name__ == "__main__":
    unittest.main()
