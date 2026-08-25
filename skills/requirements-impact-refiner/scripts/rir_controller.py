#!/usr/bin/env python3

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
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Protocol, SupportsInt, TypedDict, cast

if TYPE_CHECKING:
    from graph_builtin import ScanSeed as ScanSeedType
    from graph_coordinator import SourceInventory as SourceInventoryType
    from graph_providers import Deadline as DeadlineType
    from impact_graph import GraphReceipt as GraphReceiptType
    from impact_graph import GraphSettings as GraphSettingsType
    from impact_graph import ProviderStatus as ProviderStatusType
    from rir_contracts import (
        BeginRequest,
        DraftResult,
        FinalizeRequest,
        FinalizeResult,
        ScanRequest,
        TraceRequest,
        TraceResult,
    )
    from typing_extensions import TypeGuard


class _FcntlContract(Protocol):
    LOCK_EX: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, fd: int, operation: int) -> None: ...


class _ControllerContractsContract(Protocol):
    MAX_BEGIN_BYTES: int
    MAX_FINALIZE_BYTES: int
    MAX_STRING_BYTES: int
    MAX_TRACE_BYTES: int
    BeginRequest: type
    DraftResult: type
    FinalizeRequest: type
    FinalizeResult: type
    ScanRequest: type
    TraceRequest: type
    TraceResult: type

    def _local_key(self, value: object, label: str) -> str: ...

    def bounded_bytes(self, value: object, maximum: int, label: str) -> bytes: ...

    def canonical_bytes(self, value: object) -> bytes: ...

    def validate_analysis(self, analysis: Mapping[str, object]) -> None: ...


class _ControllerStorageContract(Protocol):
    MAX_DRAFT_BYTES: int
    DRAFT_ID_PATTERN: re.Pattern[str]
    fcntl: _FcntlContract | None

    def root_path(self, path: Path) -> Path: ...

    def write_private_draft(self, root: Path, draft_id: str, payload: bytes) -> Path: ...

    def load_private_draft(self, repo_root: Path, draft_id: str) -> dict[str, object]: ...

    def replace_private_draft(
        self, root: Path, draft_id: str, value: Mapping[str, object]
    ) -> None: ...

    def draft_path(self, root: Path, draft_id: str) -> Path: ...

    def controller_metadata_path(self, report_id: str, revision: int, root: Path) -> Path: ...

    def load_controller_metadata(self, current: object) -> dict[str, object] | None: ...

    def cas_replace_private_draft(
        self, root: Path, draft_id: str, expected: bytes, replacement: bytes
    ) -> None: ...

    def recover_private_draft_transaction(self, root: Path, draft_id: str) -> None: ...

    def report_lock(self, root: Path, report_id: str, deadline: object = None): ...

    def write_controller_metadata(
        self,
        root: Path,
        draft: Mapping[str, object],
        state_bytes: bytes,
        key_map: Mapping[str, object],
        graph_receipt: Mapping[str, object] | None = None,
    ) -> None: ...

    def consume_draft(self, path: Path, draft: dict[str, object], published, key_map) -> None: ...

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


def _is_fcntl_contract(value: object) -> TypeGuard[_FcntlContract]:
    return all(
        isinstance(getattr(value, name, None), int) for name in ("LOCK_EX", "LOCK_NB", "LOCK_UN")
    ) and callable(getattr(value, "flock", None))


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


def _is_controller_contracts_contract(value: object) -> TypeGuard[_ControllerContractsContract]:
    integer_names = (
        "MAX_BEGIN_BYTES",
        "MAX_FINALIZE_BYTES",
        "MAX_STRING_BYTES",
        "MAX_TRACE_BYTES",
    )
    class_names = (
        "BeginRequest",
        "DraftResult",
        "FinalizeRequest",
        "FinalizeResult",
        "ScanRequest",
        "TraceRequest",
        "TraceResult",
    )
    callable_names = ("_local_key", "bounded_bytes", "canonical_bytes", "validate_analysis")
    return (
        all(
            type(getattr(value, name, None)) is int and getattr(value, name) > 0
            for name in integer_names
        )
        and all(isinstance(getattr(value, name, None), type) for name in class_names)
        and all(callable(getattr(value, name, None)) for name in callable_names)
    )


def _module_uses_sibling(value: object, expected: Path) -> bool:
    module_file = getattr(value, "__file__", None)
    return isinstance(module_file, str) and _regular_module_path(Path(module_file)) == expected


def _load_registered_contracts(module_name: str, expected: Path) -> _ControllerContractsContract:
    specification = importlib.util.spec_from_file_location(module_name, expected)
    if specification is None or specification.loader is None:
        raise ImportError("cannot load fixed controller contracts sibling")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError("cannot load fixed controller contracts sibling") from error
    if not _is_controller_contracts_contract(module):
        sys.modules.pop(module_name, None)
        raise ImportError("controller contracts sibling contract is incomplete")
    return module


def _load_controller_contracts() -> _ControllerContractsContract:
    sibling = SCRIPT_DIR / "rir_contracts.py"
    expected = _regular_module_path(sibling)
    if expected is None or expected != sibling:
        raise ImportError("controller contracts sibling is unsafe")
    module_name = (
        "_rir_controller_contracts_"
        + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    )
    hashed_present = module_name in sys.modules
    hashed = sys.modules.get(module_name)
    if "rir_contracts" not in sys.modules:
        if hashed_present:
            if not _module_uses_sibling(hashed, expected):
                raise ImportError("controller contracts sibling is unsafe")
            if not _is_controller_contracts_contract(hashed):
                raise ImportError("controller contracts sibling contract is incomplete")
            sys.modules["rir_contracts"] = cast(ModuleType, hashed)
            return hashed
        return _load_registered_contracts("rir_contracts", expected)
    canonical = sys.modules.get("rir_contracts")
    if _module_uses_sibling(canonical, expected):
        if not _is_controller_contracts_contract(canonical):
            raise ImportError("controller contracts sibling contract is incomplete")
        if not hashed_present:
            return canonical
        if not _module_uses_sibling(hashed, expected):
            raise ImportError("controller contracts sibling is unsafe")
        if not _is_controller_contracts_contract(hashed):
            raise ImportError("controller contracts sibling contract is incomplete")
        return hashed
    if hashed_present:
        if not _module_uses_sibling(hashed, expected):
            raise ImportError("controller contracts sibling is unsafe")
        if not _is_controller_contracts_contract(hashed):
            raise ImportError("controller contracts sibling contract is incomplete")
        return hashed
    return _load_registered_contracts(module_name, expected)


def _is_controller_storage_contract(value: object) -> TypeGuard[_ControllerStorageContract]:
    maximum_name = "MAX_DRAFT_BYTES"
    maximum = getattr(value, maximum_name, None)
    fcntl_name = "fcntl"
    storage_fcntl = getattr(value, fcntl_name, None)
    callable_names = (
        "root_path",
        "write_private_draft",
        "load_private_draft",
        "replace_private_draft",
        "draft_path",
        "controller_metadata_path",
        "load_controller_metadata",
        "cas_replace_private_draft",
        "recover_private_draft_transaction",
        "report_lock",
        "write_controller_metadata",
        "consume_draft",
        "_read_bounded_descriptor",
        "_open_optional_transaction_component",
        "_open_transaction_component_for_cleanup",
        "_same_inode",
        "_rename_noreplace",
        "_unlink_transaction_component",
        "_write_private_transaction_component",
    )
    return (
        type(maximum) is int
        and maximum > 0
        and isinstance(getattr(value, "DRAFT_ID_PATTERN", None), re.Pattern)
        and hasattr(value, "fcntl")
        and (storage_fcntl is None or _is_fcntl_contract(storage_fcntl))
        and all(callable(getattr(value, name, None)) for name in callable_names)
    )


def _load_registered_storage(module_name: str, expected: Path) -> _ControllerStorageContract:
    specification = importlib.util.spec_from_file_location(module_name, expected)
    if specification is None or specification.loader is None:
        raise ImportError("cannot load fixed controller storage sibling")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError("cannot load fixed controller storage sibling") from error
    if not _is_controller_storage_contract(module):
        sys.modules.pop(module_name, None)
        raise ImportError("controller storage sibling contract is incomplete")
    return module


def _load_controller_storage() -> _ControllerStorageContract:
    sibling = SCRIPT_DIR / "rir_storage.py"
    expected = _regular_module_path(sibling)
    if expected is None or expected != sibling:
        raise ImportError("controller storage sibling is unsafe")
    module_name = (
        "_rir_controller_storage_" + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    )
    hashed_present = module_name in sys.modules
    hashed = sys.modules.get(module_name)
    if "rir_storage" not in sys.modules:
        if hashed_present:
            if not _module_uses_sibling(hashed, expected):
                raise ImportError("controller storage sibling is unsafe")
            if not _is_controller_storage_contract(hashed):
                raise ImportError("controller storage sibling contract is incomplete")
            sys.modules["rir_storage"] = cast(ModuleType, hashed)
            return hashed
        return _load_registered_storage("rir_storage", expected)
    canonical = sys.modules.get("rir_storage")
    if _module_uses_sibling(canonical, expected):
        if not _is_controller_storage_contract(canonical):
            raise ImportError("controller storage sibling contract is incomplete")
        if not hashed_present:
            return canonical
        if not _module_uses_sibling(hashed, expected):
            raise ImportError("controller storage sibling is unsafe")
        if not _is_controller_storage_contract(hashed):
            raise ImportError("controller storage sibling contract is incomplete")
        return hashed
    if hashed_present:
        if not _module_uses_sibling(hashed, expected):
            raise ImportError("controller storage sibling is unsafe")
        if not _is_controller_storage_contract(hashed):
            raise ImportError("controller storage sibling contract is incomplete")
        return hashed
    return _load_registered_storage(module_name, expected)


CONTRACTS = _load_controller_contracts()
STORAGE = _load_controller_storage()
MAX_BEGIN_BYTES = CONTRACTS.MAX_BEGIN_BYTES
MAX_FINALIZE_BYTES = CONTRACTS.MAX_FINALIZE_BYTES
MAX_STRING_BYTES = CONTRACTS.MAX_STRING_BYTES
MAX_TRACE_BYTES = CONTRACTS.MAX_TRACE_BYTES
if not TYPE_CHECKING:
    BeginRequest = CONTRACTS.BeginRequest
    DraftResult = CONTRACTS.DraftResult
    FinalizeRequest = CONTRACTS.FinalizeRequest
    FinalizeResult = CONTRACTS.FinalizeResult
    ScanRequest = CONTRACTS.ScanRequest
    TraceRequest = CONTRACTS.TraceRequest
    TraceResult = CONTRACTS.TraceResult
_local_key = CONTRACTS._local_key
bounded_bytes = CONTRACTS.bounded_bytes
canonical_bytes = CONTRACTS.canonical_bytes
validate_analysis = CONTRACTS.validate_analysis

MAX_DRAFT_BYTES = STORAGE.MAX_DRAFT_BYTES
DRAFT_ID_PATTERN = STORAGE.DRAFT_ID_PATTERN
fcntl = STORAGE.fcntl
_root = STORAGE.root_path
_write_private_draft = STORAGE.write_private_draft
_controller_metadata_path = STORAGE.controller_metadata_path
_load_controller_metadata = STORAGE.load_controller_metadata
_draft_path = STORAGE.draft_path
load_draft = STORAGE.load_private_draft
_replace_private_draft = STORAGE.replace_private_draft
_read_bounded_descriptor = STORAGE._read_bounded_descriptor
_open_optional_transaction_component = STORAGE._open_optional_transaction_component
_open_transaction_component_for_cleanup = STORAGE._open_transaction_component_for_cleanup
_same_inode = STORAGE._same_inode
_rename_noreplace = STORAGE._rename_noreplace
_unlink_transaction_component = STORAGE._unlink_transaction_component
_write_private_transaction_component = STORAGE._write_private_transaction_component
_recover_private_draft_transaction = STORAGE.recover_private_draft_transaction
_consume = STORAGE.consume_draft
_report_lock = STORAGE.report_lock
_write_controller_metadata = STORAGE.write_controller_metadata


def _cas_replace_private_draft(
    root: Path,
    draft_id: str,
    expected: Mapping[str, object],
    replacement: Mapping[str, object],
) -> None:
    STORAGE.cas_replace_private_draft(
        root,
        draft_id,
        canonical_bytes(expected),
        canonical_bytes(replacement),
    )


import compact_state
import fast_scan
import fast_scan_store
import impact_renderer
import payload_identity
import report_store

MAX_TRACE_SEEDS = 128
ADAPTERS = {"generic", "superpowers", "claude-feature-dev", "spec-kit"}
SUPERPOWERS_HANDOFF_MARKER = (
    "superpowers:after-approved-brainstorming;impact-refinement;manual-handoff-before-writing-plans"
)
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


class SettingsPayload(TypedDict):
    audience: str
    delivery: str
    impact_graph: GraphSettingsPayload


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
    impact_paths: dict[str, list[str]]
    rationales: dict[str, str | None]
    impact_confidences: dict[str, str]


class _SettingsContract(Protocol):
    def resolve(
        self,
        repo_root: Path,
        audience_override: str | None,
        delivery_override: str | None,
    ) -> SettingsPayload: ...


class _GraphContract(Protocol):
    ProviderStatus: type[ProviderStatusType]
    MAX_RECEIPT_BYTES: int

    def _safe_path(self, value: object) -> bool: ...

    def validate_receipt(self, value: object) -> tuple[str, ...]: ...

    def canonical_receipt_bytes(self, value: Mapping[str, object] | GraphReceiptType) -> bytes: ...

    def load_receipt_bytes(
        self, payload: bytes
    ) -> tuple[dict[str, object] | None, tuple[str, ...]]: ...


class _CacheContract(Protocol):
    _IDENTITY_FIELDS: frozenset[str]

    def _cache_directory(self, root: Path, create: bool) -> Path | None: ...

    def _read_artifact(self, path: Path) -> Mapping[str, object] | None: ...

    def _source_digests(self, value: Mapping[str, str]) -> dict[str, str]: ...

    def _canonical_json(self, value: object) -> bytes: ...

    def _normalize_receipt(self, value: object) -> tuple[dict[str, object], bytes]: ...


class _GraphCoordinatorContract(Protocol):
    GRAPH: _GraphContract
    CACHE: _CacheContract
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

    def trace_impact(
        self,
        repo_root: Path,
        draft: Mapping[str, object],
        seeds: tuple[ScanSeedType, ...],
        settings: Mapping[str, object],
        clock: object,
        runner: object = None,
        deadline: DeadlineType | None = None,
        source_inventory: SourceInventoryType | None = None,
    ) -> GraphReceiptType: ...


def _classes(value: object, names: tuple[str, ...]) -> bool:
    return all(isinstance(getattr(value, name, None), type) for name in names)


def _callables(value: object, names: tuple[str, ...]) -> bool:
    return all(callable(getattr(value, name, None)) for name in names)


def _is_settings_contract(value: object) -> TypeGuard[_SettingsContract]:
    return _callables(value, ("resolve",))


def _is_graph_contract(value: object) -> TypeGuard[_GraphContract]:
    return (
        _classes(value, ("ProviderStatus",))
        and isinstance(getattr(value, "MAX_RECEIPT_BYTES", None), int)
        and _callables(
            value,
            ("_safe_path", "validate_receipt", "canonical_receipt_bytes", "load_receipt_bytes"),
        )
    )


def _is_cache_contract(value: object) -> TypeGuard[_CacheContract]:
    return isinstance(getattr(value, "_IDENTITY_FIELDS", None), frozenset) and _callables(
        value,
        (
            "_cache_directory",
            "_read_artifact",
            "_source_digests",
            "_canonical_json",
            "_normalize_receipt",
        ),
    )


def _is_graph_coordinator_contract(value: object) -> TypeGuard[_GraphCoordinatorContract]:
    return (
        _is_graph_contract(getattr(value, "GRAPH", None))
        and _is_cache_contract(getattr(value, "CACHE", None))
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


def _load_settings_module() -> object:
    path = SCRIPT_DIR / "resolve-settings.py"
    spec = importlib.util.spec_from_file_location("rir_resolve_settings", path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load fixed settings resolver")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_loaded_settings = _load_settings_module()
if not _is_settings_contract(_loaded_settings):
    raise ImportError("settings sibling contract is incomplete")
SETTINGS = _loaded_settings


def _is_graph_delivery_contract(value: object) -> bool:
    coordinator = getattr(value, "GRAPH_COORDINATOR", None)
    delivery_contracts = getattr(value, "CONTRACTS", None)
    delivery_storage = getattr(value, "STORAGE", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "rir_graph_delivery.py")
        and _module_uses_sibling(delivery_contracts, SCRIPT_DIR / "rir_contracts.py")
        and _is_controller_contracts_contract(delivery_contracts)
        and _module_uses_sibling(delivery_storage, SCRIPT_DIR / "rir_storage.py")
        and _is_controller_storage_contract(delivery_storage)
        and _is_graph_coordinator_contract(coordinator)
        and _module_uses_sibling(coordinator, SCRIPT_DIR / "graph_coordinator.py")
        and _module_uses_sibling(coordinator.GRAPH, SCRIPT_DIR / "impact_graph.py")
        and _module_uses_sibling(coordinator.CACHE, SCRIPT_DIR / "graph_cache.py")
        and getattr(value, "GRAPH", None) is getattr(coordinator, "GRAPH", None)
        and getattr(value, "os", None) is os
        and _classes(
            value,
            (
                "TraceSeed",
                "ReceiptPayload",
                "CompactGraphPayload",
                "GraphContext",
            ),
        )
        and all(
            type(getattr(value, name, None)) is int and getattr(value, name) > 0
            for name in (
                "MAX_TRACE_SEEDS",
                "COMPACT_MAX_NODES",
                "COMPACT_MAX_PATHS",
                "COMPACT_MAX_FRONTIER",
                "COMPACT_MAX_BYTES",
            )
        )
        and _callables(
            value,
            (
                "graph_draft_identity",
                "compact_graph",
                "source_inventory_sha256",
                "new_trace_intent",
                "validate_trace_intent",
                "load_graph_context",
                "validate_graph_coverage",
                "trace_impact",
            ),
        )
    )


def _load_registered_graph_delivery(module_name: str, expected: Path) -> object:
    specification = importlib.util.spec_from_file_location(module_name, expected)
    if specification is None or specification.loader is None:
        raise ImportError("cannot load fixed graph delivery sibling")
    module = importlib.util.module_from_spec(specification)
    previous_contracts = sys.modules.get("rir_contracts")
    contracts_present = "rir_contracts" in sys.modules
    previous_storage = sys.modules.get("rir_storage")
    storage_present = "rir_storage" in sys.modules
    sys.modules[module_name] = module
    try:
        sys.modules["rir_contracts"] = cast(ModuleType, CONTRACTS)
        sys.modules["rir_storage"] = cast(ModuleType, STORAGE)
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError("cannot load fixed graph delivery sibling") from error
    finally:
        if contracts_present:
            sys.modules["rir_contracts"] = cast(ModuleType, previous_contracts)
        else:
            sys.modules.pop("rir_contracts", None)
        if storage_present:
            sys.modules["rir_storage"] = cast(ModuleType, previous_storage)
        else:
            sys.modules.pop("rir_storage", None)
    if not _is_graph_delivery_contract(module):
        sys.modules.pop(module_name, None)
        raise ImportError("graph delivery sibling contract is incomplete")
    return module


def _load_graph_delivery() -> object:
    sibling = SCRIPT_DIR / "rir_graph_delivery.py"
    expected = _regular_module_path(sibling)
    if expected is None or expected != sibling:
        raise ImportError("graph delivery sibling is unsafe")
    coordinator_path = SCRIPT_DIR / "graph_coordinator.py"
    legacy_coordinator_name = (
        "_rir_controller_graph_coordinator_"
        + hashlib.sha256(str(coordinator_path).encode("utf-8")).hexdigest()[:16]
    )
    if legacy_coordinator_name in sys.modules and not _is_graph_coordinator_contract(
        sys.modules.get(legacy_coordinator_name)
    ):
        raise ImportError("graph coordinator sibling contract is incomplete")
    module_name = (
        "_rir_controller_graph_delivery_"
        + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    )
    hashed_present = module_name in sys.modules
    hashed = sys.modules.get(module_name)
    canonical = sys.modules.get("rir_graph_delivery")
    if canonical is not None and _is_graph_delivery_contract(canonical):
        if not hashed_present:
            return canonical
        if not _module_uses_sibling(hashed, expected):
            raise ImportError("graph delivery sibling is unsafe")
        if not _is_graph_delivery_contract(hashed):
            raise ImportError("graph delivery sibling contract is incomplete")
        return hashed
    if hashed_present:
        if not _module_uses_sibling(hashed, expected):
            raise ImportError("graph delivery sibling is unsafe")
        if not _is_graph_delivery_contract(hashed):
            raise ImportError("graph delivery sibling contract is incomplete")
        if "rir_graph_delivery" not in sys.modules:
            sys.modules["rir_graph_delivery"] = cast(ModuleType, hashed)
        return hashed
    target_name = "rir_graph_delivery" if canonical is None else module_name
    return _load_registered_graph_delivery(target_name, expected)


GRAPH_DELIVERY = cast(Any, _load_graph_delivery())
GRAPH_COORDINATOR = GRAPH_DELIVERY.GRAPH_COORDINATOR
GRAPH = GRAPH_DELIVERY.GRAPH
TraceSeed = GRAPH_DELIVERY.TraceSeed


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


ScanResult = fast_scan.FastScanResult


_canonical_bytes = canonical_bytes
_bounded = bounded_bytes
_validate_analysis = validate_analysis


def _next_report_id(root: Path) -> str:
    reports = root / ".requirements-impact-refiner" / "reports"
    existing = set()
    if reports.is_dir() and not reports.is_symlink():
        existing = {
            path.name
            for path in reports.iterdir()
            if path.is_dir() and re.fullmatch(r"RPT-\d{3}", path.name)
        }
    for number in range(1, 1000):
        candidate = f"RPT-{number:03d}"
        if candidate not in existing:
            return candidate
    raise ValueError("no report IDs remain")


def _current_lineage(root: Path):
    reports = root / ".requirements-impact-refiner" / "reports"
    if not reports.exists():
        return None
    if reports.is_symlink() or not reports.is_dir():
        raise ValueError("report root must be a real directory")
    report_ids = sorted(
        path.name
        for path in reports.iterdir()
        if path.is_dir()
        and not path.is_symlink()
        and re.fullmatch(r"RPT-\d{3}", path.name)
        and (path / "current.json").is_file()
    )
    if not report_ids:
        return None
    if len(report_ids) != 1:
        raise ValueError("multiple current reports require an explicit report ID")
    current = report_store.load_current(root, report_ids[0])
    if current is None:
        return None
    prior_state, errors = compact_state.load_state_bytes(current.state_path.read_bytes())
    if errors or prior_state is None:
        raise ValueError("current report state is invalid")
    key_map: Mapping[str, object] | None = _load_controller_metadata(current)
    if key_map is None:
        key_map = _legacy_key_map(prior_state)
    return current, prior_state, key_map


def _legacy_key_map(state: Mapping[str, object]) -> dict[str, dict[str, str]]:
    sections: dict[str, tuple[object, str]] = {
        "invariants": (state.get("current_behavior", []), "inv"),
        "impacts": (state.get("impacts", []), "imp"),
        "decisions": (state.get("decisions", []), "dec"),
        "criteria": (state.get("criteria", []), "ac"),
    }
    result: dict[str, dict[str, str]] = {}
    for name, (rows, prefix) in sections.items():
        if not isinstance(rows, list):
            raise ValueError("current report cannot derive controller key lineage")
        mapping: dict[str, str] = {}
        for row in rows:
            identifier = row.get("id") if isinstance(row, dict) else None
            if not isinstance(identifier, str):
                raise ValueError("current report cannot derive controller key lineage")
            mapping[f"legacy-{prefix}-{identifier.rsplit('-', 1)[-1].lower()}"] = identifier
        result[name] = mapping
    return result


def _payload_sha256() -> str:
    candidate = SCRIPT_DIR.parent
    if not (candidate / ".codex-plugin" / "plugin.json").is_file():
        candidate = SCRIPT_DIR.parents[2]
    return payload_identity.payload_sha256(candidate)


def scan_impact(request: ScanRequest) -> ScanResult:
    root = _root(request.repo_root)
    if not isinstance(request.evidence, tuple):
        raise ValueError("scan evidence must be a tuple")
    settings = SETTINGS.resolve(root, request.audience_override, None)
    return fast_scan.execute_fast_scan(
        fast_scan.FastScanRequest(
            root, request.change_request, request.evidence, settings["audience"]
        ),
        settings["impact_graph"],
        _payload_sha256(),
    )


def _promoted_scan(root, request, settings):
    if request.scan_id is None:
        return None
    if DRAFT_ID_PATTERN.fullmatch(request.scan_id) is None:
        raise ValueError("invalid Fast Scan ID")
    prepared = fast_scan.prepare_fast_scan_identity(
        fast_scan.FastScanRequest(
            root,
            request.request,
            request.repository_evidence,
            settings["audience"],
        ),
        settings["impact_graph"],
        _payload_sha256(),
    )
    if prepared.scan_id != request.scan_id:
        raise ValueError(
            "Fast Scan request identity does not match: the change request "
            "text, repository evidence rows, audience, graph settings, and "
            "repository contents must all equal the original rir_scan call"
        )
    payload = fast_scan_store.load_scan_receipt_bytes(root, request.scan_id)
    value = json.loads(payload)
    errors = fast_scan.validate_fast_scan_receipt(value)
    if errors or fast_scan.canonical_fast_scan_bytes(value) != payload:
        raise ValueError("Fast Scan receipt is invalid")
    if value["status"] != "complete" or value["can_promote"] is not True:
        raise ValueError("Fast Scan receipt is not promotable")
    if (
        value["request_sha256"] != prepared.request_sha256
        or value["repo_root_sha256"] != prepared.repo_root_sha256
        or value["payload_sha256"] != _payload_sha256()
        or value["settings"] != prepared.settings.to_mapping()
        or value["source_inventory"] != dict(prepared.inventory_mapping)
        or value["seeds"] != [row.to_mapping() for row in prepared.seeds]
    ):
        raise ValueError("Fast Scan source or identity is stale")
    graph = value["graph_receipt"]
    graph_errors = GRAPH.validate_receipt(graph)
    if graph_errors:
        raise ValueError("Fast Scan graph receipt is invalid")
    graph_payload = GRAPH.canonical_receipt_bytes(graph)
    return {
        "scan_id": request.scan_id,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "receipt_id": graph["receipt_id"],
        "receipt_sha256": hashlib.sha256(graph_payload).hexdigest(),
    }


def begin_refinement(request: BeginRequest) -> DraftResult:
    root = _root(request.repo_root)
    if request.adapter not in ADAPTERS:
        raise ValueError(f"invalid adapter: {request.adapter}")
    if not isinstance(request.request, str) or not request.request.strip():
        raise ValueError("request must be nonempty")
    if not isinstance(request.repository_evidence, tuple) or any(
        not isinstance(item, str) or not item.strip() for item in request.repository_evidence
    ):
        raise ValueError("repository_evidence must contain nonempty strings")
    _bounded(
        {"request": request.request, "repository_evidence": request.repository_evidence},
        MAX_BEGIN_BYTES,
        "begin input",
    )
    settings = SETTINGS.resolve(root, request.audience_override, request.delivery_override)
    promotion = _promoted_scan(root, request, settings)
    current_lineage = _current_lineage(root)
    if current_lineage is None:
        report_id = _next_report_id(root)
        revision = 1
        previous_sha256 = "none"
        prior_state = None
        prior_key_map = None
    else:
        current, prior_state, prior_key_map = current_lineage
        report_id = current.report_id
        revision = current.revision + 1
        previous_sha256 = current.markdown_sha256
    draft_id = secrets.token_hex(16)
    path = _draft_path(root, draft_id)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    draft = {
        "schema_version": 1,
        "draft_id": draft_id,
        "repo_root": str(root),
        "request": request.request,
        "request_sha256": hashlib.sha256(request.request.encode("utf-8")).hexdigest(),
        "repository_evidence": list(request.repository_evidence),
        "adapter": request.adapter,
        "settings": dict(settings),
        "report_id": report_id,
        "revision": revision,
        "previous_sha256": previous_sha256,
        "prior_state": prior_state,
        "prior_key_map": prior_key_map,
        "created_at": now,
        "consumed": False,
    }
    if promotion is not None:
        draft["promoted_scan"] = promotion
    path = _write_private_draft(root, draft_id, _canonical_bytes(draft))
    return DraftResult(
        draft_id=draft_id,
        draft_path=path,
        report_id=report_id,
        revision=revision,
        previous_sha256=previous_sha256,
        settings=settings,
        prior_state=prior_state,
        prior_key_map=prior_key_map,
        scan_id=None if promotion is None else promotion["scan_id"],
        graph_receipt_id=(None if promotion is None else promotion["receipt_id"]),
    )


MAX_TRACE_SEEDS = GRAPH_DELIVERY.MAX_TRACE_SEEDS
COMPACT_MAX_NODES = GRAPH_DELIVERY.COMPACT_MAX_NODES
COMPACT_MAX_PATHS = GRAPH_DELIVERY.COMPACT_MAX_PATHS
COMPACT_MAX_FRONTIER = GRAPH_DELIVERY.COMPACT_MAX_FRONTIER
COMPACT_MAX_BYTES = GRAPH_DELIVERY.COMPACT_MAX_BYTES
TRACE_INTENT_KEYS = GRAPH_DELIVERY.TRACE_INTENT_KEYS
_STALE_CLEANUP_GUARD_KEYS = GRAPH_DELIVERY._STALE_CLEANUP_GUARD_KEYS

_graph_draft_identity = GRAPH_DELIVERY.graph_draft_identity
_compact_node_rank = GRAPH_DELIVERY._compact_node_rank
_compact_selection = GRAPH_DELIVERY._compact_selection
_compact_size = GRAPH_DELIVERY._compact_size
_enforce_compact_byte_budget = GRAPH_DELIVERY._enforce_compact_byte_budget
_compact_graph = GRAPH_DELIVERY.compact_graph
_source_inventory_sha256 = GRAPH_DELIVERY.source_inventory_sha256
_receipt_source_inventory = GRAPH_DELIVERY._receipt_source_inventory
_verify_source_inventory = GRAPH_DELIVERY._verify_source_inventory
_graph_trace_draft_identity = GRAPH_DELIVERY._graph_trace_draft_identity
_trace_intent_sha256 = GRAPH_DELIVERY._trace_intent_sha256
_new_trace_intent = GRAPH_DELIVERY.new_trace_intent
_validate_trace_intent = GRAPH_DELIVERY.validate_trace_intent
_intent_from_binding = GRAPH_DELIVERY._intent_from_binding
_open_existing_directory_at = GRAPH_DELIVERY._open_existing_directory_at
_read_bound_receipt_bytes = GRAPH_DELIVERY._read_bound_receipt_bytes
_repository_file_sha256 = GRAPH_DELIVERY._repository_file_sha256
_verify_receipt_sources = GRAPH_DELIVERY._verify_receipt_sources
_path_confidence = GRAPH_DELIVERY._path_confidence
_path_provenance = GRAPH_DELIVERY._path_provenance
_structured_path = GRAPH_DELIVERY._structured_path


def _graph_delivery_runtime() -> dict[str, object]:
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
        "graph_draft_identity": _graph_draft_identity,
        "compact_graph": _compact_graph,
        "source_inventory_sha256": _source_inventory_sha256,
        "receipt_source_inventory": _receipt_source_inventory,
        "verify_source_inventory": _verify_source_inventory,
        "trace_intent_sha256": _trace_intent_sha256,
        "new_trace_intent": _new_trace_intent,
        "validate_trace_intent": _validate_trace_intent,
        "read_bound_receipt_bytes": _read_bound_receipt_bytes,
        "remove_exact_trace_receipt": _remove_exact_trace_receipt,
        "recover_stale_cleanup_guard": _recover_stale_cleanup_guard,
        "clear_trace_intent": _clear_trace_intent,
        "load_graph_context": _load_graph_context,
        "validate_persisted_trace_receipt": _validate_persisted_trace_receipt,
        "bind_trace_receipt": _bind_trace_receipt,
    }


def _remove_exact_trace_receipt(
    root: Path,
    draft_id: str,
    expected_payload: bytes,
    *,
    commit=None,
    guard_intent_sha256=None,
) -> None:
    GRAPH_DELIVERY._remove_exact_trace_receipt(
        root,
        draft_id,
        expected_payload,
        commit=commit,
        guard_intent_sha256=guard_intent_sha256,
        _runtime=_graph_delivery_runtime(),
    )


def _recover_stale_cleanup_guard(root: Path, draft_id: str, intent: Mapping[str, object]) -> bool:
    return GRAPH_DELIVERY._recover_stale_cleanup_guard(
        root,
        draft_id,
        intent,
        _runtime=_graph_delivery_runtime(),
    )


def _clear_trace_intent(
    root: Path, draft: Mapping[str, object], intent: Mapping[str, object]
) -> dict[str, object]:
    return GRAPH_DELIVERY._clear_trace_intent(
        root,
        draft,
        intent,
        _runtime=_graph_delivery_runtime(),
    )


def _load_graph_context(
    root: Path,
    draft: Mapping[str, object],
    selected_receipt_id: str | None,
    *,
    deadline=None,
):
    return GRAPH_DELIVERY.load_graph_context(
        root,
        draft,
        selected_receipt_id,
        deadline=deadline,
        _runtime=_graph_delivery_runtime(),
    )


def _load_promoted_scan_context(
    root: Path, draft: Mapping[str, object], selected_receipt_id: str | None
):
    binding = draft.get("promoted_scan")
    if not isinstance(binding, dict) or set(binding) != {
        "scan_id",
        "sha256",
        "receipt_id",
        "receipt_sha256",
    }:
        raise ValueError("promoted Fast Scan binding is invalid")
    if selected_receipt_id != binding["receipt_id"]:
        raise ValueError("Fast Scan graph receipt does not match draft")
    request_value = draft.get("request")
    evidence_value = draft.get("repository_evidence")
    adapter_value = draft.get("adapter")
    settings_value = draft.get("settings")
    if (
        not isinstance(request_value, str)
        or not isinstance(evidence_value, list)
        or not all(isinstance(item, str) for item in evidence_value)
        or not isinstance(adapter_value, str)
        or not isinstance(settings_value, dict)
        or not isinstance(settings_value.get("audience"), str)
        or not isinstance(settings_value.get("delivery"), str)
    ):
        raise ValueError("promoted Fast Scan binding is invalid")
    audience = settings_value["audience"]
    delivery = settings_value["delivery"]
    request = BeginRequest(
        root,
        request_value,
        tuple(evidence_value),
        adapter_value,
        audience,
        delivery,
        binding["scan_id"],
    )
    promotion = _promoted_scan(root, request, draft["settings"])
    if promotion != binding:
        raise ValueError("promoted Fast Scan binding is stale")
    payload = fast_scan_store.load_scan_receipt_bytes(root, binding["scan_id"])
    if hashlib.sha256(payload).hexdigest() != binding["sha256"]:
        raise ValueError("promoted Fast Scan digest is stale")
    wrapper = json.loads(payload)
    if not isinstance(wrapper, dict):
        raise ValueError("promoted Fast Scan binding is invalid")
    receipt = wrapper["graph_receipt"]
    if not _is_receipt_payload(receipt):
        raise ValueError("promoted Fast Scan binding is invalid")
    graph_payload = GRAPH.canonical_receipt_bytes(receipt)
    if hashlib.sha256(graph_payload).hexdigest() != binding["receipt_sha256"]:
        raise ValueError("promoted graph receipt digest is stale")
    _verify_receipt_sources(root, receipt)
    return {"receipt": receipt, "sha256": binding["receipt_sha256"], "binding": binding}


def _validate_graph_coverage(analysis: Mapping[str, object], context) -> None:
    GRAPH_DELIVERY.validate_graph_coverage(analysis, context)


def _validate_persisted_trace_receipt(
    root: Path,
    draft: Mapping[str, object],
    normalized_seeds,
    graph_settings: Mapping[str, object],
    intent: Mapping[str, object],
    expected_payload: bytes | None = None,
):
    return GRAPH_DELIVERY._validate_persisted_trace_receipt(
        root,
        draft,
        normalized_seeds,
        graph_settings,
        intent,
        expected_payload,
        _runtime=_graph_delivery_runtime(),
    )


def _bind_trace_receipt(
    root: Path,
    draft: Mapping[str, object],
    normalized_seeds,
    graph_settings: Mapping[str, object],
    intent: Mapping[str, object],
    receipt_value,
    stored: bytes,
    expected_request_sha256: str,
    cache_key: str,
    source_digests: Mapping[str, str],
    source_inventory_sha256: str,
    source_inventory_complete: bool,
    source_inventory_reason: str | None,
):
    return GRAPH_DELIVERY._bind_trace_receipt(
        root,
        draft,
        normalized_seeds,
        graph_settings,
        intent,
        receipt_value,
        stored,
        expected_request_sha256,
        cache_key,
        source_digests,
        source_inventory_sha256,
        source_inventory_complete,
        source_inventory_reason,
        _runtime=_graph_delivery_runtime(),
    )


def trace_impact(request: TraceRequest) -> TraceResult:
    return GRAPH_DELIVERY.trace_impact(request, _runtime=_graph_delivery_runtime())


def _ids(rows, prefix, prior=None):
    prior = {} if prior is None else dict(prior)
    result = {}
    used_numbers = {
        int(identifier.rsplit("-", 1)[1])
        for identifier in prior.values()
        if isinstance(identifier, str) and re.fullmatch(rf"{prefix}-\d{{3}}", identifier)
    }
    next_number = 1
    for row in rows:
        key = row["key"]
        if key in prior:
            result[key] = prior[key]
            continue
        while next_number in used_numbers:
            next_number += 1
        result[key] = f"{prefix}-{next_number:03d}"
        used_numbers.add(next_number)
        next_number += 1
    return result


def _map_keys(values, mapping, label):
    result = []
    for value in values:
        key = _local_key(value, label)
        if key not in mapping:
            raise ValueError(f"unknown {label} key {key}")
        result.append(mapping[key])
    return result


def _build_state(draft, analysis, graph_context=None):
    _validate_analysis(analysis)
    prior_state = draft.get("prior_state")
    prior_key_map = draft.get("prior_key_map") or {}
    requirement_id = (
        prior_state["original_requirement"]["id"] if isinstance(prior_state, dict) else "REQ-001"
    )
    if prior_key_map:
        missing_impacts = sorted(
            set(prior_key_map.get("impacts", {})) - {row["key"] for row in analysis["impacts"]}
        )
        if missing_impacts:
            raise ValueError(f"impact key disappeared: {missing_impacts[0]}")
    invariant_ids = _ids(analysis["invariants"], "INV", prior_key_map.get("invariants"))
    impact_ids = _ids(analysis["impacts"], "IMP", prior_key_map.get("impacts"))
    decision_ids = _ids(analysis["decisions"], "DEC", prior_key_map.get("decisions"))
    criterion_ids = _ids(analysis["criteria"], "AC", prior_key_map.get("criteria"))
    key_map = {
        "invariants": invariant_ids,
        "impacts": impact_ids,
        "decisions": decision_ids,
        "criteria": criterion_ids,
    }
    impacts = []
    for row in analysis["impacts"]:
        impacts.append(
            {
                "id": impact_ids[row["key"]],
                "requirement": requirement_id,
                "category": row["category"],
                "severity": row["severity"],
                "state": row["state"],
                "evidence_level": row["evidence_level"],
                "evidence": row["evidence"],
                "invariants": _map_keys(row["invariant_keys"], invariant_ids, "invariant"),
                "decisions": _map_keys(row["decision_keys"], decision_ids, "decision"),
                "criteria": _map_keys(row["criterion_keys"], criterion_ids, "criterion"),
            }
        )
    current_behavior = [
        {
            "id": invariant_ids[row["key"]],
            "behavior": row["behavior"],
            "evidence_level": row["evidence_level"],
            "evidence": row["evidence"],
        }
        for row in analysis["invariants"]
    ]
    preserved = []
    for row in analysis["invariants"]:
        affected = [
            impact_ids[impact["key"]]
            for impact in analysis["impacts"]
            if row["key"] in impact["invariant_keys"]
        ]
        preserved.append(
            {
                "id": invariant_ids[row["key"]],
                "requirement": requirement_id,
                "impacts": affected,
                "evidence": row["evidence"],
            }
        )
    decisions = [
        {
            "id": decision_ids[row["key"]],
            "choice": row["choice"],
            "requirement": requirement_id,
            "accepted_impacts": _map_keys(row["accepted_impact_keys"], impact_ids, "impact"),
            "rationale": row["rationale"],
        }
        for row in analysis["decisions"]
    ]
    criteria = [
        {
            "id": criterion_ids[row["key"]],
            "requirement": requirement_id,
            "impact": _map_keys([row["impact_key"]], impact_ids, "impact")[0],
            "invariant": _map_keys([row["invariant_key"]], invariant_ids, "invariant")[0],
            "criterion": row["criterion"],
            "evidence": row["evidence"],
        }
        for row in analysis["criteria"]
    ]
    decision_needed = None
    if analysis["phase"] == "pre-decision":
        decision_needed = {
            "question": analysis["decision_needed"]["question"],
            "options": [
                {
                    "option": row["option"],
                    "impacts": _map_keys(row["impact_keys"], impact_ids, "impact"),
                    "tradeoff": row["tradeoff"],
                }
                for row in analysis["decision_needed"]["options"]
            ],
        }
    unresolved = [
        {
            "impact": _map_keys([row["impact_key"]], impact_ids, "impact")[0],
            "state": row["state"],
            "rationale": row["rationale"],
            "decision": None
            if row["decision_key"] is None
            else _map_keys([row["decision_key"]], decision_ids, "decision")[0],
            "owner": row["owner"],
        }
        for row in analysis["unresolved"]
    ]
    remaining = [
        row["id"] for row in impacts if row["state"] in {"accepted", "deferred", "blocked"}
    ]
    if not remaining:
        remaining = [row["id"] for row in impacts]
    all_report_ids = [
        requirement_id,
        *list(invariant_ids.values()),
        *list(impact_ids.values()),
        *list(decision_ids.values()),
    ]
    summary = [
        {
            "impact_id": impact_ids[row["key"]],
            **row["summary"],
            "severity": row["severity"],
            "status": row["state"],
        }
        for row in analysis["impacts"]
    ]
    first_decision = decisions[0]["id"] if decisions else None
    delta: dict[str, list[str]] = {category: [] for category in compact_state.DELTA_CATEGORIES}
    if prior_state is None:
        delta["new"] = list(impact_ids.values())
    else:
        previous_states = {row["id"]: row["state"] for row in prior_state["impacts"]}
        terminal = {"resolved", "accepted", "superseded"}
        active = {"detected", "refining", "mitigated", "deferred", "blocked"}
        state_category = {
            "detected": "unchanged",
            "refining": "unchanged",
            "mitigated": "mitigated",
            "resolved": "resolved",
            "accepted": "accepted",
            "deferred": "deferred",
            "blocked": "blocked",
            "superseded": "superseded",
        }
        for impact in impacts:
            previous = previous_states.get(impact["id"])
            if previous is None:
                category = "new"
            elif previous == impact["state"]:
                category = "unchanged"
            elif previous in terminal and impact["state"] in active:
                category = "reopened"
            else:
                category = state_category[impact["state"]]
            delta[category].append(impact["id"])
    prior_history = []
    if prior_state is not None:
        current_decision_ids = set(decision_ids.values())
        for prior_row in prior_state["history"]:
            history_row = dict(prior_row)
            historical_decision = history_row.get("decision")
            if (
                analysis["phase"] == "pre-decision"
                and isinstance(historical_decision, str)
                and historical_decision not in current_decision_ids
            ):
                history_row["decision"] = None
                history_row["summary"] = (
                    f"{history_row['summary']} The historical decision remains "
                    "authoritative in the prior immutable revision."
                )
            prior_history.append(history_row)
    original_requirement = (
        {
            "id": requirement_id,
            "request": draft["request"],
            "source": "User request and supplied repository evidence.",
        }
        if prior_state is None
        else prior_state["original_requirement"]
    )
    if draft.get("adapter") == "superpowers":
        handoff_workflow = SUPERPOWERS_HANDOFF_MARKER
    elif analysis["phase"] == "pre-decision" or any(row["state"] == "blocked" for row in impacts):
        handoff_workflow = "Not ready"
    else:
        handoff_workflow = analysis["workflow"]
    scope = list(analysis["scope"])
    structured_paths = []
    if graph_context is not None:
        receipt = graph_context["receipt"]
        receipt_nodes = {row["id"]: row for row in receipt["nodes"]}
        receipt_edges = {row["id"]: row for row in receipt["edges"]}
        receipt_paths = {row["id"]: row for row in receipt["paths"]}
        for row in analysis["impacts"]:
            path_descriptions = []
            path_provenance = []
            impact_paths = []
            for path_key in graph_context["impact_paths"][row["key"]]:
                path = receipt_paths[path_key]
                labels = [receipt_nodes[node]["label"] for node in path["nodes"]]
                path_descriptions.append(f"{path_key}: " + " → ".join(labels))
                path_provenance.append(
                    f"{path_key}: {_path_provenance(path, receipt_nodes, receipt_edges)}"
                )
                impact_paths.append(_structured_path(path, receipt_nodes, receipt_edges))
            if impact_paths:
                structured_paths.append(
                    {
                        "impact": impact_ids[row["key"]],
                        "paths": impact_paths,
                    }
                )
            rationale = graph_context["rationales"].get(row["key"])
            scope.append(
                {
                    "boundary": f"Graph paths for {impact_ids[row['key']]}",
                    "evidence": " || ".join(path_descriptions)
                    if path_descriptions
                    else str(rationale),
                    "confidence": (
                        " || ".join(path_provenance)
                        if path_provenance
                        else "provider unavailable; confidence unknown; location unavailable"
                    ),
                }
            )
        provider_summary = [f"{row['name']} ({row['status']})" for row in receipt["providers"]]
        elapsed = int(receipt["timings_ms"].get("total", 0))
        frontier_ids = ",".join(row["id"] for row in receipt["frontier"]) or "none"
        scope.append(
            {
                "boundary": "Impact graph coverage",
                "evidence": (
                    f"Impact scan: {elapsed / 1000:.1f} s · "
                    f"{' + '.join(provider_summary) or 'no provider'} · "
                    f"{len(receipt['nodes'])} nodes / {len(receipt['edges'])} edges · "
                    f"{len(receipt['frontier'])} unknown frontiers"
                ),
                "confidence": (
                    f"{receipt['budget_status']}; receipt {receipt['receipt_id']}; "
                    f"sha256 {graph_context['sha256']}; frontier {frontier_ids}"
                ),
            }
        )
        if len(scope) > 128:
            raise ValueError("scope has too many rows after graph coverage injection")
        if any(
            len(value.encode("utf-8")) > MAX_STRING_BYTES
            for row in scope
            for value in row.values()
            if isinstance(value, str)
        ):
            raise ValueError("graph coverage scope exceeds string limit")
    state = {
        "schema_version": 1,
        "report": {
            "id": draft["report_id"],
            "revision": draft["revision"],
            "previous_sha256": draft["previous_sha256"],
            "phase": analysis["phase"],
        },
        "settings": draft["settings"],
        "original_requirement": original_requirement,
        "refined_requirement": {
            "id": requirement_id,
            "revision": analysis["refined_requirement"],
            "decision": first_decision,
            "supersedes": [],
        },
        "current_behavior": current_behavior,
        "preserved_invariants": preserved,
        "impacts": impacts,
        "decision_needed": decision_needed,
        "decisions": decisions,
        "delta": delta,
        "history": [
            *prior_history,
            {
                "requirement": requirement_id,
                "revision": analysis["refined_requirement"],
                "decision": first_decision,
                "superseded_impacts": [],
                "summary": "Controller-created refinement revision.",
            },
        ],
        "criteria": criteria,
        "unresolved": unresolved,
        "scope": scope,
        "handoff": {
            "refined_requirement": requirement_id
            if analysis["phase"] == "post-decision"
            else "Not ready until the pending decision is selected.",
            "report_ids": all_report_ids,
            "remaining_risks": remaining,
            "criteria": list(criterion_ids.values()),
            "workflow": handoff_workflow,
        },
        "summary": summary,
    }
    if structured_paths:
        state["graph_paths"] = structured_paths
    errors = compact_state.validate_state(state)
    if errors:
        raise ValueError("; ".join(errors))
    return state, key_map


def finalize_refinement(request: FinalizeRequest) -> FinalizeResult:
    root = _root(request.repo_root)
    _bounded(request.analysis, MAX_FINALIZE_BYTES, "finalize input")
    draft = load_draft(root, request.draft_id)
    if draft.get("consumed") is True:
        raise ValueError("draft is already consumed")
    with _report_lock(root, str(draft["report_id"])):
        draft = load_draft(root, request.draft_id)
        if draft.get("consumed") is True:
            raise ValueError("draft is already consumed")
        settings_value = draft.get("settings")
        graph_settings = (
            settings_value.get("impact_graph") if isinstance(settings_value, dict) else None
        )
        if not isinstance(graph_settings, dict):
            raise ValueError("draft graph settings are invalid")
        graph_context: GraphContext | None = None
        if graph_settings.get("enabled") is True:
            graph_context = (
                _load_promoted_scan_context(root, draft, request.graph_receipt_id)
                if draft.get("promoted_scan") is not None
                else _load_graph_context(root, draft, request.graph_receipt_id)
            )
            _validate_analysis(request.analysis)
            _validate_graph_coverage(request.analysis, graph_context)
        elif request.graph_receipt_id is not None:
            raise ValueError("graph_receipt_id is not allowed when impact graph is disabled")
        state, key_map = _build_state(draft, request.analysis, graph_context)
        state_bytes = _canonical_bytes(state)
        _write_controller_metadata(
            root,
            draft,
            state_bytes,
            key_map,
            None
            if graph_context is None
            else {
                "receipt_id": graph_context["receipt"]["receipt_id"],
                "sha256": graph_context["sha256"],
            },
        )
        try:
            published = report_store.publish_revision(root, state_bytes, resume_partial=True)
        except (FileExistsError, report_store.ReportStoreError) as error:
            raise ValueError(f"controller publication failed: {error}") from error
        stored_state, errors = compact_state.load_state_bytes(published.state_path.read_bytes())
        if errors or stored_state is None:
            raise ValueError("published state could not be verified")
        stored_settings = stored_state.get("settings")
        delivery = stored_settings.get("delivery") if isinstance(stored_settings, dict) else None
        if not isinstance(delivery, str):
            raise ValueError("published state could not be verified")
        display = (
            impact_renderer.render_compact(stored_state)
            if delivery == "compact"
            else impact_renderer.render_markdown(stored_state)
        )
        if display.endswith("\n"):
            display = display[:-1]
        _consume(_draft_path(root, request.draft_id), draft, published, key_map)
    return FinalizeResult(
        status="published",
        report_id=published.report_id,
        revision=published.revision,
        delivery=delivery,
        display_text=display,
        state_path=published.state_path,
        markdown_path=published.markdown_path,
        markdown_sha256=published.markdown_sha256,
    )
