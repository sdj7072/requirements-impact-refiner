import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RENDERER = load_module("impact_renderer", SKILL_SCRIPTS / "impact_renderer.py")
DOMAIN = load_module("impact_report", SKILL_SCRIPTS / "impact_report.py")
CLI = SKILL_SCRIPTS / "render-impact-report.py"


def semantic_tables(text):
    parsed, errors = DOMAIN.parse_report(text)
    if errors:
        raise AssertionError(errors)
    return parsed.tables


class ImpactRendererTest(unittest.TestCase):
    def fixture(self, name="compact-state-post-decision.json"):
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def test_markdown_render_is_byte_deterministic_and_validator_clean(self):
        state = self.fixture()

        first = RENDERER.render_markdown(state)
        second = RENDERER.render_markdown(state)

        self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))
        self.assertEqual(
            first,
            (FIXTURES / "compact-state-post-decision.md").read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(RENDERER.validate_rendered_markdown(first), [])

    def test_compact_render_names_every_impact_once_and_stays_bounded(self):
        state = self.fixture()

        rendered = RENDERER.render_compact(state)

        for impact in state["impacts"]:
            self.assertEqual(rendered.count(impact["id"]), 1)
        self.assertLessEqual(len(rendered.split()), 450)
        self.assertIn("Full report:", rendered)
        self.assertIn("Validation: passed", rendered)

    def test_compact_output_explains_indirect_path_and_unknown_frontier(self):
        state = self.fixture()
        state["scope"].extend((
            {
                "boundary": "Graph paths for IMP-001",
                "evidence": "PATH-001: A → profile event → desktop cache → migration test",
                "confidence": "unknown; receipt-validated graph evidence; no confidence upgrade.",
            },
            {
                "boundary": "Impact graph coverage",
                "evidence": "Impact scan: 8.4 s · builtin (ready) · 4 nodes / 3 edges · 2 unknown frontiers",
                "confidence": "provider_limited; receipt 0123456789abcdef0123456789abcdef; sha256 a; frontier FRONTIER-001,FRONTIER-002",
            },
        ))

        text = RENDERER.render_compact(state)

        self.assertIn("A → profile event → desktop cache → migration test", text)
        self.assertIn("Impact scan: 8.4 s", text)
        self.assertIn("2 unknown frontiers", text)
        self.assertEqual(text.count("Impact scan:"), 1)

    def test_compact_graph_details_follow_audience_and_escape_safely(self):
        state = self.fixture()
        state["scope"].extend((
            {
                "boundary": "Graph paths for IMP-001",
                "evidence": "PATH-001: API | profile event → desktop cache",
                "confidence": "lexical; provider builtin; location desktop/profile_cache.ts",
            },
            {
                "boundary": "Impact graph coverage",
                "evidence": "Impact scan: 1.0 s · builtin (ready) · 3 nodes / 2 edges · 0 unknown frontiers",
                "confidence": "closed; receipt x; sha256 y; frontier none",
            },
        ))

        state["settings"]["audience"] = "simple"
        simple = RENDERER.render_compact(state)
        state["settings"]["audience"] = "balanced"
        balanced = RENDERER.render_compact(state)
        state["settings"]["audience"] = "technical"
        technical = RENDERER.render_compact(state)

        self.assertIn("API &#124; profile event → desktop cache", simple)
        self.assertNotIn("PATH-001", simple)
        self.assertIn("PATH-001: API &#124; profile event → desktop cache", balanced)
        self.assertIn("provider builtin; location desktop/profile_cache.ts", technical)

    def test_technical_path_discloses_compact_receipt_location_limit(self):
        state = self.fixture()
        state["settings"]["audience"] = "technical"
        state["scope"].extend((
            {
                "boundary": "Graph paths for IMP-001",
                "evidence": "PATH-001: API → cache",
                "confidence": "verified-source; receipt-validated graph evidence",
            },
            {
                "boundary": "Impact graph coverage",
                "evidence": "Impact scan: 1.0 s · builtin (ready) · 2 nodes / 1 edge · 0 unknown frontiers",
                "confidence": "closed",
            },
        ))

        text = RENDERER.render_compact(state)

        self.assertIn("provider builtin", text)
        self.assertIn("location unavailable from compact receipt", text)

    def test_existing_markdown_converts_without_semantic_loss(self):
        markdown = (FIXTURES / "compact-state-post-decision.md").read_text(
            encoding="utf-8"
        )

        state, errors = RENDERER.state_from_markdown(markdown)

        self.assertEqual(errors, [])
        self.assertEqual(
            semantic_tables(RENDERER.render_markdown(state)),
            semantic_tables(markdown),
        )

    def test_cell_escaping_preserves_table_shape_and_non_ascii(self):
        state = self.fixture()
        state["summary"][0]["possible_issue"] = "한글 | 日本語\n`code`"

        rendered = RENDERER.render_markdown(state)
        parsed, errors = RENDERER.state_from_markdown(rendered)

        self.assertEqual(errors, [])
        self.assertEqual(
            parsed["summary"][0]["possible_issue"], "한글 | 日本語\n`code`"
        )

    def test_cli_refuses_overwrite_without_force_and_supports_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            report_path = root / "report.md"
            roundtrip_path = root / "roundtrip.json"
            state_path.write_text(
                json.dumps(self.fixture(), ensure_ascii=False), encoding="utf-8"
            )

            first = subprocess.run(
                [sys.executable, str(CLI), str(state_path), "--format", "markdown", "--output", str(report_path)],
                text=True, capture_output=True, check=False,
            )
            second = subprocess.run(
                [sys.executable, str(CLI), str(state_path), "--format", "markdown", "--output", str(report_path)],
                text=True, capture_output=True, check=False,
            )
            converted = subprocess.run(
                [sys.executable, str(CLI), "--from-markdown", str(report_path), "--output", str(roundtrip_path)],
                text=True, capture_output=True, check=False,
            )

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 2)
            self.assertIn("output already exists", second.stderr)
            self.assertEqual(converted.returncode, 0, converted.stderr)
            self.assertEqual(json.loads(roundtrip_path.read_text()), self.fixture())


if __name__ == "__main__":
    unittest.main()
