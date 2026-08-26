"""Deterministic compact-delivery performance observations and smoke gate."""

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median
from typing import Optional

from .models import RunStatus

SMOKE_CASE_IDS = (
    "POS-authorization",
    "NEG-debugging",
    "INT-superpowers",
    "LINEAGE-stable-blocked",
    "LINEAGE-reopened",
    "LINEAGE-no-false-resolution",
)
BASELINE_ROUTED_RESOURCE_WORDS = 3500
MAX_MEDIAN_OUTPUT_WORDS = 450
MAX_MEDIAN_ROUTED_RESOURCE_WORDS = BASELINE_ROUTED_RESOURCE_WORDS // 2
GRAPH_SMOKE_CASE_IDS = (
    "GRAPH-api-mobile-cache-migration",
    "GRAPH-auth-role-audit-consumer",
    "GRAPH-event-retry-idempotency-side-effect",
    "GRAPH-schema-serializer-backfill-export",
    "GRAPH-config-deploy-worker-health",
    "GRAPH-negative-no-change",
)
GRAPH_NEGATIVE_CASE_ID = "GRAPH-negative-no-change"
MAX_MEDIAN_GRAPH_DURATION_MS = 10_000
MAX_GRAPH_DURATION_MS = 30_000
MAX_FAST_SCAN_OUTPUT_WORDS = 180
MAX_PREVIOUS_LOOKUP_P95_MS = 300
MAX_STALE_DELTA_P95_MS = 3_000
V05_REPEATED_INPUT_TOKEN_BASELINE = 3_500


@dataclass(frozen=True)
class PerformanceObservation:
    case_id: str
    repetition: int
    status: RunStatus
    attempt: int
    retry_of: Optional[str]
    prompt_bytes: int
    routed_resource_bytes: int
    routed_resource_words: int
    output_bytes: int
    output_words: int
    duration_ms: Optional[int]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    impact_ids: tuple[str, ...]
    state_markdown_match: bool
    workflow_boundary_passed: bool
    controller_begin_calls: int
    controller_finalize_calls: int
    controller_draft_ids_match: bool
    controller_finalize_succeeded: bool
    controller_display_text_exact_match: bool
    controller_display_text_presentation_equivalent: bool
    controller_display_comparison: str


@dataclass(frozen=True)
class SmokeGateResult:
    passed: bool
    errors: tuple[str, ...]
    median_output_words: float
    median_routed_resource_words: float


@dataclass(frozen=True)
class GraphPerformanceObservation:
    case_id: str
    repetition: int
    status: RunStatus
    mechanical_passed: bool
    graph_passed: bool
    attempt: int
    retry_of: Optional[str]
    graph_duration_ms: Optional[int]
    output_words: int
    routed_resource_words: int
    receipt_state_provider_parity: bool
    uncovered_high_risk_nodes: tuple[str, ...]
    controller_begin_calls: int
    controller_trace_calls: int
    controller_finalize_calls: int
    controller_evidence_valid: bool
    duplicate_or_error_calls: bool
    input_tokens: Optional[int]
    output_tokens: Optional[int]


@dataclass(frozen=True)
class GraphSmokeGateResult:
    passed: bool
    errors: tuple[str, ...]
    median_graph_duration_ms: float
    median_output_words: float
    median_routed_resource_words: float


@dataclass(frozen=True)
class FastScanPerformanceObservation:
    case_id: str
    repetition: int
    status: RunStatus
    attempt: int
    retry_of: Optional[str]
    scan_duration_ms: Optional[int]
    output_words: int
    controller_calls: tuple[str, ...]
    scoring_passed: bool
    exact_provenance: bool
    uncovered_high_risk_nodes: tuple[str, ...]
    input_tokens: Optional[int]
    output_tokens: Optional[int]


@dataclass(frozen=True)
class FastScanGateResult:
    passed: bool
    errors: tuple[str, ...]
    median_scan_duration_ms: float
    median_output_words: float


@dataclass(frozen=True)
class InstantPerformanceObservation:
    case_id: str
    path: str
    elapsed_ms: int
    provider_calls: int
    graph_calls: int
    model_calls: int
    estimated_input_tokens: int
    baseline_input_tokens: int
    expected_frontier: tuple[str, ...]
    observed_frontier: tuple[str, ...]


@dataclass(frozen=True)
class InstantPerformanceGateResult:
    passed: bool
    errors: tuple[str, ...]
    previous_lookup_p95_ms: int
    stale_delta_p95_ms: int
    repeated_median_estimated_input_tokens: float


def _median(values: Sequence[int]) -> float:
    return float(median(values)) if values else 0.0


def _p95(values: Sequence[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, (95 * len(ordered) + 99) // 100)
    return ordered[rank - 1]


def evaluate_instant_performance_gate(
    observations: Sequence[InstantPerformanceObservation],
) -> InstantPerformanceGateResult:
    errors = []
    rows = tuple(row for row in observations if isinstance(row, InstantPerformanceObservation))
    if len(rows) != len(observations):
        errors.append("instant observations contain invalid rows")
    if len({row.case_id for row in rows}) != len(rows):
        errors.append("instant observations contain duplicate case IDs")
    if {row.path for row in rows} != {"fresh", "stale_delta", "repeated"}:
        errors.append("instant observations must cover fresh, stale_delta, and repeated paths")
    for row in rows:
        if (
            not isinstance(row.case_id, str)
            or not row.case_id
            or row.path not in {"fresh", "stale_delta", "repeated"}
            or any(
                type(value) is not int or value < 0
                for value in (
                    row.elapsed_ms,
                    row.provider_calls,
                    row.graph_calls,
                    row.model_calls,
                    row.estimated_input_tokens,
                    row.baseline_input_tokens,
                )
            )
            or not isinstance(row.expected_frontier, tuple)
            or not isinstance(row.observed_frontier, tuple)
            or any(
                not isinstance(item, str)
                for item in (*row.expected_frontier, *row.observed_frontier)
            )
        ):
            errors.append(f"{row.case_id} has malformed instant performance evidence")

    fresh = tuple(row for row in rows if row.path == "fresh")
    stale = tuple(row for row in rows if row.path == "stale_delta")
    repeated = tuple(row for row in rows if row.path == "repeated")
    previous_p95 = _p95([row.elapsed_ms for row in fresh])
    stale_p95 = _p95([row.elapsed_ms for row in stale])
    if previous_p95 > MAX_PREVIOUS_LOOKUP_P95_MS:
        errors.append("previous lookup p95 exceeds 300 ms")
    if stale_p95 > MAX_STALE_DELTA_P95_MS:
        errors.append("stale delta p95 exceeds 3000 ms")
    if any((row.provider_calls, row.graph_calls, row.model_calls) != (0, 0, 0) for row in fresh):
        errors.append("fresh reuse performed provider, graph, or model work")
    repeated_median = _median([row.estimated_input_tokens for row in repeated])
    if any(row.baseline_input_tokens != V05_REPEATED_INPUT_TOKEN_BASELINE for row in repeated):
        errors.append("repeated request baseline is not the pinned v0.5 value")
    baseline_median = float(V05_REPEATED_INPUT_TOKEN_BASELINE)
    if repeated and repeated_median >= baseline_median:
        errors.append("repeated request did not reduce estimated input below v0.5")
    if any(not set(row.expected_frontier) <= set(row.observed_frontier) for row in rows):
        errors.append("instant path lost an expected frontier")
    unique = tuple(sorted(set(errors)))
    return InstantPerformanceGateResult(
        not unique,
        unique,
        previous_p95,
        stale_p95,
        repeated_median,
    )


def evaluate_smoke_gate(
    observations: Sequence[PerformanceObservation],
) -> SmokeGateResult:
    errors = []
    valid_observations = tuple(
        row for row in observations if isinstance(row, PerformanceObservation)
    )
    if len(valid_observations) != len(observations):
        errors.append("smoke observations contain invalid rows")
    keys = [(row.case_id, row.repetition) for row in valid_observations]
    expected = {(case_id, 1) for case_id in SMOKE_CASE_IDS}
    if set(keys) != expected or len(valid_observations) != len(expected):
        errors.append("smoke observations do not cover the exact six cases")
    if len(set(keys)) != len(keys):
        errors.append("smoke observations contain duplicate case/repetition rows")
    if any(row.attempt != 1 or row.retry_of is not None for row in valid_observations):
        errors.append("smoke observations must select attempt 1 without retry")
    if any(row.status is not RunStatus.PASS for row in valid_observations):
        errors.append("every smoke runtime result must pass")
    if any(not row.state_markdown_match for row in valid_observations):
        errors.append("state, Markdown, and compact impacts disagree")
    if any(not row.workflow_boundary_passed for row in valid_observations):
        errors.append("workflow ownership boundary failed")
    for row in valid_observations:
        expected_calls = (
            0
            if row.case_id == "NEG-debugging"
            else (2 if row.case_id.startswith("LINEAGE-") else 1)
        )
        if (
            row.controller_begin_calls != expected_calls
            or row.controller_finalize_calls != expected_calls
        ):
            errors.append("controller call count or order failed")
    if any(not row.controller_draft_ids_match for row in valid_observations):
        errors.append("controller draft IDs disagree")
    if any(not row.controller_finalize_succeeded for row in valid_observations):
        errors.append("controller finalize failed")
    if any(
        not row.controller_display_text_presentation_equivalent
        or row.controller_display_comparison != "codex-markdown-v1"
        for row in valid_observations
    ):
        errors.append("controller display text differs from final output")
    if any((row.input_tokens is None) != (row.output_tokens is None) for row in valid_observations):
        errors.append("token usage must be complete or absent")
    for row in valid_observations:
        if row.case_id != "NEG-debugging" and not row.impact_ids:
            errors.append(f"{row.case_id} has no preserved impact identifiers")
        for field in (
            "prompt_bytes",
            "routed_resource_bytes",
            "routed_resource_words",
            "output_bytes",
            "output_words",
        ):
            value = getattr(row, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                errors.append(f"{row.case_id} has invalid {field}")
    median_output = _median([row.output_words for row in valid_observations])
    median_resources = _median([row.routed_resource_words for row in valid_observations])
    if median_output > MAX_MEDIAN_OUTPUT_WORDS:
        errors.append("median compact output exceeds 450 words")
    if median_resources > MAX_MEDIAN_ROUTED_RESOURCE_WORDS:
        errors.append("median routed resources do not reduce baseline by 50 percent")
    unique_errors = tuple(sorted(set(errors)))
    return SmokeGateResult(
        passed=not unique_errors,
        errors=unique_errors,
        median_output_words=median_output,
        median_routed_resource_words=median_resources,
    )


def evaluate_graph_smoke(
    observations: Sequence[GraphPerformanceObservation],
) -> GraphSmokeGateResult:
    """Gate the exact one-attempt graph smoke; token counts are informational."""
    errors = []
    keys = [(row.case_id, row.repetition) for row in observations]
    expected = {(case_id, 1) for case_id in GRAPH_SMOKE_CASE_IDS}
    if set(keys) != expected or len(observations) != len(expected):
        errors.append("graph observations do not cover the exact six cases")
    if len(set(keys)) != len(keys):
        errors.append("graph observations contain duplicate case/repetition rows")
    if any(row.attempt != 1 or row.retry_of is not None for row in observations):
        errors.append("graph observations must select attempt 1 without retry")
    if any(row.status is not RunStatus.PASS for row in observations):
        errors.append("every graph runtime result must pass")
    if any(not row.mechanical_passed for row in observations):
        errors.append("every graph mechanical score must pass")
    if any(not row.graph_passed for row in observations):
        errors.append("every graph coverage score must pass")
    if any(not row.receipt_state_provider_parity for row in observations):
        errors.append("receipt, state, and provider provenance disagree")
    if any(row.uncovered_high_risk_nodes for row in observations):
        errors.append("graph smoke contains uncovered high-risk nodes")
    for row in observations:
        expected_calls = 0 if row.case_id == GRAPH_NEGATIVE_CASE_ID else 1
        if (
            row.controller_begin_calls,
            row.controller_trace_calls,
            row.controller_finalize_calls,
        ) != (expected_calls, expected_calls, expected_calls):
            errors.append("controller graph call count or order failed")
    if any(
        not row.controller_evidence_valid or row.duplicate_or_error_calls for row in observations
    ):
        errors.append("controller graph evidence contains duplicate or error calls")

    durations = []
    for row in observations:
        if row.case_id == GRAPH_NEGATIVE_CASE_ID:
            if row.graph_duration_ms is not None:
                errors.append("negative graph case must not report graph duration")
        elif (
            isinstance(row.graph_duration_ms, bool)
            or not isinstance(row.graph_duration_ms, int)
            or row.graph_duration_ms < 0
        ):
            errors.append(f"{row.case_id} has invalid graph duration")
        else:
            durations.append(row.graph_duration_ms)
            if row.graph_duration_ms > MAX_GRAPH_DURATION_MS:
                errors.append("graph duration exceeds 30 seconds")
        for field in ("output_words", "routed_resource_words"):
            value = getattr(row, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                errors.append(f"{row.case_id} has invalid {field}")

    median_duration = _median(durations)
    median_output = _median([row.output_words for row in observations])
    median_resources = _median([row.routed_resource_words for row in observations])
    if median_duration > MAX_MEDIAN_GRAPH_DURATION_MS:
        errors.append("median graph duration exceeds 10 seconds")
    if median_output > MAX_MEDIAN_OUTPUT_WORDS:
        errors.append("median graph compact output exceeds 450 words")
    if median_resources > MAX_MEDIAN_ROUTED_RESOURCE_WORDS:
        errors.append("median graph routed guidance does not reduce baseline by 50 percent")
    unique = tuple(sorted(set(errors)))
    return GraphSmokeGateResult(
        passed=not unique,
        errors=unique,
        median_graph_duration_ms=median_duration,
        median_output_words=median_output,
        median_routed_resource_words=median_resources,
    )


def evaluate_fast_scan_gate(observations):
    errors = []
    rows = tuple(row for row in observations if isinstance(row, FastScanPerformanceObservation))
    if len(rows) != len(observations):
        errors.append("Fast Scan observations contain invalid rows")
    keys = [(row.case_id, row.repetition) for row in rows]
    expected = {(case_id, 1) for case_id in GRAPH_SMOKE_CASE_IDS}
    if set(keys) != expected or len(rows) != len(expected):
        errors.append("Fast Scan observations do not cover the exact six cases")
    if len(set(keys)) != len(keys):
        errors.append("Fast Scan observations contain duplicates")
    if any(row.attempt != 1 or row.retry_of is not None for row in rows):
        errors.append("Fast Scan observations must not retry")
    if any(row.status is not RunStatus.PASS for row in rows):
        errors.append("every Fast Scan runtime must pass")
    durations = []
    for row in rows:
        negative = row.case_id == GRAPH_NEGATIVE_CASE_ID
        expected_calls = () if negative else ("rir_scan",)
        if row.controller_calls != expected_calls:
            errors.append("Fast Scan must call only rir_scan once")
        if not row.scoring_passed or not row.exact_provenance:
            errors.append("Fast Scan scoring or provenance failed")
        if row.uncovered_high_risk_nodes:
            errors.append("Fast Scan has uncovered high-risk nodes")
        if negative:
            if row.scan_duration_ms is not None:
                errors.append("negative Fast Scan must not report duration")
        elif (
            isinstance(row.scan_duration_ms, bool)
            or not isinstance(row.scan_duration_ms, int)
            or row.scan_duration_ms < 0
        ):
            errors.append("Fast Scan duration is invalid")
        else:
            durations.append(row.scan_duration_ms)
            if row.scan_duration_ms > MAX_GRAPH_DURATION_MS:
                errors.append("Fast Scan exceeds 30 seconds")
        if row.output_words > MAX_FAST_SCAN_OUTPUT_WORDS:
            errors.append("Fast Scan output exceeds 180 words")
        if (row.input_tokens is None) != (row.output_tokens is None):
            errors.append("Fast Scan token usage must be complete or absent")
    median_duration = _median(durations)
    median_output = _median([row.output_words for row in rows])
    if median_duration > MAX_MEDIAN_GRAPH_DURATION_MS:
        errors.append("median Fast Scan duration exceeds 10 seconds")
    unique = tuple(sorted(set(errors)))
    return FastScanGateResult(not unique, unique, median_duration, median_output)
