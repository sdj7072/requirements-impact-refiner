#!/usr/bin/env python3
"""Score genuine scoped import discovery on exact pinned public corpora."""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import hashlib
import importlib.util
import json
import os
import posixpath
import re
import stat
import statistics
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from types import MappingProxyType, ModuleType
from typing import TypeVar

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "evals" / "corpora" / "catalog.json"
EXPECTED_PATH = ROOT / "evals" / "corpora" / "expected-relationships.json"
MINIMUM_PRECISION = 0.90
MINIMUM_RECALL = 0.80
MAXIMUM_MEDIAN_MS = 10_000
MAXIMUM_HARD_MS = 30_000
MAXIMUM_COMPACT_BYTES = 24_000
MAX_SOURCE_BYTES = 1024 * 1024
PROVIDERS = ("builtin", "ast-grep")
RelationshipKey = tuple[str, str, str]
ModuleKey = tuple[str, str]
Pair = tuple[str, str]
T = TypeVar("T")


class CorpusScoreError(RuntimeError):
    """Corpus scoring failed a deterministic evidence boundary."""


def _load_script(name: str, filename: str) -> ModuleType:
    path = Path(__file__).resolve().with_name(filename)
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise CorpusScoreError(f"cannot load scorer dependency {filename}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


FETCHER = _load_script("_rir_graph_corpus_fetcher_v2", "fetch-graph-corpora.py")


@dataclass(frozen=True)
class ImportLabel:
    module: str
    target: str
    high_risk: bool
    risk_domains: tuple[str, ...]


@dataclass(frozen=True)
class SourceScope:
    path: str
    language: str
    sha256: str
    internal_imports: tuple[ImportLabel, ...]
    external_imports: tuple[str, ...]

    @property
    def labelled_modules(self) -> frozenset[str]:
        return frozenset((*self.external_imports, *(item.module for item in self.internal_imports)))


@dataclass(frozen=True)
class CorpusCase:
    id: str
    commit: str
    sources: tuple[SourceScope, ...]
    candidate_rule: object
    candidate_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExpectationSet:
    corpora: tuple[CorpusCase, ...]
    expected: Mapping[RelationshipKey, bool]
    labelled_modules: Mapping[ModuleKey, frozenset[str]]
    disclosed_high_risk_misses: Mapping[str, frozenset[str]]


@dataclass(frozen=True)
class EngineObservation:
    corpus: str
    provider: str
    predictions: tuple[Pair, ...]
    frontier_count: int
    duration_ms: int
    version: str
    executable_sha256: str | None
    discovered_modules: tuple[ModuleKey, ...] = ()
    scope_inventory_complete: bool = False
    detail: str | None = None
    scope_manifest: tuple[ModuleKey, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.corpus, str) or not self.corpus:
            raise ValueError("observation corpus must be nonblank")
        if self.provider not in PROVIDERS:
            raise ValueError("observation provider is invalid")
        if not isinstance(self.predictions, (tuple, list)) or any(
            not isinstance(pair, (tuple, list))
            or len(pair) != 2
            or any(not isinstance(item, str) or not item for item in pair)
            for pair in self.predictions
        ):
            raise ValueError("observation predictions are invalid")
        if not isinstance(self.discovered_modules, (tuple, list)) or any(
            not isinstance(pair, (tuple, list))
            or len(pair) != 2
            or any(not isinstance(item, str) or not item for item in pair)
            for pair in self.discovered_modules
        ):
            raise ValueError("observation module inventory is invalid")
        for value, label in (
            (self.frontier_count, "frontier count"),
            (self.duration_ms, "duration"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"observation {label} is invalid")
        if not isinstance(self.version, str) or not self.version:
            raise ValueError("observation version must be nonblank")
        if self.executable_sha256 is not None and (
            not isinstance(self.executable_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.executable_sha256) is None
        ):
            raise ValueError("observation executable digest is invalid")
        if not isinstance(self.scope_inventory_complete, bool):
            raise ValueError("observation scope inventory status is invalid")
        if self.detail is not None and not isinstance(self.detail, str):
            raise ValueError("observation detail is invalid")
        if not isinstance(self.scope_manifest, (tuple, list)) or any(
            not isinstance(pair, (tuple, list))
            or len(pair) != 2
            or not isinstance(pair[0], str)
            or not pair[0]
            or not isinstance(pair[1], str)
            or re.fullmatch(r"[0-9a-f]{64}", pair[1]) is None
            for pair in self.scope_manifest
        ):
            raise ValueError("observation scope manifest is invalid")
        object.__setattr__(self, "predictions", tuple(sorted(set(map(tuple, self.predictions)))))
        object.__setattr__(
            self,
            "discovered_modules",
            tuple(sorted(set(map(tuple, self.discovered_modules)))),
        )
        object.__setattr__(
            self,
            "scope_manifest",
            tuple(sorted(set(map(tuple, self.scope_manifest)))),
        )


_ENVELOPE_KEYS = frozenset({"schema_version", "curation", "gates", "corpora"})
_CURATION_KEYS = frozenset(
    {
        "method",
        "engine_output_used",
        "scope_policy",
        "reviewed_commits",
        "reviewed_license_sha256",
    }
)
_GATES = {
    "minimum_precision": MINIMUM_PRECISION,
    "minimum_recall": MINIMUM_RECALL,
    "maximum_median_seconds": 10,
    "maximum_hard_seconds": 30,
    "maximum_compact_bytes": MAXIMUM_COMPACT_BYTES,
    "allow_undisclosed_high_risk_miss": False,
    "require_zero_provider_disagreement": True,
}
_CORPUS_KEYS = frozenset({"id", "commit", "sources", "disclosed_high_risk_misses"})
_SOURCE_KEYS = frozenset({"path", "language", "sha256", "internal_imports", "external_imports"})
_IMPORT_KEYS = frozenset({"module", "target", "high_risk", "risk_domains"})


def _safe_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise CorpusScoreError(f"{label} must be a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CorpusScoreError(f"{label} must be a safe relative path")
    return path.as_posix()


def _unique_strings(value: object, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or any(not isinstance(item, str) or not item or "\x00" in item for item in value)
        or len(value) != len(set(value))
    ):
        raise CorpusScoreError(f"{label} must contain unique nonblank strings")
    return tuple(value)


def _relationship_text(key: RelationshipKey) -> str:
    corpus, source, target = key
    return f"{corpus}:{source}->{target}"


def load_expectations(path: Path, specifications: Sequence[object]) -> ExpectationSet:
    """Load complete manual import labels for the explicit source scope."""
    try:
        raw = FETCHER._read_regular(Path(path), 256 * 1024, "relationship expectations")
        payload = json.loads(raw.decode("utf-8"))
    except Exception as error:
        raise CorpusScoreError("relationship expectations are malformed") from error
    if (
        not isinstance(payload, dict)
        or set(payload) != _ENVELOPE_KEYS
        or payload.get("schema_version") != 2
        or not isinstance(payload.get("corpora"), list)
    ):
        raise CorpusScoreError("relationship expectation envelope is invalid")
    curation = payload["curation"]
    if (
        not isinstance(curation, dict)
        or set(curation) != _CURATION_KEYS
        or curation.get("method") != "manual-pinned-source-review"
        or curation.get("engine_output_used") is not False
        or not isinstance(curation.get("scope_policy"), str)
        or not curation["scope_policy"]
    ):
        raise CorpusScoreError("relationships must be independently curated from pinned source")
    if payload["gates"] != _GATES:
        raise CorpusScoreError("relationship score gates do not match literal release limits")
    by_id = {getattr(specification, "id", None): specification for specification in specifications}
    expected_order = tuple(by_id)
    if curation.get("reviewed_commits") != [
        getattr(by_id[item], "commit", None) for item in expected_order
    ]:
        raise CorpusScoreError("curation commits do not match the corpus catalog")
    if curation.get("reviewed_license_sha256") != [
        getattr(by_id[item], "license_sha256", None) for item in expected_order
    ]:
        raise CorpusScoreError("curation licenses do not match the corpus catalog")

    corpora = []
    expected: dict[RelationshipKey, bool] = {}
    labelled_modules: dict[ModuleKey, frozenset[str]] = {}
    disclosures: dict[str, set[str]] = {provider: set() for provider in PROVIDERS}
    seen_ids = []
    for raw_corpus in payload["corpora"]:
        if not isinstance(raw_corpus, dict) or set(raw_corpus) != _CORPUS_KEYS:
            raise CorpusScoreError("corpus expectation row has unknown or missing fields")
        if not isinstance(raw_corpus["sources"], list):
            raise CorpusScoreError("corpus expectation list fields are invalid")
        corpus_id = raw_corpus["id"]
        if corpus_id not in by_id or corpus_id in seen_ids:
            raise CorpusScoreError("corpus expectation identity is invalid")
        seen_ids.append(corpus_id)
        commit = raw_corpus["commit"]
        if commit != getattr(by_id[corpus_id], "commit", None):
            raise CorpusScoreError("corpus expectation commit does not match catalog")
        sources = []
        seen_paths = set()
        for raw_source in raw_corpus["sources"]:
            if not isinstance(raw_source, dict) or set(raw_source) != _SOURCE_KEYS:
                raise CorpusScoreError("source scope has unknown or missing fields")
            if not isinstance(raw_source["internal_imports"], list):
                raise CorpusScoreError("source import labels must be lists")
            path_text = _safe_path(raw_source["path"], "source scope")
            if path_text in seen_paths:
                raise CorpusScoreError("source scope paths must be unique")
            seen_paths.add(path_text)
            language = raw_source["language"]
            digest = raw_source["sha256"]
            if language not in {"python", "javascript"}:
                raise CorpusScoreError("source scope language is unsupported")
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise CorpusScoreError("source scope digest is invalid")
            imports = []
            module_names = set()
            for raw_import in raw_source["internal_imports"]:
                if not isinstance(raw_import, dict) or set(raw_import) != _IMPORT_KEYS:
                    raise CorpusScoreError("internal import label is invalid")
                module = raw_import["module"]
                target = _safe_path(raw_import["target"], "internal import target")
                if (
                    not isinstance(module, str)
                    or not module
                    or module in module_names
                    or not isinstance(raw_import["high_risk"], bool)
                ):
                    raise CorpusScoreError("internal import module label is invalid")
                module_names.add(module)
                risks = _unique_strings(raw_import["risk_domains"], "import risk domains")
                label = ImportLabel(module, target, raw_import["high_risk"], risks)
                imports.append(label)
                key = (corpus_id, path_text, target)
                if key in expected:
                    raise CorpusScoreError("internal relationship is duplicated")
                expected[key] = label.high_risk
            external = _unique_strings(
                raw_source["external_imports"], "external imports", allow_empty=True
            )
            if module_names & set(external):
                raise CorpusScoreError("internal and external module labels overlap")
            scope = SourceScope(path_text, language, digest, tuple(imports), external)
            labelled_modules[(corpus_id, path_text)] = scope.labelled_modules
            sources.append(scope)
        if not sources:
            raise CorpusScoreError("corpus source scope must not be empty")
        raw_disclosures = raw_corpus["disclosed_high_risk_misses"]
        if not isinstance(raw_disclosures, dict) or set(raw_disclosures) != set(PROVIDERS):
            raise CorpusScoreError("high-risk disclosures must be provider-specific")
        for provider in PROVIDERS:
            disclosures[provider].update(
                _unique_strings(
                    raw_disclosures[provider],
                    f"{provider} high-risk disclosures",
                    allow_empty=True,
                )
            )
        candidate_rule = getattr(by_id[corpus_id], "candidate_rule", None)
        if not isinstance(candidate_rule, FETCHER.CandidateRule):
            raise CorpusScoreError("corpus candidate rule is unavailable")
        corpora.append(CorpusCase(corpus_id, commit, tuple(sources), candidate_rule))
    if tuple(seen_ids) != expected_order or not expected:
        raise CorpusScoreError("relationship corpora must match catalog order exactly")
    high_risk = {_relationship_text(key) for key, value in expected.items() if value}
    if any(not rows <= high_risk for rows in disclosures.values()):
        raise CorpusScoreError("high-risk disclosure is not an expected high-risk relationship")
    return ExpectationSet(
        tuple(corpora),
        MappingProxyType(expected),
        MappingProxyType(labelled_modules),
        MappingProxyType({provider: frozenset(rows) for provider, rows in disclosures.items()}),
    )


def derive_candidate_paths(
    rule: object,
    head_paths: frozenset[str],
) -> tuple[str, ...]:
    """Apply one catalog rule to exact HEAD paths without expected-edge input."""
    if not isinstance(rule, FETCHER.CandidateRule):
        raise CorpusScoreError("corpus candidate rule is unavailable")
    candidates = []
    for value in sorted(head_paths):
        path = PurePosixPath(_safe_path(value, "HEAD candidate path"))
        parent = path.parent.as_posix()
        if rule.root == ".":
            within_root = parent == "." if not rule.recursive else True
        elif rule.recursive:
            within_root = parent == rule.root or parent.startswith(rule.root + "/")
        else:
            within_root = parent == rule.root
        if within_root and fnmatch.fnmatchcase(path.name, rule.pattern):
            candidates.append(path.as_posix())
    if not candidates:
        raise CorpusScoreError("candidate rule selected no files from pinned HEAD")
    if len(candidates) > rule.maximum_files:
        raise CorpusScoreError("candidate rule exceeds its bounded file count")
    return tuple(candidates)


def prepare_candidate_case(
    corpus: CorpusCase,
    head_paths: frozenset[str],
) -> CorpusCase:
    candidates = derive_candidate_paths(corpus.candidate_rule, head_paths)
    required = {source.path for source in corpus.sources} | {
        imported.target for source in corpus.sources for imported in source.internal_imports
    }
    if not required <= set(candidates):
        raise CorpusScoreError("candidate rule excludes a labelled source or expected target")
    return replace(corpus, candidate_files=candidates)


def resolve_import_target(
    source: str,
    module: str,
    language: str,
    repository_files: frozenset[str],
) -> str | None:
    """Resolve one captured module specifier using repository filesystem rules only."""
    source_path = PurePosixPath(_safe_path(source, "import source"))
    candidates = set()
    if language == "python":
        cleaned = module.strip()
        if not cleaned:
            return None
        if cleaned.startswith("."):
            level = len(cleaned) - len(cleaned.lstrip("."))
            remainder = cleaned[level:]
            base_parts = list(source_path.parent.parts)
            if level - 1 > len(base_parts):
                return None
            base_parts = base_parts[: len(base_parts) - (level - 1)]
            module_parts = [part for part in remainder.split(".") if part]
            if not module_parts:
                return None
            roots = [PurePosixPath(*base_parts, *module_parts)]
        else:
            module_parts = [part for part in cleaned.split(".") if part]
            if not module_parts:
                return None
            roots = [PurePosixPath(*module_parts), PurePosixPath("src", *module_parts)]
        for root in roots:
            candidates.add(root.with_suffix(".py").as_posix())
            candidates.add((root / "__init__.py").as_posix())
    elif language == "javascript":
        if not module.startswith(".") or "\\" in module or "\x00" in module:
            return None
        normalized = posixpath.normpath((source_path.parent / module).as_posix())
        if normalized == ".." or normalized.startswith("../") or normalized.startswith("/"):
            return None
        base = PurePosixPath(normalized)
        if base.suffix:
            candidates.add(base.as_posix())
        else:
            for suffix in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
                candidates.add(base.with_suffix(suffix).as_posix())
                candidates.add((base / ("index" + suffix)).as_posix())
    else:
        raise CorpusScoreError("import language is unsupported")
    matches = sorted(candidates & set(repository_files))
    return matches[0] if len(matches) == 1 else None


def _duration_summary(durations: Sequence[int]) -> tuple[int | float, int]:
    if not durations:
        return 0, 0
    median = statistics.median(durations)
    if isinstance(median, float) and median.is_integer():
        median = int(median)
    return median, max(durations)


def evaluate_provider_gates(
    precision: float,
    recall: float,
    undisclosed_high_risk_misses: Sequence[str],
    scope_inventory_complete: bool,
) -> dict[str, bool]:
    gates = {
        "precision": precision >= MINIMUM_PRECISION,
        "recall": recall >= MINIMUM_RECALL,
        "high_risk": not undisclosed_high_risk_misses,
        "scope_inventory": scope_inventory_complete,
    }
    gates["passed"] = all(gates.values())
    return gates


def evaluate_release_gates(
    providers_pass: bool,
    disagreement_count: int,
    durations_ms: Sequence[int],
    compact_bytes: int,
) -> dict[str, bool]:
    median_duration, hard_duration = _duration_summary(durations_ms)
    gates = {
        "providers": providers_pass,
        "disagreement": disagreement_count == 0,
        "median_duration": median_duration <= MAXIMUM_MEDIAN_MS,
        "hard_duration": hard_duration <= MAXIMUM_HARD_MS,
        "compact_bytes": compact_bytes <= MAXIMUM_COMPACT_BYTES,
    }
    gates["passed"] = all(gates.values())
    return gates


def _ratio(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else round(numerator / denominator, 6)


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def score_observations(
    expected: Mapping[RelationshipKey, bool],
    observations: Sequence[EngineObservation],
    disclosed_high_risk_misses: Mapping[str, set[str] | frozenset[str]],
    *,
    provenance: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], bytes]:
    """Score each provider independently over the complete labelled source universe."""
    expected_rows = dict(expected)
    if not expected_rows:
        raise CorpusScoreError("at least one expected relationship is required")
    if set(disclosed_high_risk_misses) != set(PROVIDERS):
        raise CorpusScoreError("high-risk disclosures must cover both providers")
    corpora = {key[0] for key in expected_rows}
    observations_by_run = {(row.corpus, row.provider): row for row in observations}
    required_runs = {(corpus, provider) for corpus in corpora for provider in PROVIDERS}
    if len(observations_by_run) != len(observations) or set(observations_by_run) != required_runs:
        raise CorpusScoreError("observations must cover each expected corpus/provider exactly once")
    expected_set = set(expected_rows)
    provider_predictions: dict[str, set[RelationshipKey]] = {
        provider: set() for provider in PROVIDERS
    }
    durations = []
    runs = []
    for run_key in sorted(required_runs):
        corpus, provider = run_key
        observation = observations_by_run[run_key]
        predictions = {(corpus, source, target) for source, target in observation.predictions}
        provider_predictions[provider].update(predictions)
        durations.append(observation.duration_ms)
        runs.append(
            {
                "corpus": corpus,
                "provider": provider,
                "prediction_count": len(predictions),
                "unknown_frontier": observation.frontier_count,
                "duration_ms": observation.duration_ms,
                "scope_inventory_complete": observation.scope_inventory_complete,
                "discovered_modules": [
                    f"{source}:{module}" for source, module in observation.discovered_modules
                ],
                "scope_manifest": [
                    {"path": path, "sha256": digest} for path, digest in observation.scope_manifest
                ],
                "version": observation.version,
                "executable_sha256": observation.executable_sha256,
                "detail": observation.detail,
            }
        )
    provider_reports = {}
    for provider in PROVIDERS:
        predictions = provider_predictions[provider]
        true_positive = predictions & expected_set
        false_positive = predictions - expected_set
        false_negative = expected_set - predictions
        precision = _ratio(len(true_positive), len(true_positive) + len(false_positive))
        recall = _ratio(len(true_positive), len(true_positive) + len(false_negative))
        missing_high_risk = tuple(
            sorted(
                _relationship_text(key)
                for key in false_negative
                if expected_rows[key]
                and _relationship_text(key) not in disclosed_high_risk_misses[provider]
            )
        )
        inventory_complete = all(
            observations_by_run[(corpus, provider)].scope_inventory_complete for corpus in corpora
        )
        gates = evaluate_provider_gates(precision, recall, missing_high_risk, inventory_complete)
        provider_reports[provider] = {
            "true_positive": len(true_positive),
            "false_positive": len(false_positive),
            "false_negative": len(false_negative),
            "precision": precision,
            "recall": recall,
            "unknown_frontier": sum(
                observations_by_run[(corpus, provider)].frontier_count for corpus in corpora
            ),
            "undisclosed_high_risk_misses": missing_high_risk[:32],
            "false_positive_edges": tuple(
                sorted(_relationship_text(key) for key in false_positive)
            )[:32],
            "false_negative_edges": tuple(
                sorted(_relationship_text(key) for key in false_negative)
            )[:32],
            "gates": gates,
            "passed": gates["passed"],
        }
    disagreement_keys = provider_predictions["builtin"] ^ provider_predictions["ast-grep"]
    disagreement = {
        "count": len(disagreement_keys),
        "edges": [_relationship_text(key) for key in sorted(disagreement_keys)[:32]],
        "passed": not disagreement_keys,
    }
    ast_grep_gates = provider_reports["ast-grep"]["gates"]
    if not isinstance(ast_grep_gates, dict):
        raise CorpusScoreError("provider gate report is malformed")
    ast_grep_gates["disagreement"] = not disagreement_keys
    ast_grep_gates["passed"] = all(ast_grep_gates.values())
    provider_reports["ast-grep"]["passed"] = ast_grep_gates["passed"]
    median_duration, hard_duration = _duration_summary(durations)
    candidate_rules = (provenance or {}).get("candidate_rules", [])
    if not isinstance(candidate_rules, list):
        raise CorpusScoreError("candidate rule provenance is malformed")
    candidate_file_count = sum(
        len(observations_by_run[(corpus, "builtin")].scope_manifest) for corpus in corpora
    )
    report: dict[str, object] = {
        "schema_version": 2,
        "scope": {
            "kind": "scoped-static-internal-import-discovery",
            "source_count": len({(key[0], key[1]) for key in expected_set}),
            "relationship_count": len(expected_set),
            "candidate_file_count": candidate_file_count,
            "candidate_rules": candidate_rules,
        },
        "provenance": dict(provenance or {}),
        "limits": {
            "minimum_precision": MINIMUM_PRECISION,
            "minimum_recall": MINIMUM_RECALL,
            "maximum_median_ms": MAXIMUM_MEDIAN_MS,
            "maximum_hard_ms": MAXIMUM_HARD_MS,
            "maximum_compact_bytes": MAXIMUM_COMPACT_BYTES,
            "allow_undisclosed_high_risk_miss": False,
            "require_zero_provider_disagreement": True,
        },
        "providers": provider_reports,
        "disagreement": disagreement,
        "performance": {
            "median_duration_ms": median_duration,
            "hard_duration_ms": hard_duration,
        },
        "runs": runs,
        "compact_bytes": 0,
        "gates": {},
        "passed": False,
    }
    previous = -1
    for _ in range(12):
        payload = _canonical_bytes(report)
        compact_bytes = len(payload)
        report["compact_bytes"] = compact_bytes
        providers_pass = all(bool(row["passed"]) for row in provider_reports.values())
        release_gates = evaluate_release_gates(
            providers_pass, len(disagreement_keys), durations, compact_bytes
        )
        report["gates"] = release_gates
        report["passed"] = release_gates["passed"]
        updated = _canonical_bytes(report)
        if len(updated) == compact_bytes and compact_bytes == previous:
            return report, updated
        previous = compact_bytes
    raise CorpusScoreError("compact report size did not converge")


def guard_verified_corpora(
    catalog_path: Path,
    destination: Path,
    operation: Callable[[], T],
    *,
    repository_root: Path = ROOT,
    allow_local_repositories: bool = False,
) -> T:
    verification_arguments = {
        "repository_root": repository_root,
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
    return value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)


def _descriptor_read(root: Path, relative: str) -> bytes:
    safe = _safe_path(relative, "scoped shadow path")
    root_metadata = root.lstat()
    if root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
        raise CorpusScoreError("scoped shadow source root is unsafe")
    descriptors = []
    try:
        root_fd = os.open(
            str(root),
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        descriptors.append(root_fd)
        if FETCHER._identity(os.fstat(root_fd)) != FETCHER._identity(root_metadata):
            raise CorpusScoreError("scoped shadow source root changed while opening")
        current = root_fd
        parts = PurePosixPath(safe).parts
        for part in parts[:-1]:
            metadata = os.stat(part, dir_fd=current, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise CorpusScoreError("scoped shadow source parent is unsafe")
            child = os.open(
                part,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current,
            )
            descriptors.append(child)
            if FETCHER._identity(os.fstat(child)) != FETCHER._identity(metadata):
                raise CorpusScoreError("scoped shadow source parent changed while opening")
            current = child
        metadata = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_SOURCE_BYTES:
            raise CorpusScoreError("scoped shadow source file is unsafe or oversized")
        payload = FETCHER._read_worktree_file(current, parts[-1], metadata, safe)
        if FETCHER._identity(root.lstat()) != FETCHER._identity(root_metadata):
            raise CorpusScoreError("scoped shadow source root changed during read")
        return payload
    except CorpusScoreError:
        raise
    except (OSError, ValueError) as error:
        raise CorpusScoreError("scoped shadow source cannot be read safely") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _write_shadow_file(root: Path, relative: str, payload: bytes) -> None:
    path = root.joinpath(*PurePosixPath(relative).parts)
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
                raise CorpusScoreError("scoped shadow write made no progress")
            offset += written
        os.fchmod(descriptor, 0o400)
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class ScopedShadow:
    root: Path
    manifest: tuple[ModuleKey, ...]


@contextlib.contextmanager
def _scoped_shadow(corpus: CorpusCase, checkout: Path) -> Iterator[ScopedShadow]:
    if not corpus.candidate_files:
        raise CorpusScoreError("candidate files are unavailable for scoped shadow")
    candidates = set(corpus.candidate_files)
    source_digests = {source.path: source.sha256 for source in corpus.sources}
    with tempfile.TemporaryDirectory(prefix="rir-builtin-scope-") as temporary:
        root = Path(temporary).resolve()
        root.chmod(0o700)
        manifest = []
        payloads = {}
        for relative in sorted(candidates):
            payload = _descriptor_read(checkout, relative)
            digest = hashlib.sha256(payload).hexdigest()
            if relative in source_digests and digest != source_digests[relative]:
                raise CorpusScoreError(
                    f"{corpus.id} source digest differs from curation: {relative}"
                )
            payloads[relative] = payload
            manifest.append((relative, digest))
            _write_shadow_file(root, relative, payload)
        for relative, digest in manifest:
            copied = _descriptor_read(root, relative)
            if copied != payloads[relative] or hashlib.sha256(copied).hexdigest() != digest:
                raise CorpusScoreError("scoped shadow manifest differs from pinned bytes")
        yield ScopedShadow(root, tuple(manifest))


def _verify_scoped_sources(corpus: CorpusCase, checkout: Path) -> None:
    for source in corpus.sources:
        payload = _descriptor_read(checkout, source.path)
        if hashlib.sha256(payload).hexdigest() != source.sha256:
            raise CorpusScoreError(
                f"{corpus.id} source digest differs from curation: {source.path}"
            )


def project_builtin_result(
    corpus: str,
    labelled_sources: Sequence[str],
    result: object,
    duration_ms: int,
    shadow_manifest: Sequence[ModuleKey],
) -> EngineObservation:
    node_locations = {
        _field(node, "id"): _field(node, "location")
        for node in tuple(getattr(result, "nodes", ()))
        if isinstance(_field(node, "id"), str) and isinstance(_field(node, "location"), str)
    }
    scope = set(labelled_sources)
    predictions = set()
    frontier = tuple(getattr(result, "frontier", ()))
    frontier_count = len(frontier)
    for edge in tuple(getattr(result, "edges", ())):
        source = node_locations.get(_field(edge, "source"))
        target = node_locations.get(_field(edge, "target"))
        if not isinstance(source, str) or not isinstance(target, str) or source == target:
            frontier_count += 1
        elif source not in scope:
            frontier_count += 1
        elif (
            _field(edge, "confidence") == "structural-inferred"
            and _field(edge, "kind") == "imports"
        ):
            predictions.add((source, target))
        else:
            frontier_count += 1
    manifest = dict(shadow_manifest)
    source_digests = getattr(result, "source_digests", {})
    skipped = getattr(result, "skipped", {})
    complete = (
        getattr(result, "budget_status", None) == "closed"
        and not frontier
        and isinstance(source_digests, Mapping)
        and all(source_digests.get(path) == digest for path, digest in manifest.items())
        and isinstance(skipped, Mapping)
        and not any(path in skipped for path in manifest)
    )
    details = []
    if getattr(result, "budget_status", None) != "closed":
        details.append("built-in scoped scan did not close")
        frontier_count += 1
    if frontier:
        details.append("built-in scoped scan reported frontier")
    if not isinstance(source_digests, Mapping) or not all(
        source_digests.get(path) == digest for path, digest in manifest.items()
    ):
        details.append("built-in scoped source digests differ from shadow manifest")
    if not isinstance(skipped, Mapping) or any(path in skipped for path in manifest):
        details.append("built-in scoped scan skipped manifest paths")
    return EngineObservation(
        corpus,
        "builtin",
        tuple(predictions),
        frontier_count,
        duration_ms,
        "builtin-v1",
        None,
        scope_inventory_complete=complete,
        detail="; ".join(details) or None,
        scope_manifest=tuple(shadow_manifest),
    )


_RUNTIME: tuple[ModuleType, ModuleType] | None = None


def _runtime() -> tuple[ModuleType, ModuleType]:
    global _RUNTIME
    if _RUNTIME is None:
        builtin = _load_script("_rir_graph_corpus_builtin_v2", "graph_builtin.py")
        canary = _load_script("_rir_graph_corpus_ast_grep_canary_v2", "run-ast-grep-canary.py")
        _RUNTIME = builtin, canary
    return _RUNTIME


def run_builtin(corpus: CorpusCase, checkout: Path) -> EngineObservation:
    _verify_scoped_sources(corpus, checkout)
    if not corpus.candidate_files:
        corpus = prepare_candidate_case(corpus, _repository_files(checkout))
    builtin, _ = _runtime()
    with _scoped_shadow(corpus, checkout) as shadow:
        seeds = tuple(builtin.ScanSeed(source.path, source.path) for source in corpus.sources)
        started = time.monotonic()
        result = builtin.scan_repository(
            shadow.root, seeds, builtin.ScanLimits(max_seconds=30), time
        )
        duration_ms = max(0, round((time.monotonic() - started) * 1000))
        return project_builtin_result(
            corpus.id,
            tuple(source.path for source in corpus.sources),
            result,
            duration_ms,
            shadow.manifest,
        )


def _repository_files(root: Path) -> frozenset[str]:
    files = set()
    for current, directories, names in os.walk(root, topdown=True, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if not (Path(current) == root and name == ".git")
            and not (Path(current) / name).is_symlink()
        )
        for name in sorted(names):
            path = Path(current) / name
            if path.is_symlink() or not path.is_file():
                continue
            files.add(path.relative_to(root).as_posix())
    return frozenset(files)


_AST_RULES = {
    "python": (
        ("from $MODULE import $$$NAMES", "MODULE", "python-from"),
        ("import $MODULE", "MODULE", "python-import"),
        ("from __future__ import $$$NAMES", None, "python-future"),
    ),
    "javascript": (("import $CLAUSE from $SOURCE", "SOURCE", "javascript-from"),),
}


def _normalize_captured_module(text: str, rule: str) -> str:
    if rule == "python-from":
        return text.strip()
    if rule == "python-import":
        value = text.split(" as ", 1)[0].strip()
        if "," in value:
            raise CorpusScoreError("multi-module Python import is outside the scoped rule")
        return value
    if rule == "javascript-from":
        match = re.fullmatch(r"(?P<quote>['\"])(?P<value>[^'\"\\\r\n]+)(?P=quote)", text)
        if match is None:
            raise CorpusScoreError("JavaScript import source capture is invalid")
        return match.group("value")
    raise CorpusScoreError("ast-grep import rule is unknown")


def _parse_ast_grep_modules(
    adapter: ModuleType,
    source: SourceScope,
    checkout: Path,
    output: str,
    capture: str | None,
    rule: str,
) -> tuple[str, ...]:
    modules = []
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, RecursionError) as error:
            raise CorpusScoreError("ast-grep import output is malformed") from error
        required = {"text", "range", "file", "lines", "charCount", "language", "metaVariables"}
        if not isinstance(row, dict) or set(row) != required:
            raise CorpusScoreError("ast-grep import output schema drifted")
        if row["file"] != source.path or not isinstance(row["text"], str):
            raise CorpusScoreError("ast-grep import output escaped the labelled source")
        start_line, start_col, end_line, end_col = adapter._range(row["range"])
        proof = adapter._source_proof(
            checkout,
            source.path,
            (start_line - 1, start_col - 1, end_line - 1, end_col - 1),
        )
        if (
            row["range"].get("byteOffset")
            != {"start": proof["byte_start"], "end": proof["byte_end"]}
            or row["charCount"] != {"leading": proof["leading"], "trailing": proof["trailing"]}
            or row["text"] != proof["excerpt"]
            or row["lines"] != proof["lines"]
        ):
            raise CorpusScoreError("ast-grep import match is not bound to source bytes")
        if capture is None:
            import_match = re.match(
                r"^\s*from\s+(?P<module>[.A-Za-z_][A-Za-z0-9_.]*)\s+import\b",
                row["text"],
            )
            if import_match is None:
                raise CorpusScoreError("ast-grep special import source is invalid")
            modules.append(import_match.group("module"))
            continue
        metadata = row["metaVariables"]
        if not isinstance(metadata, dict) or not isinstance(metadata.get("single"), dict):
            raise CorpusScoreError("ast-grep import metavariables are invalid")
        captured = metadata["single"].get(capture)
        if (
            not isinstance(captured, dict)
            or not isinstance(captured.get("text"), str)
            or not isinstance(captured.get("range"), dict)
        ):
            raise CorpusScoreError("ast-grep did not capture the module specifier")
        meta_start_line, meta_start_col, meta_end_line, meta_end_col = adapter._range(
            captured["range"]
        )
        meta_proof = adapter._source_proof(
            checkout,
            source.path,
            (
                meta_start_line - 1,
                meta_start_col - 1,
                meta_end_line - 1,
                meta_end_col - 1,
            ),
        )
        if (
            captured["range"].get("byteOffset")
            != {"start": meta_proof["byte_start"], "end": meta_proof["byte_end"]}
            or captured["text"] != meta_proof["excerpt"]
        ):
            raise CorpusScoreError("ast-grep module capture is not bound to source bytes")
        modules.append(_normalize_captured_module(captured["text"], rule))
    return tuple(modules)


def run_ast_grep(
    corpus: CorpusCase,
    checkout: Path,
    executable: Path,
) -> EngineObservation:
    _verify_scoped_sources(corpus, checkout)
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
    deadline = providers.Deadline(time, max(0.0, 30.0 - (time.monotonic() - started)))
    specification = providers.ProviderSpec("ast-grep", selected)
    repository_files = _repository_files(checkout)
    predictions = set()
    discovered = set()
    complete = True
    details = []
    for source in corpus.sources:
        source_modules: set[str] = set()
        for pattern, capture, rule in _AST_RULES[source.language]:
            result = providers.run_provider(
                specification,
                (
                    "--json=stream",
                    "--lang",
                    source.language,
                    "--pattern",
                    pattern,
                    source.path,
                ),
                checkout,
                deadline,
                runner=None,
            )
            exact_no_match = (
                result.status == "failed"
                and result.returncode == 1
                and not result.stdout
                and not result.stderr
                and not result.stdout_truncated
                and not result.stderr_truncated
                and result.executable_sha256 == executable_sha256
            )
            if exact_no_match:
                continue
            if result.status != "ready" or result.executable_sha256 != executable_sha256:
                complete = False
                details.append(result.detail or f"{rule} query failed")
                continue
            source_modules.update(
                _parse_ast_grep_modules(adapter, source, checkout, result.stdout, capture, rule)
            )
        for module in source_modules:
            discovered.add((source.path, module))
            target = resolve_import_target(source.path, module, source.language, repository_files)
            if target is not None:
                predictions.add((source.path, target))
        if frozenset(source_modules) != source.labelled_modules:
            complete = False
            details.append(f"module inventory differs from complete labels for {source.path}")
    duration_ms = max(0, round((time.monotonic() - started) * 1000))
    return EngineObservation(
        corpus.id,
        "ast-grep",
        tuple(predictions),
        0,
        duration_ms,
        version,
        executable_sha256,
        tuple(discovered),
        complete,
        "; ".join(details)[:512] or None,
    )


def _file_sha256(path: Path) -> str:
    payload = FETCHER._read_regular(Path(path), 256 * 1024, "score provenance file")
    return hashlib.sha256(payload).hexdigest()


def _candidate_rule_report(corpus: CorpusCase) -> dict[str, object]:
    rule = corpus.candidate_rule
    if not isinstance(rule, FETCHER.CandidateRule):
        raise CorpusScoreError("corpus candidate rule is unavailable")
    return {
        "corpus": corpus.id,
        "root": rule.root,
        "pattern": rule.pattern,
        "recursive": rule.recursive,
        "maximum_files": rule.maximum_files,
        "candidate_count": len(corpus.candidate_files),
    }


def run_evaluation(
    catalog_path: Path,
    expected_path: Path,
    destination: Path,
    ast_grep_executable: Path,
    *,
    repository_root: Path = ROOT,
    allow_local_repositories: bool = False,
    builtin_runner: Callable[[CorpusCase, Path], EngineObservation] = run_builtin,
    ast_grep_runner: Callable[[CorpusCase, Path, Path], EngineObservation] = run_ast_grep,
) -> tuple[dict[str, object], bytes]:
    specifications = FETCHER.load_catalog(
        catalog_path, allow_local_repositories=allow_local_repositories
    )
    expectations = load_expectations(expected_path, specifications)
    by_id = {specification.id: specification for specification in specifications}

    def evaluate() -> tuple[dict[str, object], bytes]:
        head_trees = FETCHER.verified_head_trees(
            catalog_path,
            destination,
            repository_root=repository_root,
            allow_local_repositories=allow_local_repositories,
        )
        observations = []
        runtime_cases = []
        for declared_corpus in expectations.corpora:
            tree = head_trees.get(declared_corpus.id)
            if not isinstance(tree, Mapping):
                raise CorpusScoreError("verified HEAD manifest is unavailable")
            corpus = prepare_candidate_case(declared_corpus, frozenset(tree))
            runtime_cases.append(corpus)
            checkout = Path(destination).resolve(strict=True) / by_id[corpus.id].checkout
            _verify_scoped_sources(corpus, checkout)
            observations.append(builtin_runner(corpus, checkout))
            observations.append(ast_grep_runner(corpus, checkout, ast_grep_executable))
        provenance = {
            "catalog_sha256": _file_sha256(catalog_path),
            "expectations_sha256": _file_sha256(expected_path),
            "destination": str(Path(destination).resolve(strict=True)),
            "commits": [corpus.commit for corpus in expectations.corpora],
            "candidate_rules": [_candidate_rule_report(corpus) for corpus in runtime_cases],
        }
        return score_observations(
            expectations.expected,
            tuple(observations),
            expectations.disclosed_high_risk_misses,
            provenance=provenance,
        )

    return guard_verified_corpora(
        catalog_path,
        destination,
        evaluate,
        repository_root=repository_root,
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
            lambda: run_evaluation(CATALOG_PATH, EXPECTED_PATH, args.corpora, args.ast_grep),
        )
    except (CorpusScoreError, FETCHER.CorpusError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(report_bytes + b"\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
