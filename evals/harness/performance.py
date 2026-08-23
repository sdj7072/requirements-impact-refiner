"""Deterministic compact-delivery performance observations and smoke gate."""

from dataclasses import dataclass
from statistics import median
from typing import Optional, Sequence, Tuple

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
    impact_ids: Tuple[str, ...]
    state_markdown_match: bool
    workflow_boundary_passed: bool


@dataclass(frozen=True)
class SmokeGateResult:
    passed: bool
    errors: Tuple[str, ...]
    median_output_words: float
    median_routed_resource_words: float


def _median(values: Sequence[int]) -> float:
    return float(median(values)) if values else 0.0


def evaluate_smoke_gate(
    observations: Sequence[PerformanceObservation],
) -> SmokeGateResult:
    errors = []
    keys = [(row.case_id, row.repetition) for row in observations]
    expected = {(case_id, 1) for case_id in SMOKE_CASE_IDS}
    if set(keys) != expected or len(observations) != len(expected):
        errors.append("smoke observations do not cover the exact six cases")
    if len(set(keys)) != len(keys):
        errors.append("smoke observations contain duplicate case/repetition rows")
    if any(row.attempt != 1 or row.retry_of is not None for row in observations):
        errors.append("smoke observations must select attempt 1 without retry")
    if any(row.status is not RunStatus.PASS for row in observations):
        errors.append("every smoke runtime result must pass")
    if any(not row.state_markdown_match for row in observations):
        errors.append("state, Markdown, and compact impacts disagree")
    if any(not row.workflow_boundary_passed for row in observations):
        errors.append("workflow ownership boundary failed")
    if any(
        (row.input_tokens is None) != (row.output_tokens is None)
        for row in observations
    ):
        errors.append("token usage must be complete or absent")
    for row in observations:
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
    median_output = _median([row.output_words for row in observations])
    median_resources = _median(
        [row.routed_resource_words for row in observations]
    )
    if median_output > MAX_MEDIAN_OUTPUT_WORDS:
        errors.append("median compact output exceeds 450 words")
    if median_resources > MAX_MEDIAN_ROUTED_RESOURCE_WORDS:
        errors.append(
            "median routed resources do not reduce baseline by 50 percent"
        )
    unique_errors = tuple(sorted(set(errors)))
    return SmokeGateResult(
        passed=not unique_errors,
        errors=unique_errors,
        median_output_words=median_output,
        median_routed_resource_words=median_resources,
    )
