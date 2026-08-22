"""Deterministic checks for recorded evaluation outputs.

This module deliberately scores only contracts that can be established from a
recorded run.  Whether a response discovered a meaningful impact remains an
``Adjudication`` decision and is never inferred here.
"""

import importlib.util
import re
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .models import Adjudication, CaseSpec, MechanicalScore, RunResult, RunStatus


_REFINEMENT_ID = re.compile(r"\b(?:RPT|REQ|IMP|INV|DEC|AC)-\d{3}\b")
_REPORT_WORKFLOW = re.compile(
    r"(?:^|\n)\s*#{1,6}\s+(?:requirements impact report|impact ledger|planning handoff)\b"
    r"|\b(?:begin|start|activate|perform)\s+(?:the\s+)?impact refinement\b",
    re.IGNORECASE,
)
_REJECTION_ACTIVE_STATES = frozenset(("detected", "refining", "blocked"))


def _load_validator():
    """Load the checked-in canonical validator without copying its behavior."""
    validator_path = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "requirements-impact-refiner"
        / "scripts"
        / "validate-impact-report.py"
    )
    spec = importlib.util.spec_from_file_location("_harness_impact_report", validator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("canonical impact report validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


_VALIDATOR = _load_validator()
_REPORT_MODEL = sys.modules.get("impact_report")
if _REPORT_MODEL is None:
    raise RuntimeError("canonical impact report model is unavailable")


def _complete_report_errors(
    output: str,
    previous_bytes: Optional[bytes],
) -> List[str]:
    """Delegate complete report validation to the canonical implementation."""
    if previous_bytes is None:
        return list(_VALIDATOR.validate_report(output))
    try:
        previous_output = previous_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return ["lineage predecessor is not valid UTF-8"]
    return list(
        _VALIDATOR.validate_report(
            output, previous_text=previous_output, previous_bytes=previous_bytes
        )
    )


def _has_report_shape(output: str) -> bool:
    return bool(re.search(r"(?m)^#\s+Requirements Impact Report\s*$", output))


def _planning_handoff_workflow(output: str) -> Optional[str]:
    """Read the exact canonical Planning Handoff workflow cell."""
    parsed, parse_errors = _VALIDATOR.parse_report(output)
    if parse_errors:
        return None
    rows = parsed.tables.get("Planning Handoff", ())
    if len(rows) != 1:
        return None
    return _REPORT_MODEL.unquote(rows[0].get("Selected planning workflow", ""))


def _lineage_findings(case: CaseSpec, output: str) -> List[str]:
    """Check the catalog's transition claim without making a human judgment."""
    transition = case.expected_transition
    if transition == "rejected":
        parsed, parse_errors = _VALIDATOR.parse_report(output)
        if parse_errors:
            return []
        states = {
            _VALIDATOR.enum_value(row.get("State", ""))
            for row in parsed.tables.get("Impact Ledger", ())
        }
        findings = []
        if not states or not states <= _REJECTION_ACTIVE_STATES:
            findings.append("%s requires an active evidence-supported ledger state" % case.id)
        authored = _REPORT_MODEL.authored_delta(parsed)
        if authored.get("resolved") or authored.get("accepted"):
            findings.append("%s forbids resolved or accepted Impact Delta" % case.id)
        return findings
    if transition in {"unchanged", "reopened"}:
        parsed, parse_errors = _VALIDATOR.parse_report(output)
        if parse_errors:
            return []
        authored = _REPORT_MODEL.authored_delta(parsed)
        if not authored.get(transition):
            return ["%s requires %s Impact Delta transition" % (case.id, transition)]
    return []


def score_mechanical(
    case: CaseSpec,
    result: RunResult,
    previous_bytes: Optional[bytes] = None,
) -> MechanicalScore:
    """Return a deterministic score for one recorded result.

    ``previous_bytes`` must be the exact immutable first-turn artifact for a
    lineage second turn.  It remains optional so an incomplete raw result can
    still be scored as a mechanical failure.  The ``INT-superpowers`` boundary
    is mechanical only when expressed as the exact structured Planning Handoff
    workflow marker; semantic prose remains quoted human adjudication.
    """
    findings: List[str] = []
    if result.case_id != case.id:
        findings.append("result case ID does not match case")
    if result.status is not RunStatus.PASS:
        findings.append("run status %s is not pass" % result.status.value)
        return MechanicalScore(case.id, result.repetition, False, tuple(findings))

    output = result.final_output or ""
    if not output.strip():
        findings.append("missing final output")
        return MechanicalScore(case.id, result.repetition, False, tuple(findings))

    if case.kind == "negative":
        if _REFINEMENT_ID.search(output) or _REPORT_WORKFLOW.search(output):
            findings.append("negative case activated refinement identifiers or workflow")
        return MechanicalScore(case.id, result.repetition, not findings, tuple(findings))

    requires_report = case.kind in {"positive", "lineage"}
    if requires_report and not _has_report_shape(output):
        findings.append("missing complete Requirements Impact Report")
    elif _has_report_shape(output):
        findings.extend(_complete_report_errors(output, previous_bytes))

    if case.id == "INT-superpowers":
        if (
            _planning_handoff_workflow(output)
            != _REPORT_MODEL.SUPERPOWERS_HANDOFF_MARKER
        ):
            findings.append(
                "INT-superpowers requires the exact structured Planning Handoff marker"
            )
    if case.kind == "lineage":
        findings.extend(_lineage_findings(case, output))

    return MechanicalScore(case.id, result.repetition, not findings, tuple(findings))


def validate_adjudications(
    rows: Sequence[Adjudication],
    cases: Optional[Sequence[CaseSpec]] = None,
    runs: Optional[Sequence[RunResult]] = None,
) -> List[str]:
    """Validate human judgments against the exact catalog and sealed transcript.

    Without the optional catalog/run index this retains the narrow local check
    used by callers that only need quote/rationale completeness.  Passing both
    enables full, one-row-per-rubric transcript validation.
    """
    errors: List[str] = []
    for row in rows:
        if not isinstance(row.passed, bool):
            errors.append(
                "%s/%02d %s passed must be boolean"
                % (row.case_id, row.repetition, row.rubric)
            )
        if (
            not isinstance(row.quote, str)
            or not row.quote.strip()
            or not isinstance(row.rationale, str)
            or not row.rationale.strip()
        ):
            errors.append(
                "%s/%02d %s requires quote and rationale"
                % (row.case_id, row.repetition, row.rubric)
            )
    if cases is None and runs is None:
        return errors
    if cases is None or runs is None:
        return errors + ["adjudication validation requires both cases and runs"]

    expected = {
        (case.id, repetition, rubric)
        for case in cases
        for repetition in range(1, 6)
        for rubric in case.must_detect
    }
    run_index = {}
    for run in runs:
        key = (run.case_id, run.repetition)
        if key in run_index:
            errors.append("duplicate sealed run %s/%02d" % key)
        else:
            run_index[key] = run

    seen = set()
    for row in rows:
        key = (row.case_id, row.repetition, row.rubric)
        label = "%s/%02d %s" % key
        if key not in expected:
            errors.append("unknown adjudication %s" % label)
            continue
        if key in seen:
            errors.append("duplicate adjudication %s" % label)
            continue
        seen.add(key)
        run = run_index.get((row.case_id, row.repetition))
        if run is None:
            errors.append("%s has no sealed run" % label)
        elif isinstance(row.quote, str) and row.quote.strip() not in (run.final_output or ""):
            errors.append("%s quote is not in sealed final output" % label)
    errors.extend(
        "missing adjudication %s/%02d %s" % key
        for key in sorted(expected - seen)
    )
    return errors
