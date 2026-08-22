import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "skills"
    / "requirements-impact-refiner"
    / "scripts"
    / "resolve-settings.py"
)


class PresentationSettingsTest(unittest.TestCase):
    def run_resolver(self, project_root, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--project-root", str(project_root), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_missing_config_defaults_to_balanced(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_resolver(directory)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"audience": "balanced", "source": "default"})

    def test_repository_config_selects_simple(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".requirements-impact-refiner.json").write_text(
                '{"audience":"simple"}\n', encoding="utf-8"
            )
            result = self.run_resolver(directory)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"audience": "simple", "source": "repository"})

    def test_current_request_override_has_highest_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".requirements-impact-refiner.json").write_text(
                '{"audience":"simple"}\n', encoding="utf-8"
            )
            result = self.run_resolver(directory, "--audience", "technical")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"audience": "technical", "source": "request"})

    def test_invalid_repository_value_is_disclosed_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".requirements-impact-refiner.json").write_text(
                '{"audience":"friendly-ish"}\n', encoding="utf-8"
            )
            result = self.run_resolver(directory)

        self.assertEqual(result.returncode, 2)
        self.assertIn("audience must be one of: simple, balanced, technical", result.stderr)


if __name__ == "__main__":
    unittest.main()
