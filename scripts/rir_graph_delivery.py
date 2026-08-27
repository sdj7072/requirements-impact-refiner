#!/usr/bin/env python3
"""Graph receipt binding, compact delivery, coverage, and trace orchestration."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable, Protocol, SupportsInt, TypedDict, cast

if TYPE_CHECKING:
    from graph_builtin import (
        BuiltInScanResult as BuiltInScanResultType,
    )
    from graph_builtin import ScanLimits as ScanLimitsType
    from graph_builtin import ScanSeed as ScanSeedType
    from graph_cache import CacheResult as CacheResultType
    from graph_coordinator import SourceInventory as SourceInventoryType
    from graph_providers import Deadline as DeadlineType
    from graph_providers import ProviderProbe as ProviderProbeType
    from graph_providers import ProviderQuery as ProviderQueryType
    from graph_providers import ProviderResult as ProviderResultType
    from graph_providers import ProviderSpec as ProviderSpecType
    from impact_graph import FrontierEntry as FrontierEntryType
    from impact_graph import GraphEdge as GraphEdgeType
    from impact_graph import GraphNode as GraphNodeType
    from impact_graph import GraphPath as GraphPathType
    from impact_graph import GraphReceipt as GraphReceiptType
    from impact_graph import GraphSettings as GraphSettingsType
    from impact_graph import ProviderStatus as ProviderStatusType
    from rir_contracts import TraceRequest, TraceResult
    from typing_extensions import TypeGuard


class _FcntlContract(Protocol):
    LOCK_EX: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, fd: int, operation: int) -> None: ...


class _ContractsContract(Protocol):
    MAX_STRING_BYTES: int
    MAX_TRACE_BYTES: int
    TraceRequest: type
    TraceResult: type

    def _local_key(self, value: object, label: str) -> str: ...

    def bounded_bytes(self, value: object, maximum: int, label: str) -> bytes: ...

    def canonical_bytes(self, value: object) -> bytes: ...


class _StorageContract(Protocol):
    DRAFT_ID_PATTERN: re.Pattern[str]
    fcntl: _FcntlContract | None

    def root_path(self, path: Path) -> Path: ...

    def load_private_draft(self, repo_root: Path, draft_id: str) -> dict[str, object]: ...

    def cas_replace_private_draft(
        self, root: Path, draft_id: str, expected: bytes, replacement: bytes
    ) -> None: ...

    def recover_private_draft_transaction(self, root: Path, draft_id: str) -> None: ...

    def report_lock(self, root: Path, report_id: str, deadline: object = None): ...

    def _read_bounded_descriptor(self, descriptor: int, maximum: int, label: str) -> bytes: ...

    def _open_optional_transaction_component(
        self, directory_fd: int, name: str, maximum: int, label: str
    ): ...

    def _open_transaction_component_for_cleanup(
        self, directory_fd: int, name: str, maximum: int, label: str
    ): ...

    def _same_inode(self, first, second) -> bool: ...

    def _rename_noreplace(self, directory_fd: int, source: str, destination: str) -> None: ...

    def _unlink_transaction_component(self, *args, **kwargs) -> None: ...

    def _write_private_transaction_component(self, *args, **kwargs): ...


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

    def validate_receipt(self, value: object) -> tuple[str, ...]: ...

    def canonical_receipt_bytes(self, value: Mapping[str, object] | GraphReceiptType) -> bytes: ...

    def load_receipt_bytes(
        self, payload: bytes
    ) -> tuple[dict[str, object] | None, tuple[str, ...]]: ...


class _BuiltinContract(Protocol):
    GRAPH: _GraphContract
    ScanSeed: type[ScanSeedType]
    ScanLimits: type[ScanLimitsType]
    BuiltInScanResult: type[BuiltInScanResultType]
    DEFAULT_MAX_FILE_BYTES: int

    def _read_regular_file(self, *args, **kwargs): ...

    def _safe_graph_text(self, *args, **kwargs) -> str: ...

    def _walk_files(self, *args, **kwargs): ...

    def scan_repository(self, *args, **kwargs) -> BuiltInScanResultType: ...


class _CacheContract(Protocol):
    CacheResult: type[CacheResultType]
    GRAPH: _GraphContract
    _IDENTITY_FIELDS: frozenset[str]

    def _cache_directory(self, root: Path, create: bool) -> Path | None: ...

    def _read_artifact(self, path: Path) -> Mapping[str, object] | None: ...

    def _source_digests(self, value: Mapping[str, str]) -> dict[str, str]: ...

    def _canonical_json(self, value: object) -> bytes: ...

    def _normalize_receipt(self, value: object) -> tuple[dict[str, object], bytes]: ...

    def load(self, *args, **kwargs) -> CacheResultType: ...

    def publish(self, *args, **kwargs) -> CacheResultType: ...


class _ProviderContract(Protocol):
    PROVIDER_PRIORITY: tuple[str, ...]
    Deadline: type[DeadlineType]
    ProviderProbe: type[ProviderProbeType]
    ProviderQuery: type[ProviderQueryType]
    ProviderResult: type[ProviderResultType]
    ProviderSpec: type[ProviderSpecType]

    def discover_providers(self, *args, **kwargs): ...

    def run_provider(self, *args, **kwargs): ...


class _GraphCoordinatorContract(Protocol):
    GRAPH: _GraphContract
    BUILTIN: _BuiltinContract
    CACHE: _CacheContract
    PROVIDERS: _ProviderContract
    ScanSeed: type[ScanSeedType]
    Deadline: type[DeadlineType]

    def _settings(self, value: Mapping[str, object]) -> GraphSettingsType: ...

    def _request_sha256(
        self,
        draft: Mapping[str, object],
        seeds: tuple[ScanSeedType, ...],
        settings: GraphSettingsType,
    ) -> str: ...

    def _seed_key(self, seed: ScanSeedType) -> tuple[int, str, str]: ...

    def _trace_identity(
        self,
        root: Path,
        draft_id: str,
        request_sha256: str,
        seeds: tuple[ScanSeedType, ...],
        settings: GraphSettingsType,
        probes: tuple[ProviderStatusType, ...],
    ) -> str: ...

    def _collect_source_digests(
        self, root: Path, deadline: DeadlineType
    ) -> SourceInventoryType: ...

    def trace_impact(self, *args, **kwargs) -> GraphReceiptType: ...


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def _regular_module_path(path: Path) -> Path | None:
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        return None
    return resolved


def _module_uses_sibling(value: object, expected: Path) -> bool:
    module_file = getattr(value, "__file__", None)
    return isinstance(module_file, str) and _regular_module_path(Path(module_file)) == expected


def _classes(value: object, names: Sequence[str]) -> bool:
    return all(isinstance(getattr(value, name, None), type) for name in names)


def _callables(value: object, names: Sequence[str]) -> bool:
    return all(callable(getattr(value, name, None)) for name in names)


def _is_fcntl_contract(value: object) -> TypeGuard[_FcntlContract]:
    return all(
        isinstance(getattr(value, name, None), int) for name in ("LOCK_EX", "LOCK_NB", "LOCK_UN")
    ) and callable(getattr(value, "flock", None))


def _is_contracts_contract(value: object) -> TypeGuard[_ContractsContract]:
    return (
        all(
            type(getattr(value, name, None)) is int and getattr(value, name) > 0
            for name in ("MAX_STRING_BYTES", "MAX_TRACE_BYTES")
        )
        and _classes(value, ("TraceRequest", "TraceResult"))
        and _callables(value, ("_local_key", "bounded_bytes", "canonical_bytes"))
    )


def _is_storage_contract(value: object) -> TypeGuard[_StorageContract]:
    storage_fcntl = getattr(value, "fcntl", None)
    return (
        isinstance(getattr(value, "DRAFT_ID_PATTERN", None), re.Pattern)
        and hasattr(value, "fcntl")
        and (storage_fcntl is None or _is_fcntl_contract(storage_fcntl))
        and _callables(
            value,
            (
                "root_path",
                "load_private_draft",
                "cas_replace_private_draft",
                "recover_private_draft_transaction",
                "report_lock",
                "_read_bounded_descriptor",
                "_open_optional_transaction_component",
                "_open_transaction_component_for_cleanup",
                "_same_inode",
                "_rename_noreplace",
                "_unlink_transaction_component",
                "_write_private_transaction_component",
            ),
        )
    )


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
            (
                "_safe_path",
                "_validate_settings",
                "validate_receipt",
                "canonical_receipt_bytes",
                "load_receipt_bytes",
            ),
        )
    )


def _is_builtin_contract(value: object) -> TypeGuard[_BuiltinContract]:
    return (
        _is_graph_contract(getattr(value, "GRAPH", None))
        and _classes(value, ("ScanSeed", "ScanLimits", "BuiltInScanResult"))
        and isinstance(getattr(value, "DEFAULT_MAX_FILE_BYTES", None), int)
        and _callables(
            value,
            ("_read_regular_file", "_safe_graph_text", "_walk_files", "scan_repository"),
        )
    )


def _is_cache_contract(value: object) -> TypeGuard[_CacheContract]:
    return (
        _classes(value, ("CacheResult",))
        and _is_graph_contract(getattr(value, "GRAPH", None))
        and isinstance(getattr(value, "_IDENTITY_FIELDS", None), frozenset)
        and _callables(
            value,
            (
                "_cache_directory",
                "_read_artifact",
                "_source_digests",
                "_canonical_json",
                "_normalize_receipt",
                "load",
                "publish",
            ),
        )
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


def _is_graph_coordinator_contract(value: object) -> TypeGuard[_GraphCoordinatorContract]:
    return (
        _is_graph_contract(getattr(value, "GRAPH", None))
        and _is_builtin_contract(getattr(value, "BUILTIN", None))
        and _is_cache_contract(getattr(value, "CACHE", None))
        and _is_provider_contract(getattr(value, "PROVIDERS", None))
        and _classes(value, ("ScanSeed", "Deadline"))
        and _callables(
            value,
            (
                "_settings",
                "_request_sha256",
                "_seed_key",
                "_trace_identity",
                "_collect_source_digests",
                "trace_impact",
            ),
        )
    )


def _execute_registered(
    module_name: str,
    expected: Path,
    validator: Callable[[object], bool],
    label: str,
    aliases: Mapping[str, ModuleType] | None = None,
) -> object:
    specification = importlib.util.spec_from_file_location(module_name, expected)
    if specification is None or specification.loader is None:
        raise ImportError(f"cannot load fixed graph delivery {label} sibling")
    module = importlib.util.module_from_spec(specification)
    previous = {name: (name in sys.modules, sys.modules.get(name)) for name in (aliases or {})}
    sys.modules[module_name] = module
    try:
        if aliases:
            sys.modules.update(aliases)
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError(f"cannot load fixed graph delivery {label} sibling") from error
    finally:
        for name, (present, value) in previous.items():
            if name == module_name:
                continue
            if present:
                sys.modules[name] = cast(ModuleType, value)
            else:
                sys.modules.pop(name, None)
    if not validator(module):
        sys.modules.pop(module_name, None)
        raise ImportError(f"graph delivery {label} sibling contract is incomplete")
    return module


def _load_fixed_sibling(
    filename: str,
    canonical_name: str,
    prefix: str,
    validator: Callable[[object], bool],
    label: str,
    aliases: Mapping[str, ModuleType] | None = None,
) -> object:
    sibling = SCRIPT_DIR / filename
    expected = _regular_module_path(sibling)
    if expected is None or expected != sibling:
        raise ImportError(f"graph delivery {label} sibling is unsafe")
    hashed_name = prefix + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    hashed_present = hashed_name in sys.modules
    hashed = sys.modules.get(hashed_name)
    if canonical_name not in sys.modules:
        if hashed_present:
            if not _module_uses_sibling(hashed, expected):
                raise ImportError(f"graph delivery {label} sibling is unsafe")
            if not validator(hashed):
                raise ImportError(f"graph delivery {label} sibling contract is incomplete")
            sys.modules[canonical_name] = cast(ModuleType, hashed)
            return hashed
        return _execute_registered(canonical_name, expected, validator, label, aliases=aliases)
    canonical = sys.modules.get(canonical_name)
    if _module_uses_sibling(canonical, expected):
        if not validator(canonical):
            raise ImportError(f"graph delivery {label} sibling contract is incomplete")
        if not hashed_present:
            return canonical
        if not _module_uses_sibling(hashed, expected):
            raise ImportError(f"graph delivery {label} sibling is unsafe")
        if not validator(hashed):
            raise ImportError(f"graph delivery {label} sibling contract is incomplete")
        return hashed
    if hashed_present:
        if not _module_uses_sibling(hashed, expected):
            raise ImportError(f"graph delivery {label} sibling is unsafe")
        if not validator(hashed):
            raise ImportError(f"graph delivery {label} sibling contract is incomplete")
        return hashed
    return _execute_registered(hashed_name, expected, validator, label, aliases=aliases)


CONTRACTS = cast(
    _ContractsContract,
    _load_fixed_sibling(
        "rir_contracts.py",
        "rir_contracts",
        "_rir_graph_delivery_contracts_",
        _is_contracts_contract,
        "contracts",
    ),
)
STORAGE = cast(
    _StorageContract,
    _load_fixed_sibling(
        "rir_storage.py",
        "rir_storage",
        "_rir_graph_delivery_storage_",
        _is_storage_contract,
        "storage",
    ),
)

_loaded_graph = cast(
    ModuleType,
    _load_fixed_sibling(
        "impact_graph.py",
        "_rir_impact_graph",
        "_rir_graph_delivery_schema_",
        _is_graph_contract,
        "schema",
    ),
)
_graph_alias = {"_rir_impact_graph": _loaded_graph}
_loaded_builtin = cast(
    ModuleType,
    _load_fixed_sibling(
        "graph_builtin.py",
        "_rir_graph_builtin",
        "_rir_graph_delivery_builtin_",
        _is_builtin_contract,
        "builtin",
        aliases=_graph_alias,
    ),
)
_loaded_cache = cast(
    ModuleType,
    _load_fixed_sibling(
        "graph_cache.py",
        "_rir_graph_cache",
        "_rir_graph_delivery_cache_",
        _is_cache_contract,
        "cache",
        aliases=_graph_alias,
    ),
)
_loaded_providers = cast(
    ModuleType,
    _load_fixed_sibling(
        "graph_providers.py",
        "_rir_graph_providers",
        "_rir_graph_delivery_providers_",
        _is_provider_contract,
        "providers",
    ),
)


def _load_graph_coordinator() -> object:
    sibling = SCRIPT_DIR / "graph_coordinator.py"
    expected = _regular_module_path(sibling)
    if expected is None or expected != sibling:
        raise ImportError("graph delivery coordinator sibling is unsafe")
    module_name = (
        "_rir_graph_delivery_coordinator_"
        + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    )
    loaded_present = module_name in sys.modules
    loaded = sys.modules.get(module_name)
    if loaded_present:
        if not _module_uses_sibling(loaded, expected):
            raise ImportError("graph delivery coordinator sibling is unsafe")
        if not _is_graph_coordinator_contract(loaded):
            raise ImportError("graph delivery coordinator sibling contract is incomplete")
        local_dependencies = (
            (loaded.GRAPH, "impact_graph.py"),
            (loaded.BUILTIN, "graph_builtin.py"),
            (loaded.CACHE, "graph_cache.py"),
            (loaded.PROVIDERS, "graph_providers.py"),
        )
        if (
            any(
                not _module_uses_sibling(module, SCRIPT_DIR / filename)
                for module, filename in local_dependencies
            )
            or loaded.BUILTIN.GRAPH is not loaded.GRAPH
            or loaded.CACHE.GRAPH is not loaded.GRAPH
        ):
            raise ImportError("graph delivery coordinator sibling wiring is invalid")
        return loaded
    aliases = {
        "_rir_impact_graph": _loaded_graph,
        "_rir_graph_builtin": _loaded_builtin,
        "_rir_graph_cache": _loaded_cache,
        "_rir_graph_providers": _loaded_providers,
    }
    module = cast(
        Any,
        _execute_registered(
            module_name,
            expected,
            _is_graph_coordinator_contract,
            "coordinator",
            aliases=aliases,
        ),
    )
    if (
        module.GRAPH is not _loaded_graph
        or module.BUILTIN is not _loaded_builtin
        or module.CACHE is not _loaded_cache
        or module.PROVIDERS is not _loaded_providers
    ):
        sys.modules.pop(module_name, None)
        raise ImportError("graph delivery coordinator sibling wiring is invalid")
    return module


GRAPH_COORDINATOR = cast(_GraphCoordinatorContract, _load_graph_coordinator())
GRAPH = GRAPH_COORDINATOR.GRAPH
TraceSeed = GRAPH_COORDINATOR.ScanSeed
if not TYPE_CHECKING:
    TraceRequest = CONTRACTS.TraceRequest
    TraceResult = CONTRACTS.TraceResult

MAX_STRING_BYTES = CONTRACTS.MAX_STRING_BYTES
MAX_TRACE_BYTES = CONTRACTS.MAX_TRACE_BYTES
DRAFT_ID_PATTERN = STORAGE.DRAFT_ID_PATTERN
_local_key = CONTRACTS._local_key
_bounded = CONTRACTS.bounded_bytes
_canonical_bytes = CONTRACTS.canonical_bytes
_root = STORAGE.root_path
load_draft = STORAGE.load_private_draft
_recover_private_draft_transaction = STORAGE.recover_private_draft_transaction
_report_lock = STORAGE.report_lock
_read_bounded_descriptor = STORAGE._read_bounded_descriptor
_open_optional_transaction_component = STORAGE._open_optional_transaction_component
_open_transaction_component_for_cleanup = STORAGE._open_transaction_component_for_cleanup
_same_inode = STORAGE._same_inode
_rename_noreplace = STORAGE._rename_noreplace
_unlink_transaction_component = STORAGE._unlink_transaction_component
_write_private_transaction_component = STORAGE._write_private_transaction_component


def _cas_replace_private_draft(
    root: Path,
    draft_id: str,
    expected: Mapping[str, object],
    replacement: Mapping[str, object],
) -> None:
    STORAGE.cas_replace_private_draft(
        root,
        draft_id,
        _canonical_bytes(expected),
        _canonical_bytes(replacement),
    )


MAX_TRACE_SEEDS = 128
HIGH_RISK_DOMAINS = {
    "authorization/privacy",
    "legal/policy",
    "data",
    "interfaces",
    "operations",
    "state/concurrency",
}
EVIDENCE_RANK = {"verified": 0, "inferred": 1, "unknown": 2}
GRAPH_CONFIDENCE_RANK = {
    "verified-provider": 0,
    "verified-source": 1,
    "structural-inferred": 2,
    "lexical": 3,
}


class GraphSettingsPayload(TypedDict):
    enabled: bool
    max_seconds: int
    target_seconds: int
    providers: list[str]
    install_policy: str
    deep: bool


class ProviderPayload(TypedDict):
    name: str
    status: str
    confidence: str
    version: str | None
    executable_sha256: str | None


class NodePayload(TypedDict):
    id: str
    kind: str
    label: str
    location: str | None
    provider: str
    confidence: str
    source_sha256: str | None
    risk_domains: list[str]


class EdgePayload(TypedDict):
    id: str
    source: str
    target: str
    kind: str
    location: str | None
    evidence: str
    confidence: str
    provider: str
    source_sha256: str | None


class PathPayload(TypedDict):
    id: str
    nodes: list[str]
    edges: list[str]
    distance: int
    risk_domains: list[str]


class FrontierPayload(TypedDict):
    id: str
    node: str
    reason: str
    risk_domains: list[str]


class CachePayload(TypedDict):
    status: str
    key: str
    invalidated_nodes: list[str]


class ReceiptPayload(TypedDict):
    schema_version: int
    receipt_id: str
    draft_id: str
    repo_root_sha256: str
    request_sha256: str
    settings: GraphSettingsPayload
    providers: list[ProviderPayload]
    nodes: list[NodePayload]
    edges: list[EdgePayload]
    paths: list[PathPayload]
    frontier: list[FrontierPayload]
    timings_ms: dict[str, int]
    budget_status: str
    cache: CachePayload


class CompactNodePayload(TypedDict):
    key: str
    kind: str
    label: str
    location: str | None
    confidence: str
    risk_domains: list[str]


class CompactPathNodePayload(TypedDict):
    key: str
    label: str
    location: str | None


class CompactPathEdgePayload(TypedDict):
    key: str
    kind: str
    confidence: str


class CompactPathPayload(TypedDict):
    key: str
    nodes: list[CompactPathNodePayload]
    edges: list[CompactPathEdgePayload]
    distance: int
    risk_domains: list[str]


class CompactFrontierPayload(TypedDict):
    key: str
    node_key: str
    reason: str
    risk_domains: list[str]


class CompactTruncatedPayload(TypedDict):
    nodes: int
    paths: int
    frontier: int


class CompactSummaryPayload(TypedDict):
    nodes: int
    edges: int
    paths: int
    unknown_frontiers: int
    timings_ms: dict[str, int]
    budget_status: str
    truncated: CompactTruncatedPayload


class CompactGraphPayload(TypedDict):
    providers: list[dict[str, str | None]]
    nodes: list[CompactNodePayload]
    paths: list[CompactPathPayload]
    frontier: list[CompactFrontierPayload]
    summary: CompactSummaryPayload


class GraphContext(TypedDict, total=False):
    receipt: ReceiptPayload
    sha256: str
    binding: dict[str, object]
    source_inventory: dict[str, object]
    impact_paths: dict[str, list[str]]
    rationales: dict[str, str | None]
    impact_confidences: dict[str, str]


def _is_receipt_payload(value: object) -> TypeGuard[ReceiptPayload]:
    return isinstance(value, dict) and not GRAPH.validate_receipt(value)


def _is_string_mapping(value: object) -> TypeGuard[Mapping[str, str]]:
    return isinstance(value, Mapping) and all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    )


def _is_int_input(value: object) -> TypeGuard[str | bytes | bytearray | SupportsInt]:
    return isinstance(value, (str, bytes, bytearray)) or callable(getattr(value, "__int__", None))


def _int_value(value: object) -> int:
    if not _is_int_input(value):
        raise TypeError(
            "int() argument must be a string, a bytes-like object or a real number, "
            f"not '{type(value).__name__}'"
        )
    return int(value)


_RUNTIME_KEYS = frozenset(
    {
        "clock",
        "trace_result",
        "root_path",
        "bounded_bytes",
        "load_draft",
        "cas_replace_private_draft",
        "recover_private_draft_transaction",
        "report_lock",
        "read_bounded_descriptor",
        "open_optional_transaction_component",
        "open_transaction_component_for_cleanup",
        "same_inode",
        "rename_noreplace",
        "unlink_transaction_component",
        "write_private_transaction_component",
        "graph_draft_identity",
        "compact_graph",
        "source_inventory_sha256",
        "receipt_source_inventory",
        "verify_source_inventory",
        "trace_intent_sha256",
        "new_trace_intent",
        "validate_trace_intent",
        "read_bound_receipt_bytes",
        "remove_exact_trace_receipt",
        "recover_stale_cleanup_guard",
        "clear_trace_intent",
        "load_graph_context",
        "validate_persisted_trace_receipt",
        "bind_trace_receipt",
    }
)


def _resolve_runtime(runtime: Mapping[str, object] | None) -> Mapping[str, object]:
    resolved = _default_runtime() if runtime is None else runtime
    if not isinstance(resolved, Mapping) or set(resolved) != _RUNTIME_KEYS:
        raise TypeError("graph delivery runtime wiring is incomplete")
    if not callable(getattr(resolved["clock"], "monotonic", None)) or not all(
        callable(resolved[name]) for name in _RUNTIME_KEYS - {"clock"}
    ):
        raise TypeError("graph delivery runtime wiring is incomplete")
    return resolved


def _operation(runtime: Mapping[str, object], name: str) -> Callable[..., Any]:
    return cast(Callable[..., Any], runtime[name])


def graph_draft_identity(draft: Mapping[str, object]) -> dict[str, object]:
    keys = (
        "schema_version",
        "draft_id",
        "repo_root",
        "request",
        "request_sha256",
        "repository_evidence",
        "adapter",
        "settings",
        "report_id",
        "revision",
        "previous_sha256",
        "prior_state",
        "prior_key_map",
        "created_at",
    )
    try:
        identity = {key: draft[key] for key in keys}
    except KeyError as error:
        raise ValueError(f"draft graph identity is missing {error.args[0]}") from error
    request = identity["request"]
    if (
        not isinstance(request, str)
        or identity["request_sha256"] != hashlib.sha256(request.encode("utf-8")).hexdigest()
    ):
        raise ValueError("draft request identity is invalid")
    return identity


# Compact delivery exists to fit a model turn: bound every list and
# disclose exactly what was dropped — a silent cap would read as full
# coverage when it is not.
COMPACT_MAX_NODES = 48
COMPACT_MAX_PATHS = 16
COMPACT_MAX_FRONTIER = 16
COMPACT_MAX_BYTES = 24_000
_COMPACT_RISK_ORDER = (
    "authorization/privacy",
    "interfaces",
    "data",
    "state/concurrency",
    "compatibility",
    "operations",
    "regression",
    "functionality",
    "legal/policy",
)
_COMPACT_RISK_RANK = {name: index for index, name in enumerate(_COMPACT_RISK_ORDER)}


def _compact_node_rank(row: NodePayload) -> tuple[int, str]:
    domains = row.get("risk_domains", ())
    best = min((_COMPACT_RISK_RANK.get(domain, 99) for domain in domains), default=99)
    return (best, str(row["id"]))


def _compact_selection(
    receipt: ReceiptPayload,
) -> tuple[
    list[NodePayload],
    list[PathPayload],
    list[FrontierPayload],
    CompactTruncatedPayload,
]:
    required: set[str] = set()
    frontier: list[FrontierPayload] = []
    for frontier_row in receipt["frontier"]:
        if len(frontier) >= COMPACT_MAX_FRONTIER:
            break
        candidate = required | {frontier_row["node"]}
        if len(candidate) > COMPACT_MAX_NODES:
            continue
        required = candidate
        frontier.append(frontier_row)
    paths: list[PathPayload] = []
    for path_row in receipt["paths"]:
        if len(paths) >= COMPACT_MAX_PATHS:
            break
        candidate = required | set(path_row["nodes"])
        if len(candidate) > COMPACT_MAX_NODES:
            continue
        required = candidate
        paths.append(path_row)
    selected = [node_row for node_row in receipt["nodes"] if node_row["id"] in required]
    if len(selected) < COMPACT_MAX_NODES:
        remaining = sorted(
            (node_row for node_row in receipt["nodes"] if node_row["id"] not in required),
            key=_compact_node_rank,
        )
        selected.extend(remaining[: COMPACT_MAX_NODES - len(selected)])
    selected.sort(key=lambda row: str(row["id"]))
    truncated: CompactTruncatedPayload = {
        "nodes": max(0, len(receipt["nodes"]) - len(selected)),
        "paths": max(0, len(receipt["paths"]) - len(paths)),
        "frontier": max(0, len(receipt["frontier"]) - len(frontier)),
    }
    return selected, paths, frontier, truncated


def _compact_size(value: object) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _enforce_compact_byte_budget(compact: CompactGraphPayload) -> None:
    """Shrink compact delivery while disclosing every removal."""
    summary = compact["summary"]
    truncated = summary["truncated"]
    while _compact_size(compact) > COMPACT_MAX_BYTES:
        referenced = {node["key"] for path in compact["paths"] for node in path["nodes"]}
        referenced.update(row["node_key"] for row in compact["frontier"])
        removable = next(
            (
                index
                for index in range(len(compact["nodes"]) - 1, -1, -1)
                if compact["nodes"][index]["key"] not in referenced
            ),
            None,
        )
        if removable is not None:
            compact["nodes"].pop(removable)
            truncated["nodes"] += 1
            continue
        if compact["paths"]:
            compact["paths"].pop()
            truncated["paths"] += 1
            continue
        if compact["frontier"]:
            compact["frontier"].pop()
            truncated["frontier"] += 1
            continue
        if compact["nodes"]:
            compact["nodes"].pop()
            truncated["nodes"] += 1
            continue
        raise ValueError("compact graph metadata exceeds byte budget")


def compact_graph(receipt: ReceiptPayload) -> CompactGraphPayload:
    nodes = {row["id"]: row for row in receipt["nodes"]}
    edges = {row["id"]: row for row in receipt["edges"]}
    selected_nodes, selected_paths, selected_frontier, truncated = _compact_selection(receipt)
    compact: CompactGraphPayload = {
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
            for row in selected_nodes
        ],
        "paths": [
            {
                "key": row["id"],
                "nodes": [
                    {
                        "key": node_id,
                        "label": nodes[node_id]["label"],
                        "location": nodes[node_id]["location"],
                    }
                    for node_id in row["nodes"]
                ],
                "edges": [
                    {
                        "key": edge_id,
                        "kind": edges[edge_id]["kind"],
                        "confidence": edges[edge_id]["confidence"],
                    }
                    for edge_id in row["edges"]
                ],
                "distance": row["distance"],
                "risk_domains": list(row["risk_domains"]),
            }
            for row in selected_paths
        ],
        "frontier": [
            {
                "key": row["id"],
                "node_key": row["node"],
                "reason": row["reason"],
                "risk_domains": list(row["risk_domains"]),
            }
            for row in selected_frontier
        ],
        "summary": {
            "nodes": len(receipt["nodes"]),
            "edges": len(receipt["edges"]),
            "paths": len(receipt["paths"]),
            "unknown_frontiers": len(receipt["frontier"]),
            "timings_ms": dict(receipt["timings_ms"]),
            "budget_status": receipt["budget_status"],
            "truncated": truncated,
        },
    }
    _enforce_compact_byte_budget(compact)
    return compact


def source_inventory_sha256(source_digests: Mapping[str, str]) -> str:
    payload = json.dumps(
        dict(source_digests), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _receipt_source_inventory(
    root: Path, receipt: ReceiptPayload
) -> tuple[str, dict[str, str], str, bool, str | None]:
    key = receipt["cache"]["key"]
    if not isinstance(key, str) or re.fullmatch(r"[0-9a-f]{64}", key) is None or key == "0" * 64:
        raise ValueError("graph receipt has no verifiable source inventory cache")
    cache_dir = GRAPH_COORDINATOR.CACHE._cache_directory(root, False)
    if cache_dir is None:
        raise ValueError("graph source inventory cache is unavailable")
    artifact = GRAPH_COORDINATOR.CACHE._read_artifact(cache_dir / f"{key}.json")
    if artifact is None:
        raise ValueError("graph source inventory cache is invalid")
    try:
        source_digest_value = artifact["source_digests"]
        if not _is_string_mapping(source_digest_value):
            raise ValueError("source digests must be a mapping")
        source_digests = GRAPH_COORDINATOR.CACHE._source_digests(source_digest_value)
        identity = artifact["identity"]
        cached_receipt, _ = GRAPH_COORDINATOR.CACHE._normalize_receipt(artifact["receipt"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("graph source inventory cache is invalid") from error
    if (
        not isinstance(identity, dict)
        or set(identity) != GRAPH_COORDINATOR.CACHE._IDENTITY_FIELDS
        or identity.get("source_digests") != source_digests
        or hashlib.sha256(GRAPH_COORDINATOR.CACHE._canonical_json(identity)).hexdigest() != key
    ):
        raise ValueError("graph source inventory cache identity is invalid")
    if not _is_receipt_payload(cached_receipt):
        raise ValueError("graph source inventory cache is invalid")
    complete = identity.get("source_inventory_complete")
    reason = identity.get("source_inventory_reason")
    if (
        not isinstance(complete, bool)
        or (complete and reason is not None)
        or (
            not complete
            and reason not in {"deadline", "collection-limit", "traversal", "unreadable-source"}
        )
        or identity.get("repo_root_sha256") != hashlib.sha256(str(root).encode("utf-8")).hexdigest()
        or identity.get("settings") != receipt.get("settings")
        or identity.get("providers") != receipt.get("providers")
        or any(
            identity.get(name) != receipt.get(name)
            for name in ("receipt_id", "draft_id", "request_sha256")
        )
    ):
        raise ValueError("graph source inventory cache identity is invalid")
    stable_fields = (
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
        "budget_status",
    )
    if any(cached_receipt.get(name) != receipt.get(name) for name in stable_fields):
        raise ValueError("graph source inventory cache does not match receipt")
    return (
        key,
        source_digests,
        source_inventory_sha256(source_digests),
        complete,
        cast(Any, reason),
    )


def _verify_source_inventory(
    root: Path,
    graph_settings: Mapping[str, object],
    expected_digests: Mapping[str, str],
    expected_complete: bool,
    expected_reason: str | None,
    receipt: ReceiptPayload,
    *,
    deadline=None,
    stale_message="graph receipt source inventory is stale",
) -> None:
    expected = GRAPH_COORDINATOR.CACHE._source_digests(expected_digests)
    if deadline is None:
        deadline = GRAPH_COORDINATOR.Deadline(time, _int_value(graph_settings["max_seconds"]))
    current = GRAPH_COORDINATOR._collect_source_digests(root, deadline)
    if expected_complete:
        stale = not current.complete or dict(current.digests) != expected
    else:
        if receipt.get("budget_status") == "closed" or not receipt.get("frontier"):
            raise ValueError("incomplete source inventory requires a visible unknown frontier")
        stale = any(current.digests.get(path) != digest for path, digest in expected.items())
    if stale:
        raise ValueError(stale_message)


TRACE_INTENT_KEYS = {
    "schema_version",
    "intent_id",
    "draft_id",
    "repo_root_sha256",
    "request_sha256",
    "settings",
    "seeds",
    "source_inventory_sha256",
    "source_inventory_complete",
    "source_inventory_reason",
}


def _graph_trace_draft_identity(
    draft: Mapping[str, object], transaction: Mapping[str, object]
) -> dict[str, object]:
    identity = graph_draft_identity(draft)
    identity["graph_trace_intent"] = {
        "intent_id": transaction["intent_id"],
        "source_inventory_sha256": transaction["source_inventory_sha256"],
        "source_inventory_complete": transaction["source_inventory_complete"],
        "source_inventory_reason": transaction["source_inventory_reason"],
    }
    return identity


def _trace_intent_sha256(intent: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_bytes(intent)).hexdigest()


def new_trace_intent(
    root: Path,
    draft: Mapping[str, object],
    seeds: tuple[ScanSeedType, ...],
    graph_settings: Mapping[str, object],
    source_inventory,
) -> dict[str, object]:
    intent = {
        "schema_version": 1,
        "intent_id": secrets.token_hex(16),
        "draft_id": draft["draft_id"],
        "repo_root_sha256": hashlib.sha256(str(root).encode("utf-8")).hexdigest(),
        "settings": dict(graph_settings),
        "seeds": [{"term": seed.term, "location": seed.location} for seed in seeds],
        "source_inventory_sha256": source_inventory_sha256(source_inventory.digests),
        "source_inventory_complete": source_inventory.complete,
        "source_inventory_reason": source_inventory.reason,
    }
    intent["request_sha256"] = GRAPH_COORDINATOR._request_sha256(
        _graph_trace_draft_identity(draft, intent),
        seeds,
        GRAPH_COORDINATOR._settings(graph_settings),
    )
    return intent


def validate_trace_intent(
    root: Path,
    draft: Mapping[str, object],
    seeds: tuple[ScanSeedType, ...],
    graph_settings: Mapping[str, object],
    intent: object,
) -> dict[str, object]:
    if not isinstance(intent, dict) or set(intent) != TRACE_INTENT_KEYS:
        raise ValueError("pre-publication trace intent is invalid")
    expected_seeds = [{"term": seed.term, "location": seed.location} for seed in seeds]
    if (
        intent.get("schema_version") != 1
        or not isinstance(intent.get("intent_id"), str)
        or DRAFT_ID_PATTERN.fullmatch(intent["intent_id"]) is None
        or intent.get("draft_id") != draft.get("draft_id")
        or intent.get("repo_root_sha256") != hashlib.sha256(str(root).encode("utf-8")).hexdigest()
        or intent.get("settings") != graph_settings
        or intent.get("seeds") != expected_seeds
        or not isinstance(intent.get("source_inventory_complete"), bool)
        or (
            intent.get("source_inventory_complete")
            and intent.get("source_inventory_reason") is not None
        )
        or (
            not intent.get("source_inventory_complete")
            and intent.get("source_inventory_reason")
            not in {"deadline", "collection-limit", "traversal", "unreadable-source"}
        )
        or not isinstance(intent.get("source_inventory_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", intent["source_inventory_sha256"]) is None
    ):
        raise ValueError("pre-publication trace intent identity is invalid")
    expected_request = GRAPH_COORDINATOR._request_sha256(
        _graph_trace_draft_identity(draft, intent),
        seeds,
        GRAPH_COORDINATOR._settings(graph_settings),
    )
    if intent.get("request_sha256") != expected_request:
        raise ValueError("pre-publication trace intent request is invalid")
    return intent


def _intent_from_binding(
    root: Path, draft: Mapping[str, object], binding: Mapping[str, object]
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "intent_id": binding["trace_intent_id"],
        "draft_id": draft["draft_id"],
        "repo_root_sha256": hashlib.sha256(str(root).encode("utf-8")).hexdigest(),
        "request_sha256": binding["request_sha256"],
        "settings": binding["settings"],
        "seeds": binding["seeds"],
        "source_inventory_sha256": binding["source_inventory_sha256"],
        "source_inventory_complete": binding["source_inventory_complete"],
        "source_inventory_reason": binding["source_inventory_reason"],
    }


def _open_existing_directory_at(parent_fd: int, name: str) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except OSError as error:
        raise ValueError(f"graph receipt directory is unsafe: {name}: {error}") from error


def _read_bound_receipt_bytes(root: Path, draft_id: str) -> bytes:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    root_fd = os.open(root, flags)
    base_fd = graph_fd = receipt_fd = None
    try:
        base_fd = _open_existing_directory_at(root_fd, ".requirements-impact-refiner")
        graph_fd = _open_existing_directory_at(base_fd, "graph")
        file_flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW
        receipt_fd = os.open(f"{draft_id}.json", file_flags, dir_fd=graph_fd)
        metadata = os.fstat(receipt_fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise ValueError("graph receipt must be one private regular file")
        if metadata.st_size > GRAPH.MAX_RECEIPT_BYTES:
            raise ValueError("graph receipt exceeds maximum byte size")
        payload = bytearray()
        while len(payload) <= GRAPH.MAX_RECEIPT_BYTES:
            chunk = os.read(
                receipt_fd,
                min(64 * 1024, GRAPH.MAX_RECEIPT_BYTES + 1 - len(payload)),
            )
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) > GRAPH.MAX_RECEIPT_BYTES:
            raise ValueError("graph receipt exceeds maximum byte size")
        return bytes(payload)
    except OSError as error:
        raise ValueError(f"graph receipt is unavailable or unsafe: {error}") from error
    finally:
        for descriptor in (receipt_fd, graph_fd, base_fd, root_fd):
            if descriptor is not None:
                os.close(descriptor)


def _remove_exact_trace_receipt(
    root: Path,
    draft_id: str,
    expected_payload: bytes,
    *,
    commit=None,
    guard_intent_sha256=None,
    _runtime: Mapping[str, object] | None = None,
) -> None:
    runtime = _resolve_runtime(_runtime)
    read_bound_receipt_bytes = _operation(runtime, "read_bound_receipt_bytes")
    read_bounded_descriptor = _operation(runtime, "read_bounded_descriptor")
    open_optional_transaction_component = _operation(runtime, "open_optional_transaction_component")
    same_inode = _operation(runtime, "same_inode")
    rename_noreplace = _operation(runtime, "rename_noreplace")
    unlink_transaction_component = _operation(runtime, "unlink_transaction_component")
    write_private_transaction_component = _operation(runtime, "write_private_transaction_component")
    if read_bound_receipt_bytes(root, draft_id) != expected_payload:
        raise ValueError("stale cleanup target changed before quarantine")
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    root_fd = os.open(root, flags)
    base_fd = graph_fd = receipt_fd = quarantine_fd = guard_fd = None
    filename = f"{draft_id}.json"
    cleanup_id = secrets.token_hex(16)
    quarantine_name = f".{draft_id}.{cleanup_id}.stale"
    quarantined = False
    quarantine_info = None
    guard_claimed = False
    guard_info = None
    guard_payload = _canonical_bytes(
        {
            "draft_id": draft_id,
            "kind": "stale-receipt-cleanup-guard",
            "repo_root_sha256": hashlib.sha256(str(root).encode("utf-8")).hexdigest(),
            "receipt_sha256": hashlib.sha256(expected_payload).hexdigest(),
            "schema_version": 1,
            "trace_intent_sha256": guard_intent_sha256,
            "transaction_id": cleanup_id,
        }
    )

    def restore_quarantine() -> bool:
        nonlocal quarantined
        if not quarantined:
            return True
        if graph_fd is None:
            return False
        opened_here = None
        component = None
        try:
            if quarantine_fd is not None and quarantine_info is not None:
                component = (quarantine_fd, quarantine_info, expected_payload)
            else:
                component = open_optional_transaction_component(
                    graph_fd,
                    quarantine_name,
                    GRAPH.MAX_RECEIPT_BYTES,
                    "stale cleanup quarantine restoration",
                )
                if component is None or component[2] != expected_payload:
                    return False
                opened_here = component[0]
            os.link(
                quarantine_name,
                filename,
                src_dir_fd=graph_fd,
                dst_dir_fd=graph_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            return False
        try:
            unlink_transaction_component(
                graph_fd,
                quarantine_name,
                component,
                expected_payload,
                GRAPH.MAX_RECEIPT_BYTES,
                "stale cleanup quarantine restoration",
            )
        except ValueError:
            return False
        finally:
            if opened_here is not None:
                os.close(opened_here)
        quarantined = False
        return True

    def release_guard() -> bool:
        nonlocal guard_claimed
        if not guard_claimed:
            return True
        if graph_fd is None:
            return False
        try:
            current = os.stat(filename, dir_fd=graph_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        if (
            guard_info is None
            or not same_inode(current, guard_info)
            or read_bounded_descriptor(guard_fd, 1024, "stale cleanup namespace guard")
            != guard_payload
        ):
            return False
        try:
            unlink_transaction_component(
                graph_fd,
                filename,
                (guard_fd, guard_info, guard_payload),
                guard_payload,
                1024,
                "stale cleanup namespace guard",
            )
        except ValueError:
            return False
        guard_claimed = False
        return True

    try:
        base_fd = _open_existing_directory_at(root_fd, ".requirements-impact-refiner")
        graph_fd = _open_existing_directory_at(base_fd, "graph")
        read_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        receipt_fd = os.open(filename, read_flags, dir_fd=graph_fd)
        receipt_info = os.fstat(receipt_fd)
        if (
            not stat.S_ISREG(receipt_info.st_mode)
            or stat.S_IMODE(receipt_info.st_mode) != 0o600
            or receipt_info.st_nlink != 1
            or read_bounded_descriptor(receipt_fd, GRAPH.MAX_RECEIPT_BYTES, "stale cleanup receipt")
            != expected_payload
        ):
            raise ValueError("stale cleanup target changed or is unsafe")

        rename_noreplace(graph_fd, filename, quarantine_name)
        quarantined = True
        quarantine_fd = os.open(quarantine_name, read_flags, dir_fd=graph_fd)
        quarantine_info = os.fstat(quarantine_fd)
        if (quarantine_info.st_dev, quarantine_info.st_ino) != (
            receipt_info.st_dev,
            receipt_info.st_ino,
        ) or read_bounded_descriptor(
            quarantine_fd,
            GRAPH.MAX_RECEIPT_BYTES,
            "stale cleanup quarantine",
        ) != expected_payload:
            if not restore_quarantine():
                raise ValueError("stale cleanup quarantine changed; restoration is uncertain")
            raise ValueError("stale cleanup quarantine changed before removal")

        try:
            os.stat(filename, dir_fd=graph_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError("stale cleanup replacement preserved; removal is uncertain")
        guard_fd, guard_info = write_private_transaction_component(
            graph_fd,
            filename,
            guard_payload,
            "stale cleanup namespace guard",
        )
        guard_claimed = True
        os.fsync(graph_fd)
        final_info = os.stat(quarantine_name, dir_fd=graph_fd, follow_symlinks=False)
        if (final_info.st_dev, final_info.st_ino) != (receipt_info.st_dev, receipt_info.st_ino):
            raise ValueError("stale cleanup quarantine identity is uncertain")
        unlink_transaction_component(
            graph_fd,
            quarantine_name,
            (quarantine_fd, quarantine_info, expected_payload),
            expected_payload,
            GRAPH.MAX_RECEIPT_BYTES,
            "stale cleanup quarantine",
        )
        quarantined = False
        os.fsync(graph_fd)
        if not release_guard():
            raise ValueError("stale cleanup late replacement preserved; cleanup is uncertain")
        os.fsync(graph_fd)
        if commit is not None:
            commit()
    except ValueError as error:
        if guard_claimed and not release_guard():
            raise ValueError("stale cleanup replacement preserved; cleanup is uncertain") from error
        if quarantined and not restore_quarantine():
            raise ValueError("stale cleanup failed; quarantine restoration is uncertain") from error
        raise
    except OSError as error:
        if guard_claimed and not release_guard():
            raise ValueError("stale cleanup replacement preserved; cleanup is uncertain") from error
        if quarantined and not restore_quarantine():
            raise ValueError("stale cleanup failed; quarantine restoration is uncertain") from error
        raise ValueError(f"stale cleanup target is unsafe: {error}") from error
    finally:
        for descriptor in (guard_fd, quarantine_fd, receipt_fd, graph_fd, base_fd, root_fd):
            if descriptor is not None:
                os.close(descriptor)


_STALE_CLEANUP_GUARD_KEYS = {
    "draft_id",
    "kind",
    "repo_root_sha256",
    "receipt_sha256",
    "schema_version",
    "trace_intent_sha256",
    "transaction_id",
}


def _recover_stale_cleanup_guard(
    root: Path,
    draft_id: str,
    intent: Mapping[str, object],
    *,
    _runtime: Mapping[str, object] | None = None,
) -> bool:
    runtime = _resolve_runtime(_runtime)
    open_transaction_component_for_cleanup = _operation(
        runtime, "open_transaction_component_for_cleanup"
    )
    unlink_transaction_component = _operation(runtime, "unlink_transaction_component")
    trace_intent_sha256 = _operation(runtime, "trace_intent_sha256")
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    root_fd = os.open(root, flags)
    base_fd = graph_fd = None
    opened = []
    try:
        base_fd = _open_existing_directory_at(root_fd, ".requirements-impact-refiner")
        try:
            graph_fd = _open_existing_directory_at(base_fd, "graph")
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return False
            raise
        filename = f"{draft_id}.json"
        guard, guard_selected_name = open_transaction_component_for_cleanup(
            graph_fd,
            filename,
            GRAPH.MAX_RECEIPT_BYTES,
            "stale cleanup namespace guard",
        )
        if guard is None:
            return False
        opened.append(guard[0])
        try:
            value = json.loads(guard[2].decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        if not isinstance(value, dict) or value.get("kind") != "stale-receipt-cleanup-guard":
            return False
        if (
            set(value) != _STALE_CLEANUP_GUARD_KEYS
            or value.get("schema_version") != 1
            or value.get("draft_id") != draft_id
            or value.get("repo_root_sha256")
            != hashlib.sha256(str(root).encode("utf-8")).hexdigest()
            or value.get("trace_intent_sha256") != trace_intent_sha256(intent)
            or not isinstance(value.get("transaction_id"), str)
            or DRAFT_ID_PATTERN.fullmatch(value["transaction_id"]) is None
            or not isinstance(value.get("receipt_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", value["receipt_sha256"]) is None
            or _canonical_bytes(value) != guard[2]
            or guard[1].st_nlink != 1
        ):
            raise ValueError("stale cleanup namespace guard identity is invalid")
        quarantine_name = f".{draft_id}.{value['transaction_id']}.stale"
        quarantine, quarantine_selected_name = open_transaction_component_for_cleanup(
            graph_fd,
            quarantine_name,
            GRAPH.MAX_RECEIPT_BYTES,
            "stale cleanup recovery quarantine",
        )
        if quarantine is not None:
            opened.append(quarantine[0])
            if (
                hashlib.sha256(quarantine[2]).hexdigest() != value["receipt_sha256"]
                or quarantine[1].st_nlink != 1
            ):
                raise ValueError("stale cleanup recovery quarantine identity is invalid")
            unlink_transaction_component(
                graph_fd,
                quarantine_name,
                quarantine,
                quarantine[2],
                GRAPH.MAX_RECEIPT_BYTES,
                "stale cleanup recovery quarantine",
                selected_name=quarantine_selected_name,
            )
        unlink_transaction_component(
            graph_fd,
            filename,
            guard,
            guard[2],
            1024,
            "stale cleanup namespace guard",
            selected_name=guard_selected_name,
        )
        os.fsync(graph_fd)
        return True
    finally:
        for descriptor in reversed(opened):
            try:
                os.close(descriptor)
            except OSError:
                pass
        for descriptor in (graph_fd, base_fd, root_fd):
            if descriptor is not None:
                os.close(descriptor)


def _clear_trace_intent(
    root: Path,
    draft: Mapping[str, object],
    intent: Mapping[str, object],
    *,
    _runtime: Mapping[str, object] | None = None,
) -> dict[str, object]:
    runtime = _resolve_runtime(_runtime)
    current = _operation(runtime, "load_draft")(root, str(draft["draft_id"]))
    if current.get("graph_trace_intent") != intent:
        raise ValueError("trace intent changed before cleanup")
    updated = dict(current)
    updated.pop("graph_trace_intent", None)
    _operation(runtime, "cas_replace_private_draft")(root, str(draft["draft_id"]), current, updated)
    return updated


def _repository_file_sha256(root: Path, relative: str) -> str:
    parts = relative.split("/")
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(root, flags)
    opened = [descriptor]
    try:
        for part in parts[:-1]:
            descriptor = os.open(part, flags, dir_fd=descriptor)
            opened.append(descriptor)
        file_flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW
        file_fd = os.open(parts[-1], file_flags, dir_fd=descriptor)
        opened.append(file_fd)
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("receipt source is not a regular file")
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(file_fd, 64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > 8 * 1024 * 1024:
                raise ValueError("receipt source exceeds verification limit")
            digest.update(chunk)
        return digest.hexdigest()
    except OSError as error:
        raise ValueError(f"graph receipt source is stale or unsafe: {error}") from error
    finally:
        for current in reversed(opened):
            os.close(current)


def _verify_receipt_sources(root: Path, receipt: ReceiptPayload) -> None:
    observed: dict[str, str] = {}
    for row in [*receipt["nodes"], *receipt["edges"]]:
        location, expected = row.get("location"), row.get("source_sha256")
        if location is None or expected is None:
            continue
        actual = observed.get(location)
        if actual is None:
            actual = _repository_file_sha256(root, location)
            observed[location] = actual
        if actual != expected:
            raise ValueError(f"graph receipt is stale for source {location}")


def load_graph_context(
    root: Path,
    draft: Mapping[str, object],
    selected_receipt_id: str | None,
    *,
    deadline: DeadlineType | None = None,
    _runtime: Mapping[str, object] | None = None,
) -> GraphContext:
    runtime = _resolve_runtime(_runtime)
    binding = draft.get("graph_receipt")
    if not isinstance(binding, dict) or set(binding) != {
        "receipt_id",
        "sha256",
        "request_sha256",
        "settings",
        "seeds",
        "cache_key",
        "source_inventory_sha256",
        "source_inventory_complete",
        "source_inventory_reason",
        "trace_intent_id",
        "trace_intent_sha256",
    }:
        raise ValueError("graph receipt is required for this draft")
    if (
        not isinstance(selected_receipt_id, str)
        or DRAFT_ID_PATTERN.fullmatch(selected_receipt_id) is None
    ):
        raise ValueError("valid graph_receipt_id is required")
    if selected_receipt_id != binding.get("receipt_id"):
        raise ValueError("graph receipt does not match selected draft receipt")
    draft_settings = draft.get("settings")
    graph_settings = (
        draft_settings.get("impact_graph") if isinstance(draft_settings, dict) else None
    )
    if not isinstance(graph_settings, dict):
        raise ValueError("graph receipt settings do not match draft")
    if binding.get("settings") != graph_settings:
        raise ValueError("graph receipt settings do not match draft")
    seed_rows = binding.get("seeds")
    if not isinstance(seed_rows, list) or not seed_rows:
        raise ValueError("graph receipt seed identity is invalid")
    seeds = []
    for row in seed_rows:
        if not isinstance(row, dict) or set(row) != {"term", "location"}:
            raise ValueError("graph receipt seed identity is invalid")
        try:
            seeds.append(TraceSeed(row["term"], row["location"]))
        except (TypeError, ValueError) as error:
            raise ValueError("graph receipt seed identity is invalid") from error
    intent = _intent_from_binding(root, draft, binding)
    _operation(runtime, "validate_trace_intent")(root, draft, tuple(seeds), graph_settings, intent)
    trace_intent_sha256 = _operation(runtime, "trace_intent_sha256")
    if binding.get("trace_intent_sha256") != trace_intent_sha256(intent):
        raise ValueError("graph receipt trace intent digest is invalid")
    payload = _operation(runtime, "read_bound_receipt_bytes")(root, str(draft["draft_id"]))
    receipt, errors = GRAPH.load_receipt_bytes(payload)
    if receipt is None or errors or not _is_receipt_payload(receipt):
        raise ValueError("graph receipt is invalid or tampered")
    if GRAPH.canonical_receipt_bytes(receipt) != payload:
        raise ValueError("graph receipt is not canonical")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != binding.get("sha256"):
        raise ValueError("graph receipt digest is tampered")
    expected_root = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
    expected_request = GRAPH_COORDINATOR._request_sha256(
        _graph_trace_draft_identity(draft, intent),
        tuple(seeds),
        GRAPH_COORDINATOR._settings(graph_settings),
    )
    identity_providers = tuple(
        GRAPH.ProviderStatus(
            row["name"],
            row["status"],
            row["confidence"],
            row["version"],
            row["executable_sha256"],
        )
        for row in receipt["providers"]
        if row["name"] != "builtin"
    )
    expected_receipt_id = GRAPH_COORDINATOR._trace_identity(
        root,
        str(draft["draft_id"]),
        expected_request,
        tuple(seeds),
        GRAPH_COORDINATOR._settings(graph_settings),
        identity_providers,
    )
    if (
        receipt["receipt_id"] != selected_receipt_id
        or receipt["receipt_id"] != expected_receipt_id
        or receipt["draft_id"] != draft["draft_id"]
        or receipt["repo_root_sha256"] != expected_root
        or receipt["request_sha256"] != expected_request
        or binding.get("request_sha256") != expected_request
        or receipt["settings"] != graph_settings
        or receipt["cache"]["key"] != binding.get("cache_key")
    ):
        raise ValueError("graph receipt identity does not match draft request and settings")
    (
        cache_key,
        source_digests,
        inventory_sha256,
        source_inventory_complete,
        source_inventory_reason,
    ) = _operation(runtime, "receipt_source_inventory")(root, receipt)
    if (
        binding.get("cache_key") != cache_key
        or binding.get("source_inventory_sha256") != inventory_sha256
        or binding.get("source_inventory_complete") != source_inventory_complete
        or binding.get("source_inventory_reason") != source_inventory_reason
    ):
        raise ValueError("graph source inventory cache does not match binding")
    _verify_receipt_sources(root, receipt)
    _operation(runtime, "verify_source_inventory")(
        root,
        graph_settings,
        source_digests,
        source_inventory_complete,
        source_inventory_reason,
        receipt,
        deadline=deadline,
    )
    required_digests = dict(source_digests)
    required_complete = True
    for seed in binding["seeds"]:
        location = seed.get("location")
        if location is None or location in required_digests:
            continue
        candidates = {
            row.get("source_sha256")
            for row in [*receipt["nodes"], *receipt["edges"]]
            if row.get("location") == location and row.get("source_sha256") is not None
        }
        if len(candidates) > 1:
            raise ValueError("graph seed digest conflicts across receipt evidence")
        if len(candidates) != 1:
            required_complete = False
            continue
        required_digests[location] = cast(str, next(iter(candidates)))
    return {
        "receipt": receipt,
        "sha256": digest,
        "binding": binding,
        "source_inventory": {
            "sha256": inventory_sha256,
            "complete": source_inventory_complete,
            "digests": dict(source_digests),
            "required_digests": required_digests,
            "required_complete": required_complete,
        },
    }


def _path_confidence(path, nodes, edges) -> str:
    values = [nodes[node]["confidence"] for node in path["nodes"]]
    values.extend(edges[edge]["confidence"] for edge in path["edges"])
    return max(values, key=lambda value: GRAPH_CONFIDENCE_RANK[value])


def _path_provenance(path, nodes, edges) -> str:
    records = [nodes[node] for node in path["nodes"]]
    records.extend(edges[edge] for edge in path["edges"])
    providers = list(dict.fromkeys(row.get("provider") for row in records if row.get("provider")))
    locations = list(dict.fromkeys(row.get("location") for row in records if row.get("location")))
    provider = " + ".join(providers) if providers else "unavailable"
    location = " + ".join(locations) if locations else "unavailable"
    return (
        f"provider {provider}; confidence {_path_confidence(path, nodes, edges)}; "
        f"location {location}"
    )


def _structured_path(path, nodes, edges) -> dict[str, object]:
    records = [nodes[node] for node in path["nodes"]]
    records.extend(edges[edge] for edge in path["edges"])
    return {
        "id": path["id"],
        "labels": [nodes[node]["label"] for node in path["nodes"]],
        "providers": list(dict.fromkeys(row["provider"] for row in records if row.get("provider")))
        or ["unavailable"],
        "confidence": _path_confidence(path, nodes, edges),
        "locations": list(dict.fromkeys(row["location"] for row in records if row.get("location"))),
    }


def validate_graph_coverage(analysis: Mapping[str, object], context: GraphContext) -> None:
    receipt = context["receipt"]
    nodes = {row["id"]: row for row in receipt["nodes"]}
    edges = {row["id"]: row for row in receipt["edges"]}
    paths = {row["id"]: row for row in receipt["paths"]}
    path_nodes = {identifier for path in paths.values() for identifier in path["nodes"]}
    frontier_nodes = {row["node"] for row in receipt["frontier"]}
    covered_nodes = set()
    impact_confidences: dict[str, str] = {}
    impacts = analysis["impacts"]
    invariants = analysis["invariants"]
    if not isinstance(impacts, list) or not isinstance(invariants, list):
        raise ValueError("graph coverage analysis arrays are invalid")
    impact_paths: dict[str, list[str]] = {}
    rationales: dict[str, str | None] = {}
    for impact in impacts:
        if not isinstance(impact, dict):
            raise ValueError("impact must be an object")
        impact_key = _local_key(impact.get("key"), "impact")
        if "graph_path_keys" not in impact:
            raise ValueError("graph_path_keys is required for every graph-enabled impact")
        selected = impact["graph_path_keys"]
        if (
            not isinstance(selected, list)
            or len(selected) > 128
            or len(selected) != len(set(selected))
        ):
            raise ValueError("impact graph_path_keys must be a unique bounded array")
        selected_paths = []
        for key in selected:
            if not isinstance(key, str) or re.fullmatch(r"PATH-\d{3}", key) is None:
                raise ValueError("invalid graph path key")
            if key not in paths:
                raise ValueError(f"unknown graph path key {key}")
            selected_paths.append(paths[key])
            covered_nodes.update(paths[key]["nodes"])
        rationale = impact.get("coverage_rationale")
        if rationale is not None and (
            not isinstance(rationale, str)
            or not rationale.strip()
            or len(rationale.encode("utf-8")) > MAX_STRING_BYTES
        ):
            raise ValueError("coverage_rationale must be bounded nonempty text")
        if not selected_paths:
            if rationale is None or impact.get("evidence_level") != "unknown":
                raise ValueError(
                    "supplied-only or unknown graph coverage requires rationale and unknown evidence"
                )
            if impact.get("state") == "resolved":
                raise ValueError("resolved impact cannot rely on unknown graph evidence")
            impact_confidences[impact_key] = "unknown"
            impact_paths[impact_key] = list(selected)
            rationales[impact_key] = cast(Any, rationale)
            continue
        confidences = [_path_confidence(path, nodes, edges) for path in selected_paths]
        strongest = min(confidences, key=lambda value: GRAPH_CONFIDENCE_RANK[value])
        allowed_evidence = (
            "verified"
            if GRAPH_CONFIDENCE_RANK[strongest] <= 1
            else "inferred"
            if strongest == "structural-inferred"
            else "unknown"
        )
        evidence_level = impact.get("evidence_level")
        evidence_rank = (
            EVIDENCE_RANK.get(evidence_level, -1) if isinstance(evidence_level, str) else -1
        )
        if evidence_rank < EVIDENCE_RANK[allowed_evidence]:
            raise ValueError("impact evidence confidence upgrades graph path evidence")
        if impact.get("state") == "resolved" and all(
            confidence == "lexical" for confidence in confidences
        ):
            raise ValueError("resolved impact cannot rely solely on lexical graph evidence")
        impact_confidences[impact_key] = strongest
        impact_paths[impact_key] = list(selected)
        rationales[impact_key] = cast(Any, rationale)
    invariant_lines = []
    for row in invariants:
        if not isinstance(row, dict):
            raise ValueError("invariant must be an object")
        if row.get("evidence_level") == "verified":
            invariant_lines.append(f"{row.get('behavior', '')}\n{row.get('evidence', '')}")
    invariant_text = "\n".join(invariant_lines)
    invariant_tokens = set(re.findall(r"[A-Za-z0-9_./-]+", invariant_text))
    invariant_nodes = {
        identifier
        for identifier, node in nodes.items()
        if node.get("source_sha256") is not None
        and any(
            isinstance(value, str) and len(value) >= 8 and value in invariant_tokens
            for value in (node.get("label"), node.get("location"))
        )
    }
    for identifier, node in sorted(nodes.items()):
        if (
            set(node["risk_domains"]) & HIGH_RISK_DOMAINS
            and identifier in path_nodes
            and identifier not in covered_nodes
            and identifier not in invariant_nodes
            and identifier not in frontier_nodes
        ):
            raise ValueError(f"uncovered high-risk graph node {identifier}")
    context["impact_paths"] = impact_paths
    context["rationales"] = rationales
    context["impact_confidences"] = impact_confidences


def _validate_persisted_trace_receipt(
    root: Path,
    draft: Mapping[str, object],
    normalized_seeds: tuple[ScanSeedType, ...],
    graph_settings: Mapping[str, object],
    intent: Mapping[str, object],
    expected_payload: bytes | None = None,
    *,
    _runtime: Mapping[str, object] | None = None,
):
    runtime = _resolve_runtime(_runtime)
    stored = _operation(runtime, "read_bound_receipt_bytes")(root, str(draft["draft_id"]))
    if expected_payload is not None and stored != expected_payload:
        raise ValueError("persisted graph receipt does not match coordinator result")
    receipt_value, errors = GRAPH.load_receipt_bytes(stored)
    if receipt_value is None or errors or not _is_receipt_payload(receipt_value):
        raise ValueError("persisted graph receipt is invalid")
    if GRAPH.canonical_receipt_bytes(receipt_value) != stored:
        raise ValueError("persisted graph receipt is not canonical")
    graph_draft = _graph_trace_draft_identity(draft, intent)
    settings = GRAPH_COORDINATOR._settings(graph_settings)
    expected_request_sha256 = GRAPH_COORDINATOR._request_sha256(
        graph_draft, normalized_seeds, settings
    )
    expected_root_sha256 = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
    identity_providers = tuple(
        GRAPH.ProviderStatus(
            row["name"],
            row["status"],
            row["confidence"],
            row["version"],
            row["executable_sha256"],
        )
        for row in receipt_value["providers"]
        if row["name"] != "builtin"
    )
    expected_receipt_id = GRAPH_COORDINATOR._trace_identity(
        root,
        str(draft["draft_id"]),
        expected_request_sha256,
        normalized_seeds,
        settings,
        identity_providers,
    )
    if (
        receipt_value["draft_id"] != draft["draft_id"]
        or receipt_value["receipt_id"] != expected_receipt_id
        or receipt_value["repo_root_sha256"] != expected_root_sha256
        or receipt_value["request_sha256"] != expected_request_sha256
        or receipt_value["settings"] != graph_settings
    ):
        raise ValueError("graph receipt identity does not match draft request and settings")
    inventory = _operation(runtime, "receipt_source_inventory")(root, receipt_value)
    if (
        intent.get("source_inventory_sha256") != inventory[2]
        or intent.get("source_inventory_complete") != inventory[3]
        or intent.get("source_inventory_reason") != inventory[4]
    ):
        raise ValueError("trace intent does not match receipt source inventory")
    return (
        receipt_value,
        stored,
        expected_request_sha256,
        *inventory,
    )


def _bind_trace_receipt(
    root: Path,
    draft: Mapping[str, object],
    normalized_seeds: tuple[ScanSeedType, ...],
    graph_settings: Mapping[str, object],
    intent: Mapping[str, object],
    receipt_value: ReceiptPayload,
    stored: bytes,
    expected_request_sha256: str,
    cache_key: str,
    source_digests: Mapping[str, str],
    inventory_sha256: str,
    source_inventory_complete: bool,
    source_inventory_reason: str | None,
    *,
    _runtime: Mapping[str, object] | None = None,
) -> TraceResult:
    del source_digests
    runtime = _resolve_runtime(_runtime)
    updated = dict(draft)
    digest = hashlib.sha256(stored).hexdigest()
    updated.pop("graph_trace_intent", None)
    updated["graph_receipt"] = {
        "receipt_id": receipt_value["receipt_id"],
        "sha256": digest,
        "request_sha256": expected_request_sha256,
        "settings": graph_settings,
        "cache_key": cache_key,
        "source_inventory_sha256": inventory_sha256,
        "source_inventory_complete": source_inventory_complete,
        "source_inventory_reason": source_inventory_reason,
        "trace_intent_id": intent["intent_id"],
        "trace_intent_sha256": _operation(runtime, "trace_intent_sha256")(intent),
        "seeds": [{"term": seed.term, "location": seed.location} for seed in normalized_seeds],
    }
    _operation(runtime, "cas_replace_private_draft")(root, str(draft["draft_id"]), draft, updated)
    receipt_path = root / ".requirements-impact-refiner" / "graph" / f"{draft['draft_id']}.json"
    return _operation(runtime, "trace_result")(
        receipt_id=str(receipt_value["receipt_id"]),
        receipt_path=receipt_path,
        receipt_sha256=digest,
        compact_graph=_operation(runtime, "compact_graph")(receipt_value),
        budget_status=str(receipt_value["budget_status"]),
        request_sha256=expected_request_sha256,
        seeds=normalized_seeds,
    )


def _default_runtime() -> Mapping[str, object]:
    return {
        "clock": time,
        "trace_result": TraceResult,
        "root_path": _root,
        "bounded_bytes": _bounded,
        "load_draft": load_draft,
        "cas_replace_private_draft": _cas_replace_private_draft,
        "recover_private_draft_transaction": _recover_private_draft_transaction,
        "report_lock": _report_lock,
        "read_bounded_descriptor": _read_bounded_descriptor,
        "open_optional_transaction_component": _open_optional_transaction_component,
        "open_transaction_component_for_cleanup": _open_transaction_component_for_cleanup,
        "same_inode": _same_inode,
        "rename_noreplace": _rename_noreplace,
        "unlink_transaction_component": _unlink_transaction_component,
        "write_private_transaction_component": _write_private_transaction_component,
        "graph_draft_identity": graph_draft_identity,
        "compact_graph": compact_graph,
        "source_inventory_sha256": source_inventory_sha256,
        "receipt_source_inventory": _receipt_source_inventory,
        "verify_source_inventory": _verify_source_inventory,
        "trace_intent_sha256": _trace_intent_sha256,
        "new_trace_intent": new_trace_intent,
        "validate_trace_intent": validate_trace_intent,
        "read_bound_receipt_bytes": _read_bound_receipt_bytes,
        "remove_exact_trace_receipt": _remove_exact_trace_receipt,
        "recover_stale_cleanup_guard": _recover_stale_cleanup_guard,
        "clear_trace_intent": _clear_trace_intent,
        "load_graph_context": load_graph_context,
        "validate_persisted_trace_receipt": _validate_persisted_trace_receipt,
        "bind_trace_receipt": _bind_trace_receipt,
    }


def trace_impact(
    request: TraceRequest, *, _runtime: Mapping[str, object] | None = None
) -> TraceResult:
    runtime = _resolve_runtime(_runtime)
    clock = cast(Any, runtime["clock"])
    original_root = Path(request.repo_root)
    if original_root.is_symlink():
        raise ValueError("repository root symlink is unsafe for graph tracing")
    root = _operation(runtime, "root_path")(original_root)
    if not isinstance(request.seeds, tuple):
        raise ValueError("trace seeds must be a tuple")
    if not request.seeds or len(request.seeds) > MAX_TRACE_SEEDS:
        raise ValueError("trace seeds must contain between 1 and 128 items")
    for seed in request.seeds:
        if not isinstance(seed, TraceSeed):
            raise ValueError("trace seeds must contain TraceSeed values")
        if not isinstance(seed.term, str) or not seed.term.strip():
            raise ValueError("trace seed term must be nonempty")
        if seed.location is not None and not GRAPH._safe_path(seed.location):
            raise ValueError("trace seed location must be a safe repository-relative path")
    normalized_seeds = tuple(sorted(set(request.seeds), key=GRAPH_COORDINATOR._seed_key))
    _operation(runtime, "bounded_bytes")(
        {"seeds": [{"term": seed.term, "location": seed.location} for seed in normalized_seeds]},
        MAX_TRACE_BYTES,
        "trace input",
    )
    if DRAFT_ID_PATTERN.fullmatch(request.draft_id) is None:
        raise ValueError("invalid draft ID")
    recover_private_draft_transaction = _operation(runtime, "recover_private_draft_transaction")
    load_runtime_draft = _operation(runtime, "load_draft")
    recover_private_draft_transaction(root, request.draft_id)
    draft = load_runtime_draft(root, request.draft_id)
    settings = draft.get("settings")
    graph_settings = settings.get("impact_graph") if isinstance(settings, dict) else None
    if not isinstance(graph_settings, dict):
        raise ValueError("draft graph settings are invalid")
    if graph_settings.get("enabled") is not True:
        raise ValueError("impact graph is disabled for this draft")
    deadline = GRAPH_COORDINATOR.Deadline(clock, _int_value(graph_settings["max_seconds"]))
    receipt_path = root / ".requirements-impact-refiner" / "graph" / f"{request.draft_id}.json"
    with _operation(runtime, "report_lock")(root, str(draft["report_id"]), deadline=deadline):
        recover_private_draft_transaction(root, request.draft_id)
        draft = load_runtime_draft(root, request.draft_id)
        if draft.get("consumed") is True:
            raise ValueError("draft is already consumed")
        if draft.get("promoted_scan") is not None:
            raise ValueError("promoted Fast Scan draft must not be traced again")
        if draft.get("graph_receipt") is not None:
            binding = draft["graph_receipt"]
            requested_seeds = [
                {"term": seed.term, "location": seed.location} for seed in normalized_seeds
            ]
            if not isinstance(binding, dict) or binding.get("seeds") != requested_seeds:
                raise ValueError("draft graph receipt belongs to a different trace request")
            context = _operation(runtime, "load_graph_context")(
                root, draft, binding.get("receipt_id"), deadline=deadline
            )
            receipt_value = context["receipt"]
            return _operation(runtime, "trace_result")(
                receipt_id=str(receipt_value["receipt_id"]),
                receipt_path=receipt_path,
                receipt_sha256=str(context["sha256"]),
                compact_graph=_operation(runtime, "compact_graph")(receipt_value),
                budget_status=str(receipt_value["budget_status"]),
                request_sha256=str(binding["request_sha256"]),
                seeds=normalized_seeds,
            )
        intent = draft.get("graph_trace_intent")
        if intent is not None:
            intent = _operation(runtime, "validate_trace_intent")(
                root, draft, normalized_seeds, graph_settings, intent
            )
            _operation(runtime, "recover_stale_cleanup_guard")(root, request.draft_id, intent)
        receipt_exists = receipt_path.exists() or receipt_path.is_symlink()
        source_inventory = None
        if intent is None:
            if receipt_exists:
                raise ValueError("graph receipt has no durable pre-publication trace intent")
            source_inventory = GRAPH_COORDINATOR._collect_source_digests(root, deadline)
            intent = _operation(runtime, "new_trace_intent")(
                root, draft, normalized_seeds, graph_settings, source_inventory
            )
            updated = dict(draft)
            updated["graph_trace_intent"] = intent
            _operation(runtime, "cas_replace_private_draft")(root, request.draft_id, draft, updated)
            draft = updated
        if receipt_exists:
            validated = _operation(runtime, "validate_persisted_trace_receipt")(
                root, draft, normalized_seeds, graph_settings, intent
            )
            try:
                _operation(runtime, "verify_source_inventory")(
                    root,
                    graph_settings,
                    validated[4],
                    validated[6],
                    validated[7],
                    validated[0],
                    deadline=deadline,
                    stale_message="recovery source inventory is stale",
                )
            except ValueError as error:
                if "recovery source inventory is stale" not in str(error):
                    raise
                _operation(runtime, "remove_exact_trace_receipt")(
                    root,
                    request.draft_id,
                    validated[1],
                    commit=lambda: _operation(runtime, "clear_trace_intent")(root, draft, intent),
                    guard_intent_sha256=_operation(runtime, "trace_intent_sha256")(intent),
                )
                raise
            return _operation(runtime, "bind_trace_receipt")(
                root, draft, normalized_seeds, graph_settings, intent, *validated
            )
        if source_inventory is None:
            source_inventory = GRAPH_COORDINATOR._collect_source_digests(root, deadline)
            if (
                _operation(runtime, "source_inventory_sha256")(source_inventory.digests)
                != intent["source_inventory_sha256"]
                or source_inventory.complete != intent["source_inventory_complete"]
                or source_inventory.reason != intent["source_inventory_reason"]
            ):
                _operation(runtime, "clear_trace_intent")(root, draft, intent)
                raise ValueError("trace intent source inventory is stale")
        graph_draft = _graph_trace_draft_identity(draft, intent)
        receipt = GRAPH_COORDINATOR.trace_impact(
            root,
            graph_draft,
            normalized_seeds,
            graph_settings,
            clock=clock,
            deadline=deadline,
            source_inventory=source_inventory,
        )
        payload = GRAPH.canonical_receipt_bytes(receipt)
        if not receipt_path.is_file() or receipt_path.is_symlink():
            raise ValueError("graph receipt publication failed")
        validated = _operation(runtime, "validate_persisted_trace_receipt")(
            root, draft, normalized_seeds, graph_settings, intent, payload
        )
        return _operation(runtime, "bind_trace_receipt")(
            root, draft, normalized_seeds, graph_settings, intent, *validated
        )


# Compatibility aliases used by the controller facade and its fault-injection tests.
_graph_draft_identity = graph_draft_identity
_compact_graph = compact_graph
_source_inventory_sha256 = source_inventory_sha256
_new_trace_intent = new_trace_intent
_validate_trace_intent = validate_trace_intent
_load_graph_context = load_graph_context
_validate_graph_coverage = validate_graph_coverage
verify_receipt_sources = _verify_receipt_sources
