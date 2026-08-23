#!/usr/bin/env python3
"""Deterministic, bounded lexical fallback for repository impact discovery."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import stat
import sys
from types import MappingProxyType
from typing import Mapping, Sequence


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
GraphNode = GRAPH.GraphNode
GraphEdge = GRAPH.GraphEdge
GraphPath = GRAPH.GraphPath
FrontierEntry = GRAPH.FrontierEntry

DEFAULT_MAX_FILE_BYTES = 1_048_576
IGNORED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", "vendor", "build", "dist", "generated",
    "node_modules", ".next", ".venv", "venv", "target", "coverage",
})
_DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
_SLASHED = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*(?:/[A-Za-z_][A-Za-z0-9_.-]*)+")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_QUOTED = re.compile(r"(?P<quote>['\"])(?P<value>[^'\"\r\n]{2,256})(?P=quote)")
_COMMON_TERMS = frozenset({
    "assert", "class", "const", "def", "export", "from", "function",
    "import", "interface", "profile", "return", "static", "string", "struct",
    "target", "tests", "true", "value",
})
_RISK_ORDER = (
    "authorization/privacy", "interfaces", "data", "state/concurrency",
    "compatibility", "operations", "regression", "functionality",
    "legal/policy",
)
_RISK_RANK = {name: index for index, name in enumerate(_RISK_ORDER)}


@dataclass(frozen=True)
class ScanSeed:
    term: str
    location: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.term, str) or not self.term.strip() or len(self.term) > GRAPH.MAX_STRING_LENGTH:
            raise ValueError("scan seed term must be a bounded non-empty string")
        if self.location is not None and not GRAPH._safe_path(self.location):
            raise ValueError("scan seed location must be a safe repository-relative path")


@dataclass(frozen=True)
class ScanLimits:
    max_seconds: int = 30
    max_files: int = 500
    max_bytes: int = 8_000_000
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_nodes: int = GRAPH.MAX_NODES
    max_edges: int = GRAPH.MAX_EDGES
    max_paths: int = GRAPH.MAX_PATHS

    def __post_init__(self) -> None:
        for name in (
            "max_seconds", "max_files", "max_bytes", "max_file_bytes",
            "max_nodes", "max_edges", "max_paths",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.max_seconds > 30:
            raise ValueError("max_seconds must not exceed 30")
        if self.max_file_bytes > DEFAULT_MAX_FILE_BYTES:
            raise ValueError("max_file_bytes must not exceed 1 MiB")
        for name, maximum in (
            ("max_nodes", GRAPH.MAX_NODES),
            ("max_edges", GRAPH.MAX_EDGES),
            ("max_paths", GRAPH.MAX_PATHS),
        ):
            if getattr(self, name) > maximum:
                raise ValueError(f"{name} exceeds graph contract maximum")


@dataclass(frozen=True)
class BuiltInScanResult:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    paths: tuple[GraphPath, ...]
    frontier: tuple[FrontierEntry, ...]
    source_digests: Mapping[str, str]
    skipped: Mapping[str, str]
    files_scanned: int
    bytes_scanned: int
    budget_status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "edges", tuple(self.edges))
        object.__setattr__(self, "paths", tuple(self.paths))
        object.__setattr__(self, "frontier", tuple(self.frontier))
        object.__setattr__(self, "source_digests", MappingProxyType(dict(self.source_digests)))
        object.__setattr__(self, "skipped", MappingProxyType(dict(self.skipped)))


def _empty_result(status="closed"):
    return BuiltInScanResult((), (), (), (), {}, {}, 0, 0, status)


def _risk_domains(location: str | None, text: str = "") -> tuple[str, ...]:
    haystack = ((location or "") + " " + text).lower()
    domains = set()
    if any(term in haystack for term in ("auth", "permission", "privacy", "token", "role")):
        domains.add("authorization/privacy")
    if any(term in haystack for term in ("api", "schema", "dto", "interface")):
        domains.add("interfaces")
    if any(term in haystack for term in ("data", "database", "migration", "serialize")):
        domains.add("data")
    if any(term in haystack for term in ("cache", "state", "lock", "concurr")):
        domains.add("state/concurrency")
    if any(term in haystack for term in ("mobile", "desktop", "compat", "migration")):
        domains.add("compatibility")
    if any(term in haystack for term in ("event", "deploy", "config", "queue")):
        domains.add("operations")
    if any(term in haystack for term in ("test", "fixture", "migration")):
        domains.add("regression")
    if not domains:
        domains.add("functionality")
    return tuple(sorted(domains, key=lambda item: (_RISK_RANK[item], item)))


def _node_kind(location: str | None, text: str) -> str:
    haystack = ((location or "") + " " + text).lower()
    if "test" in haystack or "fixture" in haystack:
        return "test"
    if any(term in haystack for term in ("auth", "permission", "privacy")):
        return "permission"
    if "event" in haystack:
        return "event"
    if "cache" in haystack:
        return "cache"
    if "config" in haystack:
        return "configuration"
    if "api" in haystack or "dto" in haystack:
        return "api_field"
    return "file"


def _terms(text: str) -> frozenset[str]:
    values = set()
    values.update(_DOTTED.findall(text))
    values.update(_SLASHED.findall(text))
    values.update(_IDENTIFIER.findall(text))
    values.update(match.group("value") for match in _QUOTED.finditer(text))
    expanded = set(values)
    for value in values:
        expanded.update(part for part in re.split(r"[./]", value) if len(part) >= 4)
        if "." in value:
            expanded.add(value.replace(".", "/"))
        if "/" in value:
            expanded.add(value.replace("/", "."))
    return frozenset(
        value for value in expanded
        if len(value) >= 4 and value.lower() not in _COMMON_TERMS
    )


def _read_regular_file(path: Path, maximum: int) -> tuple[bytes | None, str | None]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(str(path), flags)
    except (OSError, ValueError):
        return None, "unsafe-file"
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            return None, "not-regular"
        if metadata.st_size > maximum:
            return None, "oversized"
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            payload = handle.read(maximum + 1)
        if len(payload) > maximum:
            return None, "oversized"
        return payload, None
    finally:
        os.close(descriptor)


def _walk_files(root: Path, expired, skipped: dict[str, str]):
    pending = [root]
    while pending:
        if expired():
            return
        directory = pending.pop(0)
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            continue
        directories = []
        for entry in entries:
            relative = Path(entry.path).relative_to(root).as_posix()
            if entry.is_symlink():
                skipped[relative] = "symlink"
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in IGNORED_DIRECTORIES:
                        directories.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    yield Path(entry.path), relative
            except OSError:
                skipped[relative] = "unsafe-file"
        pending[0:0] = directories


def _edge_kind(target: str, evidence: str) -> tuple[str, str]:
    lowered = target.lower()
    if "test" in lowered or "fixture" in lowered:
        return "tests", "structural-inferred"
    if "cache" in lowered:
        return "caches", "structural-inferred"
    if "event" in lowered:
        return "publishes", "structural-inferred"
    if "/" in evidence or "." in evidence:
        return "imports", "structural-inferred"
    return "references", "lexical"


def _path_sort_key(path_data, node_risks):
    node_ids, _ = path_data
    domains = {domain for node_id in node_ids for domain in node_risks[node_id]}
    best = min((_RISK_RANK[domain] for domain in domains), default=len(_RISK_ORDER))
    return best, len(node_ids) - 1, node_ids


def scan_repository(
    repo_root: Path | str,
    seeds: Sequence[ScanSeed],
    limits: ScanLimits,
    clock,
) -> BuiltInScanResult:
    """Scan regular UTF-8 source files without crossing any supplied bound."""
    root = Path(repo_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("repo_root must be a regular directory")
    root = root.resolve()
    normalized_seeds = tuple(sorted(set(seeds), key=lambda item: (item.location or "", item.term)))
    if any(not isinstance(seed, ScanSeed) for seed in normalized_seeds):
        raise TypeError("seeds must contain ScanSeed values")
    if not isinstance(limits, ScanLimits):
        raise TypeError("limits must be ScanLimits")
    started = clock.monotonic()
    deadline = started + limits.max_seconds

    def expired():
        return clock.monotonic() >= deadline

    if expired():
        return _empty_result("budget_exhausted")

    skipped: dict[str, str] = {}
    documents: dict[str, tuple[str, frozenset[str], str]] = {}
    bytes_scanned = 0
    files_scanned = 0
    exhausted = False
    for path, relative in _walk_files(root, expired, skipped):
        if expired():
            exhausted = True
            break
        try:
            size = path.stat().st_size
        except OSError:
            skipped[relative] = "unsafe-file"
            continue
        if size > limits.max_file_bytes:
            skipped[relative] = "oversized"
            exhausted = True
            continue
        if files_scanned >= limits.max_files:
            skipped[relative] = "file-limit"
            exhausted = True
            continue
        if bytes_scanned + size > limits.max_bytes:
            skipped[relative] = "byte-limit"
            exhausted = True
            continue
        payload, reason = _read_regular_file(path, limits.max_file_bytes)
        if reason is not None or payload is None:
            skipped[relative] = reason or "unsafe-file"
            if reason == "oversized":
                exhausted = True
            continue
        files_scanned += 1
        bytes_scanned += len(payload)
        if b"\x00" in payload:
            skipped[relative] = "binary"
            continue
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            skipped[relative] = "invalid-utf8"
            continue
        documents[relative] = (text, _terms(text), hashlib.sha256(payload).hexdigest())

    if expired():
        exhausted = True

    def deadline_result(nodes=(), edges=()):
        frontier = ()
        if nodes:
            last = nodes[-1]
            frontier = (
                FrontierEntry(
                    "FRONTIER-001", last.id, "built-in scan deadline exhausted",
                    last.risk_domains,
                ),
            )
        return BuiltInScanResult(
            tuple(nodes), tuple(edges), (), frontier,
            {location: documents[location][2] for location in sorted(documents)},
            {path: skipped[path] for path in sorted(skipped)},
            files_scanned, bytes_scanned, "budget_exhausted",
        )

    if exhausted and expired():
        return deadline_result()

    seed_locations = {seed.location for seed in normalized_seeds if seed.location in documents}
    seed_terms = {term for seed in normalized_seeds for term in _terms(seed.term)}
    if not seed_terms:
        seed_terms = {seed.term for seed in normalized_seeds}

    relationships = []
    locations = sorted(documents)
    for source in locations:
        source_terms = documents[source][1]
        for target in locations:
            if expired():
                return deadline_result()
            if source == target:
                continue
            shared = sorted(source_terms & documents[target][1], key=lambda value: (-len(value), value))
            if shared:
                relationships.append((source, target, shared[0]))

    reachable = set(seed_locations)
    reachable.update(
        location for location, (_, terms, _) in documents.items()
        if terms & seed_terms
    )
    changed = True
    while changed and not expired():
        changed = False
        for source, target, _ in relationships:
            if expired():
                exhausted = True
                break
            if source in reachable and target not in reachable:
                reachable.add(target)
                changed = True
    if expired():
        return deadline_result()

    supplied_only = [seed for seed in normalized_seeds if seed.location is None or seed.location not in documents]
    ordered_locations = sorted(
        reachable,
        key=lambda location: (
            0 if location in seed_locations else 1,
            min((_RISK_RANK[item] for item in _risk_domains(location, documents[location][0])), default=99),
            location,
        ),
    )
    candidates = [(location, None) for location in ordered_locations]
    candidates.extend((None, seed) for seed in supplied_only)
    if len(candidates) > limits.max_nodes:
        exhausted = True
    candidates = candidates[:limits.max_nodes]

    nodes = []
    location_ids = {}
    node_risks = {}
    for index, (location, seed) in enumerate(candidates, start=1):
        if expired():
            return deadline_result(nodes)
        node_id = f"NODE-{index:03d}"
        if location is None:
            label = seed.term
            risk = _risk_domains(seed.location, seed.term)
            node = GraphNode(node_id, "symbol", label, seed.location, "builtin", "lexical", None, risk)
        else:
            text, _, digest = documents[location]
            risk = _risk_domains(location, text)
            label = next((seed.term for seed in normalized_seeds if seed.location == location), location)
            confidence = "structural-inferred" if location in seed_locations else "lexical"
            node = GraphNode(node_id, _node_kind(location, text), label, location, "builtin", confidence, digest, risk)
            location_ids[location] = node_id
        nodes.append(node)
        node_risks[node_id] = risk

    edge_candidates = []
    for source, target, evidence in relationships:
        if expired():
            return deadline_result(nodes)
        if source in location_ids and target in location_ids:
            kind, confidence = _edge_kind(target, evidence)
            edge_candidates.append((source, target, kind, confidence, evidence))
    edge_candidates.sort(key=lambda item: (location_ids[item[0]], location_ids[item[1]], item[2], item[4]))
    if len(edge_candidates) > limits.max_edges:
        exhausted = True
    edge_candidates = edge_candidates[:limits.max_edges]
    edges = []
    adjacency = {}
    for index, (source, target, kind, confidence, evidence) in enumerate(edge_candidates, start=1):
        if expired():
            return deadline_result(nodes, edges)
        edge_id = f"EDGE-{index:03d}"
        edge = GraphEdge(
            edge_id, location_ids[source], location_ids[target], kind, target,
            evidence[:GRAPH.MAX_STRING_LENGTH], confidence, "builtin", documents[target][2],
        )
        edges.append(edge)
        adjacency.setdefault(edge.source, []).append((edge.target, edge.id))

    raw_paths = []
    start_ids = sorted(location_ids[location] for location in seed_locations if location in location_ids)
    path_limit_reached = limits.max_paths == 0 and bool(start_ids)
    for start_id in start_ids:
        if path_limit_reached:
            exhausted = True
            break
        stack = [(start_id, (start_id,), ())]
        while stack:
            if expired():
                exhausted = True
                stack.clear()
                break
            current, path_nodes, path_edges = stack.pop()
            if path_edges:
                raw_paths.append((path_nodes, path_edges))
                if len(raw_paths) >= limits.max_paths:
                    exhausted = True
                    path_limit_reached = True
                    stack.clear()
                    break
            if len(path_edges) >= 6:
                continue
            for target, edge_id in reversed(adjacency.get(current, ())):
                if target not in path_nodes:
                    stack.append((target, path_nodes + (target,), path_edges + (edge_id,)))
        if path_limit_reached:
            break

    if expired():
        return deadline_result(nodes, edges)

    unique_paths = sorted(set(raw_paths), key=lambda item: _path_sort_key(item, node_risks))
    if len(unique_paths) > limits.max_paths:
        exhausted = True
    unique_paths = unique_paths[:limits.max_paths]
    paths = []
    for index, (path_nodes, path_edges) in enumerate(unique_paths, start=1):
        domains = {
            domain for node_id in path_nodes for domain in node_risks[node_id]
        }
        ordered_domains = tuple(sorted(domains, key=lambda item: (_RISK_RANK[item], item)))
        paths.append(GraphPath(f"PATH-{index:03d}", path_nodes, path_edges, len(path_edges), ordered_domains))

    frontier = ()
    if exhausted and nodes:
        frontier = (
            FrontierEntry("FRONTIER-001", nodes[-1].id, "built-in scan budget exhausted", nodes[-1].risk_domains),
        )
    return BuiltInScanResult(
        tuple(nodes), tuple(edges), tuple(paths), frontier,
        {location: documents[location][2] for location in sorted(documents)},
        {path: skipped[path] for path in sorted(skipped)},
        files_scanned, bytes_scanned,
        "budget_exhausted" if exhausted else "closed",
    )
