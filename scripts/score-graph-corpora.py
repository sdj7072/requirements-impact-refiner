#!/usr/bin/env python3
"""Score pinned graph corpora against literal, manually curated relationships."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import statistics
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType, ModuleType
from typing import TypeVar

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "evals" / "corpora" / "catalog.json"
EXPECTED_PATH = ROOT / "evals" / "corpora" / "expected-relationships.json"
APPROVED_CORPORA = Path("/private/tmp/rir-v06-corpora")
MINIMUM_PRECISION = 0.90
MINIMUM_RECALL = 0.80
MAXIMUM_MEDIAN_MS = 10_000
MAXIMUM_HARD_MS = 30_000
MAXIMUM_COMPACT_BYTES = 24_000
RelationshipKey = tuple[str, str, str, str]
Pair = tuple[str, str]
T = TypeVar("T")


class CorpusScoreError(RuntimeError):
    """Corpus scoring failed a deterministic evaluation boundary."""


def _load_script(name: str, filename: str) -> ModuleType:
    path = Path(__file__).resolve().with_name(filename)
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise CorpusScoreError(f"cannot load scorer dependency {filename}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


FETCHER = _load_script("_rir_graph_corpus_fetcher", "fetch-graph-corpora.py")


@dataclass(frozen=True)
class EngineObservation:
    corpus: str
    provider: str
    predictions: tuple[Pair, ...]
    frontier_count: int
    duration_ms: int
    version: str
    executable_sha256: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.corpus, str) or not self.corpus:
            raise ValueError("observation corpus must be nonblank")
        if self.provider not in {"builtin", "ast-grep"}:
            raise ValueError("observation provider is invalid")
        normalized = tuple(sorted(set(self.predictions)))
        if any(
            not isinstance(pair, tuple)
            or len(pair) != 2
            or any(not isinstance(item, str) or not item for item in pair)
            for pair in normalized
        ):
            raise ValueError("observation predictions are invalid")
        if isinstance(self.frontier_count, bool) or not isinstance(self.frontier_count, int):
            raise ValueError("observation frontier count is invalid")
        if self.frontier_count < 0:
            raise ValueError("observation frontier count is invalid")
        if isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, int):
            raise ValueError("observation duration is invalid")
        if self.duration_ms < 0:
            raise ValueError("observation duration is invalid")
        if not isinstance(self.version, str) or not self.version:
            raise ValueError("observation version must be nonblank")
        if self.executable_sha256 is not None and (
            not isinstance(self.executable_sha256, str)
            or len(self.executable_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.executable_sha256)
        ):
            raise ValueError("observation executable digest is invalid")
        object.__setattr__(self, "predictions", normalized)


@dataclass(frozen=True)
class Seed:
    term: str
    location: str


@dataclass(frozen=True)
class RelationshipQuery:
    pattern: str
    source: str
    target: str


@dataclass(frozen=True)
class CorpusCase:
    id: str
    commit: str
    scope: tuple[str, ...]
    seeds: tuple[Seed, ...]
    evidence: tuple[tuple[str, str], ...] = ()
    queries: tuple[RelationshipQuery, ...] = ()


@dataclass(frozen=True)
class ExpectationSet:
    corpora: tuple[CorpusCase, ...]
    expected: Mapping[RelationshipKey, bool]
    negatives: frozenset[RelationshipKey]
    disclosed_high_risk_misses: frozenset[str]


_EXPECTED_ENVELOPE_KEYS = frozenset({"schema_version", "curation", "gates", "corpora"})
_CURATION_KEYS = frozenset({"method", "engine_output_used", "source_basis", "reviewed_commits"})
_GATES = {
    "minimum_precision": MINIMUM_PRECISION,
    "minimum_recall": MINIMUM_RECALL,
    "maximum_median_seconds": 10,
    "maximum_hard_seconds": 30,
    "maximum_compact_bytes": MAXIMUM_COMPACT_BYTES,
    "allow_undisclosed_high_risk_miss": False,
}
_CORPUS_EXPECTATION_KEYS = frozenset(
    {
        "id",
        "commit",
        "scope",
        "seeds",
        "relationships",
        "negative_relationships",
        "disclosed_high_risk_misses",
    }
)
_RELATIONSHIP_KEYS = frozenset(
    {
        "source",
        "target",
        "term",
        "providers",
        "high_risk",
        "risk_domains",
        "evidence",
    }
)
_NEGATIVE_KEYS = frozenset({"source", "target", "providers", "rationale"})


def _safe_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise CorpusScoreError(f"{label} must be a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CorpusScoreError(f"{label} must be a safe relative path")
    return path.as_posix()


def _providers(value: object, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(item not in {"builtin", "ast-grep"} for item in value)
        or len(value) != len(set(value))
    ):
        raise CorpusScoreError(f"{label} providers are invalid")
    return tuple(value)


def _strings(value: object, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise CorpusScoreError(f"{label} must contain unique nonblank strings")
    return tuple(value)


def load_expectations(path: Path, specifications: Sequence[object]) -> ExpectationSet:
    """Load the strict hand-curated relationship and negative-control catalog."""
    try:
        raw = FETCHER._read_regular(Path(path), 256 * 1024, "relationship expectations")
        payload = json.loads(raw.decode("utf-8"))
    except CorpusScoreError:
        raise
    except Exception as error:
        raise CorpusScoreError("relationship expectations are malformed") from error
    if (
        not isinstance(payload, dict)
        or set(payload) != _EXPECTED_ENVELOPE_KEYS
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("corpora"), list)
    ):
        raise CorpusScoreError("relationship expectation envelope is invalid")
    curation = payload["curation"]
    if (
        not isinstance(curation, dict)
        or set(curation) != _CURATION_KEYS
        or curation.get("method") != "manual-pinned-source-review"
        or curation.get("engine_output_used") is not False
        or not isinstance(curation.get("source_basis"), str)
        or not curation["source_basis"]
    ):
        raise CorpusScoreError("relationships must be independently curated from pinned source")
    if payload["gates"] != _GATES:
        raise CorpusScoreError("relationship score gates do not match the literal release limits")
    by_id = {getattr(specification, "id", None): specification for specification in specifications}
    expected_order = tuple(by_id)
    reviewed_commits = curation.get("reviewed_commits")
    if reviewed_commits != [getattr(by_id[item], "commit", None) for item in expected_order]:
        raise CorpusScoreError("curation commits do not match the corpus catalog")

    corpora = []
    expected: dict[RelationshipKey, bool] = {}
    negatives: set[RelationshipKey] = set()
    disclosed: set[str] = set()
    seen_ids = []
    for raw_corpus in payload["corpora"]:
        if not isinstance(raw_corpus, dict) or set(raw_corpus) != _CORPUS_EXPECTATION_KEYS:
            raise CorpusScoreError("corpus expectation row has unknown or missing fields")
        if any(
            not isinstance(raw_corpus[field], list)
            for field in (
                "scope",
                "seeds",
                "relationships",
                "negative_relationships",
                "disclosed_high_risk_misses",
            )
        ):
            raise CorpusScoreError("corpus expectation list fields are invalid")
        corpus_id = raw_corpus["id"]
        if corpus_id not in by_id or corpus_id in seen_ids:
            raise CorpusScoreError("corpus expectation identity is invalid")
        seen_ids.append(corpus_id)
        commit = raw_corpus["commit"]
        if commit != getattr(by_id[corpus_id], "commit", None):
            raise CorpusScoreError("corpus expectation commit does not match the catalog")
        scope = tuple(_safe_path(item, f"{corpus_id} scope") for item in raw_corpus["scope"])
        if not scope or len(scope) != len(set(scope)):
            raise CorpusScoreError("corpus expectation scope must be unique and nonempty")
        scope_set = set(scope)
        seeds = []
        for raw_seed in raw_corpus["seeds"]:
            if (
                not isinstance(raw_seed, dict)
                or set(raw_seed) != {"term", "location"}
                or not isinstance(raw_seed["term"], str)
                or not raw_seed["term"]
            ):
                raise CorpusScoreError("corpus expectation seed is invalid")
            location = _safe_path(raw_seed["location"], f"{corpus_id} seed")
            if location not in scope_set:
                raise CorpusScoreError("corpus expectation seed lies outside the scope")
            seeds.append(Seed(raw_seed["term"], location))
        if not seeds or len(seeds) != len(set(seeds)):
            raise CorpusScoreError("corpus expectation seeds must be unique and nonempty")
        seed_pairs = {(seed.location, seed.term) for seed in seeds}
        evidence = []
        queries = []
        for raw_relationship in raw_corpus["relationships"]:
            if (
                not isinstance(raw_relationship, dict)
                or set(raw_relationship) != _RELATIONSHIP_KEYS
            ):
                raise CorpusScoreError("expected relationship has unknown or missing fields")
            source = _safe_path(raw_relationship["source"], "relationship source")
            target = _safe_path(raw_relationship["target"], "relationship target")
            term = raw_relationship["term"]
            if (
                source == target
                or source not in scope_set
                or target not in scope_set
                or not isinstance(term, str)
                or not term
                or (source, term) not in seed_pairs
                or not isinstance(raw_relationship["high_risk"], bool)
                or not isinstance(raw_relationship["evidence"], str)
                or not raw_relationship["evidence"]
            ):
                raise CorpusScoreError("expected relationship is invalid")
            _strings(raw_relationship["risk_domains"], "relationship risk domains")
            evidence.append((source, raw_relationship["evidence"]))
            if len(raw_relationship["evidence"].encode("utf-8")) > 256:
                raise CorpusScoreError("expected relationship evidence exceeds query bounds")
            queries.append(RelationshipQuery(raw_relationship["evidence"], source, target))
            for provider in _providers(raw_relationship["providers"], "relationship"):
                key = (corpus_id, provider, source, target)
                if key in expected:
                    raise CorpusScoreError("expected relationship is duplicated")
                expected[key] = raw_relationship["high_risk"]
        for raw_negative in raw_corpus["negative_relationships"]:
            if not isinstance(raw_negative, dict) or set(raw_negative) != _NEGATIVE_KEYS:
                raise CorpusScoreError("negative relationship has unknown or missing fields")
            source = _safe_path(raw_negative["source"], "negative source")
            target = _safe_path(raw_negative["target"], "negative target")
            if (
                source == target
                or source not in scope_set
                or target not in scope_set
                or not isinstance(raw_negative["rationale"], str)
                or not raw_negative["rationale"]
            ):
                raise CorpusScoreError("negative relationship is invalid")
            for provider in _providers(raw_negative["providers"], "negative relationship"):
                key = (corpus_id, provider, source, target)
                if key in negatives:
                    raise CorpusScoreError("negative relationship is duplicated")
                negatives.add(key)
        disclosed_rows = _strings(
            raw_corpus["disclosed_high_risk_misses"],
            "disclosed high-risk misses",
            allow_empty=True,
        )
        disclosed.update(disclosed_rows)
        corpora.append(
            CorpusCase(
                corpus_id,
                commit,
                scope,
                tuple(seeds),
                tuple(evidence),
                tuple(queries),
            )
        )
    if tuple(seen_ids) != expected_order:
        raise CorpusScoreError("relationship corpora must match the catalog order exactly")
    if set(expected) & negatives:
        raise CorpusScoreError("positive and negative relationships overlap")
    high_risk_text = {_relationship_text(key) for key, high_risk in expected.items() if high_risk}
    if not disclosed <= high_risk_text:
        raise CorpusScoreError("disclosed high-risk miss is not an expected high-risk relationship")
    return ExpectationSet(
        tuple(corpora),
        MappingProxyType(expected),
        frozenset(negatives),
        frozenset(disclosed),
    )


def _duration_summary(durations: Sequence[int]) -> tuple[int | float, int]:
    if not durations:
        return 0, 0
    median = statistics.median(durations)
    if isinstance(median, float) and median.is_integer():
        median = int(median)
    return median, max(durations)


def evaluate_gates(
    precision: float,
    recall: float,
    undisclosed_high_risk_misses: Sequence[str],
    durations_ms: Sequence[int],
    compact_bytes: int,
) -> dict[str, bool]:
    """Evaluate the six literal release boundaries."""
    median_duration, hard_duration = _duration_summary(durations_ms)
    gates = {
        "precision": precision >= MINIMUM_PRECISION,
        "recall": recall >= MINIMUM_RECALL,
        "high_risk": not undisclosed_high_risk_misses,
        "median_duration": median_duration <= MAXIMUM_MEDIAN_MS,
        "hard_duration": hard_duration <= MAXIMUM_HARD_MS,
        "compact_bytes": compact_bytes <= MAXIMUM_COMPACT_BYTES,
    }
    gates["passed"] = all(gates.values())
    return gates


def _relationship_text(key: RelationshipKey) -> str:
    corpus, provider, source, target = key
    return f"{corpus}:{provider}:{source}->{target}"


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 6)


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _finalize_report(
    report: dict[str, object],
    *,
    precision: float,
    recall: float,
    high_risk_misses: Sequence[str],
    durations: Sequence[int],
) -> tuple[dict[str, object], bytes]:
    aggregate = report["aggregate"]
    if not isinstance(aggregate, dict):
        raise CorpusScoreError("internal aggregate report shape is invalid")
    previous = -1
    for _ in range(12):
        payload = _canonical_bytes(report)
        size = len(payload)
        aggregate["compact_bytes"] = size
        gates = evaluate_gates(precision, recall, high_risk_misses, durations, size)
        report["gates"] = gates
        report["passed"] = gates["passed"]
        updated = _canonical_bytes(report)
        if len(updated) == size and size == previous:
            return report, updated
        previous = size
    raise CorpusScoreError("compact report size did not converge")


def score_observations(
    expected: Mapping[RelationshipKey, bool],
    negatives: set[RelationshipKey],
    disclosed_high_risk_misses: set[str],
    observations: Sequence[EngineObservation],
    *,
    provenance: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], bytes]:
    """Compare bounded provider observations with literal positive and negative pairs."""
    expected_rows = dict(expected)
    if not expected_rows:
        raise CorpusScoreError("at least one expected relationship is required")
    if set(expected_rows) & set(negatives):
        raise CorpusScoreError("positive and negative relationship sets overlap")
    run_keys = {(key[0], key[1]) for key in expected_rows}
    observations_by_run = {(row.corpus, row.provider): row for row in observations}
    if len(observations_by_run) != len(observations) or set(observations_by_run) != run_keys:
        raise CorpusScoreError("observations must cover each expected corpus/provider exactly once")

    total_true_positive = 0
    total_false_positive = 0
    total_false_negative = 0
    total_frontier = 0
    durations = []
    missing_keys: set[RelationshipKey] = set()
    runs = []
    for run_key in sorted(run_keys):
        corpus, provider = run_key
        observation = observations_by_run[run_key]
        run_expected = {
            (source, target)
            for row_corpus, row_provider, source, target in expected_rows
            if (row_corpus, row_provider) == run_key
        }
        run_negatives = {
            (source, target)
            for row_corpus, row_provider, source, target in negatives
            if (row_corpus, row_provider) == run_key
        }
        predictions = set(observation.predictions)
        true_positive = predictions & run_expected
        false_positive = predictions & run_negatives
        false_negative = run_expected - true_positive
        unknown = predictions - run_expected - run_negatives
        total_true_positive += len(true_positive)
        total_false_positive += len(false_positive)
        total_false_negative += len(false_negative)
        total_frontier += observation.frontier_count + len(unknown)
        durations.append(observation.duration_ms)
        missing_keys.update((corpus, provider, source, target) for source, target in false_negative)
        runs.append(
            {
                "corpus": corpus,
                "provider": provider,
                "true_positive": len(true_positive),
                "false_positive": len(false_positive),
                "false_negative": len(false_negative),
                "precision": _ratio(
                    len(true_positive),
                    len(true_positive) + len(false_positive),
                ),
                "recall": _ratio(
                    len(true_positive),
                    len(true_positive) + len(false_negative),
                ),
                "unknown_frontier": observation.frontier_count + len(unknown),
                "duration_ms": observation.duration_ms,
                "version": observation.version,
                "executable_sha256": observation.executable_sha256,
            }
        )

    precision = _ratio(total_true_positive, total_true_positive + total_false_positive)
    recall = _ratio(total_true_positive, total_true_positive + total_false_negative)
    missing_text = tuple(sorted(_relationship_text(key) for key in missing_keys))
    high_risk_misses = tuple(
        sorted(
            _relationship_text(key)
            for key in missing_keys
            if expected_rows[key] and _relationship_text(key) not in disclosed_high_risk_misses
        )
    )
    median_duration, hard_duration = _duration_summary(durations)
    report: dict[str, object] = {
        "schema_version": 1,
        "provenance": dict(provenance or {}),
        "limits": {
            "minimum_precision": MINIMUM_PRECISION,
            "minimum_recall": MINIMUM_RECALL,
            "maximum_median_ms": MAXIMUM_MEDIAN_MS,
            "maximum_hard_ms": MAXIMUM_HARD_MS,
            "maximum_compact_bytes": MAXIMUM_COMPACT_BYTES,
            "allow_undisclosed_high_risk_miss": False,
        },
        "aggregate": {
            "true_positive": total_true_positive,
            "false_positive": total_false_positive,
            "false_negative": total_false_negative,
            "precision": precision,
            "recall": recall,
            "unknown_frontier": total_frontier,
            "median_duration_ms": median_duration,
            "hard_duration_ms": hard_duration,
            "compact_bytes": 0,
        },
        "runs": runs,
        "misses": missing_text[:32],
        "undisclosed_high_risk_misses": high_risk_misses[:32],
        "gates": {},
        "passed": False,
    }
    return _finalize_report(
        report,
        precision=precision,
        recall=recall,
        high_risk_misses=high_risk_misses,
        durations=durations,
    )


def guard_verified_corpora(
    catalog_path: Path,
    destination: Path,
    operation: Callable[[], T],
    *,
    repository_root: Path = ROOT,
    approved_destination: Path = APPROVED_CORPORA,
    allow_local_repositories: bool = False,
) -> T:
    """Run an evaluator only while every checkout remains exactly verified."""
    verification_arguments = {
        "repository_root": repository_root,
        "approved_destination": approved_destination,
        "allow_local_repositories": allow_local_repositories,
    }
    before = FETCHER.verify_corpora(catalog_path, destination, **verification_arguments)
    operation_error = None
    try:
        result = operation()
    except Exception as error:
        operation_error = error
        result = None
    try:
        after = FETCHER.verify_corpora(catalog_path, destination, **verification_arguments)
    except Exception as error:
        raise CorpusScoreError("graph scorer changed corpus checkout state") from (
            operation_error or error
        )
    if after != before:
        raise CorpusScoreError("graph scorer changed corpus checkout identity") from operation_error
    if operation_error is not None:
        raise operation_error
    return result  # type: ignore[return-value]


def _field(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def project_builtin_result(
    corpus: str,
    result: object,
    duration_ms: int,
) -> EngineObservation:
    """Project structural built-in edges while retaining lexical uncertainty."""
    node_locations = {
        _field(node, "id"): _field(node, "location")
        for node in tuple(getattr(result, "nodes", ()))
        if isinstance(_field(node, "id"), str) and isinstance(_field(node, "location"), str)
    }
    predictions = set()
    uncertain_frontier = 0
    invalid_frontier = 0
    for edge in tuple(getattr(result, "edges", ())):
        source = node_locations.get(_field(edge, "source"))
        target = node_locations.get(_field(edge, "target"))
        if not isinstance(source, str) or not isinstance(target, str) or source == target:
            invalid_frontier += 1
            continue
        pair = (source, target)
        if (
            _field(edge, "confidence") == "structural-inferred"
            and _field(edge, "kind") == "imports"
        ):
            predictions.add(pair)
        else:
            uncertain_frontier += 1
    frontier_count = (
        len(tuple(getattr(result, "frontier", ()))) + uncertain_frontier + invalid_frontier
    )
    if getattr(result, "budget_status", "closed") != "closed" and frontier_count == 0:
        frontier_count = 1
    return EngineObservation(
        corpus,
        "builtin",
        tuple(sorted(predictions)),
        frontier_count,
        duration_ms,
        "builtin-v1",
        None,
    )


def project_ast_grep_result(
    corpus: str,
    result: object,
    duration_ms: int,
    version: str,
    executable_sha256: str,
) -> EngineObservation:
    """Project ast-grep reference edges and expose self/invalid matches as frontier."""
    if getattr(result, "status", None) != "ready":
        return EngineObservation(
            corpus,
            "ast-grep",
            (),
            max(1, len(tuple(getattr(result, "frontier", ())))),
            duration_ms,
            version,
            executable_sha256,
        )
    node_locations = {
        _field(node, "key"): _field(node, "location")
        for node in tuple(getattr(result, "nodes", ()))
        if isinstance(_field(node, "key"), str) and isinstance(_field(node, "location"), str)
    }
    predictions = set()
    frontier_pairs = set()
    for edge in tuple(getattr(result, "edges", ())):
        source = node_locations.get(_field(edge, "source"))
        target = node_locations.get(_field(edge, "target"))
        if not isinstance(source, str) or not isinstance(target, str) or source == target:
            frontier_pairs.add((str(source), str(target)))
            continue
        predictions.add((source, target))
    return EngineObservation(
        corpus,
        "ast-grep",
        tuple(sorted(predictions)),
        len(tuple(getattr(result, "frontier", ()))) + len(frontier_pairs),
        duration_ms,
        version,
        executable_sha256,
    )


_RUNTIME: tuple[ModuleType, ModuleType] | None = None


def _runtime() -> tuple[ModuleType, ModuleType]:
    global _RUNTIME
    if _RUNTIME is None:
        builtin = _load_script("_rir_graph_corpus_builtin", "graph_builtin.py")
        canary = _load_script("_rir_graph_corpus_ast_grep_canary", "run-ast-grep-canary.py")
        _RUNTIME = builtin, canary
    return _RUNTIME


def run_builtin(corpus: CorpusCase, checkout: Path) -> EngineObservation:
    """Run the production built-in graph path with its 30-second ceiling."""
    builtin, _ = _runtime()
    seeds = tuple(builtin.ScanSeed(seed.term, seed.location) for seed in corpus.seeds)
    started = time.monotonic()
    result = builtin.scan_repository(
        checkout,
        seeds,
        builtin.ScanLimits(max_seconds=30),
        time,
    )
    duration_ms = max(0, round((time.monotonic() - started) * 1000))
    return project_builtin_result(corpus.id, result, duration_ms)


def _write_private_view_file(path: Path, payload: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        str(path),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o400,
    )
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise CorpusScoreError("temporary ast-grep view write made no progress")
            offset += written
        os.fchmod(descriptor, 0o400)
    finally:
        os.close(descriptor)


def run_ast_grep(
    corpus: CorpusCase,
    checkout: Path,
    executable: Path,
) -> EngineObservation:
    """Run the production detect-only ast-grep path at exactly version 0.45.0."""
    _, canary = _runtime()
    adapter = canary.ADAPTER
    providers = adapter.PROVIDERS
    selected = Path(executable)
    if not selected.is_absolute():
        selected = selected.resolve(strict=True)
    started = time.monotonic()
    try:
        version_observation = canary.run_bounded(selected, ("--version",), checkout)
    except Exception as error:
        raise CorpusScoreError("ast-grep executable verification failed") from error
    version = version_observation.stdout.strip()
    if version != "ast-grep 0.45.0":
        raise CorpusScoreError("ast-grep 0.45.0 is required for corpus scoring")
    executable_sha256 = version_observation.executable_sha256
    if not isinstance(executable_sha256, str):
        raise CorpusScoreError("ast-grep executable digest is unavailable")
    remaining = max(0.0, 30.0 - (time.monotonic() - started))
    deadline = providers.Deadline(time, remaining)
    if not corpus.queries:
        raise CorpusScoreError("ast-grep corpus relationships have no curated queries")
    predictions = set()
    frontier_count = 0
    for query in corpus.queries:
        source_path = checkout.joinpath(*PurePosixPath(query.source).parts)
        source_bytes = FETCHER._read_regular(
            source_path,
            1024 * 1024,
            "ast-grep curated query source",
        )
        try:
            source_text = source_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise CorpusScoreError("ast-grep curated query source is not UTF-8") from error
        if query.pattern not in source_text:
            raise CorpusScoreError("ast-grep curated query pattern is absent from pinned source")
        with tempfile.TemporaryDirectory(prefix="rir-graph-corpus-") as temporary:
            view = Path(temporary).resolve()
            _write_private_view_file(
                view.joinpath(*PurePosixPath(query.source).parts),
                source_bytes,
            )
            fingerprint = adapter.source_fingerprint(view)
            if not isinstance(fingerprint, str):
                raise CorpusScoreError("ast-grep query view fingerprint is unavailable")
            probe = adapter.ProviderProbe(
                "ast-grep",
                "ready",
                "structural-inferred",
                selected,
                version,
                executable_sha256,
                ("json-stream", "language", "pattern"),
                repo_root=view,
                metadata={"source_fingerprint": fingerprint},
            )
            result = adapter.query(
                probe,
                (SimpleSeed(query.pattern, query.source),),
                deadline,
                None,
            )
        if result.status != "ready" or not result.edges:
            frontier_count += max(1, len(result.frontier))
            continue
        node_locations = {_field(node, "key"): _field(node, "location") for node in result.nodes}
        match_locations = {node_locations.get(_field(edge, "target")) for edge in result.edges}
        if match_locations != {query.source}:
            frontier_count += 1
            continue
        predictions.add((query.source, query.target))
        frontier_count += len(result.frontier)
    duration_ms = max(0, round((time.monotonic() - started) * 1000))
    return EngineObservation(
        corpus.id,
        "ast-grep",
        tuple(sorted(predictions)),
        frontier_count,
        duration_ms,
        version,
        executable_sha256,
    )


@dataclass(frozen=True)
class SimpleSeed:
    term: str
    location: str


def _file_sha256(path: Path) -> str:
    payload = FETCHER._read_regular(Path(path), 256 * 1024, "score provenance file")
    return hashlib.sha256(payload).hexdigest()


def _bind_curated_evidence(corpus: CorpusCase, checkout: Path) -> None:
    for source, evidence in corpus.evidence:
        path = checkout.joinpath(*PurePosixPath(source).parts)
        try:
            text = FETCHER._read_regular(path, 1024 * 1024, "curated evidence source").decode(
                "utf-8"
            )
        except Exception as error:
            raise CorpusScoreError(f"{corpus.id} curated evidence source is unreadable") from error
        if evidence not in text:
            raise CorpusScoreError(
                f"{corpus.id} curated evidence is absent from pinned source: {source}"
            )


def run_evaluation(
    catalog_path: Path,
    expected_path: Path,
    destination: Path,
    ast_grep_executable: Path,
    *,
    repository_root: Path = ROOT,
    approved_destination: Path = APPROVED_CORPORA,
    allow_local_repositories: bool = False,
    builtin_runner: Callable[[CorpusCase, Path], EngineObservation] = run_builtin,
    ast_grep_runner: Callable[[CorpusCase, Path, Path], EngineObservation] = run_ast_grep,
) -> tuple[dict[str, object], bytes]:
    """Verify, run, score, and reverify every pinned checkout."""
    specifications = FETCHER.load_catalog(
        catalog_path,
        allow_local_repositories=allow_local_repositories,
    )
    expectations = load_expectations(expected_path, specifications)
    by_id = {specification.id: specification for specification in specifications}

    def evaluate() -> tuple[dict[str, object], bytes]:
        observations = []
        for corpus in expectations.corpora:
            specification = by_id[corpus.id]
            checkout = Path(destination).resolve(strict=True) / specification.checkout
            _bind_curated_evidence(corpus, checkout)
            providers = {
                provider
                for row_corpus, provider, _source, _target in expectations.expected
                if row_corpus == corpus.id
            }
            if "builtin" in providers:
                observations.append(builtin_runner(corpus, checkout))
            if "ast-grep" in providers:
                observations.append(ast_grep_runner(corpus, checkout, ast_grep_executable))
        provenance = {
            "catalog_sha256": _file_sha256(catalog_path),
            "expectations_sha256": _file_sha256(expected_path),
            "destination": str(Path(destination).resolve(strict=True)),
            "commits": [corpus.commit for corpus in expectations.corpora],
        }
        return score_observations(
            expectations.expected,
            set(expectations.negatives),
            set(expectations.disclosed_high_risk_misses),
            tuple(observations),
            provenance=provenance,
        )

    return guard_verified_corpora(
        catalog_path,
        destination,
        evaluate,
        repository_root=repository_root,
        approved_destination=approved_destination,
        allow_local_repositories=allow_local_repositories,
    )


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpora", required=True, type=Path)
    parser.add_argument(
        "--ast-grep",
        type=Path,
        default=ROOT / ".quality-venv" / "bin" / "ast-grep",
    )
    args = parser.parse_args(arguments)
    try:
        guard = FETCHER._load_working_state_guard()
        report, report_bytes = guard.guard_working_state(
            ROOT,
            lambda: run_evaluation(
                CATALOG_PATH,
                EXPECTED_PATH,
                args.corpora,
                args.ast_grep,
            ),
        )
    except (CorpusScoreError, FETCHER.CorpusError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(report_bytes + b"\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
