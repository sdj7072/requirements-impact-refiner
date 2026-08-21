#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Sequence


RPT_PATTERN = re.compile(r"RPT-\d{3}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
IMPACT_PATTERN = re.compile(r"\bIMP-\d{3}\b")


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
