#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


AUDIENCES = ("simple", "balanced", "technical")
DELIVERIES = ("compact", "full")
CONFIG_NAME = ".requirements-impact-refiner.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve impact-summary settings")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--audience", choices=AUDIENCES)
    parser.add_argument("--delivery", choices=DELIVERIES)
    return parser


def load_repository_config(project_root: Path) -> dict[str, object]:
    config_path = project_root / CONFIG_NAME
    if not config_path.exists():
        return {}
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {CONFIG_NAME}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{CONFIG_NAME} must contain a JSON object")
    unknown = sorted(set(value) - {"audience", "delivery"})
    if unknown:
        raise ValueError(f"unsupported setting(s): {', '.join(unknown)}")
    return value


def resolve_value(
    name: str,
    override: str | None,
    config: dict[str, object],
    allowed: tuple[str, ...],
    default: str,
) -> tuple[str, str]:
    if override is not None:
        return override, "request"
    if name not in config:
        return default, "default"
    configured = config[name]
    if configured not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(allowed)}")
    return str(configured), "repository"


def resolve(
    project_root: Path,
    audience_override: str | None,
    delivery_override: str | None,
) -> dict[str, str]:
    config = load_repository_config(project_root)
    audience, audience_source = resolve_value(
        "audience", audience_override, config, AUDIENCES, "balanced"
    )
    delivery, delivery_source = resolve_value(
        "delivery", delivery_override, config, DELIVERIES, "compact"
    )
    return {
        "audience": audience,
        "audience_source": audience_source,
        "delivery": delivery,
        "delivery_source": delivery_source,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = resolve(args.project_root, args.audience, args.delivery)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    print(json.dumps(settings, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
