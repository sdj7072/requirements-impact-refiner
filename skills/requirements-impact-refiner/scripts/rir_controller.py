#!/usr/bin/env python3

from __future__ import annotations

import ctypes
import errno
import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
import sys
import tempfile
import time
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, SupportsInt, TypedDict

from typing_extensions import TypeGuard

if TYPE_CHECKING:
    from graph_builtin import ScanSeed as ScanSeedType
    from graph_coordinator import SourceInventory as SourceInventoryType
    from graph_providers import Deadline as DeadlineType
    from impact_graph import GraphReceipt as GraphReceiptType
    from impact_graph import GraphSettings as GraphSettingsType
    from impact_graph import ProviderStatus as ProviderStatusType


class _FcntlContract(Protocol):
    LOCK_EX: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, fd: int, operation: int) -> None: ...


def _is_fcntl_contract(value: object) -> TypeGuard[_FcntlContract]:
    return all(
        isinstance(getattr(value, name, None), int) for name in ("LOCK_EX", "LOCK_NB", "LOCK_UN")
    ) and callable(getattr(value, "flock", None))


try:
    import fcntl as _loaded_fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback is serialized per process
    fcntl: _FcntlContract | None = None
else:
    if not _is_fcntl_contract(_loaded_fcntl):  # pragma: no cover - standard-library contract
        raise ImportError("fcntl contract is incomplete")
    fcntl = _loaded_fcntl


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import compact_state
import fast_scan
import fast_scan_store
import impact_renderer
import payload_identity
import report_store

MAX_BEGIN_BYTES = 256 * 1024
MAX_TRACE_BYTES = 256 * 1024
MAX_FINALIZE_BYTES = 2 * 1024 * 1024
MAX_STRING_BYTES = 64 * 1024
MAX_DRAFT_BYTES = 4 * 1024 * 1024
MAX_TRACE_SEEDS = 128
DRAFT_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
LOCAL_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}")
ADAPTERS = {"generic", "superpowers", "claude-feature-dev", "spec-kit"}
SUPERPOWERS_HANDOFF_MARKER = (
    "superpowers:after-approved-brainstorming;impact-refinement;manual-handoff-before-writing-plans"
)
ANALYSIS_KEYS = {
    "phase",
    "refined_requirement",
    "invariants",
    "impacts",
    "decision_needed",
    "decisions",
    "criteria",
    "unresolved",
    "scope",
    "workflow",
}
ROW_KEYS = {
    "invariants": {"key", "behavior", "evidence_level", "evidence"},
    "impacts": {
        "key",
        "category",
        "severity",
        "state",
        "evidence_level",
        "evidence",
        "invariant_keys",
        "decision_keys",
        "criterion_keys",
        "summary",
    },
    "decisions": {"key", "choice", "accepted_impact_keys", "rationale"},
    "criteria": {"key", "impact_key", "invariant_key", "criterion", "evidence"},
    "unresolved": {"impact_key", "state", "rationale", "decision_key", "owner"},
    "scope": {"boundary", "evidence", "confidence"},
}
IMPACT_OPTIONAL_KEYS = {"graph_path_keys", "coverage_rationale"}
SUMMARY_KEYS = {"changed_feature", "possible_issue", "affected", "trigger", "prevention"}
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


def _load_graph_coordinator() -> object:
    path = SCRIPT_DIR / "graph_coordinator.py"
    module_name = (
        "_rir_controller_graph_coordinator_"
        + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    )
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load fixed graph coordinator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_loaded_graph_coordinator = _load_graph_coordinator()
if not _is_graph_coordinator_contract(_loaded_graph_coordinator):
    raise ImportError("graph coordinator sibling contract is incomplete")
GRAPH_COORDINATOR = _loaded_graph_coordinator
GRAPH = GRAPH_COORDINATOR.GRAPH
TraceSeed = GRAPH_COORDINATOR.ScanSeed


def _is_receipt_payload(value: object) -> TypeGuard[ReceiptPayload]:
    return not GRAPH.validate_receipt(value)


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


@dataclass(frozen=True)
class BeginRequest:
    repo_root: Path
    request: str
    repository_evidence: tuple[str, ...]
    adapter: str
    audience_override: str | None = None
    delivery_override: str | None = None
    scan_id: str | None = None


@dataclass(frozen=True)
class DraftResult:
    draft_id: str
    draft_path: Path
    report_id: str
    revision: int
    previous_sha256: str
    settings: Mapping[str, object]
    prior_state: Mapping[str, object] | None
    prior_key_map: Mapping[str, object] | None
    scan_id: str | None = None
    graph_receipt_id: str | None = None


@dataclass(frozen=True)
class ScanRequest:
    repo_root: Path
    change_request: str
    evidence: tuple[str, ...]
    audience_override: str | None = None


ScanResult = fast_scan.FastScanResult


@dataclass(frozen=True)
class TraceRequest:
    repo_root: Path
    draft_id: str
    seeds: tuple[ScanSeedType, ...]


@dataclass(frozen=True)
class TraceResult:
    receipt_id: str
    receipt_path: Path
    receipt_sha256: str
    compact_graph: CompactGraphPayload
    budget_status: str
    request_sha256: str
    seeds: tuple[ScanSeedType, ...]


@dataclass(frozen=True)
class FinalizeRequest:
    repo_root: Path
    draft_id: str
    analysis: Mapping[str, object]
    graph_receipt_id: str | None = None


@dataclass(frozen=True)
class FinalizeResult:
    status: str
    report_id: str
    revision: int
    delivery: str
    display_text: str
    state_path: Path
    markdown_path: Path
    markdown_sha256: str


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _root(path: Path) -> Path:
    try:
        root = Path(path).resolve(strict=True)
    except OSError as error:
        raise ValueError(f"repository root is unavailable: {error}") from error
    if not root.is_dir():
        raise ValueError("repository root must be an existing directory")
    return root


def _open_directory_at(parent_fd: int, name: str, mode: int) -> int:
    try:
        os.mkdir(name, mode=mode, dir_fd=parent_fd)
    except FileExistsError:
        pass
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except OSError as error:
        raise ValueError(f"controller directory is unsafe: {name}: {error}") from error


def _private_draft_directory_fd(root: Path) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    root_fd = os.open(root, flags)
    base_fd = None
    try:
        base_fd = _open_directory_at(root_fd, ".requirements-impact-refiner", 0o755)
        draft_fd = _open_directory_at(base_fd, "drafts", 0o700)
        os.fchmod(draft_fd, 0o700)
        return draft_fd
    finally:
        if base_fd is not None:
            os.close(base_fd)
        os.close(root_fd)


def _write_private_draft(root: Path, draft_id: str, payload: bytes) -> Path:
    directory_fd = _private_draft_directory_fd(root)
    file_fd = None
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        file_fd = os.open(f"{draft_id}.json", flags, 0o600, dir_fd=directory_fd)
        offset = 0
        while offset < len(payload):
            offset += os.write(file_fd, payload[offset:])
        os.fsync(file_fd)
    except OSError as error:
        raise ValueError(f"cannot create draft: {error}") from error
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(directory_fd)
    return root / ".requirements-impact-refiner" / "drafts" / f"{draft_id}.json"


def _all_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _all_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _all_strings(item)


def _bounded(value: object, maximum: int, label: str) -> bytes:
    payload = _canonical_bytes(value)
    if len(payload) > maximum:
        unit = "256 KiB" if maximum in {MAX_BEGIN_BYTES, MAX_TRACE_BYTES} else "2 MiB"
        raise ValueError(f"{label} exceeds {unit}")
    if any(len(text.encode("utf-8")) > MAX_STRING_BYTES for text in _all_strings(value)):
        raise ValueError(f"{label} contains a string larger than 64 KiB")
    return payload


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


def _controller_metadata_path(report_id: str, revision: int, root: Path) -> Path:
    report_dir = report_store.report_directory(root, report_id, create=True)
    return report_dir / f"revision-{revision:04d}.controller.json"


def _load_controller_metadata(current) -> dict[str, object] | None:
    path = current.state_path.with_name(f"revision-{current.revision:04d}.controller.json")
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError("controller lineage metadata is unsafe")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        current_state_sha256 = hashlib.sha256(current.state_path.read_bytes()).hexdigest()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"controller lineage metadata is invalid: {error}") from error
    if (
        not isinstance(payload, dict)
        or payload.get("report_id") != current.report_id
        or payload.get("revision") != current.revision
        or payload.get("state_sha256") != current_state_sha256
        or not isinstance(payload.get("key_map"), dict)
    ):
        raise ValueError("controller lineage metadata identity is invalid")
    return payload["key_map"]


def _draft_path(root: Path, draft_id: str) -> Path:
    if DRAFT_ID_PATTERN.fullmatch(draft_id) is None:
        raise ValueError("invalid draft ID")
    return root / ".requirements-impact-refiner" / "drafts" / f"{draft_id}.json"


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


def load_draft(repo_root: Path, draft_id: str) -> dict[str, object]:
    root = _root(repo_root)
    if DRAFT_ID_PATTERN.fullmatch(draft_id) is None:
        raise ValueError("invalid draft ID")
    directory_fd = _private_draft_directory_fd(root)
    file_fd = None
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        file_fd = os.open(f"{draft_id}.json", flags, dir_fd=directory_fd)
        chunks = []
        total = 0
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DRAFT_BYTES:
                raise ValueError("draft exceeds 4 MiB")
            chunks.append(chunk)
        value = json.loads(b"".join(chunks).decode("utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"draft is invalid: {error}") from error
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(directory_fd)
    if not isinstance(value, dict) or value.get("draft_id") != draft_id:
        raise ValueError("draft identity is invalid")
    if value.get("repo_root") != str(root):
        raise ValueError("draft repository root does not match")
    return value


def _graph_draft_identity(draft: Mapping[str, object]) -> dict[str, object]:
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


def _replace_private_draft(root: Path, draft_id: str, value: Mapping[str, object]) -> None:
    directory_fd = _private_draft_directory_fd(root)
    temporary_name = f".{draft_id}.{secrets.token_hex(8)}.tmp"
    descriptor = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
        payload = _canonical_bytes(value)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(
            temporary_name,
            f"{draft_id}.json",
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    except OSError as error:
        raise ValueError(f"cannot bind graph receipt to draft: {error}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)


def _read_bounded_descriptor(descriptor: int, maximum: int, label: str) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    payload = bytearray()
    while len(payload) <= maximum:
        chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - len(payload)))
        if not chunk:
            break
        payload.extend(chunk)
    if len(payload) > maximum:
        raise ValueError(f"{label} exceeds maximum byte size")
    return bytes(payload)


_DRAFT_TRANSACTION_KEYS = {
    "schema_version",
    "draft_id",
    "repo_root_sha256",
    "transaction_id",
    "expected_sha256",
    "expected_dev",
    "expected_ino",
    "replacement_sha256",
    "replacement_dev",
    "replacement_ino",
}
_DRAFT_TRANSACTION_MAX_BYTES = 16 * 1024


@contextmanager
def _draft_transaction_lock(directory_fd: int):
    descriptor = None
    locked = False
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(".draft-transaction.lock", flags, 0o600, dir_fd=directory_fd)
    except OSError as error:
        raise ValueError(f"draft transaction lock is unavailable: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise ValueError("draft transaction lock is unsafe")
        current_fcntl = fcntl
        if current_fcntl is not None:
            try:
                current_fcntl.flock(descriptor, current_fcntl.LOCK_EX | current_fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("draft transaction recovery is busy; retry") from error
            locked = True
        yield
    finally:
        if descriptor is not None:
            if locked and current_fcntl is not None:
                current_fcntl.flock(descriptor, current_fcntl.LOCK_UN)
            os.close(descriptor)


def _write_private_transaction_component(directory_fd: int, name: str, payload: bytes, label: str):
    descriptor = None
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise ValueError(f"{label} is unsafe")
        return descriptor, metadata
    except BaseException as error:
        cleanup_error = None
        if descriptor is not None:
            try:
                metadata = os.fstat(descriptor)
                actual_payload = _read_bounded_descriptor(descriptor, max(len(payload), 1), label)
                _unlink_transaction_component(
                    directory_fd,
                    name,
                    (descriptor, metadata, actual_payload),
                    payload,
                    max(len(payload), 1),
                    label,
                )
            except (OSError, ValueError) as cleanup_failure:
                cleanup_error = cleanup_failure
            os.close(descriptor)
        if cleanup_error is not None:
            raise ValueError(
                f"cannot persist {label}; cleanup is uncertain: {cleanup_error}"
            ) from error
        if isinstance(error, OSError):
            raise ValueError(f"cannot persist {label}: {error}") from error
        raise


def _open_optional_transaction_component(directory_fd: int, name: str, maximum: int, label: str):
    descriptor = None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ValueError(f"{label} is unavailable or unsafe: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ValueError(f"{label} is not a private regular file")
        payload = _read_bounded_descriptor(descriptor, maximum, label)
        return descriptor, metadata, payload
    except BaseException:
        os.close(descriptor)
        raise


def _transaction_removing_name(name: str) -> str:
    return f"{name}.removing"


def _open_transaction_component_for_cleanup(directory_fd: int, name: str, maximum: int, label: str):
    removing_name = _transaction_removing_name(name)
    original = _open_optional_transaction_component(directory_fd, name, maximum, label)
    try:
        removing = _open_optional_transaction_component(
            directory_fd,
            removing_name,
            maximum,
            f"{label} removal quarantine",
        )
    except BaseException:
        if original is not None:
            os.close(original[0])
        raise
    if original is not None and removing is not None:
        os.close(original[0])
        os.close(removing[0])
        raise ValueError(f"{label} and its removal quarantine both exist; recovery is uncertain")
    if removing is not None:
        return removing, removing_name
    return original, name


def _draft_transaction_phase_payload(
    draft_id: str, transaction_id: str, phase: str, manifest_sha256: str
) -> bytes:
    return _canonical_bytes(
        {
            "draft_id": draft_id,
            "manifest_sha256": manifest_sha256,
            "phase": phase,
            "schema_version": 1,
            "transaction_id": transaction_id,
        }
    )


_DRAFT_CLEANUP_KEYS = {
    "draft_id",
    "kind",
    "manifest_sha256",
    "replacement_dev",
    "replacement_ino",
    "replacement_sha256",
    "repo_root_sha256",
    "schema_version",
    "transaction_id",
}


def _draft_transaction_cleanup_payload(
    root: Path,
    draft_id: str,
    manifest: Mapping[str, object],
    manifest_payload: bytes,
) -> bytes:
    return _canonical_bytes(
        {
            "draft_id": draft_id,
            "kind": "draft-transaction-cleanup",
            "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
            "replacement_dev": manifest["replacement_dev"],
            "replacement_ino": manifest["replacement_ino"],
            "replacement_sha256": manifest["replacement_sha256"],
            "repo_root_sha256": hashlib.sha256(str(root).encode("utf-8")).hexdigest(),
            "schema_version": 1,
            "transaction_id": manifest["transaction_id"],
        }
    )


def _validate_draft_transaction_cleanup(
    root: Path,
    draft_id: str,
    cleanup_component,
    canonical_component,
    *,
    manifest: Mapping[str, object] | None = None,
    manifest_payload: bytes | None = None,
) -> Mapping[str, object]:
    try:
        cleanup = json.loads(cleanup_component[2].decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"draft transaction cleanup phase is invalid: {error}") from error
    if (
        not isinstance(cleanup, dict)
        or set(cleanup) != _DRAFT_CLEANUP_KEYS
        or cleanup.get("schema_version") != 1
        or cleanup.get("kind") != "draft-transaction-cleanup"
        or cleanup.get("draft_id") != draft_id
        or cleanup.get("repo_root_sha256") != hashlib.sha256(str(root).encode("utf-8")).hexdigest()
        or not isinstance(cleanup.get("transaction_id"), str)
        or DRAFT_ID_PATTERN.fullmatch(cleanup["transaction_id"]) is None
        or any(
            not isinstance(cleanup.get(key), int) or cleanup[key] < 0
            for key in ("replacement_dev", "replacement_ino")
        )
        or any(
            not isinstance(cleanup.get(key), str)
            or re.fullmatch(r"[0-9a-f]{64}", cleanup[key]) is None
            for key in ("manifest_sha256", "replacement_sha256")
        )
        or _canonical_bytes(cleanup) != cleanup_component[2]
        or cleanup_component[1].st_nlink != 1
    ):
        raise ValueError("draft transaction cleanup phase identity is invalid")
    if manifest is not None:
        if manifest_payload is None or cleanup_component[2] != (
            _draft_transaction_cleanup_payload(root, draft_id, manifest, manifest_payload)
        ):
            raise ValueError("draft transaction cleanup phase does not match its manifest")
    if canonical_component is None:
        raise ValueError("draft transaction cleanup phase lost canonical draft")
    canonical_info = canonical_component[1]
    canonical_payload = canonical_component[2]
    if (
        not stat.S_ISREG(canonical_info.st_mode)
        or stat.S_IMODE(canonical_info.st_mode) != 0o600
        or canonical_info.st_nlink != 1
        or (canonical_info.st_dev, canonical_info.st_ino)
        != (cleanup["replacement_dev"], cleanup["replacement_ino"])
        or hashlib.sha256(canonical_payload).hexdigest() != cleanup["replacement_sha256"]
    ):
        raise ValueError("draft transaction cleanup canonical identity is invalid")
    _validate_transaction_draft_payload(
        canonical_payload,
        root,
        draft_id,
        "draft transaction cleanup canonical",
    )
    return cleanup


def _validate_transaction_draft_payload(
    payload: bytes, root: Path, draft_id: str, label: str
) -> None:
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not a valid draft: {error}") from error
    if (
        not isinstance(value, dict)
        or value.get("draft_id") != draft_id
        or value.get("repo_root") != str(root)
        or _canonical_bytes(value) != payload
    ):
        raise ValueError(f"{label} draft identity is invalid")


def _same_inode(first, second) -> bool:
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


def _rename_noreplace(directory_fd: int, source: str, destination: str) -> None:
    """Atomically move one parent-fd-relative name without clobbering another."""
    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if sys.platform == "darwin":
        operation = library.renameatx_np
        operation.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        operation.restype = ctypes.c_int
        result = operation(
            directory_fd,
            source_bytes,
            directory_fd,
            destination_bytes,
            0x00000004,  # RENAME_EXCL
        )
    elif sys.platform.startswith("linux"):
        try:
            operation = library.renameat2
        except AttributeError as error:
            raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable") from error
        operation.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        operation.restype = ctypes.c_int
        result = operation(
            directory_fd,
            source_bytes,
            directory_fd,
            destination_bytes,
            0x00000001,  # RENAME_NOREPLACE
        )
    else:
        raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable")
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise FileExistsError(error_number, os.strerror(error_number), destination)
    raise OSError(error_number, os.strerror(error_number), source)


def _restore_quarantined_path(directory_fd: int, quarantine_name: str, original_name: str) -> bool:
    try:
        os.link(
            quarantine_name,
            original_name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
    except (FileExistsError, OSError):
        return False
    try:
        quarantine_info = os.stat(quarantine_name, dir_fd=directory_fd, follow_symlinks=False)
        restored_info = os.stat(original_name, dir_fd=directory_fd, follow_symlinks=False)
        if not _same_inode(quarantine_info, restored_info):
            return False
        os.unlink(quarantine_name, dir_fd=directory_fd)
        return True
    except OSError:
        return False


def _unlink_transaction_component(
    directory_fd: int,
    name: str,
    component,
    expected_payload: bytes,
    maximum: int,
    label: str,
    *,
    selected_name: str | None = None,
) -> None:
    if component is None:
        return
    descriptor, metadata, payload = component
    selected = name if selected_name is None else selected_name
    removing_name = _transaction_removing_name(name)
    if selected not in {name, removing_name}:
        raise ValueError(f"{label} cleanup path is invalid")
    if payload != expected_payload:
        raise ValueError(f"{label} changed before cleanup")
    try:
        current = os.stat(selected, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as error:
        raise ValueError(f"{label} is unavailable before cleanup: {error}") from error
    if (
        not _same_inode(current, metadata)
        or _read_bounded_descriptor(descriptor, maximum, label) != expected_payload
    ):
        raise ValueError(f"{label} identity changed before cleanup")

    if selected == name:
        try:
            _rename_noreplace(directory_fd, name, removing_name)
        except FileExistsError as error:
            raise ValueError(
                f"{label} removal quarantine already exists; recovery is uncertain"
            ) from error
        except OSError as error:
            raise ValueError(f"{label} cannot be quarantined: {error}") from error
        selected = removing_name

    try:
        quarantined = _open_optional_transaction_component(
            directory_fd,
            selected,
            maximum,
            f"{label} removal quarantine",
        )
    except ValueError as error:
        restored = _restore_quarantined_path(directory_fd, selected, name)
        qualifier = "restored" if restored else "restoration is uncertain"
        raise ValueError(f"{label} replacement was quarantined and {qualifier}") from error
    if quarantined is None:
        raise ValueError(f"{label} removal quarantine disappeared")
    quarantine_fd = quarantined[0]
    try:
        if (
            not _same_inode(quarantined[1], metadata)
            or quarantined[2] != expected_payload
            or _read_bounded_descriptor(descriptor, maximum, label) != expected_payload
        ):
            restored = _restore_quarantined_path(directory_fd, selected, name)
            qualifier = "restored" if restored else "restoration is uncertain"
            raise ValueError(f"{label} replacement was quarantined and {qualifier}")
        try:
            os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError as error:
            raise ValueError(f"{label} canonical cleanup namespace is unsafe: {error}") from error
        else:
            raise ValueError(f"{label} replacement preserved; recovery is uncertain")
        os.unlink(selected, dir_fd=directory_fd)
        try:
            os.stat(selected, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError(f"{label} quarantine replacement preserved; recovery is uncertain")
        try:
            os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError(f"{label} late replacement preserved; recovery is uncertain")
        os.fsync(directory_fd)
    finally:
        os.close(quarantine_fd)


def _recover_private_draft_transaction_at(root: Path, draft_id: str, directory_fd: int) -> None:
    manifest_name = f".{draft_id}.transaction"
    cleanup_name = f".{draft_id}.cleanup"
    manifest_component, manifest_selected_name = _open_transaction_component_for_cleanup(
        directory_fd,
        manifest_name,
        _DRAFT_TRANSACTION_MAX_BYTES,
        "draft transaction manifest",
    )
    try:
        cleanup_component, cleanup_selected_name = _open_transaction_component_for_cleanup(
            directory_fd,
            cleanup_name,
            _DRAFT_TRANSACTION_MAX_BYTES,
            "draft transaction cleanup phase",
        )
    except BaseException:
        if manifest_component is not None:
            os.close(manifest_component[0])
        raise
    opened = []
    if manifest_component is None:
        if cleanup_component is None:
            return
        opened.append(cleanup_component[0])
        canonical = _open_optional_transaction_component(
            directory_fd,
            f"{draft_id}.json",
            MAX_DRAFT_BYTES,
            "draft transaction cleanup canonical draft",
        )
        if canonical is not None:
            opened.append(canonical[0])
        try:
            _validate_draft_transaction_cleanup(root, draft_id, cleanup_component, canonical)
            _unlink_transaction_component(
                directory_fd,
                cleanup_name,
                cleanup_component,
                cleanup_component[2],
                _DRAFT_TRANSACTION_MAX_BYTES,
                "draft transaction cleanup phase",
                selected_name=cleanup_selected_name,
            )
            os.fsync(directory_fd)
            return
        finally:
            for descriptor in reversed(opened):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
    opened = [manifest_component[0]]
    if cleanup_component is not None:
        opened.append(cleanup_component[0])
    try:
        manifest_payload = manifest_component[2]
        try:
            manifest = json.loads(manifest_payload.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"draft transaction manifest is invalid: {error}") from error
        if (
            not isinstance(manifest, dict)
            or set(manifest) != _DRAFT_TRANSACTION_KEYS
            or manifest.get("schema_version") != 1
            or manifest.get("draft_id") != draft_id
            or manifest.get("repo_root_sha256")
            != hashlib.sha256(str(root).encode("utf-8")).hexdigest()
            or not isinstance(manifest.get("transaction_id"), str)
            or DRAFT_ID_PATTERN.fullmatch(manifest["transaction_id"]) is None
            or any(
                not isinstance(manifest.get(key), int) or manifest[key] < 0
                for key in (
                    "expected_dev",
                    "expected_ino",
                    "replacement_dev",
                    "replacement_ino",
                )
            )
            or any(
                not isinstance(manifest.get(key), str)
                or re.fullmatch(r"[0-9a-f]{64}", manifest[key]) is None
                for key in ("expected_sha256", "replacement_sha256")
            )
            or _canonical_bytes(manifest) != manifest_payload
            or manifest_component[1].st_nlink != 1
        ):
            raise ValueError("draft transaction manifest identity is invalid")

        transaction_id = manifest["transaction_id"]
        manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
        filename = f"{draft_id}.json"
        names = {
            "anchor": f".{draft_id}.{transaction_id}.anchor",
            "replacement": f".{draft_id}.{transaction_id}.new",
            "quarantine": f".{draft_id}.{transaction_id}.quarantine",
            "swap": f".{draft_id}.{transaction_id}.swap",
            "commit": f".{draft_id}.{transaction_id}.commit",
        }
        swap_payload = _draft_transaction_phase_payload(
            draft_id, transaction_id, "swap", manifest_sha256
        )
        commit_payload = _draft_transaction_phase_payload(
            draft_id, transaction_id, "commit", manifest_sha256
        )
        components = {
            "canonical": _open_optional_transaction_component(
                directory_fd,
                filename,
                MAX_DRAFT_BYTES,
                "draft transaction canonical draft",
            )
        }
        component_paths = {"canonical": filename}
        if components["canonical"] is not None:
            opened.append(components["canonical"][0])
        for component_name, maximum, label in (
            ("anchor", MAX_DRAFT_BYTES, "draft transaction expected anchor"),
            ("replacement", MAX_DRAFT_BYTES, "draft transaction replacement"),
            ("quarantine", MAX_DRAFT_BYTES, "draft transaction quarantine"),
            ("swap", 1024, "draft transaction swap phase"),
            ("commit", 1024, "draft transaction commit phase"),
        ):
            component, selected_name = _open_transaction_component_for_cleanup(
                directory_fd,
                names[component_name],
                maximum,
                label,
            )
            components[component_name] = component
            component_paths[component_name] = selected_name
            if component is not None:
                opened.append(component[0])
        if components["swap"] is not None and (
            components["swap"][2] != swap_payload or components["swap"][1].st_nlink != 1
        ):
            raise ValueError("draft transaction swap phase identity is invalid")
        if components["commit"] is not None and (
            components["commit"][2] != commit_payload or components["commit"][1].st_nlink != 1
        ):
            raise ValueError("draft transaction commit phase identity is invalid")
        if (
            cleanup_component is None
            and components["commit"] is not None
            and components["swap"] is None
        ):
            raise ValueError("draft transaction commit phase has no durable swap phase")

        expected_inode = (manifest["expected_dev"], manifest["expected_ino"])
        replacement_inode = (manifest["replacement_dev"], manifest["replacement_ino"])
        expected_payload = replacement_payload = None
        canonical_kind = None
        for name in ("canonical", "anchor", "replacement", "quarantine"):
            component = components[name]
            if component is None:
                continue
            inode = (component[1].st_dev, component[1].st_ino)
            digest = hashlib.sha256(component[2]).hexdigest()
            if inode == expected_inode and digest == manifest["expected_sha256"]:
                kind = "expected"
                if expected_payload is None:
                    expected_payload = component[2]
                elif expected_payload != component[2]:
                    raise ValueError("draft transaction expected bytes disagree")
            elif inode == replacement_inode and digest == manifest["replacement_sha256"]:
                kind = "replacement"
                if replacement_payload is None:
                    replacement_payload = component[2]
                elif replacement_payload != component[2]:
                    raise ValueError("draft transaction replacement bytes disagree")
            else:
                raise ValueError(f"draft transaction {name} identity is invalid")
            if name in {"anchor", "quarantine"} and kind != "expected":
                raise ValueError(f"draft transaction {name} is cross-transaction")
            if name == "replacement" and kind != "replacement":
                raise ValueError("draft transaction replacement is cross-transaction")
            if name == "canonical":
                canonical_kind = kind

        for payload, label in (
            (expected_payload, "draft transaction expected artifact"),
            (replacement_payload, "draft transaction replacement artifact"),
        ):
            if payload is not None:
                _validate_transaction_draft_payload(payload, root, draft_id, label)

        expected_links = sum(
            1
            for name in ("canonical", "anchor", "quarantine")
            if components[name] is not None
            and (components[name][1].st_dev, components[name][1].st_ino) == expected_inode
        )
        replacement_links = sum(
            1
            for name in ("canonical", "replacement")
            if components[name] is not None
            and (components[name][1].st_dev, components[name][1].st_ino) == replacement_inode
        )
        for name in ("canonical", "anchor", "replacement", "quarantine"):
            component = components[name]
            if component is None:
                continue
            inode = (component[1].st_dev, component[1].st_ino)
            expected_count = expected_links if inode == expected_inode else replacement_links
            if component[1].st_nlink != expected_count:
                raise ValueError(f"draft transaction {name} has an unbound hard-link identity")

        def remove(name: str, payload: bytes, maximum: int, label: str) -> None:
            _unlink_transaction_component(
                directory_fd,
                names[name],
                components[name],
                payload,
                maximum,
                label,
                selected_name=component_paths[name],
            )
            components[name] = None

        def remove_manifest() -> None:
            _unlink_transaction_component(
                directory_fd,
                manifest_name,
                manifest_component,
                manifest_payload,
                _DRAFT_TRANSACTION_MAX_BYTES,
                "draft transaction manifest",
                selected_name=manifest_selected_name,
            )

        def remove_cleanup() -> None:
            if cleanup_component is None:
                return
            _unlink_transaction_component(
                directory_fd,
                cleanup_name,
                cleanup_component,
                cleanup_component[2],
                _DRAFT_TRANSACTION_MAX_BYTES,
                "draft transaction cleanup phase",
                selected_name=cleanup_selected_name,
            )

        def finish_rollback() -> None:
            if components["replacement"] is not None:
                remove(
                    "replacement",
                    components["replacement"][2],
                    MAX_DRAFT_BYTES,
                    "draft transaction replacement",
                )
            if components["quarantine"] is not None:
                remove(
                    "quarantine",
                    components["quarantine"][2],
                    MAX_DRAFT_BYTES,
                    "draft transaction quarantine",
                )
            if components["anchor"] is not None:
                remove(
                    "anchor",
                    components["anchor"][2],
                    MAX_DRAFT_BYTES,
                    "draft transaction expected anchor",
                )
            if components["commit"] is not None:
                remove(
                    "commit",
                    commit_payload,
                    1024,
                    "draft transaction commit phase",
                )
            if components["swap"] is not None:
                remove(
                    "swap",
                    swap_payload,
                    1024,
                    "draft transaction swap phase",
                )
            canonical = _open_optional_transaction_component(
                directory_fd,
                filename,
                MAX_DRAFT_BYTES,
                "restored canonical draft",
            )
            if canonical is None:
                raise ValueError("draft transaction rollback lost canonical draft")
            opened.append(canonical[0])
            if (
                (canonical[1].st_dev, canonical[1].st_ino) != expected_inode
                or hashlib.sha256(canonical[2]).hexdigest() != manifest["expected_sha256"]
                or canonical[1].st_nlink != 1
            ):
                raise ValueError("draft transaction rollback identity is uncertain")
            remove_manifest()
            os.fsync(directory_fd)

        if cleanup_component is not None:
            _validate_draft_transaction_cleanup(
                root,
                draft_id,
                cleanup_component,
                components["canonical"],
                manifest=manifest,
                manifest_payload=manifest_payload,
            )
            if canonical_kind != "replacement" or any(
                components[name] is not None for name in ("replacement", "quarantine", "anchor")
            ):
                raise ValueError("draft transaction cleanup phase artifacts are inconsistent")
            if components["commit"] is not None:
                remove(
                    "commit",
                    commit_payload,
                    1024,
                    "draft transaction commit phase",
                )
            if components["swap"] is not None:
                remove(
                    "swap",
                    swap_payload,
                    1024,
                    "draft transaction swap phase",
                )
            remove_manifest()
            remove_cleanup()
            os.fsync(directory_fd)
            return

        if components["swap"] is None:
            if canonical_kind != "expected" or components["quarantine"] is not None:
                raise ValueError("draft transaction prepared phase is inconsistent")
            finish_rollback()
            return

        if canonical_kind == "expected":
            finish_rollback()
            return

        if canonical_kind is None:
            if components["replacement"] is not None:
                replacement = components["replacement"]
                current = os.stat(
                    component_paths["replacement"],
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                if not _same_inode(current, replacement[1]):
                    raise ValueError("draft transaction replacement changed before recovery")
                try:
                    os.link(
                        component_paths["replacement"],
                        filename,
                        src_dir_fd=directory_fd,
                        dst_dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                except FileExistsError as error:
                    raise ValueError(
                        "competing canonical draft preserved; recovery is uncertain"
                    ) from error
                canonical = _open_optional_transaction_component(
                    directory_fd,
                    filename,
                    MAX_DRAFT_BYTES,
                    "recovered canonical draft",
                )
                if canonical is None:
                    raise ValueError("replacement publication recovery failed")
                opened.append(canonical[0])
                if not _same_inode(canonical[1], replacement[1]) or canonical[2] != replacement[2]:
                    raise ValueError("replacement publication recovery is uncertain")
                components["canonical"] = canonical
                canonical_kind = "replacement"
                os.fsync(directory_fd)
            else:
                source_name = (
                    "quarantine"
                    if components["quarantine"] is not None
                    else "anchor"
                    if components["anchor"] is not None
                    else None
                )
                if source_name is None:
                    raise ValueError("draft transaction has no exact recovery artifact")
                source = components[source_name]
                try:
                    os.link(
                        component_paths[source_name],
                        filename,
                        src_dir_fd=directory_fd,
                        dst_dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                except FileExistsError as error:
                    raise ValueError(
                        "competing canonical draft preserved; recovery is uncertain"
                    ) from error
                restored = _open_optional_transaction_component(
                    directory_fd,
                    filename,
                    MAX_DRAFT_BYTES,
                    "restored canonical draft",
                )
                if restored is None or not _same_inode(restored[1], source[1]):
                    raise ValueError("canonical draft restoration is uncertain")
                opened.append(restored[0])
                components["canonical"] = restored
                canonical_kind = "expected"
                os.fsync(directory_fd)
                finish_rollback()
                return

        if canonical_kind != "replacement":
            raise ValueError("draft transaction canonical phase is invalid")
        canonical = components["canonical"]
        if replacement_payload is None:
            replacement_payload = canonical[2]
            _validate_transaction_draft_payload(
                replacement_payload,
                root,
                draft_id,
                "draft transaction replacement artifact",
            )
        if components["commit"] is None:
            commit_fd, commit_info = _write_private_transaction_component(
                directory_fd,
                names["commit"],
                commit_payload,
                "draft transaction commit phase",
            )
            opened.append(commit_fd)
            components["commit"] = (commit_fd, commit_info, commit_payload)
            os.fsync(directory_fd)
        for name, payload, maximum, label in (
            (
                "replacement",
                components["replacement"][2] if components["replacement"] is not None else b"",
                MAX_DRAFT_BYTES,
                "draft transaction replacement",
            ),
            (
                "quarantine",
                components["quarantine"][2] if components["quarantine"] is not None else b"",
                MAX_DRAFT_BYTES,
                "draft transaction quarantine",
            ),
            (
                "anchor",
                components["anchor"][2] if components["anchor"] is not None else b"",
                MAX_DRAFT_BYTES,
                "draft transaction expected anchor",
            ),
        ):
            if components[name] is not None:
                remove(name, payload, maximum, label)
        final_canonical = _open_optional_transaction_component(
            directory_fd,
            filename,
            MAX_DRAFT_BYTES,
            "committed canonical draft",
        )
        if final_canonical is None:
            raise ValueError("draft transaction commit lost canonical draft")
        opened.append(final_canonical[0])
        if (
            (final_canonical[1].st_dev, final_canonical[1].st_ino) != replacement_inode
            or hashlib.sha256(final_canonical[2]).hexdigest() != manifest["replacement_sha256"]
            or final_canonical[1].st_nlink != 1
        ):
            raise ValueError("draft transaction committed identity is uncertain")
        cleanup_payload = _draft_transaction_cleanup_payload(
            root, draft_id, manifest, manifest_payload
        )
        cleanup_fd, cleanup_info = _write_private_transaction_component(
            directory_fd,
            cleanup_name,
            cleanup_payload,
            "draft transaction cleanup phase",
        )
        opened.append(cleanup_fd)
        cleanup_component = (cleanup_fd, cleanup_info, cleanup_payload)
        cleanup_selected_name = cleanup_name
        os.fsync(directory_fd)
        remove("commit", commit_payload, 1024, "draft transaction commit phase")
        remove("swap", swap_payload, 1024, "draft transaction swap phase")
        remove_manifest()
        remove_cleanup()
        os.fsync(directory_fd)
    finally:
        for descriptor in reversed(opened):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _recover_private_draft_transaction(root: Path, draft_id: str) -> None:
    directory_fd = _private_draft_directory_fd(root)
    try:
        with _draft_transaction_lock(directory_fd):
            _recover_private_draft_transaction_at(root, draft_id, directory_fd)
    finally:
        os.close(directory_fd)


def _cas_replace_private_draft(
    root: Path,
    draft_id: str,
    expected: Mapping[str, object],
    replacement: Mapping[str, object],
) -> None:
    directory_fd = _private_draft_directory_fd(root)
    token = secrets.token_hex(16)
    filename = f"{draft_id}.json"
    temporary_name = f".{draft_id}.{token}.new"
    anchor_name = f".{draft_id}.{token}.anchor"
    quarantine_name = f".{draft_id}.{token}.quarantine"
    manifest_name = f".{draft_id}.transaction"
    swap_name = f".{draft_id}.{token}.swap"
    current_fd = temporary_fd = anchor_fd = quarantine_fd = None
    manifest_fd = swap_fd = None
    anchor_info = None
    transaction_durable = False
    try:
        with _draft_transaction_lock(directory_fd):
            _recover_private_draft_transaction_at(root, draft_id, directory_fd)
            read_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            current_fd = os.open(filename, read_flags, dir_fd=directory_fd)
            current_info = os.fstat(current_fd)
            expected_payload = _canonical_bytes(expected)
            replacement_payload = _canonical_bytes(replacement)
            if (
                not stat.S_ISREG(current_info.st_mode)
                or stat.S_IMODE(current_info.st_mode) != 0o600
                or current_info.st_nlink != 1
                or _read_bounded_descriptor(current_fd, MAX_DRAFT_BYTES, "trace transaction draft")
                != expected_payload
            ):
                raise ValueError("trace transaction changed before receipt binding")
            _validate_transaction_draft_payload(
                expected_payload, root, draft_id, "trace transaction expected"
            )
            _validate_transaction_draft_payload(
                replacement_payload,
                root,
                draft_id,
                "trace transaction replacement",
            )

            temporary_fd, temporary_info = _write_private_transaction_component(
                directory_fd,
                temporary_name,
                replacement_payload,
                "draft transaction replacement",
            )
            os.link(
                filename,
                anchor_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            anchor = _open_optional_transaction_component(
                directory_fd,
                anchor_name,
                MAX_DRAFT_BYTES,
                "draft transaction expected anchor",
            )
            if (
                anchor is None
                or not _same_inode(anchor[1], current_info)
                or anchor[2] != expected_payload
            ):
                raise ValueError("trace transaction changed before receipt binding")
            anchor_fd, anchor_info = anchor[0], anchor[1]
            manifest = {
                "schema_version": 1,
                "draft_id": draft_id,
                "repo_root_sha256": hashlib.sha256(str(root).encode("utf-8")).hexdigest(),
                "transaction_id": token,
                "expected_sha256": hashlib.sha256(expected_payload).hexdigest(),
                "expected_dev": current_info.st_dev,
                "expected_ino": current_info.st_ino,
                "replacement_sha256": hashlib.sha256(replacement_payload).hexdigest(),
                "replacement_dev": temporary_info.st_dev,
                "replacement_ino": temporary_info.st_ino,
            }
            manifest_payload = _canonical_bytes(manifest)
            manifest_fd, _ = _write_private_transaction_component(
                directory_fd,
                manifest_name,
                manifest_payload,
                "draft transaction manifest",
            )
            os.fsync(directory_fd)
            transaction_durable = True
            swap_payload = _draft_transaction_phase_payload(
                draft_id,
                token,
                "swap",
                hashlib.sha256(manifest_payload).hexdigest(),
            )
            swap_fd, _ = _write_private_transaction_component(
                directory_fd,
                swap_name,
                swap_payload,
                "draft transaction swap phase",
            )
            os.fsync(directory_fd)

            current_path_info = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
            if (
                not _same_inode(current_path_info, current_info)
                or _read_bounded_descriptor(current_fd, MAX_DRAFT_BYTES, "trace transaction draft")
                != expected_payload
            ):
                raise ValueError("trace transaction changed before receipt binding")
            _rename_noreplace(directory_fd, filename, quarantine_name)
            quarantine_fd = os.open(quarantine_name, read_flags, dir_fd=directory_fd)
            quarantine_info = os.fstat(quarantine_fd)
            if (
                not _same_inode(quarantine_info, current_info)
                or _read_bounded_descriptor(
                    quarantine_fd, MAX_DRAFT_BYTES, "trace transaction draft"
                )
                != expected_payload
            ):
                raise ValueError("trace transaction changed after durable quarantine")
            replacement_path_info = os.stat(
                temporary_name, dir_fd=directory_fd, follow_symlinks=False
            )
            if (
                not _same_inode(replacement_path_info, temporary_info)
                or _read_bounded_descriptor(
                    temporary_fd,
                    MAX_DRAFT_BYTES,
                    "draft transaction replacement",
                )
                != replacement_payload
            ):
                raise ValueError("draft transaction replacement changed")
            try:
                os.link(
                    temporary_name,
                    filename,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except FileExistsError as error:
                raise ValueError(
                    "competing trace transaction preserved; recovery is uncertain"
                ) from error
            published = _open_optional_transaction_component(
                directory_fd,
                filename,
                MAX_DRAFT_BYTES,
                "published transaction draft",
            )
            if (
                published is None
                or not _same_inode(published[1], temporary_info)
                or published[2] != replacement_payload
            ):
                raise ValueError("published transaction draft identity is uncertain")
            os.close(published[0])
            os.fsync(directory_fd)
            _recover_private_draft_transaction_at(root, draft_id, directory_fd)
            transaction_durable = False
    except OSError as error:
        raise ValueError(f"cannot compare-and-swap trace transaction: {error}") from error
    finally:
        cleanup_error = None
        if not transaction_durable:
            for name, descriptor, metadata, payload, label in (
                (
                    temporary_name,
                    temporary_fd,
                    temporary_info if temporary_fd is not None else None,
                    replacement_payload if temporary_fd is not None else b"",
                    "draft transaction replacement",
                ),
                (
                    anchor_name,
                    anchor_fd,
                    anchor_info,
                    expected_payload if anchor_fd is not None else b"",
                    "draft transaction expected anchor",
                ),
            ):
                if descriptor is None or metadata is None:
                    continue
                selected_name = name
                try:
                    os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except FileNotFoundError:
                    selected_name = _transaction_removing_name(name)
                    try:
                        os.stat(
                            selected_name,
                            dir_fd=directory_fd,
                            follow_symlinks=False,
                        )
                    except FileNotFoundError:
                        continue
                try:
                    _unlink_transaction_component(
                        directory_fd,
                        name,
                        (descriptor, metadata, payload),
                        payload,
                        MAX_DRAFT_BYTES,
                        label,
                        selected_name=selected_name,
                    )
                except (OSError, ValueError) as failure:
                    cleanup_error = failure
                    break
        for descriptor in (
            swap_fd,
            manifest_fd,
            quarantine_fd,
            anchor_fd,
            temporary_fd,
            current_fd,
        ):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        os.close(directory_fd)
        if cleanup_error is not None:
            raise ValueError(
                f"pre-manifest draft transaction cleanup is uncertain: {cleanup_error}"
            )


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
    # Admit paths and frontier entries only while their nodes fit the node
    # cap, so every delivered reference stays resolvable and the cap holds
    # even when deep paths alone would demand more nodes than the budget.
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
    """Shrink a compact delivery against its serialized byte budget.

    Actionable frontier entries out-rank paths. Nodes not referenced by a
    surviving path/frontier are removed first; then the lowest-priority path
    or frontier is dropped. Every removal is reflected in the disclosure.
    """
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


def _compact_graph(receipt: ReceiptPayload) -> CompactGraphPayload:
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


def _source_inventory_sha256(source_digests: Mapping[str, str]) -> str:
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
        _source_inventory_sha256(source_digests),
        complete,
        reason,
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
    identity = _graph_draft_identity(draft)
    identity["graph_trace_intent"] = {
        "intent_id": transaction["intent_id"],
        "source_inventory_sha256": transaction["source_inventory_sha256"],
        "source_inventory_complete": transaction["source_inventory_complete"],
        "source_inventory_reason": transaction["source_inventory_reason"],
    }
    return identity


def _trace_intent_sha256(intent: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_bytes(intent)).hexdigest()


def _new_trace_intent(
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
        "source_inventory_sha256": _source_inventory_sha256(source_inventory.digests),
        "source_inventory_complete": source_inventory.complete,
        "source_inventory_reason": source_inventory.reason,
    }
    intent["request_sha256"] = GRAPH_COORDINATOR._request_sha256(
        _graph_trace_draft_identity(draft, intent),
        seeds,
        GRAPH_COORDINATOR._settings(graph_settings),
    )
    return intent


def _validate_trace_intent(
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
) -> None:
    if _read_bound_receipt_bytes(root, draft_id) != expected_payload:
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
                component = _open_optional_transaction_component(
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
            _unlink_transaction_component(
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
            or not _same_inode(current, guard_info)
            or _read_bounded_descriptor(guard_fd, 1024, "stale cleanup namespace guard")
            != guard_payload
        ):
            return False
        try:
            _unlink_transaction_component(
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
            or _read_bounded_descriptor(
                receipt_fd, GRAPH.MAX_RECEIPT_BYTES, "stale cleanup receipt"
            )
            != expected_payload
        ):
            raise ValueError("stale cleanup target changed or is unsafe")

        _rename_noreplace(graph_fd, filename, quarantine_name)
        quarantined = True
        quarantine_fd = os.open(quarantine_name, read_flags, dir_fd=graph_fd)
        quarantine_info = os.fstat(quarantine_fd)
        if (quarantine_info.st_dev, quarantine_info.st_ino) != (
            receipt_info.st_dev,
            receipt_info.st_ino,
        ) or _read_bounded_descriptor(
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
        guard_fd, guard_info = _write_private_transaction_component(
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
        _unlink_transaction_component(
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
) -> bool:
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
        guard, guard_selected_name = _open_transaction_component_for_cleanup(
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
        if not isinstance(value, dict) or value.get("kind") != ("stale-receipt-cleanup-guard"):
            return False
        if (
            set(value) != _STALE_CLEANUP_GUARD_KEYS
            or value.get("schema_version") != 1
            or value.get("draft_id") != draft_id
            or value.get("repo_root_sha256")
            != hashlib.sha256(str(root).encode("utf-8")).hexdigest()
            or value.get("trace_intent_sha256") != _trace_intent_sha256(intent)
            or not isinstance(value.get("transaction_id"), str)
            or DRAFT_ID_PATTERN.fullmatch(value["transaction_id"]) is None
            or not isinstance(value.get("receipt_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", value["receipt_sha256"]) is None
            or _canonical_bytes(value) != guard[2]
            or guard[1].st_nlink != 1
        ):
            raise ValueError("stale cleanup namespace guard identity is invalid")
        quarantine_name = f".{draft_id}.{value['transaction_id']}.stale"
        quarantine, quarantine_selected_name = _open_transaction_component_for_cleanup(
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
            _unlink_transaction_component(
                graph_fd,
                quarantine_name,
                quarantine,
                quarantine[2],
                GRAPH.MAX_RECEIPT_BYTES,
                "stale cleanup recovery quarantine",
                selected_name=quarantine_selected_name,
            )
        _unlink_transaction_component(
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
    root: Path, draft: Mapping[str, object], intent: Mapping[str, object]
) -> dict[str, object]:
    current = load_draft(root, str(draft["draft_id"]))
    if current.get("graph_trace_intent") != intent:
        raise ValueError("trace intent changed before cleanup")
    updated = dict(current)
    updated.pop("graph_trace_intent", None)
    _cas_replace_private_draft(root, str(draft["draft_id"]), current, updated)
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


def _load_graph_context(
    root: Path,
    draft: Mapping[str, object],
    selected_receipt_id: str | None,
    *,
    deadline: DeadlineType | None = None,
) -> GraphContext:
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
    _validate_trace_intent(root, draft, tuple(seeds), graph_settings, intent)
    if binding.get("trace_intent_sha256") != _trace_intent_sha256(intent):
        raise ValueError("graph receipt trace intent digest is invalid")
    payload = _read_bound_receipt_bytes(root, str(draft["draft_id"]))
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
        source_inventory_sha256,
        source_inventory_complete,
        source_inventory_reason,
    ) = _receipt_source_inventory(root, receipt)
    if (
        binding.get("cache_key") != cache_key
        or binding.get("source_inventory_sha256") != source_inventory_sha256
        or binding.get("source_inventory_complete") != source_inventory_complete
        or binding.get("source_inventory_reason") != source_inventory_reason
    ):
        raise ValueError("graph source inventory cache does not match binding")
    _verify_receipt_sources(root, receipt)
    _verify_source_inventory(
        root,
        graph_settings,
        source_digests,
        source_inventory_complete,
        source_inventory_reason,
        receipt,
        deadline=deadline,
    )
    return {"receipt": receipt, "sha256": digest, "binding": binding}


def _load_promoted_scan_context(
    root: Path, draft: Mapping[str, object], selected_receipt_id: str | None
) -> GraphContext:
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


def _validate_graph_coverage(analysis: Mapping[str, object], context: GraphContext) -> None:
    receipt = context["receipt"]
    nodes = {row["id"]: row for row in receipt["nodes"]}
    edges = {row["id"]: row for row in receipt["edges"]}
    paths = {row["id"]: row for row in receipt["paths"]}
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
            rationales[impact_key] = rationale
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
        rationales[impact_key] = rationale
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
):
    stored = _read_bound_receipt_bytes(root, str(draft["draft_id"]))
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
    inventory = _receipt_source_inventory(root, receipt_value)
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
    source_inventory_sha256: str,
    source_inventory_complete: bool,
    source_inventory_reason: str | None,
) -> TraceResult:
    updated = dict(draft)
    digest = hashlib.sha256(stored).hexdigest()
    updated.pop("graph_trace_intent", None)
    updated["graph_receipt"] = {
        "receipt_id": receipt_value["receipt_id"],
        "sha256": digest,
        "request_sha256": expected_request_sha256,
        "settings": graph_settings,
        "cache_key": cache_key,
        "source_inventory_sha256": source_inventory_sha256,
        "source_inventory_complete": source_inventory_complete,
        "source_inventory_reason": source_inventory_reason,
        "trace_intent_id": intent["intent_id"],
        "trace_intent_sha256": _trace_intent_sha256(intent),
        "seeds": [{"term": seed.term, "location": seed.location} for seed in normalized_seeds],
    }
    _cas_replace_private_draft(root, str(draft["draft_id"]), draft, updated)
    receipt_path = root / ".requirements-impact-refiner" / "graph" / f"{draft['draft_id']}.json"
    return TraceResult(
        receipt_id=str(receipt_value["receipt_id"]),
        receipt_path=receipt_path,
        receipt_sha256=digest,
        compact_graph=_compact_graph(receipt_value),
        budget_status=str(receipt_value["budget_status"]),
        request_sha256=expected_request_sha256,
        seeds=normalized_seeds,
    )


def trace_impact(request: TraceRequest) -> TraceResult:
    original_root = Path(request.repo_root)
    if original_root.is_symlink():
        raise ValueError("repository root symlink is unsafe for graph tracing")
    root = _root(original_root)
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
    _bounded(
        {"seeds": [{"term": seed.term, "location": seed.location} for seed in normalized_seeds]},
        MAX_TRACE_BYTES,
        "trace input",
    )
    if DRAFT_ID_PATTERN.fullmatch(request.draft_id) is None:
        raise ValueError("invalid draft ID")
    _recover_private_draft_transaction(root, request.draft_id)
    draft = load_draft(root, request.draft_id)
    settings = draft.get("settings")
    graph_settings = settings.get("impact_graph") if isinstance(settings, dict) else None
    if not isinstance(graph_settings, dict):
        raise ValueError("draft graph settings are invalid")
    if graph_settings.get("enabled") is not True:
        raise ValueError("impact graph is disabled for this draft")
    deadline = GRAPH_COORDINATOR.Deadline(time, _int_value(graph_settings["max_seconds"]))
    receipt_path = root / ".requirements-impact-refiner" / "graph" / f"{request.draft_id}.json"
    with _report_lock(root, str(draft["report_id"]), deadline=deadline):
        _recover_private_draft_transaction(root, request.draft_id)
        draft = load_draft(root, request.draft_id)
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
            context = _load_graph_context(root, draft, binding.get("receipt_id"), deadline=deadline)
            receipt_value = context["receipt"]
            return TraceResult(
                receipt_id=str(receipt_value["receipt_id"]),
                receipt_path=receipt_path,
                receipt_sha256=str(context["sha256"]),
                compact_graph=_compact_graph(receipt_value),
                budget_status=str(receipt_value["budget_status"]),
                request_sha256=str(binding["request_sha256"]),
                seeds=normalized_seeds,
            )
        intent = draft.get("graph_trace_intent")
        if intent is not None:
            intent = _validate_trace_intent(root, draft, normalized_seeds, graph_settings, intent)
            _recover_stale_cleanup_guard(root, request.draft_id, intent)
        receipt_exists = receipt_path.exists() or receipt_path.is_symlink()
        source_inventory = None
        if intent is None:
            if receipt_exists:
                raise ValueError("graph receipt has no durable pre-publication trace intent")
            source_inventory = GRAPH_COORDINATOR._collect_source_digests(root, deadline)
            intent = _new_trace_intent(
                root, draft, normalized_seeds, graph_settings, source_inventory
            )
            updated = dict(draft)
            updated["graph_trace_intent"] = intent
            _cas_replace_private_draft(root, request.draft_id, draft, updated)
            draft = updated
        if receipt_exists:
            validated = _validate_persisted_trace_receipt(
                root, draft, normalized_seeds, graph_settings, intent
            )
            try:
                _verify_source_inventory(
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
                _remove_exact_trace_receipt(
                    root,
                    request.draft_id,
                    validated[1],
                    commit=lambda: _clear_trace_intent(root, draft, intent),
                    guard_intent_sha256=_trace_intent_sha256(intent),
                )
                raise
            return _bind_trace_receipt(
                root, draft, normalized_seeds, graph_settings, intent, *validated
            )
        if source_inventory is None:
            source_inventory = GRAPH_COORDINATOR._collect_source_digests(root, deadline)
            if (
                _source_inventory_sha256(source_inventory.digests)
                != intent["source_inventory_sha256"]
                or source_inventory.complete != intent["source_inventory_complete"]
                or source_inventory.reason != intent["source_inventory_reason"]
            ):
                _clear_trace_intent(root, draft, intent)
                raise ValueError("trace intent source inventory is stale")
        graph_draft = _graph_trace_draft_identity(draft, intent)
        receipt = GRAPH_COORDINATOR.trace_impact(
            root,
            graph_draft,
            normalized_seeds,
            graph_settings,
            clock=time,
            deadline=deadline,
            source_inventory=source_inventory,
        )
        payload = GRAPH.canonical_receipt_bytes(receipt)
        if not receipt_path.is_file() or receipt_path.is_symlink():
            raise ValueError("graph receipt publication failed")
        validated = _validate_persisted_trace_receipt(
            root, draft, normalized_seeds, graph_settings, intent, payload
        )
        return _bind_trace_receipt(
            root, draft, normalized_seeds, graph_settings, intent, *validated
        )


def _check_keys(label: str, value: object, expected: set[str]) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise ValueError(f"unknown {label} key {unknown[0]}")
    if missing:
        raise ValueError(f"missing {label} key {missing[0]}")


def _local_key(value: object, label: str) -> str:
    if not isinstance(value, str) or LOCAL_KEY_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid {label} local key")
    return value


def _validate_analysis(analysis: Mapping[str, object]) -> None:
    _check_keys("analysis", analysis, ANALYSIS_KEYS)
    if analysis["phase"] not in {"pre-decision", "post-decision"}:
        raise ValueError("invalid analysis phase")
    if (
        not isinstance(analysis["refined_requirement"], str)
        or not analysis["refined_requirement"].strip()
    ):
        raise ValueError("refined_requirement must be nonempty")
    for section, expected in ROW_KEYS.items():
        rows = analysis[section]
        if not isinstance(rows, list):
            raise ValueError(f"{section} must be an array")
        if len(rows) > 128:
            raise ValueError(f"{section} has too many rows")
        keys = []
        for row in rows:
            if section == "impacts":
                if not isinstance(row, dict):
                    raise ValueError("impact must be an object")
                unknown = sorted(set(row) - expected - IMPACT_OPTIONAL_KEYS)
                missing = sorted(expected - set(row))
                if unknown:
                    raise ValueError(f"unknown impact key {unknown[0]}")
                if missing:
                    raise ValueError(f"missing impact key {missing[0]}")
            else:
                _check_keys(section[:-1], row, expected)
            if "key" in row:
                keys.append(_local_key(row["key"], section[:-1]))
            if section == "impacts":
                _check_keys("impact summary", row["summary"], SUMMARY_KEYS)
                for name in ("invariant_keys", "decision_keys", "criterion_keys"):
                    if not isinstance(row[name], list) or len(row[name]) > 128:
                        raise ValueError(f"impact {name} has too many items")
            if section == "decisions" and (
                not isinstance(row["accepted_impact_keys"], list)
                or len(row["accepted_impact_keys"]) > 128
            ):
                raise ValueError("decision accepted_impact_keys has too many items")
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate {section} local key")
    if analysis["phase"] == "pre-decision":
        decision_needed = analysis["decision_needed"]
        if not isinstance(decision_needed, dict):
            raise ValueError("decision_needed must be an object")
        _check_keys("decision_needed", decision_needed, {"question", "options"})
        options = decision_needed["options"]
        if not isinstance(options, list) or not 2 <= len(options) <= 3:
            raise ValueError("decision_needed requires two or three options")
        for option in options:
            _check_keys("decision option", option, {"option", "impact_keys", "tradeoff"})
            if not isinstance(option["impact_keys"], list) or len(option["impact_keys"]) > 128:
                raise ValueError("decision option impact_keys has too many items")
        if analysis["decisions"]:
            raise ValueError("pre-decision analysis forbids decisions")
    else:
        if analysis["decision_needed"] is not None or not analysis["decisions"]:
            raise ValueError("post-decision analysis requires decisions only")
    if not isinstance(analysis["scope"], list) or not analysis["scope"]:
        raise ValueError("scope requires at least one row")
    if not isinstance(analysis["workflow"], str) or not analysis["workflow"].strip():
        raise ValueError("workflow must be nonempty")


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


def _consume(path: Path, draft: dict[str, object], published, key_map) -> None:
    updated = dict(draft)
    updated["consumed"] = True
    updated["published"] = {
        "report_id": published.report_id,
        "revision": published.revision,
        "markdown_sha256": published.markdown_sha256,
    }
    updated["key_map"] = key_map
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=".draft-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(_canonical_bytes(updated))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError as error:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ValueError(f"cannot consume draft: {error}") from error


@contextmanager
def _report_lock(root: Path, report_id: str, deadline=None):
    report_dir = report_store.report_directory(root, report_id, create=True)
    lock_path = report_dir / ".controller.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise ValueError(f"cannot open controller lock: {error}") from error
    locked = False
    try:
        if fcntl is not None:
            if deadline is None:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                locked = True
            else:
                while True:
                    if deadline.expired():
                        raise ValueError(
                            "graph trace deadline exhausted waiting for controller lock"
                        )
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        locked = True
                        break
                    except BlockingIOError:
                        time.sleep(min(0.01, deadline.remaining()))
        if deadline is not None and deadline.expired():
            raise ValueError("graph trace deadline exhausted waiting for controller lock")
        yield
    finally:
        if fcntl is not None and locked:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _write_controller_metadata(
    root: Path,
    draft: Mapping[str, object],
    state_bytes: bytes,
    key_map: Mapping[str, object],
    graph_receipt: Mapping[str, object] | None = None,
) -> None:
    revision_value = _int_value(draft["revision"])
    path = _controller_metadata_path(str(draft["report_id"]), revision_value, root)
    metadata = {
        "schema_version": 1,
        "draft_id": draft["draft_id"],
        "report_id": draft["report_id"],
        "revision": draft["revision"],
        "state_sha256": hashlib.sha256(state_bytes).hexdigest(),
        "key_map": key_map,
    }
    if graph_receipt is not None:
        metadata["graph_receipt"] = dict(graph_receipt)
    payload = _canonical_bytes(metadata)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=f".{path.name}-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    except FileExistsError:
        try:
            existing_bytes = path.read_bytes() if not path.is_symlink() else b""
            if existing_bytes != payload:
                existing = json.loads(existing_bytes.decode("utf-8", errors="strict"))
                same_draft = (
                    isinstance(existing, dict)
                    and existing.get("draft_id") == draft["draft_id"]
                    and existing.get("report_id") == draft["report_id"]
                    and existing.get("revision") == draft["revision"]
                )
                report_dir = path.parent
                revision = revision_value
                artifacts_exist = any(
                    (report_dir / f"revision-{revision:04d}.{suffix}").exists()
                    for suffix in ("json", "md")
                )
                current = report_store.load_current(root, str(draft["report_id"]))
                if (
                    not same_draft
                    or artifacts_exist
                    or (current is not None and current.revision >= revision)
                ):
                    raise ValueError("controller revision belongs to another draft")
                if temporary is None:
                    raise ValueError("controller revision temporary is unavailable")
                os.replace(temporary, path)
                temporary = None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"cannot verify controller lineage: {error}") from error
    except OSError as error:
        raise ValueError(f"cannot write controller lineage: {error}") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


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
