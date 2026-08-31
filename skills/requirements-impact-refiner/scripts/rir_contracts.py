"""Controller request/result contracts and bounded validation helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    CompactGraphPayload = Mapping[str, object]
    ScanSeedType = Any


MAX_BEGIN_BYTES = 256 * 1024
MAX_TRACE_BYTES = 256 * 1024
MAX_FINALIZE_BYTES = 2 * 1024 * 1024
MAX_STRING_BYTES = 64 * 1024
LOCAL_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}")
ANALYSIS_KEYS = {
    "phase",
    "refined_requirement",
    "invariants",
    "impacts",
    "decision_needed",
    "decisions",
    "criteria",
    "unresolved",
    "scope",
    "workflow",
}
ROW_KEYS = {
    "invariants": {"key", "behavior", "evidence_level", "evidence"},
    "impacts": {
        "key",
        "category",
        "severity",
        "state",
        "evidence_level",
        "evidence",
        "graph_path_keys",
        "invariant_keys",
        "decision_keys",
        "criterion_keys",
        "summary",
    },
    "decisions": {"key", "choice", "accepted_impact_keys", "rationale"},
    "criteria": {"key", "impact_key", "invariant_key", "criterion", "evidence"},
    "unresolved": {"impact_key", "state", "rationale", "decision_key", "owner"},
    "scope": {"boundary", "evidence", "confidence"},
}
IMPACT_OPTIONAL_KEYS = {"coverage_rationale"}
SUMMARY_KEYS = {"changed_feature", "possible_issue", "affected", "trigger", "prevention"}


@dataclass(frozen=True)
class BeginRequest:
    repo_root: Path
    request: str
    repository_evidence: tuple[str, ...]
    adapter: str
    audience_override: str | None = None
    delivery_override: str | None = None
    scan_id: str | None = None


@dataclass(frozen=True)
class DraftResult:
    draft_id: str
    draft_path: Path
    report_id: str
    revision: int
    previous_sha256: str
    settings: Mapping[str, object]
    prior_state: Mapping[str, object] | None
    prior_key_map: Mapping[str, object] | None
    scan_id: str | None = None
    graph_receipt_id: str | None = None


@dataclass(frozen=True)
class ScanRequest:
    repo_root: Path
    change_request: str
    evidence: tuple[str, ...]
    audience_override: str | None = None
    previous_report_id: str | None = None
    previous_revision: int | None = None
    changed_paths: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TraceRequest:
    repo_root: Path
    draft_id: str
    seeds: tuple[ScanSeedType, ...]


@dataclass(frozen=True)
class TraceResult:
    receipt_id: str
    receipt_path: Path
    receipt_sha256: str
    compact_graph: CompactGraphPayload
    budget_status: str
    request_sha256: str
    seeds: tuple[ScanSeedType, ...]


@dataclass(frozen=True)
class FinalizeRequest:
    repo_root: Path
    draft_id: str
    analysis: Mapping[str, object]
    graph_receipt_id: str | None = None


@dataclass(frozen=True)
class FinalizeResult:
    status: str
    report_id: str
    revision: int
    delivery: str
    display_text: str
    state_path: Path
    markdown_path: Path
    markdown_sha256: str


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _all_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _all_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _all_strings(item)


def bounded_bytes(value: object, maximum: int, label: str) -> bytes:
    payload = canonical_bytes(value)
    if len(payload) > maximum:
        unit = "256 KiB" if maximum in {MAX_BEGIN_BYTES, MAX_TRACE_BYTES} else "2 MiB"
        raise ValueError(f"{label} exceeds {unit}")
    if any(len(text.encode("utf-8")) > MAX_STRING_BYTES for text in _all_strings(value)):
        raise ValueError(f"{label} contains a string larger than 64 KiB")
    return payload


def _check_keys(label: str, value: object, expected: set[str]) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise ValueError(f"unknown {label} key {unknown[0]}")
    if missing:
        raise ValueError(f"missing {label} key {missing[0]}")


def _local_key(value: object, label: str) -> str:
    if not isinstance(value, str) or LOCAL_KEY_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid {label} local key")
    return value


def validate_analysis(analysis: Mapping[str, object]) -> None:
    _check_keys("analysis", analysis, ANALYSIS_KEYS)
    if analysis["phase"] not in {"pre-decision", "post-decision"}:
        raise ValueError("invalid analysis phase")
    if (
        not isinstance(analysis["refined_requirement"], str)
        or not analysis["refined_requirement"].strip()
    ):
        raise ValueError("refined_requirement must be nonempty")
    for section, expected in ROW_KEYS.items():
        rows = analysis[section]
        if not isinstance(rows, list):
            raise ValueError(f"{section} must be an array")
        if len(rows) > 128:
            raise ValueError(f"{section} has too many rows")
        keys = []
        for row in rows:
            if section == "impacts":
                if not isinstance(row, dict):
                    raise ValueError("impact must be an object")
                unknown = sorted(set(row) - expected - IMPACT_OPTIONAL_KEYS)
                missing = sorted(expected - set(row))
                if unknown:
                    raise ValueError(f"unknown impact key {unknown[0]}")
                if missing:
                    raise ValueError(f"missing impact key {missing[0]}")
            else:
                _check_keys(section[:-1], row, expected)
            if "key" in row:
                keys.append(_local_key(row["key"], section[:-1]))
            if section == "impacts":
                _check_keys("impact summary", row["summary"], SUMMARY_KEYS)
                for name in ("invariant_keys", "decision_keys", "criterion_keys"):
                    if not isinstance(row[name], list) or len(row[name]) > 128:
                        raise ValueError(f"impact {name} has too many items")
                graph_path_keys = row["graph_path_keys"]
                if (
                    not isinstance(graph_path_keys, list)
                    or len(graph_path_keys) > 128
                    or not all(isinstance(key, str) for key in graph_path_keys)
                    or len(graph_path_keys) != len(set(graph_path_keys))
                ):
                    raise ValueError("impact graph_path_keys must be a unique bounded array")
                if not all(re.fullmatch(r"PATH-\d{3}", key) for key in graph_path_keys):
                    raise ValueError("invalid graph path key")
            if section == "decisions" and (
                not isinstance(row["accepted_impact_keys"], list)
                or len(row["accepted_impact_keys"]) > 128
            ):
                raise ValueError("decision accepted_impact_keys has too many items")
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate {section} local key")
    if analysis["phase"] == "pre-decision":
        decision_needed = analysis["decision_needed"]
        if not isinstance(decision_needed, dict):
            raise ValueError("decision_needed must be an object")
        _check_keys("decision_needed", decision_needed, {"question", "options"})
        options = decision_needed["options"]
        if not isinstance(options, list) or not 2 <= len(options) <= 3:
            raise ValueError("decision_needed requires two or three options")
        for option in options:
            _check_keys("decision option", option, {"option", "impact_keys", "tradeoff"})
            if not isinstance(option["impact_keys"], list) or len(option["impact_keys"]) > 128:
                raise ValueError("decision option impact_keys has too many items")
        if analysis["decisions"]:
            raise ValueError("pre-decision analysis forbids decisions")
    else:
        if analysis["decision_needed"] is not None or not analysis["decisions"]:
            raise ValueError("post-decision analysis requires decisions only")
    if not isinstance(analysis["scope"], list) or not analysis["scope"]:
        raise ValueError("scope requires at least one row")
    if not isinstance(analysis["workflow"], str) or not analysis["workflow"].strip():
        raise ValueError("workflow must be nonempty")
