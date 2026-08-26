#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import inspect
import json
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Callable, Protocol, TypedDict, cast

if TYPE_CHECKING:
    from typing_extensions import TypeGuard


class _PayloadIdentityContract(Protocol):
    def payload_sha256(self, plugin_root: Path) -> str: ...


class _PreviousLookupRequestFactory(Protocol):
    def __call__(
        self,
        repo_root: Path,
        request: str,
        repository_evidence: tuple[str, ...],
    ) -> object: ...


class _BeginRequestFactory(Protocol):
    def __call__(
        self,
        *,
        repo_root: Path,
        request: str,
        repository_evidence: tuple[str, ...],
        adapter: str,
        audience_override: str | None,
        delivery_override: str | None,
        scan_id: str | None,
    ) -> object: ...


class _FinalizeRequestFactory(Protocol):
    def __call__(
        self,
        *,
        repo_root: Path,
        draft_id: str,
        analysis: Mapping[str, object],
        graph_receipt_id: str | None,
    ) -> object: ...


class _ScanRequestFactory(Protocol):
    def __call__(
        self,
        repo_root: Path,
        change_request: str,
        evidence: tuple[str, ...],
        audience_override: str | None,
    ) -> object: ...


class _TraceSeedFactory(Protocol):
    def __call__(self, term: str, location: str | None) -> object: ...


class _TraceRequestFactory(Protocol):
    def __call__(self, *, repo_root: Path, draft_id: str, seeds: tuple[object, ...]) -> object: ...


class _ControllerContract(Protocol):
    ADAPTERS: set[str]
    BeginRequest: _BeginRequestFactory
    FinalizeRequest: _FinalizeRequestFactory
    PreviousLookupRequest: _PreviousLookupRequestFactory
    PreviousReportResult: type
    ScanRequest: _ScanRequestFactory
    TraceRequest: _TraceRequestFactory
    TraceSeed: _TraceSeedFactory

    def begin_refinement(self, request: object) -> object: ...

    def finalize_refinement(self, request: object) -> object: ...

    def lookup_previous(self, request: object) -> object: ...

    def scan_impact(self, request: object) -> object: ...

    def trace_impact(self, request: object) -> object: ...


class _PriorImpact(TypedDict):
    id: str
    requirement: str
    category: str
    severity: str
    state: str
    evidence_level: str
    evidence: str
    invariants: list[str]
    decisions: list[str]
    criteria: list[str]


class _PriorDecision(TypedDict):
    id: str
    choice: str
    requirement: str
    accepted_impacts: list[str]
    rationale: str


class _PriorSummary(TypedDict):
    impact_id: str
    changed_feature: str
    possible_issue: str
    affected: str
    trigger: str
    severity: str
    prevention: str
    status: str


class _PriorState(TypedDict):
    impacts: list[_PriorImpact]
    decisions: list[_PriorDecision]
    summary: list[_PriorSummary]


class _PriorKeyMap(TypedDict):
    invariants: dict[str, str]
    impacts: dict[str, str]
    decisions: dict[str, str]
    criteria: dict[str, str]


class _BeginResult(Protocol):
    draft_id: str
    draft_path: Path
    report_id: str
    revision: int
    previous_sha256: str
    settings: Mapping[str, object]
    prior_state: _PriorState | None
    prior_key_map: _PriorKeyMap | None
    scan_id: str | None
    graph_receipt_id: str | None


class _FinalizeResult(Protocol):
    status: str
    report_id: str
    revision: int
    delivery: str
    display_text: str
    state_path: Path
    markdown_path: Path
    markdown_sha256: str


class _PreviousResult(Protocol):
    status: str
    report_id: str | None
    revision: int | None
    markdown_sha256: str | None
    created_at: str | None
    baseline_commit: str | None
    changed_paths: tuple[str, ...]
    changed_count: int | None
    requirement_sha256: str
    source_inventory_sha256: str | None
    display_text: str | None
    reason: str
    elapsed_ms: int


class _ScanResult(Protocol):
    status: str
    scan_id: str
    receipt_id: str
    receipt_sha256: str
    display_text: str
    risk_level: str
    paths: Sequence[Mapping[str, object]]
    frontier: Sequence[Mapping[str, object]]
    candidates: Sequence[Mapping[str, object]]
    elapsed_ms: int
    cache_status: str
    can_promote: bool


class _TraceSeedResult(Protocol):
    term: str
    location: str | None


class _TraceResult(Protocol):
    receipt_id: str
    receipt_path: Path
    receipt_sha256: str
    compact_graph: Mapping[str, object]
    budget_status: str
    request_sha256: str
    seeds: Sequence[_TraceSeedResult]


class _ControllerContractError(RuntimeError):
    """A validated MCP request received an invalid controller sibling result."""


def _repository_result_path(repo_root: str, result_path: Path) -> str:
    """Return a resolved repository-relative artifact path or fail closed."""
    if ".." in result_path.parts:
        raise _ControllerContractError("controller result path contract is invalid")
    try:
        root = Path(repo_root).resolve(strict=True)
        if not root.is_dir():
            raise OSError("repository root is not a directory")
        candidate = result_path if result_path.is_absolute() else root / result_path
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root)
        if not resolved.is_file():
            raise OSError("controller result is not a regular file")
    except (OSError, RuntimeError, ValueError) as error:
        raise _ControllerContractError("controller result path contract is invalid") from error
    return relative.as_posix()


def _callables(value: object, names: tuple[str, ...]) -> bool:
    return all(callable(getattr(value, name, None)) for name in names)


def _has_parameters(value: object, names: tuple[str, ...]) -> bool:
    if not callable(value):
        return False
    try:
        return tuple(inspect.signature(value).parameters) == names
    except (TypeError, ValueError):
        return False


def _is_payload_identity_contract(value: object) -> bool:
    return _has_parameters(getattr(value, "payload_sha256", None), ("plugin_root",))


def _is_controller_contract(value: object) -> bool:
    adapters = getattr(value, "ADAPTERS", None)
    return (
        isinstance(adapters, set)
        and all(isinstance(adapter, str) for adapter in adapters)
        and _callables(
            value,
            (
                "BeginRequest",
                "FinalizeRequest",
                "PreviousLookupRequest",
                "PreviousReportResult",
                "ScanRequest",
                "TraceRequest",
                "TraceSeed",
                "begin_refinement",
                "finalize_refinement",
                "lookup_previous",
                "scan_impact",
                "trace_impact",
            ),
        )
        and _has_parameters(
            getattr(value, "BeginRequest", None),
            (
                "repo_root",
                "request",
                "repository_evidence",
                "adapter",
                "audience_override",
                "delivery_override",
                "scan_id",
            ),
        )
        and _has_parameters(
            getattr(value, "FinalizeRequest", None),
            ("repo_root", "draft_id", "analysis", "graph_receipt_id"),
        )
        and _has_parameters(
            getattr(value, "PreviousLookupRequest", None),
            ("repo_root", "request", "repository_evidence"),
        )
        and _has_parameters(
            getattr(value, "ScanRequest", None),
            ("repo_root", "change_request", "evidence", "audience_override"),
        )
        and _has_parameters(
            getattr(value, "TraceRequest", None), ("repo_root", "draft_id", "seeds")
        )
        and _has_parameters(getattr(value, "TraceSeed", None), ("term", "location"))
        and all(
            _has_parameters(getattr(value, name, None), ("request",))
            for name in (
                "begin_refinement",
                "finalize_refinement",
                "lookup_previous",
                "scan_impact",
                "trace_impact",
            )
        )
    )


SCRIPT_DIR = Path(__file__).resolve().parent


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


def _load_local_sibling(
    filename: str,
    canonical_name: str,
    prefix: str,
    validator: Callable[[object], bool],
    label: str,
) -> object:
    expected = _regular_module_path(SCRIPT_DIR / filename)
    if expected is None or expected != SCRIPT_DIR / filename:
        raise ImportError(f"{label} sibling is unsafe")
    canonical = sys.modules.get(canonical_name)
    if _module_uses_sibling(canonical, expected):
        if not validator(canonical):
            raise ImportError(f"{label} sibling contract is incomplete")
        return canonical
    module_name = prefix + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    existing = sys.modules.get(module_name)
    if existing is not None:
        if not _module_uses_sibling(existing, expected):
            raise ImportError(f"{label} sibling is unsafe")
        if not validator(existing):
            raise ImportError(f"{label} sibling contract is incomplete")
        return existing
    specification = importlib.util.spec_from_file_location(module_name, expected)
    if specification is None or specification.loader is None:
        raise ImportError(f"cannot load fixed {label} sibling")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError(f"cannot load fixed {label} sibling") from error
    if not validator(module):
        sys.modules.pop(module_name, None)
        raise ImportError(f"{label} sibling contract is incomplete")
    return module


payload_identity: _PayloadIdentityContract
rir_controller: _ControllerContract


def _json_depth(text: str) -> int:
    """Peak bracket nesting outside strings. CPython 3.13 no longer raises
    RecursionError from json.loads at hostile depths, so the bound must be
    explicit rather than borrowed from the interpreter."""
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
            if depth > peak:
                peak = depth
        elif char in "]}":
            depth = max(0, depth - 1)
    return peak


_MAX_JSON_DEPTH = 64
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

_installed_payload_sha256: str
if not TYPE_CHECKING:
    _loaded_payload_identity = _load_local_sibling(
        "payload_identity.py",
        "payload_identity",
        "_rir_mcp_payload_identity_",
        _is_payload_identity_contract,
        "payload identity",
    )
    payload_identity = cast(_PayloadIdentityContract, _loaded_payload_identity)
    _installed_payload_sha256 = payload_identity.payload_sha256(SCRIPT_DIR.parent)
    if (
        not isinstance(_installed_payload_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", _installed_payload_sha256) is None
    ):
        raise ImportError("payload identity sibling result contract is incomplete")
    _loaded_controller = _load_local_sibling(
        "rir_controller.py",
        "rir_controller",
        "_rir_mcp_controller_",
        _is_controller_contract,
        "controller",
    )
    rir_controller = cast(_ControllerContract, _loaded_controller)

MAX_LINE_BYTES = 2 * 1024 * 1024
PROTOCOL_VERSION = "2025-06-18"
_analysis_schema: object = json.loads(
    (SCRIPT_DIR.parent / "schemas" / "controller-analysis.schema.json").read_text(encoding="utf-8")
)
if not isinstance(_analysis_schema, dict):
    raise ValueError("controller analysis schema must contain an object")
ANALYSIS_SCHEMA: dict[str, object] = _analysis_schema
INSTALLED_PAYLOAD_SHA256 = _installed_payload_sha256


class _OptionalScanArguments(TypedDict, total=False):
    evidence: list[str]
    presentation: str


class ScanArguments(_OptionalScanArguments):
    repo_root: str
    change_request: str


class PreviousArguments(TypedDict):
    repo_root: str
    request: str
    repository_evidence: list[str]


class _OptionalBeginArguments(TypedDict, total=False):
    audience_override: str | None
    delivery_override: str | None
    scan_id: str | None


class BeginArguments(_OptionalBeginArguments):
    repo_root: str
    request: str
    repository_evidence: list[str]
    adapter: str


class TraceSeedArguments(TypedDict):
    term: str
    location: str | None


class TraceArguments(TypedDict):
    repo_root: str
    draft_id: str
    seeds: list[TraceSeedArguments]


class _OptionalFinalizeArguments(TypedDict, total=False):
    graph_receipt_id: str


class FinalizeArguments(_OptionalFinalizeArguments):
    repo_root: str
    draft_id: str
    analysis: dict[str, object]


def _is_string_list(value: object) -> TypeGuard[list[str]]:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_optional_string(value: object) -> TypeGuard[str | None]:
    return value is None or isinstance(value, str)


def _exact_keys(
    value: object, required: frozenset[str], optional: frozenset[str] = frozenset()
) -> bool:
    return isinstance(value, dict) and required <= set(value) and set(value) <= required | optional


def _is_scan_arguments(value: object) -> TypeGuard[ScanArguments]:
    required = frozenset({"repo_root", "change_request"})
    optional = frozenset({"evidence", "presentation"})
    return (
        _exact_keys(value, required, optional)
        and isinstance(value, dict)
        and isinstance(value.get("repo_root"), str)
        and isinstance(value.get("change_request"), str)
        and _is_string_list(value.get("evidence", []))
        and _is_optional_string(value.get("presentation"))
    )


def _is_previous_arguments(value: object) -> TypeGuard[PreviousArguments]:
    required = frozenset({"repo_root", "request", "repository_evidence"})
    return (
        _exact_keys(value, required)
        and isinstance(value, dict)
        and isinstance(value.get("repo_root"), str)
        and isinstance(value.get("request"), str)
        and _is_string_list(value.get("repository_evidence"))
    )


def _is_begin_arguments(value: object) -> TypeGuard[BeginArguments]:
    required = frozenset({"repo_root", "request", "repository_evidence", "adapter"})
    optional = frozenset({"audience_override", "delivery_override", "scan_id"})
    return (
        _exact_keys(value, required, optional)
        and isinstance(value, dict)
        and isinstance(value.get("repo_root"), str)
        and isinstance(value.get("request"), str)
        and _is_string_list(value.get("repository_evidence"))
        and isinstance(value.get("adapter"), str)
        and _is_optional_string(value.get("audience_override"))
        and _is_optional_string(value.get("delivery_override"))
        and _is_optional_string(value.get("scan_id"))
    )


def _is_trace_seed(value: object) -> TypeGuard[TraceSeedArguments]:
    return (
        _exact_keys(value, frozenset({"term", "location"}))
        and isinstance(value, dict)
        and isinstance(value.get("term"), str)
        and _is_optional_string(value.get("location"))
    )


def _is_trace_arguments(value: object) -> TypeGuard[TraceArguments]:
    seeds = value.get("seeds") if isinstance(value, dict) else None
    return (
        _exact_keys(value, frozenset({"repo_root", "draft_id", "seeds"}))
        and isinstance(value, dict)
        and isinstance(value.get("repo_root"), str)
        and isinstance(value.get("draft_id"), str)
        and isinstance(seeds, list)
        and all(_is_trace_seed(seed) for seed in seeds)
    )


def _is_finalize_arguments(value: object) -> TypeGuard[FinalizeArguments]:
    required = frozenset({"repo_root", "draft_id", "analysis"})
    optional = frozenset({"graph_receipt_id"})
    return (
        _exact_keys(value, required, optional)
        and isinstance(value, dict)
        and isinstance(value.get("repo_root"), str)
        and isinstance(value.get("draft_id"), str)
        and isinstance(value.get("analysis"), dict)
        and _is_optional_string(value.get("graph_receipt_id"))
    )


def _is_json_value(value: object, depth: int = 0) -> bool:
    if depth > _MAX_JSON_DEPTH:
        return False
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item, depth + 1) for item in value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _is_json_value(item, depth + 1) for key, item in value.items()
        )
    return False


def _is_string_mapping(value: object) -> TypeGuard[dict[str, str]]:
    return isinstance(value, dict) and all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    )


def _is_prior_key_map(value: object) -> TypeGuard[_PriorKeyMap]:
    return (
        _exact_keys(value, frozenset({"invariants", "impacts", "decisions", "criteria"}))
        and isinstance(value, dict)
        and all(
            _is_string_mapping(value[name])
            for name in ("invariants", "impacts", "decisions", "criteria")
        )
    )


def _is_prior_impact(value: object) -> TypeGuard[_PriorImpact]:
    string_fields = (
        "id",
        "requirement",
        "category",
        "severity",
        "state",
        "evidence_level",
        "evidence",
    )
    list_fields = ("invariants", "decisions", "criteria")
    return (
        _exact_keys(value, frozenset({*string_fields, *list_fields}))
        and isinstance(value, dict)
        and all(isinstance(value[name], str) for name in string_fields)
        and all(_is_string_list(value[name]) for name in list_fields)
    )


def _is_prior_decision(value: object) -> TypeGuard[_PriorDecision]:
    string_fields = ("id", "choice", "requirement", "rationale")
    return (
        _exact_keys(value, frozenset({*string_fields, "accepted_impacts"}))
        and isinstance(value, dict)
        and all(isinstance(value[name], str) for name in string_fields)
        and _is_string_list(value["accepted_impacts"])
    )


def _is_prior_summary(value: object) -> TypeGuard[_PriorSummary]:
    fields = (
        "impact_id",
        "changed_feature",
        "possible_issue",
        "affected",
        "trigger",
        "severity",
        "prevention",
        "status",
    )
    return (
        _exact_keys(value, frozenset(fields))
        and isinstance(value, dict)
        and all(isinstance(value[name], str) for name in fields)
    )


def _is_prior_state(value: object) -> TypeGuard[_PriorState]:
    return (
        isinstance(value, dict)
        and _is_json_value(value)
        and isinstance(value.get("impacts"), list)
        and all(_is_prior_impact(row) for row in value["impacts"])
        and isinstance(value.get("decisions"), list)
        and all(_is_prior_decision(row) for row in value["decisions"])
        and isinstance(value.get("summary"), list)
        and all(_is_prior_summary(row) for row in value["summary"])
    )


def _is_begin_result(value: object) -> TypeGuard[_BeginResult]:
    revision = getattr(value, "revision", None)
    return (
        isinstance(getattr(value, "draft_id", None), str)
        and isinstance(getattr(value, "draft_path", None), Path)
        and isinstance(getattr(value, "report_id", None), str)
        and isinstance(revision, int)
        and not isinstance(revision, bool)
        and isinstance(getattr(value, "previous_sha256", None), str)
        and _string_key_mapping(getattr(value, "settings", None))
        and _is_json_value(getattr(value, "settings", None))
        and all(
            hasattr(value, name)
            for name in ("prior_state", "prior_key_map", "scan_id", "graph_receipt_id")
        )
        and (
            getattr(value, "prior_state", None) is None
            or _is_prior_state(getattr(value, "prior_state", None))
        )
        and (
            getattr(value, "prior_key_map", None) is None
            or _is_prior_key_map(getattr(value, "prior_key_map", None))
        )
        and _is_optional_string(getattr(value, "scan_id", None))
        and _is_optional_string(getattr(value, "graph_receipt_id", None))
    )


def _is_finalize_result(value: object) -> TypeGuard[_FinalizeResult]:
    revision = getattr(value, "revision", None)
    return (
        all(
            isinstance(getattr(value, name, None), str)
            for name in (
                "status",
                "report_id",
                "delivery",
                "display_text",
                "markdown_sha256",
            )
        )
        and isinstance(revision, int)
        and not isinstance(revision, bool)
        and isinstance(getattr(value, "state_path", None), Path)
        and isinstance(getattr(value, "markdown_path", None), Path)
    )


_PREVIOUS_REPORT_ID = re.compile(r"RPT-\d{3}")
_PREVIOUS_SHA256 = re.compile(r"[0-9a-f]{64}")
_PREVIOUS_COMMIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_PREVIOUS_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z")
MAX_PREVIOUS_CHANGED_PATHS = 4096
MAX_PREVIOUS_CHANGED_PATH_BYTES = 4096
MAX_PREVIOUS_CHANGED_TOTAL_BYTES = 256 * 1024
MAX_PREVIOUS_DISPLAY_BYTES = 256 * 1024
MAX_PREVIOUS_REASON_BYTES = 4096
MAX_PREVIOUS_ELAPSED_MS = 60_000


def _bounded_utf8(value: object, maximum: int, *, nonblank: bool = False) -> bool:
    if not isinstance(value, str) or (nonblank and not value.strip()):
        return False
    try:
        return len(value.encode("utf-8")) <= maximum
    except UnicodeEncodeError:
        return False


def _safe_previous_changed_path(value: object) -> bool:
    if not _bounded_utf8(value, MAX_PREVIOUS_CHANGED_PATH_BYTES, nonblank=True):
        return False
    assert isinstance(value, str)
    if "\\" in value or "\x00" in value:
        return False
    pure = PurePosixPath(value)
    return (
        not pure.is_absolute()
        and value == pure.as_posix()
        and all(part not in {"", ".", ".."} for part in pure.parts)
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _is_previous_result(value: object) -> TypeGuard[_PreviousResult]:
    status = getattr(value, "status", None)
    report_id = getattr(value, "report_id", None)
    revision = getattr(value, "revision", None)
    markdown_sha256 = getattr(value, "markdown_sha256", None)
    created_at = getattr(value, "created_at", None)
    baseline_commit = getattr(value, "baseline_commit", None)
    changed_paths = getattr(value, "changed_paths", None)
    changed_count = getattr(value, "changed_count", None)
    requirement_sha256 = getattr(value, "requirement_sha256", None)
    source_inventory_sha256 = getattr(value, "source_inventory_sha256", None)
    display_text = getattr(value, "display_text", None)
    reason = getattr(value, "reason", None)
    elapsed_ms = getattr(value, "elapsed_ms", None)
    if (
        status not in {"none", "fresh", "stale", "ambiguous"}
        or not isinstance(requirement_sha256, str)
        or _PREVIOUS_SHA256.fullmatch(requirement_sha256) is None
        or not _bounded_utf8(reason, MAX_PREVIOUS_REASON_BYTES, nonblank=True)
        or type(elapsed_ms) is not int
        or not 0 <= elapsed_ms <= MAX_PREVIOUS_ELAPSED_MS
        or not isinstance(changed_paths, tuple)
        or len(changed_paths) > MAX_PREVIOUS_CHANGED_PATHS
        or not all(isinstance(path, str) for path in changed_paths)
        or tuple(sorted(set(changed_paths))) != changed_paths
        or not all(_safe_previous_changed_path(path) for path in changed_paths)
    ):
        return False
    try:
        changed_path_bytes = sum(len(path.encode("utf-8")) for path in changed_paths)
    except UnicodeEncodeError:
        return False
    if changed_path_bytes > MAX_PREVIOUS_CHANGED_TOTAL_BYTES:
        return False
    if status in {"none", "ambiguous"}:
        return (
            all(
                item is None
                for item in (
                    report_id,
                    revision,
                    markdown_sha256,
                    created_at,
                    baseline_commit,
                    source_inventory_sha256,
                    display_text,
                )
            )
            and changed_paths == ()
            and changed_count is None
        )
    return (
        isinstance(report_id, str)
        and _PREVIOUS_REPORT_ID.fullmatch(report_id) is not None
        and type(revision) is int
        and 1 <= revision <= 2_147_483_647
        and isinstance(markdown_sha256, str)
        and _PREVIOUS_SHA256.fullmatch(markdown_sha256) is not None
        and isinstance(created_at, str)
        and len(created_at) <= 64
        and _PREVIOUS_TIMESTAMP.fullmatch(created_at) is not None
        and (
            baseline_commit is None
            or (
                isinstance(baseline_commit, str)
                and _PREVIOUS_COMMIT.fullmatch(baseline_commit) is not None
            )
        )
        and (
            source_inventory_sha256 is None
            or (
                isinstance(source_inventory_sha256, str)
                and _PREVIOUS_SHA256.fullmatch(source_inventory_sha256) is not None
            )
        )
        and _bounded_utf8(display_text, MAX_PREVIOUS_DISPLAY_BYTES, nonblank=True)
        and (
            (changed_count is None and not changed_paths)
            or (
                type(changed_count) is int
                and len(changed_paths) <= changed_count <= MAX_PREVIOUS_CHANGED_PATHS
            )
        )
    )


def _string_key_mapping(value: object) -> bool:
    return isinstance(value, Mapping) and all(isinstance(key, str) for key in value)


def _mapping_sequence(value: object) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and all(_string_key_mapping(item) and _is_json_value(item) for item in value)
    )


def _is_scan_result(value: object) -> TypeGuard[_ScanResult]:
    elapsed_ms = getattr(value, "elapsed_ms", None)
    return (
        all(
            isinstance(getattr(value, name, None), str)
            for name in (
                "status",
                "scan_id",
                "receipt_id",
                "receipt_sha256",
                "display_text",
                "risk_level",
                "cache_status",
            )
        )
        and _mapping_sequence(getattr(value, "paths", None))
        and _mapping_sequence(getattr(value, "frontier", None))
        and _mapping_sequence(getattr(value, "candidates", None))
        and isinstance(elapsed_ms, int)
        and not isinstance(elapsed_ms, bool)
        and isinstance(getattr(value, "can_promote", None), bool)
    )


def _is_trace_seed_result(value: object) -> TypeGuard[_TraceSeedResult]:
    return (
        hasattr(value, "location")
        and isinstance(getattr(value, "term", None), str)
        and _is_optional_string(getattr(value, "location", None))
    )


def _is_trace_result(value: object) -> TypeGuard[_TraceResult]:
    seeds = getattr(value, "seeds", None)
    return (
        all(
            isinstance(getattr(value, name, None), str)
            for name in ("receipt_id", "receipt_sha256", "budget_status", "request_sha256")
        )
        and isinstance(getattr(value, "receipt_path", None), Path)
        and _string_key_mapping(getattr(value, "compact_graph", None))
        and _is_json_value(getattr(value, "compact_graph", None))
        and isinstance(seeds, Sequence)
        and not isinstance(seeds, (str, bytes))
        and all(_is_trace_seed_result(seed) for seed in seeds)
    )


def _expand_schema(schema, root):
    if isinstance(schema, list):
        return [_expand_schema(item, root) for item in schema]
    if not isinstance(schema, dict):
        return schema
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/"):
        target = root
        for part in reference[2:].split("/"):
            target = target[part]
        return _expand_schema(target, root)
    return {
        key: _expand_schema(value, root)
        for key, value in schema.items()
        if key not in {"$schema", "$defs"}
    }


EXPANDED_ANALYSIS_SCHEMA = _expand_schema(ANALYSIS_SCHEMA, ANALYSIS_SCHEMA)

PREVIOUS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["repo_root", "request", "repository_evidence"],
    "properties": {
        "repo_root": {"type": "string", "minLength": 1, "maxLength": 4096},
        "request": {"type": "string", "minLength": 1, "maxLength": 262144},
        "repository_evidence": {
            "type": "array",
            "maxItems": 128,
            "items": {"type": "string", "minLength": 1, "maxLength": 65536},
        },
    },
}

SCAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["repo_root", "change_request"],
    "properties": {
        "repo_root": {"type": "string", "minLength": 1},
        "change_request": {"type": "string", "minLength": 1, "maxLength": 4096},
        "evidence": {
            "type": "array",
            "maxItems": 32,
            "items": {"type": "string", "minLength": 1, "maxLength": 4096},
        },
        "presentation": {"enum": ["simple", "balanced", "technical"]},
    },
}

BEGIN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["repo_root", "request", "repository_evidence", "adapter"],
    "properties": {
        "repo_root": {"type": "string", "minLength": 1},
        "request": {"type": "string", "minLength": 1, "maxLength": 262144},
        "repository_evidence": {
            "type": "array",
            "maxItems": 128,
            "items": {"type": "string", "minLength": 1, "maxLength": 65536},
        },
        "adapter": {"enum": ["generic", "superpowers", "claude-feature-dev", "spec-kit"]},
        "audience_override": {
            "type": ["string", "null"],
            "enum": ["simple", "balanced", "technical", None],
        },
        "delivery_override": {"type": ["string", "null"], "enum": ["compact", "full", None]},
        "scan_id": {"type": ["string", "null"], "pattern": "^[0-9a-f]{32}$"},
    },
}
TRACE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["repo_root", "draft_id", "seeds"],
    "properties": {
        "repo_root": {"type": "string", "minLength": 1},
        "draft_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
        "seeds": {
            "type": "array",
            "minItems": 1,
            "maxItems": 128,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["term", "location"],
                "properties": {
                    "term": {"type": "string", "minLength": 1, "maxLength": 4096},
                    "location": {
                        "type": ["string", "null"],
                        "minLength": 1,
                        "maxLength": 4096,
                        "pattern": "^(?!/)(?!.*(?:^|/)\\.{1,2}(?:/|$))(?!.*\\\\).+$",
                    },
                },
            },
        },
    },
}
FINALIZE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["repo_root", "draft_id", "analysis"],
    "properties": {
        "repo_root": {"type": "string", "minLength": 1},
        "draft_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
        "graph_receipt_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
        "analysis": EXPANDED_ANALYSIS_SCHEMA,
    },
}
TOOLS = [
    {
        "name": "rir_previous",
        "description": "Look up one bounded local, network-free previous impact report before scanning; report content is returned only for a safe same-lineage match.",
        "inputSchema": PREVIOUS_SCHEMA,
    },
    {
        "name": "rir_scan",
        "description": "Run one bounded local, network-free Fast Scan without automatic detailed refinement.",
        "inputSchema": SCAN_SCHEMA,
    },
    {
        "name": "rir_begin",
        "description": "Create a local, network-free, repository-bound impact-refinement draft before analysis; data stays in the isolated workspace.",
        "inputSchema": BEGIN_SCHEMA,
    },
    {
        "name": "rir_trace_impact",
        "description": "Trace bounded local, network-free repository impact evidence for one unconsumed controller draft inside the isolated workspace.",
        "inputSchema": TRACE_SCHEMA,
    },
    {
        "name": "rir_finalize",
        "description": "Validate, publish, and render one local, network-free controller draft inside the isolated workspace.",
        "inputSchema": FINALIZE_SCHEMA,
    },
]


def _error(identifier: object, code: int, message: object) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": identifier,
        "error": {"code": code, "message": str(message)[:1024]},
    }


def _result(identifier: object, result: object) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def _validate_arguments(arguments: object, schema: dict[str, object], label: str) -> None:
    _validate_schema(arguments, schema, f"{label} arguments")


def _matches_type(value, expected):
    types = expected if isinstance(expected, list) else [expected]
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "null": lambda item: item is None,
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
    }
    return any(name in checks and checks[name](value) for name in types)


def _validate_schema(value, schema, label):
    if "oneOf" in schema:
        matches = 0
        for option in schema["oneOf"]:
            try:
                _validate_schema(value, option, label)
            except ValueError:
                continue
            matches += 1
        if matches != 1:
            raise ValueError(f"{label} does not match exactly one allowed shape")
        return
    if "type" in schema and not _matches_type(value, schema["type"]):
        raise ValueError(f"{label} has the wrong type")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{label} has an unsupported value")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = sorted(set(schema.get("required", [])) - set(value))
        unknown = (
            sorted(set(value) - set(properties))
            if schema.get("additionalProperties") is False
            else []
        )
        if missing:
            raise ValueError(f"{label} is missing {missing[0]}")
        if unknown:
            raise ValueError(f"{label} has unknown key {unknown[0]}")
        for key, item in value.items():
            if key in properties:
                _validate_schema(item, properties[key], f"{label}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"{label} has too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValueError(f"{label} has too many items")
        if schema.get("uniqueItems"):
            serialized = [json.dumps(item, sort_keys=True) for item in value]
            if len(serialized) != len(set(serialized)):
                raise ValueError(f"{label} contains duplicate items")
        for item in value:
            _validate_schema(item, schema.get("items", {}), f"{label} item")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValueError(f"{label} is too short")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValueError(f"{label} is too long")
        pattern = schema.get("pattern")
        if pattern is not None and re.fullmatch(pattern, value) is None:
            raise ValueError(f"{label} has an invalid format")


def _validated_previous_root(value: str) -> Path:
    if not _bounded_utf8(value, 4096, nonblank=True) or "\x00" in value:
        raise ValueError("rir_previous arguments.repo_root is invalid")
    path = Path(value)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise _ControllerContractError("previous repository root operation failed") from error
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode) or not resolved.is_dir():
        raise _ControllerContractError("previous repository root operation failed")
    return resolved


def _previous(arguments: object) -> dict[str, object]:
    _validate_arguments(arguments, PREVIOUS_SCHEMA, "rir_previous")
    if not _is_previous_arguments(arguments):
        raise ValueError("rir_previous arguments have the wrong type")
    root = _validated_previous_root(arguments["repo_root"])
    previous_request = rir_controller.PreviousLookupRequest(
        root,
        arguments["request"],
        tuple(arguments["repository_evidence"]),
    )
    try:
        result = rir_controller.lookup_previous(previous_request)
    except Exception as error:
        raise _ControllerContractError("controller previous operation failed") from error
    if not _is_previous_result(result):
        raise _ControllerContractError("controller previous result contract is incomplete")
    structured = {
        "status": result.status,
        "report_id": result.report_id,
        "revision": result.revision,
        "markdown_sha256": result.markdown_sha256,
        "created_at": result.created_at,
        "baseline_commit": result.baseline_commit,
        "changed_paths": list(result.changed_paths),
        "changed_count": result.changed_count,
        "requirement_sha256": result.requirement_sha256,
        "source_inventory_sha256": result.source_inventory_sha256,
        "display_text": result.display_text,
        "reason": result.reason,
        "elapsed_ms": result.elapsed_ms,
    }
    if not _is_json_value(structured):
        raise _ControllerContractError("controller previous result is not JSON-safe")
    content = [] if result.display_text is None else [{"type": "text", "text": result.display_text}]
    return {
        "content": content,
        "structuredContent": structured,
        "isError": False,
    }


def _begin(arguments: object) -> dict[str, object]:
    _validate_arguments(arguments, BEGIN_SCHEMA, "rir_begin")
    if not _is_begin_arguments(arguments):
        raise ValueError("rir_begin arguments have the wrong type")
    result = rir_controller.begin_refinement(
        rir_controller.BeginRequest(
            repo_root=Path(arguments["repo_root"]),
            request=arguments["request"],
            repository_evidence=tuple(arguments["repository_evidence"]),
            adapter=arguments["adapter"],
            audience_override=arguments.get("audience_override"),
            delivery_override=arguments.get("delivery_override"),
            scan_id=arguments.get("scan_id"),
        )
    )
    if not _is_begin_result(result):
        raise _ControllerContractError("controller begin result contract is incomplete")
    draft_path = _repository_result_path(arguments["repo_root"], result.draft_path)
    prior_state = result.prior_state
    prior_key_map = result.prior_key_map
    key_maps = (
        {
            "invariants": {},
            "impacts": {},
            "decisions": {},
            "criteria": {},
        }
        if prior_key_map is None
        else prior_key_map
    )
    decision_keys = {identifier: key for key, identifier in key_maps["decisions"].items()}
    impact_keys = {identifier: key for key, identifier in key_maps["impacts"].items()}
    invariant_keys = {identifier: key for key, identifier in key_maps["invariants"].items()}
    criterion_keys = {identifier: key for key, identifier in key_maps["criteria"].items()}
    summary_rows = [] if prior_state is None else prior_state["summary"]
    impact_rows = [] if prior_state is None else prior_state["impacts"]
    decision_rows = [] if prior_state is None else prior_state["decisions"]
    summaries = {summary_row["impact_id"]: summary_row for summary_row in summary_rows}
    carry_forward_impacts = []
    for impact_row in impact_rows:
        if impact_row["id"] not in impact_keys:
            continue
        identifiers = (
            list(impact_row["invariants"])
            + list(impact_row["decisions"])
            + list(impact_row["criteria"])
        )
        if not all(
            identifier in {**invariant_keys, **decision_keys, **criterion_keys}
            for identifier in identifiers
        ):
            continue
        summary = summaries.get(impact_row["id"])
        if summary is None:
            continue
        carry_forward_impacts.append(
            {
                "key": impact_keys[impact_row["id"]],
                "category": impact_row["category"],
                "severity": impact_row["severity"],
                "state": impact_row["state"],
                "evidence_level": impact_row["evidence_level"],
                "evidence": impact_row["evidence"],
                "invariant_keys": [invariant_keys[value] for value in impact_row["invariants"]],
                "decision_keys": [decision_keys[value] for value in impact_row["decisions"]],
                "criterion_keys": [criterion_keys[value] for value in impact_row["criteria"]],
                "summary": {
                    "changed_feature": summary["changed_feature"],
                    "possible_issue": summary["possible_issue"],
                    "affected": summary["affected"],
                    "trigger": summary["trigger"],
                    "prevention": summary["prevention"],
                },
            }
        )
    carry_forward_decisions = []
    for decision_row in decision_rows:
        if decision_row["id"] not in decision_keys:
            continue
        accepted = decision_row["accepted_impacts"]
        if not all(identifier in impact_keys for identifier in accepted):
            continue
        carry_forward_decisions.append(
            {
                "key": decision_keys[decision_row["id"]],
                "choice": decision_row["choice"],
                "accepted_impact_keys": [impact_keys[identifier] for identifier in accepted],
                "rationale": decision_row["rationale"],
            }
        )
    structured = {
        "draft_id": result.draft_id,
        "draft_path": draft_path,
        "report_id": result.report_id,
        "revision": result.revision,
        "previous_sha256": result.previous_sha256,
        "settings": dict(result.settings),
        "prior_state": result.prior_state,
        "prior_key_map": result.prior_key_map,
        "analysis_guidance": {
            "recommended_phase": ("post-decision" if carry_forward_decisions else None),
            "carry_forward_decisions": carry_forward_decisions,
            "carry_forward_impacts": carry_forward_impacts,
        },
        "repository_evidence": list(arguments["repository_evidence"]),
        "allowed_enums": {
            "phase": ["pre-decision", "post-decision"],
            "adapter": sorted(rir_controller.ADAPTERS),
            "audience": ["simple", "balanced", "technical"],
            "delivery": ["compact", "full"],
        },
        "analysis_contract": EXPANDED_ANALYSIS_SCHEMA,
        "semantic_rules": [
            (
                "this promoted Fast Scan already supplies graph_receipt_id; do not call rir_trace_impact and return the supplied ID unchanged to finalize"
                if result.scan_id is not None
                else "when settings.impact_graph.enabled is true, call rir_trace_impact exactly once before finalize and return its graph_receipt_id unchanged"
            ),
            "every graph-enabled impact requires receipt-local graph_path_keys or supplied-only unknown coverage_rationale without upgrading evidence confidence",
            "pre-decision requires decision_needed with two or three options and decisions must be empty",
            "post-decision requires decision_needed null and at least one explicit decision",
            "blocked impacts require workflow Not ready",
            "deferred impacts may proceed only when listed as a remaining risk with an owner",
            "accepted impacts require a linked decision and resolved impacts require current evidence",
            "the Superpowers handoff marker is controller-owned and must not be authored or decorated",
            "when analysis_guidance supplies prior decisions, copy those normalized rows unchanged into a post-decision revision unless the user explicitly selected a new choice",
            "reassess every carry_forward_impacts row; when new evidence changes the same risk, reuse its key and change its state so terminal-to-active Delta is reopened; create a new key only for a distinct risk",
        ],
        "installed_payload_sha256": INSTALLED_PAYLOAD_SHA256,
        "scan_id": result.scan_id,
        "graph_receipt_id": result.graph_receipt_id,
    }
    return {
        "content": [
            {"type": "text", "text": json.dumps(structured, ensure_ascii=False, sort_keys=True)}
        ],
        "structuredContent": structured,
        "isError": False,
    }


def _finalize(arguments: object) -> dict[str, object]:
    _validate_arguments(arguments, FINALIZE_SCHEMA, "rir_finalize")
    if not _is_finalize_arguments(arguments):
        raise ValueError("rir_finalize arguments have the wrong type")
    result = rir_controller.finalize_refinement(
        rir_controller.FinalizeRequest(
            repo_root=Path(arguments["repo_root"]),
            draft_id=arguments["draft_id"],
            analysis=arguments["analysis"],
            graph_receipt_id=arguments.get("graph_receipt_id"),
        )
    )
    if not _is_finalize_result(result):
        raise _ControllerContractError("controller finalize result contract is incomplete")
    state_path = _repository_result_path(arguments["repo_root"], result.state_path)
    markdown_path = _repository_result_path(arguments["repo_root"], result.markdown_path)
    structured = {
        "status": result.status,
        "report_id": result.report_id,
        "revision": result.revision,
        "delivery": result.delivery,
        "display_text": result.display_text,
        "state_path": state_path,
        "markdown_path": markdown_path,
        "markdown_sha256": result.markdown_sha256,
    }
    return {
        "content": [{"type": "text", "text": result.display_text}],
        "structuredContent": structured,
        "isError": False,
    }


def _scan(arguments: object) -> dict[str, object]:
    _validate_arguments(arguments, SCAN_SCHEMA, "rir_scan")
    if not _is_scan_arguments(arguments):
        raise ValueError("rir_scan arguments have the wrong type")
    result = rir_controller.scan_impact(
        rir_controller.ScanRequest(
            Path(arguments["repo_root"]),
            arguments["change_request"],
            tuple(arguments.get("evidence", [])),
            arguments.get("presentation"),
        )
    )
    if not _is_scan_result(result):
        raise _ControllerContractError("controller scan result contract is incomplete")
    structured = {
        "status": result.status,
        "scan_id": result.scan_id,
        "receipt_id": result.receipt_id,
        "receipt_sha256": result.receipt_sha256,
        "display_text": result.display_text,
        "risk_level": result.risk_level,
        "paths": list(result.paths),
        "frontier": list(result.frontier),
        "candidates": list(result.candidates),
        "elapsed_ms": result.elapsed_ms,
        "cache_status": result.cache_status,
        "can_promote": result.can_promote,
    }
    return {
        "content": [{"type": "text", "text": result.display_text}],
        "structuredContent": structured,
        "isError": False,
    }


def _trace(arguments: object) -> dict[str, object]:
    _validate_arguments(arguments, TRACE_SCHEMA, "rir_trace_impact")
    if not _is_trace_arguments(arguments):
        raise ValueError("rir_trace_impact arguments have the wrong type")
    result = rir_controller.trace_impact(
        rir_controller.TraceRequest(
            repo_root=Path(arguments["repo_root"]),
            draft_id=arguments["draft_id"],
            seeds=tuple(
                rir_controller.TraceSeed(row["term"], row["location"]) for row in arguments["seeds"]
            ),
        )
    )
    if not _is_trace_result(result):
        raise _ControllerContractError("controller trace result contract is incomplete")
    receipt_path = _repository_result_path(arguments["repo_root"], result.receipt_path)
    structured = {
        "receipt_id": result.receipt_id,
        "receipt_path": receipt_path,
        "receipt_sha256": result.receipt_sha256,
        "compact_graph": result.compact_graph,
        "budget_status": result.budget_status,
        "request_sha256": result.request_sha256,
        "seeds": [{"term": seed.term, "location": seed.location} for seed in result.seeds],
    }
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(structured, ensure_ascii=False, sort_keys=True),
            }
        ],
        "structuredContent": structured,
        "isError": False,
    }


def handle(message: object) -> dict[str, object] | None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, -32600, "invalid JSON-RPC request")
    identifier = message.get("id")
    method = message.get("method")
    params = message.get("params", {})
    if identifier is None:
        return None
    if method == "initialize":
        return _result(
            identifier,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "requirements-impact-refiner", "version": "0.4.0"},
            },
        )
    if method == "tools/list":
        return _result(identifier, {"tools": TOOLS})
    if method != "tools/call" or not isinstance(params, dict):
        return _error(identifier, -32601, "method not found")
    name = params.get("name")
    arguments = params.get("arguments")
    try:
        if name == "rir_previous":
            result = _previous(arguments)
        elif name == "rir_scan":
            result = _scan(arguments)
        elif name == "rir_begin":
            result = _begin(arguments)
        elif name == "rir_trace_impact":
            result = _trace(arguments)
        elif name == "rir_finalize":
            result = _finalize(arguments)
        else:
            return _error(identifier, -32602, "unknown tool")
    except _ControllerContractError:
        return _error(identifier, -32603, "controller operation failed")
    except (TypeError, ValueError) as error:
        return _error(identifier, -32602, error)
    except Exception:
        return _error(identifier, -32603, "controller operation failed")
    return _result(identifier, result)


def main() -> int:
    source = sys.stdin.buffer
    destination = sys.stdout
    while True:
        response: dict[str, object] | None
        raw = source.readline(MAX_LINE_BYTES + 1)
        if not raw:
            return 0
        if len(raw) > MAX_LINE_BYTES:
            while raw and not raw.endswith(b"\n"):
                raw = source.readline(MAX_LINE_BYTES + 1)
            response = _error(None, -32700, "request exceeds 2 MiB")
        else:
            try:
                decoded = raw.decode("utf-8")
                if _json_depth(decoded) > _MAX_JSON_DEPTH:
                    raise ValueError("json nesting depth exceeded")
                message: object = json.loads(decoded)
            except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError):
                response = _error(None, -32700, "parse error")
            else:
                response = handle(message)
        if response is not None:
            destination.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
            destination.flush()


if __name__ == "__main__":
    raise SystemExit(main())
