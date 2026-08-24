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
MAX_GRAPH_ID = 999
IGNORED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", ".requirements-impact-refiner",
    "vendor", "build", "dist", "generated",
    "node_modules", ".next", ".venv", "venv", "target", "coverage",
})
_DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
_SLASHED = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*(?:/[A-Za-z_][A-Za-z0-9_.-]*)+")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_QUOTED = re.compile(r"(?P<quote>['\"])(?P<value>[^'\"\r\n]{2,256})(?P=quote)")
_IMPORT = re.compile(r"(?m)^\s*(?:from|import)\s+(?P<value>[^\r\n#]+)")
# Credential-shaped names are matched as whole identifier segments so that
# prefixed and suffixed forms (GITHUB_TOKEN, STRIPE_SECRET_KEY, apiKey) are
# caught, while embedded fragments (tokenizer, keyboard) are preserved.
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(?P<prefix>(?<![A-Za-z0-9_])(?P<keyquote>['\"]?)"
    r"(?:[A-Za-z0-9]+[_-])*"
    r"(?:aws[_-]secret[_-]access[_-]key|client[_-]?secret|access[_-]?token|"
    r"refresh[_-]?token|auth[_-]?token|api[_-]?key|api[_-]?secret|"
    r"private[_-]key|secret[_-]?key|token|password|passwd|passphrase|secret|"
    r"credential)"
    r"(?:[_-][A-Za-z0-9]+)*"
    r"(?P=keyquote)\s*[:=]\s*)"
    r"(?:(?P<quote>['\"])(?P<quoted>[^'\"\r\n]+)(?P=quote)|"
    r"(?P<bare>[^\s,#}\]]+))"
)
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
    max_nodes: int = min(GRAPH.MAX_NODES, MAX_GRAPH_ID)
    max_edges: int = min(GRAPH.MAX_EDGES, MAX_GRAPH_ID)
    max_paths: int = min(GRAPH.MAX_PATHS, MAX_GRAPH_ID)

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
            ("max_nodes", min(GRAPH.MAX_NODES, MAX_GRAPH_ID)),
            ("max_edges", min(GRAPH.MAX_EDGES, MAX_GRAPH_ID)),
            ("max_paths", min(GRAPH.MAX_PATHS, MAX_GRAPH_ID)),
        ):
            if getattr(self, name) > maximum:
                raise ValueError(f"{name} exceeds graph contract three-digit ID maximum")


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


def _expanded_terms(values) -> frozenset[str]:
    expanded = set(values)
    for value in tuple(expanded):
        expanded.update(part for part in re.split(r"[./]", value) if len(part) >= 4)
        if "." in value:
            expanded.add(value.replace(".", "/"))
        if "/" in value:
            expanded.add(value.replace("/", "."))
    return frozenset(
        value for value in expanded
        if len(value) >= 4 and value.lower() not in _COMMON_TERMS
    )


def _safe_graph_text(value: str, sensitive_literals=()) -> str:
    if value in sensitive_literals:
        return "sensitive-sha256-" + hashlib.sha256(value.encode("utf-8")).hexdigest()
    return value


def _redact_sensitive_literals(text: str) -> tuple[str, frozenset[str]]:
    sensitive = set()

    def replace(match):
        value = match.group("quoted") or match.group("bare")
        sensitive.add(value)
        safe = _safe_graph_text(value, (value,))
        quote = match.group("quote") or ""
        return match.group("prefix") + quote + safe + quote

    return _SENSITIVE_ASSIGNMENT.sub(replace, text), frozenset(sensitive)


def _term_categories(text: str) -> Mapping[str, frozenset[str]]:
    values = set()
    values.update(_DOTTED.findall(text))
    values.update(_SLASHED.findall(text))
    values.update(_IDENTIFIER.findall(text))
    values.update(match.group("value") for match in _QUOTED.finditer(text))
    categories = {value: {"lexical"} for value in _expanded_terms(values)}
    imports = set()
    for match in _IMPORT.finditer(text):
        import_text = match.group("value")
        imports.update(_DOTTED.findall(import_text))
        imports.update(_IDENTIFIER.findall(import_text))
    for value in _expanded_terms(imports):
        categories.setdefault(value, set()).add("import")
    return MappingProxyType({
        value: frozenset(categories[value]) for value in sorted(categories)
    })


def _terms(text: str) -> frozenset[str]:
    return frozenset(_term_categories(text))


def _open_below_root(root: Path, relative: str) -> int:
    """Open relative under root with a per-component descriptor walk, so a
    parent directory swapped for a symlink after the walk check cannot pull
    out-of-repo content into the scan."""
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    file_flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
        file_flags |= os.O_NOFOLLOW
    parts = [part for part in relative.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("unsafe relative path")
    parent = os.open(str(root), directory_flags)
    try:
        for part in parts[:-1]:
            next_parent = os.open(part, directory_flags, dir_fd=parent)
            os.close(parent)
            parent = next_parent
        return os.open(parts[-1], file_flags, dir_fd=parent)
    finally:
        os.close(parent)


def _read_regular_file(
    root: Path, relative: str, maximum: int, remaining: int | None = None,
    read_allowed: bool = True,
) -> tuple[bytes | None, str | None]:
    try:
        descriptor = _open_below_root(root, relative)
    except (OSError, ValueError):
        return None, "unsafe-file"
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            return None, "not-regular"
        if metadata.st_size > maximum:
            return None, "oversized"
        if remaining is not None and metadata.st_size > remaining:
            return None, "byte-limit"
        if not read_allowed:
            return None, "file-limit"
        read_limit = min(maximum, remaining) if remaining is not None else maximum
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            payload = handle.read(read_limit + 1)
        if len(payload) > maximum:
            return None, "oversized"
        if remaining is not None and len(payload) > remaining:
            return None, "byte-limit"
        return payload, None
    finally:
        os.close(descriptor)


def _walk_files(
    root: Path, expired, skipped: dict[str, str], traversal_errors: list[str]
):
    pending = [root]
    while pending:
        if expired():
            return
        directory = pending.pop(0)
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            traversal_errors.append(directory.relative_to(root).as_posix())
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
                traversal_errors.append(relative)
        pending[0:0] = directories


_TEST_PATH_TOKENS = frozenset(
    {"test", "tests", "testing", "conftest", "fixture", "fixtures"}
)


def _is_test_path(target: str) -> bool:
    """Match whole path segments so latest/contest/testimonial stay untouched."""
    for part in target.lower().split("/"):
        for token in re.split(r"[^a-z0-9]+", part):
            if token in _TEST_PATH_TOKENS:
                return True
    return False


def _import_resolves_to_target(target: str, evidence: str) -> bool:
    """An imports edge must plausibly resolve to the target file, not merely
    share a token that happened to appear on an import line of the source."""
    stem = target.lower().rsplit("/", 1)[-1].split(".", 1)[0]
    collapsed_stem = re.sub(r"[^a-z0-9]", "", stem)
    collapsed_evidence = re.sub(r"[^a-z0-9]", "", evidence.lower())
    if len(collapsed_evidence) < 3 or not collapsed_stem:
        return False
    return (
        collapsed_evidence in collapsed_stem
        or collapsed_stem in collapsed_evidence
    )


def _edge_kind(
    target: str, categories: frozenset[str], evidence: str
) -> tuple[str, str]:
    if _is_test_path(target):
        return "tests", "structural-inferred"
    if "import" in categories and _import_resolves_to_target(target, evidence):
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
    traversal_errors: list[str] = []
    documents: dict[str, tuple[str, frozenset[str], str, Mapping[str, frozenset[str]]]] = {}
    sensitive_literals = set()
    bytes_scanned = 0
    files_scanned = 0
    exhausted = False
    for path, relative in _walk_files(root, expired, skipped, traversal_errors):
        if expired():
            exhausted = True
            break
        remaining = limits.max_bytes - bytes_scanned
        payload, reason = _read_regular_file(
            root, relative, limits.max_file_bytes, remaining,
            read_allowed=files_scanned < limits.max_files,
        )
        if reason is not None or payload is None:
            skipped[relative] = reason or "unsafe-file"
            if reason in {"oversized", "byte-limit", "file-limit"}:
                exhausted = True
            continue
        if len(payload) > remaining:
            skipped[relative] = "byte-limit"
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
        safe_text, found_sensitive = _redact_sensitive_literals(text)
        sensitive_literals.update(found_sensitive)
        categories = _term_categories(safe_text)
        documents[relative] = (
            safe_text, frozenset(categories), hashlib.sha256(payload).hexdigest(),
            categories,
        )

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
                evidence = shared[0]
                categories = documents[source][3].get(evidence, frozenset())
                relationships.append((source, target, evidence, categories))

    reachable = set(seed_locations)
    reachable.update(
        location for location, (_, terms, _, _) in documents.items()
        if terms & seed_terms
    )
    changed = True
    while changed and not expired():
        changed = False
        for source, target, _, _ in relationships:
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
    all_error_locations = sorted(set(traversal_errors))
    error_limit = (
        GRAPH.MAX_FRONTIER - 1
        if len(all_error_locations) > GRAPH.MAX_FRONTIER
        else GRAPH.MAX_FRONTIER
    )
    error_locations = all_error_locations[:error_limit]
    matched_locations = [
        location for location in ordered_locations if location in seed_locations
    ]
    remaining_locations = [
        location for location in ordered_locations if location not in seed_locations
    ]
    candidates = [(location, None, False) for location in matched_locations]
    candidates.extend((None, seed, False) for seed in supplied_only)
    candidates.extend((location, None, False) for location in remaining_locations)
    candidates.extend((location, None, True) for location in error_locations)
    if len(candidates) > limits.max_nodes:
        exhausted = True
    candidates = candidates[:limits.max_nodes]

    nodes = []
    location_ids = {}
    error_node_ids = {}
    node_risks = {}
    for index, (location, seed, is_error) in enumerate(candidates, start=1):
        if expired():
            return deadline_result(nodes)
        node_id = f"NODE-{index:03d}"
        if is_error:
            safe_location = None if location == "." else location
            label = "unreadable repository directory"
            risk = ("functionality",)
            node = GraphNode(
                node_id, "file", label, safe_location, "builtin", "lexical",
                None, risk,
            )
            error_node_ids[location] = node_id
        elif location is None:
            label = _safe_graph_text(seed.term, sensitive_literals)
            risk = _risk_domains(seed.location, seed.term)
            node = GraphNode(node_id, "symbol", label, seed.location, "builtin", "lexical", None, risk)
        else:
            text, _, digest, _ = documents[location]
            risk = _risk_domains(location, text)
            label = next((
                _safe_graph_text(seed.term, sensitive_literals)
                for seed in normalized_seeds if seed.location == location
            ), location)
            confidence = "structural-inferred" if location in seed_locations else "lexical"
            node = GraphNode(node_id, _node_kind(location, text), label, location, "builtin", confidence, digest, risk)
            location_ids[location] = node_id
        nodes.append(node)
        node_risks[node_id] = risk

    edge_candidates = []
    for source, target, evidence, categories in relationships:
        if expired():
            return deadline_result(nodes)
        if source in location_ids and target in location_ids:
            kind, confidence = _edge_kind(target, categories, evidence)
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
            _safe_graph_text(evidence, sensitive_literals)[:GRAPH.MAX_STRING_LENGTH],
            confidence, "builtin", documents[target][2],
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

    frontier_items = []
    for location in error_locations:
        node_id = error_node_ids.get(location)
        if node_id is not None and len(frontier_items) < GRAPH.MAX_FRONTIER:
            display = "repository root" if location == "." else location
            frontier_items.append(FrontierEntry(
                f"FRONTIER-{len(frontier_items) + 1:03d}", node_id,
                f"unreadable directory: {display}", ("functionality",),
            ))
    omitted_errors = len(all_error_locations) - len(error_node_ids)
    if omitted_errors and nodes and len(frontier_items) < GRAPH.MAX_FRONTIER:
        frontier_items.append(FrontierEntry(
            f"FRONTIER-{len(frontier_items) + 1:03d}", nodes[0].id,
            f"{omitted_errors} unreadable directories omitted from node capacity",
            nodes[0].risk_domains,
        ))
    if exhausted and nodes and len(frontier_items) < GRAPH.MAX_FRONTIER:
        frontier_items.append(FrontierEntry(
            f"FRONTIER-{len(frontier_items) + 1:03d}", nodes[-1].id,
            "built-in scan budget exhausted", nodes[-1].risk_domains,
        ))
    frontier = tuple(frontier_items)
    status = (
        "provider_limited" if traversal_errors else
        "budget_exhausted" if exhausted else "closed"
    )
    return BuiltInScanResult(
        tuple(nodes), tuple(edges), tuple(paths), frontier,
        {location: documents[location][2] for location in sorted(documents)},
        {path: skipped[path] for path in sorted(skipped)},
        files_scanned, bytes_scanned,
        status,
    )
