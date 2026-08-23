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

    def test_missing_config_defaults_to_balanced_compact(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_resolver(directory)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "audience": "balanced",
                "audience_source": "default",
                "delivery": "compact",
                "delivery_source": "default",
            },
        )

    def test_repository_config_selects_simple(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".requirements-impact-refiner.json").write_text(
                '{"audience":"simple"}\n', encoding="utf-8"
            )
            result = self.run_resolver(directory)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "audience": "simple",
                "audience_source": "repository",
                "delivery": "compact",
                "delivery_source": "default",
            },
        )

    def test_request_overrides_each_repository_setting_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".requirements-impact-refiner.json").write_text(
                '{"audience":"simple","delivery":"full"}\n', encoding="utf-8"
            )
            result = self.run_resolver(
                directory,
                "--audience",
                "technical",
                "--delivery",
                "compact",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "audience": "technical",
                "audience_source": "request",
                "delivery": "compact",
                "delivery_source": "request",
            },
        )

    def test_invalid_repository_value_is_disclosed_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".requirements-impact-refiner.json").write_text(
                '{"audience":"friendly-ish"}\n', encoding="utf-8"
            )
            result = self.run_resolver(directory)

        self.assertEqual(result.returncode, 2)
        self.assertIn("audience must be one of: simple, balanced, technical", result.stderr)

    def test_invalid_delivery_is_disclosed_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".requirements-impact-refiner.json").write_text(
                '{"delivery":"shortish"}\n', encoding="utf-8"
            )
            result = self.run_resolver(directory)

        self.assertEqual(result.returncode, 2)
        self.assertIn("delivery must be one of: compact, full", result.stderr)


if __name__ == "__main__":
    unittest.main()
