#!/usr/bin/env python3

import re
import sys
from pathlib import Path


ID_PATTERN = re.compile(r"\b(?:REQ|INV|IMP|DEC|AC)-\d{3}\b")
ID_LIKE_PATTERN = re.compile(r"^(?:REQ|INV|IMP|DEC|AC)-")
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


def table_rows(section: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in section.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return []
    headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def references(value: str) -> set[str]:
    return set(ID_PATTERN.findall(value))


def validate_report(text: str) -> list[str]:
    errors: list[str] = []
    sections = markdown_sections(text)
    for name in sorted(REQUIRED_SECTIONS - sections.keys()):
        errors.append(f"missing section: {name}")

    definitions: list[str] = []
    for name, column in DEFINITION_COLUMNS.items():
        for row in table_rows(sections.get(name, "")):
            identifier = row.get(column, "").strip("`")
            if ID_PATTERN.fullmatch(identifier):
                definitions.append(identifier)
            elif ID_LIKE_PATTERN.match(identifier):
                errors.append(f"invalid identifier {identifier}")
    known = set(definitions)
    for identifier in sorted(known):
        if definitions.count(identifier) > 1:
            errors.append(f"duplicate identifier {identifier}")

    for section in sections.values():
        for row in table_rows(section):
            for value in row.values():
                for reference in references(value):
                    if reference not in known:
                        errors.append(f"unknown reference {reference}")

    for row in table_rows(sections.get("Impact Ledger", "")):
        impact_id = row.get("ID", "unknown impact")
        state = row.get("State", "")
        level = row.get("Evidence Level", "")
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
        if state not in IMPACT_STATES:
            errors.append(f"invalid impact state {state}")
        if level not in EVIDENCE_LEVELS:
            errors.append(f"invalid evidence level {level}")
        if not requirement_refs:
            errors.append(f"impact {impact_id} requires REQ reference")
        if state == "resolved" and not evidence:
            errors.append(f"resolved impact {impact_id} requires evidence")
        if state == "accepted" and not decision_refs:
            errors.append(f"accepted impact {impact_id} requires DEC reference")
        if row.get("Severity", "").lower() == "critical" and not ac_refs:
            errors.append(f"critical impact {impact_id} requires AC reference")
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
