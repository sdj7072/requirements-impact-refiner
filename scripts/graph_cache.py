#!/usr/bin/env python3
"""Private, receipt-derived incremental cache for impact graphs."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from typing_extensions import TypeGuard


class _GraphCacheContract(Protocol):
    MAX_RECEIPT_BYTES: int

    def _safe_path(self, value: object) -> bool: ...

    def canonical_receipt_bytes(self, value: object) -> bytes: ...

    def load_receipt_bytes(
        self, payload: bytes
    ) -> tuple[dict[str, object] | None, tuple[str, ...]]: ...


def _load_graph_contract() -> object:
    name = "_rir_impact_graph"
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    path = Path(__file__).with_name("impact_graph.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load impact graph contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _is_graph_cache_contract(value: object) -> TypeGuard[_GraphCacheContract]:
    return isinstance(getattr(value, "MAX_RECEIPT_BYTES", None), int) and all(
        callable(getattr(value, name, None))
        for name in ("_safe_path", "canonical_receipt_bytes", "load_receipt_bytes")
    )


_loaded_graph = _load_graph_contract()
if not _is_graph_cache_contract(_loaded_graph):
    raise ImportError("impact graph cache contract is incomplete")
GRAPH = cast(_GraphCacheContract, _loaded_graph)
_HEX64 = re.compile(r"[0-9a-f]{64}")
_MAX_JSON_DEPTH = 64
_CACHE_COMPONENTS = (
    ".requirements-impact-refiner",
    "cache",
    "graph",
    "v1",
)
_CACHE_FIELDS = frozenset(
    {
        "cache_schema_version",
        "identity",
        "receipt",
        "source_digests",
    }
)
_IDENTITY_FIELDS = frozenset(
    {
        "graph_schema_version",
        "repo_root_sha256",
        "settings",
        "providers",
        "source_digests",
        "receipt_id",
        "draft_id",
        "request_sha256",
        "source_inventory_complete",
        "source_inventory_reason",
    }
)
_INVENTORY_REASONS = frozenset({"deadline", "collection-limit", "traversal", "unreadable-source"})
MAX_CACHE_BYTES = GRAPH.MAX_RECEIPT_BYTES * 2


def _json_depth(text: str) -> int:
    """Return peak JSON container nesting without invoking the decoder."""
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
            peak = max(peak, depth)
        elif char in "]}":
            depth = max(0, depth - 1)
    return peak


def _mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping) and all(isinstance(key, str) for key in value)


def _rows(value: object) -> TypeGuard[Sequence[Mapping[str, object]]]:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and all(_mapping(row) for row in value)
    )


def _strings(value: object) -> TypeGuard[Sequence[str]]:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and all(isinstance(item, str) for item in value)
    )


@dataclass(frozen=True)
class CacheResult:
    status: str
    key: str
    receipt: Mapping[str, object] | None
    invalidated_nodes: tuple[str, ...]
    artifact: Path | None = None


def _miss(key: str = "0" * 64) -> CacheResult:
    safe_key = key if isinstance(key, str) and _HEX64.fullmatch(key) else "0" * 64
    return CacheResult("miss", safe_key, None, ())


def _root(repo_root: Path | str) -> Path:
    root = Path(repo_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("repo_root must be a regular directory")
    return root.resolve()


def _source_digests(value: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("source digests must be a mapping")
    result = {}
    for path, digest in value.items():
        if not isinstance(path, str) or not GRAPH._safe_path(path):
            raise ValueError("source digest path must be safe and repository-relative")
        if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
            raise ValueError(f"source digest for {path} must be lowercase SHA-256")
        result[path] = digest
    return {path: result[path] for path in sorted(result)}


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _cache_directory(root: Path, create: bool) -> Path | None:
    current = root
    for component in _CACHE_COMPONENTS:
        current = current / component
        if current.exists() or current.is_symlink():
            try:
                metadata = current.lstat()
            except OSError as error:
                raise ValueError("cache component is unavailable") from error
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError("cache component must not be a symlink")
            if not stat.S_ISDIR(metadata.st_mode):
                raise ValueError("cache component must be a directory")
        elif create:
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                if current.is_symlink() or not current.is_dir():
                    raise ValueError("cache component must not be a symlink") from None
            os.chmod(current, 0o700)
        else:
            return None
    return current


def _normalize_receipt(value: object) -> tuple[dict[str, object], bytes]:
    try:
        canonical = GRAPH.canonical_receipt_bytes(value)
        normalized, errors = GRAPH.load_receipt_bytes(canonical)
    except (RecursionError, TypeError, ValueError) as error:
        raise ValueError("invalid graph receipt") from error
    if errors or normalized is None:
        raise ValueError("invalid graph receipt")
    return cast(dict[str, object], normalized), canonical


def _identity(
    root: Path,
    receipt: Mapping[str, object],
    source_digests,
    schema_version: int,
    inventory_complete: bool,
    inventory_reason: str | None,
):
    if type(schema_version) is not int or schema_version < 1:
        raise ValueError("schema_version must be a positive integer")
    if not isinstance(inventory_complete, bool):
        raise ValueError("inventory_complete must be boolean")
    if inventory_complete:
        reason_valid = inventory_reason is None
    else:
        reason_valid = isinstance(inventory_reason, str) and inventory_reason in _INVENTORY_REASONS
    if not reason_valid:
        raise ValueError("inventory completeness reason is invalid")
    return {
        "graph_schema_version": schema_version,
        "repo_root_sha256": hashlib.sha256(str(root).encode("utf-8")).hexdigest(),
        "receipt_id": receipt["receipt_id"],
        "draft_id": receipt["draft_id"],
        "request_sha256": receipt["request_sha256"],
        "source_inventory_complete": inventory_complete,
        "source_inventory_reason": inventory_reason,
        "settings": receipt["settings"],
        "providers": receipt["providers"],
        "source_digests": source_digests,
    }


def _write_exclusive(path: Path, payload: bytes) -> None:
    worker_token = os.environ.get("RIR_DELTA_WORKER_TOKEN")
    if isinstance(worker_token, str) and re.fullmatch(r"[0-9a-f]{32}", worker_token):
        temporary = path.with_name(f".{path.name}.{worker_token}.tmp")
        descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    else:
        temporary = None
        descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(descriptor)
        if temporary is not None:
            os.link(temporary, path, follow_symlinks=False)
    finally:
        os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _replace_pointer(cache_dir: Path, key: str) -> None:
    pointer = cache_dir / "current"
    if pointer.is_symlink():
        raise ValueError("cache pointer must not be a symlink")
    worker_token = os.environ.get("RIR_DELTA_WORKER_TOKEN")
    token_prefix = (
        f"{worker_token}."
        if isinstance(worker_token, str) and re.fullmatch(r"[0-9a-f]{32}", worker_token)
        else ""
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".current.{token_prefix}", suffix=".tmp", dir=str(cache_dir)
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write((key + "\n").encode("ascii"))
            handle.flush()
            os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, pointer)
        os.chmod(pointer, 0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def publish(
    repo_root: Path | str,
    receipt,
    source_digests: Mapping[str, str],
    *,
    schema_version: int = 1,
    inventory_complete: bool = True,
    inventory_reason: str | None = None,
) -> CacheResult:
    """Publish normalized receipt data and atomically select its cache key."""
    root = _root(repo_root)
    normalized_digests = _source_digests(source_digests)
    normalized_receipt, _ = _normalize_receipt(receipt)
    identity = _identity(
        root,
        normalized_receipt,
        normalized_digests,
        schema_version,
        inventory_complete,
        inventory_reason,
    )
    key = hashlib.sha256(_canonical_json(identity)).hexdigest()
    payload = _canonical_json(
        {
            "cache_schema_version": 1,
            "identity": identity,
            "receipt": normalized_receipt,
            "source_digests": normalized_digests,
        }
    )
    if len(payload) > MAX_CACHE_BYTES:
        raise ValueError("graph cache artifact exceeds maximum byte size")
    cache_dir = _cache_directory(root, True)
    assert cache_dir is not None
    artifact = cache_dir / f"{key}.json"
    if artifact.is_symlink():
        raise ValueError("cache artifact must not be a symlink")
    if not artifact.exists():
        _write_exclusive(artifact, payload)
    else:
        metadata = artifact.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("cache artifact must be a regular file")
        if artifact.read_bytes() != payload:
            raise ValueError("existing cache artifact does not match its identity")
        os.chmod(artifact, 0o600)
    _replace_pointer(cache_dir, key)
    return CacheResult("miss", key, normalized_receipt, (), artifact)


def invalidate(
    receipt: Mapping[str, object],
    cached_source_digests: Mapping[str, str],
    current_source_digests: Mapping[str, str],
) -> tuple[str, ...]:
    """Return changed receipt nodes plus their directed dependents."""
    cached = _source_digests(cached_source_digests)
    current = _source_digests(current_source_digests)
    changed_paths = {
        path for path in set(cached) | set(current) if cached.get(path) != current.get(path)
    }
    node_value = receipt.get("nodes", ())
    nodes = node_value if _rows(node_value) else ()
    direct = {
        node_id
        for node in nodes
        if node.get("location") in changed_paths and isinstance((node_id := node.get("id")), str)
    }
    invalidated = set(direct)
    adjacency: dict[str, set[str]] = {}
    edge_value = receipt.get("edges", ())
    edges = edge_value if _rows(edge_value) else ()
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if isinstance(source, str) and isinstance(target, str):
            adjacency.setdefault(source, set()).add(target)
    pending = sorted(direct)
    while pending:
        source = pending.pop(0)
        for target in sorted(adjacency.get(source, ())):
            if target not in invalidated:
                invalidated.add(target)
                pending.append(target)
    path_value = receipt.get("paths", ())
    paths = path_value if _rows(path_value) else ()
    for path in paths:
        path_node_value = path.get("nodes", ())
        path_nodes = path_node_value if _strings(path_node_value) else ()
        for index, node_id in enumerate(path_nodes):
            if node_id in direct:
                invalidated.update(path_nodes[index:])
    node_order = {node["id"]: index for index, node in enumerate(nodes)}
    return tuple(sorted(invalidated, key=lambda node_id: (node_order.get(node_id, 10**9), node_id)))


def _read_artifact(path: Path) -> dict[str, object] | None:
    try:
        metadata = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        return None
    if metadata.st_size > MAX_CACHE_BYTES:
        return None
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8")
        if _json_depth(text) > _MAX_JSON_DEPTH:
            return None
        value = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError, TypeError):
        return None
    if not isinstance(value, dict) or set(value) != _CACHE_FIELDS:
        return None
    cache_schema_version = value.get("cache_schema_version")
    if type(cache_schema_version) is not int or cache_schema_version != 1:
        return None
    return cast(dict[str, object], value)


def load(
    repo_root: Path | str,
    key: str,
    source_digests: Mapping[str, str],
) -> CacheResult:
    """Load a cache artifact, failing closed on every malformed input."""
    if not isinstance(key, str) or _HEX64.fullmatch(key) is None:
        return _miss()
    try:
        root = _root(repo_root)
        current = _source_digests(source_digests)
        cache_dir = _cache_directory(root, False)
    except (RecursionError, TypeError, ValueError):
        return _miss(key)
    if cache_dir is None:
        return _miss(key)
    artifact = cache_dir / f"{key}.json"
    value = _read_artifact(artifact)
    if value is None:
        return _miss(key)
    identity = value.get("identity")
    cached = value.get("source_digests")
    receipt = value.get("receipt")
    if (
        not isinstance(identity, dict)
        or not isinstance(cached, dict)
        or not isinstance(receipt, dict)
    ):
        return _miss(key)
    try:
        cached = _source_digests(cached)
        normalized, _ = _normalize_receipt(receipt)
    except ValueError:
        return _miss(key)
    if set(identity) != _IDENTITY_FIELDS:
        return _miss(key)
    expected_root = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
    if identity.get("repo_root_sha256") != expected_root:
        return _miss(key)
    if identity.get("source_digests") != cached:
        return _miss(key)
    complete = identity.get("source_inventory_complete")
    reason = identity.get("source_inventory_reason")
    if not isinstance(complete, bool):
        return _miss(key)
    if complete:
        reason_valid = reason is None
    else:
        reason_valid = isinstance(reason, str) and reason in _INVENTORY_REASONS
    if not reason_valid:
        return _miss(key)
    if any(
        identity.get(name) != normalized.get(name)
        for name in ("receipt_id", "draft_id", "request_sha256")
    ):
        return _miss(key)
    if identity.get("settings") != normalized["settings"]:
        return _miss(key)
    if identity.get("providers") != normalized["providers"]:
        return _miss(key)
    schema_version = identity.get("graph_schema_version")
    if type(schema_version) is not int or schema_version < 1:
        return _miss(key)
    try:
        identity_key = hashlib.sha256(_canonical_json(identity)).hexdigest()
    except (RecursionError, TypeError, ValueError):
        return _miss(key)
    if identity_key != key:
        return _miss(key)
    if not complete:
        return _miss(key)
    changed_paths = {
        path for path in set(cached) | set(current) if cached.get(path) != current.get(path)
    }
    normalized_node_value = normalized["nodes"]
    normalized_nodes = normalized_node_value if _rows(normalized_node_value) else ()
    mapped_paths = {
        node.get("location") for node in normalized_nodes if node.get("location") is not None
    }
    if not changed_paths <= mapped_paths:
        return _miss(key)
    invalidated = invalidate(normalized, cached, current)
    if cached != current and not invalidated:
        return _miss(key)
    status = "partial" if cached != current else "hit"
    return CacheResult(status, key, normalized, invalidated, artifact)


class GraphCache:
    """Namespaced public cache interface used by the graph coordinator."""

    publish = staticmethod(publish)
    load = staticmethod(load)
    invalidate = staticmethod(invalidate)
