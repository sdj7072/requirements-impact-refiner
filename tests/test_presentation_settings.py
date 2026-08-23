import json
import importlib.util
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
SPEC = importlib.util.spec_from_file_location("resolve_settings", SCRIPT)
SETTINGS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETTINGS)


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
                "impact_graph": {
                    "enabled": True,
                    "max_seconds": 30,
                    "target_seconds": 10,
                    "providers": ["auto"],
                    "install_policy": "never",
                    "deep": False,
                },
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
                "impact_graph": {
                    "enabled": True,
                    "max_seconds": 30,
                    "target_seconds": 10,
                    "providers": ["auto"],
                    "install_policy": "never",
                    "deep": False,
                },
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
                "impact_graph": {
                    "enabled": True,
                    "max_seconds": 30,
                    "target_seconds": 10,
                    "providers": ["auto"],
                    "install_policy": "never",
                    "deep": False,
                },
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

    def test_graph_settings_accept_exact_fields_and_fall_back_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".requirements-impact-refiner.json").write_text(
                '{"impact_graph":{"enabled":false,"max_seconds":12,'
                '"target_seconds":5,"providers":["builtin"],'
                '"install_policy":"never","deep":true}}\n',
                encoding="utf-8",
            )
            result = self.run_resolver(directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["impact_graph"], {
                "enabled": False, "max_seconds": 12, "target_seconds": 5,
                "providers": ["builtin"], "install_policy": "never", "deep": True,
            })

            Path(directory, ".requirements-impact-refiner.json").write_text(
                '{"impact_graph":{"max_seconds":31}}\n', encoding="utf-8"
            )
            result = self.run_resolver(directory)

        value = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(value["impact_graph"]["max_seconds"], 30)
        self.assertIn("invalid impact_graph configuration", value["warnings"][0])

    def test_graph_target_may_not_exceed_maximum(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".requirements-impact-refiner.json").write_text(
                '{"impact_graph":{"enabled":true,"max_seconds":10,'
                '"target_seconds":11,"providers":["auto"],'
                '"install_policy":"never","deep":false}}\n',
                encoding="utf-8",
            )
            result = self.run_resolver(directory)

        value = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(value["impact_graph"]["target_seconds"], 10)
        self.assertIn("target_seconds", value["warnings"][0])

    def test_graph_default_providers_are_not_shared_between_resolutions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = SETTINGS.resolve(root, None, None)
            first["impact_graph"]["providers"].append("mutated")
            second = SETTINGS.resolve(root, None, None)

        self.assertEqual(second["impact_graph"]["providers"], ["auto"])


if __name__ == "__main__":
    unittest.main()
