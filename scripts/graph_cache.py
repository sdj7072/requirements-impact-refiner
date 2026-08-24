#!/usr/bin/env python3
"""Private, receipt-derived incremental cache for impact graphs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any, Mapping


def _load_graph_contract():
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


GRAPH = _load_graph_contract()
_HEX64 = re.compile(r"[0-9a-f]{64}")
_CACHE_COMPONENTS = (
    ".requirements-impact-refiner", "cache", "graph", "v1",
)
_CACHE_FIELDS = frozenset({
    "cache_schema_version", "identity", "receipt", "source_digests",
})
_IDENTITY_FIELDS = frozenset({
    "graph_schema_version", "repo_root_sha256", "settings", "providers",
    "source_digests", "receipt_id", "draft_id", "request_sha256",
    "source_inventory_complete", "source_inventory_reason",
})
_INVENTORY_REASONS = frozenset({"deadline", "collection-limit", "traversal", "unreadable-source"})
MAX_CACHE_BYTES = GRAPH.MAX_RECEIPT_BYTES * 2


@dataclass(frozen=True)
class CacheResult:
    status: str
    key: str
    receipt: Mapping[str, Any] | None
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
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


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
                    raise ValueError("cache component must not be a symlink")
            os.chmod(current, 0o700)
        else:
            return None
    return current


def _normalize_receipt(value) -> tuple[dict[str, Any], bytes]:
    canonical = GRAPH.canonical_receipt_bytes(value)
    normalized, errors = GRAPH.load_receipt_bytes(canonical)
    if errors or normalized is None:
        raise ValueError("invalid graph receipt")
    return normalized, canonical


def _identity(
    root: Path, receipt: Mapping[str, Any], source_digests, schema_version: int,
    inventory_complete: bool, inventory_reason: str | None,
):
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version < 1:
        raise ValueError("schema_version must be a positive integer")
    if not isinstance(inventory_complete, bool):
        raise ValueError("inventory_complete must be boolean")
    if (
        (inventory_complete and inventory_reason is not None)
        or (
            not inventory_complete
            and inventory_reason not in _INVENTORY_REASONS
        )
    ):
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
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_pointer(cache_dir: Path, key: str) -> None:
    pointer = cache_dir / "current"
    if pointer.is_symlink():
        raise ValueError("cache pointer must not be a symlink")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".current.", suffix=".tmp", dir=str(cache_dir)
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
        root, normalized_receipt, normalized_digests, schema_version,
        inventory_complete, inventory_reason,
    )
    key = hashlib.sha256(_canonical_json(identity)).hexdigest()
    payload = _canonical_json({
        "cache_schema_version": 1,
        "identity": identity,
        "receipt": normalized_receipt,
        "source_digests": normalized_digests,
    })
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
    receipt: Mapping[str, Any],
    cached_source_digests: Mapping[str, str],
    current_source_digests: Mapping[str, str],
) -> tuple[str, ...]:
    """Return changed receipt nodes plus their directed dependents."""
    cached = _source_digests(cached_source_digests)
    current = _source_digests(current_source_digests)
    changed_paths = {
        path for path in set(cached) | set(current)
        if cached.get(path) != current.get(path)
    }
    nodes = receipt.get("nodes", ())
    direct = {
        node["id"] for node in nodes
        if node.get("location") in changed_paths
    }
    invalidated = set(direct)
    adjacency = {}
    for edge in receipt.get("edges", ()):
        adjacency.setdefault(edge.get("source"), set()).add(edge.get("target"))
    pending = sorted(direct)
    while pending:
        source = pending.pop(0)
        for target in sorted(adjacency.get(source, ())):
            if target not in invalidated:
                invalidated.add(target)
                pending.append(target)
    for path in receipt.get("paths", ()):
        path_nodes = path.get("nodes", ())
        for index, node_id in enumerate(path_nodes):
            if node_id in direct:
                invalidated.update(path_nodes[index:])
    node_order = {node["id"]: index for index, node in enumerate(nodes)}
    return tuple(sorted(invalidated, key=lambda node_id: (node_order.get(node_id, 10**9), node_id)))


def _read_artifact(path: Path) -> dict[str, Any] | None:
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
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or set(value) != _CACHE_FIELDS:
        return None
    if value.get("cache_schema_version") != 1:
        return None
    return value


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
    except ValueError:
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
    if not isinstance(identity, dict) or not isinstance(cached, dict) or not isinstance(receipt, dict):
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
    if (
        not isinstance(complete, bool)
        or (complete and reason is not None)
        or (not complete and reason not in _INVENTORY_REASONS)
    ):
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
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version < 1:
        return _miss(key)
    if hashlib.sha256(_canonical_json(identity)).hexdigest() != key:
        return _miss(key)
    if not complete:
        return _miss(key)
    changed_paths = {
        path for path in set(cached) | set(current)
        if cached.get(path) != current.get(path)
    }
    mapped_paths = {
        node.get("location") for node in normalized["nodes"]
        if node.get("location") is not None
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
