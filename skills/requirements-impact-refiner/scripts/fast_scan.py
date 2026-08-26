"""Fast Scan domain contract and deterministic repository-backed seed derivation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, TypedDict, cast

if TYPE_CHECKING:
    from typing_extensions import TypeGuard

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import fast_scan_renderer
import fast_scan_store
import graph_builtin
import graph_coordinator

MAX_CHANGE_BYTES = 4 * 1024
MAX_EVIDENCE_ROWS = 32
MAX_EVIDENCE_BYTES = 4 * 1024
MAX_SEEDS = 16
MAX_DELTA_SEEDS = 512
MAX_SOURCE_BYTES = 1024 * 1024
MAX_FRONTIER = 1024
MAX_CANDIDATES = 3

_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_REPORT_ID = re.compile(r"^RPT-\d{3}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_PATH = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+"
)
_QUALIFIED = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"[A-Za-z_][A-Za-z0-9_-]*"
    r"(?:\.[A-Za-z_][A-Za-z0-9_-]*)+"
)
# Whole identifier segments across snake, kebab, and camel case, so
# prefixed, suffixed, and camelCase credential names (GITHUB_TOKEN,
# stripeSecretKey, tokenProd) are caught while fragments (tokenizer) are
# not; := is covered so walrus and Go declarations cannot slip through.
_SECRET = re.compile(
    r"(?i)(?<![A-Za-z0-9_])"
    r"(?:[A-Za-z0-9]+[_-]|(?-i:[A-Z]?[a-z0-9]+(?=[A-Z])))*"
    r"(?:api[_-]?key|api[_-]?token|api[_-]?secret|access[_-]?token|"
    r"auth[_-]?token|secret[_-]?key|token|secret|password|passwd|passphrase|"
    r"private[_-]?key|credential)"
    r"(?:[_-][A-Za-z0-9]+|(?-i:[A-Z][A-Za-z0-9]*))*"
    r"\s*(?::=|[:=])\s*\S+"
)
_SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".m",
    ".mm",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".sql",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".xml",
}
# Session-control directories plus the graph scanner's dependency and build
# directories, so scan identity is never bound to node_modules churn and
# dependency files are never read or hashed.
_CONTROL_PARTS = {
    ".git",
    ".mypy_cache",
    ".quality-venv",
    ".requirements-impact-refiner",
    "__pycache__",
    ".pytest_cache",
} | set(graph_builtin.IGNORED_DIRECTORIES)
_REQUIRED_KEYS = {
    "schema_version",
    "status",
    "scan_id",
    "receipt_id",
    "repo_root_sha256",
    "request_sha256",
    "payload_sha256",
    "settings",
    "source_inventory",
    "seeds",
    "graph_receipt",
    "risk_level",
    "frontier",
    "candidates",
    "elapsed_ms",
    "cache_status",
    "can_promote",
    "created_at",
}
_OPTIONAL_KEYS = {"delta_context"}
_STATUSES = {"complete", "partial", "needs_input"}
_RISKS = {"low", "medium", "high", "critical", "unknown"}
_CACHE = {"hit", "miss", "bypassed"}
_SEED_KEYS = {"term", "location", "derivation", "source_sha256"}
_CANDIDATE_KEYS = {"term", "location", "derivation"}


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class DerivedSeed:
    term: str
    location: str | None
    derivation: str
    source_sha256: str | None

    def to_mapping(self) -> dict[str, object]:
        return {
            "term": self.term,
            "location": self.location,
            "derivation": self.derivation,
            "source_sha256": self.source_sha256,
        }


@dataclass(frozen=True)
class FastScanRequest:
    repo_root: Path
    change_request: str
    evidence: tuple[str, ...]
    audience: str
    previous_report_id: str | None = None
    previous_revision: int | None = None
    changed_paths: tuple[str, ...] = ()
    delta_max_seconds: int = 3

    def __post_init__(self):
        object.__setattr__(self, "repo_root", Path(self.repo_root))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "changed_paths", tuple(self.changed_paths))


@dataclass(frozen=True)
class FastScanReceipt:
    schema_version: int
    status: str
    scan_id: str
    receipt_id: str
    repo_root_sha256: str
    request_sha256: str
    payload_sha256: str
    settings: Mapping[str, object]
    source_inventory: Mapping[str, object]
    seeds: tuple[DerivedSeed, ...]
    graph_receipt: Mapping[str, object]
    risk_level: str
    frontier: tuple[Mapping[str, object], ...]
    candidates: tuple[Mapping[str, object], ...]
    elapsed_ms: int
    cache_status: str
    can_promote: bool
    created_at: str
    delta_context: Mapping[str, object] | None = None

    def __post_init__(self):
        object.__setattr__(self, "settings", _freeze(self.settings))
        object.__setattr__(self, "source_inventory", _freeze(self.source_inventory))
        object.__setattr__(self, "seeds", tuple(self.seeds))
        object.__setattr__(self, "graph_receipt", _freeze(self.graph_receipt))
        object.__setattr__(self, "frontier", tuple(_freeze(row) for row in self.frontier))
        object.__setattr__(self, "candidates", tuple(_freeze(row) for row in self.candidates))
        if self.delta_context is not None:
            object.__setattr__(self, "delta_context", _freeze(self.delta_context))

    def to_mapping(self) -> dict[str, object]:
        value = {
            "schema_version": self.schema_version,
            "status": self.status,
            "scan_id": self.scan_id,
            "receipt_id": self.receipt_id,
            "repo_root_sha256": self.repo_root_sha256,
            "request_sha256": self.request_sha256,
            "payload_sha256": self.payload_sha256,
            "settings": _thaw(self.settings),
            "source_inventory": _thaw(self.source_inventory),
            "seeds": [seed.to_mapping() for seed in self.seeds],
            "graph_receipt": _thaw(self.graph_receipt),
            "risk_level": self.risk_level,
            "frontier": _thaw(self.frontier),
            "candidates": _thaw(self.candidates),
            "elapsed_ms": self.elapsed_ms,
            "cache_status": self.cache_status,
            "can_promote": self.can_promote,
            "created_at": self.created_at,
        }
        if self.delta_context is not None:
            value["delta_context"] = _thaw(self.delta_context)
        return value


@dataclass(frozen=True)
class FastScanResult:
    status: str
    scan_id: str
    receipt_id: str
    receipt_sha256: str
    display_text: str
    risk_level: str
    paths: tuple[Mapping[str, object], ...]
    frontier: tuple[Mapping[str, object], ...]
    candidates: tuple[Mapping[str, object], ...]
    elapsed_ms: int
    cache_status: str
    can_promote: bool
    previous_report_id: str | None = None
    previous_revision: int | None = None
    changed_paths: tuple[str, ...] = ()
    changed_count: int | None = None
    previous_display_text: str | None = None


@dataclass(frozen=True)
class PreparedFastScan:
    root: Path
    settings: graph_coordinator.GraphSettings
    deadline: graph_coordinator.Deadline
    seeds: tuple[DerivedSeed, ...]
    source_inventory: graph_coordinator.SourceInventory
    inventory_mapping: Mapping[str, object]
    request_sha256: str
    scan_id: str
    repo_root_sha256: str
    delta_context: Mapping[str, object] | None = None
    delta_seed_selection: object | None = None


def _root(value: Path) -> Path:
    path = Path(value)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"repository root is unavailable: {error}") from error
    if stat.S_ISLNK(metadata.st_mode) or not resolved.is_dir():
        raise ValueError("repository root must be a real directory")
    return resolved


class _StoredFastScan(TypedDict):
    schema_version: int
    status: str
    scan_id: str
    receipt_id: str
    repo_root_sha256: str
    request_sha256: str
    payload_sha256: str
    settings: Mapping[str, object]
    source_inventory: Mapping[str, object]
    seeds: list[Mapping[str, object]]
    graph_receipt: Mapping[str, object]
    risk_level: str
    frontier: list[Mapping[str, object]]
    candidates: list[Mapping[str, object]]
    elapsed_ms: int
    cache_status: str
    can_promote: bool
    created_at: str


class _GraphSettingsArgs(TypedDict, total=False):
    enabled: bool
    max_seconds: int
    target_seconds: int
    providers: tuple[str, ...]
    install_policy: str
    deep: bool


class _Coordinator(Protocol):
    def __call__(
        self,
        repo_root: Path,
        draft: object,
        seeds: tuple[graph_coordinator.ScanSeed, ...],
        settings: graph_coordinator.GraphSettings,
        *,
        deadline: graph_coordinator.Deadline,
        source_inventory: graph_coordinator.SourceInventory,
    ) -> object: ...


class _DeltaSeedContract(Protocol):
    term: str
    location: str | None
    derivation: str
    source_sha256: str | None


class _DeltaSeedSelectionContract(Protocol):
    seeds: tuple[_DeltaSeedContract, ...]
    omitted_count: int
    omitted_by_source: Mapping[str, int]


class _DeltaContext(Protocol):
    previous_report_id: str
    previous_revision: int
    changed_paths: tuple[str, ...]
    max_seconds: int
    previous_display_text: str

    def derive_seed_selection(
        self, request_seeds: Sequence[DerivedSeed] = ()
    ) -> _DeltaSeedSelectionContract: ...

    def to_mapping(self, selection: _DeltaSeedSelectionContract) -> dict[str, object]: ...

    def merge_frontier(
        self,
        graph: Mapping[str, object],
        selection: _DeltaSeedSelectionContract | None = None,
    ) -> tuple[Mapping[str, object], ...]: ...


def _safe_relative(value: object) -> TypeGuard[str]:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def _expired(deadline: object) -> bool:
    method = getattr(deadline, "expired", None)
    if not callable(method):
        raise TypeError("deadline must provide expired()")
    return bool(method())


def _terms(text: str) -> tuple[str, ...]:
    values = []
    for match in _QUALIFIED.finditer(text):
        value = match.group(0)
        if Path(value).suffix.lower() in _SOURCE_SUFFIXES:
            continue
        if value not in values:
            values.append(value)
    return tuple(values)


def _paths(text: str) -> tuple[str, ...]:
    matches: list[tuple[int, str]] = []
    for match in _PATH.finditer(text):
        value = match.group(0).rstrip(".,:;)")
        if _safe_relative(value):
            matches.append((match.start(), value))
    for match in _QUALIFIED.finditer(text):
        value = match.group(0).rstrip(".,:;)")
        if (
            Path(value).suffix.lower() in _SOURCE_SUFFIXES
            and (match.start() == 0 or text[match.start() - 1] not in "/\\")
            and (match.end() == len(text) or text[match.end()] not in "/\\")
            and _safe_relative(value)
        ):
            matches.append((match.start(), value))
    values = []
    for _offset, value in sorted(matches):
        if value not in values:
            values.append(value)
    return tuple(values)


def explicit_path_candidates(change_request: str, evidence: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(change_request, str) or not isinstance(evidence, (tuple, list)):
        raise TypeError("explicit path inputs are invalid")
    values: list[str] = []
    for text in (change_request, *evidence):
        if not isinstance(text, str):
            raise TypeError("explicit path evidence must be text")
        for path in _paths(text):
            if path not in values:
                values.append(path)
                if len(values) > MAX_SEEDS:
                    raise ValueError("explicit path candidates exceed their limit")
    return tuple(values)


def _read_source(root: Path, relative: str) -> tuple[str, str] | None:
    return _read_source_detailed(root, relative)[0]


def _read_source_detailed(root: Path, relative: str) -> tuple[tuple[str, str] | None, str | None]:
    """Read a source file; on failure, say whether the content is
    legitimately outside a text inventory (binary, encoding) or genuinely
    unaccounted for (permission, mutation, oversize)."""
    if not _safe_relative(relative):
        return None, "control"
    parts = PurePosixPath(relative).parts
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    root_fd = None
    parent_fd = None
    descriptor = None
    try:
        root_fd = os.open(root, directory_flags)
        parent_fd = root_fd
        for part in parts[:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=parent_fd)
            if parent_fd != root_fd:
                os.close(parent_fd)
            parent_fd = next_fd
        descriptor = os.open(parts[-1], file_flags, dir_fd=parent_fd)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return None, "not-regular"
        if before.st_size > MAX_SOURCE_BYTES:
            return None, "unreadable-source"
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                return None, "unreadable-source"
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            return None, "unreadable-source"
        raw = b"".join(chunks)
        if b"\x00" in raw:
            return None, "binary"
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None, "encoding"
        return (text, hashlib.sha256(raw).hexdigest()), None
    except OSError:
        return None, "unreadable-source"
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None and parent_fd != root_fd:
            os.close(parent_fd)
        if root_fd is not None:
            os.close(root_fd)


def _source_files(root: Path, deadline: object, explicit_paths: Sequence[str] = ()):
    seen: set[str] = set()
    for directory, names, files in os.walk(root, followlinks=False):
        if _expired(deadline):
            return
        relative_directory = Path(directory).relative_to(root)
        kept = []
        for name in sorted(names):
            parts = (*relative_directory.parts, name)
            if name in _CONTROL_PARTS:
                continue
            if len(parts) >= 2 and parts[:2] == ("evals", "results"):
                continue
            path = Path(directory) / name
            try:
                if path.is_symlink():
                    continue
            except OSError:
                continue
            kept.append(name)
        names[:] = kept
        for name in sorted(files):
            if _expired(deadline):
                return
            path = Path(directory) / name
            try:
                relative = path.relative_to(root).as_posix()
                if path.is_symlink() or path.suffix.lower() not in _SOURCE_SUFFIXES:
                    continue
            except OSError:
                continue
            seen.add(relative)
            yield relative
    for relative in explicit_paths:
        if _expired(deadline):
            return
        if relative in seen or not _safe_relative(relative):
            continue
        if Path(relative).suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        yield relative


def _validate_inputs(
    change_request: str,
    evidence: tuple[str, ...],
    deadline: object,
    maximum: int,
) -> None:
    if not isinstance(change_request, str) or not change_request.strip():
        raise ValueError("change request must be nonblank")
    if len(change_request.encode("utf-8")) > MAX_CHANGE_BYTES:
        raise ValueError("change request exceeds 4 KiB")
    if not isinstance(evidence, (tuple, list)) or len(evidence) > MAX_EVIDENCE_ROWS:
        raise ValueError("evidence must contain at most 32 rows")
    for row in evidence:
        if not isinstance(row, str) or not row.strip():
            raise ValueError("evidence rows must be nonblank strings")
        if len(row.encode("utf-8")) > MAX_EVIDENCE_BYTES:
            raise ValueError("evidence row exceeds 4 KiB")
        if _SECRET.search(row):
            raise ValueError("credential-shaped evidence is not allowed")
    if (
        not isinstance(maximum, int)
        or isinstance(maximum, bool)
        or maximum < 1
        or maximum > MAX_SEEDS
    ):
        raise ValueError("maximum seeds must be an integer from 1 to 16")
    _expired(deadline)


def derive_seeds(
    repo_root: Path,
    change_request: str,
    evidence: tuple[str, ...],
    deadline: object,
    maximum: int = MAX_SEEDS,
) -> tuple[DerivedSeed, ...]:
    """Derive stable, repository-backed seeds without model-authored graph data."""
    evidence = tuple(evidence)
    _validate_inputs(change_request, evidence, deadline, maximum)
    root = _root(repo_root)
    if _expired(deadline):
        return ()

    ordered: list[DerivedSeed] = []
    seen: set[tuple[str, str | None]] = set()

    def add(term: str, location: str, derivation: str) -> None:
        if len(ordered) >= maximum or (term, location) in seen:
            return
        source = _read_source(root, location)
        if source is None or term not in source[0]:
            return
        seen.add((term, location))
        ordered.append(DerivedSeed(term, location, derivation, source[1]))

    def add_path(location: str, derivation: str) -> None:
        if len(ordered) >= maximum or (location, location) in seen:
            return
        source = _read_source(root, location)
        if source is None:
            return
        seen.add((location, location))
        ordered.append(DerivedSeed(location, location, derivation, source[1]))

    request_terms = _terms(change_request)
    for location in _paths(change_request):
        if request_terms:
            for term in request_terms:
                add(term, location, "request-path-symbol")
        else:
            add_path(location, "request-path-only")

    all_terms = list(request_terms)
    for row in evidence:
        row_terms = _terms(row)
        for term in row_terms:
            if term not in all_terms:
                all_terms.append(term)
        for location in _paths(row):
            if row_terms:
                for term in row_terms:
                    add(term, location, "evidence-path-symbol")
            else:
                add_path(location, "evidence-path-only")

    if len(ordered) < maximum:
        files = tuple(_source_files(root, deadline))
        # Read each candidate file once for the whole term sweep; the
        # (term, file) pair-product of reads dominated scan wall time.
        source_cache: dict[str, tuple[str, str] | None] = {}

        def _cached_source(relative: str) -> tuple[str, str] | None:
            if relative not in source_cache:
                source_cache[relative] = _read_source(root, relative)
            return source_cache[relative]

        for term in all_terms:
            for relative in files:
                if len(ordered) >= maximum or _expired(deadline):
                    break
                if (term, relative) in seen:
                    continue
                source = _cached_source(relative)
                if source is not None and term in source[0]:
                    seen.add((term, relative))
                    ordered.append(DerivedSeed(term, relative, "repository-match", source[1]))
    return tuple(ordered)


def _mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping) and all(isinstance(key, str) for key in value)


def _string(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value.strip())


def _rows(value: object) -> TypeGuard[Sequence[Mapping[str, object]]]:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and all(_mapping(row) for row in value)
    )


def _values(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _row_tuple(value: object) -> tuple[Mapping[str, object], ...]:
    return tuple(value) if _rows(value) else ()


_DELTA_CONTEXT_KEYS = {
    "previous_report_id",
    "previous_revision",
    "previous_markdown_sha256",
    "previous_state_sha256",
    "previous_graph_receipt_id",
    "previous_graph_sha256",
    "previous_display_text",
    "changed_paths",
    "changed_count",
    "max_seconds",
    "seed_provenance",
    "omitted_seed_count",
    "omitted_seed_provenance",
    "previous_frontier",
}


def _validate_delta_mapping(value: object, seeds: object) -> tuple[str, ...]:
    errors: list[str] = []
    if not _mapping(value) or set(value) != _DELTA_CONTEXT_KEYS:
        return ("delta_context must have exact fields",)
    report_id = value["previous_report_id"]
    if not isinstance(report_id, str) or _REPORT_ID.fullmatch(report_id) is None:
        errors.append("delta_context previous_report_id is invalid")
    revision = value["previous_revision"]
    if type(revision) is not int or revision < 1:
        errors.append("delta_context previous_revision is invalid")
    graph_receipt_id = value["previous_graph_receipt_id"]
    if not isinstance(graph_receipt_id, str) or _HEX32.fullmatch(graph_receipt_id) is None:
        errors.append("delta_context previous_graph_receipt_id is invalid")
    for key in (
        "previous_markdown_sha256",
        "previous_state_sha256",
        "previous_graph_sha256",
    ):
        digest = value[key]
        if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
            errors.append(f"delta_context {key} is invalid")
    display = value["previous_display_text"]
    try:
        display_valid = (
            isinstance(display, str)
            and bool(display.strip())
            and len(display.encode("utf-8")) <= 256 * 1024
        )
    except UnicodeEncodeError:
        display_valid = False
    if not display_valid:
        errors.append("delta_context previous_display_text is invalid")
    paths = value["changed_paths"]
    if (
        not isinstance(paths, list)
        or any(not _safe_relative(path) for path in paths)
        or sorted(set(paths)) != paths
    ):
        errors.append("delta_context changed_paths are invalid")
    count = value["changed_count"]
    if count is not None and (
        type(count) is not int or not isinstance(paths, list) or count < len(paths)
    ):
        errors.append("delta_context changed_count is invalid")
    maximum = value["max_seconds"]
    if type(maximum) is not int or not 1 <= maximum <= 3:
        errors.append("delta_context max_seconds must be an integer from 1 to 3")
    provenance = value["seed_provenance"]
    if (
        not isinstance(provenance, list)
        or not isinstance(seeds, list)
        or len(provenance) != len(seeds)
    ):
        errors.append("delta_context seed_provenance must match seeds")
    else:
        for row in provenance:
            if (
                not _mapping(row)
                or set(row) != {"term", "location", "derivation", "provenance"}
                or not _string(row["term"])
                or (row["location"] is not None and not _safe_relative(row["location"]))
                or not _string(row["derivation"])
                or not _mapping(row["provenance"])
            ):
                errors.append("delta_context seed_provenance is invalid")
                break
    omitted_count = value["omitted_seed_count"]
    omitted_provenance = value["omitted_seed_provenance"]
    if (
        type(omitted_count) is not int
        or omitted_count < 0
        or not _mapping(omitted_provenance)
        or any(type(count) is not int or count < 1 for count in omitted_provenance.values())
        or sum(cast(int, count) for count in omitted_provenance.values()) != omitted_count
    ):
        errors.append("delta_context omitted seed provenance is invalid")
    previous_frontier = value["previous_frontier"]
    if (
        not isinstance(previous_frontier, list)
        or len(previous_frontier) > 512
        or any(not _mapping(row) for row in previous_frontier)
    ):
        errors.append("delta_context previous_frontier is invalid")
    return tuple(errors)


def validate_fast_scan_receipt(value: object) -> tuple[str, ...]:
    errors: list[str] = []
    if not _mapping(value):
        return ("fast scan receipt must be an object",)
    keys = set(value)
    for key in sorted(_REQUIRED_KEYS - keys):
        errors.append(f"missing top-level key {key}")
    for key in sorted(keys - _REQUIRED_KEYS - _OPTIONAL_KEYS):
        errors.append(f"unknown top-level key {key}")
    if _REQUIRED_KEYS - keys:
        return tuple(errors)

    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        errors.append("schema_version must be 1")
    status = value["status"]
    status_valid = isinstance(status, str) and status in _STATUSES
    if not status_valid:
        errors.append("status is invalid")
    for key in ("scan_id", "receipt_id"):
        identifier = value[key]
        if not isinstance(identifier, str) or _HEX32.fullmatch(identifier) is None:
            errors.append(f"{key} must be 32 lowercase hex characters")
    for key in ("repo_root_sha256", "request_sha256", "payload_sha256"):
        digest_value = value[key]
        if not isinstance(digest_value, str) or _HEX64.fullmatch(digest_value) is None:
            errors.append(f"{key} must be 64 lowercase hex characters")
    if not _mapping(value["settings"]):
        errors.append("settings must be an object")

    inventory = value["source_inventory"]
    inventory_valid = False
    inventory_complete_valid = False
    if not _mapping(inventory) or set(inventory) != {"digests", "complete", "reason"}:
        errors.append("source_inventory must have exact fields")
    else:
        inventory_valid = True
        digests = inventory["digests"]
        if not _mapping(digests):
            errors.append("source_inventory digests must be an object")
        else:
            for location, digest in digests.items():
                if (
                    not _safe_relative(location)
                    or not isinstance(digest, str)
                    or _HEX64.fullmatch(digest) is None
                ):
                    errors.append("source_inventory contains an unsafe path or digest")
                    break
        inventory_complete = inventory["complete"]
        inventory_complete_valid = isinstance(inventory_complete, bool)
        if not inventory_complete_valid:
            errors.append("source_inventory complete must be boolean")
        inventory_reason = inventory["reason"]
        inventory_reason_valid = inventory_reason is None or _string(inventory_reason)
        if not inventory_reason_valid:
            errors.append("source_inventory reason must be null or nonblank text")
        if inventory_complete_valid and inventory_reason_valid:
            if inventory_complete is True and inventory_reason is not None:
                errors.append("complete source_inventory cannot have a reason")
            if inventory_complete is False and inventory_reason is None:
                errors.append("incomplete source_inventory requires a reason")

    delta_value = value.get("delta_context")
    if delta_value is not None:
        errors.extend(_validate_delta_mapping(delta_value, value["seeds"]))
    seeds = value["seeds"]
    seed_maximum = MAX_DELTA_SEEDS if delta_value is not None else MAX_SEEDS
    if not isinstance(seeds, list) or len(seeds) > seed_maximum:
        errors.append("seeds exceeds maximum collection size")
    else:
        identities = set()
        for index, row in enumerate(seeds, start=1):
            if not _mapping(row) or set(row) != _SEED_KEYS:
                errors.append(f"seed row {index} must have exact fields")
                continue
            term = row["term"]
            term_valid = _string(term)
            if not term_valid:
                errors.append(f"seed row {index} term must be nonblank")
            seed_location = row["location"]
            location_valid = seed_location is None or _safe_relative(seed_location)
            if not location_valid:
                errors.append(f"seed row {index} location is unsafe")
            derivation = row["derivation"]
            if not _string(derivation):
                errors.append(f"seed row {index} derivation must be nonblank")
            digest = row["source_sha256"]
            if digest is not None and (
                not isinstance(digest, str) or _HEX64.fullmatch(digest) is None
            ):
                errors.append(f"seed row {index} source_sha256 is invalid")
            if term_valid and location_valid:
                identity = (term, seed_location)
                if identity in identities:
                    errors.append(f"duplicate seed row {index}")
                identities.add(identity)

    graph_receipt_valid = _mapping(value["graph_receipt"])
    if not graph_receipt_valid:
        errors.append("graph_receipt must be an object")
    risk_level = value["risk_level"]
    if not isinstance(risk_level, str) or risk_level not in _RISKS:
        errors.append("risk_level is invalid")
    frontier = value["frontier"]
    if not isinstance(frontier, list) or len(frontier) > MAX_FRONTIER:
        errors.append("frontier exceeds maximum collection size")
    else:
        for index, row in enumerate(frontier, start=1):
            if not _mapping(row):
                errors.append(f"frontier row {index} must be an object")
    candidates = value["candidates"]
    if not isinstance(candidates, list) or len(candidates) > MAX_CANDIDATES:
        errors.append("candidates exceeds maximum collection size")
    else:
        for index, row in enumerate(candidates, start=1):
            if not _mapping(row) or set(row) != _CANDIDATE_KEYS:
                errors.append(f"candidate row {index} must have exact fields")
                continue
            if not _string(row["term"]) or not _string(row["derivation"]):
                errors.append(f"candidate row {index} must be substantive")
            if row["location"] is not None and not _safe_relative(row["location"]):
                errors.append(f"candidate row {index} location is unsafe")
    elapsed_ms = value["elapsed_ms"]
    if type(elapsed_ms) is not int or elapsed_ms < 0 or elapsed_ms > 30_000:
        errors.append("elapsed_ms must be an integer from 0 to 30000")
    cache_status = value["cache_status"]
    if not isinstance(cache_status, str) or cache_status not in _CACHE:
        errors.append("cache_status is invalid")
    can_promote = value["can_promote"]
    can_promote_valid = isinstance(can_promote, bool)
    if not can_promote_valid:
        errors.append("can_promote must be boolean")
    if (
        not isinstance(value["created_at"], str)
        or _TIMESTAMP.fullmatch(value["created_at"]) is None
    ):
        errors.append("created_at must be RFC 3339 UTC text")

    if status_valid and status == "needs_input":
        if can_promote_valid and can_promote:
            errors.append("needs_input scan cannot be promoted")
        if isinstance(seeds, list) and (seeds or (graph_receipt_valid and value["graph_receipt"])):
            errors.append("needs_input scan cannot contain graph evidence")
        if isinstance(risk_level, str) and risk_level in _RISKS and risk_level != "unknown":
            errors.append("needs_input risk_level must be unknown")
        if delta_value is not None:
            errors.append("delta scan cannot require input")
    elif status_valid and status == "partial":
        if can_promote_valid and can_promote:
            errors.append("partial scan cannot be promoted")
        if isinstance(candidates, list) and candidates:
            errors.append("partial scan cannot contain candidates")
    elif status_valid and status == "complete":
        if can_promote_valid and not can_promote:
            errors.append("complete scan must be promotable")
        if isinstance(candidates, list) and candidates:
            errors.append("complete scan cannot contain candidates")
        if graph_receipt_valid and not value["graph_receipt"]:
            errors.append("complete scan requires graph_receipt")
        if (
            inventory_valid
            and inventory_complete_valid
            and _mapping(inventory)
            and inventory.get("complete") is not True
        ):
            errors.append("complete scan requires complete source inventory")
    return tuple(errors)


def canonical_fast_scan_bytes(value: Mapping[str, object] | FastScanReceipt) -> bytes:
    try:
        mapping = value.to_mapping() if isinstance(value, FastScanReceipt) else value
        errors = validate_fast_scan_receipt(mapping)
    except (RecursionError, TypeError) as error:
        raise ValueError("invalid fast scan receipt: malformed value") from error
    if errors:
        raise ValueError("invalid fast scan receipt: " + "; ".join(errors))
    try:
        return json.dumps(
            mapping, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (RecursionError, TypeError, ValueError) as error:
        raise ValueError("invalid fast scan receipt: value is not canonical JSON") from error


def _graph_mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        thawed = _thaw(value)
        if _mapping(thawed):
            return dict(thawed)
        raise ValueError("graph receipt must be an object")
    loaded: object = json.loads(graph_coordinator.GRAPH.canonical_receipt_bytes(value))
    if not _mapping(loaded):
        raise ValueError("graph receipt must be an object")
    return dict(loaded)


_BENIGN_SKIPS = {"binary", "encoding", "not-regular", "control"}
_PROVIDER_UNAVAILABLE_REASON = re.compile(
    r"provider unavailable; built-in fallback used: "
    r"[A-Za-z0-9_.+-]+(?:, [A-Za-z0-9_.+-]+)*"
)
_KOREAN_TEXT = re.compile(r"[\u3131-\u318e\uac00-\ud7a3]")
_JAPANESE_TEXT = re.compile(r"[\u3040-\u30ff]")


def _request_locale(request: FastScanRequest) -> str:
    text = request.change_request + " " + " ".join(request.evidence)
    if _KOREAN_TEXT.search(text):
        return "ko"
    if _JAPANESE_TEXT.search(text):
        return "ja"
    return "en"


def _only_expected_provider_gap(graph: Mapping[str, object]) -> bool:
    provider_value = graph.get("providers", [])
    providers = provider_value if _rows(provider_value) else ()
    unavailable = sorted(
        {
            str(row.get("name"))
            for row in providers
            if isinstance(row, Mapping)
            and row.get("name") != "builtin"
            and row.get("status") != "ready"
        }
    )
    if not unavailable:
        return False
    expected = "provider unavailable; built-in fallback used: " + ", ".join(unavailable)
    frontier_value = graph.get("frontier", [])
    frontier = frontier_value if _rows(frontier_value) else ()
    return (
        len(frontier) == 1
        and str(frontier[0].get("reason", "")) == expected
        and _PROVIDER_UNAVAILABLE_REASON.fullmatch(expected) is not None
    )


def _inventory(
    root: Path,
    deadline: graph_coordinator.Deadline,
    explicit_paths: Sequence[str] = (),
) -> graph_coordinator.SourceInventory:
    digests: dict[str, str] = {}
    unreadable = False
    for relative in _source_files(root, deadline, explicit_paths):
        source, reason = _read_source_detailed(root, relative)
        if source is not None:
            digests[relative] = source[1]
        elif reason not in _BENIGN_SKIPS:
            unreadable = True
    if _expired(deadline):
        return graph_coordinator.SourceInventory(digests, False, "deadline")
    if unreadable:
        return graph_coordinator.SourceInventory(digests, False, "unreadable-source")
    return graph_coordinator.SourceInventory(digests, True, None)


def _delta_hints_present(request: FastScanRequest) -> bool:
    return (
        request.previous_report_id is not None
        or request.previous_revision is not None
        or bool(request.changed_paths)
    )


def _validated_delta_context(request: FastScanRequest, value: object) -> _DeltaContext | None:
    if value is None:
        if _delta_hints_present(request):
            raise ValueError("delta hints require a trusted delta context")
        return None
    required = (
        "previous_report_id",
        "previous_revision",
        "changed_paths",
        "max_seconds",
        "previous_display_text",
        "derive_seed_selection",
        "to_mapping",
        "merge_frontier",
    )
    if any(not hasattr(value, name) for name in required):
        raise TypeError("delta_context has an incomplete trusted contract")
    trusted = cast(_DeltaContext, value)
    if (
        request.previous_report_id is None
        or request.previous_revision is None
        or request.previous_report_id != trusted.previous_report_id
        or request.previous_revision != trusted.previous_revision
        or request.changed_paths != trusted.changed_paths
    ):
        raise ValueError("scan delta hints do not match trusted delta context")
    if (
        type(request.delta_max_seconds) is not int
        or request.delta_max_seconds < 1
        or trusted.max_seconds != min(request.delta_max_seconds, 3)
    ):
        raise ValueError("scan delta_max_seconds does not match trusted delta context")
    return trusted


def _delta_result_fields(
    delta_mapping: object,
) -> tuple[str | None, int | None, tuple[str, ...], int | None, str | None]:
    if not _mapping(delta_mapping):
        return None, None, (), None, None
    report_id = delta_mapping.get("previous_report_id")
    revision = delta_mapping.get("previous_revision")
    changed = delta_mapping.get("changed_paths")
    count = delta_mapping.get("changed_count")
    display = delta_mapping.get("previous_display_text")
    return (
        report_id if isinstance(report_id, str) else None,
        revision if type(revision) is int else None,
        tuple(changed) if isinstance(changed, list) else (),
        count if type(count) is int else None,
        display if isinstance(display, str) else None,
    )


def _display_with_previous(previous: str | None, current: str) -> str:
    if previous is None:
        return current
    return previous.rstrip() + "\n\n" + current.lstrip()


def _risk(graph: Mapping[str, object]) -> str:
    collections = []
    for key in ("nodes", "frontier"):
        value = graph.get(key, [])
        collections.append(value if _rows(value) else ())
    domains = {
        str(domain)
        for collection in collections
        for row in collection
        for domain_value in (row.get("risk_domains", []),)
        if _values(domain_value)
        for domain in domain_value
    }
    if domains & {"authorization/privacy", "legal/policy"}:
        return "critical"
    if domains & {"data", "interfaces", "operations", "state/concurrency"}:
        return "high"
    return "medium" if graph.get("nodes") else "low"


def execute_fast_scan(
    request: FastScanRequest,
    graph_settings: Mapping[str, object],
    payload_sha256: str,
    *,
    coordinator: _Coordinator = graph_coordinator.trace_impact,
    delta_context: object | None = None,
    operation_started: float | None = None,
) -> FastScanResult:
    delta_context = _validated_delta_context(request, delta_context)
    prepared = prepare_fast_scan_identity(
        request,
        graph_settings,
        payload_sha256,
        delta_context,
        operation_started=operation_started,
    )
    locale = _request_locale(request)
    root = prepared.root
    settings = prepared.settings
    deadline = prepared.deadline
    seeds = prepared.seeds
    source_inventory = prepared.source_inventory
    inventory_mapping = prepared.inventory_mapping
    request_sha = prepared.request_sha256
    scan_id = prepared.scan_id
    root_sha = prepared.repo_root_sha256
    delta_mapping = prepared.delta_context
    delta_seed_selection = (
        None
        if prepared.delta_seed_selection is None
        else cast(_DeltaSeedSelectionContract, prepared.delta_seed_selection)
    )

    try:
        existing_payload = fast_scan_store.load_scan_receipt_bytes(root, scan_id)
    except FileNotFoundError:
        existing_payload = None
    if existing_payload is not None:
        existing_value: object = json.loads(existing_payload)
        errors = validate_fast_scan_receipt(existing_value)
        if (
            not _mapping(existing_value)
            or errors
            or existing_value.get("request_sha256") != request_sha
        ):
            raise ValueError("existing fast scan receipt is invalid")
        existing = cast(_StoredFastScan, existing_value)
        rendered = dict(existing)
        rendered["cache_status"] = "hit"
        display = fast_scan_renderer.render_fast_scan(rendered, request.audience, locale)
        graph = existing["graph_receipt"]
        (
            previous_report_id,
            previous_revision,
            changed_paths,
            changed_count,
            previous_display,
        ) = _delta_result_fields(existing.get("delta_context"))
        return FastScanResult(
            existing["status"],
            scan_id,
            existing["receipt_id"],
            hashlib.sha256(existing_payload).hexdigest(),
            _display_with_previous(previous_display, display),
            existing["risk_level"],
            _row_tuple(graph.get("paths", [])),
            tuple(existing["frontier"]),
            tuple(existing["candidates"]),
            deadline.elapsed_ms()
            if delta_context is not None
            else min(30_000, deadline.elapsed_ms()),
            "hit",
            existing["can_promote"],
            previous_report_id,
            previous_revision,
            changed_paths,
            changed_count,
            previous_display,
        )
    candidates: list[Mapping[str, object]] = []
    merged_frontier: tuple[Mapping[str, object], ...] = ()
    if not seeds and delta_context is None:
        graph = {}
        status = "needs_input"
        receipt_id = hashlib.sha256((scan_id + ":needs-input").encode()).hexdigest()[:32]
        risk_level = "unknown"
        cache_status = "bypassed"
    elif not seeds:
        graph = {}
        status = "partial"
        receipt_id = hashlib.sha256((scan_id + ":delta-no-seed").encode()).hexdigest()[:32]
        risk_level = "unknown"
        cache_status = "bypassed"
    else:
        graph = _graph_mapping(
            coordinator(
                root,
                {"draft_id": scan_id},
                tuple(graph_coordinator.ScanSeed(row.term, row.location) for row in seeds),
                settings,
                deadline=deadline,
                source_inventory=source_inventory,
            )
        )
        receipt_value = graph["receipt_id"]
        if not isinstance(receipt_value, str):
            raise ValueError("graph receipt_id is invalid")
        receipt_id = receipt_value
        # A missing optional provider alone must not make the documented
        # promotion path unreachable on default installs — but only when
        # every frontier entry is that disclosure. Any other frontier
        # reason (coverage gap, deadline, disagreement) keeps the scan
        # partial and unpromotable.
        only_provider_gaps = _only_expected_provider_gap(graph)
        status = (
            "complete"
            if source_inventory.complete
            and (
                graph.get("budget_status") == "closed"
                or (graph.get("budget_status") == "provider_limited" and only_provider_gaps)
            )
            else "partial"
        )
        risk_level = _risk(graph)
        cache_value = graph.get("cache", {})
        cache_mapping = cache_value if _mapping(cache_value) else {}
        cache_status = str(cache_mapping.get("status", "bypassed"))
    if delta_context is not None:
        merged_value = delta_context.merge_frontier(graph, delta_seed_selection)
        if not isinstance(merged_value, tuple) or any(
            not isinstance(row, Mapping) for row in merged_value
        ):
            raise TypeError("trusted delta frontier contract is invalid")
        merged_frontier = merged_value
        if status != "needs_input" and (
            graph.get("budget_status") != "closed"
            or not source_inventory.complete
            or merged_frontier
        ):
            status = "partial"
    else:
        merged_frontier = _row_tuple(graph.get("frontier", []))
    elapsed = (
        deadline.elapsed_ms() if delta_context is not None else min(30_000, deadline.elapsed_ms())
    )
    receipt = FastScanReceipt(
        1,
        status,
        scan_id,
        receipt_id,
        root_sha,
        request_sha,
        payload_sha256,
        settings.to_mapping(),
        inventory_mapping,
        seeds,
        graph,
        risk_level,
        merged_frontier,
        tuple(candidates),
        elapsed,
        cache_status,
        status == "complete",
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        delta_mapping,
    )
    payload = canonical_fast_scan_bytes(receipt)
    fast_scan_store.publish_scan_receipt(root, scan_id, payload)
    mapping = receipt.to_mapping()
    display = fast_scan_renderer.render_fast_scan(mapping, request.audience, locale)
    digest = hashlib.sha256(payload).hexdigest()
    (
        previous_report_id,
        previous_revision,
        changed_paths,
        changed_count,
        previous_display,
    ) = _delta_result_fields(delta_mapping)
    return FastScanResult(
        status,
        scan_id,
        receipt_id,
        digest,
        _display_with_previous(previous_display, display),
        risk_level,
        _row_tuple(graph.get("paths", [])),
        merged_frontier,
        tuple(candidates),
        elapsed,
        cache_status,
        status == "complete",
        previous_report_id,
        previous_revision,
        changed_paths,
        changed_count,
        previous_display,
    )


def prepare_fast_scan_identity(
    request: FastScanRequest,
    graph_settings: Mapping[str, object],
    payload_sha256: str,
    delta_context: object | None = None,
    *,
    operation_started: float | None = None,
) -> PreparedFastScan:
    root = _root(request.repo_root)
    delta_context = _validated_delta_context(request, delta_context)
    if not isinstance(payload_sha256, str) or _HEX64.fullmatch(payload_sha256) is None:
        raise ValueError("payload_sha256 must be 64 lowercase hex characters")
    settings_mapping = dict(graph_settings)
    settings_errors: list[str] = []
    graph_coordinator.GRAPH._validate_settings(settings_mapping, settings_errors)
    if settings_errors:
        raise ValueError("invalid graph settings: " + "; ".join(settings_errors))
    if delta_context is not None:
        effective_maximum = min(
            cast(int, settings_mapping["max_seconds"]),
            delta_context.max_seconds,
        )
        settings_mapping["max_seconds"] = effective_maximum
        settings_mapping["target_seconds"] = min(
            cast(int, settings_mapping["target_seconds"]), effective_maximum
        )
    constructor_mapping = dict(settings_mapping)
    constructor_mapping["providers"] = tuple(cast(list[str], settings_mapping["providers"]))
    settings = graph_coordinator.GraphSettings(**cast(_GraphSettingsArgs, constructor_mapping))
    deadline = graph_coordinator.Deadline(time, settings.max_seconds, started=operation_started)
    request_seeds = derive_seeds(root, request.change_request, request.evidence, deadline)
    if delta_context is None:
        seeds = request_seeds
        delta_mapping = None
        delta_seed_selection = None
    else:
        delta_seed_selection = delta_context.derive_seed_selection(request_seeds)
        derived = delta_seed_selection.seeds
        if not isinstance(derived, tuple):
            raise TypeError("trusted delta seed contract is invalid")
        seeds = tuple(
            DerivedSeed(
                row.term,
                row.location,
                row.derivation,
                row.source_sha256,
            )
            for row in derived
        )
        delta_mapping_value = delta_context.to_mapping(delta_seed_selection)
        if not _mapping(delta_mapping_value):
            raise TypeError("trusted delta context mapping is invalid")
        delta_mapping = dict(delta_mapping_value)
    source_inventory = _inventory(root, deadline)
    inventory_mapping = {
        "digests": dict(source_inventory.digests),
        "complete": source_inventory.complete,
        "reason": source_inventory.reason,
    }
    identity_value = {
        "root": str(root),
        "change_request": request.change_request,
        "evidence": list(request.evidence),
        "settings": settings.to_mapping(),
        "payload_sha256": payload_sha256,
        "source_inventory": inventory_mapping,
        "seeds": [row.to_mapping() for row in seeds],
    }
    if delta_mapping is not None:
        identity_value["delta_context"] = delta_mapping
    identity = json.dumps(
        identity_value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_sha = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    scan_id = request_sha[:32]
    root_sha = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
    return PreparedFastScan(
        root,
        settings,
        deadline,
        seeds,
        source_inventory,
        inventory_mapping,
        request_sha,
        scan_id,
        root_sha,
        delta_mapping,
        delta_seed_selection,
    )


__all__ = [
    "DerivedSeed",
    "FastScanReceipt",
    "FastScanRequest",
    "FastScanResult",
    "PreparedFastScan",
    "canonical_fast_scan_bytes",
    "derive_seeds",
    "execute_fast_scan",
    "explicit_path_candidates",
    "prepare_fast_scan_identity",
    "validate_fast_scan_receipt",
]
