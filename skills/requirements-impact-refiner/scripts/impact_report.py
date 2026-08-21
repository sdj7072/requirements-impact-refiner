#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Sequence


RPT_PATTERN = re.compile(r"RPT-\d{3}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
IMPACT_PATTERN = re.compile(r"\bIMP-\d{3}\b")
ENTITY_PATTERN = re.compile(r"\b(?:REQ|INV|IMP|DEC|AC)-\d{3}\b")
IMPACT_CATEGORIES = {
    "functionality",
    "data",
    "interfaces",
    "authorization/privacy",
    "state/concurrency",
    "operations",
    "compatibility",
    "legal/policy",
    "regression",
}
SEVERITIES = {"critical", "high", "medium", "low"}
EVIDENCE_LEVELS = {"verified", "inferred", "unknown"}


@dataclass(frozen=True)
class ReportMetadata:
    report_id: str
    revision: int
    previous_sha256: str
    phase: str


@dataclass(frozen=True)
class ParsedReport:
    text: str
    metadata: ReportMetadata | None
    sections: Mapping[str, str]
    tables: Mapping[str, Sequence[Mapping[str, str]]]


def markdown_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines) for name, lines in sections.items()}


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_section_table(section: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in section.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return []
    headers = table_cells(lines[0])
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        cells = table_cells(line)
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


def present(value: str) -> bool:
    return unquote(value).strip().lower() not in {"", "—", "none"}


def references(value: str, prefix: str) -> set[str]:
    return {
        token
        for token in ENTITY_PATTERN.findall(value)
        if token.startswith(prefix)
    }


def entity_id(row: Mapping[str, str], column: str, fallback: str) -> str:
    return unquote(row.get(column, "")) or fallback


def parse_metadata(
    rows: Sequence[Mapping[str, str]],
) -> tuple[ReportMetadata | None, list[str]]:
    if len(rows) != 1:
        return None, ["report state requires exactly one metadata row"]
    row = rows[0]
    report_id = unquote(row.get("Report ID", ""))
    revision_text = unquote(row.get("Revision", ""))
    previous_sha256 = unquote(row.get("Previous SHA-256", ""))
    phase = unquote(row.get("Phase", ""))
    errors: list[str] = []
    if not RPT_PATTERN.fullmatch(report_id):
        errors.append(f"invalid Report ID {report_id or '<empty>'}")
    try:
        revision = int(revision_text)
    except ValueError:
        revision = 0
    if revision < 1:
        errors.append(f"invalid report revision {revision_text or '<empty>'}")
    if revision == 1 and previous_sha256 != "none":
        errors.append("revision 1 requires Previous SHA-256 none")
    if revision > 1 and not SHA256_PATTERN.fullmatch(previous_sha256):
        errors.append("later revision requires lowercase 64-character Previous SHA-256")
    if errors:
        return None, errors
    return ReportMetadata(report_id, revision, previous_sha256, phase), []


def parse_report(text: str) -> tuple[ParsedReport, list[str]]:
    sections = markdown_sections(text)
    tables = {
        name: parse_section_table(section) for name, section in sections.items()
    }
    metadata, errors = parse_metadata(tables.get("Report State", ()))
    return ParsedReport(text, metadata, sections, tables), sorted(set(errors))


def validate_baseline(report: ParsedReport) -> list[str]:
    if report.metadata is None or report.metadata.revision != 1:
        return []
    impacts = {
        unquote(row.get("ID", ""))
        for row in report.tables.get("Impact Ledger", ())
        if IMPACT_PATTERN.fullmatch(unquote(row.get("ID", "")))
    }
    delta = {
        unquote(row.get("Category", "")): set(IMPACT_PATTERN.findall(row.get("Impact IDs", "")))
        for row in report.tables.get("Impact Delta", ())
    }
    errors: list[str] = []
    for impact_id in sorted(impacts):
        if impact_id not in delta.get("new", set()):
            errors.append(f"revision 1 impact {impact_id} must be new")
    for category, impact_ids in delta.items():
        if category != "new":
            for impact_id in sorted(impact_ids):
                errors.append(
                    f"revision 1 impact {impact_id} must be new, not {category}"
                )
    return errors


def validate_evidence_bases(report: ParsedReport) -> list[str]:
    errors: list[str] = []
    evidence_sections = (
        ("Current Behavior", "Invariant ID", "Evidence level", "Evidence", "invariant"),
        ("Impact Ledger", "ID", "Evidence Level", "Evidence", "impact"),
    )
    for section, id_column, level_column, evidence_column, label in evidence_sections:
        for row in report.tables.get(section, ()):
            identifier = entity_id(row, id_column, f"unknown {label}")
            level = unquote(row.get(level_column, "")).lower()
            evidence = row.get(evidence_column, "")
            if level in EVIDENCE_LEVELS and not present(evidence):
                errors.append(
                    f"{label} {identifier} evidence level {level} requires an evidence basis"
                )
    for row in report.tables.get("Current Behavior", ()):
        identifier = entity_id(row, "Invariant ID", "unknown invariant")
        if not present(row.get("Current behavior", "")):
            errors.append(f"invariant {identifier} requires a current behavior")
    return errors


def validate_impact_semantics(report: ParsedReport) -> list[str]:
    errors: list[str] = []
    for row in report.tables.get("Impact Ledger", ()):
        impact_id = entity_id(row, "ID", "unknown impact")
        category = unquote(row.get("Category", "")).lower()
        severity = unquote(row.get("Severity", "")).lower()
        state = unquote(row.get("State", "")).lower()
        if not category:
            errors.append(f"impact {impact_id} requires a category")
        elif category not in IMPACT_CATEGORIES:
            errors.append(f"impact {impact_id} has invalid category {category}")
        if not severity:
            errors.append(f"impact {impact_id} requires severity")
        elif severity not in SEVERITIES:
            errors.append(f"impact {impact_id} has invalid severity {severity}")
        if state != "superseded" and not references(
            row.get("Acceptance Criteria", ""), "AC-"
        ):
            errors.append(f"impact {impact_id} requires acceptance criteria")
        if state == "superseded" and not (
            present(row.get("Evidence", ""))
            or references(row.get("Decision", ""), "DEC-")
        ):
            errors.append(f"superseded impact {impact_id} requires successor or rationale")
    return errors


def validate_relationship_semantics(report: ParsedReport) -> list[str]:
    errors: list[str] = []
    for row in report.tables.get("Original Requirement", ()):
        requirement_id = entity_id(row, "Requirement ID", "unknown requirement")
        if not present(row.get("Original request", "")):
            errors.append(f"requirement {requirement_id} requires an original request")
        if not present(row.get("Source", "")):
            errors.append(f"requirement {requirement_id} requires a source")
    for row in report.tables.get("Current Refined Requirement", ()):
        requirement_id = entity_id(row, "Requirement ID", "unknown requirement")
        if not present(row.get("Revision", "")):
            errors.append(f"requirement {requirement_id} requires a refined revision")
    for row in report.tables.get("Preserved Invariants", ()):
        invariant_id = entity_id(row, "Invariant ID", "unknown invariant")
        if not references(row.get("Must preserve for requirement", ""), "REQ-"):
            errors.append(
                f"preserved invariant {invariant_id} requires a requirement link"
            )
        if not references(row.get("Affected impacts", ""), "IMP-"):
            errors.append(f"preserved invariant {invariant_id} requires affected impacts")
        if not present(row.get("Evidence", "")):
            errors.append(f"preserved invariant {invariant_id} requires evidence")
    for row in report.tables.get("Acceptance and Regression Criteria", ()):
        criterion_id = entity_id(row, "Criterion ID", "unknown criterion")
        if not references(row.get("Requirement", ""), "REQ-"):
            errors.append(f"criterion {criterion_id} requires a requirement link")
        if not references(row.get("Impact", ""), "IMP-"):
            errors.append(f"criterion {criterion_id} requires an impact link")
        if not references(row.get("Invariant", ""), "INV-"):
            errors.append(f"criterion {criterion_id} requires an invariant link")
        if not present(row.get("Observable criterion", "")):
            errors.append(
                f"criterion {criterion_id} requires a nonempty observable criterion"
            )
        if not present(row.get("Evidence/test", "")):
            errors.append(f"criterion {criterion_id} requires evidence or test")
    for row in report.tables.get("Unresolved, Deferred, and Blocked Items", ()):
        impact_id = entity_id(row, "Impact ID", "unknown impact")
        if not present(row.get("Information gap or rationale", "")):
            errors.append(f"unresolved impact {impact_id} requires a rationale")
        if not present(row.get("Next owner", "")):
            errors.append(f"unresolved impact {impact_id} requires a next owner")
    return errors


def validate_scope_semantics(report: ParsedReport) -> list[str]:
    rows = report.tables.get("Analysis Scope and Limitations", ())
    if not rows or not any(all(present(value) for value in row.values()) for row in rows):
        return ["analysis scope requires a substantive row"]
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        for column in (
            "Scope or limitation",
            "Inspected evidence",
            "Consequence for confidence",
        ):
            if not present(row.get(column, "")):
                errors.append(f"analysis scope row {index} requires {column}")
    return errors


def validate_handoff_semantics(report: ParsedReport) -> list[str]:
    rows = report.tables.get("Planning Handoff", ())
    if len(rows) != 1:
        return ["Planning Handoff requires exactly one row"]
    row = rows[0]
    errors: list[str] = []
    for column in (
        "Refined requirement",
        "Report IDs",
        "Remaining risks",
        "Acceptance criteria",
        "Selected planning workflow",
    ):
        if not present(row.get(column, "")):
            errors.append(f"Planning Handoff requires {column}")
    workflow = unquote(row.get("Selected planning workflow", "")).lower()
    if report.metadata and report.metadata.phase == "pre-decision" and workflow != "not ready":
        errors.append("pre-decision Planning Handoff workflow must be Not ready")
    impact_rows = report.tables.get("Impact Ledger", ())
    states = {
        entity_id(impact, "ID", "unknown impact"): unquote(impact.get("State", "")).lower()
        for impact in impact_rows
    }
    if any(state == "blocked" for state in states.values()) and workflow != "not ready":
        errors.append("blocked impacts require Planning Handoff workflow Not ready")
    remaining = references(row.get("Remaining risks", ""), "IMP-")
    for impact_id, state in states.items():
        if state in {"accepted", "deferred"} and impact_id not in remaining:
            errors.append(f"remaining risks must name {state} impact {impact_id}")
    return errors


def validate_semantics(report: ParsedReport) -> list[str]:
    errors: list[str] = []
    for validator in (
        validate_evidence_bases,
        validate_impact_semantics,
        validate_relationship_semantics,
        validate_scope_semantics,
        validate_handoff_semantics,
    ):
        errors.extend(validator(report))
    return sorted(set(errors))
