import contextlib
import importlib.metadata
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def load_canonical_runner():
    runner_path = Path("skills/requirements-impact-refiner/scripts/run-quality-gates.py")
    specification = importlib.util.spec_from_file_location("quality_runner", runner_path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"could not load quality runner from {runner_path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


QUALITY_RUNNER = load_canonical_runner()


class QualityRunnerTest(unittest.TestCase):
    def test_print_commands_lists_every_quality_gate_in_order(self):
        result = subprocess.run(
            [sys.executable, "scripts/run-quality-gates.py", "--print-commands"],
            text=True,
            capture_output=True,
            check=True,
        )

        self.assertEqual(
            result.stdout.splitlines(),
            [
                "ruff check scripts skills/requirements-impact-refiner/scripts evals/harness tests",
                "ruff format --check scripts skills/requirements-impact-refiner/scripts evals/harness tests",
                "mypy scripts evals/harness",
                "coverage run --branch -m unittest discover -s tests -q",
                "coverage report --fail-under=80",
                "bandit -q -r scripts skills/requirements-impact-refiner/scripts evals/harness "
                "-x tests,evals/results -ll -ii",
            ],
        )

    def test_canonical_runner_print_mode_matches_the_command_contract(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = QUALITY_RUNNER.main(["--print-commands"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "ruff check scripts skills/requirements-impact-refiner/scripts evals/harness tests",
                "ruff format --check scripts skills/requirements-impact-refiner/scripts evals/harness tests",
                "mypy scripts evals/harness",
                "coverage run --branch -m unittest discover -s tests -q",
                "coverage report --fail-under=80",
                "bandit -q -r scripts skills/requirements-impact-refiner/scripts evals/harness "
                "-x tests,evals/results -ll -ii",
            ],
        )

    def test_version_verification_accepts_an_installed_exact_pin(self):
        installed_version = importlib.metadata.version("pip")
        with tempfile.TemporaryDirectory() as directory:
            requirements_path = Path(directory) / "requirements-quality.txt"
            requirements_path.write_text(f"pip=={installed_version}\n", encoding="utf-8")

            self.assertTrue(QUALITY_RUNNER.verify_tool_versions(requirements_path))

    def test_version_verification_rejects_a_mismatched_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            requirements_path = Path(directory) / "requirements-quality.txt"
            requirements_path.write_text("pip==0.0.0\n", encoding="utf-8")
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                valid = QUALITY_RUNNER.verify_tool_versions(requirements_path)

        self.assertFalse(valid)
        self.assertIn("quality tool version mismatch", errors.getvalue())

    def test_runner_returns_the_first_gate_failure_status(self):
        exit_code = QUALITY_RUNNER.run_gates(((sys.executable, "-c", "import sys; sys.exit(17)"),))

        self.assertEqual(exit_code, 17)


if __name__ == "__main__":
    unittest.main()
