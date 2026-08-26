#!/usr/bin/env python3
"""Final refinement validation, publication, verification, and consumption."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import TYPE_CHECKING, Any, Callable, Protocol, cast

if TYPE_CHECKING:
    from rir_contracts import FinalizeRequest, FinalizeResult
    from typing_extensions import TypeGuard


class _ContractsContract(Protocol):
    MAX_FINALIZE_BYTES: int
    BeginRequest: type
    FinalizeRequest: type
    FinalizeResult: type

    def bounded_bytes(self, value: object, maximum: int, label: str) -> bytes: ...

    def canonical_bytes(self, value: object) -> bytes: ...

    def validate_analysis(self, analysis: Mapping[str, object]) -> None: ...


class _StorageContract(Protocol):
    DRAFT_ID_PATTERN: re.Pattern[str]
    report_store: _ReportStoreContract

    def root_path(self, path: Path) -> Path: ...

    def load_private_draft(self, repo_root: Path, draft_id: str) -> dict[str, object]: ...

    def draft_path(self, root: Path, draft_id: str) -> Path: ...

    def load_controller_completion_metadata(self, current): ...

    def load_legacy_controller_completion_metadata(self, current): ...

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

    def migrate_legacy_controller_metadata(self, *args, **kwargs) -> None: ...

    def consume_draft(self, path: Path, draft: dict[str, object], published, key_map) -> None: ...


class _LineageContract(Protocol):
    BeginRequest: type
    CONTRACTS: _ContractsContract
    STORAGE: _StorageContract
    COMPACT_STATE: _CompactStateContract
    IMPACT_RENDERER: _ImpactRendererContract
    REPORT_STORE: _ReportStoreContract

    def build_state(self, draft, analysis, graph_context=None): ...


class _GraphContract(Protocol):
    GraphSettings: type
    ProviderStatus: type
    GraphNode: type
    GraphEdge: type
    GraphPath: type
    FrontierEntry: type
    GraphReceipt: type
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

    def canonical_receipt_bytes(self, value: object) -> bytes: ...

    def load_receipt_bytes(self, payload: bytes): ...


class _CompactStateContract(Protocol):
    def load_state_bytes(self, raw: bytes) -> tuple[dict[str, object] | None, list[str]]: ...


class _ImpactRendererContract(Protocol):
    compact_state: _CompactStateContract
    impact_report: object

    def render_compact(self, state: Mapping[str, object]) -> str: ...

    def render_markdown(self, state: Mapping[str, object]) -> str: ...


class _ReportStoreContract(Protocol):
    compact_state: _CompactStateContract
    impact_renderer: _ImpactRendererContract
    ReportStoreError: type[Exception]

    def load_current(self, repo_root: Path, report_id: str): ...

    def publish_revision(
        self, repo_root: Path, state_bytes: bytes, *, resume_partial: bool = False
    ): ...

    def report_directory(
        self, repo_root: Path, report_id: str, *, create: bool = False
    ) -> Path: ...


class _ReportContextContract(Protocol):
    ReportContext: type
    MAX_CONTEXT_BYTES: int
    MAX_EVIDENCE_BYTES: int
    MAX_REQUIREMENT_INPUT_BYTES: int
    MAX_REQUIREMENT_BYTES: int

    def canonical_requirement_text(self, request: str) -> str: ...

    def canonical_requirement_sha256(self, request: str) -> str: ...

    def canonical_repository_evidence_sha256(self, evidence: Sequence[str]) -> str: ...

    def repo_root_sha256(self, root: Path) -> str: ...

    def created_at_utc(self) -> str: ...

    def probe_git_baseline(self, root: Path): ...

    def probe_source_inventory_git(self, root: Path, source_digests: Mapping[str, str]): ...

    def publish_report_context(self, root: Path, context): ...

    def load_report_context(self, root: Path, report_id: str, revision: int): ...

    def load_legacy_report_context(self, root: Path, report_id: str, revision: int): ...


class _BuiltinContract(Protocol):
    GRAPH: _GraphContract
    IGNORED_DIRECTORIES: frozenset[str]
    GraphNode: type
    GraphEdge: type
    GraphPath: type
    FrontierEntry: type
    ScanSeed: type
    ScanLimits: type
    BuiltInScanResult: type
    DEFAULT_MAX_FILE_BYTES: int

    def _read_regular_file(self, *args, **kwargs): ...

    def _safe_graph_text(self, *args, **kwargs): ...

    def _walk_files(self, *args, **kwargs): ...

    def scan_repository(self, *args, **kwargs): ...


class _CacheContract(Protocol):
    GRAPH: _GraphContract
    CacheResult: type
    _IDENTITY_FIELDS: frozenset[str]

    def _cache_directory(self, *args, **kwargs): ...

    def _read_artifact(self, *args, **kwargs): ...

    def _source_digests(self, *args, **kwargs): ...

    def _canonical_json(self, *args, **kwargs): ...

    def _normalize_receipt(self, *args, **kwargs): ...

    def load(self, *args, **kwargs): ...

    def publish(self, *args, **kwargs): ...


class _ProvidersContract(Protocol):
    Deadline: type
    ProviderProbe: type
    ProviderQuery: type
    ProviderResult: type
    ProviderSpec: type


class _CoordinatorContract(Protocol):
    GRAPH: _GraphContract
    BUILTIN: _BuiltinContract
    CACHE: _CacheContract
    PROVIDERS: _ProvidersContract
    GraphSettings: type
    ProviderProbe: type
    ProviderQuery: type
    ProviderResult: type
    ProviderSpec: type
    Deadline: type
    ScanSeed: type
    ScanLimits: type
    SourceInventory: type

    def _settings(self, *args, **kwargs): ...

    def _request_sha256(self, *args, **kwargs): ...

    def _seed_key(self, *args, **kwargs): ...

    def _trace_identity(self, *args, **kwargs): ...

    def _collect_source_digests(self, *args, **kwargs): ...

    def discover_providers(self, *args, **kwargs): ...

    def run_provider(self, *args, **kwargs): ...

    def trace_impact(self, *args, **kwargs): ...


class _GraphDeliveryContract(Protocol):
    CONTRACTS: _ContractsContract
    STORAGE: _StorageContract
    GRAPH: _GraphContract
    GRAPH_COORDINATOR: _CoordinatorContract

    def load_graph_context(
        self,
        root: Path,
        draft: Mapping[str, object],
        selected_receipt_id: str | None,
        *,
        deadline=None,
        _runtime=None,
    ): ...

    def validate_graph_coverage(self, analysis: Mapping[str, object], context) -> None: ...

    def source_inventory_sha256(self, source_digests: Mapping[str, str]) -> str: ...

    def verify_receipt_sources(self, root: Path, receipt: Mapping[str, object]) -> None: ...


class _FastScanContract(Protocol):
    DerivedSeed: type
    FastScanRequest: type
    FastScanReceipt: type
    FastScanResult: type
    PreparedFastScan: type

    def prepare_fast_scan_identity(self, request, graph_settings, payload_sha256): ...

    def validate_fast_scan_receipt(self, value: object) -> tuple[str, ...]: ...

    def canonical_fast_scan_bytes(self, value: Mapping[str, object]) -> bytes: ...

    def derive_seeds(self, *args, **kwargs): ...

    def execute_fast_scan(self, *args, **kwargs): ...

    def explicit_path_candidates(
        self, change_request: str, evidence: Sequence[str]
    ) -> tuple[str, ...]: ...


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


def _callables(value: object, names: Sequence[str]) -> bool:
    return all(callable(getattr(value, name, None)) for name in names)


def _classes(value: object, names: Sequence[str]) -> bool:
    return all(isinstance(getattr(value, name, None), type) for name in names)


def _is_lineage_contract(value: object) -> TypeGuard[_LineageContract]:
    contracts = getattr(value, "CONTRACTS", None)
    storage = getattr(value, "STORAGE", None)
    compact_state = getattr(value, "COMPACT_STATE", None)
    renderer = getattr(value, "IMPACT_RENDERER", None)
    report_store = getattr(value, "REPORT_STORE", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "rir_lineage.py")
        and _module_uses_sibling(contracts, SCRIPT_DIR / "rir_contracts.py")
        and all(
            type(getattr(contracts, name, None)) is int and getattr(contracts, name) > 0
            for name in ("MAX_FINALIZE_BYTES", "MAX_STRING_BYTES")
        )
        and _classes(contracts, ("BeginRequest", "FinalizeRequest", "FinalizeResult"))
        and _callables(contracts, ("bounded_bytes", "canonical_bytes", "validate_analysis"))
        and getattr(value, "BeginRequest", None) is getattr(contracts, "BeginRequest", None)
        and _module_uses_sibling(storage, SCRIPT_DIR / "rir_storage.py")
        and isinstance(getattr(storage, "DRAFT_ID_PATTERN", None), re.Pattern)
        and _callables(
            storage,
            (
                "root_path",
                "load_private_draft",
                "draft_path",
                "load_controller_completion_metadata",
                "load_legacy_controller_completion_metadata",
                "report_lock",
                "write_controller_metadata",
                "migrate_legacy_controller_metadata",
                "consume_draft",
            ),
        )
        and _module_uses_sibling(compact_state, SCRIPT_DIR / "compact_state.py")
        and _module_uses_sibling(renderer, SCRIPT_DIR / "impact_renderer.py")
        and _module_uses_sibling(report_store, SCRIPT_DIR / "report_store.py")
        and _module_uses_sibling(
            getattr(renderer, "impact_report", None), SCRIPT_DIR / "impact_report.py"
        )
        and getattr(storage, "report_store", None) is report_store
        and getattr(report_store, "compact_state", None) is compact_state
        and getattr(report_store, "impact_renderer", None) is renderer
        and getattr(renderer, "compact_state", None) is compact_state
        and _callables(compact_state, ("load_state_bytes", "validate_state"))
        and _callables(renderer, ("render_compact", "render_markdown"))
        and isinstance(getattr(report_store, "ReportStoreError", None), type)
        and _callables(report_store, ("load_current", "publish_revision", "report_directory"))
        and _callables(
            value,
            ("current_lineage", "legacy_key_map", "allocate_ids", "map_keys", "build_state"),
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
        raise ImportError(f"cannot load fixed finalize {label} sibling")
    module = importlib.util.module_from_spec(specification)
    previous = {name: (name in sys.modules, sys.modules.get(name)) for name in (aliases or {})}
    sys.modules[module_name] = module
    try:
        if aliases:
            sys.modules.update(aliases)
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError(f"cannot load fixed finalize {label} sibling") from error
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
        raise ImportError(f"finalize {label} sibling contract is incomplete")
    return module


def _load_fixed_sibling(
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
        raise ImportError(f"finalize {label} sibling is unsafe")
    hashed_name = prefix + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    hashed_present = hashed_name in sys.modules
    hashed = sys.modules.get(hashed_name)

    def rewired() -> object:
        if aliases is None:
            raise ImportError(f"finalize {label} sibling contract is incomplete")
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
                raise ImportError(f"finalize {label} sibling is unsafe")
            if not validator(existing):
                raise ImportError(f"finalize {label} sibling contract is incomplete")
            return existing
        return _execute_registered(
            rewired_name,
            expected,
            validator,
            label,
            aliases=aliases,
        )

    if canonical_name not in sys.modules:
        if hashed_present:
            if not _module_uses_sibling(hashed, expected):
                raise ImportError(f"finalize {label} sibling is unsafe")
            if not validator(hashed):
                raise ImportError(f"finalize {label} sibling contract is incomplete")
            sys.modules[canonical_name] = cast(ModuleType, hashed)
            return hashed
        return _execute_registered(canonical_name, expected, validator, label, aliases=aliases)
    canonical = sys.modules.get(canonical_name)
    if _module_uses_sibling(canonical, expected):
        if validator(canonical) and not hashed_present:
            return canonical
        if hashed_present:
            if not _module_uses_sibling(hashed, expected):
                raise ImportError(f"finalize {label} sibling is unsafe")
            if validator(hashed):
                return hashed
            if rewire_validator is not None and rewire_validator(hashed):
                return rewired()
            raise ImportError(f"finalize {label} sibling contract is incomplete")
        if rewire_validator is not None and rewire_validator(canonical):
            return _execute_registered(hashed_name, expected, validator, label, aliases=aliases)
        raise ImportError(f"finalize {label} sibling contract is incomplete")
    if hashed_present:
        if not _module_uses_sibling(hashed, expected):
            raise ImportError(f"finalize {label} sibling is unsafe")
        if validator(hashed):
            return hashed
        if rewire_validator is not None and rewire_validator(hashed):
            return rewired()
        raise ImportError(f"finalize {label} sibling contract is incomplete")
    return _execute_registered(hashed_name, expected, validator, label, aliases=aliases)


LINEAGE = cast(
    _LineageContract,
    _load_fixed_sibling(
        "rir_lineage.py",
        "rir_lineage",
        "_rir_finalize_lineage_",
        _is_lineage_contract,
        "lineage",
    ),
)
CONTRACTS = LINEAGE.CONTRACTS
STORAGE = LINEAGE.STORAGE
COMPACT_STATE = cast(Any, LINEAGE.COMPACT_STATE)
IMPACT_RENDERER = cast(Any, LINEAGE.IMPACT_RENDERER)
REPORT_STORE = cast(Any, LINEAGE.REPORT_STORE)


def _is_report_context_contract(value: object) -> TypeGuard[_ReportContextContract]:
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "rir_report_context.py")
        and _classes(value, ("ReportContext",))
        and all(
            type(getattr(value, name, None)) is int and getattr(value, name) > 0
            for name in (
                "MAX_CONTEXT_BYTES",
                "MAX_EVIDENCE_BYTES",
                "MAX_REQUIREMENT_INPUT_BYTES",
                "MAX_REQUIREMENT_BYTES",
            )
        )
        and _callables(
            value,
            (
                "canonical_requirement_text",
                "canonical_requirement_sha256",
                "canonical_repository_evidence_sha256",
                "repo_root_sha256",
                "created_at_utc",
                "probe_git_baseline",
                "probe_source_inventory_git",
                "publish_report_context",
                "load_report_context",
                "load_legacy_report_context",
            ),
        )
    )


REPORT_CONTEXT = cast(
    _ReportContextContract,
    _load_fixed_sibling(
        "rir_report_context.py",
        "rir_report_context",
        "_rir_finalize_report_context_",
        _is_report_context_contract,
        "report context",
    ),
)


def _is_graph_contract(value: object) -> TypeGuard[_GraphContract]:
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "impact_graph.py")
        and _classes(
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
            type(getattr(value, name, None)) is int and getattr(value, name) > 0
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


def _is_builtin_contract(value: object, graph: object) -> TypeGuard[_BuiltinContract]:
    maximum = getattr(value, "DEFAULT_MAX_FILE_BYTES", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "graph_builtin.py")
        and getattr(value, "GRAPH", None) is graph
        and all(
            getattr(value, name, None) is getattr(graph, name, None)
            for name in ("GraphNode", "GraphEdge", "GraphPath", "FrontierEntry")
        )
        and isinstance(getattr(value, "IGNORED_DIRECTORIES", None), frozenset)
        and type(maximum) is int
        and maximum > 0
        and _classes(value, ("ScanSeed", "ScanLimits", "BuiltInScanResult"))
        and _callables(
            value,
            ("_read_regular_file", "_safe_graph_text", "_walk_files", "scan_repository"),
        )
    )


def _is_cache_contract(value: object, graph: object) -> TypeGuard[_CacheContract]:
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "graph_cache.py")
        and getattr(value, "GRAPH", None) is graph
        and _classes(value, ("CacheResult",))
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


def _is_providers_contract(value: object) -> TypeGuard[_ProvidersContract]:
    priority = getattr(value, "PROVIDER_PRIORITY", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "graph_providers.py")
        and isinstance(priority, tuple)
        and all(isinstance(item, str) for item in priority)
        and _classes(
            value,
            ("Deadline", "ProviderProbe", "ProviderQuery", "ProviderResult", "ProviderSpec"),
        )
        and _callables(value, ("discover_providers", "run_provider"))
    )


def _is_coordinator_contract(value: object, graph: object) -> TypeGuard[_CoordinatorContract]:
    builtin = getattr(value, "BUILTIN", None)
    cache = getattr(value, "CACHE", None)
    providers = getattr(value, "PROVIDERS", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "graph_coordinator.py")
        and getattr(value, "GRAPH", None) is graph
        and _is_builtin_contract(builtin, graph)
        and _is_cache_contract(cache, graph)
        and _is_providers_contract(providers)
        and getattr(value, "GraphSettings", None) is getattr(graph, "GraphSettings", None)
        and getattr(value, "Deadline", None) is getattr(providers, "Deadline", None)
        and all(
            getattr(value, name, None) is getattr(providers, name, None)
            for name in ("ProviderProbe", "ProviderQuery", "ProviderResult", "ProviderSpec")
        )
        and getattr(value, "ScanSeed", None) is getattr(builtin, "ScanSeed", None)
        and getattr(value, "ScanLimits", None) is getattr(builtin, "ScanLimits", None)
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
                "discover_providers",
                "run_provider",
                "trace_impact",
            ),
        )
    )


def _is_graph_delivery_shape(value: object) -> bool:
    contracts = getattr(value, "CONTRACTS", None)
    storage = getattr(value, "STORAGE", None)
    report_store = getattr(storage, "report_store", None)
    coordinator = getattr(value, "GRAPH_COORDINATOR", None)
    graph = getattr(value, "GRAPH", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "rir_graph_delivery.py")
        and _module_uses_sibling(contracts, SCRIPT_DIR / "rir_contracts.py")
        and _classes(contracts, ("BeginRequest", "FinalizeRequest", "FinalizeResult"))
        and _callables(contracts, ("bounded_bytes", "canonical_bytes", "validate_analysis"))
        and _module_uses_sibling(storage, SCRIPT_DIR / "rir_storage.py")
        and _module_uses_sibling(report_store, SCRIPT_DIR / "report_store.py")
        and getattr(storage, "report_store", None) is report_store
        and _callables(
            storage,
            (
                "root_path",
                "load_private_draft",
                "draft_path",
                "report_lock",
                "write_controller_metadata",
                "consume_draft",
            ),
        )
        and _module_uses_sibling(graph, SCRIPT_DIR / "impact_graph.py")
        and _is_graph_contract(graph)
        and _is_coordinator_contract(coordinator, graph)
        and getattr(coordinator, "GRAPH", None) is graph
        and _callables(
            value,
            (
                "load_graph_context",
                "validate_graph_coverage",
                "source_inventory_sha256",
                "verify_receipt_sources",
            ),
        )
    )


def _is_graph_delivery_contract(value: object) -> TypeGuard[_GraphDeliveryContract]:
    return (
        _is_graph_delivery_shape(value)
        and getattr(value, "CONTRACTS", None) is CONTRACTS
        and getattr(value, "STORAGE", None) is STORAGE
    )


GRAPH_DELIVERY = cast(
    _GraphDeliveryContract,
    _load_fixed_sibling(
        "rir_graph_delivery.py",
        "rir_graph_delivery",
        "_rir_finalize_graph_delivery_",
        _is_graph_delivery_contract,
        "graph delivery",
        aliases={
            "rir_contracts": cast(ModuleType, CONTRACTS),
            "rir_storage": cast(ModuleType, STORAGE),
        },
        rewire_validator=_is_graph_delivery_shape,
    ),
)

if not TYPE_CHECKING:
    FinalizeRequest = CONTRACTS.FinalizeRequest
    FinalizeResult = CONTRACTS.FinalizeResult


def _is_payload_identity_contract(value: object) -> bool:
    root_files = getattr(value, "ROOT_FILES", None)
    return (
        isinstance(root_files, tuple)
        and all(isinstance(item, str) for item in root_files)
        and {
            "scripts/rir_finalize.py",
            "scripts/rir_lineage.py",
            "scripts/rir_report_context.py",
        }
        <= set(root_files)
        and _callables(value, ("functional_paths", "payload_sha256"))
    )


def _payload_identity_module() -> object:
    return _load_fixed_sibling(
        "payload_identity.py",
        "payload_identity",
        "_rir_finalize_payload_identity_",
        _is_payload_identity_contract,
        "payload identity",
    )


def _payload_sha256() -> str:
    payload_identity = _payload_identity_module()
    candidate = SCRIPT_DIR.parent
    if not (candidate / ".codex-plugin" / "plugin.json").is_file():
        candidate = SCRIPT_DIR.parents[2]
    return cast(Any, payload_identity).payload_sha256(candidate)


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
        and _callables(value, ("publish_scan_receipt", "load_scan_receipt_bytes"))
    )


def _is_fast_scan_shape(value: object) -> bool:
    renderer = getattr(value, "fast_scan_renderer", None)
    store = getattr(value, "fast_scan_store", None)
    builtin = getattr(value, "graph_builtin", None)
    coordinator = getattr(value, "graph_coordinator", None)
    graph = getattr(coordinator, "GRAPH", None)
    builtin_graph = getattr(builtin, "GRAPH", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "fast_scan.py")
        and _module_uses_sibling(renderer, SCRIPT_DIR / "fast_scan_renderer.py")
        and _is_fast_scan_renderer_contract(renderer)
        and _module_uses_sibling(store, SCRIPT_DIR / "fast_scan_store.py")
        and _is_fast_scan_store_contract(store)
        and _module_uses_sibling(builtin, SCRIPT_DIR / "graph_builtin.py")
        and _module_uses_sibling(builtin_graph, SCRIPT_DIR / "impact_graph.py")
        and _is_graph_contract(builtin_graph)
        and _is_builtin_contract(builtin, builtin_graph)
        and _is_coordinator_contract(coordinator, graph)
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
                "explicit_path_candidates",
                "prepare_fast_scan_identity",
                "validate_fast_scan_receipt",
                "canonical_fast_scan_bytes",
            ),
        )
    )


def _fast_scan_modules():
    renderer = _load_fixed_sibling(
        "fast_scan_renderer.py",
        "fast_scan_renderer",
        "_rir_finalize_fast_scan_renderer_",
        _is_fast_scan_renderer_contract,
        "Fast Scan renderer",
    )
    store = _load_fixed_sibling(
        "fast_scan_store.py",
        "fast_scan_store",
        "_rir_finalize_fast_scan_store_",
        _is_fast_scan_store_contract,
        "Fast Scan store",
    )
    coordinator = GRAPH_DELIVERY.GRAPH_COORDINATOR

    def valid(value: object) -> bool:
        return (
            _is_fast_scan_shape(value)
            and getattr(value, "fast_scan_renderer", None) is renderer
            and getattr(value, "fast_scan_store", None) is store
            and getattr(value, "graph_builtin", None) is coordinator.BUILTIN
            and getattr(value, "graph_coordinator", None) is coordinator
        )

    fast_scan = _load_fixed_sibling(
        "fast_scan.py",
        "fast_scan",
        "_rir_finalize_fast_scan_",
        valid,
        "Fast Scan",
        aliases={
            "fast_scan_renderer": cast(ModuleType, renderer),
            "fast_scan_store": cast(ModuleType, store),
            "graph_builtin": cast(ModuleType, coordinator.BUILTIN),
            "graph_coordinator": cast(ModuleType, coordinator),
        },
        rewire_validator=_is_fast_scan_shape,
    )
    return cast(_FastScanContract, fast_scan), cast(Any, store)


def _promoted_scan(root: Path, request, settings: Mapping[str, object]):
    if request.scan_id is None:
        return None
    if STORAGE.DRAFT_ID_PATTERN.fullmatch(request.scan_id) is None:
        raise ValueError("invalid Fast Scan ID")
    fast_scan, fast_scan_store = _fast_scan_modules()
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
    graph_errors = GRAPH_DELIVERY.GRAPH.validate_receipt(graph)
    if graph_errors:
        raise ValueError("Fast Scan graph receipt is invalid")
    graph_payload = GRAPH_DELIVERY.GRAPH.canonical_receipt_bytes(graph)
    return {
        "scan_id": request.scan_id,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "receipt_id": graph["receipt_id"],
        "receipt_sha256": hashlib.sha256(graph_payload).hexdigest(),
    }


def load_promoted_scan_context(
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
    request = CONTRACTS.BeginRequest(
        root,
        request_value,
        tuple(evidence_value),
        adapter_value,
        audience,
        delivery,
        binding["scan_id"],
    )
    promotion = _promoted_scan(root, request, settings_value)
    if promotion != binding:
        raise ValueError("promoted Fast Scan binding is stale")
    _fast_scan, fast_scan_store = _fast_scan_modules()
    payload = fast_scan_store.load_scan_receipt_bytes(root, binding["scan_id"])
    if hashlib.sha256(payload).hexdigest() != binding["sha256"]:
        raise ValueError("promoted Fast Scan digest is stale")
    wrapper = json.loads(payload)
    if not isinstance(wrapper, dict):
        raise ValueError("promoted Fast Scan binding is invalid")
    receipt = wrapper["graph_receipt"]
    if not isinstance(receipt, dict) or GRAPH_DELIVERY.GRAPH.validate_receipt(receipt):
        raise ValueError("promoted Fast Scan binding is invalid")
    graph_payload = GRAPH_DELIVERY.GRAPH.canonical_receipt_bytes(receipt)
    if hashlib.sha256(graph_payload).hexdigest() != binding["receipt_sha256"]:
        raise ValueError("promoted graph receipt digest is stale")
    GRAPH_DELIVERY.verify_receipt_sources(root, receipt)
    inventory = wrapper.get("source_inventory")
    if (
        not isinstance(inventory, dict)
        or set(inventory) != {"digests", "complete", "reason"}
        or not isinstance(inventory.get("digests"), dict)
        or not isinstance(inventory.get("complete"), bool)
    ):
        raise ValueError("promoted Fast Scan source inventory is invalid")
    inventory_digests = cast(dict[str, str], inventory["digests"])
    required_digests = dict(inventory_digests)
    required_complete = True
    seeds = wrapper.get("seeds")
    if not isinstance(seeds, list):
        raise ValueError("promoted Fast Scan seed identity is invalid")
    for row in seeds:
        if not isinstance(row, Mapping):
            raise ValueError("promoted Fast Scan seed identity is invalid")
        location = row.get("location")
        digest = row.get("source_sha256")
        if location is None:
            continue
        if (
            not isinstance(location, str)
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            required_complete = False
            continue
        existing = required_digests.get(location)
        if existing is not None and existing != digest:
            raise ValueError("promoted Fast Scan seed digest conflicts with source inventory")
        required_digests[location] = digest
    return {
        "receipt": receipt,
        "sha256": binding["receipt_sha256"],
        "binding": binding,
        "source_inventory": {
            "sha256": GRAPH_DELIVERY.source_inventory_sha256(inventory_digests),
            "complete": inventory["complete"],
            "digests": dict(inventory_digests),
            "required_digests": required_digests,
            "required_complete": required_complete,
        },
    }


_RUNTIME_CALLABLES = (
    "root_path",
    "bounded_bytes",
    "load_draft",
    "report_lock",
    "load_graph_context",
    "load_promoted_scan_context",
    "validate_analysis",
    "validate_graph_coverage",
    "build_state",
    "canonical_bytes",
    "load_current",
    "load_controller_completion_metadata",
    "load_legacy_controller_completion_metadata",
    "write_controller_metadata",
    "migrate_legacy_controller_metadata",
    "publish_revision",
    "load_state_bytes",
    "render_compact",
    "render_markdown",
    "context_type",
    "canonical_requirement_sha256",
    "canonical_repository_evidence_sha256",
    "repo_root_sha256",
    "created_at_utc",
    "probe_git_baseline",
    "probe_source_inventory_git",
    "payload_sha256",
    "load_report_context",
    "load_legacy_report_context",
    "publish_report_context",
    "draft_path",
    "consume_draft",
    "result_type",
)


def _validate_dependency_graph() -> None:
    if not _is_lineage_contract(LINEAGE):
        raise ImportError("finalize lineage sibling contract is incomplete")
    if not _is_graph_delivery_contract(GRAPH_DELIVERY):
        raise ImportError("finalize graph delivery sibling contract is incomplete")
    if not _is_report_context_contract(REPORT_CONTEXT):
        raise ImportError("finalize report context sibling contract is incomplete")
    _payload_identity_module()
    _fast_scan_modules()


def default_runtime() -> Mapping[str, object]:
    _validate_dependency_graph()
    runtime = {
        "root_path": STORAGE.root_path,
        "bounded_bytes": CONTRACTS.bounded_bytes,
        "max_finalize_bytes": CONTRACTS.MAX_FINALIZE_BYTES,
        "load_draft": STORAGE.load_private_draft,
        "report_lock": STORAGE.report_lock,
        "load_graph_context": GRAPH_DELIVERY.load_graph_context,
        "load_promoted_scan_context": load_promoted_scan_context,
        "validate_analysis": CONTRACTS.validate_analysis,
        "validate_graph_coverage": GRAPH_DELIVERY.validate_graph_coverage,
        "build_state": LINEAGE.build_state,
        "canonical_bytes": CONTRACTS.canonical_bytes,
        "load_current": REPORT_STORE.load_current,
        "load_controller_completion_metadata": STORAGE.load_controller_completion_metadata,
        "load_legacy_controller_completion_metadata": STORAGE.load_legacy_controller_completion_metadata,
        "write_controller_metadata": STORAGE.write_controller_metadata,
        "migrate_legacy_controller_metadata": STORAGE.migrate_legacy_controller_metadata,
        "publish_revision": REPORT_STORE.publish_revision,
        "report_store_error": REPORT_STORE.ReportStoreError,
        "load_state_bytes": COMPACT_STATE.load_state_bytes,
        "render_compact": IMPACT_RENDERER.render_compact,
        "render_markdown": IMPACT_RENDERER.render_markdown,
        "context_type": REPORT_CONTEXT.ReportContext,
        "canonical_requirement_sha256": REPORT_CONTEXT.canonical_requirement_sha256,
        "canonical_repository_evidence_sha256": REPORT_CONTEXT.canonical_repository_evidence_sha256,
        "repo_root_sha256": REPORT_CONTEXT.repo_root_sha256,
        "created_at_utc": REPORT_CONTEXT.created_at_utc,
        "probe_git_baseline": REPORT_CONTEXT.probe_git_baseline,
        "probe_source_inventory_git": REPORT_CONTEXT.probe_source_inventory_git,
        "payload_sha256": _payload_sha256,
        "load_report_context": REPORT_CONTEXT.load_report_context,
        "load_legacy_report_context": REPORT_CONTEXT.load_legacy_report_context,
        "publish_report_context": REPORT_CONTEXT.publish_report_context,
        "draft_path": STORAGE.draft_path,
        "consume_draft": STORAGE.consume_draft,
        "result_type": CONTRACTS.FinalizeResult,
    }
    if not all(callable(runtime.get(name)) for name in _RUNTIME_CALLABLES):
        raise ImportError("finalize default runtime contract is incomplete")
    maximum = runtime["max_finalize_bytes"]
    report_error = runtime["report_store_error"]
    if type(maximum) is not int or maximum <= 0:
        raise ImportError("finalize default runtime contract is incomplete")
    if not isinstance(report_error, type) or not issubclass(report_error, Exception):
        raise ImportError("finalize default runtime contract is incomplete")
    return MappingProxyType(runtime)


_default_runtime = default_runtime


def _operation(runtime: Mapping[str, object], name: str):
    value = runtime.get(name)
    if not callable(value):
        raise TypeError(f"finalize runtime operation is invalid: {name}")
    return value


def _source_inventory_identity(
    graph_context: object,
) -> tuple[str | None, bool, bool, dict[str, str] | None]:
    if not isinstance(graph_context, Mapping):
        return None, False, False, None
    promoted = graph_context.get("source_inventory")
    if isinstance(promoted, Mapping):
        digest = promoted.get("sha256")
        complete = promoted.get("complete")
        digests = promoted.get("digests")
        required_digests = promoted.get("required_digests")
        required_complete = promoted.get("required_complete")
        if (
            isinstance(digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
            and isinstance(complete, bool)
            and isinstance(digests, Mapping)
            and isinstance(required_digests, Mapping)
            and isinstance(required_complete, bool)
            and all(
                isinstance(key, str) and isinstance(value, str) for key, value in digests.items()
            )
        ):
            required = (
                dict(cast(Mapping[str, str], required_digests)) if required_complete else None
            )
            return digest, True, complete, required
    binding = graph_context.get("binding")
    if isinstance(binding, Mapping):
        digest = binding.get("source_inventory_sha256")
        complete = binding.get("source_inventory_complete")
        if (
            isinstance(digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
            and isinstance(complete, bool)
        ):
            return digest, True, complete, None
    return None, False, False, None


def _existing_context_matches(
    context: object,
    context_type: type,
    *,
    report_id: str,
    revision: int,
    markdown_sha256: str,
    state_sha256: str,
    repo_sha256: str,
    requirement_sha256: str,
    repository_evidence_sha256: str,
    source_inventory_sha256: str | None,
    source_inventory_available: bool,
    source_inventory_complete: bool,
    source_inventory_git_tracked_only: bool,
    payload_sha256: str,
) -> bool:
    return (
        isinstance(context, context_type)
        and getattr(context, "schema_version", None) == 2
        and getattr(context, "report_id", None) == report_id
        and getattr(context, "revision", None) == revision
        and getattr(context, "markdown_sha256", None) == markdown_sha256
        and getattr(context, "state_sha256", None) == state_sha256
        and getattr(context, "repo_root_sha256", None) == repo_sha256
        and getattr(context, "requirement_sha256", None) == requirement_sha256
        and getattr(context, "repository_evidence_sha256", None) == repository_evidence_sha256
        and getattr(context, "source_inventory_sha256", None) == source_inventory_sha256
        and getattr(context, "source_inventory_available", None) is source_inventory_available
        and getattr(context, "source_inventory_complete", None) is source_inventory_complete
        and getattr(context, "source_inventory_git_tracked_only", None)
        is source_inventory_git_tracked_only
        and getattr(context, "payload_sha256", None) == payload_sha256
    )


def _context_identity(
    repo_sha256: str,
    requirement_sha256: str,
    state_sha256: str,
    repository_evidence_sha256: str,
    source_inventory_sha256: str | None,
    source_inventory_available: bool,
    source_inventory_complete: bool,
    source_inventory_git_tracked_only: bool,
    payload_sha256: str,
) -> dict[str, object]:
    return {
        "repo_root_sha256": repo_sha256,
        "requirement_sha256": requirement_sha256,
        "state_sha256": state_sha256,
        "repository_evidence_sha256": repository_evidence_sha256,
        "source_inventory_sha256": source_inventory_sha256,
        "source_inventory_available": source_inventory_available,
        "source_inventory_complete": source_inventory_complete,
        "source_inventory_git_tracked_only": source_inventory_git_tracked_only,
        "payload_sha256": payload_sha256,
    }


def _draft_graph_receipt_identity(draft: Mapping[str, object]) -> dict[str, str] | None:
    promoted = draft.get("promoted_scan")
    if isinstance(promoted, Mapping):
        receipt_id = promoted.get("receipt_id")
        receipt_sha256 = promoted.get("receipt_sha256")
        if isinstance(receipt_id, str) and isinstance(receipt_sha256, str):
            return {"receipt_id": receipt_id, "sha256": receipt_sha256}
    bound = draft.get("graph_receipt")
    if isinstance(bound, Mapping):
        receipt_id = bound.get("receipt_id")
        receipt_sha256 = bound.get("sha256")
        if isinstance(receipt_id, str) and isinstance(receipt_sha256, str):
            return {"receipt_id": receipt_id, "sha256": receipt_sha256}
    return None


def _verified_published_display(runtime: Mapping[str, object], published):
    try:
        state_bytes = published.state_path.read_bytes()
    except OSError as error:
        raise ValueError("published state could not be verified") from error
    stored_state, errors = _operation(runtime, "load_state_bytes")(state_bytes)
    if errors or stored_state is None:
        raise ValueError("published state could not be verified")
    report = stored_state.get("report")
    if (
        not isinstance(report, Mapping)
        or report.get("id") != published.report_id
        or report.get("revision") != published.revision
    ):
        raise ValueError("published state could not be verified")
    stored_settings = stored_state.get("settings")
    delivery = stored_settings.get("delivery") if isinstance(stored_settings, Mapping) else None
    if not isinstance(delivery, str):
        raise ValueError("published state could not be verified")
    display = (
        _operation(runtime, "render_compact")(stored_state)
        if delivery == "compact"
        else _operation(runtime, "render_markdown")(stored_state)
    )
    if display.endswith("\n"):
        display = display[:-1]
    return state_bytes, stored_state, delivery, display


def _result(runtime: Mapping[str, object], published, delivery: str, display: str):
    return _operation(runtime, "result_type")(
        status="published",
        report_id=published.report_id,
        revision=published.revision,
        delivery=delivery,
        display_text=display,
        state_path=published.state_path,
        markdown_path=published.markdown_path,
        markdown_sha256=published.markdown_sha256,
    )


def _resume_legacy_completed_publication(
    root: Path,
    draft: Mapping[str, object],
    request,
    analysis_sha256: str,
    runtime: Mapping[str, object],
    current,
    metadata: Mapping[str, object],
):
    report_id = str(draft["report_id"])
    revision_value = draft.get("revision")
    if type(revision_value) is not int:
        return None
    revision = revision_value
    if (
        metadata.get("draft_id") != draft.get("draft_id")
        or metadata.get("report_id") != report_id
        or metadata.get("revision") != revision
        or metadata.get("analysis_sha256") != analysis_sha256
        or not isinstance(metadata.get("key_map"), Mapping)
    ):
        return None
    settings = draft.get("settings")
    graph_settings = settings.get("impact_graph") if isinstance(settings, Mapping) else None
    if not isinstance(graph_settings, Mapping):
        return None
    expected_graph = _draft_graph_receipt_identity(draft)
    metadata_graph = metadata.get("graph_receipt")
    if graph_settings.get("enabled") is True:
        if (
            expected_graph is None
            or metadata_graph != expected_graph
            or request.graph_receipt_id != expected_graph["receipt_id"]
        ):
            return None
    elif (
        request.graph_receipt_id is not None
        or expected_graph is not None
        or metadata_graph is not None
    ):
        return None
    legacy_context = _operation(runtime, "load_legacy_report_context")(root, report_id, revision)
    if not isinstance(legacy_context, Mapping):
        return None
    request_value = draft.get("request")
    evidence_value = draft.get("repository_evidence")
    if (
        not isinstance(request_value, str)
        or not isinstance(evidence_value, list)
        or not all(isinstance(item, str) for item in evidence_value)
    ):
        return None
    repo_sha256 = _operation(runtime, "repo_root_sha256")(root)
    requirement_sha256 = _operation(runtime, "canonical_requirement_sha256")(request_value)
    evidence_sha256 = _operation(runtime, "canonical_repository_evidence_sha256")(
        tuple(evidence_value)
    )
    state_bytes, stored_state, delivery, display = _verified_published_display(runtime, current)
    state_sha256 = hashlib.sha256(state_bytes).hexdigest()
    if (
        metadata.get("state_sha256") != state_sha256
        or legacy_context.get("report_id") != report_id
        or legacy_context.get("revision") != revision
        or legacy_context.get("markdown_sha256") != current.markdown_sha256
        or legacy_context.get("repo_root_sha256") != repo_sha256
        or legacy_context.get("requirement_sha256") != requirement_sha256
    ):
        return None
    original = stored_state.get("original_requirement")
    if not isinstance(original, Mapping) or original.get("request") != request_value:
        return None
    source_sha256 = legacy_context.get("source_inventory_sha256")
    source_available = legacy_context.get("source_inventory_available")
    source_complete = legacy_context.get("source_inventory_complete")
    if (
        (source_sha256 is not None and not isinstance(source_sha256, str))
        or not isinstance(source_available, bool)
        or not isinstance(source_complete, bool)
    ):
        return None
    payload_sha256 = _operation(runtime, "payload_sha256")()
    context_identity = _context_identity(
        repo_sha256,
        requirement_sha256,
        state_sha256,
        evidence_sha256,
        cast(Any, source_sha256),
        source_available,
        source_complete,
        False,
        payload_sha256,
    )
    graph_receipt = cast(Any, metadata_graph)
    context_type = runtime.get("context_type")
    if not isinstance(context_type, type) or context_type is not REPORT_CONTEXT.ReportContext:
        raise TypeError("finalize report context type is invalid")
    migrated_context = _operation(runtime, "context_type")(
        schema_version=2,
        report_id=report_id,
        revision=revision,
        markdown_sha256=current.markdown_sha256,
        state_sha256=state_sha256,
        repo_root_sha256=repo_sha256,
        requirement_sha256=requirement_sha256,
        repository_evidence_sha256=evidence_sha256,
        source_inventory_sha256=source_sha256,
        payload_sha256=payload_sha256,
        created_at=legacy_context["created_at"],
        baseline_commit=legacy_context["baseline_commit"],
        baseline_clean=legacy_context["baseline_clean"],
        source_inventory_available=source_available,
        source_inventory_complete=source_complete,
        source_inventory_git_tracked_only=False,
    )
    _operation(runtime, "publish_report_context")(root, migrated_context)
    _operation(runtime, "migrate_legacy_controller_metadata")(
        root,
        draft,
        state_bytes,
        metadata["key_map"],
        graph_receipt,
        analysis_sha256,
        context_identity,
    )
    _operation(runtime, "consume_draft")(
        _operation(runtime, "draft_path")(root, str(draft["draft_id"])),
        draft,
        current,
        metadata["key_map"],
    )
    return _result(runtime, current, delivery, display)


def _resume_completed_publication(
    root: Path,
    draft: Mapping[str, object],
    request,
    analysis_sha256: str,
    runtime: Mapping[str, object],
):
    report_id = draft.get("report_id")
    revision = draft.get("revision")
    if not isinstance(report_id, str) or type(revision) is not int or revision < 1:
        return None
    current = _operation(runtime, "load_current")(root, report_id)
    if current is None or current.report_id != report_id or current.revision != revision:
        return None
    try:
        metadata = _operation(runtime, "load_controller_completion_metadata")(current)
    except ValueError as current_error:
        try:
            legacy = _operation(runtime, "load_legacy_controller_completion_metadata")(current)
        except ValueError:
            raise current_error from None
        if not isinstance(legacy, Mapping):
            raise current_error from None
        return _resume_legacy_completed_publication(
            root,
            draft,
            request,
            analysis_sha256,
            runtime,
            current,
            legacy,
        )
    if not isinstance(metadata, Mapping):
        return None
    if (
        metadata.get("draft_id") != draft.get("draft_id")
        or metadata.get("report_id") != report_id
        or metadata.get("revision") != revision
        or metadata.get("analysis_sha256") != analysis_sha256
        or not isinstance(metadata.get("key_map"), Mapping)
        or not isinstance(metadata.get("context_identity"), Mapping)
    ):
        return None
    settings = draft.get("settings")
    graph_settings = settings.get("impact_graph") if isinstance(settings, Mapping) else None
    if not isinstance(graph_settings, Mapping):
        return None
    expected_graph = _draft_graph_receipt_identity(draft)
    metadata_graph = metadata.get("graph_receipt")
    if graph_settings.get("enabled") is True:
        if (
            expected_graph is None
            or metadata_graph != expected_graph
            or request.graph_receipt_id != expected_graph["receipt_id"]
        ):
            return None
    elif (
        request.graph_receipt_id is not None
        or expected_graph is not None
        or metadata_graph is not None
    ):
        return None
    context_type = runtime.get("context_type")
    if not isinstance(context_type, type) or context_type is not REPORT_CONTEXT.ReportContext:
        raise TypeError("finalize report context type is invalid")
    context = _operation(runtime, "load_report_context")(root, report_id, revision)
    if context is None:
        identity = metadata["context_identity"]
        try:
            legacy_context = _operation(runtime, "load_legacy_report_context")(
                root, report_id, revision
            )
        except ValueError:
            return None
        request_value = draft.get("request")
        evidence_value = draft.get("repository_evidence")
        if (
            not isinstance(identity, Mapping)
            or identity.get("source_inventory_git_tracked_only") is not False
            or not isinstance(legacy_context, Mapping)
            or not isinstance(request_value, str)
            or not isinstance(evidence_value, list)
            or not all(isinstance(item, str) for item in evidence_value)
        ):
            return None
        state_bytes, _stored_state, _delivery, _display = _verified_published_display(
            runtime, current
        )
        repo_sha256 = _operation(runtime, "repo_root_sha256")(root)
        requirement_sha256 = _operation(runtime, "canonical_requirement_sha256")(request_value)
        evidence_sha256 = _operation(runtime, "canonical_repository_evidence_sha256")(
            tuple(evidence_value)
        )
        if (
            identity.get("repo_root_sha256") != repo_sha256
            or identity.get("requirement_sha256") != requirement_sha256
            or identity.get("repository_evidence_sha256") != evidence_sha256
            or identity.get("state_sha256") != hashlib.sha256(state_bytes).hexdigest()
            or legacy_context.get("markdown_sha256") != current.markdown_sha256
        ):
            return None
        context = _operation(runtime, "context_type")(
            schema_version=2,
            report_id=report_id,
            revision=revision,
            markdown_sha256=current.markdown_sha256,
            state_sha256=identity["state_sha256"],
            repo_root_sha256=repo_sha256,
            requirement_sha256=requirement_sha256,
            repository_evidence_sha256=evidence_sha256,
            source_inventory_sha256=identity.get("source_inventory_sha256"),
            payload_sha256=identity["payload_sha256"],
            created_at=legacy_context["created_at"],
            baseline_commit=legacy_context["baseline_commit"],
            baseline_clean=legacy_context["baseline_clean"],
            source_inventory_available=identity["source_inventory_available"],
            source_inventory_complete=identity["source_inventory_complete"],
            source_inventory_git_tracked_only=False,
        )
        _operation(runtime, "publish_report_context")(root, context)
    request_value = draft.get("request")
    if not isinstance(request_value, str):
        return None
    identity = metadata["context_identity"]
    source_sha256 = identity.get("source_inventory_sha256")
    source_available = identity.get("source_inventory_available")
    source_complete = identity.get("source_inventory_complete")
    source_tracked_only = identity.get("source_inventory_git_tracked_only")
    state_sha256 = identity.get("state_sha256")
    evidence_sha256 = identity.get("repository_evidence_sha256")
    if (
        (source_sha256 is not None and not isinstance(source_sha256, str))
        or not isinstance(source_available, bool)
        or not isinstance(source_complete, bool)
        or not isinstance(source_tracked_only, bool)
        or not isinstance(state_sha256, str)
        or not isinstance(evidence_sha256, str)
    ):
        return None
    repo_sha256 = _operation(runtime, "repo_root_sha256")(root)
    requirement_sha256 = _operation(runtime, "canonical_requirement_sha256")(request_value)
    evidence_value = draft.get("repository_evidence")
    if not isinstance(evidence_value, list) or not all(
        isinstance(item, str) for item in evidence_value
    ):
        return None
    expected_evidence_sha256 = _operation(runtime, "canonical_repository_evidence_sha256")(
        tuple(evidence_value)
    )
    payload_sha256 = _operation(runtime, "payload_sha256")()
    if (
        identity.get("repo_root_sha256") != repo_sha256
        or identity.get("requirement_sha256") != requirement_sha256
        or evidence_sha256 != expected_evidence_sha256
        or identity.get("payload_sha256") != payload_sha256
        or not _existing_context_matches(
            context,
            context_type,
            report_id=report_id,
            revision=revision,
            markdown_sha256=current.markdown_sha256,
            state_sha256=state_sha256,
            repo_sha256=repo_sha256,
            requirement_sha256=requirement_sha256,
            repository_evidence_sha256=expected_evidence_sha256,
            source_inventory_sha256=source_sha256,
            source_inventory_available=source_available,
            source_inventory_complete=source_complete,
            source_inventory_git_tracked_only=source_tracked_only,
            payload_sha256=payload_sha256,
        )
    ):
        return None
    state_bytes, stored_state, delivery, display = _verified_published_display(runtime, current)
    if (
        hashlib.sha256(state_bytes).hexdigest() != metadata.get("state_sha256")
        or hashlib.sha256(state_bytes).hexdigest() != state_sha256
    ):
        return None
    original = stored_state.get("original_requirement")
    if not isinstance(original, Mapping) or original.get("request") != request_value:
        return None
    _operation(runtime, "publish_report_context")(root, context)
    _operation(runtime, "consume_draft")(
        _operation(runtime, "draft_path")(root, str(draft["draft_id"])),
        draft,
        current,
        metadata["key_map"],
    )
    return _result(runtime, current, delivery, display)


def _finalize(request, runtime: Mapping[str, object]):
    root = _operation(runtime, "root_path")(request.repo_root)
    maximum = runtime.get("max_finalize_bytes")
    if type(maximum) is not int or maximum <= 0:
        raise TypeError("finalize runtime maximum is invalid")
    _operation(runtime, "bounded_bytes")(request.analysis, maximum, "finalize input")
    load_draft = _operation(runtime, "load_draft")
    draft = load_draft(root, request.draft_id)
    if draft.get("consumed") is True:
        raise ValueError("draft is already consumed")
    with _operation(runtime, "report_lock")(root, str(draft["report_id"])):
        draft = load_draft(root, request.draft_id)
        if draft.get("consumed") is True:
            raise ValueError("draft is already consumed")
        analysis_sha256 = hashlib.sha256(
            _operation(runtime, "canonical_bytes")(request.analysis)
        ).hexdigest()
        resumed = _resume_completed_publication(root, draft, request, analysis_sha256, runtime)
        if resumed is not None:
            return resumed
        settings_value = draft.get("settings")
        graph_settings = (
            settings_value.get("impact_graph") if isinstance(settings_value, dict) else None
        )
        if not isinstance(graph_settings, dict):
            raise ValueError("draft graph settings are invalid")
        graph_context = None
        if graph_settings.get("enabled") is True:
            graph_context = (
                _operation(runtime, "load_promoted_scan_context")(
                    root, draft, request.graph_receipt_id
                )
                if draft.get("promoted_scan") is not None
                else _operation(runtime, "load_graph_context")(
                    root, draft, request.graph_receipt_id
                )
            )
            _operation(runtime, "validate_analysis")(request.analysis)
            _operation(runtime, "validate_graph_coverage")(request.analysis, graph_context)
        elif request.graph_receipt_id is not None:
            raise ValueError("graph_receipt_id is not allowed when impact graph is disabled")
        state, key_map = _operation(runtime, "build_state")(draft, request.analysis, graph_context)
        state_bytes = _operation(runtime, "canonical_bytes")(state)
        request_value = draft.get("request")
        if not isinstance(request_value, str):
            raise ValueError("draft requirement identity is invalid")
        requirement_sha256 = _operation(runtime, "canonical_requirement_sha256")(request_value)
        evidence_value = draft.get("repository_evidence")
        if not isinstance(evidence_value, list) or not all(
            isinstance(item, str) for item in evidence_value
        ):
            raise ValueError("draft repository evidence identity is invalid")
        repository_evidence_sha256 = _operation(runtime, "canonical_repository_evidence_sha256")(
            tuple(evidence_value)
        )
        repo_sha256 = _operation(runtime, "repo_root_sha256")(root)
        payload_sha256 = _operation(runtime, "payload_sha256")()
        source_sha256, source_available, source_complete, source_digests = (
            _source_inventory_identity(graph_context)
        )
        fast_scan_module, _fast_scan_store = _fast_scan_modules()
        explicit_paths = fast_scan_module.explicit_path_candidates(
            request_value, tuple(evidence_value)
        )
        explicit_paths_complete = source_digests is not None and all(
            path in source_digests for path in explicit_paths
        )
        if not explicit_paths_complete:
            source_digests = None
        state_sha256 = hashlib.sha256(state_bytes).hexdigest()
        baseline = (
            _operation(runtime, "probe_source_inventory_git")(root, source_digests)
            if source_available and source_complete and source_digests is not None
            else (*_operation(runtime, "probe_git_baseline")(root), False)
        )
        if (
            not isinstance(baseline, tuple)
            or len(baseline) != 3
            or (baseline[0] is not None and not isinstance(baseline[0], str))
            or not isinstance(baseline[1], bool)
            or not isinstance(baseline[2], bool)
        ):
            raise TypeError("finalize Git source proof result is invalid")
        baseline_commit, baseline_clean, source_inventory_git_tracked_only = baseline
        context_identity = _context_identity(
            repo_sha256,
            requirement_sha256,
            state_sha256,
            repository_evidence_sha256,
            source_sha256,
            source_available,
            source_complete,
            source_inventory_git_tracked_only,
            payload_sha256,
        )
        created_at = _operation(runtime, "created_at_utc")()
        _operation(runtime, "write_controller_metadata")(
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
            analysis_sha256,
            context_identity,
        )
        report_store_error = runtime.get("report_store_error")
        if not isinstance(report_store_error, type) or not issubclass(
            report_store_error, Exception
        ):
            raise TypeError("finalize runtime report error is invalid")
        try:
            published = _operation(runtime, "publish_revision")(
                root, state_bytes, resume_partial=True
            )
        except (FileExistsError, report_store_error) as error:
            raise ValueError(f"controller publication failed: {error}") from error
        _stored_bytes, _stored_state, delivery, display = _verified_published_display(
            runtime, published
        )
        if hashlib.sha256(_stored_bytes).hexdigest() != state_sha256:
            raise ValueError("published state does not match finalization identity")
        context_type = runtime.get("context_type")
        if not isinstance(context_type, type) or context_type is not REPORT_CONTEXT.ReportContext:
            raise TypeError("finalize report context type is invalid")
        existing_context = _operation(runtime, "load_report_context")(
            root, published.report_id, published.revision
        )
        if existing_context is None:
            report_context = _operation(runtime, "context_type")(
                schema_version=2,
                report_id=published.report_id,
                revision=published.revision,
                markdown_sha256=published.markdown_sha256,
                state_sha256=state_sha256,
                repo_root_sha256=repo_sha256,
                requirement_sha256=requirement_sha256,
                repository_evidence_sha256=repository_evidence_sha256,
                source_inventory_sha256=source_sha256,
                payload_sha256=payload_sha256,
                created_at=created_at,
                baseline_commit=baseline_commit,
                baseline_clean=baseline_clean,
                source_inventory_available=source_available,
                source_inventory_complete=source_complete,
                source_inventory_git_tracked_only=source_inventory_git_tracked_only,
            )
        else:
            if not _existing_context_matches(
                existing_context,
                context_type,
                report_id=published.report_id,
                revision=published.revision,
                markdown_sha256=published.markdown_sha256,
                state_sha256=state_sha256,
                repo_sha256=repo_sha256,
                requirement_sha256=requirement_sha256,
                repository_evidence_sha256=repository_evidence_sha256,
                source_inventory_sha256=source_sha256,
                source_inventory_available=source_available,
                source_inventory_complete=source_complete,
                source_inventory_git_tracked_only=source_inventory_git_tracked_only,
                payload_sha256=payload_sha256,
            ):
                raise ValueError("published report context does not match finalization identity")
            report_context = existing_context
        _operation(runtime, "publish_report_context")(root, report_context)
        _operation(runtime, "consume_draft")(
            _operation(runtime, "draft_path")(root, request.draft_id),
            draft,
            published,
            key_map,
        )
    return _result(runtime, published, delivery, display)


def finalize_refinement(
    request: FinalizeRequest, *, _runtime: Mapping[str, object] | None = None
) -> FinalizeResult:
    return _finalize(request, default_runtime() if _runtime is None else _runtime)
