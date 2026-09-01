#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

AUDIENCES = ("simple", "balanced", "technical")
DELIVERIES = ("compact", "full")
FLOWS = ("report", "ask")
REPORT_LAYOUTS = ("table", "narrative")
CONFIG_NAME = ".requirements-impact-refiner.json"
DELTA_MAX_SECONDS_DEFAULT = 3
DELTA_MAX_SECONDS_LIMIT = 30
GRAPH_DEFAULTS = {
    "enabled": True,
    "max_seconds": 30,
    "target_seconds": 10,
    "providers": ["auto"],
    "install_policy": "never",
    "deep": False,
}
GRAPH_FIELDS = frozenset(GRAPH_DEFAULTS)


def graph_defaults() -> dict[str, object]:
    """Return fresh nested graph defaults for each resolution."""
    return {
        "enabled": True,
        "max_seconds": 30,
        "target_seconds": 10,
        "providers": ["auto"],
        "install_policy": "never",
        "deep": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve impact-summary settings")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--audience", choices=AUDIENCES)
    parser.add_argument("--delivery", choices=DELIVERIES)
    parser.add_argument("--flow", choices=FLOWS)
    parser.add_argument("--report-layout", choices=REPORT_LAYOUTS)
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
    unknown = sorted(
        set(value)
        - {
            "audience",
            "delivery",
            "flow",
            "report_layout",
            "impact_graph",
            "delta_max_seconds",
        }
    )
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


def resolve_graph_settings(config: dict[str, object]) -> tuple[dict[str, object], str | None]:
    """Normalize only the explicitly supported local graph configuration."""
    configured = config.get("impact_graph")
    if configured is None:
        return graph_defaults(), None
    if not isinstance(configured, dict):
        return graph_defaults(), "impact_graph must be an object"
    unknown = sorted(set(configured) - GRAPH_FIELDS)
    missing = sorted(GRAPH_FIELDS - set(configured))
    if unknown or missing:
        detail = []
        if unknown:
            detail.append("unsupported field(s): " + ", ".join(unknown))
        if missing:
            detail.append("missing field(s): " + ", ".join(missing))
        return graph_defaults(), "; ".join(detail)
    enabled, deep = configured.get("enabled"), configured.get("deep")
    maximum, target = configured.get("max_seconds"), configured.get("target_seconds")
    providers, install_policy = configured.get("providers"), configured.get("install_policy")
    if not isinstance(enabled, bool) or not isinstance(deep, bool):
        return graph_defaults(), "enabled and deep must be booleans"
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1 or maximum > 30:
        return graph_defaults(), "max_seconds must be a positive integer at most 30"
    if not isinstance(target, int) or isinstance(target, bool) or target < 1 or target > maximum:
        return (
            graph_defaults(),
            "target_seconds must be a positive integer no greater than max_seconds",
        )
    if (
        not isinstance(providers, list)
        or not providers
        or any(not isinstance(item, str) or not item for item in providers)
        or len(set(providers)) != len(providers)
    ):
        return graph_defaults(), "providers must be a non-empty list of unique names"
    if install_policy != "never":
        return graph_defaults(), "install_policy must be never"
    return {
        "enabled": enabled,
        "max_seconds": maximum,
        "target_seconds": target,
        "providers": list(providers),
        "install_policy": install_policy,
        "deep": deep,
    }, None


def _resolve_delta_max_seconds(config: dict[str, object]) -> tuple[int, str | None]:
    configured = config.get("delta_max_seconds", DELTA_MAX_SECONDS_DEFAULT)
    if (
        not isinstance(configured, int)
        or isinstance(configured, bool)
        or configured < 1
        or configured > DELTA_MAX_SECONDS_LIMIT
    ):
        return (
            DELTA_MAX_SECONDS_DEFAULT,
            "delta_max_seconds must be a positive integer at most 30",
        )
    return configured, None


def resolve_delta_max_seconds(project_root: Path) -> int:
    value, _warning = _resolve_delta_max_seconds(load_repository_config(project_root))
    return value


def resolve(
    project_root: Path,
    audience_override: str | None,
    delivery_override: str | None,
    flow_override: str | None = None,
    report_layout_override: str | None = None,
) -> dict[str, object]:
    config = load_repository_config(project_root)
    audience, audience_source = resolve_value(
        "audience", audience_override, config, AUDIENCES, "balanced"
    )
    # The default flow answers with the impact report itself; the scan
    # summary plus a refinement question is an explicit opt-in ("ask").
    flow, flow_source = resolve_value("flow", flow_override, config, FLOWS, "report")
    # Report flow always returns the complete reader view. Ask flow keeps a
    # compact default for its explicit scan-and-confirm interaction.
    delivery_default = "full" if flow == "report" else "compact"
    delivery, delivery_source = resolve_value(
        "delivery", delivery_override, config, DELIVERIES, delivery_default
    )
    report_layout, report_layout_source = resolve_value(
        "report_layout", report_layout_override, config, REPORT_LAYOUTS, "table"
    )
    delivery_warning = None
    if flow == "report" and delivery == "compact":
        delivery = "full"
        delivery_source = "default"
        delivery_warning = "compact delivery is ignored for report flow; using full"
    impact_graph, warning = resolve_graph_settings(config)
    _delta_max_seconds, delta_warning = _resolve_delta_max_seconds(config)
    resolved: dict[str, object] = {
        "audience": audience,
        "audience_source": audience_source,
        "delivery": delivery,
        "delivery_source": delivery_source,
        "flow": flow,
        "flow_source": flow_source,
        "report_layout": report_layout,
        "report_layout_source": report_layout_source,
        "impact_graph": impact_graph,
    }
    warnings = []
    if delivery_warning is not None:
        warnings.append(delivery_warning)
    if warning is not None:
        warnings.append("invalid impact_graph configuration: " + warning)
    if delta_warning is not None:
        warnings.append("invalid delta_max_seconds configuration: " + delta_warning)
    if warnings:
        resolved["warnings"] = warnings
    return resolved


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = resolve(
            args.project_root,
            args.audience,
            args.delivery,
            args.flow,
            args.report_layout,
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    print(json.dumps(settings, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
