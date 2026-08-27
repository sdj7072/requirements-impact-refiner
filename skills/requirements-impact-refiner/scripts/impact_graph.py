#!/usr/bin/env python3
"""Strict, provider-neutral contracts for transitive impact graph receipts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing_extensions import TypeGuard

MAX_RECEIPT_BYTES = 1_048_576
MAX_STRING_LENGTH = 4_096
MAX_NODES = 512
MAX_EDGES = 2_048
MAX_PATHS = 256
MAX_FRONTIER = 256
MAX_PROVIDERS = 16
MAX_COLLECTION_LENGTH = 64
_MAX_JSON_DEPTH = 64

NODE_KINDS = frozenset(
    {
        "symbol",
        "file",
        "api_field",
        "data_key",
        "schema",
        "database",
        "cache",
        "event",
        "permission",
        "configuration",
        "operation",
        "test",
    }
)
EDGE_KINDS = frozenset(
    {
        "calls",
        "references",
        "implements",
        "imports",
        "reads",
        "writes",
        "serializes",
        "persists",
        "caches",
        "publishes",
        "subscribes",
        "authorizes",
        "configures",
        "deploys",
        "tests",
    }
)
CONFIDENCES = ("verified-provider", "verified-source", "structural-inferred", "lexical")
PROVIDER_STATUSES = frozenset(
    {
        "ready",
        "missing",
        "stale",
        "unsafe",
        "unsupported",
        "failed",
        "timed_out",
    }
)
BUDGET_STATUSES = frozenset({"closed", "budget_exhausted", "provider_limited", "no_workspace"})
CACHE_STATUSES = frozenset({"miss", "hit", "partial"})
RISK_DOMAINS = frozenset(
    {
        "functionality",
        "data",
        "interfaces",
        "authorization/privacy",
        "state/concurrency",
        "operations",
        "compatibility",
        "legal/policy",
        "regression",
    }
)
GRAPH_SETTING_KEYS = frozenset(
    {
        "enabled",
        "max_seconds",
        "target_seconds",
        "providers",
        "install_policy",
        "deep",
    }
)

_ID_PATTERNS = {
    "node": re.compile(r"NODE-\d{3}"),
    "edge": re.compile(r"EDGE-\d{3}"),
    "path": re.compile(r"PATH-\d{3}"),
    "frontier": re.compile(r"FRONTIER-\d{3}"),
}
_HEX32 = re.compile(r"[0-9a-f]{32}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_CONFIDENCE_RANK = {value: index for index, value in enumerate(CONFIDENCES)}


def _json_depth(text: str) -> int:
    """Return peak JSON container nesting without invoking the decoder."""
    depth = 0
    peak = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            peak = max(peak, depth)
        elif char in "]}":
            depth = max(0, depth - 1)
    return peak


def _tuples(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(values)


def _immutable_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType({key: _freeze(item) for key, item in value.items()})


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, frozenset, set)):
        return [_json_value(item) for item in value]
    return value


@dataclass(frozen=True)
class GraphSettings:
    enabled: bool = True
    max_seconds: int = 30
    target_seconds: int = 10
    providers: tuple[str, ...] = ("auto",)
    install_policy: str = "never"
    deep: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "providers", _tuples(self.providers))

    def to_mapping(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "max_seconds": self.max_seconds,
            "target_seconds": self.target_seconds,
            "providers": list(self.providers),
            "install_policy": self.install_policy,
            "deep": self.deep,
        }


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    status: str
    confidence: str
    version: str | None = None
    executable_sha256: str | None = None


@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: str
    label: str
    location: str | None
    provider: str
    confidence: str
    source_sha256: str | None
    risk_domains: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk_domains", _tuples(self.risk_domains))


@dataclass(frozen=True)
class GraphEdge:
    id: str
    source: str
    target: str
    kind: str
    location: str | None
    evidence: str
    confidence: str
    provider: str
    source_sha256: str | None


@dataclass(frozen=True)
class GraphPath:
    id: str
    nodes: tuple[str, ...]
    edges: tuple[str, ...]
    distance: int
    risk_domains: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", _tuples(self.nodes))
        object.__setattr__(self, "edges", _tuples(self.edges))
        object.__setattr__(self, "risk_domains", _tuples(self.risk_domains))


@dataclass(frozen=True)
class FrontierEntry:
    id: str
    node: str
    reason: str
    risk_domains: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk_domains", _tuples(self.risk_domains))


@dataclass(frozen=True)
class GraphReceipt:
    receipt_id: str
    draft_id: str
    repo_root_sha256: str
    request_sha256: str
    settings: GraphSettings
    providers: tuple[ProviderStatus, ...]
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    paths: tuple[GraphPath, ...]
    frontier: tuple[FrontierEntry, ...]
    timings_ms: Mapping[str, int]
    budget_status: str
    cache: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "providers", tuple(self.providers))
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "edges", tuple(self.edges))
        object.__setattr__(self, "paths", tuple(self.paths))
        object.__setattr__(self, "frontier", tuple(self.frontier))
        object.__setattr__(self, "timings_ms", _immutable_mapping(self.timings_ms))
        object.__setattr__(self, "cache", _immutable_mapping(self.cache))


def _mapping(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _keys(
    errors: list[str], label: str, value: object, expected: frozenset[str] | set[str]
) -> bool:
    if not _mapping(value):
        errors.append(f"{label} must be an object")
        return False
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    errors.extend(f"{label} missing key {key}" for key in missing)
    errors.extend(f"{label} has unknown key {key}" for key in unknown)
    return not missing and not unknown


def _identifier(value: object, kind: str) -> TypeGuard[str]:
    return isinstance(value, str) and _ID_PATTERNS[kind].fullmatch(value) is not None


def _string(value: object, *, allow_empty: bool = False) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and len(value) <= MAX_STRING_LENGTH
        and (allow_empty or bool(value.strip()))
    )


def _exact_int(value: object) -> TypeGuard[int]:
    return type(value) is int


def _confidence(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and value in CONFIDENCES


def _known_provider(value: object, providers: Mapping[str, object]) -> TypeGuard[str]:
    return isinstance(value, str) and value in providers


def _safe_path(value: object) -> bool:
    if not _string(value) or "\\" in str(value):
        return False
    path = str(value)
    if path.startswith("/") or path.startswith("//"):
        return False
    parts = path.split("/")
    return (
        all(part not in {"", ".", ".."} for part in parts) and not PurePosixPath(path).is_absolute()
    )


def _string_list(
    value: object, label: str, errors: list[str], allowed: frozenset[str] | None = None
) -> bool:
    if not isinstance(value, list):
        errors.append(f"{label} must be an array")
        return False
    valid = True
    if len(value) > MAX_COLLECTION_LENGTH:
        errors.append(f"{label} exceeds maximum collection size")
        valid = False
    for item in value:
        if not _string(item):
            errors.append(f"{label} must contain non-empty strings")
            valid = False
        elif allowed is not None and item not in allowed:
            errors.append(f"{label} has invalid value {item}")
            valid = False
    return valid


def _validate_settings(value: object, errors: list[str]) -> None:
    if not _keys(errors, "settings", value, GRAPH_SETTING_KEYS) or not _mapping(value):
        return
    if not isinstance(value.get("enabled"), bool):
        errors.append("settings enabled must be boolean")
    if not isinstance(value.get("deep"), bool):
        errors.append("settings deep must be boolean")
    maximum = value.get("max_seconds")
    target = value.get("target_seconds")
    maximum_number = maximum if _exact_int(maximum) else 0
    target_number = target if _exact_int(target) else 0
    maximum_valid = _exact_int(maximum) and maximum_number >= 1
    target_valid = _exact_int(target) and target_number >= 1
    if not maximum_valid:
        errors.append("settings max_seconds must be a positive integer")
    if not target_valid:
        errors.append("settings target_seconds must be a positive integer")
    if maximum_valid and maximum_number > 30:
        errors.append("settings max_seconds must not exceed 30")
    if maximum_valid and maximum_number <= 30 and target_valid and target_number > maximum_number:
        errors.append("settings target_seconds must not exceed max_seconds")
    providers = value.get("providers")
    if (
        not isinstance(providers, list)
        or not providers
        or len(providers) > MAX_COLLECTION_LENGTH
        or any(not _string(item) for item in providers)
        or len(set(providers)) != len(providers)
    ):
        errors.append("settings providers must be a non-empty list of unique names")
    if not isinstance(value.get("install_policy"), str) or value.get("install_policy") != "never":
        errors.append(f"settings has invalid install_policy {value.get('install_policy')}")


def _check_limit(
    rows: object, label: str, maximum: int, errors: list[str]
) -> list[dict[str, object]]:
    if not isinstance(rows, list):
        errors.append(f"{label} must be an array")
        return []
    if len(rows) > maximum:
        errors.append(f"{label} exceeds maximum collection size")
    result: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        if not _mapping(row):
            errors.append(f"{label} row {index} must be an object")
        else:
            result.append(row)
    return result


def _valid_hash(value: object, length: int) -> bool:
    pattern = _HEX32 if length == 32 else _HEX64
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _receipt_mapping(value: object) -> dict[str, object] | None:
    if isinstance(value, GraphReceipt):
        return {
            "schema_version": 1,
            "receipt_id": value.receipt_id,
            "draft_id": value.draft_id,
            "repo_root_sha256": value.repo_root_sha256,
            "request_sha256": value.request_sha256,
            "settings": value.settings.to_mapping(),
            "providers": [
                {
                    "name": item.name,
                    "status": item.status,
                    "confidence": item.confidence,
                    "version": item.version,
                    "executable_sha256": item.executable_sha256,
                }
                for item in value.providers
            ],
            "nodes": [
                {
                    "id": item.id,
                    "kind": item.kind,
                    "label": item.label,
                    "location": item.location,
                    "provider": item.provider,
                    "confidence": item.confidence,
                    "source_sha256": item.source_sha256,
                    "risk_domains": list(item.risk_domains),
                }
                for item in value.nodes
            ],
            "edges": [
                {
                    "id": item.id,
                    "source": item.source,
                    "target": item.target,
                    "kind": item.kind,
                    "location": item.location,
                    "evidence": item.evidence,
                    "confidence": item.confidence,
                    "provider": item.provider,
                    "source_sha256": item.source_sha256,
                }
                for item in value.edges
            ],
            "paths": [
                {
                    "id": item.id,
                    "nodes": list(item.nodes),
                    "edges": list(item.edges),
                    "distance": item.distance,
                    "risk_domains": list(item.risk_domains),
                }
                for item in value.paths
            ],
            "frontier": [
                {
                    "id": item.id,
                    "node": item.node,
                    "reason": item.reason,
                    "risk_domains": list(item.risk_domains),
                }
                for item in value.frontier
            ],
            "timings_ms": _json_value(value.timings_ms),
            "budget_status": value.budget_status,
            "cache": _json_value(value.cache),
        }
    return value if _mapping(value) else None


TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "receipt_id",
        "draft_id",
        "repo_root_sha256",
        "request_sha256",
        "settings",
        "providers",
        "nodes",
        "edges",
        "paths",
        "frontier",
        "timings_ms",
        "budget_status",
        "cache",
    }
)


def validate_receipt(value: object) -> tuple[str, ...]:
    """Return deterministic validation errors for an untrusted graph receipt."""
    receipt = _receipt_mapping(value)
    if receipt is None:
        return ("receipt must contain a JSON object",)
    errors: list[str] = []
    errors.extend(f"missing top-level key {key}" for key in sorted(TOP_LEVEL_KEYS - set(receipt)))
    errors.extend(f"unknown top-level key {key}" for key in sorted(set(receipt) - TOP_LEVEL_KEYS))
    if errors:
        return tuple(errors)
    if type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1:
        errors.append("schema_version must be 1")
    for name, length in (
        ("receipt_id", 32),
        ("draft_id", 32),
        ("repo_root_sha256", 64),
        ("request_sha256", 64),
    ):
        if not _valid_hash(receipt[name], length):
            errors.append(f"{name} must be a lowercase SHA-{length * 4} hex string")
    _validate_settings(receipt["settings"], errors)

    provider_rows = _check_limit(receipt["providers"], "providers", MAX_PROVIDERS, errors)
    providers: dict[str, dict[str, object]] = {}
    provider_fields = {"name", "status", "confidence", "version", "executable_sha256"}
    for row in provider_rows:
        _keys(errors, "provider", row, provider_fields)
        provider_name = row.get("name")
        if not _string(provider_name):
            errors.append("provider requires a name")
            continue
        if provider_name in providers:
            errors.append(f"duplicate provider {provider_name}")
        providers[provider_name] = row
        provider_status = row.get("status")
        if not isinstance(provider_status, str) or provider_status not in PROVIDER_STATUSES:
            errors.append(f"provider {provider_name} has invalid status {provider_status}")
        provider_confidence = row.get("confidence")
        if not _confidence(provider_confidence):
            errors.append(f"provider {provider_name} has invalid confidence {provider_confidence}")
        for field in ("version", "executable_sha256"):
            current = row.get(field)
            if current is not None and not _string(current):
                errors.append(f"provider {provider_name} has invalid {field}")
        executable = row.get("executable_sha256")
        if executable is not None and not _valid_hash(executable, 64):
            errors.append(
                f"provider {provider_name} executable_sha256 must be a lowercase SHA-256 hex string"
            )

    node_rows = _check_limit(receipt["nodes"], "nodes", MAX_NODES, errors)
    nodes: dict[str, dict[str, object]] = {}
    node_fields = {
        "id",
        "kind",
        "label",
        "location",
        "provider",
        "confidence",
        "source_sha256",
        "risk_domains",
    }
    for row in node_rows:
        _keys(errors, "node", row, node_fields)
        identifier = row.get("id")
        if not _identifier(identifier, "node"):
            errors.append(f"invalid graph node {identifier}")
            continue
        if identifier in nodes:
            errors.append(f"duplicate graph node {identifier}")
        nodes[identifier] = row
        node_kind = row.get("kind")
        if not isinstance(node_kind, str) or node_kind not in NODE_KINDS:
            errors.append(f"node {identifier} has invalid kind {node_kind}")
        label = row.get("label")
        if isinstance(label, str) and len(label) > MAX_STRING_LENGTH:
            errors.append(f"node {identifier} label exceeds maximum length")
        elif not _string(label):
            errors.append(f"node {identifier} requires a label")
        location = row.get("location")
        if location is not None and not _safe_path(location):
            errors.append(f"node {identifier} has unsafe location {location}")
        provider = row.get("provider")
        known_provider = provider if _known_provider(provider, providers) else None
        if known_provider is None:
            errors.append(f"node {identifier} references unknown provider {provider}")
        confidence = row.get("confidence")
        if not _confidence(confidence):
            errors.append(f"node {identifier} has invalid confidence {confidence}")
        elif known_provider is not None:
            provider_confidence = providers[known_provider].get("confidence")
            if (
                _confidence(provider_confidence)
                and _CONFIDENCE_RANK[confidence] < _CONFIDENCE_RANK[provider_confidence]
            ):
                errors.append(f"node {identifier} upgrades provider {provider} confidence")
        source = row.get("source_sha256")
        if source is not None and not _valid_hash(source, 64):
            errors.append(f"node {identifier} source_sha256 must be a lowercase SHA-256 hex string")
        _string_list(
            row.get("risk_domains"), f"node {identifier} risk_domains", errors, RISK_DOMAINS
        )

    edge_rows = _check_limit(receipt["edges"], "edges", MAX_EDGES, errors)
    edges: dict[str, dict[str, object]] = {}
    edge_fields = {
        "id",
        "source",
        "target",
        "kind",
        "location",
        "evidence",
        "confidence",
        "provider",
        "source_sha256",
    }
    for row in edge_rows:
        _keys(errors, "edge", row, edge_fields)
        identifier = row.get("id")
        if not _identifier(identifier, "edge"):
            errors.append(f"invalid graph edge {identifier}")
            continue
        if identifier in edges:
            errors.append(f"duplicate graph edge {identifier}")
        edges[identifier] = row
        for field in ("source", "target"):
            reference = row.get(field)
            if not isinstance(reference, str) or reference not in nodes:
                errors.append(f"edge {identifier} references unknown graph node {reference}")
        edge_kind = row.get("kind")
        if not isinstance(edge_kind, str) or edge_kind not in EDGE_KINDS:
            errors.append(f"edge {identifier} has invalid kind {edge_kind}")
        location = row.get("location")
        if location is not None and not _safe_path(location):
            errors.append(f"edge {identifier} has unsafe location {location}")
        if not _string(row.get("evidence")):
            errors.append(f"edge {identifier} requires evidence")
        provider = row.get("provider")
        known_provider = provider if _known_provider(provider, providers) else None
        if known_provider is None:
            errors.append(f"edge {identifier} references unknown provider {provider}")
        confidence = row.get("confidence")
        if not _confidence(confidence):
            errors.append(f"edge {identifier} has invalid confidence {confidence}")
        elif known_provider is not None:
            provider_confidence = providers[known_provider].get("confidence")
            if (
                _confidence(provider_confidence)
                and _CONFIDENCE_RANK[confidence] < _CONFIDENCE_RANK[provider_confidence]
            ):
                errors.append(f"edge {identifier} upgrades provider {provider} confidence")
        source = row.get("source_sha256")
        if source is not None and not _valid_hash(source, 64):
            errors.append(f"edge {identifier} source_sha256 must be a lowercase SHA-256 hex string")

    path_rows = _check_limit(receipt["paths"], "paths", MAX_PATHS, errors)
    paths: set[str] = set()
    path_fields = {"id", "nodes", "edges", "distance", "risk_domains"}
    for row in path_rows:
        _keys(errors, "path", row, path_fields)
        identifier = row.get("id")
        if not _identifier(identifier, "path"):
            errors.append(f"invalid graph path {identifier}")
            continue
        if identifier in paths:
            errors.append(f"duplicate graph path {identifier}")
        paths.add(identifier)
        node_ids, edge_ids = row.get("nodes"), row.get("edges")
        node_ids_valid = _string_list(node_ids, f"path {identifier} nodes", errors)
        edge_ids_valid = _string_list(edge_ids, f"path {identifier} edges", errors)
        if node_ids_valid and isinstance(node_ids, list):
            for node in node_ids:
                if node not in nodes:
                    errors.append(f"unknown graph node {node}")
        if edge_ids_valid and isinstance(edge_ids, list):
            for edge in edge_ids:
                if edge not in edges:
                    errors.append(f"unknown graph edge {edge}")
        if (
            node_ids_valid
            and edge_ids_valid
            and isinstance(node_ids, list)
            and isinstance(edge_ids, list)
        ):
            if not edge_ids or len(node_ids) != len(edge_ids) + 1:
                errors.append(f"path {identifier} requires contiguous node and edge evidence")
            elif all(edge in edges for edge in edge_ids):
                for index, edge in enumerate(edge_ids):
                    if (
                        edges[edge].get("source") != node_ids[index]
                        or edges[edge].get("target") != node_ids[index + 1]
                    ):
                        errors.append(
                            f"path {identifier} edge {edge} does not connect declared nodes"
                        )
        distance = row.get("distance")
        if type(distance) is not int:
            errors.append(f"path {identifier} distance must equal edge count")
        elif edge_ids_valid and isinstance(edge_ids, list) and distance != len(edge_ids):
            errors.append(f"path {identifier} distance must equal edge count")
        _string_list(
            row.get("risk_domains"), f"path {identifier} risk_domains", errors, RISK_DOMAINS
        )

    frontier_rows = _check_limit(receipt["frontier"], "frontier", MAX_FRONTIER, errors)
    frontier: set[str] = set()
    frontier_fields = {"id", "node", "reason", "risk_domains"}
    for row in frontier_rows:
        _keys(errors, "frontier", row, frontier_fields)
        identifier = row.get("id")
        if not _identifier(identifier, "frontier"):
            errors.append(f"invalid frontier {identifier}")
            continue
        if identifier in frontier:
            errors.append(f"duplicate frontier {identifier}")
        frontier.add(identifier)
        frontier_node = row.get("node")
        if not isinstance(frontier_node, str) or frontier_node not in nodes:
            errors.append(f"frontier {identifier} references unknown graph node {frontier_node}")
        if not _string(row.get("reason")):
            errors.append(f"frontier {identifier} requires a reason")
        _string_list(
            row.get("risk_domains"), f"frontier {identifier} risk_domains", errors, RISK_DOMAINS
        )
    budget_status = receipt["budget_status"]
    budget_status_valid = isinstance(budget_status, str) and budget_status in BUDGET_STATUSES
    if not budget_status_valid:
        errors.append(f"invalid budget_status {budget_status}")
    elif budget_status != "closed" and not frontier_rows:
        errors.append("non-closed receipt requires an unknown frontier")

    timings = receipt["timings_ms"]
    if not _mapping(timings):
        errors.append("timings_ms must be an object")
    else:
        if len(timings) > MAX_COLLECTION_LENGTH:
            errors.append("timings_ms exceeds maximum collection size")
        for name, milliseconds in timings.items():
            if (
                not _string(name)
                or not isinstance(milliseconds, int)
                or isinstance(milliseconds, bool)
                or milliseconds < 0
            ):
                errors.append("timings_ms must map names to non-negative integers")
                break
    cache = receipt["cache"]
    cache_fields = {"status", "key", "invalidated_nodes"}
    if _keys(errors, "cache", cache, cache_fields) and _mapping(cache):
        cache_status = cache.get("status")
        if not isinstance(cache_status, str) or cache_status not in CACHE_STATUSES:
            errors.append(f"cache has invalid status {cache_status}")
        if not _valid_hash(cache.get("key"), 64):
            errors.append("cache key must be a lowercase SHA-256 hex string")
        invalidated = cache.get("invalidated_nodes")
        invalidated_valid = _string_list(invalidated, "cache invalidated_nodes", errors)
        if invalidated_valid and isinstance(invalidated, list):
            for node in invalidated:
                if node not in nodes:
                    errors.append(f"cache references unknown graph node {node}")
    return tuple(errors)


def load_receipt_bytes(payload: bytes) -> tuple[dict[str, object] | None, tuple[str, ...]]:
    """Decode a bounded, UTF-8 JSON receipt without accepting malformed input."""
    if not isinstance(payload, bytes):
        return None, ("receipt must be bytes",)
    if len(payload) > MAX_RECEIPT_BYTES:
        return None, ("receipt exceeds maximum byte size",)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None, ("receipt must be UTF-8",)
    if _json_depth(text) > _MAX_JSON_DEPTH:
        return None, ("receipt exceeds maximum JSON nesting depth",)
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, RecursionError, TypeError):
        return None, ("receipt must contain valid JSON",)
    try:
        errors = validate_receipt(value)
    except (RecursionError, TypeError):
        return None, ("receipt contains malformed values",)
    return (value, errors) if not errors else (None, errors)


def canonical_receipt_bytes(value: Mapping[str, object] | GraphReceipt) -> bytes:
    """Return the single stable JSON representation used for receipt digests."""
    try:
        receipt = _receipt_mapping(value)
        errors = validate_receipt(receipt)
    except (RecursionError, TypeError) as error:
        raise ValueError("invalid graph receipt: malformed value") from error
    if errors:
        raise ValueError("invalid graph receipt: " + "; ".join(errors))
    try:
        payload = json.dumps(
            receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (RecursionError, TypeError, ValueError) as error:
        raise ValueError("invalid graph receipt: value is not canonical JSON") from error
    if len(payload) > MAX_RECEIPT_BYTES:
        raise ValueError("canonical graph receipt exceeds maximum byte size")
    return payload
