"""Bounded public summaries for installed-plugin evaluation evidence."""

from typing import Dict, Mapping, Optional, Sequence

from .models import Adjudication, MechanicalScore, RunResult, RunStatus
from .scoring import validate_adjudications


_STATUS_KEYS = tuple(status.value for status in RunStatus)
_REQUIRED_METADATA = (
    "client",
    "version",
    "enabled_composition",
    "model",
    "reasoning",
    "repetitions",
)


def summarize(
    results: Sequence[RunResult], scores: Optional[Sequence[MechanicalScore]] = None
) -> Dict[str, int]:
    """Count every outcome, treating only strict pass as a pass.

    When scores are provided, a run counts as a strict pass only when both the
    adapter result and its corresponding mechanical score pass.  Human
    adjudications are deliberately not accepted here.
    """
    summary = {key: 0 for key in _STATUS_KEYS}
    summary["total"] = len(results)
    score_by_key = {}
    if scores is not None:
        score_by_key = {(score.case_id, score.repetition): score for score in scores}

    strict_passes = 0
    for result in results:
        summary[result.status.value] += 1
        if result.status is RunStatus.PASS:
            score = score_by_key.get((result.case_id, result.repetition))
            if scores is None or (score is not None and score.passed):
                strict_passes += 1
    summary["strict_passes"] = strict_passes
    summary["mechanical_failed"] = sum(
        1 for score in score_by_key.values() if not score.passed
    )
    return summary


def _metadata_value(metadata: Mapping[str, object], key: str) -> object:
    if key == "enabled_composition":
        for alias in ("enabled_composition", "composition", "environment"):
            value = metadata.get(alias)
            if value is not None:
                return value
        return None
    return metadata.get(key)


def _require_metadata(metadata: Mapping[str, object]) -> Dict[str, object]:
    values = {}
    for key in _REQUIRED_METADATA:
        value = _metadata_value(metadata, key)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("report metadata requires %s" % key)
        values[key] = value
    repetitions = values["repetitions"]
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("report metadata repetitions must be a positive integer")
    return values


def _verification_status(metadata: Mapping[str, object], summary: Mapping[str, int]) -> str:
    if (
        metadata["client"] == "codex"
        and metadata["enabled_composition"] == "Codex with Superpowers"
        and metadata["repetitions"] == 5
        and summary["total"] == 85
        and summary["strict_passes"] == 85
    ):
        return "verified"
    return "not verified"


def render_report(
    results: Sequence[RunResult],
    metadata: Mapping[str, object],
    scores: Optional[Sequence[MechanicalScore]] = None,
    adjudications: Sequence[Adjudication] = (),
) -> str:
    """Render a bounded Markdown report without promoting other environments.

    Claude behavior and all Codex modes other than the exact installed
    Superpowers composition remain ``not verified`` regardless of their score.
    """
    required = _require_metadata(metadata)
    adjudication_errors = validate_adjudications(adjudications)
    if adjudication_errors:
        raise ValueError("incomplete adjudications: %s" % "; ".join(adjudication_errors))
    summary = summarize(results, scores)
    status = _verification_status(required, summary)
    lines = (
        "# Installed Plugin Evaluation",
        "",
        "- status: %s" % status,
        "- client: %s" % required["client"],
        "- version: %s" % required["version"],
        "- enabled composition: %s" % required["enabled_composition"],
        "- model: %s" % required["model"],
        "- reasoning: %s" % required["reasoning"],
        "- repetitions: %s" % required["repetitions"],
        "- strict score: %d/%d" % (summary["strict_passes"], summary["total"]),
        "- pass: %d" % summary[RunStatus.PASS.value],
        "- partial: %d" % summary[RunStatus.PARTIAL.value],
        "- fail: %d" % summary[RunStatus.FAIL.value],
        "- blocked: %d" % summary[RunStatus.BLOCKED.value],
        "- infra_error: %d" % summary[RunStatus.INFRA_ERROR.value],
        "- invalid_evidence: %d" % summary[RunStatus.INVALID_EVIDENCE.value],
        "- mechanical failures: %d" % summary["mechanical_failed"],
        "- adjudications: %d" % len(adjudications),
    )
    return "\n".join(lines) + "\n"
