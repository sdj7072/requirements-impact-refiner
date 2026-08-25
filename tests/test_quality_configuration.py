import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import payload_identity


class QualityConfigurationTest(unittest.TestCase):
    def test_coverage_measures_root_scripts_and_harness_exactly_once(self):
        configuration = Path("pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('source = ["scripts", "evals/harness"]', configuration)

    @unittest.skipUnless(importlib.util.find_spec("coverage"), "quality environment only")
    def test_coverage_report_includes_root_only_shipped_scripts(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            probe = directory_path / "coverage_probe.py"
            probe.write_text(
                "import runpy\n"
                "import sys\n"
                "sys.path.insert(0, '.')\n"
                "import scripts.rir_mcp_server\n"
                "runpy.run_path('scripts/install-agent-skill.py')\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["COVERAGE_FILE"] = str(directory_path / ".coverage")
            subprocess.run(
                [sys.executable, "-m", "coverage", "run", "--branch", str(probe)],
                check=True,
                env=environment,
            )
            result = subprocess.run(
                [sys.executable, "-m", "coverage", "report", "--fail-under=0"],
                text=True,
                capture_output=True,
                check=True,
                env=environment,
            )

        self.assertIn("scripts/rir_mcp_server.py", result.stdout)
        self.assertIn("scripts/install-agent-skill.py", result.stdout)

    @unittest.skipUnless(importlib.util.find_spec("coverage"), "quality environment only")
    def test_coverage_threshold_rejects_a_79_point_9_percent_report(self):
        probe = Path("scripts") / "_coverage_precision_probe.py"
        probe.write_text(
            "import os\n"
            + "".join(f"covered_{index} = {index}\n" for index in range(799))
            + 'if os.environ.get("RIR_COVERAGE_PRECISION_PROBE") == "run":\n'
            + "".join(f"    missed_{index} = {index}\n" for index in range(201)),
            encoding="utf-8",
        )
        self.addCleanup(probe.unlink, missing_ok=True)
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment["COVERAGE_FILE"] = str(Path(directory) / ".coverage")
            subprocess.run(
                [sys.executable, "-m", "coverage", "run", "--branch", str(probe)],
                check=True,
                env=environment,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "coverage",
                    "report",
                    "--include",
                    str(probe),
                    "--fail-under=80",
                ],
                text=True,
                capture_output=True,
                env=environment,
            )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_root_only_skill_installer_copies_the_canonical_skill(self):
        installer_path = Path("scripts/install-agent-skill.py")
        specification = importlib.util.spec_from_file_location("skill_installer", installer_path)
        self.assertIsNotNone(specification)
        self.assertIsNotNone(specification.loader)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as directory:
            destination = module.install(Path(directory))
            self.assertEqual(destination.name, "requirements-impact-refiner")
            self.assertTrue((destination / "SKILL.md").is_file())

    def test_quality_requirements_are_exactly_pinned(self):
        rows = Path("requirements-quality.txt").read_text().splitlines()
        self.assertEqual(
            rows,
            [
                "bandit==1.9.4",
                "coverage==7.15.4",
                "mypy==1.18.2",
                "ruff==0.16.3",
            ],
        )

    def test_runtime_payload_does_not_import_quality_tools(self):
        forbidden = ("bandit", "coverage", "mypy", "ruff")
        for path in payload_identity.functional_paths(Path.cwd()):
            if path.suffix == ".py":
                text = path.read_text(encoding="utf-8")
                self.assertFalse(any(f"import {name}" in text for name in forbidden), path)


if __name__ == "__main__":
    unittest.main()
