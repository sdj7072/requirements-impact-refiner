#!/usr/bin/env python3
"""Run the project's deterministic local and CI quality gates."""

import argparse
import importlib.metadata
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Optional

GATES = (
    (
        "ruff",
        "check",
        "scripts",
        "skills/requirements-impact-refiner/scripts",
        "evals/harness",
        "tests",
    ),
    (
        "ruff",
        "format",
        "--check",
        "scripts",
        "skills/requirements-impact-refiner/scripts",
        "evals/harness",
        "tests",
    ),
    ("mypy", "scripts", "evals/harness"),
    ("coverage", "run", "--branch", "-m", "unittest", "discover", "-s", "tests", "-q"),
    ("coverage", "report", "--fail-under=80"),
    (
        "bandit",
        "-q",
        "-r",
        "scripts",
        "skills/requirements-impact-refiner/scripts",
        "evals/harness",
        "-x",
        "tests,evals/results",
        "-ll",
        "-ii",
    ),
)


def expected_tool_versions(requirements_path: Path) -> dict[str, str]:
    """Read the exact development-tool pins used by the quality environment."""
    versions = {}
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, version = line.partition("==")
        if not separator or not name or not version:
            raise ValueError(f"expected an exact pin in {requirements_path}: {raw_line}")
        versions[name] = version
    return versions


def verify_tool_versions(requirements_path: Path) -> bool:
    """Return whether every locally installed quality tool matches its exact pin."""
    try:
        expected_versions = expected_tool_versions(requirements_path)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return False

    for tool, expected_version in expected_versions.items():
        try:
            installed_version = importlib.metadata.version(tool)
        except importlib.metadata.PackageNotFoundError:
            print(f"quality tool is not installed: {tool}=={expected_version}", file=sys.stderr)
            return False
        if installed_version != expected_version:
            print(
                f"quality tool version mismatch: {tool} is {installed_version}, expected {expected_version}",
                file=sys.stderr,
            )
            return False
    return True


def run_gates(gates: Sequence[Sequence[str]]) -> int:
    """Run each gate in order and return the first failing process status."""
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join((str(Path(sys.executable).parent), environment["PATH"]))
    for command in gates:
        try:
            subprocess.run(command, check=True, env=environment)
        except subprocess.CalledProcessError as error:
            return error.returncode
        except FileNotFoundError:
            print(f"quality tool is not installed: {command[0]}", file=sys.stderr)
            return 127
    return 0


def main(arguments: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-commands", action="store_true", help="print gates without running them"
    )
    args = parser.parse_args(arguments)

    if args.print_commands:
        print("\n".join(" ".join(command) for command in GATES))
        return 0

    if not verify_tool_versions(Path("requirements-quality.txt")):
        return 2
    return run_gates(GATES)


if __name__ == "__main__":
    raise SystemExit(main())
