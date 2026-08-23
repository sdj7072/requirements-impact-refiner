#!/usr/bin/env python3
"""Read-only adapter for an existing repository-local SCIP index."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys


def _load(filename, name):
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load " + filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PROVIDERS = _load("graph_providers.py", "_rir_graph_providers")
COMMON = _load("graph_adapter_ast_grep.py", "_rir_graph_adapter_ast_grep")
ProviderProbe = PROVIDERS.ProviderProbe
ProviderResult = PROVIDERS.ProviderResult
ProviderSpec = PROVIDERS.ProviderSpec

_VERSION = re.compile(r"(?i)^scip(?:\s+version)?\s+0\.6\.\d+(?:[-+][^\s]+)?$")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_MAX_INDEX_BYTES = 256 * 1024 * 1024
_MAX_DOCUMENTS = 512
_MAX_OCCURRENCES = 16_384
_MAX_SYMBOL = 4096


class _IndexChangedError(ValueError):
    pass


def _read_chunk(descriptor, size):
    return os.read(descriptor, size)


def _deadline_expired(deadline):
    return deadline is not None and deadline.expired()


def _identity(info):
    return {
        "device": info.st_dev, "inode": info.st_ino, "size": info.st_size,
        "modified_ns": info.st_mtime_ns,
    }


def _read_exact_identity(descriptor, deadline, *, write_descriptor=None):
    initial = os.fstat(descriptor)
    if not stat.S_ISREG(initial.st_mode) or initial.st_size <= 0 or initial.st_size > _MAX_INDEX_BYTES:
        raise ValueError("index.scip must be a bounded regular file")
    observed = _identity(initial)
    remaining = initial.st_size
    digest = hashlib.sha256()
    total = 0
    while remaining:
        if _deadline_expired(deadline):
            raise TimeoutError("shared deadline exhausted while reading index.scip")
        chunk = _read_chunk(descriptor, min(64 * 1024, remaining))
        if not chunk:
            raise _IndexChangedError("index.scip shrank while reading")
        if len(chunk) > remaining:
            raise _IndexChangedError("index.scip exceeded its observed size")
        total += len(chunk)
        if total > initial.st_size or total > _MAX_INDEX_BYTES:
            raise _IndexChangedError("index.scip exceeded its bounded identity")
        digest.update(chunk)
        if write_descriptor is not None:
            offset = 0
            while offset < len(chunk):
                written = os.write(write_descriptor, chunk[offset:])
                if written <= 0:
                    raise OSError("SCIP snapshot write made no progress")
                offset += written
        remaining -= len(chunk)
    final = os.fstat(descriptor)
    if _identity(final) != observed:
        raise _IndexChangedError("index.scip changed while reading")
    return {**observed, "sha256": digest.hexdigest()}


def _failure(status, detail, digests=()):
    return ProviderResult("scip", status, "verified-provider", raw_receipt_sha256=digests, detail=str(detail)[:512])


def _regular_index(root):
    path = root / "index.scip"
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return "stale", "repository-local index.scip is missing"
    except OSError as error:
        return "unsafe", str(error)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        return "unsafe", "index.scip must be a regular non-symlink file"
    if metadata.st_size <= 0 or metadata.st_size > _MAX_INDEX_BYTES:
        return "unsafe", "index.scip size is outside the supported bound"
    return "ready", None


def _index_observation(root, deadline=None):
    path = root / "index.scip"
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as error:
        raise ValueError("index.scip is unavailable or unsafe") from error
    try:
        return _read_exact_identity(descriptor, deadline)
    finally:
        os.close(descriptor)


def _same_index(left, right):
    return left == right


def _snapshot_observation(directory_fd, deadline):
    try:
        info = os.stat("index.scip", dir_fd=directory_fd, follow_symlinks=False)
    except OSError:
        return None
    if (
        stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o400
        or info.st_size <= 0 or info.st_size > _MAX_INDEX_BYTES
    ):
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open("index.scip", flags, dir_fd=directory_fd)
    except OSError:
        return None
    try:
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(info):
            return None
        return _read_exact_identity(descriptor, deadline)["sha256"]
    except (TimeoutError, _IndexChangedError, ValueError):
        return None
    finally:
        os.close(descriptor)


def _range(value):
    if not isinstance(value, list) or len(value) not in {3, 4}:
        raise ValueError("SCIP occurrence range must contain three or four integers")
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 or item > 10_000_000 for item in value):
        raise ValueError("SCIP occurrence range is invalid")
    if len(value) == 3:
        start_line, start_col, end_col = value
        end_line = start_line
    else:
        start_line, start_col, end_line, end_col = value
    if (end_line, end_col) < (start_line, start_col):
        raise ValueError("SCIP occurrence range is reversed")
    return start_line, start_col, end_line, end_col


def _parse(value, root, fingerprint):
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "metadata", "documents"} or value["schemaVersion"] != 1:
        raise ValueError("SCIP print JSON shape is unsupported")
    metadata = value["metadata"]
    if not isinstance(metadata, dict) or set(metadata) != {"projectRoot", "sourceFingerprint", "indexer"}:
        raise ValueError("SCIP metadata shape is unsupported")
    indexer = metadata["indexer"]
    if not isinstance(indexer, dict) or set(indexer) != {"name", "version"}:
        raise ValueError("SCIP indexer metadata shape is unsupported")
    if not all(isinstance(indexer.get(key), str) and indexer[key] and len(indexer[key]) <= 128 for key in ("name", "version")):
        raise ValueError("SCIP indexer identity is invalid")
    if metadata["projectRoot"] != str(root):
        raise ValueError("SCIP project root does not exactly match repository")
    if not isinstance(metadata["sourceFingerprint"], str) or _HEX64.fullmatch(metadata["sourceFingerprint"]) is None:
        raise ValueError("SCIP source fingerprint is invalid")
    if metadata["sourceFingerprint"] != fingerprint:
        raise RuntimeError("SCIP index is stale for repository sources")
    documents = value["documents"]
    if not isinstance(documents, list) or len(documents) > _MAX_DOCUMENTS:
        raise ValueError("SCIP document collection exceeds supported shape")
    occurrences = {}
    count = 0
    for document in documents:
        if not isinstance(document, dict) or set(document) != {"relativePath", "occurrences"}:
            raise ValueError("SCIP document shape is unsupported")
        path = COMMON._safe_relative(document["relativePath"])
        payload = COMMON._regular_bytes(root, path) if path is not None else None
        if path is None or payload is None:
            raise ValueError("SCIP document path is outside regular repository source")
        rows = document["occurrences"]
        if not isinstance(rows, list):
            raise ValueError("SCIP occurrences must be a list")
        for row in rows:
            count += 1
            if count > _MAX_OCCURRENCES:
                raise ValueError("SCIP occurrence collection exceeds bound")
            if not isinstance(row, dict) or set(row) != {"range", "symbol", "symbolRoles", "excerpt"}:
                raise ValueError("SCIP occurrence shape is unsupported")
            symbol, roles = row["symbol"], row["symbolRoles"]
            if not isinstance(symbol, str) or not symbol or len(symbol) > _MAX_SYMBOL:
                raise ValueError("SCIP symbol is invalid")
            if not isinstance(roles, int) or isinstance(roles, bool) or roles < 0 or roles > 127:
                raise ValueError("SCIP symbol roles are invalid")
            source_range = _range(row["range"])
            proof = COMMON._source_proof(root, path, source_range)
            if not isinstance(row["excerpt"], str) or row["excerpt"] != proof["excerpt"]:
                raise ValueError("SCIP occurrence excerpt does not match declared source range")
            signature = (path, source_range, roles)
            occurrences.setdefault(symbol, {})[signature] = (
                path, source_range, roles, proof["sha256"], proof["excerpt"],
            )
    return metadata, occurrences


def _print(spec, root, deadline, runner, expected_identity=None):
    try:
        before = _index_observation(root, deadline)
    except TimeoutError as error:
        return None, "timed_out", str(error), None
    except _IndexChangedError as error:
        return None, "stale", str(error), None
    except ValueError as error:
        return None, "unsafe", str(error), None
    if expected_identity is not None and not _same_index(before, expected_identity):
        return None, "stale", "index.scip changed after probe", before
    try:
        directory, directory_fd = PROVIDERS.create_private_root("rir-scip-index-")
    except OSError as error:
        return None, "unsafe", str(error), before
    snapshot = directory / "index.scip"
    source = destination = -1
    cleaned = False

    def finish(value):
        nonlocal cleaned, source, destination, directory_fd
        if cleaned:
            return value
        if destination >= 0:
            os.close(destination)
            destination = -1
        if source >= 0:
            os.close(source)
            source = -1
        cleaned, changed, cleanup_detail = PROVIDERS.cleanup_private_root(
            directory, directory_fd,
        )
        directory_fd = -1
        if not cleaned or changed:
            return (
                None, "unsafe",
                cleanup_detail or "private SCIP snapshot cleanup failed", before,
            )
        return value

    try:
        source = os.open(str(root / "index.scip"), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        destination = os.open(
            "index.scip", os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o400, dir_fd=directory_fd,
        )
        copied = _read_exact_identity(
            source, deadline, write_descriptor=destination,
        )
        os.fchmod(destination, 0o400)
        os.fsync(destination)
        os.close(destination)
        destination = -1
        os.fsync(directory_fd)
        if copied != before:
            return finish((None, "stale", "index.scip changed while snapshotting", before))
        during = _index_observation(root, deadline)
        if not _same_index(before, during):
            return finish((None, "stale", "index.scip changed while snapshotting", during))
        result = PROVIDERS.run_provider(
            spec, ("print", "--json", str(snapshot)), root, deadline,
            runner=runner, expect_json=True,
        )
        snapshot_digest = _snapshot_observation(directory_fd, deadline)
        if snapshot_digest != before["sha256"]:
            if _deadline_expired(deadline):
                return finish((None, "timed_out", "shared deadline exhausted while verifying SCIP snapshot", before))
            return finish((None, "unsafe", "private SCIP snapshot changed during print", before))
        after = _index_observation(root, deadline)
        if not _same_index(before, after):
            return finish((None, "stale", "index.scip changed during print", after))
        return finish((result, result.status, result.detail, before))
    except TimeoutError as error:
        return finish((None, "timed_out", str(error), before))
    except _IndexChangedError as error:
        return finish((None, "stale", str(error), before))
    except (OSError, ValueError) as error:
        return finish((None, "unsafe", str(error), before))
    finally:
        if source >= 0:
            os.close(source)
        if destination >= 0:
            os.close(destination)
        if not cleaned and directory_fd >= 0:
            finish((None, "unsafe", "private SCIP snapshot cleanup failed", before))


def probe(spec, root, deadline, runner) -> ProviderProbe:
    if not isinstance(spec, ProviderSpec) or spec.name != "scip":
        raise TypeError("SCIP probe requires its ProviderSpec")
    base = Path(root)
    resolved = base.resolve() if not base.is_symlink() and base.is_dir() else base.absolute()
    index_status, index_detail = _regular_index(resolved)
    if index_status != "ready":
        return ProviderProbe("scip", index_status, "verified-provider", spec.executable, detail=index_detail, repo_root=resolved)
    fingerprint = COMMON.source_fingerprint(resolved)
    if fingerprint is None:
        return ProviderProbe("scip", "unsafe", "verified-provider", spec.executable, detail="repository source identity is unsafe or exceeds bounds", repo_root=resolved)
    version_result = PROVIDERS.run_provider(spec, ("--version",), resolved, deadline, runner=runner)
    if version_result.status != "ready":
        return ProviderProbe("scip", version_result.status, "verified-provider", spec.executable, executable_sha256=version_result.executable_sha256, detail=version_result.detail, repo_root=resolved)
    version = next((line.strip() for line in version_result.stdout.splitlines() if line.strip()), "")
    if _VERSION.fullmatch(version) is None:
        return ProviderProbe("scip", "unsupported", "verified-provider", spec.executable, version[:256] or None, version_result.executable_sha256, detail="SCIP reader 0.6.x is required", repo_root=resolved)
    for arguments, patterns in (
        (("--help",), (r"(?m)^\s{2,}print\s*$",)),
        (("print", "--help"), (r"(?m)^Usage:\s+scip print --json <index>\s*$",)),
    ):
        help_result = PROVIDERS.run_provider(spec, arguments, resolved, deadline, runner=runner)
        if help_result.status != "ready":
            status = help_result.status if help_result.status in {"unsafe", "timed_out"} else "unsupported"
            return ProviderProbe("scip", status, "verified-provider", spec.executable, version, version_result.executable_sha256, detail=help_result.detail or "SCIP print help unavailable", repo_root=resolved)
        if help_result.executable_sha256 != version_result.executable_sha256:
            return ProviderProbe("scip", "unsafe", "verified-provider", spec.executable, version, version_result.executable_sha256, detail="provider executable changed between probes", repo_root=resolved)
        if not all(re.search(pattern, help_result.stdout) for pattern in patterns):
            return ProviderProbe("scip", "unsupported", "verified-provider", spec.executable, version, version_result.executable_sha256, detail="SCIP help does not confirm read-only JSON print", repo_root=resolved)
    printed, print_status, print_detail, index_identity = _print(spec, resolved, deadline, runner)
    if print_status != "ready" or printed is None:
        return ProviderProbe("scip", print_status, "verified-provider", spec.executable, version, version_result.executable_sha256, detail=print_detail or "SCIP print failed", repo_root=resolved)
    if printed.executable_sha256 != version_result.executable_sha256:
        return ProviderProbe("scip", "unsafe", "verified-provider", spec.executable, version, version_result.executable_sha256, detail="provider executable changed before SCIP print", repo_root=resolved)
    try:
        metadata, _ = _parse(printed.parsed_json, resolved, fingerprint)
    except RuntimeError as error:
        return ProviderProbe("scip", "stale", "verified-provider", spec.executable, version, version_result.executable_sha256, detail=error, repo_root=resolved)
    except (TypeError, ValueError) as error:
        return ProviderProbe("scip", "failed", "verified-provider", spec.executable, version, version_result.executable_sha256, detail=error, repo_root=resolved)
    indexer = metadata["indexer"]
    return ProviderProbe(
        "scip", "ready", "verified-provider", spec.executable, version,
        version_result.executable_sha256, ("print-json",), repo_root=resolved,
        metadata={
            "index": "index.scip", "source_fingerprint": fingerprint,
            "indexer": "%s %s" % (indexer["name"], indexer["version"]),
            "index_sha256": index_identity["sha256"], "index_identity": index_identity,
        },
    )


def _node_kind(path, symbol):
    return COMMON._kind(path, symbol)


def query(probe, seeds, deadline, runner) -> ProviderResult:
    if not isinstance(probe, ProviderProbe) or probe.name != "scip":
        raise TypeError("SCIP query requires its ProviderProbe")
    if probe.status != "ready" or probe.executable is None or probe.repo_root is None:
        return _failure(probe.status, probe.detail or "provider is not ready")
    root = probe.repo_root.resolve()
    index_status, index_detail = _regular_index(root)
    if index_status != "ready":
        return _failure(index_status, index_detail)
    fingerprint = COMMON.source_fingerprint(root)
    if fingerprint is None or fingerprint != probe.metadata.get("source_fingerprint"):
        return _failure("stale", "repository changed after SCIP probe")
    spec = ProviderSpec("scip", probe.executable)
    expected_identity = dict(probe.metadata.get("index_identity", {}))
    if not expected_identity or probe.metadata.get("index_sha256") != expected_identity.get("sha256"):
        return _failure("unsafe", "SCIP index identity is missing or invalid")
    printed, print_status, print_detail, _ = _print(
        spec, root, deadline, runner, expected_identity,
    )
    if print_status != "ready" or printed is None:
        return _failure(print_status, print_detail or "SCIP print failed")
    if probe.executable_sha256 is not None and printed.executable_sha256 != probe.executable_sha256:
        return _failure("unsafe", "SCIP executable changed after probe")
    digest = hashlib.sha256(printed.stdout.encode("utf-8")).hexdigest()
    try:
        _, symbols = _parse(printed.parsed_json, root, fingerprint)
    except RuntimeError as error:
        return _failure("stale", error, (digest,))
    except (TypeError, ValueError) as error:
        return _failure("failed", error, (digest,))
    seed_terms = tuple(
        term for term in (getattr(seed, "term", None) for seed in tuple(seeds)[:16])
        if isinstance(term, str) and term
    )
    nodes = {}
    edges = {}
    for symbol, occurrences in sorted(symbols.items()):
        if seed_terms and not any(
            term in symbol
            or term.rsplit(".", 1)[-1].rsplit("/", 1)[-1] in symbol
            for term in seed_terms
        ):
            continue
        definitions = [item for item in occurrences.values() if item[2] & 1]
        references = [item for item in occurrences.values() if not item[2] & 1]
        for definition_index, definition in enumerate(definitions):
            source_path, source_range, _, source_digest, source_excerpt = definition
            source_key = "definition:%s:%d" % (hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:16], definition_index)
            nodes[source_key] = {
                "key": source_key, "kind": _node_kind(source_path, symbol),
                "label": symbol[-256:], "location": source_path,
                "confidence": "verified-provider", "source_sha256": source_digest,
                "risk_domains": COMMON._risk_domains(source_path, symbol),
            }
            for reference_index, reference in enumerate(references):
                target_path, target_range, roles, target_digest, target_excerpt = reference
                target_key = "reference:%s:%d:%d" % (
                    hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:16],
                    definition_index, reference_index,
                )
                nodes[target_key] = {
                    "key": target_key, "kind": _node_kind(target_path, symbol),
                    "label": symbol[-256:], "location": target_path,
                    "confidence": "verified-provider", "source_sha256": target_digest,
                    "risk_domains": COMMON._risk_domains(target_path, symbol),
                }
                kind = "implements" if roles & 64 else ("writes" if roles & 4 else "references")
                start_line, start_col, end_line, end_col = target_range
                signature = (source_key, target_key, kind, target_path, target_range)
                edges[signature] = {
                    "source": source_key, "target": target_key, "kind": kind,
                    "location": target_path,
                    "evidence": "SCIP %s at %d:%d-%d:%d" % (
                        kind, start_line + 1, start_col + 1, end_line + 1, end_col + 1,
                    ) + ": " + target_excerpt[:128],
                    "confidence": "verified-provider", "source_sha256": target_digest,
                }
    if COMMON.source_fingerprint(root) != fingerprint:
        return _failure("stale", "repository changed during SCIP query", (digest,))
    return ProviderResult(
        "scip", "ready", "verified-provider", tuple(nodes.values()),
        tuple(edges.values()), raw_receipt_sha256=(digest,),
        metadata={"indexer": probe.metadata.get("indexer")},
    )


__all__ = ["probe", "query"]
