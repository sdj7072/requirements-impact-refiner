#!/usr/bin/env python3

import re
import sys
from pathlib import Path


ID_PATTERN = re.compile(r"\b(?:REQ|INV|IMP|DEC|AC)-\d{3}\b")
ID_LIKE_PATTERN = re.compile(r"^(?:REQ|INV|IMP|DEC|AC)-")
ID_TOKEN_PATTERN = re.compile(r"\b(?:REQ|INV|IMP|DEC|AC)-[A-Za-z0-9]+\b")
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
REQUIRED_SECTIONS = {
    "Original Requirement",
    "Current Refined Requirement",
    "Current Behavior",
    "Preserved Invariants",
    "Impact Ledger",
    "Decisions and Accepted Risks",
    "Requirement Revision History",
    "Acceptance and Regression Criteria",
    "Unresolved, Deferred, and Blocked Items",
    "Analysis Scope and Limitations",
    "Planning Handoff",
}
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
    "Requirement Revision History": [
        "Requirement ID",
        "Revision",
        "Decision",
        "Superseded impacts",
        "Delta",
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
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines) for name, lines in sections.items()}


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_table(
    section_name: str, section: str, expected_headers: list[str]
) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    lines = [line.strip() for line in section.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return [], [f"invalid table schema in {section_name}"]
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


def validate_report(text: str) -> list[str]:
    errors: list[str] = []
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first_line != "# Requirements Impact Report":
        errors.append("missing canonical title: # Requirements Impact Report")
    sections = markdown_sections(text)
    for name in sorted(REQUIRED_SECTIONS - sections.keys()):
        errors.append(f"missing section: {name}")

    tables: dict[str, list[dict[str, str]]] = {}
    for name, headers in TABLE_HEADERS.items():
        rows, table_errors = parse_table(name, sections.get(name, ""), headers)
        tables[name] = rows
        errors.extend(table_errors)

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
            ref
            for ref in references(row.get("Acceptance Criteria", ""))
            if ref.startswith("AC-")
        }
        if not requirement_refs:
            errors.append(f"impact {impact_id} requires REQ reference")
        else:
            has_requirement_relationship = True
        if state == "resolved" and not evidence:
            errors.append(f"resolved impact {impact_id} requires evidence")
        if state == "accepted" and not decision_refs:
            errors.append(f"accepted impact {impact_id} requires DEC reference")
        if row.get("Severity", "").lower() == "critical" and not ac_refs:
            errors.append(f"critical impact {impact_id} requires AC reference")
    if not has_requirement_relationship:
        errors.append("report requires at least one impact with REQ relationship")

    unresolved_counts: dict[str, int] = {}
    for row in tables["Unresolved, Deferred, and Blocked Items"]:
        impact_id = row.get("Impact ID", "").strip("`")
        state = enum_value(row.get("State", ""))
        if not ID_PATTERN.fullmatch(impact_id):
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
                f"ledger impact {impact_id} in state {state} "
                "is missing from unresolved items"
            )
    return sorted(set(errors))


def validate_path(path: Path) -> list[str]:
    return validate_report(path.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate-impact-report.py REPORT.md", file=sys.stderr)
        return 2
    errors = validate_path(Path(argv[1]))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("valid impact report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
