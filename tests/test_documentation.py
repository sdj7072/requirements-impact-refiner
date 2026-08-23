import re
import shlex
import unittest
from pathlib import Path

from evals.harness.catalog import load_all, select_suite
from evals.harness.run import build_parser


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
    "human adjudication": "400/400 passed; every adjudication quote is bound to its selected final output",
    "release status": "not verified; one mechanical verification blocker",
    "Claude probe": "2.1.228 (Claude Code) / RIR 0.3.1; structural-only, behavioral compatibility remains blocked",
}
PRE_LIVE_COMPATIBILITY = {
    "Codex standalone behavioral harness": "not verified",
    "Codex with Superpowers": "not verified",
    "Codex skill quick validator": "blocked",
    "Codex plugin validator": "blocked",
    "Claude Code standalone": "blocked",
    "Claude Code with Superpowers": "blocked",
    "Claude Code with `feature-dev`": "blocked",
    "Claude Code with Spec Kit": "blocked",
    "Generic Agent Skills-compatible harness": "blocked",
}


def headings(path):
    text = path.read_text(encoding="utf-8")
    return [
        re.sub(r"^#+\s+", "", line).strip()
        for line in text.splitlines()
        if line.startswith("## ")
    ]


def compatibility_identity_rows(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if re.match(r"^## 6\.", line)
    )
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
    def test_core_skill_is_a_short_controller_first_positive_recipe(self):
        core = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        body = core.split("---", 2)[2]
        self.assertLess(len(body.split()), 320)
        self.assertEqual(body.count("`rir_begin`"), 1)
        self.assertEqual(body.count("`rir_finalize`"), 1)
        self.assertLess(body.index("`rir_begin`"), body.index("`rir_finalize`"))
        self.assertIn("return `display_text` verbatim", body)
        self.assertIn("controller-workflow.md", body)
        self.assertIn("CLI fallback", body)
        self.assertIn("full-inline", body)
        self.assertNotIn("Author complete state JSON", body)

    def test_top_release_descriptions_identify_the_current_patch_release(self):
        for name in READMES:
            description = (ROOT / name).read_text(encoding="utf-8").splitlines()[4]
            self.assertIn("`0.4.0`", description, name)
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
                "codex plugin marketplace upgrade requirements-impact-refiner",
                "/plugin marketplace update requirements-impact-refiner",
                "/plugin update requirements-impact-refiner@requirements-impact-refiner",
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
