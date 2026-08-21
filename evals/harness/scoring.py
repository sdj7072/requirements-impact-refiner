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
_AFTER_BRAINSTORMING = re.compile(
    r"\bafter\s+(?:the\s+)?approved\s+brainstorming\b", re.IGNORECASE
)
_BEFORE_WRITING_PLANS = re.compile(r"\bbefore\s+(?:the\s+)?writing-plans\b", re.IGNORECASE)
_AUTOMATIC_WRITING_PLANS = re.compile(
    r"\b(?:automatically|automated|auto(?:matically)?)\b.{0,80}\bwriting-plans\b"
    r"|\bwriting-plans\b.{0,80}\b(?:automatically|automated|auto(?:matically)?)\b",
    re.IGNORECASE | re.DOTALL,
)
_RESOLVED_STATE = re.compile(r"\|\s*[^|]+\|[^\n]*\|\s*resolved\s*\|", re.IGNORECASE)


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


def _complete_report_errors(
    output: str,
    previous_output: Optional[str],
    previous_bytes: Optional[bytes],
) -> List[str]:
    """Delegate complete report validation to the canonical implementation."""
    if previous_output is None:
        return list(_VALIDATOR.validate_report(output))
    predecessor = previous_bytes
    if predecessor is None:
        predecessor = previous_output.encode("utf-8")
    return list(
        _VALIDATOR.validate_report(
            output, previous_text=previous_output, previous_bytes=predecessor
        )
    )


def _has_report_shape(output: str) -> bool:
    return bool(re.search(r"(?m)^#\s+Requirements Impact Report\s*$", output))


def _lineage_findings(case: CaseSpec, output: str) -> List[str]:
    """Check the catalog's transition claim without making a human judgment."""
    transition = case.expected_transition
    if transition == "rejected":
        if _RESOLVED_STATE.search(output):
            return ["%s requires resolution rejection" % case.id]
        return []
    if transition in {"unchanged", "reopened"}:
        parsed, parse_errors = _VALIDATOR.parse_report(output)
        if parse_errors:
            return []
        authored = _VALIDATOR.authored_delta(parsed)
        if not authored.get(transition):
            return ["%s requires %s Impact Delta transition" % (case.id, transition)]
    return []


def score_mechanical(
    case: CaseSpec,
    result: RunResult,
    previous_output: Optional[str] = None,
    previous_bytes: Optional[bytes] = None,
) -> MechanicalScore:
    """Return a deterministic score for one recorded result.

    ``previous_output`` and ``previous_bytes`` are supplied for the second
    lineage turn when available.  They are intentionally optional so a raw
    result remains scoreable while still failing a missing lineage contract.
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
        findings.extend(_complete_report_errors(output, previous_output, previous_bytes))

    if case.id == "INT-superpowers":
        if not _AFTER_BRAINSTORMING.search(output):
            findings.append("INT-superpowers requires entry after approved brainstorming")
        if not _BEFORE_WRITING_PLANS.search(output):
            findings.append("INT-superpowers requires exit before writing-plans")
        if _AUTOMATIC_WRITING_PLANS.search(output):
            findings.append("INT-superpowers forbids automatic writing-plans")

    if case.kind == "lineage":
        findings.extend(_lineage_findings(case, output))

    return MechanicalScore(case.id, result.repetition, not findings, tuple(findings))


def validate_adjudications(rows: Sequence[Adjudication]) -> List[str]:
    """Require an exact transcript quote and rationale for every human rubric."""
    errors: List[str] = []
    for row in rows:
        if not row.quote.strip() or not row.rationale.strip():
            errors.append(
                "%s/%02d %s requires quote and rationale"
                % (row.case_id, row.repetition, row.rubric)
            )
    return errors
