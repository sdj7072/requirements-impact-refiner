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
