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
from typing import Protocol, cast

from typing_extensions import TypedDict, TypeGuard

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
MAX_SOURCE_BYTES = 1024 * 1024
MAX_FRONTIER = 128
MAX_CANDIDATES = 3

_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
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

    def __post_init__(self):
        object.__setattr__(self, "repo_root", Path(self.repo_root))
        object.__setattr__(self, "evidence", tuple(self.evidence))


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

    def __post_init__(self):
        object.__setattr__(self, "settings", _freeze(self.settings))
        object.__setattr__(self, "source_inventory", _freeze(self.source_inventory))
        object.__setattr__(self, "seeds", tuple(self.seeds))
        object.__setattr__(self, "graph_receipt", _freeze(self.graph_receipt))
        object.__setattr__(self, "frontier", tuple(_freeze(row) for row in self.frontier))
        object.__setattr__(self, "candidates", tuple(_freeze(row) for row in self.candidates))

    def to_mapping(self) -> dict[str, object]:
        return {
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
    values = []
    for match in _PATH.finditer(text):
        value = match.group(0).rstrip(".,:;)")
        if _safe_relative(value) and value not in values:
            values.append(value)
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


def _source_files(root: Path, deadline: object):
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


def validate_fast_scan_receipt(value: object) -> tuple[str, ...]:
    errors: list[str] = []
    if not _mapping(value):
        return ("fast scan receipt must be an object",)
    keys = set(value)
    for key in sorted(_REQUIRED_KEYS - keys):
        errors.append(f"missing top-level key {key}")
    for key in sorted(keys - _REQUIRED_KEYS):
        errors.append(f"unknown top-level key {key}")
    if _REQUIRED_KEYS - keys:
        return tuple(errors)

    if value["schema_version"] != 1:
        errors.append("schema_version must be 1")
    if value["status"] not in _STATUSES:
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
    if not _mapping(inventory) or set(inventory) != {"digests", "complete", "reason"}:
        errors.append("source_inventory must have exact fields")
    else:
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
        if not isinstance(inventory["complete"], bool):
            errors.append("source_inventory complete must be boolean")
        if inventory["reason"] is not None and not _string(inventory["reason"]):
            errors.append("source_inventory reason must be null or nonblank text")
        if inventory["complete"] is True and inventory["reason"] is not None:
            errors.append("complete source_inventory cannot have a reason")
        if inventory["complete"] is False and inventory["reason"] is None:
            errors.append("incomplete source_inventory requires a reason")

    seeds = value["seeds"]
    if not isinstance(seeds, list) or len(seeds) > MAX_SEEDS:
        errors.append("seeds exceeds maximum collection size")
    else:
        identities = set()
        for index, row in enumerate(seeds, start=1):
            if not _mapping(row) or set(row) != _SEED_KEYS:
                errors.append(f"seed row {index} must have exact fields")
                continue
            if not _string(row["term"]):
                errors.append(f"seed row {index} term must be nonblank")
            seed_location = row["location"]
            if seed_location is not None and not _safe_relative(seed_location):
                errors.append(f"seed row {index} location is unsafe")
            if not _string(row["derivation"]):
                errors.append(f"seed row {index} derivation must be nonblank")
            digest = row["source_sha256"]
            if digest is not None and (
                not isinstance(digest, str) or _HEX64.fullmatch(digest) is None
            ):
                errors.append(f"seed row {index} source_sha256 is invalid")
            identity = (row.get("term"), seed_location)
            if identity in identities:
                errors.append(f"duplicate seed row {index}")
            identities.add(identity)

    if not _mapping(value["graph_receipt"]):
        errors.append("graph_receipt must be an object")
    if value["risk_level"] not in _RISKS:
        errors.append("risk_level is invalid")
    if not isinstance(value["frontier"], list) or len(value["frontier"]) > MAX_FRONTIER:
        errors.append("frontier exceeds maximum collection size")
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
    if (
        not isinstance(value["elapsed_ms"], int)
        or isinstance(value["elapsed_ms"], bool)
        or value["elapsed_ms"] < 0
        or value["elapsed_ms"] > 30_000
    ):
        errors.append("elapsed_ms must be an integer from 0 to 30000")
    if value["cache_status"] not in _CACHE:
        errors.append("cache_status is invalid")
    if not isinstance(value["can_promote"], bool):
        errors.append("can_promote must be boolean")
    if (
        not isinstance(value["created_at"], str)
        or _TIMESTAMP.fullmatch(value["created_at"]) is None
    ):
        errors.append("created_at must be RFC 3339 UTC text")

    status = value["status"]
    if status == "needs_input":
        if value["can_promote"]:
            errors.append("needs_input scan cannot be promoted")
        if value["seeds"] or value["graph_receipt"]:
            errors.append("needs_input scan cannot contain graph evidence")
        if value["risk_level"] != "unknown":
            errors.append("needs_input risk_level must be unknown")
    elif status == "partial":
        if value["can_promote"]:
            errors.append("partial scan cannot be promoted")
        if value["candidates"]:
            errors.append("partial scan cannot contain candidates")
    elif status == "complete":
        if not value["can_promote"]:
            errors.append("complete scan must be promotable")
        if value["candidates"]:
            errors.append("complete scan cannot contain candidates")
        if not value["graph_receipt"]:
            errors.append("complete scan requires graph_receipt")
        if _mapping(inventory) and inventory.get("complete") is not True:
            errors.append("complete scan requires complete source inventory")
    return tuple(errors)


def canonical_fast_scan_bytes(value: Mapping[str, object] | FastScanReceipt) -> bytes:
    mapping = value.to_mapping() if isinstance(value, FastScanReceipt) else value
    errors = validate_fast_scan_receipt(mapping)
    if errors:
        raise ValueError("invalid fast scan receipt: " + "; ".join(errors))
    return json.dumps(mapping, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


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
    root: Path, deadline: graph_coordinator.Deadline
) -> graph_coordinator.SourceInventory:
    digests: dict[str, str] = {}
    unreadable = False
    for relative in _source_files(root, deadline):
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
) -> FastScanResult:
    prepared = prepare_fast_scan_identity(request, graph_settings, payload_sha256)
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

    try:
        existing_payload = fast_scan_store.load_scan_receipt_bytes(root, scan_id)
    except FileNotFoundError:
        existing_payload = None
    if existing_payload is not None:
        existing_value: object = json.loads(existing_payload)
        errors = validate_fast_scan_receipt(existing_value)
        if not _mapping(existing_value) or errors or existing_value.get("request_sha256") != request_sha:
            raise ValueError("existing fast scan receipt is invalid")
        existing = cast(_StoredFastScan, existing_value)
        rendered = dict(existing)
        rendered["cache_status"] = "hit"
        display = fast_scan_renderer.render_fast_scan(rendered, request.audience, locale)
        graph = existing["graph_receipt"]
        return FastScanResult(
            existing["status"],
            scan_id,
            existing["receipt_id"],
            hashlib.sha256(existing_payload).hexdigest(),
            display,
            existing["risk_level"],
            _row_tuple(graph.get("paths", [])),
            tuple(existing["frontier"]),
            tuple(existing["candidates"]),
            min(30_000, deadline.elapsed_ms()),
            "hit",
            existing["can_promote"],
        )
    candidates: list[Mapping[str, object]] = []
    if not seeds:
        graph = {}
        status = "needs_input"
        receipt_id = hashlib.sha256((scan_id + ":needs-input").encode()).hexdigest()[:32]
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
        graph.get("frontier", [])
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
    elapsed = min(30_000, deadline.elapsed_ms())
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
        _row_tuple(graph.get("frontier", [])),
        tuple(candidates),
        elapsed,
        cache_status,
        status == "complete",
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    payload = canonical_fast_scan_bytes(receipt)
    fast_scan_store.publish_scan_receipt(root, scan_id, payload)
    mapping = receipt.to_mapping()
    display = fast_scan_renderer.render_fast_scan(mapping, request.audience, locale)
    digest = hashlib.sha256(payload).hexdigest()
    return FastScanResult(
        status,
        scan_id,
        receipt_id,
        digest,
        display,
        risk_level,
        _row_tuple(graph.get("paths", [])),
        _row_tuple(graph.get("frontier", [])),
        tuple(candidates),
        elapsed,
        cache_status,
        status == "complete",
    )


def prepare_fast_scan_identity(
    request: FastScanRequest,
    graph_settings: Mapping[str, object],
    payload_sha256: str,
) -> PreparedFastScan:
    root = _root(request.repo_root)
    if not isinstance(payload_sha256, str) or _HEX64.fullmatch(payload_sha256) is None:
        raise ValueError("payload_sha256 must be 64 lowercase hex characters")
    settings = graph_coordinator.GraphSettings(
        **cast(_GraphSettingsArgs, dict(graph_settings))
    )
    deadline = graph_coordinator.Deadline(time, settings.max_seconds)
    seeds = derive_seeds(root, request.change_request, request.evidence, deadline)
    source_inventory = _inventory(root, deadline)
    inventory_mapping = {
        "digests": dict(source_inventory.digests),
        "complete": source_inventory.complete,
        "reason": source_inventory.reason,
    }
    identity = json.dumps(
        {
            "root": str(root),
            "change_request": request.change_request,
            "evidence": list(request.evidence),
            "settings": settings.to_mapping(),
            "payload_sha256": payload_sha256,
            "source_inventory": inventory_mapping,
            "seeds": [row.to_mapping() for row in seeds],
        },
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
    "prepare_fast_scan_identity",
    "validate_fast_scan_receipt",
]
