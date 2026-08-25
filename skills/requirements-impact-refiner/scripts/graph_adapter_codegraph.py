#!/usr/bin/env python3
"""Detect-only adapter for a verified local CodeGraph 1.x JSON CLI."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypedDict, cast

if TYPE_CHECKING:
    from graph_providers import (
        Deadline,
        ProviderProbe,
        ProviderQuery,
        ProviderResult,
        ProviderSpec,
    )
    from graph_providers import (
        ProviderSpec as ProviderSpecType,
    )
    from typing_extensions import TypeGuard


class _ProviderContract(Protocol):
    ProviderProbe: type[ProviderProbe]
    ProviderResult: type[ProviderResult]
    ProviderSpec: type[ProviderSpec]

    def run_provider(
        self,
        spec: ProviderSpecType,
        arguments: Sequence[str],
        repo_root: Path | str,
        deadline: Deadline,
        *,
        runner: object = None,
        expect_json: bool = False,
    ) -> ProviderQuery: ...


class _SourceProof(TypedDict):
    excerpt: str
    sha256: str


class _CommonContract(Protocol):
    def _risk_domains(self, path: object, label: str = "") -> tuple[str, ...]: ...

    def _safe_relative(self, value: object) -> str | None: ...

    def _source_proof(
        self, root: Path, relative: str, source_range: Sequence[int]
    ) -> _SourceProof: ...

    def source_fingerprint(self, root: Path) -> str | None: ...


def _load(filename: str, name: str) -> object:
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


_loaded_providers = _load("graph_providers.py", "_rir_graph_providers")
_loaded_common = _load("graph_adapter_ast_grep.py", "_rir_graph_adapter_ast_grep")


def _is_provider_contract(value: object) -> TypeGuard[_ProviderContract]:
    return all(
        isinstance(getattr(value, name, None), type)
        for name in ("ProviderProbe", "ProviderResult", "ProviderSpec")
    ) and callable(getattr(value, "run_provider", None))


def _is_common_contract(value: object) -> TypeGuard[_CommonContract]:
    return all(
        callable(getattr(value, name, None))
        for name in ("_risk_domains", "_safe_relative", "_source_proof", "source_fingerprint")
    )


if not _is_provider_contract(_loaded_providers):
    raise ImportError("graph provider contract is incomplete")
if not _is_common_contract(_loaded_common):
    raise ImportError("ast-grep adapter contract is incomplete")
PROVIDERS = cast(_ProviderContract, _loaded_providers)
COMMON = cast(_CommonContract, _loaded_common)
if not TYPE_CHECKING:
    ProviderProbe = PROVIDERS.ProviderProbe
    ProviderResult = PROVIDERS.ProviderResult
    ProviderSpec = PROVIDERS.ProviderSpec

_VERSION = re.compile(r"(?i)^codegraph\s+1\.\d+\.\d+(?:[-+][^\s]+)?$")
_NODE_KINDS = frozenset(
    {
        "symbol",
        "file",
        "api_field",
        "data_key",
        "schema",
        "database",
        "cache",
        "event",
        "permission",
        "configuration",
        "operation",
        "test",
    }
)
_EDGE_KINDS = frozenset(
    {
        "calls",
        "references",
        "implements",
        "imports",
        "reads",
        "writes",
        "serializes",
        "persists",
        "caches",
        "publishes",
        "subscribes",
        "authorizes",
        "configures",
        "deploys",
        "tests",
    }
)
_MAX_SEEDS = 16
_MAX_NODES = 512
_MAX_EDGES = 2048


def _failure(status, detail, digests=()):
    return ProviderResult(
        "codegraph",
        status,
        "verified-provider",
        raw_receipt_sha256=digests,
        detail=str(detail)[:512],
    )


def _first_line(text):
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def _read_graph_json(result, label):
    if result.status != "ready":
        raise RuntimeError(result.detail or (label + " command failed"))
    value = result.parsed_json
    if not isinstance(value, dict):
        raise ValueError(label + " JSON must be an object")
    return value


def _source_range(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("provider source range must contain four integers")
    if any(
        not isinstance(item, int) or isinstance(item, bool) or item < 0 or item > 10_000_000
        for item in value
    ):
        raise ValueError("provider source range is invalid")
    if (value[2], value[3]) < (value[0], value[1]):
        raise ValueError("provider source range is reversed")
    return tuple(value)


def _evidence(prefix, value):
    start_line, start_col, end_line, end_col = _source_range(value)
    return "%s at %d:%d-%d:%d" % (prefix, start_line + 1, start_col + 1, end_line + 1, end_col + 1)


def _validate_status(value, root, fingerprint):
    required = {"schemaVersion", "project", "license", "provenance"}
    if set(value) != required or value["schemaVersion"] != 1:
        return "failed", "CodeGraph status JSON shape is unsupported", None
    project, license_info, provenance = value["project"], value["license"], value["provenance"]
    if not isinstance(project, dict) or set(project) != {
        "root",
        "sourceFingerprint",
        "fresh",
        "local",
    }:
        return "failed", "CodeGraph project status shape is unsupported", None
    try:
        reported_root = Path(project["root"])
    except TypeError:
        return "failed", "CodeGraph project root is invalid", None
    if not reported_root.is_absolute() or reported_root != root:
        return "unsupported", "CodeGraph project root does not exactly match repository", None
    if project["local"] is not True:
        return "unsupported", "remote CodeGraph projects are not allowed", None
    if not isinstance(license_info, dict) or set(license_info) != {"spdx", "verified"}:
        return "failed", "CodeGraph license status shape is unsupported", None
    if license_info != {"spdx": "Apache-2.0", "verified": True}:
        return "unsupported", "CodeGraph installation license is not verified", None
    if not isinstance(provenance, dict) or set(provenance) != {"channel", "artifact", "verified"}:
        return "failed", "CodeGraph provenance shape is unsupported", None
    if provenance != {"channel": "local-cli", "artifact": "codegraph", "verified": True}:
        return "unsupported", "CodeGraph installation provenance is not verified local CLI", None
    if project["fresh"] is not True or project["sourceFingerprint"] != fingerprint:
        return "stale", "CodeGraph project is stale for repository sources", None
    return (
        "ready",
        None,
        {"license": "Apache-2.0", "source_fingerprint": fingerprint, "provenance": "local-cli"},
    )


def probe(spec, root, deadline, runner) -> ProviderProbe:
    if not isinstance(spec, ProviderSpec) or spec.name != "codegraph":
        raise TypeError("CodeGraph probe requires its ProviderSpec")
    base = Path(root)
    resolved = base.resolve() if not base.is_symlink() and base.is_dir() else base.absolute()
    fingerprint = COMMON.source_fingerprint(resolved)
    if fingerprint is None:
        return ProviderProbe(
            "codegraph",
            "unsafe",
            repo_root=resolved,
            detail="repository source identity is unsafe or exceeds bounds",
        )
    version_result = PROVIDERS.run_provider(spec, ("--version",), resolved, deadline, runner=runner)
    if version_result.status != "ready":
        return ProviderProbe(
            "codegraph",
            version_result.status,
            "verified-provider",
            spec.executable,
            executable_sha256=version_result.executable_sha256,
            detail=version_result.detail,
            repo_root=resolved,
        )
    version = _first_line(version_result.stdout)
    if _VERSION.fullmatch(version) is None:
        return ProviderProbe(
            "codegraph",
            "unsupported",
            "verified-provider",
            spec.executable,
            version[:256] or None,
            version_result.executable_sha256,
            detail="CodeGraph 1.x is required",
            repo_root=resolved,
        )
    checks = (
        (("--help",), (r"(?m)^\s{2,}status\s*$", r"(?m)^\s{2,}explore\s*$")),
        (("status", "--help"), (r"(?m)^Usage:\s+codegraph status --json\s*$",)),
        (("explore", "--help"), (r"(?m)^Usage:\s+codegraph explore --json --seed <TEXT>\s*$",)),
    )
    capabilities = []
    for arguments, tokens in checks:
        help_result = PROVIDERS.run_provider(spec, arguments, resolved, deadline, runner=runner)
        if help_result.status != "ready":
            status = (
                help_result.status
                if help_result.status in {"unsafe", "timed_out"}
                else "unsupported"
            )
            return ProviderProbe(
                "codegraph",
                status,
                "verified-provider",
                spec.executable,
                version,
                version_result.executable_sha256,
                detail=help_result.detail or "CodeGraph help unavailable",
                repo_root=resolved,
            )
        if help_result.executable_sha256 != version_result.executable_sha256:
            return ProviderProbe(
                "codegraph",
                "unsafe",
                "verified-provider",
                spec.executable,
                version,
                version_result.executable_sha256,
                detail="provider executable changed between probes",
                repo_root=resolved,
            )
        if not all(re.search(pattern, help_result.stdout) for pattern in tokens):
            return ProviderProbe(
                "codegraph",
                "unsupported",
                "verified-provider",
                spec.executable,
                version,
                version_result.executable_sha256,
                detail="CodeGraph help does not confirm required read-only JSON capabilities",
                repo_root=resolved,
            )
        capabilities.append(" ".join(arguments))
    status_result = PROVIDERS.run_provider(
        spec, ("status", "--json"), resolved, deadline, runner=runner, expect_json=True
    )
    if status_result.status != "ready":
        return ProviderProbe(
            "codegraph",
            status_result.status,
            "verified-provider",
            spec.executable,
            version,
            version_result.executable_sha256,
            detail=status_result.detail or "CodeGraph status failed",
            repo_root=resolved,
        )
    if status_result.executable_sha256 != version_result.executable_sha256:
        return ProviderProbe(
            "codegraph",
            "unsafe",
            "verified-provider",
            spec.executable,
            version,
            version_result.executable_sha256,
            detail="provider executable changed before status",
            repo_root=resolved,
        )
    try:
        status_value = _read_graph_json(status_result, "CodeGraph status")
        status, detail, metadata = _validate_status(status_value, resolved, fingerprint)
    except (TypeError, ValueError, RuntimeError) as error:
        status, detail, metadata = "failed", str(error), None
    return ProviderProbe(
        "codegraph",
        status,
        "verified-provider",
        spec.executable,
        version,
        version_result.executable_sha256,
        tuple(dict.fromkeys(capabilities)),
        detail,
        resolved,
        metadata,
    )


def _parse_explore(value, root, fingerprint):
    required = {"schemaVersion", "projectRoot", "sourceFingerprint", "nodes", "edges"}
    if not isinstance(value, dict) or set(value) != required or value["schemaVersion"] != 1:
        raise ValueError("CodeGraph explore JSON shape is unsupported")
    if value["projectRoot"] != str(root) or value["sourceFingerprint"] != fingerprint:
        raise ValueError("CodeGraph explore identity does not match probe")
    raw_nodes, raw_edges = value["nodes"], value["edges"]
    if not isinstance(raw_nodes, list) or len(raw_nodes) > _MAX_NODES:
        raise ValueError("CodeGraph node collection exceeds supported shape")
    if not isinstance(raw_edges, list) or len(raw_edges) > _MAX_EDGES:
        raise ValueError("CodeGraph edge collection exceeds supported shape")
    nodes = {}
    for row in raw_nodes:
        if not isinstance(row, dict) or set(row) != {
            "id",
            "kind",
            "label",
            "path",
            "range",
            "excerpt",
        }:
            raise ValueError("CodeGraph node shape is unsupported")
        identifier, kind, label = row["id"], row["kind"], row["label"]
        path = COMMON._safe_relative(row["path"])
        if (
            not isinstance(identifier, str)
            or not identifier
            or len(identifier) > 256
            or identifier in nodes
        ):
            raise ValueError("CodeGraph node id is invalid or duplicated")
        if (
            kind not in _NODE_KINDS
            or not isinstance(label, str)
            or not label.strip()
            or len(label) > 256
        ):
            raise ValueError("CodeGraph node kind or label is invalid")
        source_range = _source_range(row["range"])
        proof = COMMON._source_proof(root, path, source_range) if path is not None else None
        if (
            path is None
            or proof is None
            or not isinstance(row["excerpt"], str)
            or row["excerpt"] != proof["excerpt"]
        ):
            raise ValueError("CodeGraph node path is outside regular repository source")
        nodes[identifier] = {
            "key": identifier,
            "kind": kind,
            "label": label,
            "location": path,
            "confidence": "verified-provider",
            "source_sha256": proof["sha256"],
            "risk_domains": COMMON._risk_domains(path, label),
        }
    edges = {}
    for row in raw_edges:
        if not isinstance(row, dict) or set(row) != {
            "source",
            "target",
            "kind",
            "path",
            "range",
            "excerpt",
        }:
            raise ValueError("CodeGraph edge shape is unsupported")
        source, target, kind = row["source"], row["target"], row["kind"]
        path = COMMON._safe_relative(row["path"])
        source_range = _source_range(row["range"])
        proof = COMMON._source_proof(root, path, source_range) if path is not None else None
        if (
            source not in nodes
            or target not in nodes
            or kind not in _EDGE_KINDS
            or proof is None
            or not isinstance(row["excerpt"], str)
            or row["excerpt"] != proof["excerpt"]
        ):
            raise ValueError("CodeGraph edge references invalid graph evidence")
        signature = (source, target, kind, path, source_range)
        edges[signature] = {
            "source": source,
            "target": target,
            "kind": kind,
            "location": path,
            "evidence": _evidence(f"CodeGraph {kind}", source_range)
            + ": "
            + proof["excerpt"][:128],
            "confidence": "verified-provider",
            "source_sha256": proof["sha256"],
        }
    return tuple(nodes.values()), tuple(edges.values())


def query(probe, seeds, deadline, runner) -> ProviderResult:
    if not isinstance(probe, ProviderProbe) or probe.name != "codegraph":
        raise TypeError("CodeGraph query requires its ProviderProbe")
    if probe.status != "ready" or probe.executable is None or probe.repo_root is None:
        return _failure(probe.status, probe.detail or "provider is not ready")
    root = probe.repo_root.resolve()
    fingerprint = COMMON.source_fingerprint(root)
    if fingerprint is None or fingerprint != probe.metadata.get("source_fingerprint"):
        return _failure("stale", "repository changed after CodeGraph probe")
    spec = ProviderSpec("codegraph", probe.executable)
    nodes: dict[object, Mapping[str, object]] = {}
    edges: dict[tuple[object, ...], Mapping[str, object]] = {}
    digests: list[str] = []
    for seed in tuple(seeds)[:_MAX_SEEDS]:
        term = getattr(seed, "term", None)
        if not isinstance(term, str) or not term or len(term) > 256:
            continue
        result = PROVIDERS.run_provider(
            spec,
            ("explore", "--json", "--seed", term),
            root,
            deadline,
            runner=runner,
            expect_json=True,
        )
        if result.status != "ready":
            return _failure(
                result.status, result.detail or "CodeGraph explore failed", tuple(digests)
            )
        if (
            probe.executable_sha256 is not None
            and result.executable_sha256 != probe.executable_sha256
        ):
            return _failure("unsafe", "CodeGraph executable changed after probe", tuple(digests))
        digest = hashlib.sha256(result.stdout.encode("utf-8")).hexdigest()
        digests.append(digest)
        try:
            parsed_nodes, parsed_edges = _parse_explore(result.parsed_json, root, fingerprint)
            for row in parsed_nodes:
                prior = nodes.get(row["key"])
                if prior is not None and prior != row:
                    raise ValueError("CodeGraph node id changed across seed queries")
                nodes[row["key"]] = row
            for row in parsed_edges:
                signature = (
                    row["source"],
                    row["target"],
                    row["kind"],
                    row["location"],
                    row["evidence"],
                )
                edges[signature] = row
        except (TypeError, ValueError) as error:
            return _failure("failed", error, tuple(digests))
    if COMMON.source_fingerprint(root) != fingerprint:
        return _failure("stale", "repository changed during CodeGraph query", tuple(digests))
    return ProviderResult(
        "codegraph",
        "ready",
        "verified-provider",
        tuple(nodes.values()),
        tuple(edges.values()),
        raw_receipt_sha256=tuple(digests),
        metadata={"queries": len(digests)},
    )


__all__ = ["probe", "query"]
