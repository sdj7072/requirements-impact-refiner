"""Strict loading and selection for the fixed evaluation catalog."""

import json
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, Tuple

from .models import CaseSpec, CaseTurn


_EVALS_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CASES_PATH = _EVALS_ROOT / "cases.json"
_DEFAULT_LINEAGE_PATH = _EVALS_ROOT / "installed-v0.3-lineage-cases.json"
_KNOWN_KINDS = frozenset(("positive", "negative", "integration", "lineage"))
_KNOWN_MODES = frozenset(
    ("generic", "codex", "claude-code", "superpowers", "claude-feature-dev", "spec-kit")
)
_LINEAGE_TRANSITIONS = frozenset(("unchanged", "reopened", "rejected"))
_SMOKE_CASE_IDS = (
    "POS-authorization",
    "NEG-debugging",
    "INT-superpowers",
    "LINEAGE-stable-blocked",
    "LINEAGE-reopened",
    "LINEAGE-no-false-resolution",
)


class CatalogError(ValueError):
    """Raised when a checked-in evaluation case does not meet the contract."""


def _read_cases(path: Path) -> Sequence[Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogError("cannot read catalog %s: %s" % (path, error)) from error
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise CatalogError("catalog %s must contain a cases list" % path)
    return payload["cases"]


def _required_string(value: Any, field: str, case_id: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogError("%s %s must be a non-blank string" % (case_id, field))
    return value


def _rubric_array(value: Any, field: str, case_id: str) -> Tuple[str, ...]:
    if not isinstance(value, list):
        raise CatalogError("%s %s must be a list" % (case_id, field))
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise CatalogError("%s %s entries must be non-blank strings" % (case_id, field))
    return tuple(value)


def _modes(value: Any, case_id: str) -> Tuple[str, ...]:
    modes = _rubric_array(value, "modes", case_id)
    unknown = set(modes).difference(_KNOWN_MODES)
    if unknown:
        raise CatalogError("%s has unknown modes: %s" % (case_id, ", ".join(sorted(unknown))))
    return modes


def _turns(value: Any, case_id: str, require_two: bool) -> Tuple[CaseTurn, ...]:
    if not isinstance(value, list) or not value:
        raise CatalogError("%s turns must be a non-empty list" % case_id)
    if require_two and len(value) != 2:
        raise CatalogError("%s lineage cases must contain exactly two turns" % case_id)

    turns = []
    for index, raw_turn in enumerate(value, start=1):
        if not isinstance(raw_turn, dict):
            raise CatalogError("%s turn %d must be an object" % (case_id, index))
        prompt = _required_string(raw_turn.get("prompt"), "turn %d prompt" % index, case_id)
        evidence = _rubric_array(
            raw_turn.get("repository_evidence"),
            "turn %d repository_evidence" % index,
            case_id,
        )
        turns.append(CaseTurn(prompt=prompt, repository_evidence=evidence))
    return tuple(turns)


def _case_from_raw(raw: Any, lineage: bool) -> CaseSpec:
    if not isinstance(raw, dict):
        raise CatalogError("case must be an object")
    case_id = _required_string(raw.get("id"), "id", "case")
    kind = raw.get("kind")
    if not isinstance(kind, str) or kind not in _KNOWN_KINDS:
        raise CatalogError("%s has unknown kind: %r" % (case_id, kind))
    if lineage != (kind == "lineage"):
        raise CatalogError("%s is in the wrong catalog" % case_id)

    if lineage:
        turns = _turns(raw.get("turns"), case_id, require_two=True)
        expected_transition = _required_string(
            raw.get("expected_transition"), "expected_transition", case_id
        )
        if expected_transition not in _LINEAGE_TRANSITIONS:
            raise CatalogError("%s has unsupported transition: %s" % (case_id, expected_transition))
    else:
        prompt = _required_string(raw.get("request"), "request", case_id)
        evidence = _rubric_array(raw.get("repository_evidence"), "repository_evidence", case_id)
        turns = (CaseTurn(prompt=prompt, repository_evidence=evidence),)
        expected_transition = None

    must_detect = _rubric_array(raw.get("must_detect"), "must_detect", case_id)
    must_not_do = _rubric_array(raw.get("must_not_do"), "must_not_do", case_id)
    duplicated_rubrics = set(must_detect).intersection(must_not_do)
    if duplicated_rubrics:
        raise CatalogError(
            "%s repeats rubrics across must_detect and must_not_do: %s"
            % (case_id, ", ".join(sorted(duplicated_rubrics)))
        )

    return CaseSpec(
        id=case_id,
        kind=kind,
        turns=turns,
        must_detect=must_detect,
        must_not_do=must_not_do,
        modes=_modes(raw.get("modes"), case_id),
        expected_transition=expected_transition,
    )


def load_catalog(
    cases_path: Optional[Path] = None, lineage_path: Optional[Path] = None
) -> Tuple[CaseSpec, ...]:
    """Load the base and lineage catalogs without mutating their source files."""
    base_path = Path(cases_path) if cases_path is not None else _DEFAULT_CASES_PATH
    lineage_catalog_path = Path(lineage_path) if lineage_path is not None else _DEFAULT_LINEAGE_PATH
    cases = tuple(_case_from_raw(raw, lineage=False) for raw in _read_cases(base_path))
    lineage_cases = tuple(_case_from_raw(raw, lineage=True) for raw in _read_cases(lineage_catalog_path))
    all_cases = cases + lineage_cases
    ids = [case.id for case in all_cases]
    if len(ids) != len(set(ids)):
        raise CatalogError("catalog contains duplicate case IDs")
    return all_cases


def load_all() -> Tuple[CaseSpec, ...]:
    """Load the checked-in evaluation catalog used by installed-client suites."""
    return load_catalog()


def select_suite(cases: Iterable[CaseSpec], suite: str) -> Tuple[CaseSpec, ...]:
    """Return a deterministic suite from a validated complete catalog."""
    case_list = tuple(cases)
    by_id = {case.id: case for case in case_list}
    if len(by_id) != len(case_list):
        raise CatalogError("cannot select a suite from duplicate case IDs")

    if suite == "installed-superpowers":
        selected = tuple(
            case
            for case in case_list
            if case.kind in {"positive", "negative", "lineage"}
            or case.id == "INT-superpowers"
        )
        if len(selected) != 17:
            raise CatalogError("installed-superpowers suite must contain exactly 17 cases")
        if sum(case.kind == "positive" for case in selected) != 8:
            raise CatalogError("installed-superpowers suite must contain eight positive cases")
        if sum(case.kind == "negative" for case in selected) != 5:
            raise CatalogError("installed-superpowers suite must contain five negative cases")
        if [case.id for case in selected if case.kind == "integration"] != ["INT-superpowers"]:
            raise CatalogError("installed-superpowers suite must contain exactly INT-superpowers")
        if sum(case.kind == "lineage" for case in selected) != 3:
            raise CatalogError("installed-superpowers suite must contain three lineage cases")
        return selected
    if suite == "smoke":
        missing = [case_id for case_id in _SMOKE_CASE_IDS if case_id not in by_id]
        if missing:
            raise CatalogError("smoke suite is missing: %s" % ", ".join(missing))
        return tuple(by_id[case_id] for case_id in _SMOKE_CASE_IDS)
    raise CatalogError("unknown suite: %s" % suite)
