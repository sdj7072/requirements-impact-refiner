#!/usr/bin/env python3
"""Install the canonical Agent Skill into a client skill directory."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SKILL_NAME = "requirements-impact-refiner"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPOSITORY_ROOT / "skills" / SKILL_NAME


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy Requirements Impact Refiner into an Agent Skills directory."
    )
    parser.add_argument(
        "--target-dir",
        required=True,
        help="Directory that contains installed skills, such as ~/.agents/skills",
    )
    return parser.parse_args()


def install(target_dir: Path) -> Path:
    destination = target_dir.expanduser().resolve() / SKILL_NAME
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(
            f"{destination} already exists; remove or move it before reinstalling"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE, destination)
    return destination


def main() -> int:
    args = parse_args()
    try:
        destination = install(Path(args.target_dir))
    except (FileExistsError, OSError) as error:
        print(f"Installation failed: {error}", file=sys.stderr)
        return 1
    print(f"Installed {SKILL_NAME} at {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
