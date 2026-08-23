#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json


AUDIENCES = {"simple", "balanced", "technical"}
DELIVERIES = {"compact", "full"}
PHASES = {"pre-decision", "post-decision"}
ADAPTERS = {
    "generic": "references/integration-generic.md",
    "superpowers": "references/integration-superpowers.md",
    "claude-feature-dev": "references/integration-claude-feature-dev.md",
    "spec-kit": "references/integration-spec-kit.md",
}


@dataclass(frozen=True)
class ResourceRoute:
    references: tuple[str, ...]


def resolve_route(
    *,
    predecessor: bool,
    evidence_ambiguity: bool,
    multiple_domains: bool,
    audience: str,
    delivery: str,
    phase: str,
    adapter: str,
) -> ResourceRoute:
    for name, value, allowed in (
        ("audience", audience, AUDIENCES),
        ("delivery", delivery, DELIVERIES),
        ("phase", phase, PHASES),
        ("adapter", adapter, set(ADAPTERS)),
    ):
        if value not in allowed:
            raise ValueError(f"invalid {name}: {value}")
    references = ["references/controller-workflow.md", ADAPTERS[adapter]]
    if predecessor:
        references.append("references/refinement-loop.md")
    if evidence_ambiguity:
        references.append("references/evidence-model.md")
    if multiple_domains:
        references.append("references/impact-taxonomy.md")
    if audience != "balanced":
        references.append("references/presentation-modes.md")
    if delivery == "full":
        template = (
            "impact-report-pre-decision-template.md"
            if phase == "pre-decision"
            else "impact-report-post-decision-template.md"
        )
        references.append(f"assets/{template}")
    return ResourceRoute(tuple(references))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve impact-refiner resources")
    parser.add_argument("--predecessor", action="store_true")
    parser.add_argument("--evidence-ambiguity", action="store_true")
    parser.add_argument("--multiple-domains", action="store_true")
    parser.add_argument("--audience", choices=sorted(AUDIENCES), required=True)
    parser.add_argument("--delivery", choices=sorted(DELIVERIES), required=True)
    parser.add_argument("--phase", choices=sorted(PHASES), required=True)
    parser.add_argument("--adapter", choices=sorted(ADAPTERS), required=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    route = resolve_route(
        predecessor=args.predecessor,
        evidence_ambiguity=args.evidence_ambiguity,
        multiple_domains=args.multiple_domains,
        audience=args.audience,
        delivery=args.delivery,
        phase=args.phase,
        adapter=args.adapter,
    )
    print(json.dumps({"references": list(route.references)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
