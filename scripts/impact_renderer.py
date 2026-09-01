#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import compact_state
import impact_report

VALIDATOR_PATH = SCRIPT_DIR / "validate-impact-report.py"
VALIDATOR_SPEC = importlib.util.spec_from_file_location("compact_render_validator", VALIDATOR_PATH)
assert VALIDATOR_SPEC is not None and VALIDATOR_SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(VALIDATOR)
GENERIC_ID_PATTERN = re.compile(r"\b(?:REQ|INV|IMP|DEC|AC)-\d{3}\b")
COMPACT_WORD_LIMIT = 450
COMPACT_SUMMARY_ROWS = 6
COMPACT_FIELD_WORDS = 8
KOREAN_TEXT = re.compile(r"[\u3131-\u318e\uac00-\ud7a3]")

READER_LABELS = {
    "en": {
        "title": "Requirements Impact Report",
        "report_state": "Report State",
        "summary": "Change Impact Summary",
        "impact": "Impact",
        "original_requirement": "Original Requirement",
        "refined_requirement": "Current Refined Requirement",
        "current_behavior": "Current Behavior",
        "invariant": "Invariant",
        "preserved_invariants": "Preserved Invariants",
        "preserved_invariant": "Preserved invariant",
        "impact_ledger": "Impact Ledger",
        "impact_detail": "Impact detail",
        "decision_needed": "Decision Needed",
        "option": "Option",
        "decisions": "Decisions and Accepted Risks",
        "decision": "Decision",
        "impact_delta": "Impact Delta",
        "history": "Requirement Revision History",
        "history_item": "Requirement",
        "criteria": "Acceptance and Regression Criteria",
        "criterion_item": "Criterion",
        "unresolved": "Unresolved, Deferred, and Blocked Items",
        "unresolved_item": "Unresolved impact",
        "scope": "Analysis Scope and Limitations",
        "scope_item": "Scope",
        "handoff": "Planning Handoff",
        "none": "none",
        "id": "ID",
        "revision": "Revision",
        "previous_sha256": "Previous SHA-256",
        "phase": "Phase",
        "changed_feature": "Changed feature",
        "possible_issue": "Possible issue",
        "affected": "Affected feature or user",
        "trigger": "Trigger",
        "severity": "Severity",
        "prevention": "Prevention or check",
        "status": "Status",
        "request": "Original request",
        "source": "Source",
        "decision_id": "Refined by decision",
        "supersedes": "Supersedes",
        "behavior": "Current behavior",
        "evidence_level": "Evidence level",
        "evidence": "Evidence",
        "requirement": "Requirement",
        "impacts": "Affected impacts",
        "category": "Category",
        "state": "State",
        "invariants": "Invariants",
        "decision_ids": "Decision",
        "criterion_ids": "Acceptance criteria",
        "question": "Question",
        "option_text": "Option",
        "tradeoff": "Trade-off",
        "choice": "Choice",
        "accepted_impacts": "Accepted impacts",
        "rationale": "Rationale",
        "superseded_impacts": "Superseded impacts",
        "change_summary": "Change summary",
        "impact_id": "Impact",
        "invariant_id": "Invariant",
        "criterion": "Observable criterion",
        "linked_decision": "Linked decision",
        "owner": "Next owner",
        "boundary": "Scope or limitation",
        "confidence": "Consequence for confidence",
        "refined_requirement_id": "Refined requirement",
        "report_ids": "Report IDs",
        "remaining_risks": "Remaining risks",
        "workflow": "Selected planning workflow",
    },
    "ko": {
        "title": "요구사항 영향 보고서",
        "report_state": "보고서 상태",
        "summary": "변경 영향 요약",
        "impact": "영향",
        "original_requirement": "원래 요구사항",
        "refined_requirement": "현재 정제된 요구사항",
        "current_behavior": "현재 동작",
        "invariant": "불변 조건",
        "preserved_invariants": "보존할 불변 조건",
        "preserved_invariant": "보존 조건",
        "impact_ledger": "영향 원장",
        "impact_detail": "상세 영향",
        "decision_needed": "필요한 결정",
        "option": "선택지",
        "decisions": "결정과 수용한 위험",
        "decision": "결정",
        "impact_delta": "영향 변경분",
        "history": "요구사항 변경 이력",
        "history_item": "요구사항",
        "criteria": "수용 및 회귀 기준",
        "criterion_item": "수용 기준",
        "unresolved": "미해결·보류·차단 항목",
        "unresolved_item": "미해결 영향",
        "scope": "분석 범위와 한계",
        "scope_item": "범위",
        "handoff": "계획 인계",
        "none": "없음",
        "id": "ID",
        "revision": "개정",
        "previous_sha256": "이전 SHA-256",
        "phase": "단계",
        "changed_feature": "변경 기능",
        "possible_issue": "발생 가능한 문제",
        "affected": "영향받는 기능 또는 사용자",
        "trigger": "발생 조건",
        "severity": "심각도",
        "prevention": "예방 또는 확인",
        "status": "상태",
        "request": "원래 요청",
        "source": "출처",
        "decision_id": "정제 결정",
        "supersedes": "대체 대상",
        "behavior": "현재 동작",
        "evidence_level": "근거 수준",
        "evidence": "근거",
        "requirement": "요구사항",
        "impacts": "영향 항목",
        "category": "범주",
        "state": "상태",
        "invariants": "불변 조건",
        "decision_ids": "결정",
        "criterion_ids": "수용 기준",
        "question": "질문",
        "option_text": "선택",
        "tradeoff": "절충점",
        "choice": "선택",
        "accepted_impacts": "수용한 영향",
        "rationale": "근거",
        "superseded_impacts": "대체된 영향",
        "change_summary": "변경 요약",
        "impact_id": "영향",
        "invariant_id": "불변 조건",
        "criterion": "관찰 가능한 기준",
        "linked_decision": "연결된 결정",
        "owner": "다음 담당자",
        "boundary": "범위 또는 한계",
        "confidence": "신뢰도 결과",
        "refined_requirement_id": "정제된 요구사항",
        "report_ids": "보고서 ID",
        "remaining_risks": "남은 위험",
        "workflow": "선택한 계획 절차",
    },
}


def _text(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
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
        .replace("&lt;", "<")
        .replace("&gt;", ">")
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


def _render_report_state(state: compact_state.State) -> str:
    report = state["report"]
    return _table(
        "Report State",
        ("Report ID", "Revision", "Previous SHA-256", "Phase"),
        (
            (
                _identifier(report["id"]),
                str(report["revision"]),
                report["previous_sha256"],
                report["phase"],
            ),
        ),
    )


def _render_summary(state: compact_state.State) -> str:
    return _table(
        "Change Impact Summary",
        (
            "Impact ID",
            "Changed feature",
            "Possible issue",
            "Affected feature or user",
            "Trigger",
            "Severity",
            "Prevention or check",
            "Status",
        ),
        tuple(
            (
                _identifier(row["impact_id"]),
                _text(row["changed_feature"]),
                _text(row["possible_issue"]),
                _text(row["affected"]),
                _text(row["trigger"]),
                row["severity"],
                _text(row["prevention"]),
                row["status"],
            )
            for row in state["summary"]
        ),
    )


def _render_original_requirement(state: compact_state.State) -> str:
    row = state["original_requirement"]
    return _table(
        "Original Requirement",
        ("Requirement ID", "Original request", "Source"),
        ((_identifier(row["id"]), _text(row["request"]), _text(row["source"])),),
    )


def _render_refined_requirement(state: compact_state.State) -> str:
    row = state["refined_requirement"]
    decision = _identifier(row["decision"]) if row["decision"] else "—"
    return _table(
        "Current Refined Requirement",
        ("Requirement ID", "Revision", "Refined by decision", "Supersedes"),
        (
            (
                _identifier(row["id"]),
                _text(row["revision"]),
                decision,
                _identifiers(row["supersedes"]),
            ),
        ),
    )


def _render_current_behavior(state: compact_state.State) -> str:
    return _table(
        "Current Behavior",
        ("Invariant ID", "Current behavior", "Evidence level", "Evidence"),
        tuple(
            (
                _identifier(row["id"]),
                _text(row["behavior"]),
                row["evidence_level"],
                _text(row["evidence"]),
            )
            for row in state["current_behavior"]
        ),
    )


def _render_preserved_invariants(state: compact_state.State) -> str:
    return _table(
        "Preserved Invariants",
        ("Invariant ID", "Must preserve for requirement", "Affected impacts", "Evidence"),
        tuple(
            (
                _identifier(row["id"]),
                _identifier(row["requirement"]),
                _identifiers(row["impacts"]),
                _text(row["evidence"]),
            )
            for row in state["preserved_invariants"]
        ),
    )


def _render_impacts(state: compact_state.State) -> str:
    pre = state["report"]["phase"] == "pre-decision"
    rows = []
    for row in state["impacts"]:
        decision = _identifiers(row["decisions"])
        if pre and not row["decisions"]:
            decision = "the pending decision"
        rows.append(
            (
                _identifier(row["id"]),
                _identifier(row["requirement"]),
                row["category"],
                row["severity"],
                row["state"],
                row["evidence_level"],
                _text(row["evidence"]),
                _identifiers(row["invariants"]),
                decision,
                _identifiers(row["criteria"]),
            )
        )
    return _table(
        "Impact Ledger",
        (
            "ID",
            "Requirement",
            "Category",
            "Severity",
            "State",
            "Evidence Level",
            "Evidence",
            "Invariants",
            "Decision",
            "Acceptance Criteria",
        ),
        tuple(rows),
    )


def _render_decision(state: compact_state.State) -> str:
    if state["report"]["phase"] == "pre-decision":
        needed = state["decision_needed"]
        assert needed is not None
        return _table(
            "Decision Needed",
            ("Question", "Option", "Impact IDs", "Trade-off"),
            tuple(
                (
                    _text(needed["question"]),
                    _text(option["option"]),
                    _identifiers(option["impacts"]),
                    _text(option["tradeoff"]),
                )
                for option in needed["options"]
            ),
        )
    return _table(
        "Decisions and Accepted Risks",
        ("Decision ID", "Choice", "Requirement revision", "Accepted impacts", "Rationale"),
        tuple(
            (
                _identifier(row["id"]),
                _text(row["choice"]),
                _identifier(row["requirement"]),
                _identifiers(row["accepted_impacts"]),
                _text(row["rationale"]),
            )
            for row in state["decisions"]
        ),
    )


def _render_delta(state: compact_state.State) -> str:
    return _table(
        "Impact Delta",
        ("Category", "Impact IDs"),
        tuple(
            (category, _identifiers(state["delta"][category]))
            for category in compact_state.DELTA_CATEGORIES
        ),
    )


def _render_history(state: compact_state.State) -> str:
    pre = state["report"]["phase"] == "pre-decision"
    rows = []
    for row in state["history"]:
        decision = (
            _identifier(row["decision"])
            if row["decision"]
            else ("the pending decision" if pre else "none")
        )
        rows.append(
            (
                _identifier(row["requirement"]),
                _text(row["revision"]),
                decision,
                _identifiers(row["superseded_impacts"]),
                _text(row["summary"]),
            )
        )
    return _table(
        "Requirement Revision History",
        ("Requirement ID", "Revision", "Decision", "Superseded impacts", "Change summary"),
        tuple(rows),
    )


def _render_criteria(state: compact_state.State) -> str:
    return _table(
        "Acceptance and Regression Criteria",
        (
            "Criterion ID",
            "Requirement",
            "Impact",
            "Invariant",
            "Observable criterion",
            "Evidence/test",
        ),
        tuple(
            (
                _identifier(row["id"]),
                _identifier(row["requirement"]),
                _identifier(row["impact"]),
                _identifier(row["invariant"]),
                _text(row["criterion"]),
                _text(row["evidence"]),
            )
            for row in state["criteria"]
        ),
    )


def _render_unresolved(state: compact_state.State) -> str:
    return _table(
        "Unresolved, Deferred, and Blocked Items",
        ("Impact ID", "State", "Information gap or rationale", "Linked decision", "Next owner"),
        tuple(
            (
                _identifier(row["impact"]),
                row["state"],
                _text(row["rationale"]),
                _identifier(row["decision"]) if row["decision"] else "none",
                _text(row["owner"]),
            )
            for row in state["unresolved"]
        ),
    )


def _render_scope(state: compact_state.State) -> str:
    return _table(
        "Analysis Scope and Limitations",
        ("Scope or limitation", "Inspected evidence", "Consequence for confidence"),
        tuple(
            (_text(row["boundary"]), _text(row["evidence"]), _text(row["confidence"]))
            for row in state["scope"]
        ),
    )


def _render_handoff(state: compact_state.State) -> str:
    row = state["handoff"]
    refined = (
        _identifier(row["refined_requirement"])
        if re.fullmatch(r"REQ-\d{3}", row["refined_requirement"])
        else _text(row["refined_requirement"])
    )
    return _table(
        "Planning Handoff",
        (
            "Refined requirement",
            "Report IDs",
            "Remaining risks",
            "Acceptance criteria",
            "Selected planning workflow",
        ),
        (
            (
                refined,
                _identifiers(row["report_ids"]),
                _identifiers(row["remaining_risks"]),
                _identifiers(row["criteria"]),
                _text(row["workflow"]),
            ),
        ),
    )


def _reader_label(locale: str, key: str) -> str:
    labels = READER_LABELS.get(locale, READER_LABELS["en"])
    return labels.get(key, READER_LABELS["en"].get(key, key))


def _reader_value(value: object, locale: str) -> str:
    if value is None or value == "" or value == []:
        return _reader_label(locale, "none")
    if isinstance(value, list):
        return ", ".join(_text(item) for item in value)
    return _text(value)


def _reader_fields(
    lines: list[str],
    row: Mapping[str, object],
    fields: Sequence[tuple[str, str]],
    locale: str,
) -> None:
    for field, label in fields:
        lines.append(f"- {_reader_label(locale, label)}: {_reader_value(row[field], locale)}")


def _reader_section(lines: list[str], locale: str, key: str) -> None:
    lines.extend((f"## {_reader_label(locale, key)}", ""))


def _reader_heading(lines: list[str], locale: str, key: str, value: object) -> None:
    lines.extend((f"### {_reader_label(locale, key)} {_reader_value(value, locale)}", ""))


def _reader_locale(state: compact_state.State, locale: str | None) -> str:
    if locale in READER_LABELS:
        return cast(str, locale)
    if locale is not None:
        return "en"
    request = state["original_requirement"]["request"]
    return "ko" if KOREAN_TEXT.search(request) else "en"


def render_reader_view(state: Mapping[str, object], locale: str | None = None) -> str:
    errors = compact_state.validate_state(state)
    if errors:
        raise ValueError("; ".join(errors))
    typed_state = cast(
        compact_state.State, state
    )  # compact_state.validate_state proves the complete State shape.
    locale = _reader_locale(typed_state, locale)
    lines = [f"# {_reader_label(locale, 'title')}", ""]

    _reader_section(lines, locale, "report_state")
    _reader_fields(
        lines,
        typed_state["report"],
        (
            ("id", "id"),
            ("revision", "revision"),
            ("previous_sha256", "previous_sha256"),
            ("phase", "phase"),
        ),
        locale,
    )
    lines.append("")

    _reader_section(lines, locale, "summary")
    for summary_row in typed_state["summary"]:
        _reader_heading(lines, locale, "impact", summary_row["impact_id"])
        _reader_fields(
            lines,
            summary_row,
            (
                ("changed_feature", "changed_feature"),
                ("possible_issue", "possible_issue"),
                ("affected", "affected"),
                ("trigger", "trigger"),
                ("severity", "severity"),
                ("prevention", "prevention"),
                ("status", "status"),
            ),
            locale,
        )
        lines.append("")

    _reader_section(lines, locale, "original_requirement")
    _reader_fields(
        lines,
        typed_state["original_requirement"],
        (("id", "id"), ("request", "request"), ("source", "source")),
        locale,
    )
    lines.append("")

    _reader_section(lines, locale, "refined_requirement")
    _reader_fields(
        lines,
        typed_state["refined_requirement"],
        (
            ("id", "id"),
            ("revision", "revision"),
            ("decision", "decision_id"),
            ("supersedes", "supersedes"),
        ),
        locale,
    )
    lines.append("")

    _reader_section(lines, locale, "current_behavior")
    for behavior_row in typed_state["current_behavior"]:
        _reader_heading(lines, locale, "invariant", behavior_row["id"])
        _reader_fields(
            lines,
            behavior_row,
            (
                ("behavior", "behavior"),
                ("evidence_level", "evidence_level"),
                ("evidence", "evidence"),
            ),
            locale,
        )
        lines.append("")

    _reader_section(lines, locale, "preserved_invariants")
    for invariant_row in typed_state["preserved_invariants"]:
        _reader_heading(lines, locale, "preserved_invariant", invariant_row["id"])
        _reader_fields(
            lines,
            invariant_row,
            (
                ("requirement", "requirement"),
                ("impacts", "impacts"),
                ("evidence", "evidence"),
            ),
            locale,
        )
        lines.append("")

    _reader_section(lines, locale, "impact_ledger")
    for impact_row in typed_state["impacts"]:
        _reader_heading(lines, locale, "impact_detail", impact_row["id"])
        _reader_fields(
            lines,
            impact_row,
            (
                ("requirement", "requirement"),
                ("category", "category"),
                ("severity", "severity"),
                ("state", "state"),
                ("evidence_level", "evidence_level"),
                ("evidence", "evidence"),
                ("invariants", "invariants"),
                ("decisions", "decision_ids"),
                ("criteria", "criterion_ids"),
            ),
            locale,
        )
        lines.append("")

    if typed_state["report"]["phase"] == "pre-decision":
        _reader_section(lines, locale, "decision_needed")
        needed = typed_state["decision_needed"]
        assert needed is not None
        _reader_fields(lines, needed, (("question", "question"),), locale)
        lines.append("")
        for index, option in enumerate(needed["options"], 1):
            _reader_heading(lines, locale, "option", index)
            _reader_fields(
                lines,
                option,
                (
                    ("option", "option_text"),
                    ("impacts", "impacts"),
                    ("tradeoff", "tradeoff"),
                ),
                locale,
            )
            lines.append("")
    else:
        _reader_section(lines, locale, "decisions")
        for decision_row in typed_state["decisions"]:
            _reader_heading(lines, locale, "decision", decision_row["id"])
            _reader_fields(
                lines,
                decision_row,
                (
                    ("choice", "choice"),
                    ("requirement", "requirement"),
                    ("accepted_impacts", "accepted_impacts"),
                    ("rationale", "rationale"),
                ),
                locale,
            )
            lines.append("")

    _reader_section(lines, locale, "impact_delta")
    for category in compact_state.DELTA_CATEGORIES:
        lines.append(f"- {category}: {_reader_value(typed_state['delta'][category], locale)}")
    lines.append("")

    _reader_section(lines, locale, "history")
    for history_row in typed_state["history"]:
        _reader_heading(lines, locale, "history_item", history_row["requirement"])
        _reader_fields(
            lines,
            history_row,
            (
                ("revision", "revision"),
                ("decision", "decision"),
                ("superseded_impacts", "superseded_impacts"),
                ("summary", "change_summary"),
            ),
            locale,
        )
        lines.append("")

    _reader_section(lines, locale, "criteria")
    for criterion_row in typed_state["criteria"]:
        _reader_heading(lines, locale, "criterion_item", criterion_row["id"])
        _reader_fields(
            lines,
            criterion_row,
            (
                ("requirement", "requirement"),
                ("impact", "impact_id"),
                ("invariant", "invariant_id"),
                ("criterion", "criterion"),
                ("evidence", "evidence"),
            ),
            locale,
        )
        lines.append("")

    _reader_section(lines, locale, "unresolved")
    if not typed_state["unresolved"]:
        lines.extend((f"- {_reader_label(locale, 'none')}", ""))
    for unresolved_row in typed_state["unresolved"]:
        _reader_heading(lines, locale, "unresolved_item", unresolved_row["impact"])
        _reader_fields(
            lines,
            unresolved_row,
            (
                ("state", "state"),
                ("rationale", "rationale"),
                ("decision", "linked_decision"),
                ("owner", "owner"),
            ),
            locale,
        )
        lines.append("")

    _reader_section(lines, locale, "scope")
    for index, scope_row in enumerate(typed_state["scope"], 1):
        _reader_heading(lines, locale, "scope_item", index)
        _reader_fields(
            lines,
            scope_row,
            (
                ("boundary", "boundary"),
                ("evidence", "evidence"),
                ("confidence", "confidence"),
            ),
            locale,
        )
        lines.append("")

    _reader_section(lines, locale, "handoff")
    _reader_fields(
        lines,
        typed_state["handoff"],
        (
            ("refined_requirement", "refined_requirement_id"),
            ("report_ids", "report_ids"),
            ("remaining_risks", "remaining_risks"),
            ("criteria", "criterion_ids"),
            ("workflow", "workflow"),
        ),
        locale,
    )
    return "\n".join(lines).rstrip() + "\n"


def render_full_view(state: Mapping[str, object], locale: str | None = None) -> str:
    """Render the configured full display without changing canonical state bytes."""
    settings = state.get("settings") if isinstance(state, Mapping) else None
    layout = settings.get("report_layout", "narrative") if isinstance(settings, Mapping) else None
    if layout == "table":
        return render_markdown(state)
    if layout == "narrative":
        return render_reader_view(state, locale)
    raise ValueError("report_layout must be table or narrative")


def render_markdown(state: Mapping[str, object]) -> str:
    errors = compact_state.validate_state(state)
    if errors:
        raise ValueError("; ".join(errors))
    typed_state = cast(
        compact_state.State, state
    )  # compact_state.validate_state proves the complete State shape.
    sections = (
        _render_report_state,
        _render_summary,
        _render_original_requirement,
        _render_refined_requirement,
        _render_current_behavior,
        _render_preserved_invariants,
        _render_impacts,
        _render_decision,
        _render_delta,
        _render_history,
        _render_criteria,
        _render_unresolved,
        _render_scope,
        _render_handoff,
    )
    return (
        "# Requirements Impact Report\n\n"
        + "\n\n".join(section(typed_state) for section in sections)
        + "\n"
    )


def validate_rendered_markdown(text: str, previous_bytes: bytes | None = None) -> list[str]:
    if previous_bytes is None:
        return VALIDATOR.validate_report(text, require_summary=True)
    try:
        previous_text = previous_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return ["predecessor Markdown must be UTF-8"]
    return VALIDATOR.validate_report(
        text,
        previous_text=previous_text,
        previous_bytes=previous_bytes,
        require_summary=True,
    )


def _artifact_path(state: compact_state.State, suffix: str) -> str:
    report = state["report"]
    return f".requirements-impact-refiner/reports/{report['id']}/revision-{report['revision']:04d}.{suffix}"


def _graph_scope(
    state: compact_state.State,
) -> tuple[dict[str, tuple[str, str]], str | None]:
    paths: dict[str, tuple[str, str]] = {}
    coverage: str | None = None
    for row in state["scope"]:
        boundary = row["boundary"]
        match = re.fullmatch(r"Graph paths for (IMP-\d{3})", boundary)
        if match:
            paths[match.group(1)] = (row["evidence"], row["confidence"])
        elif boundary == "Impact graph coverage":
            coverage = row["evidence"]
    return paths, coverage


def _structured_graph_paths(
    state: compact_state.State,
) -> dict[str, list[compact_state.GraphPath]]:
    return {row["impact"]: row["paths"] for row in state.get("graph_paths", [])}


def _short(value: object, limit: int) -> str:
    words = str(value).split()
    return " ".join(words[:limit]) + (" …" if len(words) > limit else "")


def _word_count(lines: Sequence[str]) -> int:
    return len("\n".join(lines).split())


def _compact_path(evidence: str, confidence: str, audience: str) -> str:
    evidence = evidence.split(" || ", 1)[0]
    confidence = confidence.split(" || ", 1)[0]
    if audience == "simple":
        return evidence.split(": ", 1)[-1]
    if audience == "balanced":
        return evidence
    return f"{evidence} ({confidence})"


def _structured_compact_path(path: compact_state.GraphPath, audience: str) -> str:
    label = _short(" → ".join(path["labels"]), 24)
    if audience == "simple":
        return label
    if audience == "balanced":
        return f"{path['id']}: {label}"
    providers = " + ".join(path["providers"])
    locations = " + ".join(path["locations"]) or "unavailable"
    return (
        f"{path['id']}: {label} (provider {providers}; "
        f"confidence {path['confidence']}; location {locations})"
    )


def _severity_rank(row: compact_state.Summary) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}[row["severity"]]


def _coverage_text(value: str) -> str:
    match = re.search(r"(Impact scan: [^·]+).*?(\d+ unknown frontiers)", value)
    if match:
        return f"{match.group(1).strip()} · {match.group(2)}"
    return value


def render_compact(state: Mapping[str, object]) -> str:
    errors = compact_state.validate_state(state)
    if errors:
        raise ValueError("; ".join(errors))
    typed_state = cast(
        compact_state.State, state
    )  # compact_state.validate_state proves the complete State shape.
    ranked = sorted(
        enumerate(typed_state["summary"]), key=lambda item: (_severity_rank(item[1]), item[0])
    )
    displayed = [row for _, row in ranked[:COMPACT_SUMMARY_ROWS]]
    lines = [
        "## Change Impact Summary",
        "",
        "| Impact | Possible issue | Affected | Prevention |",
        "| --- | --- | --- | --- |",
    ]
    for row in displayed:
        lines.append(
            f"| {_identifier(row['impact_id'])} | {_text(_short(row['possible_issue'], COMPACT_FIELD_WORDS))} | {_text(_short(row['affected'], COMPACT_FIELD_WORDS))} | {_text(_short(row['prevention'], COMPACT_FIELD_WORDS))} |"
        )
    omitted = len(typed_state["summary"]) - len(displayed)
    if omitted:
        lines.append(f"| — | {omitted} lower-priority impacts remain in the full report. | — | — |")
    graph_paths, graph_coverage = _graph_scope(typed_state)
    structured_paths = _structured_graph_paths(typed_state)
    remaining = [
        row
        for row in typed_state["summary"]
        if row["status"] in {"accepted", "deferred", "blocked"}
    ]
    tail: list[str] = []
    if remaining:
        shown_risks = remaining[:3]
        risk_text = "; ".join(
            _text(_short(row["possible_issue"], COMPACT_FIELD_WORDS)) for row in shown_risks
        )
        if len(remaining) > len(shown_risks):
            risk_text += f"; {len(remaining) - len(shown_risks)} more in the full report"
        tail.extend(("", "**Remaining risks:** " + risk_text))
    if typed_state["report"]["phase"] == "pre-decision":
        needed = typed_state["decision_needed"]
        assert needed is not None
        tail.extend(("", f"**Decision needed:** {_text(_short(needed['question'], 18))}"))
        tail.extend(
            f"- {_text(_short(option['option'], 10))}: {_text(_short(option['tradeoff'], 12))}"
            for option in needed["options"]
        )
    else:
        shown_decisions = typed_state["decisions"][:3]
        choices = "; ".join(_text(_short(row["choice"], 18)) for row in shown_decisions)
        if len(typed_state["decisions"]) > len(shown_decisions):
            choices += (
                f"; {len(typed_state['decisions']) - len(shown_decisions)} more in the full report"
            )
        tail.extend(("", f"**Recorded decision:** {choices}"))
    tail.extend(
        (
            "",
            f"Validation: passed · Report {_identifier(typed_state['report']['id'])} revision {typed_state['report']['revision']}",
            f"State: `{_artifact_path(typed_state, 'json')}`",
            f"Full report: `{_artifact_path(typed_state, 'md')}`",
        )
    )
    graph_lines: list[str] = []
    if graph_coverage is not None:
        graph_lines.extend(("", f"**Coverage:** {_text(_coverage_text(graph_coverage))}"))
    if graph_paths or structured_paths:
        candidates: list[str] = []
        for _, row in ranked:
            structured = structured_paths.get(row["impact_id"])
            if structured:
                rendered = _structured_compact_path(
                    structured[0], typed_state["settings"]["audience"]
                )
            else:
                path = graph_paths.get(row["impact_id"])
                if path is None:
                    continue
                evidence, confidence = path
                rendered = _short(
                    _compact_path(evidence, confidence, typed_state["settings"]["audience"]),
                    36,
                )
            candidates.append(f"- {_identifier(row['impact_id'])}: {_text(rendered)}")
        selected: list[str] = []
        for candidate in candidates:
            proposal = [*lines, "", "**Impact paths:**", *selected, candidate, *graph_lines, *tail]
            if _word_count(proposal) <= COMPACT_WORD_LIMIT:
                selected.append(candidate)
        if selected:
            graph_lines = ["", "**Impact paths:**", *selected, *graph_lines]
    output = lines + graph_lines + tail
    if _word_count(output) > COMPACT_WORD_LIMIT:
        raise ValueError("compact output exceeds word budget")
    return "\n".join(output) + "\n"


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
        "report": {
            "id": metadata.report_id,
            "revision": metadata.revision,
            "previous_sha256": metadata.previous_sha256,
            "phase": metadata.phase,
        },
        "settings": {
            "audience": "balanced",
            "audience_source": "default",
            "delivery": "compact",
            "delivery_source": "default",
        },
        "original_requirement": {
            "id": _unquote(original["Requirement ID"]),
            "request": _unquote(original["Original request"]),
            "source": _unquote(original["Source"]),
        },
        "refined_requirement": {
            "id": _unquote(refined["Requirement ID"]),
            "revision": _unquote(refined["Revision"]),
            "decision": next(iter(_ids(refined["Refined by decision"], "DEC-")), None),
            "supersedes": _ids(refined["Supersedes"], "REQ-"),
        },
        "current_behavior": [
            {
                "id": _unquote(row["Invariant ID"]),
                "behavior": _unquote(row["Current behavior"]),
                "evidence_level": _unquote(row["Evidence level"]),
                "evidence": _unquote(row["Evidence"]),
            }
            for row in tables["Current Behavior"]
        ],
        "preserved_invariants": [
            {
                "id": _unquote(row["Invariant ID"]),
                "requirement": _ids(row["Must preserve for requirement"], "REQ-")[0],
                "impacts": _ids(row["Affected impacts"], "IMP-"),
                "evidence": _unquote(row["Evidence"]),
            }
            for row in tables["Preserved Invariants"]
        ],
        "impacts": [
            {
                "id": _unquote(row["ID"]),
                "requirement": _ids(row["Requirement"], "REQ-")[0],
                "category": _unquote(row["Category"]),
                "severity": _unquote(row["Severity"]),
                "state": _unquote(row["State"]),
                "evidence_level": _unquote(row["Evidence Level"]),
                "evidence": _unquote(row["Evidence"]),
                "invariants": _ids(row["Invariants"], "INV-"),
                "decisions": _ids(row["Decision"], "DEC-"),
                "criteria": _ids(row["Acceptance Criteria"], "AC-"),
            }
            for row in tables["Impact Ledger"]
        ],
        "decisions": [],
        "decision_needed": None,
        "delta": {
            row["Category"].strip("`"): _ids(row["Impact IDs"], "IMP-")
            for row in tables["Impact Delta"]
        },
        "history": [
            {
                "requirement": _ids(row["Requirement ID"], "REQ-")[0],
                "revision": _unquote(row["Revision"]),
                "decision": next(iter(_ids(row["Decision"], "DEC-")), None),
                "superseded_impacts": _ids(row["Superseded impacts"], "IMP-"),
                "summary": _unquote(row["Change summary"]),
            }
            for row in tables["Requirement Revision History"]
        ],
        "criteria": [
            {
                "id": _unquote(row["Criterion ID"]),
                "requirement": _ids(row["Requirement"], "REQ-")[0],
                "impact": _ids(row["Impact"], "IMP-")[0],
                "invariant": _ids(row["Invariant"], "INV-")[0],
                "criterion": _unquote(row["Observable criterion"]),
                "evidence": _unquote(row["Evidence/test"]),
            }
            for row in tables["Acceptance and Regression Criteria"]
        ],
        "unresolved": [
            {
                "impact": _ids(row["Impact ID"], "IMP-")[0],
                "state": _unquote(row["State"]),
                "rationale": _unquote(row["Information gap or rationale"]),
                "decision": next(iter(_ids(row["Linked decision"], "DEC-")), None),
                "owner": _unquote(row["Next owner"]),
            }
            for row in tables["Unresolved, Deferred, and Blocked Items"]
        ],
        "scope": [
            {
                "boundary": _unquote(row["Scope or limitation"]),
                "evidence": _unquote(row["Inspected evidence"]),
                "confidence": _unquote(row["Consequence for confidence"]),
            }
            for row in tables["Analysis Scope and Limitations"]
        ],
        "summary": [
            {
                "impact_id": _unquote(row["Impact ID"]),
                "changed_feature": _unquote(row["Changed feature"]),
                "possible_issue": _unquote(row["Possible issue"]),
                "affected": _unquote(row["Affected feature or user"]),
                "trigger": _unquote(row["Trigger"]),
                "severity": _unquote(row["Severity"]),
                "prevention": _unquote(row["Prevention or check"]),
                "status": _unquote(row["Status"]),
            }
            for row in tables["Change Impact Summary"]
        ],
    }
    handoff = tables["Planning Handoff"][0]
    refined_handoff_ids = _ids(handoff["Refined requirement"], "REQ-")
    state["handoff"] = {
        "refined_requirement": refined_handoff_ids[0]
        if len(refined_handoff_ids) == 1
        and _unquote(handoff["Refined requirement"]) == refined_handoff_ids[0]
        else _unquote(handoff["Refined requirement"]),
        "report_ids": _ids(handoff["Report IDs"]),
        "remaining_risks": _ids(handoff["Remaining risks"], "IMP-"),
        "criteria": _ids(handoff["Acceptance criteria"], "AC-"),
        "workflow": _unquote(handoff["Selected planning workflow"]),
    }
    if metadata.phase == "pre-decision":
        rows = tables["Decision Needed"]
        state["decision_needed"] = {
            "question": _unquote(rows[0]["Question"]),
            "options": [
                {
                    "option": _unquote(row["Option"]),
                    "impacts": _ids(row["Impact IDs"], "IMP-"),
                    "tradeoff": _unquote(row["Trade-off"]),
                }
                for row in rows
            ],
        }
    else:
        state["decisions"] = [
            {
                "id": _unquote(row["Decision ID"]),
                "choice": _unquote(row["Choice"]),
                "requirement": _ids(row["Requirement revision"], "REQ-")[0],
                "accepted_impacts": _ids(row["Accepted impacts"], "IMP-"),
                "rationale": _unquote(row["Rationale"]),
            }
            for row in tables["Decisions and Accepted Risks"]
        ]
    state_errors = compact_state.validate_state(state)
    return (None, state_errors) if state_errors else (state, [])
