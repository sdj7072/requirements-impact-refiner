"""Bounded public summaries for installed-plugin evaluation evidence."""

from typing import Dict, Mapping, Optional, Sequence

from .catalog import load_all, select_suite
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


def _environment_values(run: RunResult) -> tuple[str, ...]:
    return tuple(value for key, value in run.metadata if key == "environment")


def _verification_errors(
    results: Sequence[RunResult],
    scores: Optional[Sequence[MechanicalScore]],
    adjudications: Sequence[Adjudication],
) -> list[str]:
    """Require the sealed canonical matrix, never a caller-supplied summary."""
    cases = select_suite(load_all(), "installed-superpowers")
    expected_runs = {
        (case.id, repetition) for case in cases for repetition in range(1, 6)
    }
    errors = []
    actual_runs = [(run.case_id, run.repetition) for run in results]
    if len(results) != len(expected_runs) or set(actual_runs) != expected_runs:
        errors.append("runs are not the canonical 17-case by 5-repetition matrix")
    if len(set(actual_runs)) != len(actual_runs):
        errors.append("runs contain duplicate case/repetition finals")
    if any(run.status is not RunStatus.PASS for run in results):
        errors.append("every sealed final must have pass status")
    if any(run.client != "codex" for run in results):
        errors.append("runs are not all Codex finals")
    if any(_environment_values(run) != ("Codex with Superpowers",) for run in results):
        errors.append("runs are not all Codex with Superpowers finals")

    if scores is None:
        errors.append("mechanical scores are required")
    else:
        score_keys = [(score.case_id, score.repetition) for score in scores]
        if len(scores) != len(expected_runs) or set(score_keys) != expected_runs:
            errors.append("mechanical scores do not cover the canonical matrix")
        if len(set(score_keys)) != len(score_keys):
            errors.append("mechanical scores contain duplicate case/repetition rows")
        if any(score.passed is not True for score in scores):
            errors.append("every mechanical score must pass")

    adjudication_errors = validate_adjudications(adjudications, cases, results)
    if adjudication_errors:
        errors.append("adjudications are incomplete or untraceable")
    if any(row.passed is not True for row in adjudications):
        errors.append("every adjudication must pass")
    return errors


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
    summary = summarize(results, scores)
    verification_errors = _verification_errors(results, scores, adjudications)
    status = "verified" if not verification_errors else "not verified"
    actual_clients = sorted({run.client for run in results})
    actual_compositions = sorted(
        {value for run in results for value in _environment_values(run)}
    )
    rendered_client = actual_clients[0] if len(actual_clients) == 1 else "mixed"
    rendered_composition = (
        actual_compositions[0] if len(actual_compositions) == 1 else "mixed"
    )
    lines = (
        "# Installed Plugin Evaluation",
        "",
        "- status: %s" % status,
        "- client: %s" % rendered_client,
        "- version: %s" % required["version"],
        "- enabled composition: %s" % rendered_composition,
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
        "- verification blockers: %d" % len(verification_errors),
    )
    return "\n".join(lines) + "\n"
