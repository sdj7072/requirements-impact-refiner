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
            if not isinstance(row, dict) or set(row) != {"range", "symbol", "symbolRoles"}:
                raise ValueError("SCIP occurrence shape is unsupported")
            symbol, roles = row["symbol"], row["symbolRoles"]
            if not isinstance(symbol, str) or not symbol or len(symbol) > _MAX_SYMBOL:
                raise ValueError("SCIP symbol is invalid")
            if not isinstance(roles, int) or isinstance(roles, bool) or roles < 0 or roles > 127:
                raise ValueError("SCIP symbol roles are invalid")
            source_range = _range(row["range"])
            signature = (path, source_range, roles)
            occurrences.setdefault(symbol, {})[signature] = (
                path, source_range, roles, hashlib.sha256(payload).hexdigest(),
            )
    return metadata, occurrences


def _print(spec, root, deadline, runner):
    return PROVIDERS.run_provider(
        spec, ("print", "--json", "index.scip"), root, deadline,
        runner=runner, expect_json=True,
    )


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
    for arguments, tokens in (
        (("--help",), ("print",)),
        (("print", "--help"), ("--json", "<index>")),
    ):
        help_result = PROVIDERS.run_provider(spec, arguments, resolved, deadline, runner=runner)
        if help_result.status != "ready":
            status = help_result.status if help_result.status in {"unsafe", "timed_out"} else "unsupported"
            return ProviderProbe("scip", status, "verified-provider", spec.executable, version, version_result.executable_sha256, detail=help_result.detail or "SCIP print help unavailable", repo_root=resolved)
        if help_result.executable_sha256 != version_result.executable_sha256:
            return ProviderProbe("scip", "unsafe", "verified-provider", spec.executable, version, version_result.executable_sha256, detail="provider executable changed between probes", repo_root=resolved)
        if not all(token in help_result.stdout for token in tokens):
            return ProviderProbe("scip", "unsupported", "verified-provider", spec.executable, version, version_result.executable_sha256, detail="SCIP help does not confirm read-only JSON print", repo_root=resolved)
    printed = _print(spec, resolved, deadline, runner)
    if printed.status != "ready":
        return ProviderProbe("scip", printed.status, "verified-provider", spec.executable, version, version_result.executable_sha256, detail=printed.detail or "SCIP print failed", repo_root=resolved)
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
    printed = _print(spec, root, deadline, runner)
    if printed.status != "ready":
        return _failure(printed.status, printed.detail or "SCIP print failed")
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
            source_path, source_range, _, source_digest = definition
            source_key = "definition:%s:%d" % (hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:16], definition_index)
            nodes[source_key] = {
                "key": source_key, "kind": _node_kind(source_path, symbol),
                "label": symbol[-256:], "location": source_path,
                "confidence": "verified-provider", "source_sha256": source_digest,
                "risk_domains": COMMON._risk_domains(source_path, symbol),
            }
            for reference_index, reference in enumerate(references):
                target_path, target_range, roles, target_digest = reference
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
                    ),
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
