#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from impact_report import (
    calculate_delta,
    parse_report,
    render_delta,
    strip_fenced_blocks,
    table_block,
    validate_authored_delta,
    validate_baseline,
    validate_lineage,
    validate_semantics,
)

ID_PATTERN = re.compile(r"\b(?:REQ|INV|IMP|DEC|AC)-\d{3}\b")
ID_LIKE_PATTERN = re.compile(r"^(?:REQ|INV|IMP|DEC|AC)-")
ID_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:REQ|INV|IMP|DEC|AC)-[A-Za-z0-9#]+(?![A-Za-z0-9_])"
)
IMPACT_STATES = {
    "detected",
    "refining",
    "mitigated",
    "resolved",
    "accepted",
    "deferred",
    "blocked",
    "superseded",
}
EVIDENCE_LEVELS = {"verified", "inferred", "unknown"}
UNRESOLVED_STATES = {"deferred", "blocked"}
REPORT_PHASES = {"pre-decision", "post-decision"}
DELTA_CATEGORIES = {
    "resolved",
    "mitigated",
    "unchanged",
    "accepted",
    "deferred",
    "blocked",
    "superseded",
    "reopened",
    "new",
}
STATE_TO_DELTA = {
    "detected": "unchanged",
    "refining": "unchanged",
    "mitigated": "mitigated",
    "resolved": "resolved",
    "accepted": "accepted",
    "deferred": "deferred",
    "blocked": "blocked",
    "superseded": "superseded",
}
COMMON_REQUIRED_SECTIONS = {
    "Report State",
    "Original Requirement",
    "Current Refined Requirement",
    "Current Behavior",
    "Preserved Invariants",
    "Impact Ledger",
    "Impact Delta",
    "Requirement Revision History",
    "Acceptance and Regression Criteria",
    "Unresolved, Deferred, and Blocked Items",
    "Analysis Scope and Limitations",
    "Planning Handoff",
}
SUMMARY_SECTION = "Change Impact Summary"
PHASE_REQUIRED_SECTION = {
    "pre-decision": "Decision Needed",
    "post-decision": "Decisions and Accepted Risks",
}
PHASE_FORBIDDEN_SECTION = {
    "pre-decision": "Decisions and Accepted Risks",
    "post-decision": "Decision Needed",
}
REQUIRED_SECTIONS = COMMON_REQUIRED_SECTIONS | set(PHASE_REQUIRED_SECTION.values())
DEFINITION_COLUMNS = {
    "Original Requirement": "Requirement ID",
    "Current Behavior": "Invariant ID",
    "Impact Ledger": "ID",
    "Decisions and Accepted Risks": "Decision ID",
    "Acceptance and Regression Criteria": "Criterion ID",
}
EVIDENCE_LEVEL_COLUMNS = {
    "Current Behavior": "Evidence level",
    "Impact Ledger": "Evidence Level",
}
STATE_RULES = {
    "Impact Ledger": ("State", IMPACT_STATES),
    "Unresolved, Deferred, and Blocked Items": ("State", UNRESOLVED_STATES),
}
TABLE_HEADERS = {
    SUMMARY_SECTION: [
        "Impact ID",
        "Changed feature",
        "Possible issue",
        "Affected feature or user",
        "Trigger",
        "Severity",
        "Prevention or check",
        "Status",
    ],
    "Report State": ["Report ID", "Revision", "Previous SHA-256", "Phase"],
    "Original Requirement": ["Requirement ID", "Original request", "Source"],
    "Current Refined Requirement": [
        "Requirement ID",
        "Revision",
        "Refined by decision",
        "Supersedes",
    ],
    "Current Behavior": [
        "Invariant ID",
        "Current behavior",
        "Evidence level",
        "Evidence",
    ],
    "Preserved Invariants": [
        "Invariant ID",
        "Must preserve for requirement",
        "Affected impacts",
        "Evidence",
    ],
    "Impact Ledger": [
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
    ],
    "Decisions and Accepted Risks": [
        "Decision ID",
        "Choice",
        "Requirement revision",
        "Accepted impacts",
        "Rationale",
    ],
    "Decision Needed": ["Question", "Option", "Impact IDs", "Trade-off"],
    "Impact Delta": ["Category", "Impact IDs"],
    "Requirement Revision History": [
        "Requirement ID",
        "Revision",
        "Decision",
        "Superseded impacts",
        "Change summary",
    ],
    "Acceptance and Regression Criteria": [
        "Criterion ID",
        "Requirement",
        "Impact",
        "Invariant",
        "Observable criterion",
        "Evidence/test",
    ],
    "Unresolved, Deferred, and Blocked Items": [
        "Impact ID",
        "State",
        "Information gap or rationale",
        "Linked decision",
        "Next owner",
    ],
    "Analysis Scope and Limitations": [
        "Scope or limitation",
        "Inspected evidence",
        "Consequence for confidence",
    ],
    "Planning Handoff": [
        "Refined requirement",
        "Report IDs",
        "Remaining risks",
        "Acceptance criteria",
        "Selected planning workflow",
    ],
}
REQUIRED_DEFINITION_ROWS = {
    "Original Requirement": "requirement",
    "Current Behavior": "invariant",
    "Impact Ledger": "impact",
    "Acceptance and Regression Criteria": "criterion",
}


def markdown_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in strip_fenced_blocks(text).splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines) for name, lines in sections.items()}


def duplicate_section_names(text: str) -> set[str]:
    counts: dict[str, int] = {}
    for line in strip_fenced_blocks(text).splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            counts[name] = counts.get(name, 0) + 1
    return {name for name, count in counts.items() if count > 1}


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_table(
    section_name: str, section: str, expected_headers: list[str]
) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    lines, extra_table = table_block(section)
    if extra_table:
        errors.append(f"multiple tables in {section_name}")
    if len(lines) < 2:
        return [], [*errors, f"invalid table schema in {section_name}"]
    headers = table_cells(lines[0])
    if headers != expected_headers:
        return [], [f"invalid table schema in {section_name}"]
    separator = table_cells(lines[1])
    if len(separator) != len(headers) or any(
        not re.fullmatch(r":?-{3,}:?", cell) for cell in separator
    ):
        errors.append(f"invalid table schema in {section_name}")
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        cells = table_cells(line)
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
        else:
            errors.append(
                f"malformed table row in {section_name}: "
                f"expected {len(headers)} cells, got {len(cells)}"
            )
    return rows, errors


def references(value: str) -> set[str]:
    return set(ID_PATTERN.findall(value))


def enum_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


def _validate_single_report(text: str, *, require_summary: bool = False) -> list[str]:
    errors: list[str] = []
    parsed_report, report_errors = parse_report(text)
    errors.extend(report_errors)
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first_line != "# Requirements Impact Report":
        errors.append("missing canonical title: # Requirements Impact Report")
    sections = markdown_sections(text)
    for name in sorted(duplicate_section_names(text) & TABLE_HEADERS.keys()):
        errors.append(f"duplicate section: {name}")
    if require_summary and SUMMARY_SECTION not in sections:
        errors.append(f"missing section: {SUMMARY_SECTION}")
    for name in sorted(COMMON_REQUIRED_SECTIONS - sections.keys()):
        errors.append(f"missing section: {name}")

    phase_rows, phase_table_errors = parse_table(
        "Report State", sections.get("Report State", ""), TABLE_HEADERS["Report State"]
    )
    errors.extend(phase_table_errors)
    phase = enum_value(phase_rows[0].get("Phase", "")) if len(phase_rows) == 1 else ""
    if len(phase_rows) != 1:
        errors.append("report state requires exactly one phase row")
    if phase and phase not in REPORT_PHASES:
        errors.append(f"invalid report phase {phase}")
    if phase in REPORT_PHASES:
        required = PHASE_REQUIRED_SECTION[phase]
        forbidden = PHASE_FORBIDDEN_SECTION[phase]
        if required not in sections:
            errors.append(f"missing section: {required}")
        if forbidden in sections:
            errors.append(f"{phase} report forbids section: {forbidden}")

    tables: dict[str, list[dict[str, str]]] = {}
    for name, headers in TABLE_HEADERS.items():
        if name == SUMMARY_SECTION and name not in sections:
            tables[name] = []
            continue
        if name in {"Decision Needed", "Decisions and Accepted Risks"} and name not in sections:
            tables[name] = []
            continue
        rows, table_errors = parse_table(name, sections.get(name, ""), headers)
        tables[name] = rows
        errors.extend(table_errors)

    if phase == "pre-decision":
        option_rows = tables["Decision Needed"]
        if not 2 <= len(option_rows) <= 3:
            errors.append("pre-decision report requires two or three options")
        questions = {row.get("Question", "").strip() for row in option_rows}
        if len(questions) != 1 or not next(iter(questions), ""):
            errors.append("pre-decision report requires one focused question")
        options = [row.get("Option", "").strip() for row in option_rows]
        if any(not option for option in options) or len(set(options)) != len(options):
            errors.append("pre-decision report requires distinct options")
        for row in option_rows:
            if not any(ref.startswith("IMP-") for ref in references(row.get("Impact IDs", ""))):
                errors.append("pre-decision option requires IMP reference")
            if not row.get("Trade-off", "").strip():
                errors.append("pre-decision option requires a nonempty trade-off")
        if any(token.startswith("DEC-") for token in ID_PATTERN.findall(text)):
            errors.append("pre-decision report forbids concrete DEC identifiers")
    elif phase == "post-decision":
        if not tables["Decisions and Accepted Risks"]:
            errors.append("post-decision report requires a recorded decision row")
        for row in tables["Decisions and Accepted Risks"]:
            decision_id = row.get("Decision ID", "unknown decision").strip("`")
            if not row.get("Choice", "").strip():
                errors.append(f"recorded decision {decision_id} requires a nonempty choice")
            if not row.get("Rationale", "").strip():
                errors.append(f"recorded decision {decision_id} requires a nonempty rationale")
            if not any(
                ref.startswith("REQ-") for ref in references(row.get("Requirement revision", ""))
            ):
                errors.append(f"recorded decision {decision_id} requires a requirement revision")
            accepted = enum_value(row.get("Accepted impacts", ""))
            accepted_refs = {
                ref for ref in references(row.get("Accepted impacts", "")) if ref.startswith("IMP-")
            }
            if accepted != "none" and not accepted_refs:
                errors.append(f"recorded decision {decision_id} requires accepted impacts or none")
        current_rows = tables["Current Refined Requirement"]
        if not any(
            any(ref.startswith("DEC-") for ref in references(row.get("Refined by decision", "")))
            for row in current_rows
        ):
            errors.append("post-decision current requirement requires DEC reference")

    for section_name, entity in REQUIRED_DEFINITION_ROWS.items():
        if not tables[section_name]:
            errors.append(f"missing required {entity} row")

    definitions: list[str] = []
    for name, column in DEFINITION_COLUMNS.items():
        for row in tables[name]:
            identifier = row.get(column, "").strip("`")
            if ID_PATTERN.fullmatch(identifier):
                definitions.append(identifier)
            elif ID_LIKE_PATTERN.match(identifier):
                errors.append(f"invalid identifier {identifier}")
    known = set(definitions)
    for identifier in sorted(known):
        if definitions.count(identifier) > 1:
            errors.append(f"duplicate identifier {identifier}")

    for rows in tables.values():
        for row in rows:
            for value in row.values():
                for token in ID_TOKEN_PATTERN.findall(value):
                    if not ID_PATTERN.fullmatch(token):
                        errors.append(f"invalid identifier {token}")
                for reference in references(value):
                    if reference not in known:
                        errors.append(f"unknown reference {reference}")

    for row in tables["Current Refined Requirement"]:
        requirement_id = row.get("Requirement ID", "").strip("`")
        if (
            not ID_PATTERN.fullmatch(requirement_id)
            or not requirement_id.startswith("REQ-")
            or requirement_id not in known
        ):
            errors.append("current refined requirement requires one known REQ identifier")

    for name, column in EVIDENCE_LEVEL_COLUMNS.items():
        for row in tables[name]:
            level = enum_value(row.get(column, ""))
            if level not in EVIDENCE_LEVELS:
                errors.append(f"invalid evidence level {level}")

    for name, (column, allowed_states) in STATE_RULES.items():
        for row in tables[name]:
            state = enum_value(row.get(column, ""))
            if state not in allowed_states:
                errors.append(f"invalid impact state {state}")

    impact_states: dict[str, str] = {}
    has_requirement_relationship = False
    for row in tables["Impact Ledger"]:
        impact_id = row.get("ID", "unknown impact")
        normalized_impact_id = impact_id.strip("`")
        state = enum_value(row.get("State", ""))
        if ID_PATTERN.fullmatch(normalized_impact_id):
            impact_states[normalized_impact_id] = state
        evidence = row.get("Evidence", "").strip()
        requirement_refs = {
            ref for ref in references(row.get("Requirement", "")) if ref.startswith("REQ-")
        }
        decision_refs = {
            ref for ref in references(row.get("Decision", "")) if ref.startswith("DEC-")
        }
        ac_refs = {
            ref for ref in references(row.get("Acceptance Criteria", "")) if ref.startswith("AC-")
        }
        if not requirement_refs:
            errors.append(f"impact {impact_id} requires REQ reference")
        else:
            has_requirement_relationship = True
        if state == "resolved" and not evidence:
            errors.append(f"resolved impact {impact_id} requires evidence")
        if state == "accepted" and not decision_refs:
            errors.append(f"accepted impact {impact_id} requires DEC reference")
        if enum_value(row.get("Severity", "")).lower() == "critical" and not ac_refs:
            errors.append(f"critical impact {impact_id} requires AC reference")
    if not has_requirement_relationship:
        errors.append("report requires at least one impact with REQ relationship")

    if SUMMARY_SECTION in sections:
        summary_counts: dict[str, int] = {}
        for row in tables[SUMMARY_SECTION]:
            impact_id = row.get("Impact ID", "").strip("`")
            if not ID_PATTERN.fullmatch(impact_id) or not impact_id.startswith("IMP-"):
                errors.append("impact summary row requires exactly one canonical IMP identifier")
                continue
            summary_counts[impact_id] = summary_counts.get(impact_id, 0) + 1
            if impact_id not in impact_states:
                errors.append(f"impact summary references unknown impact {impact_id}")
            for column in (
                "Changed feature",
                "Possible issue",
                "Affected feature or user",
                "Trigger",
                "Prevention or check",
            ):
                if not row.get(column, "").strip():
                    errors.append(f"impact summary {impact_id} requires {column}")
            ledger_row = next(
                (
                    impact
                    for impact in tables["Impact Ledger"]
                    if impact.get("ID", "").strip("`") == impact_id
                ),
                None,
            )
            if ledger_row is not None:
                summary_severity = enum_value(row.get("Severity", ""))
                ledger_severity = enum_value(ledger_row.get("Severity", ""))
                if summary_severity != ledger_severity:
                    errors.append(
                        f"impact summary {impact_id} severity {summary_severity or '<empty>'} "
                        f"disagrees with ledger {ledger_severity or '<empty>'}"
                    )
                summary_status = enum_value(row.get("Status", ""))
                ledger_status = enum_value(ledger_row.get("State", ""))
                if summary_status != ledger_status:
                    errors.append(
                        f"impact summary {impact_id} status {summary_status or '<empty>'} "
                        f"disagrees with ledger {ledger_status or '<empty>'}"
                    )
        for impact_id, count in summary_counts.items():
            if count > 1:
                errors.append(f"impact summary lists {impact_id} more than once")
        for impact_id in sorted(impact_states):
            if summary_counts.get(impact_id, 0) == 0:
                errors.append(f"impact summary missing known impact {impact_id}")

    delta_rows = tables["Impact Delta"]
    delta_by_category: dict[str, set[str]] = {}
    delta_counts: dict[str, int] = {}
    for row in delta_rows:
        category = enum_value(row.get("Category", ""))
        if category not in DELTA_CATEGORIES:
            errors.append(f"invalid impact delta category {category}")
            continue
        if category in delta_by_category:
            errors.append(f"duplicate impact delta category {category}")
        impact_cell = row.get("Impact IDs", "").strip()
        normalized_cell = impact_cell.replace("`", "").strip().lower()
        canonical_ids = [part.strip() for part in impact_cell.replace("`", "").split(",")]
        if normalized_cell != "none" and (
            not canonical_ids or any(not re.fullmatch(r"IMP-\d{3}", part) for part in canonical_ids)
        ):
            errors.append(
                f"impact delta category {category} requires literal none or canonical IMP identifiers"
            )
        id_occurrences = [
            ref for ref in references(row.get("Impact IDs", "")) if ref.startswith("IMP-")
        ]
        raw_occurrences = [
            ref for ref in ID_PATTERN.findall(row.get("Impact IDs", "")) if ref.startswith("IMP-")
        ]
        ids = set(id_occurrences)
        delta_by_category.setdefault(category, set()).update(ids)
        for impact_id in raw_occurrences:
            delta_counts[impact_id] = delta_counts.get(impact_id, 0) + 1
            if impact_id not in impact_states:
                errors.append(f"impact delta references unknown impact {impact_id}")
    for category in sorted(DELTA_CATEGORIES - delta_by_category.keys()):
        errors.append(f"impact delta missing category {category}")
    for impact_id in sorted(impact_states):
        count = delta_counts.get(impact_id, 0)
        if count == 0:
            errors.append(f"impact delta missing known impact {impact_id}")
        elif count > 1:
            errors.append(f"impact delta lists {impact_id} more than once")
    if parsed_report.metadata and parsed_report.metadata.revision == 1:
        for category, impact_ids in delta_by_category.items():
            if category in {"new", "reopened"}:
                continue
            for impact_id in impact_ids:
                delta_state = impact_states.get(impact_id)
                if delta_state is not None and STATE_TO_DELTA.get(delta_state) != category:
                    errors.append(
                        f"impact {impact_id} state {delta_state} disagrees with delta category {category}"
                    )

    unresolved_counts: dict[str, int] = {}
    for row in tables["Unresolved, Deferred, and Blocked Items"]:
        impact_id = row.get("Impact ID", "").strip("`")
        state = enum_value(row.get("State", ""))
        if not ID_PATTERN.fullmatch(impact_id) or not impact_id.startswith("IMP-"):
            errors.append("unresolved row requires exactly one canonical IMP identifier")
            continue
        if impact_id not in impact_states:
            errors.append(f"unresolved impact {impact_id} is not in ledger")
            continue
        unresolved_counts[impact_id] = unresolved_counts.get(impact_id, 0) + 1
        ledger_state = impact_states.get(impact_id)
        if ledger_state is not None and state != ledger_state:
            errors.append(
                f"unresolved impact {impact_id} state {state} "
                f"disagrees with ledger state {ledger_state}"
            )
    for impact_id, count in unresolved_counts.items():
        if count > 1:
            errors.append(f"duplicate unresolved impact {impact_id}")
    for impact_id, state in impact_states.items():
        if state in UNRESOLVED_STATES and unresolved_counts.get(impact_id, 0) == 0:
            errors.append(
                f"ledger impact {impact_id} in state {state} is missing from unresolved items"
            )
    errors.extend(validate_baseline(parsed_report))
    errors.extend(validate_semantics(parsed_report))
    return sorted(set(errors))


def validate_report(
    text: str,
    *,
    previous_text: str | None = None,
    previous_bytes: bytes | None = None,
    require_summary: bool = False,
) -> list[str]:
    errors = _validate_single_report(text, require_summary=require_summary)
    current, current_parse_errors = parse_report(text)
    errors.extend(current_parse_errors)
    if current.metadata is None:
        return sorted(set(errors))
    if previous_text is None:
        if current.metadata.revision > 1:
            errors.append(f"revision {current.metadata.revision} requires --previous")
        return sorted(set(errors))
    previous, previous_parse_errors = parse_report(previous_text)
    errors.extend(f"previous report: {error}" for error in previous_parse_errors)
    errors.extend(f"previous report: {error}" for error in _validate_single_report(previous_text))
    if previous.metadata is None:
        return sorted(set(errors))
    if previous_bytes is None:
        errors.append("lineage validation requires exact previous bytes")
        return sorted(set(errors))
    errors.extend(validate_lineage(previous, current, previous_bytes))
    current_states = {
        enum_value(row.get("State", "")) for row in current.tables.get("Impact Ledger", ())
    }
    previous_states = {
        enum_value(row.get("State", "")) for row in previous.tables.get("Impact Ledger", ())
    }
    if current_states <= IMPACT_STATES and previous_states <= IMPACT_STATES:
        errors.extend(validate_authored_delta(previous, current))
    return sorted(set(errors))


def validate_path(path: Path) -> list[str]:
    return validate_report(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a requirements impact report")
    parser.add_argument("report", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--print-expected-delta", action="store_true")
    parser.add_argument("--require-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        current_bytes = args.report.read_bytes()
        current_text = current_bytes.decode("utf-8")
        previous_bytes = args.previous.read_bytes() if args.previous else None
        previous_text = previous_bytes.decode("utf-8") if previous_bytes is not None else None
    except (OSError, UnicodeDecodeError) as error:
        print(f"cannot read report: {error}", file=sys.stderr)
        return 2
    errors = validate_report(
        current_text,
        previous_text=previous_text,
        previous_bytes=previous_bytes,
        require_summary=args.require_summary,
    )
    if args.print_expected_delta and not errors:
        current_report, current_errors = parse_report(current_text)
        previous_report = None
        previous_errors: list[str] = []
        if previous_text is not None:
            previous_report, previous_errors = parse_report(previous_text)
        if not current_errors and not previous_errors:
            print(render_delta(calculate_delta(previous_report, current_report)))
    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        return 1
    print("valid impact report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
