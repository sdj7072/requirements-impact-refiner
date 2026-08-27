import ast
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_PYTHON_PAYLOAD_ROOTS = (
    Path("scripts"),
    Path("skills/requirements-impact-refiner/scripts"),
    Path("evals/harness"),
)


def _is_type_checking_guard(value):
    return (isinstance(value, ast.Name) and value.id == "TYPE_CHECKING") or (
        isinstance(value, ast.Attribute)
        and isinstance(value.value, ast.Name)
        and value.value.id == "typing"
        and value.attr == "TYPE_CHECKING"
    )


class _RuntimeImportVisitor(ast.NodeVisitor):
    def __init__(self):
        self.roots = set()

    def visit_If(self, node):
        if _is_type_checking_guard(node.test):
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)

    def visit_Import(self, node):
        self.roots.update(alias.name.partition(".")[0] for alias in node.names)

    def visit_ImportFrom(self, node):
        if node.level == 0 and node.module:
            self.roots.add(node.module.partition(".")[0])


def _disallowed_runtime_import_roots(source, allowed_roots, filename="<fixture>"):
    visitor = _RuntimeImportVisitor()
    visitor.visit(ast.parse(source, filename=filename))
    return tuple(sorted(visitor.roots - set(allowed_roots)))


def _functional_python_payloads(repo_root):
    paths = (
        path
        for relative_root in _PYTHON_PAYLOAD_ROOTS
        for path in (repo_root / relative_root).rglob("*.py")
        if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts
    )
    return tuple(sorted(paths, key=lambda path: path.relative_to(repo_root).as_posix()))


def _repository_local_import_roots(repo_root, payloads):
    roots = set()
    for path in payloads:
        relative = path.relative_to(repo_root)
        if path.stem.isidentifier() and path.stem != "__init__":
            roots.add(path.stem)
        roots.update(part for part in relative.parts[:-1] if part.isidentifier())
    return roots


class QualityConfigurationTest(unittest.TestCase):
    def test_generated_coverage_data_is_ignored(self):
        ignored = Path(".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".coverage", ignored)
        self.assertIn(".coverage.*", ignored)

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
        configuration = Path("pyproject.toml").read_text(encoding="utf-8")
        report_section = re.search(
            r"(?ms)^\[tool\.coverage\.report\]\n(?P<body>.*?)(?=^\[|\Z)", configuration
        )
        self.assertIsNotNone(report_section)
        precision_row = re.search(r"(?m)^precision\s*=\s*(\d+)\s*$", report_section.group("body"))
        self.assertIsNotNone(precision_row)
        precision = int(precision_row.group(1))
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            source_root = directory_path / "source"
            config_root = directory_path / "config"
            data_root = directory_path / "data"
            source_root.mkdir()
            config_root.mkdir()
            data_root.mkdir()
            probe = source_root / "coverage_precision_probe.py"
            probe.write_text(
                "import os\n"
                + "".join(f"covered_{index} = {index}\n" for index in range(799))
                + 'if os.environ.get("RIR_COVERAGE_PRECISION_PROBE") == "run":\n'
                + "".join(f"    missed_{index} = {index}\n" for index in range(201)),
                encoding="utf-8",
            )
            coverage_config = config_root / ".coveragerc"
            coverage_config.write_text(
                "[run]\n"
                "branch = True\n"
                "source =\n"
                f"    {source_root}\n"
                "[report]\n"
                f"precision = {precision}\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["COVERAGE_FILE"] = str(data_root / ".coverage")
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "coverage",
                    "run",
                    "--rcfile",
                    str(coverage_config),
                    str(probe),
                ],
                check=True,
                env=environment,
                cwd=directory_path,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "coverage",
                    "report",
                    "--rcfile",
                    str(coverage_config),
                    "--include",
                    str(probe),
                    "--fail-under=80",
                ],
                text=True,
                capture_output=True,
                env=environment,
                cwd=directory_path,
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

    def test_ast_runtime_import_audit_distinguishes_runtime_and_type_only_imports(self):
        cases = (
            ("from bandit import x\n", {"json", "local_module"}, ("bandit",)),
            ("import arbitrary_vendor.deep\n", {"json", "local_module"}, ("arbitrary_vendor",)),
            (
                'if __name__ == "__main__":\n    import hidden_entrypoint_dependency\n',
                {"json", "local_module"},
                ("hidden_entrypoint_dependency",),
            ),
            ("import json\n", {"json", "local_module"}, ()),
            ("import local_module.feature\n", {"json", "local_module"}, ()),
            ("from . import sibling\n", {"json", "local_module"}, ()),
            (
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    from typing_extensions import TypeGuard\n",
                {"typing"},
                (),
            ),
            (
                "import typing\nif typing.TYPE_CHECKING:\n    import arbitrary_vendor\n",
                {"typing"},
                (),
            ),
        )
        for source, allowed_roots, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    _disallowed_runtime_import_roots(source, allowed_roots),
                    expected,
                )

    @unittest.skipUnless(hasattr(sys, "stdlib_module_names"), "platform stdlib inventory")
    def test_runtime_payload_imports_are_standard_library_or_repository_local(self):
        repo_root = Path.cwd().resolve()
        payloads = _functional_python_payloads(repo_root)
        allowed_roots = set(getattr(sys, "stdlib_module_names", ()))
        allowed_roots.update(_repository_local_import_roots(repo_root, payloads))
        failures = {}
        for path in payloads:
            disallowed = _disallowed_runtime_import_roots(
                path.read_text(encoding="utf-8"),
                allowed_roots,
                path.relative_to(repo_root).as_posix(),
            )
            if disallowed:
                failures[path.relative_to(repo_root).as_posix()] = disallowed

        self.assertEqual(failures, {})


if __name__ == "__main__":
    unittest.main()
