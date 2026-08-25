"""Strict graph-smoke catalog loading and deterministic receipt scoring."""

import hashlib
import importlib.util
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

from .models import CaseSpec, CaseTurn


def _load_graph_contract():
    path = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "requirements-impact-refiner"
        / "scripts"
        / "impact_graph.py"
    )
    module_name = (
        "_rir_eval_impact_graph_" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    )
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError("packaged graph receipt contract is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module


GRAPH_CONTRACT = _load_graph_contract()
canonical_receipt_bytes = GRAPH_CONTRACT.canonical_receipt_bytes


GRAPH_CASE_IDS = (
    "GRAPH-api-mobile-cache-migration",
    "GRAPH-auth-role-audit-consumer",
    "GRAPH-event-retry-idempotency-side-effect",
    "GRAPH-schema-serializer-backfill-export",
    "GRAPH-config-deploy-worker-health",
    "GRAPH-negative-no-change",
)
HIGH_RISK_DOMAINS = frozenset(
    (
        "authorization/privacy",
        "legal/policy",
        "data",
        "interfaces",
        "operations",
        "state/concurrency",
    )
)
BUILTIN_GRAPH_SETTINGS = {
    "enabled": True,
    "max_seconds": 30,
    "target_seconds": 10,
    "providers": ["builtin"],
    "install_policy": "never",
    "deep": False,
}
_CASE_KEYS = frozenset(
    (
        "id",
        "kind",
        "request",
        "repository_evidence",
        "seeds",
        "required_nodes",
        "required_edge_types",
        "minimum_path_distance",
        "forbidden_precision",
        "allowed_providers",
        "unknown_frontier_expected",
        "compact_output_phrases",
        "controller_required",
        "fixture_files",
    )
)


class GraphCatalogError(ValueError):
    pass


@dataclass(frozen=True)
class RequiredNode:
    location: str
    kind: str
    label: str
    risk_domains: tuple[str, ...]


@dataclass(frozen=True)
class ForbiddenPrecision:
    provider: str
    confidences: tuple[str, ...]
    edge_types: tuple[str, ...]


@dataclass(frozen=True)
class GraphCaseSpec:
    id: str
    kind: str
    request: str
    repository_evidence: tuple[str, ...]
    seeds: tuple[tuple[str, Optional[str]], ...]
    required_nodes: tuple[RequiredNode, ...]
    required_edge_types: tuple[str, ...]
    minimum_path_distance: int
    forbidden_precision: tuple[ForbiddenPrecision, ...]
    allowed_providers: tuple[str, ...]
    unknown_frontier_expected: bool
    compact_output_phrases: tuple[str, ...]
    controller_required: bool
    fixture_files: tuple[tuple[str, str], ...]

    def to_case_spec(self) -> CaseSpec:
        return CaseSpec(
            id=self.id,
            kind=self.kind,
            turns=(CaseTurn(self.request, self.repository_evidence),),
            must_detect=(),
            must_not_do=(),
            modes=("codex",),
        )


@dataclass(frozen=True)
class GraphScore:
    case_id: str
    passed: bool
    findings: tuple[str, ...]
    maximum_required_distance: int
    receipt_id: Optional[str]
    receipt_sha256: Optional[str]
    providers: tuple[str, ...]
    uncovered_high_risk_nodes: tuple[str, ...]
    matched_path_ids: tuple[str, ...]


def graph_run_policy(case: GraphCaseSpec) -> dict[str, object]:
    if not isinstance(case, GraphCaseSpec):
        raise TypeError("case must be a GraphCaseSpec")
    if case.kind == "negative":
        return {
            "schema_version": 1,
            "settings": None,
            "provider_inventory": [],
            "seeds": [],
        }
    return {
        "schema_version": 1,
        "settings": dict(BUILTIN_GRAPH_SETTINGS),
        "provider_inventory": ["builtin"],
        "seeds": [{"term": term, "location": location} for term, location in case.seeds],
    }


def _strings(value, label, *, allow_empty=True, unique=True):
    if not isinstance(value, list) or (not allow_empty and not value):
        raise GraphCatalogError(f"{label} must be a list")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise GraphCatalogError(f"{label} must contain nonblank strings")
    if unique and len(value) != len(set(value)):
        raise GraphCatalogError(f"{label} must not contain duplicates")
    return tuple(value)


def _safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise GraphCatalogError("fixture path must be a safe relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise GraphCatalogError("fixture path must be a safe relative POSIX path")
    return value


def _case(raw) -> GraphCaseSpec:
    if not isinstance(raw, dict) or set(raw) != _CASE_KEYS:
        raise GraphCatalogError("graph case has unknown or missing fields")
    case_id = raw["id"]
    kind = raw["kind"]
    request = raw["request"]
    if not isinstance(case_id, str) or not case_id or kind not in ("positive", "negative"):
        raise GraphCatalogError("graph case identity is invalid")
    if not isinstance(request, str) or not request.strip():
        raise GraphCatalogError(f"{case_id} request must be nonblank")
    evidence = _strings(raw["repository_evidence"], f"{case_id} repository_evidence")
    seeds = []
    if not isinstance(raw["seeds"], list):
        raise GraphCatalogError(f"{case_id} seeds must be a list")
    for seed in raw["seeds"]:
        if not isinstance(seed, dict) or set(seed) != {"term", "location"}:
            raise GraphCatalogError(f"{case_id} seed is invalid")
        if not isinstance(seed["term"], str) or not seed["term"].strip():
            raise GraphCatalogError(f"{case_id} seed term is invalid")
        location = None if seed["location"] is None else _safe_relative(seed["location"])
        seeds.append((seed["term"], location))
    nodes = []
    if not isinstance(raw["required_nodes"], list):
        raise GraphCatalogError(f"{case_id} required_nodes must be a list")
    for node in raw["required_nodes"]:
        if not isinstance(node, dict) or set(node) != {"location", "kind", "label", "risk_domains"}:
            raise GraphCatalogError(f"{case_id} required node is invalid")
        nodes.append(
            RequiredNode(
                _safe_relative(node["location"]),
                node["kind"]
                if isinstance(node["kind"], str) and node["kind"]
                else (_ for _ in ()).throw(GraphCatalogError(f"{case_id} node kind is invalid")),
                node["label"]
                if isinstance(node["label"], str) and node["label"]
                else (_ for _ in ()).throw(GraphCatalogError(f"{case_id} node label is invalid")),
                _strings(node["risk_domains"], f"{case_id} node risk domains", allow_empty=False),
            )
        )
    forbidden = []
    if not isinstance(raw["forbidden_precision"], list):
        raise GraphCatalogError(f"{case_id} forbidden_precision must be a list")
    for row in raw["forbidden_precision"]:
        if not isinstance(row, dict) or set(row) != {"provider", "confidences", "edge_types"}:
            raise GraphCatalogError(f"{case_id} forbidden precision is invalid")
        if not isinstance(row["provider"], str) or not row["provider"]:
            raise GraphCatalogError(f"{case_id} forbidden provider is invalid")
        forbidden.append(
            ForbiddenPrecision(
                row["provider"],
                _strings(row["confidences"], f"{case_id} forbidden confidences"),
                _strings(row["edge_types"], f"{case_id} forbidden edge types"),
            )
        )
    fixtures = []
    if not isinstance(raw["fixture_files"], list):
        raise GraphCatalogError(f"{case_id} fixture_files must be a list")
    for fixture in raw["fixture_files"]:
        if (
            not isinstance(fixture, dict)
            or set(fixture) != {"path", "content"}
            or not isinstance(fixture["content"], str)
        ):
            raise GraphCatalogError(f"{case_id} fixture is invalid")
        fixtures.append((_safe_relative(fixture["path"]), fixture["content"]))
    distance = raw["minimum_path_distance"]
    frontier = raw["unknown_frontier_expected"]
    controller = raw["controller_required"]
    if isinstance(distance, bool) or not isinstance(distance, int) or distance < 0:
        raise GraphCatalogError(f"{case_id} minimum_path_distance is invalid")
    if not isinstance(frontier, bool) or not isinstance(controller, bool):
        raise GraphCatalogError(f"{case_id} boolean contract fields are invalid")
    result = GraphCaseSpec(
        case_id,
        kind,
        request,
        evidence,
        tuple(seeds),
        tuple(nodes),
        _strings(
            raw["required_edge_types"],
            f"{case_id} required edge types",
            unique=False,
        ),
        distance,
        tuple(forbidden),
        _strings(raw["allowed_providers"], f"{case_id} allowed providers"),
        frontier,
        _strings(raw["compact_output_phrases"], f"{case_id} compact output phrases"),
        controller,
        tuple(fixtures),
    )
    if kind == "positive" and (
        len(result.required_nodes) < 2
        or len(result.required_edge_types) != len(result.required_nodes) - 1
        or result.minimum_path_distance < 1
        or not result.controller_required
        or not result.fixture_files
    ):
        raise GraphCatalogError(f"{case_id} positive graph contract is incomplete")
    if kind == "negative" and any(
        (
            result.seeds,
            result.required_nodes,
            result.required_edge_types,
            result.minimum_path_distance,
            result.forbidden_precision,
            result.allowed_providers,
            result.compact_output_phrases,
            result.controller_required,
            result.fixture_files,
        )
    ):
        raise GraphCatalogError(f"{case_id} negative graph contract must be empty")
    return result


def load_graph_cases(path: Optional[Path] = None) -> tuple[GraphCaseSpec, ...]:
    selected = (
        Path(path) if path is not None else Path(__file__).resolve().parents[1] / "graph-cases.json"
    )
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise GraphCatalogError(f"cannot read graph catalog: {error}") from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "cases"}
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("cases"), list)
    ):
        raise GraphCatalogError("graph catalog envelope is invalid")
    cases = tuple(_case(row) for row in payload["cases"])
    ids = tuple(case.id for case in cases)
    if len(ids) != len(set(ids)):
        raise GraphCatalogError("graph catalog contains duplicate case IDs")
    if (
        selected.resolve() == (Path(__file__).resolve().parents[1] / "graph-cases.json").resolve()
        and ids != GRAPH_CASE_IDS
    ):
        raise GraphCatalogError("checked-in graph catalog must contain the exact six cases")
    return cases


def compact_graph(receipt: Mapping[str, object]) -> dict[str, object]:
    nodes = {row["id"]: row for row in receipt["nodes"]}
    edges = {row["id"]: row for row in receipt["edges"]}
    return {
        "providers": [
            {
                "name": row["name"],
                "status": row["status"],
                "confidence": row["confidence"],
                "version": row["version"],
            }
            for row in receipt["providers"]
        ],
        "nodes": [
            {
                "key": row["id"],
                "kind": row["kind"],
                "label": row["label"],
                "location": row["location"],
                "confidence": row["confidence"],
                "risk_domains": list(row["risk_domains"]),
            }
            for row in receipt["nodes"]
        ],
        "paths": [
            {
                "key": row["id"],
                "nodes": [
                    {"key": key, "label": nodes[key]["label"], "location": nodes[key]["location"]}
                    for key in row["nodes"]
                ],
                "edges": [
                    {"key": key, "kind": edges[key]["kind"], "confidence": edges[key]["confidence"]}
                    for key in row["edges"]
                ],
                "distance": row["distance"],
                "risk_domains": list(row["risk_domains"]),
            }
            for row in receipt["paths"]
        ],
        "frontier": [
            {
                "key": row["id"],
                "node_key": row["node"],
                "reason": row["reason"],
                "risk_domains": list(row["risk_domains"]),
            }
            for row in receipt["frontier"]
        ],
        "summary": {
            "nodes": len(receipt["nodes"]),
            "edges": len(receipt["edges"]),
            "paths": len(receipt["paths"]),
            "unknown_frontiers": len(receipt["frontier"]),
            "timings_ms": dict(receipt["timings_ms"]),
            "budget_status": receipt["budget_status"],
        },
    }


def _ordered_subset(required: Sequence[str], observed: Sequence[str]) -> bool:
    iterator = iter(observed)
    return all(any(value == candidate for candidate in iterator) for value in required)


def _normalized_label(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    return " ".join(value.split())


def _required_nodes_match(required_nodes, path_nodes) -> bool:
    position = 0
    for required in required_nodes:
        found = None
        for index in range(position, len(path_nodes)):
            observed = path_nodes[index]
            if (
                observed.get("location") == required.location
                and observed.get("kind") == required.kind
                and _normalized_label(observed.get("label")) == _normalized_label(required.label)
                and frozenset(required.risk_domains).issubset(observed.get("risk_domains", ()))
            ):
                found = index
                break
        if found is None:
            return False
        position = found + 1
    return True


def score_graph(
    case: GraphCaseSpec, receipt: Optional[Mapping[str, object]], final_output: str
) -> GraphScore:
    if not isinstance(case, GraphCaseSpec):
        raise TypeError("case must be a GraphCaseSpec")
    if not isinstance(final_output, str):
        raise TypeError("final_output must be a string")
    if case.kind == "negative":
        findings = () if receipt is None else ("negative graph case must not produce a receipt",)
        return GraphScore(case.id, not findings, findings, 0, None, None, (), (), ())
    findings = []
    if not isinstance(receipt, Mapping):
        return GraphScore(
            case.id, False, ("positive graph case requires a receipt",), 0, None, None, (), (), ()
        )
    validation_errors = GRAPH_CONTRACT.validate_receipt(receipt)
    if validation_errors:
        findings = tuple("production receipt validation: " + error for error in validation_errors)
        receipt_id = receipt.get("receipt_id")
        if not isinstance(receipt_id, str) or re.fullmatch(r"[0-9a-f]{32}", receipt_id) is None:
            receipt_id = None
        return GraphScore(case.id, False, findings, 0, receipt_id, None, (), (), ())
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or re.fullmatch(r"[0-9a-f]{32}", receipt_id) is None:
        findings.append("receipt identity is invalid")
        receipt_id = None
    try:
        digest = hashlib.sha256(canonical_receipt_bytes(receipt)).hexdigest()
    except (TypeError, ValueError, RecursionError):
        digest = None
        findings.append("receipt serialization is invalid")
    nodes_raw = receipt.get("nodes")
    edges_raw = receipt.get("edges")
    paths_raw = receipt.get("paths")
    frontier_raw = receipt.get("frontier")
    providers_raw = receipt.get("providers")
    if not all(
        isinstance(value, list)
        for value in (nodes_raw, edges_raw, paths_raw, frontier_raw, providers_raw)
    ):
        return GraphScore(
            case.id,
            False,
            tuple(sorted(set([*findings, "receipt graph collections are invalid"]))),
            0,
            receipt_id,
            digest,
            (),
            (),
            (),
        )
    nodes = {
        row.get("id"): row
        for row in nodes_raw
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    edges = {
        row.get("id"): row
        for row in edges_raw
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    if len(nodes) != len(nodes_raw) or len(edges) != len(edges_raw):
        findings.append("receipt graph identifiers are invalid or duplicated")
    provider_names = tuple(
        sorted(
            {
                row.get("name")
                for row in providers_raw
                if isinstance(row, dict) and isinstance(row.get("name"), str)
            }
        )
    )
    if any(name not in case.allowed_providers for name in provider_names):
        findings.append("disallowed provider appears in receipt inventory")
    expected_policy = graph_run_policy(case)
    if (
        receipt.get("settings") != expected_policy["settings"]
        or list(provider_names) != expected_policy["provider_inventory"]
    ):
        findings.append("builtin graph provider policy does not match receipt")
    matching_paths = []
    identity_path_exists = False
    maximum_distance = 0
    for path in paths_raw:
        if (
            not isinstance(path, dict)
            or not isinstance(path.get("nodes"), list)
            or not isinstance(path.get("edges"), list)
        ):
            continue
        path_nodes = [nodes.get(identifier) for identifier in path["nodes"]]
        path_edges = [edges.get(identifier) for identifier in path["edges"]]
        if any(row is None for row in path_nodes + path_edges):
            continue
        edge_types = tuple(row.get("kind") for row in path_edges)
        identity_matches = _required_nodes_match(case.required_nodes, path_nodes)
        identity_path_exists = identity_path_exists or identity_matches
        if identity_matches and _ordered_subset(case.required_edge_types, edge_types):
            matching_paths.append(path)
            distance = path.get("distance")
            if isinstance(distance, int) and not isinstance(distance, bool):
                maximum_distance = max(maximum_distance, distance)
    if not identity_path_exists:
        findings.append("required node identity must bind label, kind, location, and risks")
    if not matching_paths:
        findings.append("required graph path or required edge types are missing")
    if maximum_distance < case.minimum_path_distance:
        findings.append("minimum distance is not satisfied")
    for row in nodes_raw:
        if not isinstance(row, dict):
            continue
        if row.get("provider") not in case.allowed_providers:
            findings.append("disallowed provider appears on graph evidence")
        for forbidden in case.forbidden_precision:
            if (
                row.get("provider") == forbidden.provider
                and row.get("confidence") in forbidden.confidences
            ):
                findings.append("forbidden fabricated precision appears on graph evidence")
    for row in edges_raw:
        if not isinstance(row, dict):
            continue
        if row.get("provider") not in case.allowed_providers:
            findings.append("disallowed provider appears on graph evidence")
        for forbidden in case.forbidden_precision:
            if row.get("provider") == forbidden.provider and (
                row.get("confidence") in forbidden.confidences
                or row.get("kind") in forbidden.edge_types
            ):
                findings.append("forbidden fabricated precision appears on graph evidence")
    frontier_present = bool(frontier_raw)
    if frontier_present != case.unknown_frontier_expected:
        findings.append("unknown frontier expectation does not match receipt")
    covered = {
        identifier
        for path in paths_raw
        if isinstance(path, dict)
        for identifier in path.get("nodes", ())
    }
    frontier_nodes = {row.get("node") for row in frontier_raw if isinstance(row, dict)}
    uncovered = tuple(
        sorted(
            identifier
            for identifier, row in nodes.items()
            if set(row.get("risk_domains", ())) & HIGH_RISK_DOMAINS
            and identifier not in covered
            and identifier not in frontier_nodes
        )
    )
    if uncovered:
        findings.append("receipt contains uncovered high-risk nodes")
    for phrase in case.compact_output_phrases:
        if phrase not in final_output:
            findings.append(f"compact output phrase is missing: {phrase}")
    unique = tuple(sorted(set(findings)))
    matched_ids = tuple(path["id"] for path in matching_paths if isinstance(path.get("id"), str))
    return GraphScore(
        case.id,
        not unique,
        unique,
        maximum_distance,
        receipt_id,
        digest,
        provider_names,
        uncovered,
        matched_ids,
    )
