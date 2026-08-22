#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


AUDIENCES = ("simple", "balanced", "technical")
CONFIG_NAME = ".requirements-impact-refiner.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve impact-summary settings")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--audience", choices=AUDIENCES)
    return parser


def resolve(project_root: Path, override: str | None) -> dict[str, str]:
    if override is not None:
        return {"audience": override, "source": "request"}
    config_path = project_root / CONFIG_NAME
    if not config_path.exists():
        return {"audience": "balanced", "source": "default"}
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {CONFIG_NAME}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{CONFIG_NAME} must contain a JSON object")
    unknown = sorted(set(value) - {"audience"})
    if unknown:
        raise ValueError(f"unsupported setting(s): {', '.join(unknown)}")
    audience = value.get("audience", "balanced")
    if audience not in AUDIENCES:
        raise ValueError("audience must be one of: simple, balanced, technical")
    return {"audience": audience, "source": "repository"}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = resolve(args.project_root, args.audience)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    print(json.dumps(settings, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
