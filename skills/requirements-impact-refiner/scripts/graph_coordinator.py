#!/usr/bin/env python3
"""Coordinate cached, optional, and built-in transitive impact evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from graph_builtin import (
        BuiltInScanResult as BuiltInScanResultType,
    )
    from graph_builtin import ScanLimits, ScanSeed
    from graph_builtin import (
        ScanLimits as ScanLimitsType,
    )
    from graph_builtin import (
        ScanSeed as ScanSeedType,
    )
    from graph_cache import CacheResult as CacheResultType
    from graph_providers import Deadline, ProviderProbe, ProviderQuery, ProviderResult, ProviderSpec
    from graph_providers import (
        Deadline as DeadlineType,
    )
    from graph_providers import (
        ProviderProbe as ProviderProbeType,
    )
    from graph_providers import (
        ProviderQuery as ProviderQueryType,
    )
    from graph_providers import (
        ProviderResult as ProviderResultType,
    )
    from graph_providers import (
        ProviderSpec as ProviderSpecType,
    )
    from impact_graph import (
        FrontierEntry as FrontierEntryType,
    )
    from impact_graph import (
        GraphEdge as GraphEdgeType,
    )
    from impact_graph import (
        GraphNode as GraphNodeType,
    )
    from impact_graph import (
        GraphPath as GraphPathType,
    )
    from impact_graph import (
        GraphReceipt as GraphReceiptType,
    )
    from impact_graph import GraphSettings
    from impact_graph import (
        GraphSettings as GraphSettingsType,
    )
    from impact_graph import (
        ProviderStatus as ProviderStatusType,
    )
    from typing_extensions import TypeGuard


class _GraphContract(Protocol):
    GraphSettings: type[GraphSettingsType]
    ProviderStatus: type[ProviderStatusType]
    GraphNode: type[GraphNodeType]
    GraphEdge: type[GraphEdgeType]
    GraphPath: type[GraphPathType]
    FrontierEntry: type[FrontierEntryType]
    GraphReceipt: type[GraphReceiptType]
    CONFIDENCES: Sequence[str]
    EDGE_KINDS: frozenset[str]
    NODE_KINDS: frozenset[str]
    RISK_DOMAINS: frozenset[str]
    MAX_EDGES: int
    MAX_FRONTIER: int
    MAX_NODES: int
    MAX_PATHS: int
    MAX_RECEIPT_BYTES: int
    MAX_STRING_LENGTH: int

    def _safe_path(self, value: object) -> bool: ...

    def _validate_settings(self, value: Mapping[str, object], errors: list[str]) -> None: ...

    def canonical_receipt_bytes(self, value: object) -> bytes: ...

    def load_receipt_bytes(
        self, payload: bytes
    ) -> tuple[dict[str, object] | None, tuple[str, ...]]: ...


class _BuiltinContract(Protocol):
    ScanSeed: type[ScanSeedType]
    ScanLimits: type[ScanLimitsType]
    BuiltInScanResult: type[BuiltInScanResultType]
    DEFAULT_MAX_FILE_BYTES: int

    def _read_regular_file(
        self,
        root: Path,
        relative: str,
        maximum: int,
        remaining: int | None = None,
        read_allowed: bool = True,
    ) -> tuple[bytes | None, str | None]: ...

    def _safe_graph_text(self, value: str, sensitive_literals: Sequence[str] = ()) -> str: ...

    def _walk_files(
        self,
        root: Path,
        expired: Callable[[], bool],
        skipped: dict[str, str],
        traversal_errors: list[str],
    ) -> Iterable[tuple[Path, str]]: ...

    def scan_repository(
        self,
        repo_root: Path | str,
        seeds: Sequence[ScanSeedType],
        limits: ScanLimitsType,
        clock: object,
    ) -> BuiltInScanResultType: ...


class _CacheContract(Protocol):
    CacheResult: type[CacheResultType]

    def _configure_delta_worker(self, token: str) -> None: ...

    def _source_digests(self, value: Mapping[str, str]) -> dict[str, str]: ...

    def load(
        self, repo_root: Path | str, key: str, source_digests: Mapping[str, str]
    ) -> CacheResultType: ...

    def publish(
        self,
        repo_root: Path | str,
        receipt: object,
        source_digests: Mapping[str, str],
        *,
        schema_version: int = 1,
        inventory_complete: bool = True,
        inventory_reason: str | None = None,
    ) -> CacheResultType: ...


class _ProviderContract(Protocol):
    PROVIDER_PRIORITY: tuple[str, ...]
    Deadline: type[DeadlineType]
    ProviderProbe: type[ProviderProbeType]
    ProviderQuery: type[ProviderQueryType]
    ProviderResult: type[ProviderResultType]
    ProviderSpec: type[ProviderSpecType]

    def _configure_delta_worker(self, enabled: bool = True) -> None: ...

    def discover_providers(
        self,
        repo_root: Path | str,
        requested: Sequence[str] = ("auto",),
        deadline: DeadlineType | None = None,
        *,
        runner: object = None,
        search_path: str | None = None,
        deep: bool = False,
    ) -> tuple[ProviderProbeType, ...]: ...

    def run_provider(
        self,
        spec: ProviderSpecType,
        arguments: Sequence[str],
        repo_root: Path | str,
        deadline: DeadlineType,
        *,
        runner: object = None,
        expect_json: bool = False,
    ) -> ProviderQueryType: ...


def _load_sibling(filename: str, module_name: str) -> object:
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        return loaded
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load " + filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _classes(value: object, names: Sequence[str]) -> bool:
    return all(isinstance(getattr(value, name, None), type) for name in names)


def _callables(value: object, names: Sequence[str]) -> bool:
    return all(callable(getattr(value, name, None)) for name in names)


def _is_graph_contract(value: object) -> TypeGuard[_GraphContract]:
    return (
        _classes(
            value,
            (
                "GraphSettings",
                "ProviderStatus",
                "GraphNode",
                "GraphEdge",
                "GraphPath",
                "FrontierEntry",
                "GraphReceipt",
            ),
        )
        and all(
            isinstance(getattr(value, name, None), int)
            for name in (
                "MAX_EDGES",
                "MAX_FRONTIER",
                "MAX_NODES",
                "MAX_PATHS",
                "MAX_RECEIPT_BYTES",
                "MAX_STRING_LENGTH",
            )
        )
        and isinstance(getattr(value, "CONFIDENCES", None), Sequence)
        and all(
            isinstance(getattr(value, name, None), frozenset)
            for name in ("EDGE_KINDS", "NODE_KINDS", "RISK_DOMAINS")
        )
        and _callables(
            value,
            ("_safe_path", "_validate_settings", "canonical_receipt_bytes", "load_receipt_bytes"),
        )
    )


def _is_builtin_contract(value: object) -> TypeGuard[_BuiltinContract]:
    return (
        _classes(value, ("ScanSeed", "ScanLimits", "BuiltInScanResult"))
        and isinstance(getattr(value, "DEFAULT_MAX_FILE_BYTES", None), int)
        and _callables(
            value,
            ("_read_regular_file", "_safe_graph_text", "_walk_files", "scan_repository"),
        )
    )


def _is_cache_contract(value: object) -> TypeGuard[_CacheContract]:
    return _classes(value, ("CacheResult",)) and _callables(
        value, ("_source_digests", "load", "publish")
    )


def _is_provider_contract(value: object) -> TypeGuard[_ProviderContract]:
    priority = getattr(value, "PROVIDER_PRIORITY", None)
    return (
        isinstance(priority, tuple)
        and all(isinstance(item, str) for item in priority)
        and _classes(
            value,
            ("Deadline", "ProviderProbe", "ProviderQuery", "ProviderResult", "ProviderSpec"),
        )
        and _callables(value, ("discover_providers", "run_provider"))
    )


_loaded_graph = _load_sibling("impact_graph.py", "_rir_impact_graph")
_loaded_builtin = _load_sibling("graph_builtin.py", "_rir_graph_builtin")
_loaded_cache = _load_sibling("graph_cache.py", "_rir_graph_cache")
_loaded_providers = _load_sibling("graph_providers.py", "_rir_graph_providers")
if not _is_graph_contract(_loaded_graph):
    raise ImportError("graph sibling contract is incomplete")
if not _is_builtin_contract(_loaded_builtin):
    raise ImportError("graph sibling contract is incomplete")
if not _is_cache_contract(_loaded_cache):
    raise ImportError("graph sibling contract is incomplete")
if not _is_provider_contract(_loaded_providers):
    raise ImportError("graph sibling contract is incomplete")
GRAPH = cast(_GraphContract, _loaded_graph)
BUILTIN = cast(_BuiltinContract, _loaded_builtin)
CACHE = cast(_CacheContract, _loaded_cache)
PROVIDERS = cast(_ProviderContract, _loaded_providers)

if not TYPE_CHECKING:
    Deadline = PROVIDERS.Deadline
    ProviderProbe = PROVIDERS.ProviderProbe
    ProviderQuery = PROVIDERS.ProviderQuery
    ProviderResult = PROVIDERS.ProviderResult
    ProviderSpec = PROVIDERS.ProviderSpec
    ScanSeed = BUILTIN.ScanSeed
    ScanLimits = BUILTIN.ScanLimits
    GraphSettings = GRAPH.GraphSettings

discover_providers = PROVIDERS.discover_providers
run_provider = PROVIDERS.run_provider


class _Adapter(Protocol):
    def probe(
        self, spec: ProviderSpec, root: Path, deadline: Deadline, runner: object
    ) -> ProviderProbe: ...

    def query(
        self,
        probe: ProviderProbe,
        seeds: tuple[ScanSeed, ...],
        deadline: Deadline,
        runner: object,
    ) -> ProviderResult: ...


ADAPTERS: dict[str, _Adapter] = {}
_HEX32 = re.compile(r"[0-9a-f]{32}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
# Canonical FrontierEntry has no severity field. Boundary-crossing domains at
# the front of this table are the coordinator's deterministic high/critical tier.
_RISK_ORDER = (
    "authorization/privacy",
    "legal/policy",
    "data",
    "interfaces",
    "operations",
    "state/concurrency",
    "regression",
    "compatibility",
    "functionality",
)
_RISK_RANK = {name: index for index, name in enumerate(_RISK_ORDER)}
_PROVIDER_RANK = {name: index for index, name in enumerate(PROVIDERS.PROVIDER_PRIORITY)}
_CONTROL = (".requirements-impact-refiner", "graph")
_CACHE_POINTER = (".requirements-impact-refiner", "cache", "graph", "v1", "current")
_DELTA_WORKER_TOKEN = None


def _configure_delta_worker(token):
    global _DELTA_WORKER_TOKEN
    if not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{32}", token) is None:
        raise ValueError("delta worker token is invalid")
    _DELTA_WORKER_TOKEN = token
    CACHE._configure_delta_worker(token)
    PROVIDERS._configure_delta_worker(True)


@dataclass(frozen=True)
class SourceInventory:
    digests: Mapping[str, str]
    complete: bool
    reason: str | None = None

    def __post_init__(self):
        normalized = CACHE._source_digests(self.digests)
        if not isinstance(self.complete, bool):
            raise TypeError("source inventory completeness must be boolean")
        if (self.complete and self.reason is not None) or (
            not self.complete
            and self.reason
            not in {"deadline", "collection-limit", "traversal", "unreadable-source"}
        ):
            raise ValueError("source inventory reason is invalid")
        object.__setattr__(self, "digests", MappingProxyType(normalized))


def _settings(value) -> GraphSettings:
    if isinstance(value, GraphSettings):
        settings = value
    elif isinstance(value, Mapping):
        settings = GraphSettings(**dict(value))
    else:
        raise TypeError("settings must be GraphSettings or a mapping")
    errors: list[str] = []
    GRAPH._validate_settings(settings.to_mapping(), errors)
    if errors:
        raise ValueError("invalid graph settings: " + "; ".join(errors))
    return settings


def _draft_id(draft) -> str:
    if isinstance(draft, Mapping):
        value = draft.get("draft_id", draft.get("id"))
    else:
        value = getattr(draft, "draft_id", None)
    if isinstance(value, str) and _HEX32.fullmatch(value):
        return value
    stable = value if value is not None else draft
    return hashlib.sha256(repr(stable).encode("utf-8")).hexdigest()[:32]


def _json_default(value):
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dict__"):
        return value.__dict__
    return repr(value)


def _request_sha256(draft, seeds, settings) -> str:
    payload = json.dumps(
        {
            "draft": draft,
            "seeds": [{"term": item.term, "location": item.location} for item in seeds],
            "settings": settings.to_mapping(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _repo_identity(root: Path) -> str:
    return hashlib.sha256(str(root).encode("utf-8")).hexdigest()


def _basic_provider_inventory(probes):
    return tuple(sorted((probe.name, probe.version, probe.executable_sha256) for probe in probes))


def _trace_identity(root, draft_id, request_sha256, seeds, settings, probes):
    payload = json.dumps(
        {
            "repo_root_sha256": _repo_identity(root),
            "draft_id": draft_id,
            "request_sha256": request_sha256,
            "seeds": [{"term": seed.term, "location": seed.location} for seed in seeds],
            "settings": settings.to_mapping(),
            "providers": _basic_provider_inventory(probes),
            "builtin": ("builtin", "builtin-v1"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


# Seed risk keywords match whole identifier tokens (camel boundaries
# split), never substrings: author.name, statement.value, and rapid.value
# must not classify as authorization, concurrency, or interface risks.
_SEED_RISK_PATTERNS = {
    "authorization/privacy": re.compile(
        r"auth(?:z|n|orization|oriz\w+|entic\w+)?|oauth|permissions?|"
        r"privacy|roles|access|acl|rbac"
    ),
    "legal/policy": re.compile(r"legal|licenses?|licensing|policy|policies|compliance|terms"),
    "data": re.compile(r"schemas?|database|db|cached?|caches|persist\w*|profiles?|data"),
    "interfaces": re.compile(r"apis?|contracts?|events?|clients?"),
    "operations": re.compile(r"deploy\w*|configs?|configuration|workers?|health|operations?"),
    "state/concurrency": re.compile(
        r"states?|stateful|concurr\w*|locks?|locking|locked|races?|"
        r"retry|retries|idempot\w*|mutex"
    ),
    "regression": re.compile(r"regressions?|tests?|testing|conftest|fixtures?"),
    "compatibility": re.compile(r"compatibility|compat|backward|legacy|migrations?"),
}
_SEED_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _risk_domains(seed: ScanSeed) -> tuple:
    haystack = _SEED_CAMEL_BOUNDARY.sub(" ", seed.term + " " + (seed.location or "")).lower()
    tokens = {token for token in re.split(r"[^a-z0-9]+", haystack) if token}
    domains = set()
    for domain, pattern in _SEED_RISK_PATTERNS.items():
        if any(pattern.fullmatch(token) for token in tokens):
            domains.add(domain)
    if not domains:
        domains.add("functionality")
    return tuple(sorted(domains, key=lambda item: (_RISK_RANK[item], item)))


def _seed_key(seed: ScanSeed):
    domains = _risk_domains(seed)
    return (
        min((_RISK_RANK.get(domain, 99) for domain in domains), default=99),
        seed.location or "",
        seed.term,
    )


def _provider_status(probe: ProviderProbe):
    return GRAPH.ProviderStatus(
        probe.name,
        probe.status,
        probe.confidence,
        probe.version,
        probe.executable_sha256,
    )


def _builtin_status():
    return GRAPH.ProviderStatus(
        "builtin",
        "ready",
        "structural-inferred",
        "builtin-v1",
        None,
    )


def _placeholder(seed: ScanSeed, index: int):
    return GRAPH.GraphNode(
        "NODE-%03d" % index,
        "symbol",
        seed.term[: GRAPH.MAX_STRING_LENGTH],
        seed.location,
        "builtin",
        "lexical",
        None,
        _risk_domains(seed),
    )


def _frontier(identifier, node, reason, domains):
    return GRAPH.FrontierEntry(identifier, node, reason[: GRAPH.MAX_STRING_LENGTH], domains)


def _frontier_sort(item):
    return (
        min((_RISK_RANK.get(domain, 99) for domain in item.risk_domains), default=99),
        item.node,
        item.reason,
        item.id,
    )


def _path_sort(item):
    return (
        min((_RISK_RANK.get(domain, 99) for domain in item.risk_domains), default=99),
        item.distance,
        item.id,
    )


def _adapter(name: str) -> _Adapter | None:
    configured = ADAPTERS.get(name)
    if configured is not None:
        return configured
    filename = "graph_adapter_{}.py".format(name.replace("-", "_"))
    path = Path(__file__).with_name(filename)
    if not path.is_file():
        return None
    loaded = _load_sibling(filename, "_rir_" + filename[:-3])
    if not callable(getattr(loaded, "probe", None)) or not callable(getattr(loaded, "query", None)):
        raise ImportError("provider adapter contract is incomplete")
    return cast(_Adapter, loaded)


def _current_cache_key(root: Path):
    current = root
    for component in _CACHE_POINTER:
        current = current / component
        try:
            metadata = current.lstat()
        except OSError:
            return None
        if stat.S_ISLNK(metadata.st_mode):
            return None
        if component != "current" and not stat.S_ISDIR(metadata.st_mode):
            return None
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 65:
        return None
    try:
        value = current.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return value if _HEX64.fullmatch(value) else None


def _receipt_from_mapping(value):
    """Construct public canonical types only after GraphCache validated the mapping."""
    settings = GraphSettings(
        **{
            **value["settings"],
            "providers": tuple(value["settings"]["providers"]),
        }
    )
    return GRAPH.GraphReceipt(
        value["receipt_id"],
        value["draft_id"],
        value["repo_root_sha256"],
        value["request_sha256"],
        settings,
        tuple(GRAPH.ProviderStatus(**row) for row in value["providers"]),
        tuple(
            GRAPH.GraphNode(
                **{
                    **row,
                    "risk_domains": tuple(row["risk_domains"]),
                }
            )
            for row in value["nodes"]
        ),
        tuple(GRAPH.GraphEdge(**row) for row in value["edges"]),
        tuple(
            GRAPH.GraphPath(
                **{
                    **row,
                    "nodes": tuple(row["nodes"]),
                    "edges": tuple(row["edges"]),
                    "risk_domains": tuple(row["risk_domains"]),
                }
            )
            for row in value["paths"]
        ),
        tuple(
            GRAPH.FrontierEntry(
                **{
                    **row,
                    "risk_domains": tuple(row["risk_domains"]),
                }
            )
            for row in value["frontier"]
        ),
        value["timings_ms"],
        value["budget_status"],
        value["cache"],
    )


def _provider_inventory_matches(receipt, probes) -> bool:
    cached = {
        item["name"]: (item["version"], item["executable_sha256"])
        for item in receipt.get("providers", ())
        if item.get("name") != "builtin"
    }
    current = {item.name: (item.version, item.executable_sha256) for item in probes}
    return cached == current


def _cached_trace_matches(
    receipt,
    trace_identity,
    draft_id,
    root,
    request_sha256,
    settings,
    probes,
):
    return (
        receipt.get("receipt_id") == trace_identity
        and receipt.get("draft_id") == draft_id
        and receipt.get("repo_root_sha256") == _repo_identity(root)
        and receipt.get("request_sha256") == request_sha256
        and receipt.get("settings") == settings.to_mapping()
        and _provider_inventory_matches(receipt, probes)
    )


def _load_cache(
    root,
    source_digests,
    probes,
    trace_identity,
    draft_id,
    request_sha256,
    settings,
):
    key = _current_cache_key(root)
    if key is None:
        return CACHE.CacheResult("miss", "0" * 64, None, ())
    result = CACHE.load(root, key, source_digests)
    if result.receipt is not None and not _cached_trace_matches(
        result.receipt,
        trace_identity,
        draft_id,
        root,
        request_sha256,
        settings,
        probes,
    ):
        return CACHE.CacheResult("miss", "0" * 64, None, ())
    return result


def _collect_source_digests(root: Path, deadline: Deadline):
    """Collect the exact built-in document identity without expanding relationships."""
    skipped: dict[str, str] = {}
    traversal_errors: list[str] = []
    digests: dict[str, str] = {}
    files = 0
    total_bytes = 0
    if deadline.expired():
        return SourceInventory({}, False, "deadline")
    for _path, relative in BUILTIN._walk_files(
        root,
        deadline.expired,
        skipped,
        traversal_errors,
    ):
        if deadline.expired():
            return SourceInventory(digests, False, "deadline")
        remaining = 8_000_000 - total_bytes
        payload, reason = BUILTIN._read_regular_file(
            root,
            relative,
            BUILTIN.DEFAULT_MAX_FILE_BYTES,
            remaining,
            read_allowed=files < 500,
        )
        if reason is not None or payload is None:
            if reason in {"file-limit", "byte-limit"}:
                return SourceInventory(digests, False, "collection-limit")
            if reason == "oversized":
                return SourceInventory(digests, False, "collection-limit")
            if reason == "unsafe-file":
                return SourceInventory(digests, False, "unreadable-source")
            continue
        files += 1
        total_bytes += len(payload)
        if b"\x00" in payload:
            continue
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError:
            continue
        digests[relative] = hashlib.sha256(payload).hexdigest()
    if deadline.expired():
        return SourceInventory(digests, False, "deadline")
    if traversal_errors:
        return SourceInventory(digests, False, "traversal")
    return SourceInventory(digests, True, None)


def _normalize_candidate_node(row, result):
    if not isinstance(row, Mapping):
        raise ValueError("provider node must be an object")
    required = {
        "key",
        "kind",
        "label",
        "location",
        "confidence",
        "source_sha256",
        "risk_domains",
    }
    if set(row) != required:
        raise ValueError("provider node shape is unsupported")
    key = row["key"]
    if not isinstance(key, str) or not key or len(key) > 256:
        raise ValueError("provider node key must be bounded")
    if row["kind"] not in GRAPH.NODE_KINDS:
        raise ValueError("provider node kind is unsupported")
    label = row["label"]
    if not isinstance(label, str) or not label.strip():
        raise ValueError("provider node label is required")
    label = BUILTIN._safe_graph_text(label)[:256]
    location = row["location"]
    if location is not None and not GRAPH._safe_path(location):
        raise ValueError("provider node path is unsafe")
    confidence = row["confidence"]
    if confidence not in GRAPH.CONFIDENCES:
        raise ValueError("provider node confidence is invalid")
    if GRAPH.CONFIDENCES.index(confidence) < GRAPH.CONFIDENCES.index(result.confidence):
        raise ValueError("provider node upgrades provider confidence")
    source = row["source_sha256"]
    if source is not None and (not isinstance(source, str) or not _HEX64.fullmatch(source)):
        raise ValueError("provider node source digest is invalid")
    domains = tuple(row["risk_domains"])
    if any(domain not in GRAPH.RISK_DOMAINS for domain in domains):
        raise ValueError("provider node risk domain is invalid")
    return key, row["kind"], label, location, confidence, source, domains


def _normalize_candidate_edge(row, result):
    if not isinstance(row, Mapping):
        raise ValueError("provider edge must be an object")
    required = {
        "source",
        "target",
        "kind",
        "location",
        "evidence",
        "confidence",
        "source_sha256",
    }
    if set(row) != required:
        raise ValueError("provider edge shape is unsupported")
    if row["kind"] not in GRAPH.EDGE_KINDS:
        raise ValueError("provider edge kind is unsupported")
    location = row["location"]
    if location is not None and not GRAPH._safe_path(location):
        raise ValueError("provider edge path is unsafe")
    confidence = row["confidence"]
    if confidence not in GRAPH.CONFIDENCES:
        raise ValueError("provider edge confidence is invalid")
    if GRAPH.CONFIDENCES.index(confidence) < GRAPH.CONFIDENCES.index(result.confidence):
        raise ValueError("provider edge upgrades provider confidence")
    source_digest = row["source_sha256"]
    if source_digest is not None and (
        not isinstance(source_digest, str) or not _HEX64.fullmatch(source_digest)
    ):
        raise ValueError("provider edge source digest is invalid")
    evidence = BUILTIN._safe_graph_text(str(row["evidence"]))[:512]
    if not evidence:
        raise ValueError("provider edge evidence is required")
    return (
        row["source"],
        row["target"],
        row["kind"],
        location,
        evidence,
        confidence,
        source_digest,
    )


def _validate_provider_result(result) -> None:
    if any(
        not isinstance(value, str) or _HEX64.fullmatch(value) is None
        for value in result.raw_receipt_sha256
    ):
        raise ValueError("provider raw receipt digest is invalid")
    if result.status != "ready":
        if result.nodes or result.edges:
            raise ValueError("failed provider result must not contain graph evidence")
        return
    keys = set()
    for row in result.nodes:
        key = _normalize_candidate_node(row, result)[0]
        if key in keys:
            raise ValueError("provider node keys must be unique")
        keys.add(key)
    for row in result.edges:
        source, target, *_ = _normalize_candidate_edge(row, result)
        if source not in keys or target not in keys:
            raise ValueError("provider edge references an unknown candidate node")
    for row in result.frontier:
        if not isinstance(row, Mapping):
            raise ValueError("provider frontier must be an object")
        if set(row) != {"node", "reason", "risk_domains"}:
            raise ValueError("provider frontier shape is unsupported")
        if (
            row["node"] not in keys
            or not isinstance(row["reason"], str)
            or not row["reason"].strip()
        ):
            raise ValueError("provider frontier is invalid")
        if any(domain not in GRAPH.RISK_DOMAINS for domain in row["risk_domains"]):
            raise ValueError("provider frontier risk domain is invalid")


def _merge_provider_results(base, results):
    nodes = list(base.nodes)
    edges = list(base.edges)
    paths = list(base.paths)
    frontier = list(base.frontier)
    identity = {(node.kind, node.label, node.location): node.id for node in nodes}
    edge_pairs: dict[tuple[str, str], set[str]] = {}
    for edge in edges:
        edge_pairs.setdefault((edge.source, edge.target), set()).add(edge.kind)
    compacted = False
    disagreements = []
    for result in results:
        if result.status != "ready":
            continue
        if any(
            not isinstance(value, str) or not _HEX64.fullmatch(value)
            for value in result.raw_receipt_sha256
        ):
            continue
        local = {}
        try:
            for row in result.nodes:
                normalized = _normalize_candidate_node(row, result)
                key, kind, label, location, confidence, source, domains = normalized
                node_id = identity.get((kind, label, location))
                if node_id is None:
                    if len(nodes) >= min(GRAPH.MAX_NODES, 999):
                        compacted = True
                        continue
                    node_id = "NODE-%03d" % (len(nodes) + 1)
                    nodes.append(
                        GRAPH.GraphNode(
                            node_id,
                            kind,
                            label,
                            location,
                            result.provider,
                            confidence,
                            source,
                            domains,
                        )
                    )
                    identity[(kind, label, location)] = node_id
                local[key] = node_id
            for row in result.edges:
                normalized = _normalize_candidate_edge(row, result)
                source_key, target_key, kind, location, evidence, confidence, digest = normalized
                source, target = local.get(source_key), local.get(target_key)
                if source is None or target is None:
                    compacted = True
                    continue
                pair = (source, target)
                prior = edge_pairs.setdefault(pair, set())
                if prior and kind not in prior:
                    disagreements.append((target, tuple(sorted(prior | {kind}))))
                signature = (source, target, kind, result.provider)
                if any(
                    (edge.source, edge.target, edge.kind, edge.provider) == signature
                    for edge in edges
                ):
                    continue
                if len(edges) >= min(GRAPH.MAX_EDGES, 999):
                    compacted = True
                    continue
                edges.append(
                    GRAPH.GraphEdge(
                        "EDGE-%03d" % (len(edges) + 1),
                        source,
                        target,
                        kind,
                        location,
                        evidence,
                        confidence,
                        result.provider,
                        digest,
                    )
                )
                prior.add(kind)
        except (TypeError, ValueError):
            compacted = True
            continue
        for row in result.frontier:
            if not isinstance(row, Mapping):
                compacted = True
                continue
            node = local.get(row.get("node"))
            reason = row.get("reason")
            domains = tuple(row.get("risk_domains", ()))
            if (
                node
                and isinstance(reason, str)
                and all(item in GRAPH.RISK_DOMAINS for item in domains)
            ):
                frontier.append(_frontier("FRONTIER-000", node, reason, domains))
    for node, kinds in disagreements:
        domains = next(item.risk_domains for item in nodes if item.id == node)
        frontier.append(
            _frontier(
                "FRONTIER-000",
                node,
                "provider disagreement: " + " versus ".join(kinds),
                domains,
            )
        )
    if compacted and nodes:
        frontier.append(
            _frontier(
                "FRONTIER-000",
                nodes[-1].id,
                "provider output compacted at the graph receipt limit",
                nodes[-1].risk_domains,
            )
        )
    covered_edges = {edge_id for path in paths for edge_id in path.edges}
    node_risks = {node.id: node.risk_domains for node in nodes}
    provider_edges = sorted(
        (edge for edge in edges if edge.provider != "builtin" and edge.id not in covered_edges),
        key=lambda edge: (
            min(
                (_RISK_RANK.get(domain, 99) for domain in node_risks.get(edge.target, ())),
                default=99,
            ),
            edge.id,
        ),
    )
    for edge in provider_edges:
        if len(paths) >= min(GRAPH.MAX_PATHS, 999):
            compacted = True
            break
        domains = set(node_risks.get(edge.source, ()))
        domains.update(node_risks.get(edge.target, ()))
        ordered = tuple(sorted(domains, key=lambda item: (_RISK_RANK.get(item, 99), item)))
        paths.append(
            GRAPH.GraphPath(
                "PATH-%03d" % (len(paths) + 1),
                (edge.source, edge.target),
                (edge.id,),
                1,
                ordered,
            )
        )
    adjacency: dict[str, list[tuple[str, str]]] = {}
    provider_sources = set()
    provider_targets = set()
    for edge in provider_edges:
        adjacency.setdefault(edge.source, []).append((edge.target, edge.id))
        provider_sources.add(edge.source)
        provider_targets.add(edge.target)
    for source in adjacency:
        adjacency[source].sort(key=lambda item: item[1])
    roots = sorted(
        provider_sources - provider_targets or provider_sources,
        key=lambda node_id: (
            min((_RISK_RANK.get(domain, 99) for domain in node_risks.get(node_id, ())), default=99),
            node_id,
        ),
    )
    known_paths = {path.edges for path in paths}
    pending: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
        (root, (root,), ()) for root in reversed(roots)
    ]
    expansions = 0
    while pending and len(paths) < min(GRAPH.MAX_PATHS, 999):
        current, path_nodes, path_edges = pending.pop()
        expansions += 1
        if expansions > GRAPH.MAX_PATHS * 16:
            compacted = True
            break
        if len(path_edges) >= 2 and path_edges not in known_paths:
            domains = {domain for node_id in path_nodes for domain in node_risks.get(node_id, ())}
            ordered = tuple(
                sorted(
                    domains,
                    key=lambda item: (_RISK_RANK.get(item, 99), item),
                )
            )
            paths.append(
                GRAPH.GraphPath(
                    "PATH-%03d" % (len(paths) + 1),
                    path_nodes,
                    path_edges,
                    len(path_edges),
                    ordered,
                )
            )
            known_paths.add(path_edges)
        if len(path_edges) >= 6:
            continue
        for target, edge_id in reversed(adjacency.get(current, ())):
            if target not in path_nodes:
                pending.append(
                    (
                        target,
                        (*path_nodes, target),
                        (*path_edges, edge_id),
                    )
                )
    if pending and len(paths) >= min(GRAPH.MAX_PATHS, 999):
        compacted = True
    return nodes, edges, paths, frontier, compacted or bool(disagreements)


def _renumber_frontier(frontier):
    unique = []
    seen = set()
    for item in sorted(frontier, key=_frontier_sort):
        signature = (item.node, item.reason, item.risk_domains)
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(item)
        if len(unique) >= min(GRAPH.MAX_FRONTIER, 999):
            break
    return tuple(
        GRAPH.FrontierEntry(
            "FRONTIER-%03d" % index,
            item.node,
            item.reason,
            item.risk_domains,
        )
        for index, item in enumerate(unique, start=1)
    )


def _receipt(
    *,
    receipt_id,
    draft_id,
    root,
    request_sha256,
    settings,
    providers,
    nodes,
    edges,
    paths,
    frontier,
    timings,
    status,
    cache,
):
    value = GRAPH.GraphReceipt(
        receipt_id,
        draft_id,
        _repo_identity(root),
        request_sha256,
        settings,
        tuple(providers),
        tuple(nodes),
        tuple(edges),
        tuple(sorted(paths, key=_path_sort)),
        _renumber_frontier(frontier),
        timings,
        status,
        cache,
    )
    GRAPH.canonical_receipt_bytes(value)
    return value


def _private_directory(root: Path) -> Path:
    current = root
    for component in _CONTROL:
        current = current / component
        if current.exists() or current.is_symlink():
            metadata = current.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise ValueError("graph receipt directory must not be a symlink")
        else:
            current.mkdir(mode=0o700)
        os.chmod(current, 0o700)
    return current


def _persist_receipt(root: Path, receipt) -> Path:
    directory = _private_directory(root)
    destination = directory / (receipt.draft_id + ".json")
    if destination.is_symlink():
        raise ValueError("graph receipt path must not be a symlink")
    if destination.exists() and not destination.is_file():
        raise ValueError("graph receipt path must be a regular file")
    payload = GRAPH.canonical_receipt_bytes(receipt)
    worker_token = _DELTA_WORKER_TOKEN
    token_prefix = (
        f"{worker_token}."
        if isinstance(worker_token, str) and re.fullmatch(r"[0-9a-f]{32}", worker_token)
        else ""
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{receipt.draft_id}.{token_prefix}",
        suffix=".tmp",
        dir=str(directory),
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        reopened = os.open(str(destination), flags)
        try:
            metadata = os.fstat(reopened)
            if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
                raise ValueError("persisted graph receipt is not a private regular file")
            actual = bytearray()
            while len(actual) <= GRAPH.MAX_RECEIPT_BYTES:
                chunk = os.read(reopened, min(64 * 1024, GRAPH.MAX_RECEIPT_BYTES + 1 - len(actual)))
                if not chunk:
                    break
                actual.extend(chunk)
        finally:
            os.close(reopened)
        if bytes(actual) != payload:
            raise ValueError("persisted graph receipt digest mismatch")
        loaded, errors = GRAPH.load_receipt_bytes(bytes(actual))
        if loaded is None or errors:
            raise ValueError("persisted graph receipt failed canonical validation")
        if hashlib.sha256(actual).digest() != hashlib.sha256(payload).digest():
            raise ValueError("persisted graph receipt digest mismatch")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return destination


def receipt_sha256(path) -> str:
    target = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(target), flags)
    except OSError as error:
        raise ValueError("graph receipt must be a regular non-symlink file") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("graph receipt must be a regular non-symlink file")
        if metadata.st_size > GRAPH.MAX_RECEIPT_BYTES:
            raise ValueError("graph receipt exceeds maximum byte size")
        payload = bytearray()
        while len(payload) <= GRAPH.MAX_RECEIPT_BYTES:
            chunk = os.read(
                descriptor,
                min(64 * 1024, GRAPH.MAX_RECEIPT_BYTES + 1 - len(payload)),
            )
            if not chunk:
                break
            payload.extend(chunk)
    finally:
        os.close(descriptor)
    payload_bytes = bytes(payload)
    loaded, errors = GRAPH.load_receipt_bytes(payload_bytes)
    if loaded is None or errors:
        raise ValueError("graph receipt is invalid")
    return hashlib.sha256(payload_bytes).hexdigest()


def _unavailable_frontier(nodes, probes, provider_results):
    if not nodes:
        return []
    unavailable = [probe.name for probe in probes if probe.status != "ready"]
    unavailable.extend(result.provider for result in provider_results if result.status != "ready")
    if not unavailable:
        return []
    node = min(
        nodes,
        key=lambda item: (
            min((_RISK_RANK.get(domain, 99) for domain in item.risk_domains), default=99),
            item.id,
        ),
    )
    return [
        _frontier(
            "FRONTIER-000",
            node.id,
            "provider unavailable; built-in fallback used: " + ", ".join(sorted(set(unavailable))),
            node.risk_domains,
        )
    ]


def trace_impact(
    repo_root,
    draft,
    seeds,
    settings,
    clock=time,
    runner=None,
    deadline=None,
    source_inventory=None,
):
    """Return and privately persist one bounded canonical graph receipt."""
    settings = _settings(settings)
    normalized_seeds = tuple(sorted(set(seeds), key=_seed_key))
    if any(not isinstance(seed, ScanSeed) for seed in normalized_seeds):
        raise TypeError("seeds must contain ScanSeed values")
    if deadline is None:
        deadline = Deadline(clock, settings.max_seconds)
    elif not isinstance(deadline, Deadline):
        raise TypeError("deadline must be a provider Deadline")
    elif deadline.clock is not clock or deadline.max_seconds != settings.max_seconds:
        raise ValueError("shared deadline must match graph clock and settings")
    if source_inventory is None:
        source_inventory = _collect_source_digests(Path(repo_root), deadline)
    elif not isinstance(source_inventory, SourceInventory):
        raise TypeError("source_inventory must be a SourceInventory")
    draft_id = _draft_id(draft)
    request_sha256 = _request_sha256(draft, normalized_seeds, settings)
    root_input = Path(repo_root)
    workspace = not root_input.is_symlink() and root_input.is_dir()
    root = root_input.resolve() if workspace else root_input.absolute()
    if not workspace:
        trace_identity = _trace_identity(
            root,
            draft_id,
            request_sha256,
            normalized_seeds,
            settings,
            (),
        )
        nodes = [_placeholder(seed, index) for index, seed in enumerate(normalized_seeds, start=1)]
        if not nodes:
            nodes = [
                GRAPH.GraphNode(
                    "NODE-001",
                    "file",
                    "workspace unavailable",
                    None,
                    "builtin",
                    "lexical",
                    None,
                    ("functionality",),
                )
            ]
        frontier = [
            _frontier(
                "FRONTIER-001",
                node.id,
                "supplied-only evidence; workspace unavailable",
                node.risk_domains,
            )
            for node in nodes[: GRAPH.MAX_FRONTIER]
        ]
        return _receipt(
            receipt_id=trace_identity,
            draft_id=draft_id,
            root=root,
            request_sha256=request_sha256,
            settings=settings,
            providers=(_builtin_status(),),
            nodes=nodes,
            edges=(),
            paths=(),
            frontier=frontier,
            timings={"total": deadline.elapsed_ms()},
            status="no_workspace",
            cache={
                "status": "miss",
                "key": "0" * 64,
                "invalidated_nodes": [],
            },
        )

    requested = tuple(item for item in settings.providers if item != "builtin")
    probes: tuple[ProviderProbe, ...] = ()
    if settings.enabled and requested and not deadline.expired():
        probes = discover_providers(
            root,
            requested,
            deadline,
            runner=runner,
            deep=settings.deep,
        )
        probes = tuple(
            sorted(
                probes,
                key=lambda item: (
                    _PROVIDER_RANK.get(item.name, 99),
                    item.name,
                ),
            )
        )

    trace_identity = _trace_identity(
        root,
        draft_id,
        request_sha256,
        normalized_seeds,
        settings,
        probes,
    )
    cache_result = (
        _load_cache(
            root,
            source_inventory.digests,
            probes,
            trace_identity,
            draft_id,
            request_sha256,
            settings,
        )
        if source_inventory.complete and not deadline.expired()
        else CACHE.CacheResult("miss", "0" * 64, None, ())
    )
    if cache_result.status == "hit" and cache_result.receipt is not None:
        cached = _receipt_from_mapping(cache_result.receipt)
        cached = replace(
            cached,
            timings_ms={**dict(cached.timings_ms), "total": deadline.elapsed_ms()},
            cache={
                "status": "hit",
                "key": cache_result.key,
                "invalidated_nodes": [],
            },
        )
        GRAPH.canonical_receipt_bytes(cached)
        _persist_receipt(root, cached)
        if cached.budget_status == "closed" or not cached.frontier:
            return cached

    prepared_probes: list[ProviderProbe] = []
    prepared_adapters: dict[str, _Adapter] = {}
    for probe in probes:
        if deadline.expired():
            prepared_probes.append(
                replace(
                    probe,
                    status="timed_out",
                    confidence="lexical",
                    detail="shared deadline exhausted before provider probe",
                )
            )
            continue
        if probe.status != "ready":
            prepared_probes.append(probe)
            continue
        adapter = _adapter(probe.name)
        if adapter is None:
            prepared_probes.append(
                replace(
                    probe,
                    status="unsupported",
                    confidence="lexical",
                    detail="provider adapter is unavailable",
                )
            )
            continue
        try:
            specific = adapter.probe(
                ProviderSpec(probe.name, probe.executable),
                root,
                deadline,
                runner,
            )
            if not isinstance(specific, ProviderProbe) or specific.name != probe.name:
                raise ValueError("provider adapter returned an invalid probe")
            specific = replace(
                specific,
                executable=probe.executable,
                version=probe.version,
                executable_sha256=probe.executable_sha256,
                repo_root=root,
            )
        except Exception as error:
            specific = replace(
                probe,
                status="failed",
                confidence="lexical",
                detail=str(error)[:512],
            )
        prepared_probes.append(specific)
        prepared_adapters[probe.name] = adapter
    probes = tuple(prepared_probes)

    provider_results: list[ProviderResult] = []
    final_probes: list[ProviderProbe] = list(probes)
    for index, probe in enumerate(probes):
        if deadline.expired():
            for remaining in range(index, len(final_probes)):
                if final_probes[remaining].status == "ready":
                    final_probes[remaining] = replace(
                        final_probes[remaining],
                        status="timed_out",
                        confidence="lexical",
                        detail="shared deadline exhausted before provider query",
                    )
            break
        if probe.status != "ready":
            continue
        adapter = prepared_adapters[probe.name]
        try:
            result = adapter.query(probe, normalized_seeds, deadline, runner)
            if not isinstance(result, ProviderResult) or result.provider != probe.name:
                raise ValueError("provider adapter returned an invalid result")
            _validate_provider_result(result)
        except Exception as error:
            result = ProviderResult(
                probe.name,
                "failed",
                "lexical",
                detail=str(error)[:512],
            )
        provider_results.append(result)
        if result.status != "ready":
            final_probes[index] = replace(
                probe,
                status=result.status,
                confidence=result.confidence,
                detail=result.detail,
            )

    if deadline.expired():
        scan = BUILTIN.BuiltInScanResult((), (), (), (), {}, {}, 0, 0, "budget_exhausted")
    else:
        remaining = min(settings.max_seconds, max(0, int(deadline.remaining())))
        scan = BUILTIN.scan_repository(
            root,
            normalized_seeds,
            ScanLimits(max_seconds=remaining),
            clock,
        )
    nodes, edges, paths, frontier, limited = _merge_provider_results(scan, provider_results)
    frontier.extend(_unavailable_frontier(nodes, final_probes, provider_results))
    if limited and nodes:
        # Compaction or provider disagreement is a coverage gap; it must be
        # visible even when provider-unavailable entries already exist,
        # because promotion treats a frontier made solely of those
        # disclosures as complete built-in coverage.
        frontier.append(
            _frontier(
                "FRONTIER-000",
                nodes[0].id,
                "graph coverage remains incomplete: provider results were compacted or disagreed",
                nodes[0].risk_domains,
            )
        )
    if not source_inventory.complete:
        if not nodes and normalized_seeds:
            nodes = [_placeholder(normalized_seeds[0], 1)]
        if nodes:
            frontier.append(
                _frontier(
                    "FRONTIER-000",
                    nodes[0].id,
                    "source inventory incomplete: " + str(source_inventory.reason),
                    nodes[0].risk_domains,
                )
            )
    supplied_only_ids = {
        node.id for node in nodes if node.location is None and node.provider == "builtin"
    }
    for node_id in sorted(supplied_only_ids):
        node = next(item for item in nodes if item.id == node_id)
        frontier.append(
            _frontier(
                "FRONTIER-000",
                node.id,
                "supplied-only evidence requires repository verification",
                node.risk_domains,
            )
        )
    if (
        deadline.expired()
        or scan.budget_status == "budget_exhausted"
        or source_inventory.reason == "deadline"
    ):
        status = "budget_exhausted"
        if not nodes and normalized_seeds:
            nodes = [_placeholder(normalized_seeds[0], 1)]
        if nodes and not frontier:
            ranked = min(
                nodes,
                key=lambda item: (
                    min((_RISK_RANK.get(domain, 99) for domain in item.risk_domains), default=99),
                    item.id,
                ),
            )
            frontier.append(
                _frontier(
                    "FRONTIER-000",
                    ranked.id,
                    "shared graph deadline exhausted",
                    ranked.risk_domains,
                )
            )
    elif (
        scan.budget_status == "provider_limited"
        or not source_inventory.complete
        or frontier
        or limited
    ):
        status = "provider_limited"
    else:
        status = "closed"
    if status != "closed" and not frontier and nodes:
        frontier.append(
            _frontier(
                "FRONTIER-000",
                nodes[0].id,
                "graph coverage remains incomplete",
                nodes[0].risk_domains,
            )
        )

    providers = [_provider_status(item) for item in final_probes]
    providers.append(_builtin_status())
    invalidated = tuple(
        item for item in cache_result.invalidated_nodes if any(node.id == item for node in nodes)
    )
    interim_cache = {
        "status": cache_result.status,
        "key": cache_result.key,
        "invalidated_nodes": list(invalidated),
    }
    receipt = _receipt(
        receipt_id=trace_identity,
        draft_id=draft_id,
        root=root,
        request_sha256=request_sha256,
        settings=settings,
        providers=providers,
        nodes=nodes,
        edges=edges,
        paths=paths,
        frontier=frontier,
        timings={"total": deadline.elapsed_ms()},
        status=status,
        cache=interim_cache,
    )
    try:
        published = CACHE.publish(
            root,
            receipt,
            source_inventory.digests,
            inventory_complete=source_inventory.complete,
            inventory_reason=source_inventory.reason,
        )
        receipt = replace(
            receipt,
            cache={
                "status": cache_result.status,
                "key": published.key,
                "invalidated_nodes": list(invalidated),
            },
        )
        GRAPH.canonical_receipt_bytes(receipt)
    except ValueError:
        pass
    _persist_receipt(root, receipt)
    return receipt


__all__ = [
    "Deadline",
    "GraphSettings",
    "ProviderProbe",
    "ProviderQuery",
    "ProviderResult",
    "ProviderSpec",
    "ScanLimits",
    "ScanSeed",
    "SourceInventory",
    "discover_providers",
    "receipt_sha256",
    "run_provider",
    "trace_impact",
]
