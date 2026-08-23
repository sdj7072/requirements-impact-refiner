#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import compact_state
import impact_report


VALIDATOR_PATH = SCRIPT_DIR / "validate-impact-report.py"
VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "compact_render_validator", VALIDATOR_PATH
)
VALIDATOR = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(VALIDATOR)
GENERIC_ID_PATTERN = re.compile(r"\b(?:REQ|INV|IMP|DEC|AC)-\d{3}\b")


def _text(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("|", "&#124;")
        .replace("`", "&#96;")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "<br>")
    )


def _restore(value: str) -> str:
    return (
        value.replace("<br>", "\n")
        .replace("&#96;", "`")
        .replace("&#124;", "|")
        .replace("&amp;", "&")
    )


def _identifier(value: str) -> str:
    return f"`{value}`"


def _identifiers(values: Sequence[str]) -> str:
    return ", ".join(_identifier(value) for value in values) if values else "none"


def _table(title: str, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = [
        f"## {title}",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def _render_report_state(state):
    report = state["report"]
    return _table(
        "Report State",
        ("Report ID", "Revision", "Previous SHA-256", "Phase"),
        ((_identifier(report["id"]), str(report["revision"]), report["previous_sha256"], report["phase"]),),
    )


def _render_summary(state):
    return _table(
        "Change Impact Summary",
        ("Impact ID", "Changed feature", "Possible issue", "Affected feature or user", "Trigger", "Severity", "Prevention or check", "Status"),
        tuple(
            (
                _identifier(row["impact_id"]), _text(row["changed_feature"]),
                _text(row["possible_issue"]), _text(row["affected"]),
                _text(row["trigger"]), row["severity"],
                _text(row["prevention"]), row["status"],
            )
            for row in state["summary"]
        ),
    )


def _render_original_requirement(state):
    row = state["original_requirement"]
    return _table(
        "Original Requirement", ("Requirement ID", "Original request", "Source"),
        ((_identifier(row["id"]), _text(row["request"]), _text(row["source"])),),
    )


def _render_refined_requirement(state):
    row = state["refined_requirement"]
    decision = _identifier(row["decision"]) if row["decision"] else "—"
    return _table(
        "Current Refined Requirement",
        ("Requirement ID", "Revision", "Refined by decision", "Supersedes"),
        ((_identifier(row["id"]), _text(row["revision"]), decision, _identifiers(row["supersedes"])),),
    )


def _render_current_behavior(state):
    return _table(
        "Current Behavior", ("Invariant ID", "Current behavior", "Evidence level", "Evidence"),
        tuple((_identifier(row["id"]), _text(row["behavior"]), row["evidence_level"], _text(row["evidence"])) for row in state["current_behavior"]),
    )


def _render_preserved_invariants(state):
    return _table(
        "Preserved Invariants", ("Invariant ID", "Must preserve for requirement", "Affected impacts", "Evidence"),
        tuple((_identifier(row["id"]), _identifier(row["requirement"]), _identifiers(row["impacts"]), _text(row["evidence"])) for row in state["preserved_invariants"]),
    )


def _render_impacts(state):
    pre = state["report"]["phase"] == "pre-decision"
    rows = []
    for row in state["impacts"]:
        decision = _identifiers(row["decisions"])
        if pre and not row["decisions"]:
            decision = "the pending decision"
        rows.append((
            _identifier(row["id"]), _identifier(row["requirement"]), row["category"],
            row["severity"], row["state"], row["evidence_level"], _text(row["evidence"]),
            _identifiers(row["invariants"]), decision, _identifiers(row["criteria"]),
        ))
    return _table(
        "Impact Ledger",
        ("ID", "Requirement", "Category", "Severity", "State", "Evidence Level", "Evidence", "Invariants", "Decision", "Acceptance Criteria"),
        tuple(rows),
    )


def _render_decision(state):
    if state["report"]["phase"] == "pre-decision":
        needed = state["decision_needed"]
        return _table(
            "Decision Needed", ("Question", "Option", "Impact IDs", "Trade-off"),
            tuple((_text(needed["question"]), _text(option["option"]), _identifiers(option["impacts"]), _text(option["tradeoff"])) for option in needed["options"]),
        )
    return _table(
        "Decisions and Accepted Risks",
        ("Decision ID", "Choice", "Requirement revision", "Accepted impacts", "Rationale"),
        tuple((_identifier(row["id"]), _text(row["choice"]), _identifier(row["requirement"]), _identifiers(row["accepted_impacts"]), _text(row["rationale"])) for row in state["decisions"]),
    )


def _render_delta(state):
    return _table(
        "Impact Delta", ("Category", "Impact IDs"),
        tuple((category, _identifiers(state["delta"][category])) for category in compact_state.DELTA_CATEGORIES),
    )


def _render_history(state):
    pre = state["report"]["phase"] == "pre-decision"
    rows = []
    for row in state["history"]:
        decision = _identifier(row["decision"]) if row["decision"] else ("the pending decision" if pre else "none")
        rows.append((_identifier(row["requirement"]), _text(row["revision"]), decision, _identifiers(row["superseded_impacts"]), _text(row["summary"])))
    return _table(
        "Requirement Revision History", ("Requirement ID", "Revision", "Decision", "Superseded impacts", "Change summary"), tuple(rows)
    )


def _render_criteria(state):
    return _table(
        "Acceptance and Regression Criteria",
        ("Criterion ID", "Requirement", "Impact", "Invariant", "Observable criterion", "Evidence/test"),
        tuple((_identifier(row["id"]), _identifier(row["requirement"]), _identifier(row["impact"]), _identifier(row["invariant"]), _text(row["criterion"]), _text(row["evidence"])) for row in state["criteria"]),
    )


def _render_unresolved(state):
    return _table(
        "Unresolved, Deferred, and Blocked Items",
        ("Impact ID", "State", "Information gap or rationale", "Linked decision", "Next owner"),
        tuple((_identifier(row["impact"]), row["state"], _text(row["rationale"]), _identifier(row["decision"]) if row["decision"] else "none", _text(row["owner"])) for row in state["unresolved"]),
    )


def _render_scope(state):
    return _table(
        "Analysis Scope and Limitations",
        ("Scope or limitation", "Inspected evidence", "Consequence for confidence"),
        tuple((_text(row["boundary"]), _text(row["evidence"]), _text(row["confidence"])) for row in state["scope"]),
    )


def _render_handoff(state):
    row = state["handoff"]
    refined = _identifier(row["refined_requirement"]) if re.fullmatch(r"REQ-\d{3}", row["refined_requirement"]) else _text(row["refined_requirement"])
    return _table(
        "Planning Handoff",
        ("Refined requirement", "Report IDs", "Remaining risks", "Acceptance criteria", "Selected planning workflow"),
        ((refined, _identifiers(row["report_ids"]), _identifiers(row["remaining_risks"]), _identifiers(row["criteria"]), _text(row["workflow"])),),
    )


def render_markdown(state: Mapping[str, object]) -> str:
    errors = compact_state.validate_state(state)
    if errors:
        raise ValueError("; ".join(errors))
    sections = (
        _render_report_state, _render_summary, _render_original_requirement,
        _render_refined_requirement, _render_current_behavior,
        _render_preserved_invariants, _render_impacts, _render_decision,
        _render_delta, _render_history, _render_criteria, _render_unresolved,
        _render_scope, _render_handoff,
    )
    return "# Requirements Impact Report\n\n" + "\n\n".join(section(state) for section in sections) + "\n"


def validate_rendered_markdown(text: str) -> list[str]:
    return VALIDATOR.validate_report(text, require_summary=True)


def _artifact_path(state, suffix):
    report = state["report"]
    return f".requirements-impact-refiner/reports/{report['id']}/revision-{report['revision']:04d}.{suffix}"


def render_compact(state: Mapping[str, object]) -> str:
    errors = compact_state.validate_state(state)
    if errors:
        raise ValueError("; ".join(errors))
    lines = ["## Change Impact Summary", "", "| Impact | Possible issue | Affected | Prevention |", "| --- | --- | --- | --- |"]
    for row in state["summary"]:
        lines.append(f"| {_identifier(row['impact_id'])} | {_text(row['possible_issue'])} | {_text(row['affected'])} | {_text(row['prevention'])} |")
    remaining = [row for row in state["summary"] if row["status"] in {"accepted", "deferred", "blocked"}]
    if remaining:
        lines.extend(("", "**Remaining risks:** " + "; ".join(_text(row["possible_issue"]) for row in remaining)))
    if state["report"]["phase"] == "pre-decision":
        needed = state["decision_needed"]
        lines.extend(("", f"**Decision needed:** {_text(needed['question'])}"))
        lines.extend(f"- {_text(option['option'])}: {_text(option['tradeoff'])}" for option in needed["options"])
    else:
        choices = "; ".join(_text(row["choice"]) for row in state["decisions"])
        lines.extend(("", f"**Recorded decision:** {choices}"))
    lines.extend((
        "", f"Validation: passed · Report {_identifier(state['report']['id'])} revision {state['report']['revision']}",
        f"State: `{_artifact_path(state, 'json')}`", f"Full report: `{_artifact_path(state, 'md')}`",
    ))
    return "\n".join(lines) + "\n"


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        value = value[1:-1]
    return _restore(value)


def _ids(value: str, prefix: str | None = None) -> list[str]:
    values = GENERIC_ID_PATTERN.findall(value)
    return [value for value in values if prefix is None or value.startswith(prefix)]


def state_from_markdown(text: str) -> tuple[dict[str, object] | None, list[str]]:
    report_errors = validate_rendered_markdown(text)
    if report_errors:
        return None, report_errors
    parsed, parse_errors = impact_report.parse_report(text)
    if parse_errors or parsed.metadata is None:
        return None, parse_errors or ["report metadata is unavailable"]
    tables = parsed.tables
    metadata = parsed.metadata
    original = tables["Original Requirement"][0]
    refined = tables["Current Refined Requirement"][0]
    state = {
        "schema_version": 1,
        "report": {"id": metadata.report_id, "revision": metadata.revision, "previous_sha256": metadata.previous_sha256, "phase": metadata.phase},
        "settings": {"audience": "balanced", "audience_source": "default", "delivery": "compact", "delivery_source": "default"},
        "original_requirement": {"id": _unquote(original["Requirement ID"]), "request": _unquote(original["Original request"]), "source": _unquote(original["Source"])},
        "refined_requirement": {"id": _unquote(refined["Requirement ID"]), "revision": _unquote(refined["Revision"]), "decision": next(iter(_ids(refined["Refined by decision"], "DEC-")), None), "supersedes": _ids(refined["Supersedes"], "REQ-")},
        "current_behavior": [{"id": _unquote(row["Invariant ID"]), "behavior": _unquote(row["Current behavior"]), "evidence_level": _unquote(row["Evidence level"]), "evidence": _unquote(row["Evidence"])} for row in tables["Current Behavior"]],
        "preserved_invariants": [{"id": _unquote(row["Invariant ID"]), "requirement": _ids(row["Must preserve for requirement"], "REQ-")[0], "impacts": _ids(row["Affected impacts"], "IMP-"), "evidence": _unquote(row["Evidence"])} for row in tables["Preserved Invariants"]],
        "impacts": [{"id": _unquote(row["ID"]), "requirement": _ids(row["Requirement"], "REQ-")[0], "category": _unquote(row["Category"]), "severity": _unquote(row["Severity"]), "state": _unquote(row["State"]), "evidence_level": _unquote(row["Evidence Level"]), "evidence": _unquote(row["Evidence"]), "invariants": _ids(row["Invariants"], "INV-"), "decisions": _ids(row["Decision"], "DEC-"), "criteria": _ids(row["Acceptance Criteria"], "AC-")} for row in tables["Impact Ledger"]],
        "decisions": [], "decision_needed": None,
        "delta": {row["Category"].strip("`"): _ids(row["Impact IDs"], "IMP-") for row in tables["Impact Delta"]},
        "history": [{"requirement": _ids(row["Requirement ID"], "REQ-")[0], "revision": _unquote(row["Revision"]), "decision": next(iter(_ids(row["Decision"], "DEC-")), None), "superseded_impacts": _ids(row["Superseded impacts"], "IMP-"), "summary": _unquote(row["Change summary"])} for row in tables["Requirement Revision History"]],
        "criteria": [{"id": _unquote(row["Criterion ID"]), "requirement": _ids(row["Requirement"], "REQ-")[0], "impact": _ids(row["Impact"], "IMP-")[0], "invariant": _ids(row["Invariant"], "INV-")[0], "criterion": _unquote(row["Observable criterion"]), "evidence": _unquote(row["Evidence/test"])} for row in tables["Acceptance and Regression Criteria"]],
        "unresolved": [{"impact": _ids(row["Impact ID"], "IMP-")[0], "state": _unquote(row["State"]), "rationale": _unquote(row["Information gap or rationale"]), "decision": next(iter(_ids(row["Linked decision"], "DEC-")), None), "owner": _unquote(row["Next owner"])} for row in tables["Unresolved, Deferred, and Blocked Items"]],
        "scope": [{"boundary": _unquote(row["Scope or limitation"]), "evidence": _unquote(row["Inspected evidence"]), "confidence": _unquote(row["Consequence for confidence"])} for row in tables["Analysis Scope and Limitations"]],
        "summary": [{"impact_id": _unquote(row["Impact ID"]), "changed_feature": _unquote(row["Changed feature"]), "possible_issue": _unquote(row["Possible issue"]), "affected": _unquote(row["Affected feature or user"]), "trigger": _unquote(row["Trigger"]), "severity": _unquote(row["Severity"]), "prevention": _unquote(row["Prevention or check"]), "status": _unquote(row["Status"])} for row in tables["Change Impact Summary"]],
    }
    handoff = tables["Planning Handoff"][0]
    refined_handoff_ids = _ids(handoff["Refined requirement"], "REQ-")
    state["handoff"] = {"refined_requirement": refined_handoff_ids[0] if len(refined_handoff_ids) == 1 and _unquote(handoff["Refined requirement"]) == refined_handoff_ids[0] else _unquote(handoff["Refined requirement"]), "report_ids": _ids(handoff["Report IDs"]), "remaining_risks": _ids(handoff["Remaining risks"], "IMP-"), "criteria": _ids(handoff["Acceptance criteria"], "AC-"), "workflow": _unquote(handoff["Selected planning workflow"])}
    if metadata.phase == "pre-decision":
        rows = tables["Decision Needed"]
        state["decision_needed"] = {"question": _unquote(rows[0]["Question"]), "options": [{"option": _unquote(row["Option"]), "impacts": _ids(row["Impact IDs"], "IMP-"), "tradeoff": _unquote(row["Trade-off"])} for row in rows]}
    else:
        state["decisions"] = [{"id": _unquote(row["Decision ID"]), "choice": _unquote(row["Choice"]), "requirement": _ids(row["Requirement revision"], "REQ-")[0], "accepted_impacts": _ids(row["Accepted impacts"], "IMP-"), "rationale": _unquote(row["Rationale"])} for row in tables["Decisions and Accepted Risks"]]
    state_errors = compact_state.validate_state(state)
    return (None, state_errors) if state_errors else (state, [])
