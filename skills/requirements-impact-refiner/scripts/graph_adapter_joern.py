#!/usr/bin/env python3
"""Deep-only, detect-only adapter for an existing fresh Joern graph."""

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
CODEGRAPH = _load("graph_adapter_codegraph.py", "_rir_graph_adapter_codegraph")
ProviderProbe = PROVIDERS.ProviderProbe
ProviderResult = PROVIDERS.ProviderResult
ProviderSpec = PROVIDERS.ProviderSpec

_VERSION = re.compile(r"(?i)^joern\s+4\.\d+\.\d+(?:[-+][^\s]+)?$")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_MAX_GRAPH_BYTES = 512 * 1024 * 1024
_MAX_METADATA_BYTES = 64 * 1024


def _failure(status, detail, digests=()):
    return ProviderResult("joern", status, "verified-provider", raw_receipt_sha256=digests, detail=str(detail)[:512])


def _file_bytes(path, maximum):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            return None
        payload = bytearray()
        while len(payload) <= maximum:
            chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        return bytes(payload) if len(payload) <= maximum else None
    finally:
        os.close(descriptor)


def _file_sha256(path, maximum):
    payload = _file_bytes(path, maximum)
    return hashlib.sha256(payload).hexdigest() if payload is not None else None


def _regular_graph(root):
    directory = root / ".joern"
    graph = directory / "cpg.bin"
    metadata = directory / "metadata.json"
    try:
        directory_info = directory.lstat()
    except FileNotFoundError:
        return "stale", "existing repository-local Joern graph is missing", None
    except OSError as error:
        return "unsafe", str(error), None
    if stat.S_ISLNK(directory_info.st_mode) or not stat.S_ISDIR(directory_info.st_mode):
        return "unsafe", ".joern must be a regular repository-local directory", None
    for path, maximum in ((graph, _MAX_GRAPH_BYTES), (metadata, _MAX_METADATA_BYTES)):
        try:
            info = path.lstat()
        except FileNotFoundError:
            return "stale", "existing Joern graph metadata is incomplete", None
        except OSError as error:
            return "unsafe", str(error), None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > maximum:
            return "unsafe", "Joern graph files must be bounded regular non-symlink files", None
    digest = _file_sha256(graph, _MAX_GRAPH_BYTES)
    if digest is None:
        return "unsafe", "Joern graph identity could not be read safely", None
    return "ready", None, digest


def _metadata(root):
    payload = _file_bytes(root / ".joern" / "metadata.json", _MAX_METADATA_BYTES)
    if payload is None:
        raise ValueError("Joern graph metadata is unreadable")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Joern graph metadata must be UTF-8 JSON") from error
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "projectRoot", "sourceFingerprint", "createdBy"} or value["schemaVersion"] != 1:
        raise ValueError("Joern graph metadata shape is unsupported")
    created = value["createdBy"]
    if not isinstance(created, dict) or set(created) != {"name", "version"}:
        raise ValueError("Joern graph creator metadata shape is unsupported")
    if created.get("name") != "joern" or not isinstance(created.get("version"), str):
        raise ValueError("Joern graph creator is unsupported")
    if not isinstance(value["sourceFingerprint"], str) or _HEX64.fullmatch(value["sourceFingerprint"]) is None:
        raise ValueError("Joern source fingerprint is invalid")
    return value


def probe(spec, root, deadline, runner) -> ProviderProbe:
    if not isinstance(spec, ProviderSpec) or spec.name != "joern":
        raise TypeError("Joern probe requires its ProviderSpec")
    base = Path(root)
    resolved = base.resolve() if not base.is_symlink() and base.is_dir() else base.absolute()
    graph_status, graph_detail, graph_digest = _regular_graph(resolved)
    if graph_status != "ready":
        return ProviderProbe("joern", graph_status, "verified-provider", spec.executable, detail=graph_detail, repo_root=resolved)
    fingerprint = COMMON.source_fingerprint(resolved)
    if fingerprint is None:
        return ProviderProbe("joern", "unsafe", "verified-provider", spec.executable, detail="repository source identity is unsafe or exceeds bounds", repo_root=resolved)
    try:
        metadata = _metadata(resolved)
    except ValueError as error:
        return ProviderProbe("joern", "failed", "verified-provider", spec.executable, detail=error, repo_root=resolved)
    if metadata["projectRoot"] != str(resolved):
        return ProviderProbe("joern", "unsupported", "verified-provider", spec.executable, detail="Joern graph project root does not exactly match repository", repo_root=resolved)
    if metadata["sourceFingerprint"] != fingerprint:
        return ProviderProbe("joern", "stale", "verified-provider", spec.executable, detail="Joern graph is stale for repository sources", repo_root=resolved)
    version_result = PROVIDERS.run_provider(spec, ("--version",), resolved, deadline, runner=runner)
    if version_result.status != "ready":
        return ProviderProbe("joern", version_result.status, "verified-provider", spec.executable, executable_sha256=version_result.executable_sha256, detail=version_result.detail, repo_root=resolved)
    version = next((line.strip() for line in version_result.stdout.splitlines() if line.strip()), "")
    if _VERSION.fullmatch(version) is None:
        return ProviderProbe("joern", "unsupported", "verified-provider", spec.executable, version[:256] or None, version_result.executable_sha256, detail="Joern 4.x JSON query CLI is required", repo_root=resolved)
    if metadata["createdBy"]["version"] not in version:
        return ProviderProbe("joern", "unsupported", "verified-provider", spec.executable, version, version_result.executable_sha256, detail="Joern graph creator version does not match installed reader", repo_root=resolved)
    for arguments in (("--help",), ("query", "--help")):
        help_result = PROVIDERS.run_provider(spec, arguments, resolved, deadline, runner=runner)
        if help_result.status != "ready":
            status = help_result.status if help_result.status in {"unsafe", "timed_out"} else "unsupported"
            return ProviderProbe("joern", status, "verified-provider", spec.executable, version, version_result.executable_sha256, detail=help_result.detail or "Joern query help unavailable", repo_root=resolved)
        if help_result.executable_sha256 != version_result.executable_sha256:
            return ProviderProbe("joern", "unsafe", "verified-provider", spec.executable, version, version_result.executable_sha256, detail="provider executable changed between probes", repo_root=resolved)
        if not all(token in help_result.stdout for token in ("query", "--json", "--graph", "--seed")):
            return ProviderProbe("joern", "unsupported", "verified-provider", spec.executable, version, version_result.executable_sha256, detail="Joern help does not confirm non-interactive JSON graph queries", repo_root=resolved)
    return ProviderProbe(
        "joern", "ready", "verified-provider", spec.executable, version,
        version_result.executable_sha256, ("query-json", "existing-graph"),
        repo_root=resolved, metadata={
            "graph": ".joern/cpg.bin", "graph_sha256": graph_digest,
            "source_fingerprint": fingerprint,
        },
    )


def query(probe, seeds, deadline, runner) -> ProviderResult:
    if not isinstance(probe, ProviderProbe) or probe.name != "joern":
        raise TypeError("Joern query requires its ProviderProbe")
    if probe.status != "ready" or probe.executable is None or probe.repo_root is None:
        return _failure(probe.status, probe.detail or "provider is not ready")
    root = probe.repo_root.resolve()
    graph_status, graph_detail, graph_digest = _regular_graph(root)
    if graph_status != "ready":
        return _failure(graph_status, graph_detail)
    fingerprint = COMMON.source_fingerprint(root)
    if fingerprint != probe.metadata.get("source_fingerprint") or graph_digest != probe.metadata.get("graph_sha256"):
        return _failure("stale", "repository or Joern graph changed after probe")
    spec = ProviderSpec("joern", probe.executable)
    nodes = {}
    edges = {}
    digests = []
    for seed in tuple(seeds)[:16]:
        term = getattr(seed, "term", None)
        if not isinstance(term, str) or not term or len(term) > 256:
            continue
        result = PROVIDERS.run_provider(
            spec, ("query", "--json", "--graph", ".joern/cpg.bin", "--seed", term),
            root, deadline, runner=runner, expect_json=True,
        )
        if result.status != "ready":
            return _failure(result.status, result.detail or "Joern graph query failed", tuple(digests))
        if probe.executable_sha256 is not None and result.executable_sha256 != probe.executable_sha256:
            return _failure("unsafe", "Joern executable changed after probe", tuple(digests))
        digest = hashlib.sha256(result.stdout.encode("utf-8")).hexdigest()
        digests.append(digest)
        try:
            parsed_nodes, parsed_edges = CODEGRAPH._parse_explore(result.parsed_json, root, fingerprint)
            for row in parsed_nodes:
                prior = nodes.get(row["key"])
                if prior is not None and prior != row:
                    raise ValueError("Joern node id changed across seed queries")
                nodes[row["key"]] = row
            for row in parsed_edges:
                rewritten = dict(row)
                rewritten["evidence"] = row["evidence"].replace("CodeGraph ", "Joern ", 1)
                signature = (rewritten["source"], rewritten["target"], rewritten["kind"], rewritten["location"], rewritten["evidence"])
                edges[signature] = rewritten
        except (TypeError, ValueError) as error:
            return _failure("failed", error, tuple(digests))
    final_graph = _file_sha256(root / ".joern" / "cpg.bin", _MAX_GRAPH_BYTES)
    if COMMON.source_fingerprint(root) != fingerprint or final_graph != graph_digest:
        return _failure("stale", "repository or Joern graph changed during query", tuple(digests))
    return ProviderResult(
        "joern", "ready", "verified-provider", tuple(nodes.values()),
        tuple(edges.values()), raw_receipt_sha256=tuple(digests),
        metadata={"queries": len(digests), "graph_sha256": graph_digest},
    )


__all__ = ["probe", "query"]
