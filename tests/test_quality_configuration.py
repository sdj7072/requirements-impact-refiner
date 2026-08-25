import unittest
from pathlib import Path

from scripts import payload_identity


class QualityConfigurationTest(unittest.TestCase):
    def test_quality_requirements_are_exactly_pinned(self):
        rows = Path("requirements-quality.txt").read_text().splitlines()
        self.assertEqual(
            rows,
            [
                "bandit==1.9.4",
                "coverage==7.15.4",
                "mypy==2.3.1",
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
