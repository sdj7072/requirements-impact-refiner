"""Deterministic policy scoring for one-call Fast Scan evidence."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

CASE_IDS = (
    "GRAPH-api-mobile-cache-migration",
    "GRAPH-auth-role-audit-consumer",
    "GRAPH-event-retry-idempotency-side-effect",
    "GRAPH-schema-serializer-backfill-export",
    "GRAPH-config-deploy-worker-health",
    "GRAPH-negative-no-change",
)


@dataclass(frozen=True)
class FastScanCase:
    id: str
    kind: str
    required_seeds: tuple[tuple[str, str], ...]
    minimum_path_distance: int
    maximum_output_words: int
    maximum_scan_ms: int
    controller_required: bool


@dataclass(frozen=True)
class FastScanScore:
    case_id: str
    passed: bool
    findings: tuple[str, ...]


def load_fast_scan_cases(path: Optional[Path] = None) -> tuple[FastScanCase, ...]:
    selected = Path(path) if path else Path(__file__).resolve().parents[1] / "fast-scan-cases.json"
    value = json.loads(selected.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "cases"}
        or value["schema_version"] != 1
    ):
        raise ValueError("Fast Scan catalog envelope is invalid")
    if not isinstance(value["cases"], list):
        raise ValueError("Fast Scan catalog cases are invalid")
    rows: list[FastScanCase] = []
    for raw in value["cases"]:
        if set(raw) != {
            "id",
            "kind",
            "required_seeds",
            "minimum_path_distance",
            "maximum_output_words",
            "maximum_scan_ms",
            "controller_required",
        }:
            raise ValueError("Fast Scan case fields are invalid")
        seeds = tuple((row["term"], row["location"]) for row in raw["required_seeds"])
        rows.append(
            FastScanCase(
                raw["id"],
                raw["kind"],
                seeds,
                raw["minimum_path_distance"],
                raw["maximum_output_words"],
                raw["maximum_scan_ms"],
                raw["controller_required"],
            )
        )
    result = tuple(rows)
    if tuple(row.id for row in result) != CASE_IDS:
        raise ValueError("Fast Scan catalog IDs are invalid")
    return result


def score_fast_scan(case: FastScanCase, result: Mapping[str, object]) -> FastScanScore:
    findings: list[str] = []
    calls = result.get("controller_calls")
    if case.kind == "negative":
        if calls != []:
            findings.append("negative case must not call controller")
        if result.get("status") != "not_applicable":
            findings.append("negative case status is invalid")
    else:
        if calls != ["rir_scan"]:
            findings.append("Fast Scan must call only rir_scan once")
        if result.get("status") != "complete":
            findings.append("positive Fast Scan must complete")
        raw_seeds = result.get("seeds", [])
        seed_rows = raw_seeds if isinstance(raw_seeds, list) else []
        actual = {
            (row.get("term"), row.get("location")) for row in seed_rows if isinstance(row, dict)
        }
        if not set(case.required_seeds).issubset(actual):
            findings.append("required seeds are missing")
        observed_distance = result.get("maximum_path_distance", -1)
        if (
            not isinstance(observed_distance, int)
            or isinstance(observed_distance, bool)
            or (observed_distance < case.minimum_path_distance)
        ):
            findings.append("required distant path is missing")
        elapsed = result.get("elapsed_ms")
        if (
            isinstance(elapsed, bool)
            or not isinstance(elapsed, int)
            or elapsed > case.maximum_scan_ms
        ):
            findings.append("Fast Scan exceeds 30 seconds")
        if len(str(result.get("display_text", "")).split()) > case.maximum_output_words:
            findings.append("Fast Scan exceeds 180 words")
        if result.get("uncovered_high_risk_nodes"):
            findings.append("Fast Scan leaves uncovered high-risk nodes")
    return FastScanScore(case.id, not findings, tuple(sorted(set(findings))))
