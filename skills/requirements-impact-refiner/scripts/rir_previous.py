#!/usr/bin/env python3
"""Bounded, fail-closed lookup of an immutable previous impact report."""

from __future__ import annotations

import contextvars
import hashlib
import importlib.util
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Callable, Literal, Protocol, cast

if TYPE_CHECKING:
    from typing_extensions import TypeGuard


class _ReportContextContract(Protocol):
    ReportContext: type
    REPORT_ID_PATTERN: re.Pattern[str]
    SHA256_PATTERN: re.Pattern[str]
    MAX_REQUIREMENT_INPUT_BYTES: int
    MAX_REQUIREMENT_BYTES: int

    def canonical_requirement_text(self, request: str) -> str: ...

    def canonical_requirement_sha256(self, request: str) -> str: ...

    def canonical_repository_evidence_sha256(self, evidence: Sequence[str]) -> str: ...

    def repo_root_sha256(self, root: Path) -> str: ...

    def load_report_context(self, root: Path, report_id: str, revision: int): ...


class _PayloadIdentityContract(Protocol):
    ROOT_FILES: tuple[str, ...]

    def functional_paths(self, plugin_root: Path) -> tuple[Path, ...]: ...

    def payload_sha256(self, plugin_root: Path) -> str: ...


class _CompactStateContract(Protocol):
    def validate_state(self, value: object) -> list[str]: ...

    def load_state_bytes(self, raw: bytes) -> tuple[dict[str, object] | None, list[str]]: ...


class _ImpactRendererContract(Protocol):
    compact_state: _CompactStateContract

    def render_compact(self, state: Mapping[str, object]) -> str: ...

    def render_markdown(self, state: Mapping[str, object]) -> str: ...


class _PreviousRendererContract(Protocol):
    COMPACT_STATE: _CompactStateContract
    IMPACT_RENDERER: _ImpactRendererContract

    def module_uses_sibling(self, value: object, filename: str) -> bool: ...

    def load_local_module(
        self,
        filename: str,
        canonical_name: str,
        prefix: str,
        validator: Callable[[object], bool],
        label: str,
    ) -> object: ...

    def render_previous(self, result: object, compact_state: Mapping[str, object]) -> str: ...


class _PerformanceContract(Protocol):
    MAX_METRIC_BYTES: int
    PhaseMetric: type
    PerformanceMetrics: type

    def estimate_tokens(self, payload: bytes) -> int: ...


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

STATUS_VALUES = frozenset({"none", "fresh", "stale", "ambiguous"})
REPORT_ID_PATTERN = re.compile(r"RPT-\d{3}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
CREATED_AT_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z")
POINTER_FIELDS = frozenset(
    {"schema_version", "report_id", "revision", "state", "markdown", "markdown_sha256"}
)
MAX_POINTER_BYTES = 8 * 1024
MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_MARKDOWN_BYTES = 4 * 1024 * 1024
MAX_GIT_OUTPUT_BYTES = 256 * 1024
MAX_CHANGED_PATHS = 4096
MAX_CHANGED_PATH_BYTES = 4096
MAX_REPORT_ENTRIES = 4096
MAX_REPORT_LINEAGES = 1000
MAX_AMBIGUOUS_CANDIDATES = 16
MAX_REQUIRED_SOURCE_DIGESTS = 64
MAX_REQUIRED_SOURCE_PATH_BYTES = 1024
MAX_REQUIRED_SOURCE_MAP_BYTES = 64 * 1024
MAX_SOURCE_RECHECK_BYTES = 4 * 1024 * 1024
OPERATION_TIMEOUT_SECONDS = 0.25
_TRANSFORM_CONFIG_PATTERN = r"^(core\.autocrlf|core\.eol|core\.attributesfile|filter\.)"
_DELTA_WORKER_SHARED_GROUP = False


def _configure_delta_worker(enabled=True):
    global _DELTA_WORKER_SHARED_GROUP
    if not isinstance(enabled, bool):
        raise TypeError("delta worker group flag must be boolean")
    _DELTA_WORKER_SHARED_GROUP = enabled


class _UnsafeLookup(ValueError):
    pass


class _LookupDeadline(TimeoutError):
    pass


class _GitUnavailable(RuntimeError):
    pass


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


def _is_previous_renderer_contract(value: object) -> TypeGuard[_PreviousRendererContract]:
    compact_state = getattr(value, "COMPACT_STATE", None)
    impact_renderer = getattr(value, "IMPACT_RENDERER", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "rir_previous_renderer.py")
        and _module_uses_sibling(compact_state, SCRIPT_DIR / "compact_state.py")
        and _module_uses_sibling(impact_renderer, SCRIPT_DIR / "impact_renderer.py")
        and getattr(impact_renderer, "compact_state", None) is compact_state
        and callable(getattr(compact_state, "validate_state", None))
        and callable(getattr(compact_state, "load_state_bytes", None))
        and callable(getattr(impact_renderer, "render_compact", None))
        and callable(getattr(impact_renderer, "render_markdown", None))
        and callable(getattr(value, "module_uses_sibling", None))
        and callable(getattr(value, "load_local_module", None))
        and callable(getattr(value, "render_previous", None))
    )


def _load_previous_renderer() -> _PreviousRendererContract:
    filename = "rir_previous_renderer.py"
    expected = _regular_module_path(SCRIPT_DIR / filename)
    if expected is None or expected != SCRIPT_DIR / filename:
        raise ImportError("previous renderer sibling is unsafe")
    canonical = sys.modules.get("rir_previous_renderer")
    if _module_uses_sibling(canonical, expected) and _is_previous_renderer_contract(canonical):
        return cast(_PreviousRendererContract, canonical)
    module_name = (
        "_rir_previous_renderer_" + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    )
    existing = sys.modules.get(module_name)
    if existing is not None:
        if not _module_uses_sibling(existing, expected) or not _is_previous_renderer_contract(
            existing
        ):
            raise ImportError("previous renderer sibling contract is incomplete")
        return cast(_PreviousRendererContract, existing)
    if canonical is None:
        module_name = "rir_previous_renderer"
    specification = importlib.util.spec_from_file_location(module_name, expected)
    if specification is None or specification.loader is None:
        raise ImportError("cannot load fixed previous renderer sibling")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError("cannot load fixed previous renderer sibling") from error
    if not _is_previous_renderer_contract(module):
        sys.modules.pop(module_name, None)
        raise ImportError("previous renderer sibling contract is incomplete")
    return cast(_PreviousRendererContract, module)


RENDERER = _load_previous_renderer()


def _is_performance_contract(value: object) -> TypeGuard[_PerformanceContract]:
    return (
        RENDERER.module_uses_sibling(value, "rir_performance.py")
        and type(getattr(value, "MAX_METRIC_BYTES", None)) is int
        and isinstance(getattr(value, "PhaseMetric", None), type)
        and isinstance(getattr(value, "PerformanceMetrics", None), type)
    )


PERFORMANCE = cast(
    _PerformanceContract,
    RENDERER.load_local_module(
        "rir_performance.py",
        "rir_performance",
        "_rir_previous_performance_",
        _is_performance_contract,
        "performance metrics",
    ),
)


@dataclass
class _LookupAccounting:
    bytes_read: int = 0
    reused_payloads: dict[str, int] = field(default_factory=dict)
    exclusions: set[str] = field(
        default_factory=lambda: {
            "directory entry and filesystem metadata bytes",
            "report-context recovery staging bytes not exposed by loader",
            "subprocess stderr bytes",
        }
    )

    def read(self, payload: bytes) -> None:
        self.bytes_read += len(payload)

    def read_size(self, size: int) -> None:
        if type(size) is int and size > 0:
            self.bytes_read += size

    def reuse(self, payload: bytes) -> None:
        if payload:
            self.reused_payloads.setdefault(hashlib.sha256(payload).hexdigest(), len(payload))


_ACCOUNTING: contextvars.ContextVar[_LookupAccounting | None] = contextvars.ContextVar(
    "rir_previous_accounting", default=None
)


def _accounting() -> _LookupAccounting:
    current = _ACCOUNTING.get()
    return current if current is not None else _LookupAccounting()


def _is_report_context_contract(value: object) -> TypeGuard[_ReportContextContract]:
    return (
        RENDERER.module_uses_sibling(value, "rir_report_context.py")
        and isinstance(getattr(value, "ReportContext", None), type)
        and isinstance(getattr(value, "REPORT_ID_PATTERN", None), re.Pattern)
        and isinstance(getattr(value, "SHA256_PATTERN", None), re.Pattern)
        and all(
            type(getattr(value, name, None)) is int and getattr(value, name) > 0
            for name in ("MAX_REQUIREMENT_INPUT_BYTES", "MAX_REQUIREMENT_BYTES")
        )
        and all(
            callable(getattr(value, name, None))
            for name in (
                "canonical_requirement_text",
                "canonical_requirement_sha256",
                "canonical_repository_evidence_sha256",
                "repo_root_sha256",
                "load_report_context",
            )
        )
    )


def _is_payload_identity_contract(value: object) -> TypeGuard[_PayloadIdentityContract]:
    root_files = getattr(value, "ROOT_FILES", None)
    return (
        RENDERER.module_uses_sibling(value, "payload_identity.py")
        and isinstance(root_files, tuple)
        and all(isinstance(item, str) for item in root_files)
        and {"scripts/rir_previous.py", "scripts/rir_previous_renderer.py"} <= set(root_files)
        and callable(getattr(value, "functional_paths", None))
        and callable(getattr(value, "payload_sha256", None))
    )


REPORT_CONTEXT = cast(
    _ReportContextContract,
    RENDERER.load_local_module(
        "rir_report_context.py",
        "rir_report_context",
        "_rir_previous_report_context_",
        _is_report_context_contract,
        "report context",
    ),
)
PAYLOAD_IDENTITY = cast(
    _PayloadIdentityContract,
    RENDERER.load_local_module(
        "payload_identity.py",
        "payload_identity",
        "_rir_previous_payload_identity_",
        _is_payload_identity_contract,
        "payload identity",
    ),
)


@dataclass(frozen=True)
class PreviousLookupRequest:
    repo_root: Path
    request: str
    repository_evidence: tuple[str, ...] = ()
    report_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.repo_root, Path):
            raise TypeError("previous lookup repo_root must be a Path")
        REPORT_CONTEXT.canonical_requirement_text(self.request)
        if not isinstance(self.repository_evidence, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.repository_evidence
        ):
            raise ValueError("previous lookup repository_evidence must contain nonblank text")
        REPORT_CONTEXT.canonical_repository_evidence_sha256(self.repository_evidence)
        if self.report_id is not None and REPORT_ID_PATTERN.fullmatch(self.report_id) is None:
            raise ValueError("previous lookup report ID is invalid")


@dataclass(frozen=True)
class PreviousReportCandidate:
    report_id: str
    revision: int
    created_at: str

    def __post_init__(self) -> None:
        if REPORT_ID_PATTERN.fullmatch(self.report_id) is None:
            raise ValueError("previous candidate report ID is invalid")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("previous candidate revision is invalid")
        if (
            not isinstance(self.created_at, str)
            or len(self.created_at.encode("utf-8")) > 64
            or CREATED_AT_PATTERN.fullmatch(self.created_at) is None
        ):
            raise ValueError("previous candidate creation time is invalid")


@dataclass(frozen=True)
class PreviousReportResult:
    status: Literal["none", "fresh", "stale", "ambiguous"]
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
    candidates: tuple[PreviousReportCandidate, ...] = ()
    performance_metrics: object = field(default_factory=PERFORMANCE.PerformanceMetrics)

    def __post_init__(self) -> None:
        if self.status not in STATUS_VALUES:
            raise ValueError("previous result status is invalid")
        if SHA256_PATTERN.fullmatch(self.requirement_sha256) is None:
            raise ValueError("previous result requirement digest is invalid")
        if not isinstance(self.changed_paths, tuple) or any(
            not isinstance(item, str) for item in self.changed_paths
        ):
            raise TypeError("previous result changed paths must be a text tuple")
        if tuple(sorted(set(self.changed_paths))) != self.changed_paths:
            raise ValueError("previous result changed paths must be unique and sorted")
        if self.changed_count is not None and (
            type(self.changed_count) is not int
            or self.changed_count < len(self.changed_paths)
            or self.changed_count < 0
        ):
            raise ValueError("previous result changed count is invalid")
        if type(self.elapsed_ms) is not int or self.elapsed_ms < 0:
            raise ValueError("previous result elapsed time is invalid")
        if not isinstance(self.performance_metrics, PERFORMANCE.PerformanceMetrics):
            raise TypeError("previous result performance metrics are invalid")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("previous result reason is required")
        if (
            not isinstance(self.candidates, tuple)
            or len(self.candidates) > MAX_AMBIGUOUS_CANDIDATES
            or any(
                not isinstance(candidate, PreviousReportCandidate) for candidate in self.candidates
            )
            or tuple(sorted(self.candidates, key=lambda candidate: candidate.report_id))
            != self.candidates
            or len({candidate.report_id for candidate in self.candidates}) != len(self.candidates)
        ):
            raise ValueError("previous result candidates are invalid")
        if self.status in {"none", "ambiguous"}:
            if any(
                value is not None
                for value in (
                    self.report_id,
                    self.revision,
                    self.markdown_sha256,
                    self.created_at,
                    self.baseline_commit,
                    self.source_inventory_sha256,
                    self.display_text,
                )
            ):
                raise ValueError("non-selected previous result cannot disclose report identity")
            if self.changed_paths or self.changed_count is not None:
                raise ValueError("non-selected previous result cannot disclose changed paths")
            if self.status == "none" and self.candidates:
                raise ValueError("none previous result cannot disclose candidates")
            if self.status == "ambiguous" and len(self.candidates) < 2:
                raise ValueError("ambiguous previous result requires candidates")
            return
        if self.candidates:
            raise ValueError("selected previous result cannot disclose candidates")
        if self.report_id is None or REPORT_ID_PATTERN.fullmatch(self.report_id) is None:
            raise ValueError("selected previous result report ID is invalid")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("selected previous result revision is invalid")
        if self.markdown_sha256 is None or SHA256_PATTERN.fullmatch(self.markdown_sha256) is None:
            raise ValueError("selected previous result Markdown digest is invalid")
        if (
            self.baseline_commit is not None
            and COMMIT_PATTERN.fullmatch(self.baseline_commit) is None
        ):
            raise ValueError("selected previous result baseline commit is invalid")
        if self.source_inventory_sha256 is not None and (
            SHA256_PATTERN.fullmatch(self.source_inventory_sha256) is None
        ):
            raise ValueError("selected previous result source inventory digest is invalid")
        if self.display_text is not None and not self.display_text.strip():
            raise ValueError("selected previous result display text is invalid")


@dataclass(frozen=True)
class _CurrentCandidate:
    report_id: str
    revision: int
    markdown_sha256: str
    state: Mapping[str, object]
    requirement_sha256: str
    context: object | None
    incompatible_context: bool
    state_payload: bytes
    markdown_payload: bytes


@dataclass(frozen=True)
class _GitCommandResult:
    returncode: int
    output: bytes


@dataclass(frozen=True)
class _GitSnapshot:
    available: bool
    commit: str | None
    changed_paths: tuple[str, ...]
    changed_count: int | None
    worktree_clean: bool
    reason: str


@dataclass(frozen=True)
class _GitProofState:
    commit: str
    status_payload: bytes
    status_paths: tuple[str, ...]
    index_flags: bytes
    transforms: tuple[tuple[str, bytes | None], ...]


def _root(value: Path) -> Path:
    path = Path(value)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError(f"repository root is unavailable: {error}") from error
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode) or not resolved.is_dir():
        raise ValueError("repository root must be a real directory")
    return resolved


def _plugin_root() -> Path:
    candidate = SCRIPT_DIR.parent
    if not (candidate / ".codex-plugin" / "plugin.json").is_file():
        candidate = SCRIPT_DIR.parents[2]
    return candidate


def _payload_sha256() -> str:
    plugin_root = _plugin_root()
    digest = PAYLOAD_IDENTITY.payload_sha256(plugin_root)
    accounting = _ACCOUNTING.get()
    if accounting is not None:
        try:
            accounting.read_size(
                sum(path.stat().st_size for path in PAYLOAD_IDENTITY.functional_paths(plugin_root))
            )
        except OSError:
            accounting.exclusions.add("payload identity bytes after an unstable read")
    return digest


def _directory_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _open_child_directory(parent: int, name: str, *, missing_ok: bool = False) -> int | None:
    try:
        return os.open(name, _directory_flags(), dir_fd=parent)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise _UnsafeLookup(f"report directory is unavailable: {name}") from None
    except OSError as error:
        raise _UnsafeLookup(f"report directory is unsafe: {name}") from error


def _open_reports_directory(root: Path) -> int | None:
    root_fd: int | None = None
    state_fd: int | None = None
    try:
        root_fd = os.open(root, _directory_flags())
        state_fd = _open_child_directory(root_fd, ".requirements-impact-refiner", missing_ok=True)
        if state_fd is None:
            return None
        reports_fd = _open_child_directory(state_fd, "reports", missing_ok=True)
        return reports_fd
    except OSError as error:
        raise _UnsafeLookup("repository root is unsafe") from error
    finally:
        if state_fd is not None:
            os.close(state_fd)
        if root_fd is not None:
            os.close(root_fd)


def _report_ids(reports_fd: int, deadline: float) -> tuple[str, ...]:
    names: list[str] = []
    entries_seen = 0
    try:
        with os.scandir(reports_fd) as entries:
            for entry in entries:
                _check_deadline(deadline)
                entries_seen += 1
                if entries_seen > MAX_REPORT_ENTRIES:
                    raise _UnsafeLookup("report lineage inventory exceeds its entry limit")
                if REPORT_ID_PATTERN.fullmatch(entry.name) is None:
                    continue
                if len(names) >= MAX_REPORT_LINEAGES:
                    raise _UnsafeLookup("report lineage inventory exceeds its lineage limit")
                try:
                    if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                        raise _UnsafeLookup("report lineage path is unsafe")
                except OSError as error:
                    raise _UnsafeLookup("report lineage path is unsafe") from error
                names.append(entry.name)
    except OSError as error:
        raise _UnsafeLookup("cannot inspect report lineage inventory") from error
    return tuple(sorted(names))


def _read_regular(
    directory_fd: int,
    name: str,
    maximum: int,
    *,
    missing_ok: bool = False,
) -> bytes | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise _UnsafeLookup(f"report artifact is unavailable: {name}") from None
    except OSError as error:
        raise _UnsafeLookup(f"report artifact is unsafe: {name}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size < 0 or metadata.st_size > maximum:
            raise _UnsafeLookup(f"report artifact is unsafe: {name}")
        payload = bytearray()
        while len(payload) <= maximum:
            chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
            accounting = _ACCOUNTING.get()
            if accounting is not None:
                accounting.read(chunk)
        if len(payload) > maximum:
            raise _UnsafeLookup(f"report artifact exceeds its byte limit: {name}")
        raw = bytes(payload)
        return raw
    except OSError as error:
        raise _UnsafeLookup(f"cannot read report artifact: {name}") from error
    finally:
        os.close(descriptor)


def _json_object(payload: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise _UnsafeLookup(f"{label} is invalid") from error
    if not isinstance(value, dict):
        raise _UnsafeLookup(f"{label} is invalid")
    return value


def _context_artifact_state(report_fd: int, revision: int) -> tuple[bool, bool]:
    names = (
        f"revision-{revision:04d}.context-v2.json",
        f".revision-{revision:04d}.context-v2.json.pending",
    )
    current = False
    for name in names:
        try:
            os.stat(name, dir_fd=report_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise _UnsafeLookup("report context identity is unsafe") from error
        current = True
        break
    legacy_name = f"revision-{revision:04d}.context.json"
    try:
        os.stat(legacy_name, dir_fd=report_fd, follow_symlinks=False)
    except FileNotFoundError:
        legacy = False
    except OSError as error:
        raise _UnsafeLookup("report context identity is unsafe") from error
    else:
        legacy = True
    return current, legacy


def _read_candidate(root: Path, reports_fd: int, report_id: str, deadline: float):
    report_fd = _open_child_directory(reports_fd, report_id)
    if report_fd is None:  # pragma: no cover - missing_ok=False is exhaustive
        raise _UnsafeLookup("report lineage is unavailable")
    try:
        pointer_payload = _read_regular(
            report_fd, "current.json", MAX_POINTER_BYTES, missing_ok=True
        )
        if pointer_payload is None:
            return None
        _check_deadline(deadline)
        pointer = _json_object(pointer_payload, "current report pointer")
        if set(pointer) != POINTER_FIELDS:
            raise _UnsafeLookup("current report pointer schema is invalid")
        schema_version = pointer.get("schema_version")
        revision = pointer.get("revision")
        markdown_sha256 = pointer.get("markdown_sha256")
        if (
            type(schema_version) is not int
            or schema_version != 1
            or pointer.get("report_id") != report_id
            or type(revision) is not int
            or revision < 1
            or not isinstance(markdown_sha256, str)
            or SHA256_PATTERN.fullmatch(markdown_sha256) is None
        ):
            raise _UnsafeLookup("current report pointer identity is invalid")
        state_name = f"revision-{revision:04d}.json"
        markdown_name = f"revision-{revision:04d}.md"
        if pointer.get("state") != state_name or pointer.get("markdown") != markdown_name:
            raise _UnsafeLookup("current report pointer revision paths are invalid")
        state_payload = _read_regular(report_fd, state_name, MAX_STATE_BYTES)
        markdown_payload = _read_regular(report_fd, markdown_name, MAX_MARKDOWN_BYTES)
        assert state_payload is not None and markdown_payload is not None
        if hashlib.sha256(markdown_payload).hexdigest() != markdown_sha256:
            raise _UnsafeLookup("current report Markdown digest is invalid")
        _check_deadline(deadline)
        try:
            state, errors = RENDERER.COMPACT_STATE.load_state_bytes(state_payload)
        except (RecursionError, ValueError, TypeError) as error:
            raise _UnsafeLookup("current compact state is invalid") from error
        if errors or state is None:
            raise _UnsafeLookup("current compact state is invalid")
        report = state.get("report")
        original = state.get("original_requirement")
        if (
            not isinstance(report, Mapping)
            or report.get("id") != report_id
            or report.get("revision") != revision
            or not isinstance(original, Mapping)
            or not isinstance(original.get("request"), str)
        ):
            raise _UnsafeLookup("current compact state identity is invalid")
        try:
            rendered_markdown = RENDERER.IMPACT_RENDERER.render_markdown(state).encode("utf-8")
        except (TypeError, ValueError, RecursionError) as error:
            raise _UnsafeLookup(
                "current compact state cannot reproduce immutable Markdown"
            ) from error
        if rendered_markdown != markdown_payload:
            raise _UnsafeLookup("current compact state does not match immutable Markdown")
        requirement_sha256 = REPORT_CONTEXT.canonical_requirement_sha256(
            cast(str, original["request"])
        )
        context_present, legacy_context_present = _context_artifact_state(report_fd, revision)
    finally:
        os.close(report_fd)
    _check_deadline(deadline)
    try:
        context = REPORT_CONTEXT.load_report_context(root, report_id, revision)
    except (OSError, TypeError, ValueError) as error:
        raise _UnsafeLookup("report context identity is unsafe") from error
    _check_deadline(deadline)
    accounting = _ACCOUNTING.get()
    if accounting is not None and context_present:
        try:
            accounting.read_size(
                (
                    root
                    / ".requirements-impact-refiner"
                    / "reports"
                    / report_id
                    / f"revision-{revision:04d}.context-v2.json"
                )
                .stat()
                .st_size
            )
        except OSError:
            accounting.exclusions.add("report context bytes after an unstable read")
    if context_present and context is None:
        raise _UnsafeLookup("report context identity is unavailable")
    if context is not None:
        if (
            getattr(context, "schema_version", None) != 2
            or getattr(context, "report_id", None) != report_id
            or getattr(context, "revision", None) != revision
            or getattr(context, "markdown_sha256", None) != markdown_sha256
            or getattr(context, "state_sha256", None) != hashlib.sha256(state_payload).hexdigest()
            or getattr(context, "repo_root_sha256", None) != REPORT_CONTEXT.repo_root_sha256(root)
            or getattr(context, "requirement_sha256", None) != requirement_sha256
        ):
            raise _UnsafeLookup("report context does not match the selected revision")
    return _CurrentCandidate(
        report_id=report_id,
        revision=revision,
        markdown_sha256=markdown_sha256,
        state=state,
        requirement_sha256=requirement_sha256,
        context=context,
        incompatible_context=legacy_context_present and context is None,
        state_payload=state_payload,
        markdown_payload=markdown_payload,
    )


def _git_environment() -> dict[str, str]:
    environment = {
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", ""),
    }
    system_root = os.environ.get("SYSTEMROOT")
    if system_root:
        environment["SYSTEMROOT"] = system_root
    return environment


def _git_configuration_environment() -> dict[str, str]:
    environment = _git_environment()
    environment.pop("GIT_CONFIG_GLOBAL", None)
    environment.pop("GIT_CONFIG_NOSYSTEM", None)
    for name in ("HOME", "XDG_CONFIG_HOME", "PROGRAMDATA"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    return environment


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    group_signaled = False
    if hasattr(os, "killpg"):
        try:
            os.killpg(process.pid, signal.SIGTERM)
            group_signaled = True
        except OSError:
            pass
    if not group_signaled and process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.wait(timeout=0.01)
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
        process.wait(timeout=0.01)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _run_git_command(
    root: Path,
    arguments: tuple[str, ...],
    deadline: float,
    *,
    environment: Mapping[str, str] | None = None,
) -> _GitCommandResult | None:
    command = (
        "git",
        "--no-pager",
        "--no-replace-objects",
        "--literal-pathspecs",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "core.preloadIndex=false",
        "-c",
        "color.ui=false",
        "-c",
        "core.quotePath=true",
        "-c",
        "submodule.recurse=false",
        *arguments,
    )
    if deadline <= time.monotonic():
        return None
    try:
        process = subprocess.Popen(
            command,
            cwd=str(root),
            env=dict(environment) if environment is not None else _git_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=not _DELTA_WORKER_SHARED_GROUP,
        )
    except OSError:
        return None
    if process.stdout is None:  # pragma: no cover - PIPE guarantees stdout
        _stop_process(process)
        return None
    selector = selectors.DefaultSelector()
    payload = bytearray()
    try:
        descriptor = process.stdout.fileno()
        os.set_blocking(descriptor, False)
        selector.register(descriptor, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _stop_process(process)
                return None
            events = selector.select(remaining)
            if not events:
                _stop_process(process)
                return None
            try:
                chunk = os.read(
                    descriptor,
                    min(64 * 1024, MAX_GIT_OUTPUT_BYTES + 1 - len(payload)),
                )
            except BlockingIOError:
                continue
            if not chunk:
                break
            payload.extend(chunk)
            accounting = _ACCOUNTING.get()
            if accounting is not None:
                accounting.read(chunk)
            if len(payload) > MAX_GIT_OUTPUT_BYTES:
                _stop_process(process)
                raise _GitUnavailable("Git output exceeds its byte limit")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _stop_process(process)
            return None
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            _stop_process(process)
            return None
        raw = bytes(payload)
        return _GitCommandResult(returncode, raw)
    except OSError:
        _stop_process(process)
        return None
    finally:
        selector.close()
        process.stdout.close()


def _safe_changed_path(payload: bytes) -> str:
    if not payload or len(payload) > MAX_CHANGED_PATH_BYTES:
        raise _GitUnavailable("Git changed path is invalid")
    try:
        path = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise _GitUnavailable("Git changed path is not UTF-8") from error
    pure = PurePosixPath(path)
    if (
        pure.is_absolute()
        or path in {".", ".."}
        or ".." in pure.parts
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
    ):
        raise _GitUnavailable("Git changed path is unsafe")
    return path


def _status_paths(payload: bytes) -> tuple[str, ...]:
    if not payload:
        return ()
    records = payload.split(b"\0")
    if records[-1] != b"":
        raise _GitUnavailable("Git status output is incomplete")
    paths = set()
    for record in records[:-1]:
        if len(record) < 4 or record[2:3] != b" ":
            raise _GitUnavailable("Git status output is malformed")
        status_code = record[:2]
        if any(character not in b" MADTUXBRC?!" for character in status_code):
            raise _GitUnavailable("Git status code is invalid")
        if b"R" in status_code or b"C" in status_code:
            raise _GitUnavailable("Git rename output is unexpected")
        paths.add(_safe_changed_path(record[3:]))
        if len(paths) > MAX_CHANGED_PATHS:
            raise _GitUnavailable("Git changed path count exceeds its limit")
    return tuple(sorted(paths))


def _diff_paths(payload: bytes) -> tuple[str, ...]:
    if not payload:
        return ()
    records = payload.split(b"\0")
    if records[-1] != b"":
        raise _GitUnavailable("Git diff output is incomplete")
    paths = {_safe_changed_path(record) for record in records[:-1]}
    if len(paths) > MAX_CHANGED_PATHS:
        raise _GitUnavailable("Git changed path count exceeds its limit")
    return tuple(sorted(paths))


def _required_source_digest_map(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise _GitUnavailable("required source digest map is unavailable")
    if len(value) > MAX_REQUIRED_SOURCE_DIGESTS:
        raise _GitUnavailable("required source digest map exceeds its count limit")
    normalized: dict[str, str] = {}
    for path, digest in value.items():
        if not isinstance(path, str) or not path or "\\" in path:
            raise _GitUnavailable("required source path is unsafe")
        try:
            encoded_path = path.encode("utf-8")
        except UnicodeEncodeError as error:
            raise _GitUnavailable("required source path is not UTF-8") from error
        if len(encoded_path) > MAX_REQUIRED_SOURCE_PATH_BYTES:
            raise _GitUnavailable("required source path exceeds its byte limit")
        pure = PurePosixPath(path)
        if (
            pure.is_absolute()
            or pure.as_posix() != path
            or any(part in {"", ".", ".."} for part in pure.parts)
            or any(ord(character) < 32 or ord(character) == 127 for character in path)
        ):
            raise _GitUnavailable("required source path is unsafe")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise _GitUnavailable("required source digest is invalid")
        normalized[path] = digest
    normalized = dict(sorted(normalized.items()))
    payload = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if len(payload) > MAX_REQUIRED_SOURCE_MAP_BYTES:
        raise _GitUnavailable("required source digest map exceeds its serialized byte limit")
    return normalized


def _same_path_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
    )


def _source_file_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _source_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise _GitUnavailable("required source proof exceeded the lookup deadline")


def _hash_required_source(
    root: Path,
    relative: str,
    maximum: int,
    deadline: float,
) -> tuple[str, int]:
    parts = PurePosixPath(relative).parts
    opened: list[int] = []
    bindings: list[tuple[int, str, int]] = []
    try:
        _source_deadline(deadline)
        directory_fd = os.open(root, _directory_flags())
        opened.append(directory_fd)
        root_fd_metadata = os.fstat(directory_fd)
        root_path_metadata = os.stat(root, follow_symlinks=False)
        if not _same_path_identity(root_fd_metadata, root_path_metadata):
            raise _GitUnavailable("required source root identity changed")
        for part in parts[:-1]:
            _source_deadline(deadline)
            parent_fd = directory_fd
            child_fd = os.open(part, _directory_flags(), dir_fd=parent_fd)
            opened.append(child_fd)
            child_metadata = os.fstat(child_fd)
            path_metadata = os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISDIR(child_metadata.st_mode) or not _same_path_identity(
                child_metadata, path_metadata
            ):
                raise _GitUnavailable("required source directory identity changed")
            bindings.append((parent_fd, part, child_fd))
            directory_fd = child_fd
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(parts[-1], flags, dir_fd=directory_fd)
        opened.append(descriptor)
        metadata = os.fstat(descriptor)
        path_metadata = os.stat(parts[-1], dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size < 0
            or metadata.st_size > maximum
            or not _same_path_identity(metadata, path_metadata)
            or _source_file_identity(metadata) != _source_file_identity(path_metadata)
        ):
            if metadata.st_size > maximum:
                raise _GitUnavailable("required source bytes exceed the recheck byte limit")
            raise _GitUnavailable("required source is not a safe regular file")
        initial_identity = _source_file_identity(metadata)
        digest = hashlib.sha256()
        remaining = metadata.st_size
        while remaining:
            _source_deadline(deadline)
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                raise _GitUnavailable("required source was truncated during hashing")
            digest.update(chunk)
            accounting = _ACCOUNTING.get()
            if accounting is not None:
                accounting.read(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise _GitUnavailable("required source grew during hashing")
        final_metadata = os.fstat(descriptor)
        final_path_metadata = os.stat(parts[-1], dir_fd=directory_fd, follow_symlinks=False)
        if (
            _source_file_identity(final_metadata) != initial_identity
            or _source_file_identity(final_path_metadata) != initial_identity
        ):
            raise _GitUnavailable("required source identity changed during hashing")
        for parent_fd, name, child_fd in reversed(bindings):
            if not _same_path_identity(
                os.fstat(child_fd),
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False),
            ):
                raise _GitUnavailable("required source path identity changed during hashing")
        if not _same_path_identity(os.fstat(opened[0]), os.stat(root, follow_symlinks=False)):
            raise _GitUnavailable("required source root identity changed during hashing")
        _source_deadline(deadline)
        return digest.hexdigest(), metadata.st_size
    except _GitUnavailable:
        raise
    except OSError as error:
        raise _GitUnavailable("required source is unavailable or unsafe") from error
    finally:
        for descriptor in reversed(opened):
            os.close(descriptor)


def _hash_required_sources(
    root: Path,
    required: Mapping[str, str],
    deadline: float,
) -> dict[str, str]:
    normalized = _required_source_digest_map(required)
    remaining = MAX_SOURCE_RECHECK_BYTES
    observed: dict[str, str] = {}
    for path in normalized:
        digest, size = _hash_required_source(root, path, remaining, deadline)
        remaining -= size
        observed[path] = digest
    return observed


def _successful(result: _GitCommandResult | None, label: str) -> bytes:
    if result is None:
        raise _GitUnavailable(f"{label} timed out or is unavailable")
    if result.returncode != 0:
        raise _GitUnavailable(f"{label} failed")
    if b"\0" in result.output and label not in {
        "Git status",
        "Git diff",
        "Git index flags",
    }:
        raise _GitUnavailable(f"{label} output contains NUL")
    return result.output


def _decode_single_path(payload: bytes, label: str) -> Path:
    if b"\0" in payload:
        raise _GitUnavailable(f"{label} output contains NUL")
    try:
        value = payload.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise _GitUnavailable(f"{label} output is not UTF-8") from error
    if not value or "\n" in value or "\r" in value:
        raise _GitUnavailable(f"{label} output is invalid")
    return Path(value)


def _filesystem_git_dir(root: Path) -> Path:
    marker = root / ".git"
    try:
        metadata = marker.lstat()
    except OSError as error:
        raise _GitUnavailable("Git directory is unavailable") from error
    if stat.S_ISDIR(metadata.st_mode) and not marker.is_symlink():
        return marker.resolve()
    if not stat.S_ISREG(metadata.st_mode) or marker.is_symlink() or metadata.st_size > 4096:
        raise _GitUnavailable("Git directory marker is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(marker, flags)
        try:
            payload = os.read(descriptor, 4097)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise _GitUnavailable("Git directory marker is unavailable") from error
    accounting = _ACCOUNTING.get()
    if accounting is not None:
        accounting.read(payload)
    try:
        text = payload.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise _GitUnavailable("Git directory marker is not UTF-8") from error
    prefix = "gitdir: "
    if not text.startswith(prefix) or "\n" in text or "\r" in text:
        raise _GitUnavailable("Git directory marker is invalid")
    value = Path(text[len(prefix) :])
    git_dir = value if value.is_absolute() else marker.parent / value
    try:
        resolved = git_dir.resolve(strict=True)
    except OSError as error:
        raise _GitUnavailable("Git directory is unavailable") from error
    if not resolved.is_dir():
        raise _GitUnavailable("Git directory is invalid")
    return resolved


def _read_git_control_file(path: Path, maximum: int) -> bytes | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise _GitUnavailable("Git control file is unavailable") from error
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
        raise _GitUnavailable("Git control file is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            payload = os.read(descriptor, maximum + 1)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise _GitUnavailable("Git control file is unavailable") from error
    if len(payload) > maximum:
        raise _GitUnavailable("Git control file exceeds its byte limit")
    accounting = _ACCOUNTING.get()
    if accounting is not None:
        accounting.read(payload)
    return payload


def _filesystem_common_dir(git_dir: Path) -> Path:
    common_dir = git_dir
    commondir_payload = _read_git_control_file(git_dir / "commondir", 4096)
    if commondir_payload is not None:
        try:
            value = commondir_payload.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError as error:
            raise _GitUnavailable("Git common directory is not UTF-8") from error
        if not value or "\n" in value or "\r" in value:
            raise _GitUnavailable("Git common directory is invalid")
        candidate = Path(value)
        try:
            common_dir = (candidate if candidate.is_absolute() else git_dir / candidate).resolve(
                strict=True
            )
        except OSError as error:
            raise _GitUnavailable("Git common directory is unavailable") from error
        if not common_dir.is_dir():
            raise _GitUnavailable("Git common directory is invalid")
    return common_dir


def _filesystem_head(git_dir: Path) -> str:
    payload = _read_git_control_file(git_dir / "HEAD", 4096)
    if payload is None:
        raise _GitUnavailable("Git HEAD is unavailable")
    try:
        value = payload.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise _GitUnavailable("Git HEAD is not ASCII") from error
    if COMMIT_PATTERN.fullmatch(value) is not None:
        return value
    prefix = "ref: "
    if not value.startswith(prefix):
        raise _GitUnavailable("Git HEAD is invalid")
    reference = value[len(prefix) :]
    reference_path = PurePosixPath(reference)
    if (
        not reference.startswith("refs/")
        or reference_path.is_absolute()
        or ".." in reference_path.parts
    ):
        raise _GitUnavailable("Git HEAD reference is unsafe")
    common_dir = _filesystem_common_dir(git_dir)
    loose = _read_git_control_file(common_dir.joinpath(*reference_path.parts), 4096)
    if loose is not None:
        try:
            commit = loose.decode("ascii", errors="strict").strip()
        except UnicodeDecodeError as error:
            raise _GitUnavailable("Git HEAD reference is not ASCII") from error
        if COMMIT_PATTERN.fullmatch(commit) is None:
            raise _GitUnavailable("Git HEAD reference is invalid")
        return commit
    packed = _read_git_control_file(common_dir / "packed-refs", 4 * 1024 * 1024)
    if packed is None:
        raise _GitUnavailable("Git HEAD reference is unavailable")
    try:
        lines = packed.decode("ascii", errors="strict").splitlines()
    except UnicodeDecodeError as error:
        raise _GitUnavailable("Git packed refs are not ASCII") from error
    matches = [line.split(" ", 1)[0] for line in lines if line.endswith(" " + reference)]
    if len(matches) != 1 or COMMIT_PATTERN.fullmatch(matches[0]) is None:
        raise _GitUnavailable("Git HEAD reference is unavailable")
    return matches[0]


def _configured_worktree_matches(root: Path, git_dir: Path) -> bool:
    common_dir = _filesystem_common_dir(git_dir)
    configured_paths: list[Path] = []
    for config_path in (common_dir / "config", git_dir / "config.worktree"):
        payload = _read_git_control_file(config_path, 256 * 1024)
        if payload is None:
            continue
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise _GitUnavailable("Git local config is not UTF-8") from error
        section = ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("#", ";")):
                continue
            if line.startswith("["):
                if not line.endswith("]"):
                    raise _GitUnavailable("Git local config is malformed")
                section = line[1:-1].split(maxsplit=1)[0].strip('"').lower()
                if section in {"include", "includeif"}:
                    return False
                continue
            key, separator, value = line.partition("=")
            if section == "core" and key.strip().lower() == "worktree":
                if not separator:
                    return False
                configured = value.strip().strip('"')
                if not configured:
                    return False
                configured_path = Path(configured)
                configured_paths.append(
                    configured_path
                    if configured_path.is_absolute()
                    else config_path.parent / configured_path
                )
    return all(path.resolve() == root for path in configured_paths)


def _replacement_refs_present(git_dir: Path) -> bool:
    common_dir = _filesystem_common_dir(git_dir)
    replace_dir = common_dir / "refs" / "replace"
    try:
        metadata = replace_dir.lstat()
    except FileNotFoundError:
        metadata = None
    except OSError as error:
        raise _GitUnavailable("Git replacement refs are unavailable") from error
    if metadata is not None:
        if replace_dir.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise _GitUnavailable("Git replacement refs are unsafe")
        try:
            with os.scandir(replace_dir) as entries:
                if next(entries, None) is not None:
                    return True
        except OSError as error:
            raise _GitUnavailable("Git replacement refs are unavailable") from error
    packed = _read_git_control_file(common_dir / "packed-refs", 4 * 1024 * 1024)
    return packed is not None and b" refs/replace/" in packed


def _worktree_scope(root: Path, deadline: float) -> tuple[str, str]:
    git_dir = _filesystem_git_dir(root)
    scope = (f"--git-dir={git_dir}", f"--work-tree={root}")
    if not _configured_worktree_matches(root, git_dir):
        raise _GitUnavailable("Git core.worktree redirects outside the repository")
    return scope


def _index_flags_snapshot(root: Path, scope: tuple[str, str], deadline: float) -> bytes:
    payload = _successful(
        _run_git_command(root, (*scope, "ls-files", "-s", "-v", "-z"), deadline),
        "Git index flags",
    )
    if not payload:
        return payload
    records = payload.split(b"\0")
    if records[-1] != b"":
        raise _GitUnavailable("Git index flags output is incomplete")
    for record in records[:-1]:
        header, separator, path = record.partition(b"\t")
        fields = header.split(b" ")
        if not separator or len(fields) != 4 or len(fields[0]) != 1:
            raise _GitUnavailable("Git index flags output is malformed")
        relative = _safe_changed_path(path)
        if fields[0] != b"H":
            raise _GitUnavailable("Git index visibility flags are present")
        if fields[1] == b"160000":
            raise _GitUnavailable("Git gitlinks are outside the freshness proof scope")
        if relative == ".gitattributes" or relative.endswith("/.gitattributes"):
            raise _GitUnavailable("tracked Git attributes are outside the freshness proof scope")
    return payload


def _checkout_transform_snapshot(
    root: Path,
    scope: tuple[str, str],
    git_dir: Path,
    deadline: float,
) -> tuple[tuple[str, bytes | None], ...]:
    config = _run_git_command(
        root,
        (*scope, "config", "--null", "--get-regexp", _TRANSFORM_CONFIG_PATTERN),
        deadline,
        environment=_git_configuration_environment(),
    )
    if config is None or config.returncode not in {0, 1}:
        raise _GitUnavailable("Git checkout transform configuration is unavailable")
    if config.returncode == 0 or config.output:
        raise _GitUnavailable("Git checkout transform configuration is present")

    snapshots: list[tuple[str, bytes | None]] = []
    directories = (git_dir, _filesystem_common_dir(git_dir))
    for directory in dict.fromkeys(directories):
        info = directory / "info"
        try:
            info_metadata = info.lstat()
        except FileNotFoundError:
            payload = None
        except OSError as error:
            raise _GitUnavailable("Git info attributes are unavailable") from error
        else:
            if info.is_symlink() or not stat.S_ISDIR(info_metadata.st_mode):
                raise _GitUnavailable("Git info attributes are unsafe")
            payload = _read_git_control_file(info / "attributes", MAX_GIT_OUTPUT_BYTES)
        if payload:
            raise _GitUnavailable("Git info attributes are present")
        snapshots.append((str(info / "attributes"), payload))
    return tuple(snapshots)


def _capture_git_proof_state(
    root: Path,
    scope: tuple[str, str],
    git_dir: Path,
    deadline: float,
) -> _GitProofState:
    _check_deadline(deadline)
    if _replacement_refs_present(git_dir):
        raise _GitUnavailable("Git replacement refs are present")
    commit = _filesystem_head(git_dir)
    transforms = _checkout_transform_snapshot(root, scope, git_dir, deadline)
    status_payload = _successful(
        _run_git_command(
            root,
            (
                *scope,
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=normal",
                "--ignore-submodules=none",
                "--no-renames",
            ),
            deadline,
        ),
        "Git status",
    )
    status_paths = _status_paths(status_payload)
    index_flags = _index_flags_snapshot(root, scope, deadline)
    _check_deadline(deadline)
    return _GitProofState(commit, status_payload, status_paths, index_flags, transforms)


def _assert_stable_git_proof(before: _GitProofState, after: _GitProofState) -> None:
    if after.commit != before.commit:
        raise _GitUnavailable("Git HEAD changed during freshness proof")
    if after.status_payload != before.status_payload or after.status_paths != before.status_paths:
        raise _GitUnavailable("Git working tree changed during freshness proof")
    if after.index_flags != before.index_flags:
        raise _GitUnavailable("Git index changed during freshness proof")
    if after.transforms != before.transforms:
        raise _GitUnavailable("Git checkout transform state changed during freshness proof")


def _probe_git(
    root: Path,
    baseline_commit: str | None,
    deadline: float,
    required_source_digests: Mapping[str, str] | None = None,
) -> _GitSnapshot:
    try:
        scope = _worktree_scope(root, deadline)
        git_dir = Path(scope[0].split("=", 1)[1])
        before = _capture_git_proof_state(root, scope, git_dir, deadline)
        required = (
            None
            if required_source_digests is None
            else _required_source_digest_map(required_source_digests)
        )
        prove_sources = (
            required is not None
            and not before.status_paths
            and baseline_commit is not None
            and baseline_commit == before.commit
        )
        source_error: _GitUnavailable | None = None
        observed_before: dict[str, str] | None = None
        if prove_sources:
            assert required is not None
            try:
                observed_before = _hash_required_sources(root, required, deadline)
            except _GitUnavailable as error:
                source_error = error
        diff_paths: tuple[str, ...] = ()
        if baseline_commit is not None and baseline_commit != before.commit:
            diff_payload = _successful(
                _run_git_command(
                    root,
                    (
                        *scope,
                        "diff",
                        "--name-only",
                        "--no-renames",
                        "--no-ext-diff",
                        "--no-textconv",
                        "-z",
                        baseline_commit,
                        before.commit,
                        "--",
                    ),
                    deadline,
                ),
                "Git diff",
            )
            diff_paths = _diff_paths(diff_payload)
        after = _capture_git_proof_state(root, scope, git_dir, deadline)
        _assert_stable_git_proof(before, after)
        if source_error is not None:
            raise source_error
        if prove_sources:
            assert required is not None and observed_before is not None
            if observed_before != required:
                raise _GitUnavailable("required source bytes do not match report evidence")
            if _hash_required_sources(root, required, deadline) != required:
                raise _GitUnavailable("required source bytes changed during freshness proof")
        changed = tuple(sorted(set(before.status_paths) | set(diff_paths)))
        if len(changed) > MAX_CHANGED_PATHS:
            raise _GitUnavailable("Git changed path count exceeds its limit")
        return _GitSnapshot(
            available=True,
            commit=before.commit,
            changed_paths=changed,
            changed_count=len(changed),
            worktree_clean=not before.status_paths,
            reason="Git freshness proof is complete",
        )
    except (_GitUnavailable, _LookupDeadline) as error:
        return _GitSnapshot(
            available=False,
            commit=None,
            changed_paths=(),
            changed_count=None,
            worktree_clean=False,
            reason=str(error),
        )


def _check_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise _LookupDeadline("previous lookup exceeded its operation deadline")


def _elapsed_ms(started_ns: int) -> int:
    return max(0, (time.monotonic_ns() - started_ns) // 1_000_000)


def _lookup_metrics(elapsed_ms: int, *, output: str | None = None):
    accounting = _accounting()
    cache_status = "hit" if accounting.reused_payloads else "miss"
    reused_bytes: int | None = sum(accounting.reused_payloads.values())
    bytes_read: int | None = accounting.bytes_read
    if accounting.bytes_read > PERFORMANCE.MAX_METRIC_BYTES:
        bytes_read = None
        accounting.exclusions.add("bounded read-byte accounting overflow")
    if reused_bytes is not None and reused_bytes > PERFORMANCE.MAX_METRIC_BYTES:
        reused_bytes = None
        accounting.exclusions.add("bounded reused-byte accounting overflow")
    return PERFORMANCE.PerformanceMetrics(
        previous_lookup=PERFORMANCE.PhaseMetric(
            elapsed_ms=elapsed_ms,
            bytes_read=bytes_read,
            serialized_bytes=0 if output is None else len(output.encode("utf-8")),
            cache_status=cache_status,
        ),
        accounted_reused_bytes=reused_bytes,
        accounting_exclusions=tuple(sorted(accounting.exclusions)),
        estimated_serialized_output_tokens=(
            0 if output is None else PERFORMANCE.estimate_tokens(output.encode("utf-8"))
        ),
        cache_status=cache_status,
        analysis_elapsed_ms=elapsed_ms,
        operation_elapsed_ms=elapsed_ms,
    )


def _unselected(
    status: Literal["none", "ambiguous"],
    requirement_sha256: str,
    reason: str,
    started_ns: int,
    candidates: tuple[PreviousReportCandidate, ...] = (),
) -> PreviousReportResult:
    elapsed_ms = _elapsed_ms(started_ns)
    return PreviousReportResult(
        status=status,
        report_id=None,
        revision=None,
        markdown_sha256=None,
        created_at=None,
        baseline_commit=None,
        changed_paths=(),
        changed_count=None,
        requirement_sha256=requirement_sha256,
        source_inventory_sha256=None,
        display_text=None,
        reason=reason,
        elapsed_ms=elapsed_ms,
        candidates=candidates,
        performance_metrics=_lookup_metrics(elapsed_ms),
    )


def _public_candidates(
    candidates: Sequence[_CurrentCandidate],
) -> tuple[PreviousReportCandidate, ...]:
    return tuple(
        PreviousReportCandidate(
            report_id=candidate.report_id,
            revision=candidate.revision,
            created_at=cast(str, cast(Any, candidate.context).created_at),
        )
        for candidate in candidates[:MAX_AMBIGUOUS_CANDIDATES]
    )


def _selected_result(
    status: Literal["fresh", "stale"],
    candidate: _CurrentCandidate,
    requirement_sha256: str,
    snapshot: _GitSnapshot,
    reason: str,
    started_ns: int,
) -> PreviousReportResult:
    context = candidate.context
    accounting = _ACCOUNTING.get()
    if accounting is not None:
        accounting.reuse(candidate.state_payload)
        accounting.reuse(candidate.markdown_payload)
    elapsed_ms = _elapsed_ms(started_ns)
    base = PreviousReportResult(
        status=status,
        report_id=candidate.report_id,
        revision=candidate.revision,
        markdown_sha256=candidate.markdown_sha256,
        created_at=getattr(context, "created_at", None),
        baseline_commit=getattr(context, "baseline_commit", None),
        changed_paths=snapshot.changed_paths,
        changed_count=snapshot.changed_count,
        requirement_sha256=requirement_sha256,
        source_inventory_sha256=getattr(context, "source_inventory_sha256", None),
        display_text=None,
        reason=reason,
        elapsed_ms=elapsed_ms,
        performance_metrics=_lookup_metrics(elapsed_ms),
    )
    try:
        display = RENDERER.render_previous(base, candidate.state)
    except (TypeError, ValueError, RecursionError):
        return _unselected(
            "none",
            requirement_sha256,
            "selected previous report could not be rendered safely",
            started_ns,
        )
    elapsed_ms = _elapsed_ms(started_ns)
    return replace(
        base,
        display_text=display,
        elapsed_ms=elapsed_ms,
        performance_metrics=_lookup_metrics(elapsed_ms, output=display),
    )


def _lookup_previous(request: PreviousLookupRequest) -> PreviousReportResult:
    """Select and compactly render one exact report lineage within 250 milliseconds."""

    if not isinstance(request, PreviousLookupRequest):
        raise TypeError("request must be PreviousLookupRequest")
    started_ns = time.monotonic_ns()
    deadline = time.monotonic() + OPERATION_TIMEOUT_SECONDS
    requirement_sha256 = REPORT_CONTEXT.canonical_requirement_sha256(request.request)
    repository_evidence_sha256 = REPORT_CONTEXT.canonical_repository_evidence_sha256(
        request.repository_evidence
    )
    root = _root(request.repo_root)
    try:
        payload_sha256 = _payload_sha256()
        _check_deadline(deadline)
        reports_fd = _open_reports_directory(root)
        if reports_fd is None:
            return _unselected(
                "none", requirement_sha256, "no previous report lineage exists", started_ns
            )
        try:
            report_ids = _report_ids(reports_fd, deadline)
            candidates = []
            for report_id in report_ids:
                candidate = _read_candidate(root, reports_fd, report_id, deadline)
                if candidate is not None:
                    candidates.append(candidate)
        finally:
            os.close(reports_fd)
    except _LookupDeadline:
        return _unselected(
            "none",
            requirement_sha256,
            "previous report identity could not be bounded",
            started_ns,
        )
    except (_UnsafeLookup, OSError, TypeError, ValueError):
        return _unselected(
            "none",
            requirement_sha256,
            "previous report identity is unsafe",
            started_ns,
        )
    requirement_matching = [
        candidate for candidate in candidates if candidate.requirement_sha256 == requirement_sha256
    ]
    context_matching = [
        candidate
        for candidate in requirement_matching
        if not candidate.incompatible_context and candidate.context is not None
    ]
    evidence_matching = [
        candidate
        for candidate in context_matching
        if getattr(candidate.context, "repository_evidence_sha256", None)
        == repository_evidence_sha256
    ]
    matching = [
        candidate
        for candidate in evidence_matching
        if candidate.context is not None
        and getattr(candidate.context, "payload_sha256", None) == payload_sha256
    ]
    if not matching:
        if requirement_matching and not context_matching:
            reason = "previous report schema or payload identity is incompatible with this runtime"
        elif context_matching and not evidence_matching:
            reason = "previous report evidence identity does not match"
        elif evidence_matching:
            reason = "previous report schema or payload identity is incompatible with this runtime"
        else:
            reason = "no previous report lineage matches the normalized requirement"
        return _unselected(
            "none",
            requirement_sha256,
            reason,
            started_ns,
        )
    public_candidates = _public_candidates(matching) if len(matching) > 1 else ()
    if request.report_id is not None:
        if public_candidates and request.report_id not in {
            candidate.report_id for candidate in public_candidates
        }:
            return _unselected(
                "none",
                requirement_sha256,
                "requested previous report is outside the disclosed candidate window",
                started_ns,
            )
        matching = [candidate for candidate in matching if candidate.report_id == request.report_id]
        if not matching:
            return _unselected(
                "none",
                requirement_sha256,
                "requested previous report does not match the private candidate set",
                started_ns,
            )
    if len(matching) != 1:
        return _unselected(
            "ambiguous",
            requirement_sha256,
            "multiple previous report lineages match the normalized requirement",
            started_ns,
            public_candidates,
        )
    candidate = matching[0]
    baseline_commit = getattr(candidate.context, "baseline_commit", None)
    context = candidate.context
    if context is None:  # pragma: no cover - selected candidates require a v2 context
        return _unselected(
            "none", requirement_sha256, "previous report context is unavailable", started_ns
        )
    can_attempt_fresh = (
        getattr(context, "source_inventory_available", False)
        and getattr(context, "source_inventory_complete", False)
        and getattr(context, "baseline_clean", False)
        and baseline_commit is not None
        and getattr(context, "source_inventory_git_tracked_only", False)
        and getattr(context, "source_recheck_complete", False)
    )
    required_source_digests = (
        getattr(context, "required_source_digests", None) if can_attempt_fresh else None
    )
    snapshot = _probe_git(root, baseline_commit, deadline, required_source_digests)
    if not getattr(context, "source_inventory_available", False) or not getattr(
        context, "source_inventory_complete", False
    ):
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            "source inventory is incomplete",
            started_ns,
        )
    if not getattr(context, "baseline_clean", False) or baseline_commit is None:
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            "report baseline was not clean",
            started_ns,
        )
    if not getattr(context, "source_inventory_git_tracked_only", False):
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            "source inventory is not proven Git-tracked",
            started_ns,
        )
    if not getattr(context, "source_recheck_complete", False):
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            "required source byte recheck is incomplete",
            started_ns,
        )
    if getattr(context, "required_source_digests", None) is None:
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            "required source digest map is unavailable",
            started_ns,
        )
    if not snapshot.available:
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            snapshot.reason,
            started_ns,
        )
    if not snapshot.worktree_clean:
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            "Git working tree contains tracked or untracked changes",
            started_ns,
        )
    if snapshot.commit != baseline_commit:
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            "Git HEAD differs from the report baseline",
            started_ns,
        )
    return _selected_result(
        "fresh",
        candidate,
        requirement_sha256,
        snapshot,
        "repository and report identities match a clean Git baseline",
        started_ns,
    )


def lookup_previous(request: PreviousLookupRequest) -> PreviousReportResult:
    accounting = _LookupAccounting()
    token = _ACCOUNTING.set(accounting)
    try:
        return _lookup_previous(request)
    finally:
        _ACCOUNTING.reset(token)
