#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import secrets
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable, Protocol, SupportsInt, TypedDict, cast

if TYPE_CHECKING:
    from fast_scan import FastScanResult as ScanResult
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
    from rir_previous import PreviousLookupRequest, PreviousReportCandidate, PreviousReportResult
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
    COMPACT_STATE: object
    IMPACT_RENDERER: object
    REPORT_STORE: object
    report_store: object

    def root_path(self, path: Path) -> Path: ...

    def write_private_draft(self, root: Path, draft_id: str, payload: bytes) -> Path: ...

    def load_private_draft(self, repo_root: Path, draft_id: str) -> dict[str, object]: ...

    def replace_private_draft(
        self, root: Path, draft_id: str, value: Mapping[str, object]
    ) -> None: ...

    def draft_path(self, root: Path, draft_id: str) -> Path: ...

    def controller_metadata_path(self, report_id: str, revision: int, root: Path) -> Path: ...

    def load_controller_metadata(self, current: object) -> dict[str, object] | None: ...

    def load_controller_completion_metadata(self, current: object) -> dict[str, object] | None: ...

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
        analysis_sha256: str | None = None,
        context_identity: Mapping[str, object] | None = None,
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
    compact_state = getattr(value, "COMPACT_STATE", None)
    renderer = getattr(value, "IMPACT_RENDERER", None)
    report_store = getattr(value, "REPORT_STORE", None)
    callable_names = (
        "root_path",
        "write_private_draft",
        "load_private_draft",
        "replace_private_draft",
        "draft_path",
        "controller_metadata_path",
        "load_controller_metadata",
        "load_controller_completion_metadata",
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
        and _module_uses_sibling(compact_state, SCRIPT_DIR / "compact_state.py")
        and _module_uses_sibling(renderer, SCRIPT_DIR / "impact_renderer.py")
        and _module_uses_sibling(
            getattr(renderer, "impact_report", None), SCRIPT_DIR / "impact_report.py"
        )
        and _module_uses_sibling(report_store, SCRIPT_DIR / "report_store.py")
        and getattr(value, "report_store", None) is report_store
        and getattr(report_store, "compact_state", None) is compact_state
        and getattr(report_store, "impact_renderer", None) is renderer
        and getattr(renderer, "compact_state", None) is compact_state
        and all(
            callable(getattr(compact_state, name, None))
            for name in ("load_state_bytes", "validate_state")
        )
        and all(
            callable(getattr(renderer, name, None))
            for name in ("render_markdown", "render_compact", "validate_rendered_markdown")
        )
        and isinstance(getattr(report_store, "ReportStoreError", None), type)
        and isinstance(getattr(report_store, "CurrentRevision", None), type)
        and all(
            callable(getattr(report_store, name, None))
            for name in ("load_current", "publish_revision", "report_directory")
        )
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
_load_controller_completion_metadata = STORAGE.load_controller_completion_metadata
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
    source_inventory: dict[str, object]
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

    def resolve_delta_max_seconds(self, repo_root: Path) -> int: ...


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


def _execute_controller_sibling(
    module_name: str,
    expected: Path,
    validator: Callable[[object], bool],
    label: str,
    aliases: Mapping[str, ModuleType] | None = None,
) -> object:
    specification = importlib.util.spec_from_file_location(module_name, expected)
    if specification is None or specification.loader is None:
        raise ImportError(f"cannot load fixed controller {label} sibling")
    module = importlib.util.module_from_spec(specification)
    previous = {name: (name in sys.modules, sys.modules.get(name)) for name in (aliases or {})}
    sys.modules[module_name] = module
    try:
        if aliases:
            sys.modules.update(aliases)
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError(f"cannot load fixed controller {label} sibling") from error
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
        raise ImportError(f"controller {label} sibling contract is incomplete")
    return module


def _load_controller_sibling(
    filename: str,
    canonical_name: str,
    prefix: str,
    validator: Callable[[object], bool],
    label: str,
    aliases: Mapping[str, ModuleType] | None = None,
    rewire_validator: Callable[[object], bool] | None = None,
) -> object:
    sibling = SCRIPT_DIR / filename
    expected = _regular_module_path(sibling)
    if expected is None or expected != sibling:
        raise ImportError(f"controller {label} sibling is unsafe")
    hashed_name = prefix + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    hashed_present = hashed_name in sys.modules
    hashed = sys.modules.get(hashed_name)

    def rewired() -> object:
        if aliases is None:
            raise ImportError(f"controller {label} sibling contract is incomplete")
        identity = []
        for alias, module in sorted(aliases.items()):
            registrations = sorted(name for name, value in sys.modules.items() if value is module)
            identity.append(
                (
                    alias,
                    getattr(module, "__name__", ""),
                    getattr(module, "__file__", ""),
                    registrations,
                )
            )
        suffix = hashlib.sha256(repr(identity).encode("utf-8")).hexdigest()[:16]
        rewired_name = f"{hashed_name}_{suffix}"
        existing = sys.modules.get(rewired_name)
        if existing is not None:
            if not _module_uses_sibling(existing, expected):
                raise ImportError(f"controller {label} sibling is unsafe")
            if not validator(existing):
                raise ImportError(f"controller {label} sibling contract is incomplete")
            return existing
        return _execute_controller_sibling(
            rewired_name,
            expected,
            validator,
            label,
            aliases=aliases,
        )

    if canonical_name not in sys.modules:
        if hashed_present:
            if not _module_uses_sibling(hashed, expected):
                raise ImportError(f"controller {label} sibling is unsafe")
            if not validator(hashed):
                raise ImportError(f"controller {label} sibling contract is incomplete")
            sys.modules[canonical_name] = cast(ModuleType, hashed)
            return hashed
        return _execute_controller_sibling(
            canonical_name, expected, validator, label, aliases=aliases
        )
    canonical = sys.modules.get(canonical_name)
    if _module_uses_sibling(canonical, expected):
        if validator(canonical) and not hashed_present:
            return canonical
        if hashed_present:
            if not _module_uses_sibling(hashed, expected):
                raise ImportError(f"controller {label} sibling is unsafe")
            if validator(hashed):
                return hashed
            if rewire_validator is not None and rewire_validator(hashed):
                return rewired()
            raise ImportError(f"controller {label} sibling contract is incomplete")
        if rewire_validator is not None and rewire_validator(canonical):
            return _execute_controller_sibling(
                hashed_name, expected, validator, label, aliases=aliases
            )
        raise ImportError(f"controller {label} sibling contract is incomplete")
    if hashed_present:
        if not _module_uses_sibling(hashed, expected):
            raise ImportError(f"controller {label} sibling is unsafe")
        if validator(hashed):
            return hashed
        if rewire_validator is not None and rewire_validator(hashed):
            return rewired()
        raise ImportError(f"controller {label} sibling contract is incomplete")
    return _execute_controller_sibling(hashed_name, expected, validator, label, aliases=aliases)


def _is_fast_scan_renderer_contract(value: object) -> bool:
    word_limit = getattr(value, "WORD_LIMIT", None)
    return (
        type(word_limit) is int
        and word_limit > 0
        and isinstance(getattr(value, "AUDIENCES", None), set)
        and isinstance(getattr(value, "LOCALES", None), set)
        and callable(getattr(value, "render_fast_scan", None))
    )


def _is_fast_scan_store_contract(value: object) -> bool:
    return (
        isinstance(getattr(value, "_ID", None), re.Pattern)
        and all(
            type(getattr(value, name, None)) is int and getattr(value, name) > 0
            for name in ("_MAX", "_MAX_JSON_DEPTH")
        )
        and _callables(
            value,
            ("_configure_delta_worker", "publish_scan_receipt", "load_scan_receipt_bytes"),
        )
    )


def _is_fast_scan_coordinator_graph(value: object) -> bool:
    graph = getattr(value, "GRAPH", None)
    builtin = getattr(value, "BUILTIN", None)
    cache = getattr(value, "CACHE", None)
    providers = getattr(value, "PROVIDERS", None)
    priority = getattr(providers, "PROVIDER_PRIORITY", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "graph_coordinator.py")
        and _module_uses_sibling(graph, SCRIPT_DIR / "impact_graph.py")
        and _module_uses_sibling(builtin, SCRIPT_DIR / "graph_builtin.py")
        and _module_uses_sibling(cache, SCRIPT_DIR / "graph_cache.py")
        and _module_uses_sibling(providers, SCRIPT_DIR / "graph_providers.py")
        and getattr(builtin, "GRAPH", None) is graph
        and getattr(cache, "GRAPH", None) is graph
        and isinstance(priority, tuple)
        and all(isinstance(item, str) for item in priority)
        and _classes(
            graph,
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
        and _classes(builtin, ("ScanSeed", "ScanLimits", "BuiltInScanResult"))
        and _classes(cache, ("CacheResult",))
        and _classes(
            providers,
            ("Deadline", "ProviderProbe", "ProviderQuery", "ProviderResult", "ProviderSpec"),
        )
        and getattr(value, "GraphSettings", None) is getattr(graph, "GraphSettings", None)
        and getattr(value, "Deadline", None) is getattr(providers, "Deadline", None)
        and getattr(value, "ScanSeed", None) is getattr(builtin, "ScanSeed", None)
        and getattr(value, "ScanLimits", None) is getattr(builtin, "ScanLimits", None)
        and all(
            getattr(value, name, None) is getattr(providers, name, None)
            for name in ("ProviderProbe", "ProviderQuery", "ProviderResult", "ProviderSpec")
        )
        and getattr(value, "discover_providers", None)
        is getattr(providers, "discover_providers", None)
        and getattr(value, "run_provider", None) is getattr(providers, "run_provider", None)
        and _classes(value, ("SourceInventory",))
        and _callables(
            value,
            (
                "_settings",
                "_request_sha256",
                "_seed_key",
                "_trace_identity",
                "_collect_source_digests",
                "_configure_delta_worker",
                "trace_impact",
            ),
        )
    )


def _is_fast_scan_shape(value: object) -> bool:
    renderer = getattr(value, "fast_scan_renderer", None)
    store = getattr(value, "fast_scan_store", None)
    builtin = getattr(value, "graph_builtin", None)
    coordinator = getattr(value, "graph_coordinator", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "fast_scan.py")
        and _module_uses_sibling(renderer, SCRIPT_DIR / "fast_scan_renderer.py")
        and _is_fast_scan_renderer_contract(renderer)
        and _module_uses_sibling(store, SCRIPT_DIR / "fast_scan_store.py")
        and _is_fast_scan_store_contract(store)
        and _module_uses_sibling(builtin, SCRIPT_DIR / "graph_builtin.py")
        and _is_fast_scan_coordinator_graph(coordinator)
        and getattr(builtin, "GRAPH", None) is getattr(coordinator, "GRAPH", None)
        and _classes(
            value,
            (
                "DerivedSeed",
                "FastScanRequest",
                "FastScanReceipt",
                "FastScanResult",
                "PreparedFastScan",
            ),
        )
        and all(
            type(getattr(value, name, None)) is int and getattr(value, name) > 0
            for name in (
                "MAX_CHANGE_BYTES",
                "MAX_EVIDENCE_ROWS",
                "MAX_EVIDENCE_BYTES",
                "MAX_SEEDS",
                "MAX_SOURCE_BYTES",
                "MAX_FRONTIER",
                "MAX_CANDIDATES",
            )
        )
        and _callables(
            value,
            (
                "derive_seeds",
                "execute_fast_scan",
                "prepare_fast_scan_identity",
                "validate_fast_scan_receipt",
                "canonical_fast_scan_bytes",
            ),
        )
    )


def _is_delta_contract(value: object) -> bool:
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "rir_delta.py")
        and _classes(
            value,
            ("DeltaScanContext", "DeltaSeed", "DeltaSeedSelection", "DeltaSourceInventory"),
        )
        and type(getattr(value, "MAX_DELTA_SECONDS", None)) is int
        and _callables(
            value,
            (
                "bind_delta_context",
                "collect_sources",
                "derive_delta_seeds",
                "derive_delta_seed_selection",
                "delta_timeout_fallback",
                "load_trusted_previous_artifacts",
                "validate_delta_hints",
            ),
        )
    )


def _is_payload_identity_contract(value: object) -> bool:
    root_files = getattr(value, "ROOT_FILES", None)
    return (
        isinstance(root_files, tuple)
        and all(isinstance(item, str) for item in root_files)
        and {
            "scripts/fast_scan.py",
            "scripts/fast_scan_renderer.py",
            "scripts/fast_scan_store.py",
            "scripts/rir_previous.py",
            "scripts/rir_previous_renderer.py",
            "scripts/rir_controller.py",
            "scripts/rir_delta.py",
            "scripts/rir_delta_worker.py",
        }
        <= set(root_files)
        and _callables(value, ("functional_paths", "payload_sha256"))
    )


def _is_settings_contract(value: object) -> TypeGuard[_SettingsContract]:
    return _callables(value, ("resolve", "resolve_delta_max_seconds"))


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


def _load_controller_fast_scan_graph():
    if not _is_fast_scan_coordinator_graph(GRAPH_COORDINATOR):
        raise ImportError("controller Fast Scan coordinator graph is incomplete")
    renderer = _load_controller_sibling(
        "fast_scan_renderer.py",
        "fast_scan_renderer",
        "_rir_controller_fast_scan_renderer_",
        _is_fast_scan_renderer_contract,
        "Fast Scan renderer",
    )
    store = _load_controller_sibling(
        "fast_scan_store.py",
        "fast_scan_store",
        "_rir_controller_fast_scan_store_",
        _is_fast_scan_store_contract,
        "Fast Scan store",
    )
    delta = _load_controller_sibling(
        "rir_delta.py",
        "rir_delta",
        "_rir_controller_delta_",
        _is_delta_contract,
        "delta scan",
    )

    def valid(value: object) -> bool:
        return (
            _is_fast_scan_shape(value)
            and getattr(value, "fast_scan_renderer", None) is renderer
            and getattr(value, "fast_scan_store", None) is store
            and getattr(value, "graph_builtin", None) is GRAPH_COORDINATOR.BUILTIN
            and getattr(value, "graph_coordinator", None) is GRAPH_COORDINATOR
        )

    fast_scan_module = _load_controller_sibling(
        "fast_scan.py",
        "fast_scan",
        "_rir_controller_fast_scan_",
        valid,
        "Fast Scan",
        aliases={
            "fast_scan_renderer": cast(ModuleType, renderer),
            "fast_scan_store": cast(ModuleType, store),
            "graph_builtin": cast(ModuleType, GRAPH_COORDINATOR.BUILTIN),
            "graph_coordinator": cast(ModuleType, GRAPH_COORDINATOR),
        },
        rewire_validator=_is_fast_scan_shape,
    )
    payload_identity_module = _load_controller_sibling(
        "payload_identity.py",
        "payload_identity",
        "_rir_controller_payload_identity_",
        _is_payload_identity_contract,
        "payload identity",
    )
    return renderer, store, fast_scan_module, payload_identity_module, delta


(
    FAST_SCAN_RENDERER,
    FAST_SCAN_STORE,
    FAST_SCAN,
    PAYLOAD_IDENTITY,
    DELTA,
) = _load_controller_fast_scan_graph()
fast_scan_renderer = FAST_SCAN_RENDERER
fast_scan_store = FAST_SCAN_STORE
fast_scan = FAST_SCAN
payload_identity = PAYLOAD_IDENTITY
rir_delta = DELTA


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


if not TYPE_CHECKING:
    ScanResult = FAST_SCAN.FastScanResult


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


def _is_lineage_contract(value: object) -> bool:
    lineage_storage = getattr(value, "STORAGE", None)
    lineage_report_store = getattr(value, "REPORT_STORE", None)
    lineage_compact_state = getattr(value, "COMPACT_STATE", None)
    lineage_renderer = getattr(value, "IMPACT_RENDERER", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "rir_lineage.py")
        and _module_uses_sibling(getattr(value, "CONTRACTS", None), SCRIPT_DIR / "rir_contracts.py")
        and _is_controller_contracts_contract(getattr(value, "CONTRACTS", None))
        and _module_uses_sibling(lineage_storage, SCRIPT_DIR / "rir_storage.py")
        and _is_controller_storage_contract(lineage_storage)
        and _module_uses_sibling(lineage_compact_state, SCRIPT_DIR / "compact_state.py")
        and _module_uses_sibling(lineage_renderer, SCRIPT_DIR / "impact_renderer.py")
        and _module_uses_sibling(lineage_report_store, SCRIPT_DIR / "report_store.py")
        and getattr(lineage_storage, "report_store", None) is lineage_report_store
        and getattr(lineage_report_store, "compact_state", None) is lineage_compact_state
        and getattr(lineage_report_store, "impact_renderer", None) is lineage_renderer
        and getattr(value, "BeginRequest", None)
        is getattr(getattr(value, "CONTRACTS", None), "BeginRequest", None)
        and _callables(
            value,
            ("current_lineage", "legacy_key_map", "allocate_ids", "map_keys", "build_state"),
        )
    )


def _load_registered_lineage(module_name: str, expected: Path) -> object:
    specification = importlib.util.spec_from_file_location(module_name, expected)
    if specification is None or specification.loader is None:
        raise ImportError("cannot load fixed lineage sibling")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError("cannot load fixed lineage sibling") from error
    if not _is_lineage_contract(module):
        sys.modules.pop(module_name, None)
        raise ImportError("lineage sibling contract is incomplete")
    return module


def _load_lineage() -> object:
    sibling = SCRIPT_DIR / "rir_lineage.py"
    expected = _regular_module_path(sibling)
    if expected is None or expected != sibling:
        raise ImportError("lineage sibling is unsafe")
    module_name = (
        "_rir_controller_lineage_" + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    )
    hashed_present = module_name in sys.modules
    hashed = sys.modules.get(module_name)
    canonical = sys.modules.get("rir_lineage")
    if canonical is not None and _is_lineage_contract(canonical):
        if not hashed_present:
            return canonical
        if not _module_uses_sibling(hashed, expected):
            raise ImportError("lineage sibling is unsafe")
        if not _is_lineage_contract(hashed):
            raise ImportError("lineage sibling contract is incomplete")
        return hashed
    if hashed_present:
        if not _module_uses_sibling(hashed, expected):
            raise ImportError("lineage sibling is unsafe")
        if not _is_lineage_contract(hashed):
            raise ImportError("lineage sibling contract is incomplete")
        if "rir_lineage" not in sys.modules:
            sys.modules["rir_lineage"] = cast(ModuleType, hashed)
        return hashed
    target_name = "rir_lineage" if canonical is None else module_name
    return _load_registered_lineage(target_name, expected)


LINEAGE = cast(Any, _load_lineage())
_current_lineage = LINEAGE.current_lineage
_legacy_key_map = LINEAGE.legacy_key_map


def _payload_sha256() -> str:
    candidate = SCRIPT_DIR.parent
    if not (candidate / ".codex-plugin" / "plugin.json").is_file():
        candidate = SCRIPT_DIR.parents[2]
    return PAYLOAD_IDENTITY.payload_sha256(candidate)


def _previous_delta_identity(value: object) -> tuple[object, ...]:
    return tuple(
        getattr(value, name, None)
        for name in (
            "status",
            "report_id",
            "revision",
            "markdown_sha256",
            "changed_paths",
            "changed_count",
            "requirement_sha256",
            "source_inventory_sha256",
            "display_text",
        )
    )


def _configured_delta_max_seconds(root: Path, settings: Mapping[str, object]) -> int:
    configured = settings.get("delta_max_seconds")
    if configured is None:
        configured = SETTINGS.resolve_delta_max_seconds(root)
    if type(configured) is not int or configured < 1:
        raise ValueError("delta_max_seconds must be a positive integer")
    return configured


def _trusted_delta_context(root: Path, request: ScanRequest, settings: Mapping[str, object]):
    changed_paths = tuple(request.changed_paths)
    hints_present = (
        request.previous_report_id is not None
        or request.previous_revision is not None
        or bool(changed_paths)
    )
    if not hints_present:
        return None
    if request.previous_report_id is None or request.previous_revision is None:
        raise ValueError("delta hints require previous_report_id and previous_revision")
    lookup_request = PreviousLookupRequest(
        root,
        request.change_request,
        request.evidence,
        request.previous_report_id,
    )
    trusted = lookup_previous(lookup_request)
    DELTA.validate_delta_hints(
        trusted,
        request.previous_report_id,
        request.previous_revision,
        changed_paths,
    )
    state, graph, prior_graph_status, prior_graph_receipt_id, prior_graph_sha256 = (
        DELTA.load_trusted_previous_artifacts(
            root,
            trusted,
            state_loader=cast(Any, STORAGE.COMPACT_STATE).load_state_bytes,
            receipt_loader=GRAPH.load_receipt_bytes,
            canonical_receipt_bytes=GRAPH.canonical_receipt_bytes,
            max_receipt_bytes=GRAPH.MAX_RECEIPT_BYTES,
            expected_payload_sha256=_payload_sha256(),
            expected_repository_evidence_sha256=(
                FINALIZE.REPORT_CONTEXT.canonical_repository_evidence_sha256(request.evidence)
            ),
        )
    )
    verified = lookup_previous(lookup_request)
    if _previous_delta_identity(verified) != _previous_delta_identity(trusted):
        raise ValueError("trusted stale previous identity changed during delta binding")
    configured = _configured_delta_max_seconds(root, settings)
    return DELTA.bind_delta_context(
        root,
        verified,
        state,
        graph,
        previous_report_id=request.previous_report_id,
        previous_revision=request.previous_revision,
        changed_paths=changed_paths,
        configured_max_seconds=configured,
        prior_graph_status=prior_graph_status,
        previous_graph_receipt_id=prior_graph_receipt_id,
        previous_graph_sha256=prior_graph_sha256,
    )


_DELTA_WORKER_MAX_INPUT = 512 * 1024
_DELTA_WORKER_MAX_OUTPUT = 4 * 1024 * 1024
_DELTA_WORKER_MAX_ERROR = 64 * 1024


def _configure_delta_worker_runtime(token: str) -> None:
    if re.fullmatch(r"[0-9a-f]{32}", token) is None:
        raise ValueError("delta worker token is invalid")
    cast(Any, FAST_SCAN_STORE)._configure_delta_worker(token)
    cast(Any, GRAPH_COORDINATOR)._configure_delta_worker(token)
    cast(Any, PREVIOUS)._configure_delta_worker(True)
    cast(Any, FINALIZE.REPORT_CONTEXT)._configure_delta_worker(True)


def _worker_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _worker_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_worker_json_value(item) for item in value]
    return value


def _scan_result_mapping(result: object) -> dict[str, object]:
    typed = cast(Any, result)
    return {
        "status": typed.status,
        "scan_id": typed.scan_id,
        "receipt_id": typed.receipt_id,
        "receipt_sha256": typed.receipt_sha256,
        "display_text": typed.display_text,
        "risk_level": typed.risk_level,
        "paths": _worker_json_value(typed.paths),
        "frontier": _worker_json_value(typed.frontier),
        "candidates": _worker_json_value(typed.candidates),
        "elapsed_ms": typed.elapsed_ms,
        "cache_status": typed.cache_status,
        "can_promote": typed.can_promote,
        "previous_report_id": getattr(typed, "previous_report_id", None),
        "previous_revision": getattr(typed, "previous_revision", None),
        "changed_paths": list(getattr(typed, "changed_paths", ())),
        "changed_count": getattr(typed, "changed_count", None),
        "previous_display_text": getattr(typed, "previous_display_text", None),
    }


_DELTA_WORKER_RESULT_KEYS = frozenset(
    {
        "status",
        "scan_id",
        "receipt_id",
        "receipt_sha256",
        "display_text",
        "risk_level",
        "paths",
        "frontier",
        "candidates",
        "elapsed_ms",
        "cache_status",
        "can_promote",
        "previous_report_id",
        "previous_revision",
        "changed_paths",
        "changed_count",
        "previous_display_text",
    }
)


def _scan_result_from_mapping(value: object, elapsed_ms: int):
    if not isinstance(value, Mapping) or set(value) != _DELTA_WORKER_RESULT_KEYS:
        raise ValueError("delta worker result shape is invalid")
    status = value["status"]
    can_promote = value["can_promote"]
    if (
        status not in {"complete", "partial", "needs_input"}
        or not isinstance(can_promote, bool)
        or (status == "partial" and can_promote)
        or not isinstance(value["scan_id"], str)
        or DRAFT_ID_PATTERN.fullmatch(value["scan_id"]) is None
        or not isinstance(value["receipt_id"], str)
        or DRAFT_ID_PATTERN.fullmatch(value["receipt_id"]) is None
        or not isinstance(value["receipt_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", value["receipt_sha256"]) is None
        or not isinstance(value["display_text"], str)
        or not value["display_text"].strip()
        or not isinstance(value["risk_level"], str)
        or not isinstance(value["cache_status"], str)
        or any(not isinstance(value[name], list) for name in ("paths", "frontier", "candidates"))
        or any(
            not isinstance(row, Mapping)
            for name in ("paths", "frontier", "candidates")
            for row in cast(list[object], value[name])
        )
        or not isinstance(value["changed_paths"], list)
        or any(not isinstance(path, str) for path in value["changed_paths"])
    ):
        raise ValueError("delta worker result contract is invalid")
    previous_report_id = value["previous_report_id"]
    previous_revision = value["previous_revision"]
    previous_display = value["previous_display_text"]
    if previous_report_id is not None and (
        not isinstance(previous_report_id, str)
        or re.fullmatch(r"RPT-\d{3}", previous_report_id) is None
        or type(previous_revision) is not int
        or not isinstance(previous_display, str)
        or not previous_display.strip()
    ):
        raise ValueError("delta worker previous result identity is invalid")
    return FAST_SCAN.FastScanResult(
        status,
        value["scan_id"],
        value["receipt_id"],
        value["receipt_sha256"],
        value["display_text"],
        value["risk_level"],
        tuple(value["paths"]),
        tuple(value["frontier"]),
        tuple(value["candidates"]),
        elapsed_ms,
        value["cache_status"],
        can_promote,
        previous_report_id,
        previous_revision,
        tuple(value["changed_paths"]),
        value["changed_count"],
        previous_display,
    )


def _terminate_delta_worker(process: subprocess.Popen[bytes]) -> None:
    if hasattr(os, "killpg"):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            pass
    elif process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.wait(timeout=0.025)
    except (OSError, subprocess.TimeoutExpired):
        pass
    if hasattr(os, "killpg"):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
    elif process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=0.05)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _cleanup_delta_worker_temps(root: Path, token: str) -> None:
    directories = (
        (".requirements-impact-refiner", "scans"),
        (".requirements-impact-refiner", "graph"),
        (".requirements-impact-refiner", "cache", "graph", "v1"),
    )
    marker = f".{token}."
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    for parts in directories:
        opened = []
        try:
            parent = os.open(root, directory_flags)
            opened.append(parent)
            for part in parts:
                parent = os.open(part, directory_flags, dir_fd=parent)
                opened.append(parent)
        except OSError:
            for descriptor in reversed(opened):
                os.close(descriptor)
            continue
        try:
            with os.scandir(parent) as entries:
                for index, entry in enumerate(entries):
                    if index >= 4096:
                        break
                    if marker not in entry.name or not entry.name.endswith(".tmp"):
                        continue
                    if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                        continue
                    try:
                        os.unlink(entry.name, dir_fd=parent)
                    except OSError:
                        continue
        except OSError:
            pass
        finally:
            for descriptor in reversed(opened):
                try:
                    os.close(descriptor)
                except OSError:
                    continue


def _delta_worker_frame(payload: bytes) -> Mapping[str, object]:
    if len(payload) < 9 or len(payload) > _DELTA_WORKER_MAX_OUTPUT:
        raise ValueError("delta worker frame size is invalid")
    header = payload[:9]
    if re.fullmatch(rb"[0-9a-f]{8}\n", header) is None:
        raise ValueError("delta worker frame header is invalid")
    declared = int(header[:8], 16)
    body = payload[9:]
    if declared > _DELTA_WORKER_MAX_OUTPUT - 9 or declared != len(body):
        raise ValueError("delta worker frame length is invalid")
    try:
        value = json.loads(body.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("delta worker frame payload is invalid") from error
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    if not isinstance(value, dict) or set(value) != {"result"} or canonical != body:
        raise ValueError("delta worker frame is not one canonical result")
    result = value["result"]
    if not isinstance(result, Mapping):
        raise ValueError("delta worker frame result is invalid")
    return result


def _read_delta_worker_output(
    process: subprocess.Popen[bytes], work_deadline: float
) -> tuple[bytes, bytes, bool, bool]:
    if process.stdout is None or process.stderr is None:
        raise ValueError("delta worker pipes are unavailable")
    selector = selectors.DefaultSelector()
    streams = {
        process.stdout: (bytearray(), _DELTA_WORKER_MAX_OUTPUT),
        process.stderr: (bytearray(), _DELTA_WORKER_MAX_ERROR),
    }
    for stream in streams:
        selector.register(stream, selectors.EVENT_READ)
    timed_out = False
    overflow = False
    try:
        while selector.get_map():
            now = time.monotonic()
            if now >= work_deadline:
                timed_out = True
                break
            events = selector.select(max(0.0, min(work_deadline - now, 0.025)))
            for key, _mask in events:
                selected_stream = cast(Any, key.fileobj)
                if not hasattr(selected_stream, "fileno"):
                    raise TypeError("delta worker stream must provide fileno()")
                chunk = os.read(selected_stream.fileno(), 65_536)
                if not chunk:
                    selector.unregister(selected_stream)
                    continue
                buffer, maximum = streams[selected_stream]
                if len(buffer) + len(chunk) > maximum:
                    overflow = True
                    break
                buffer.extend(chunk)
            if overflow:
                break
        if timed_out or overflow:
            _terminate_delta_worker(process)
        else:
            try:
                process.wait(timeout=max(0.001, work_deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_delta_worker(process)
        return (
            bytes(streams[process.stdout][0]),
            bytes(streams[process.stderr][0]),
            timed_out,
            overflow,
        )
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()


def _run_delta_worker(
    worker: Path,
    root: Path,
    input_path: Path,
    input_sha256: str,
    token: str,
    environment: Mapping[str, str],
    work_deadline: float,
) -> Mapping[str, object] | None:
    try:
        process = subprocess.Popen(
            (
                sys.executable,
                str(worker),
                "--input",
                str(input_path),
                "--sha256",
                input_sha256,
                "--token",
                token,
                "--parent-pid",
                str(os.getpid()),
            ),
            cwd=str(root),
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            close_fds=True,
        )
    except OSError:
        return None
    try:
        stdout, stderr, timed_out, overflow = _read_delta_worker_output(process, work_deadline)
        if process.poll() is not None and hasattr(os, "killpg"):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
        if timed_out or overflow or stderr or process.returncode != 0:
            return None
        try:
            return _delta_worker_frame(stdout)
        except ValueError:
            return None
    finally:
        if process.poll() is None:
            _terminate_delta_worker(process)


def _execute_delta_worker(
    request: ScanRequest,
    max_seconds: float,
    operation_started: float,
    *,
    worker_path: Path | None = None,
    worker_environment: Mapping[str, str] | None = None,
):
    if (
        not isinstance(max_seconds, (int, float))
        or isinstance(max_seconds, bool)
        or max_seconds <= 0
        or max_seconds > 3
    ):
        raise ValueError("delta worker deadline must be between zero and three seconds")
    root = _root(request.repo_root)
    selected_worker = (
        SCRIPT_DIR / "rir_delta_worker.py" if worker_path is None else Path(worker_path)
    )
    if worker_path is None and _regular_module_path(selected_worker) != selected_worker:
        raise ImportError("delta worker sibling is unsafe")
    if not selected_worker.is_file() or selected_worker.is_symlink():
        raise ValueError("delta worker path is unsafe")
    cleanup_reserve = min(0.075, max_seconds / 4)
    work_deadline = operation_started + max_seconds - cleanup_reserve
    fallback_mapping = _prepare_delta_fallback_in_process(request, operation_started)
    fallback_value = dict(fallback_mapping)
    fallback_value["status"] = "partial"
    fallback_value["can_promote"] = False
    elapsed_ms = max(0, round((time.monotonic() - operation_started) * 1000))
    trusted_fallback = _scan_result_from_mapping(fallback_value, elapsed_ms)
    if (
        trusted_fallback.previous_report_id != request.previous_report_id
        or trusted_fallback.previous_revision != request.previous_revision
        or trusted_fallback.changed_paths != tuple(request.changed_paths)
        or trusted_fallback.previous_display_text is None
    ):
        raise ValueError("delta parent fallback identity is invalid")
    if time.monotonic() >= work_deadline:
        elapsed_ms = max(0, round((time.monotonic() - operation_started) * 1000))
        return _scan_result_from_mapping(_scan_result_mapping(trusted_fallback), elapsed_ms)
    request_value = {
        "schema_version": 1,
        "repo_root": str(root),
        "change_request": request.change_request,
        "evidence": list(request.evidence),
        "audience_override": request.audience_override,
        "previous_report_id": request.previous_report_id,
        "previous_revision": request.previous_revision,
        "changed_paths": list(request.changed_paths),
        "operation_started": operation_started,
        "max_seconds": max_seconds,
        "worker_token": None,
        "parent_pid": os.getpid(),
    }
    token = secrets.token_hex(16)
    request_value["worker_token"] = token
    request_payload = canonical_bytes(request_value)
    if len(request_payload) > _DELTA_WORKER_MAX_INPUT:
        raise ValueError("delta worker input exceeds its byte limit")
    worker_temp = Path(tempfile.mkdtemp(prefix="rir-delta-worker-"))
    worker_temp.chmod(0o700)
    input_path = worker_temp / "input.json"
    descriptor = -1
    try:
        descriptor = os.open(input_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(request_payload):
            offset += os.write(descriptor, request_payload[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        environment = {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.environ.get("PATH", ""),
            "TMPDIR": str(worker_temp),
            "TMP": str(worker_temp),
            "TEMP": str(worker_temp),
        }
        system_root = os.environ.get("SYSTEMROOT")
        if system_root:
            environment["SYSTEMROOT"] = system_root
        if worker_environment:
            for name, value in worker_environment.items():
                if not name.startswith("RIR_DELTA_TEST_") or not isinstance(value, str):
                    raise ValueError("delta worker test environment is invalid")
                environment[name] = value
        if time.monotonic() >= work_deadline:
            elapsed_ms = max(0, round((time.monotonic() - operation_started) * 1000))
            return _scan_result_from_mapping(_scan_result_mapping(trusted_fallback), elapsed_ms)
        request_sha256 = hashlib.sha256(request_payload).hexdigest()
        result_mapping = _run_delta_worker(
            selected_worker,
            root,
            input_path,
            request_sha256,
            token,
            environment,
            work_deadline,
        )
        elapsed_ms = max(0, round((time.monotonic() - operation_started) * 1000))
        if result_mapping is None:
            return _scan_result_from_mapping(_scan_result_mapping(trusted_fallback), elapsed_ms)
        try:
            result = _scan_result_from_mapping(result_mapping, elapsed_ms)
        except ValueError:
            return _scan_result_from_mapping(_scan_result_mapping(trusted_fallback), elapsed_ms)
        if (
            result.previous_report_id != trusted_fallback.previous_report_id
            or result.previous_revision != trusted_fallback.previous_revision
            or result.changed_paths != trusted_fallback.changed_paths
            or result.previous_display_text != trusted_fallback.previous_display_text
        ):
            return _scan_result_from_mapping(_scan_result_mapping(trusted_fallback), elapsed_ms)
        return result
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            input_path.unlink()
        except OSError:
            pass
        _cleanup_delta_worker_temps(root, token)
        shutil.rmtree(worker_temp, ignore_errors=True)


def _scan_impact_in_process(
    request: ScanRequest,
    *,
    operation_started: float | None = None,
):
    root = _root(request.repo_root)
    if not isinstance(request.evidence, tuple):
        raise ValueError("scan evidence must be a tuple")
    settings = SETTINGS.resolve(root, request.audience_override, None)
    delta_context = _trusted_delta_context(root, request, settings)
    return FAST_SCAN.execute_fast_scan(
        FAST_SCAN.FastScanRequest(
            root,
            request.change_request,
            request.evidence,
            settings["audience"],
            previous_report_id=request.previous_report_id,
            previous_revision=request.previous_revision,
            changed_paths=tuple(request.changed_paths),
            delta_max_seconds=(
                _configured_delta_max_seconds(root, settings) if delta_context is not None else 3
            ),
        ),
        settings["impact_graph"],
        _payload_sha256(),
        delta_context=delta_context,
        operation_started=operation_started,
    )


def _prepare_delta_fallback_in_process(
    request: ScanRequest, operation_started: float
) -> Mapping[str, object]:
    root = _root(request.repo_root)
    if not isinstance(request.evidence, tuple):
        raise ValueError("scan evidence must be a tuple")
    settings = SETTINGS.resolve(root, request.audience_override, None)
    delta_context = _trusted_delta_context(root, request, settings)
    if delta_context is None:
        raise ValueError("delta fallback requires trusted stale context")
    elapsed_ms = max(0, round((time.monotonic() - operation_started) * 1000))
    return DELTA.delta_timeout_fallback(delta_context, elapsed_ms)


def scan_impact(request: ScanRequest) -> ScanResult:
    operation_started = time.monotonic()
    root = _root(request.repo_root)
    if not isinstance(request.evidence, tuple):
        raise ValueError("scan evidence must be a tuple")
    delta_requested = (
        request.previous_report_id is not None
        or request.previous_revision is not None
        or bool(request.changed_paths)
    )
    if delta_requested:
        settings = SETTINGS.resolve(root, request.audience_override, None)
        max_seconds = min(_configured_delta_max_seconds(root, settings), 3)
        return _execute_delta_worker(request, max_seconds, operation_started)
    return _scan_impact_in_process(request)


def _promoted_scan(root, request, settings):
    if request.scan_id is None:
        return None
    if DRAFT_ID_PATTERN.fullmatch(request.scan_id) is None:
        raise ValueError("invalid Fast Scan ID")
    payload = FAST_SCAN_STORE.load_scan_receipt_bytes(root, request.scan_id)
    value = json.loads(payload)
    errors = FAST_SCAN.validate_fast_scan_receipt(value)
    if errors or FAST_SCAN.canonical_fast_scan_bytes(value) != payload:
        raise ValueError("Fast Scan receipt is invalid")
    delta_value = value.get("delta_context")
    delta_context = None
    if isinstance(delta_value, Mapping):
        report_id = delta_value.get("previous_report_id")
        revision = delta_value.get("previous_revision")
        changed_paths = delta_value.get("changed_paths")
        if (
            not isinstance(report_id, str)
            or type(revision) is not int
            or not isinstance(changed_paths, list)
        ):
            raise ValueError("Fast Scan delta context is invalid")
        scan_request = ScanRequest(
            root,
            request.request,
            request.repository_evidence,
            settings["audience"],
            report_id,
            revision,
            tuple(changed_paths),
        )
        delta_context = _trusted_delta_context(root, scan_request, settings)
        fast_request = FAST_SCAN.FastScanRequest(
            root,
            request.request,
            request.repository_evidence,
            settings["audience"],
            previous_report_id=report_id,
            previous_revision=revision,
            changed_paths=tuple(changed_paths),
            delta_max_seconds=_configured_delta_max_seconds(root, settings),
        )
    else:
        fast_request = FAST_SCAN.FastScanRequest(
            root,
            request.request,
            request.repository_evidence,
            settings["audience"],
        )
    prepared = FAST_SCAN.prepare_fast_scan_identity(
        fast_request,
        settings["impact_graph"],
        _payload_sha256(),
        delta_context,
    )
    if prepared.scan_id != request.scan_id:
        raise ValueError(
            "Fast Scan request identity does not match: the change request "
            "text, repository evidence rows, audience, graph settings, and "
            "repository contents must all equal the original rir_scan call"
        )
    if value["status"] != "complete" or value["can_promote"] is not True:
        raise ValueError("Fast Scan receipt is not promotable")
    if (
        value["request_sha256"] != prepared.request_sha256
        or value["repo_root_sha256"] != prepared.repo_root_sha256
        or value["payload_sha256"] != _payload_sha256()
        or value["settings"] != prepared.settings.to_mapping()
        or value["source_inventory"] != dict(prepared.inventory_mapping)
        or value["seeds"] != [row.to_mapping() for row in prepared.seeds]
        or value.get("delta_context")
        != (None if prepared.delta_context is None else dict(prepared.delta_context))
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
    normalized_request = FINALIZE.REPORT_CONTEXT.canonical_requirement_text(request.request)
    _bounded(
        {"request": normalized_request, "repository_evidence": request.repository_evidence},
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
    payload = FAST_SCAN_STORE.load_scan_receipt_bytes(root, binding["scan_id"])
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


_ids = LINEAGE.allocate_ids
_map_keys = LINEAGE.map_keys
_build_state = LINEAGE.build_state


def _is_finalize_contract(value: object) -> bool:
    finalize_lineage = getattr(value, "LINEAGE", None)
    finalize_storage = getattr(value, "STORAGE", None)
    finalize_report_store = getattr(value, "REPORT_STORE", None)
    finalize_graph_delivery = getattr(value, "GRAPH_DELIVERY", None)
    finalize_context = getattr(value, "REPORT_CONTEXT", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "rir_finalize.py")
        and _module_uses_sibling(finalize_lineage, SCRIPT_DIR / "rir_lineage.py")
        and _is_lineage_contract(finalize_lineage)
        and _module_uses_sibling(getattr(value, "CONTRACTS", None), SCRIPT_DIR / "rir_contracts.py")
        and _is_controller_contracts_contract(getattr(value, "CONTRACTS", None))
        and _module_uses_sibling(finalize_storage, SCRIPT_DIR / "rir_storage.py")
        and _is_controller_storage_contract(finalize_storage)
        and _module_uses_sibling(finalize_report_store, SCRIPT_DIR / "report_store.py")
        and getattr(finalize_storage, "report_store", None) is finalize_report_store
        and _module_uses_sibling(finalize_graph_delivery, SCRIPT_DIR / "rir_graph_delivery.py")
        and _is_graph_delivery_contract(finalize_graph_delivery)
        and _module_uses_sibling(finalize_context, SCRIPT_DIR / "rir_report_context.py")
        and callable(getattr(finalize_context, "canonical_requirement_text", None))
        and callable(getattr(finalize_context, "load_report_context", None))
        and callable(getattr(finalize_context, "publish_report_context", None))
        and callable(getattr(value, "finalize_refinement", None))
        and callable(getattr(value, "default_runtime", None))
    )


def _load_registered_finalize(module_name: str, expected: Path) -> object:
    specification = importlib.util.spec_from_file_location(module_name, expected)
    if specification is None or specification.loader is None:
        raise ImportError("cannot load fixed finalize sibling")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError("cannot load fixed finalize sibling") from error
    if not _is_finalize_contract(module):
        sys.modules.pop(module_name, None)
        raise ImportError("finalize sibling contract is incomplete")
    try:
        runtime = module.default_runtime()
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    if not isinstance(runtime, Mapping):
        sys.modules.pop(module_name, None)
        raise ImportError("finalize default runtime contract is incomplete")
    return module


def _load_finalize() -> object:
    sibling = SCRIPT_DIR / "rir_finalize.py"
    expected = _regular_module_path(sibling)
    if expected is None or expected != sibling:
        raise ImportError("finalize sibling is unsafe")
    module_name = (
        "_rir_controller_finalize_" + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    )
    hashed_present = module_name in sys.modules
    hashed = sys.modules.get(module_name)
    canonical = sys.modules.get("rir_finalize")
    if canonical is not None and _is_finalize_contract(canonical):
        if not hashed_present:
            return canonical
        if not _module_uses_sibling(hashed, expected):
            raise ImportError("finalize sibling is unsafe")
        if not _is_finalize_contract(hashed):
            raise ImportError("finalize sibling contract is incomplete")
        return hashed
    if hashed_present:
        if not _module_uses_sibling(hashed, expected):
            raise ImportError("finalize sibling is unsafe")
        if not _is_finalize_contract(hashed):
            raise ImportError("finalize sibling contract is incomplete")
        if "rir_finalize" not in sys.modules:
            sys.modules["rir_finalize"] = cast(ModuleType, hashed)
        return hashed
    target_name = "rir_finalize" if canonical is None else module_name
    return _load_registered_finalize(target_name, expected)


FINALIZE = cast(Any, _load_finalize())

compact_state = FINALIZE.COMPACT_STATE
impact_renderer = FINALIZE.IMPACT_RENDERER
report_store = FINALIZE.REPORT_STORE


def _is_previous_renderer_shape(value: object) -> bool:
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "rir_previous_renderer.py")
        and _module_uses_sibling(
            getattr(value, "COMPACT_STATE", None), SCRIPT_DIR / "compact_state.py"
        )
        and _module_uses_sibling(
            getattr(value, "IMPACT_RENDERER", None), SCRIPT_DIR / "impact_renderer.py"
        )
        and callable(getattr(value, "render_previous", None))
    )


def _is_previous_renderer_contract(value: object) -> bool:
    return (
        _is_previous_renderer_shape(value)
        and getattr(value, "COMPACT_STATE", None) is compact_state
        and getattr(value, "IMPACT_RENDERER", None) is impact_renderer
    )


PREVIOUS_RENDERER = _load_controller_sibling(
    "rir_previous_renderer.py",
    "rir_previous_renderer",
    "_rir_controller_previous_renderer_",
    _is_previous_renderer_contract,
    "previous renderer",
    aliases={
        "compact_state": cast(ModuleType, compact_state),
        "impact_report": cast(ModuleType, impact_renderer.impact_report),
        "impact_renderer": cast(ModuleType, impact_renderer),
    },
    rewire_validator=_is_previous_renderer_shape,
)


def _is_previous_shape(value: object) -> bool:
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "rir_previous.py")
        and _module_uses_sibling(
            getattr(value, "REPORT_CONTEXT", None), SCRIPT_DIR / "rir_report_context.py"
        )
        and _module_uses_sibling(
            getattr(value, "PAYLOAD_IDENTITY", None), SCRIPT_DIR / "payload_identity.py"
        )
        and _module_uses_sibling(
            getattr(value, "RENDERER", None), SCRIPT_DIR / "rir_previous_renderer.py"
        )
        and _classes(
            value,
            ("PreviousLookupRequest", "PreviousReportCandidate", "PreviousReportResult"),
        )
        and callable(getattr(value, "lookup_previous", None))
    )


def _is_previous_contract(value: object) -> bool:
    return (
        _is_previous_shape(value)
        and getattr(value, "REPORT_CONTEXT", None) is FINALIZE.REPORT_CONTEXT
        and getattr(value, "PAYLOAD_IDENTITY", None) is PAYLOAD_IDENTITY
        and getattr(value, "RENDERER", None) is PREVIOUS_RENDERER
    )


PREVIOUS = cast(
    Any,
    _load_controller_sibling(
        "rir_previous.py",
        "rir_previous",
        "_rir_controller_previous_",
        _is_previous_contract,
        "previous lookup",
        aliases={
            "rir_report_context": cast(ModuleType, FINALIZE.REPORT_CONTEXT),
            "payload_identity": cast(ModuleType, PAYLOAD_IDENTITY),
            "rir_previous_renderer": cast(ModuleType, PREVIOUS_RENDERER),
        },
        rewire_validator=_is_previous_shape,
    ),
)
if not TYPE_CHECKING:
    PreviousLookupRequest = PREVIOUS.PreviousLookupRequest
    PreviousReportCandidate = PREVIOUS.PreviousReportCandidate
    PreviousReportResult = PREVIOUS.PreviousReportResult


def lookup_previous(request: PreviousLookupRequest) -> PreviousReportResult:
    return PREVIOUS.lookup_previous(request)


_FACADE_BUILD_STATE = _build_state
_FACADE_LOAD_GRAPH_CONTEXT = _load_graph_context
_FACADE_VALIDATE_ANALYSIS = _validate_analysis
_FACADE_VALIDATE_GRAPH_COVERAGE = _validate_graph_coverage
_FACADE_CONSUME = _consume


def _overlay_finalize_hook(
    runtime: dict[str, object], name: str, current: object, original: object
) -> None:
    if current is original:
        return
    if not callable(current):
        raise TypeError(f"finalize facade hook is invalid: {name}")
    runtime[name] = current


def _validate_finalize_hooks() -> None:
    if (
        _FACADE_BUILD_STATE is not LINEAGE.build_state
        or _FACADE_VALIDATE_ANALYSIS is not CONTRACTS.validate_analysis
        or _FACADE_CONSUME is not STORAGE.consume_draft
        or not _module_uses_sibling(STORAGE, SCRIPT_DIR / "rir_storage.py")
        or getattr(_FACADE_LOAD_GRAPH_CONTEXT, "__module__", None) != __name__
        or getattr(_FACADE_VALIDATE_GRAPH_COVERAGE, "__module__", None) != __name__
    ):
        raise ImportError("finalize facade hook contract is invalid")


def _finalize_runtime() -> dict[str, object]:
    _validate_finalize_hooks()
    runtime = dict(FINALIZE.default_runtime())
    _overlay_finalize_hook(runtime, "build_state", _build_state, _FACADE_BUILD_STATE)
    _overlay_finalize_hook(
        runtime,
        "load_graph_context",
        _load_graph_context,
        _FACADE_LOAD_GRAPH_CONTEXT,
    )
    _overlay_finalize_hook(
        runtime,
        "validate_analysis",
        _validate_analysis,
        _FACADE_VALIDATE_ANALYSIS,
    )
    _overlay_finalize_hook(
        runtime,
        "validate_graph_coverage",
        _validate_graph_coverage,
        _FACADE_VALIDATE_GRAPH_COVERAGE,
    )
    _overlay_finalize_hook(runtime, "consume_draft", _consume, _FACADE_CONSUME)
    if (
        not _module_uses_sibling(CONTRACTS, SCRIPT_DIR / "rir_contracts.py")
        or FinalizeResult is not CONTRACTS.FinalizeResult
    ):
        raise ImportError("finalize facade result contract is invalid")
    runtime["result_type"] = FinalizeResult
    return runtime


def finalize_refinement(request: FinalizeRequest) -> FinalizeResult:
    return FINALIZE.finalize_refinement(request, _runtime=_finalize_runtime())
