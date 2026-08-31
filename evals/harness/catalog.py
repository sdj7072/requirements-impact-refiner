"""Strict loading and selection for the fixed evaluation catalog."""

import json
from collections.abc import Iterable, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from .models import CaseSpec, CaseTurn

_EVALS_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CASES_PATH = _EVALS_ROOT / "cases.json"
_DEFAULT_LINEAGE_PATH = _EVALS_ROOT / "installed-v0.3-lineage-cases.json"
_KNOWN_KINDS = frozenset(("positive", "negative", "integration", "lineage"))
_KNOWN_MODES = frozenset(
    ("generic", "codex", "claude-code", "superpowers", "claude-feature-dev", "spec-kit")
)
_LINEAGE_TRANSITIONS = frozenset(("unchanged", "reopened", "rejected"))
MAX_FIXTURE_FILES = 32
MAX_FIXTURE_PATH_BYTES = 4096
MAX_FIXTURE_CONTENT_BYTES = 64 * 1024
MAX_FIXTURE_TOTAL_BYTES = 256 * 1024
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
        raise CatalogError(f"cannot read catalog {path}: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise CatalogError(f"catalog {path} must contain a cases list")
    return payload["cases"]


def _required_string(value: Any, field: str, case_id: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"{case_id} {field} must be a non-blank string")
    return value


def _rubric_array(value: Any, field: str, case_id: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CatalogError(f"{case_id} {field} must be a list")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise CatalogError(f"{case_id} {field} entries must be non-blank strings")
    return tuple(value)


def _modes(value: Any, case_id: str) -> tuple[str, ...]:
    modes = _rubric_array(value, "modes", case_id)
    unknown = set(modes).difference(_KNOWN_MODES)
    if unknown:
        raise CatalogError("{} has unknown modes: {}".format(case_id, ", ".join(sorted(unknown))))
    return modes


def _fixture_files(
    value: Any,
    case_id: str,
    rubrics: tuple[str, ...],
    *,
    field: str,
    policy: str,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list) or len(value) > MAX_FIXTURE_FILES:
        raise CatalogError(f"{case_id} {field} must be a bounded list")
    fixtures = []
    paths = set()
    total_bytes = 0
    for row in value:
        if not isinstance(row, dict) or set(row) != {"path", "content"}:
            raise CatalogError(f"{case_id} fixture file must contain path and content")
        path = _required_string(row["path"], "fixture path", case_id)
        content = _required_string(row["content"], "fixture content", case_id)
        pure = PurePosixPath(path)
        if (
            pure.is_absolute()
            or path != pure.as_posix()
            or "\\" in path
            or any(part in {"", ".", ".."} for part in pure.parts)
            or (pure.parts and pure.parts[0] == ".requirements-impact-refiner")
            or any(ord(character) < 32 or ord(character) == 127 for character in path)
        ):
            raise CatalogError(f"{case_id} fixture path is unsafe")
        try:
            path_bytes = len(path.encode("utf-8"))
            content_bytes = len(content.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise CatalogError(f"{case_id} fixture file is not valid UTF-8") from error
        if path_bytes > MAX_FIXTURE_PATH_BYTES or content_bytes > MAX_FIXTURE_CONTENT_BYTES:
            raise CatalogError(f"{case_id} fixture file exceeds its byte limit")
        if path in paths:
            raise CatalogError(f"{case_id} fixture path is duplicated")
        paths.add(path)
        total_bytes += path_bytes + content_bytes
        fixtures.append((path, content))
    if total_bytes > MAX_FIXTURE_TOTAL_BYTES:
        raise CatalogError(f"{case_id} fixture files exceed their total byte limit")
    if policy == "required" and not fixtures:
        raise CatalogError(f"{case_id} requires repository fixtures")
    if policy == "forbidden" and fixtures:
        raise CatalogError(f"{case_id} forbids {field}")
    fixture_text = "\n".join(path + "\n" + content for path, content in fixtures).casefold()
    if any(rubric.casefold() in fixture_text for rubric in rubrics):
        raise CatalogError(f"{case_id} fixture leaks a scoring rubric")
    return tuple(fixtures)


def _turns(value: Any, case_id: str, require_two: bool) -> tuple[CaseTurn, ...]:
    if not isinstance(value, list) or not value:
        raise CatalogError(f"{case_id} turns must be a non-empty list")
    if require_two and len(value) != 2:
        raise CatalogError(f"{case_id} lineage cases must contain exactly two turns")

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
        raise CatalogError(f"{case_id} has unknown kind: {kind!r}")
    if lineage != (kind == "lineage"):
        raise CatalogError(f"{case_id} is in the wrong catalog")

    if lineage:
        turns = _turns(raw.get("turns"), case_id, require_two=True)
        expected_transition = _required_string(
            raw.get("expected_transition"), "expected_transition", case_id
        )
        if expected_transition not in _LINEAGE_TRANSITIONS:
            raise CatalogError(f"{case_id} has unsupported transition: {expected_transition}")
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
            "{} repeats rubrics across must_detect and must_not_do: {}".format(
                case_id, ", ".join(sorted(duplicated_rubrics))
            )
        )
    fixture_files = _fixture_files(
        raw.get("fixture_files"),
        case_id,
        (*must_detect, *must_not_do),
        field="fixture_files",
        policy=(
            "required"
            if kind in {"positive", "lineage"} or case_id == "INT-superpowers"
            else "forbidden"
        ),
    )
    followup_fixture_files = _fixture_files(
        raw.get("followup_fixture_files"),
        case_id,
        (*must_detect, *must_not_do),
        field="followup_fixture_files",
        policy="optional" if kind == "lineage" else "forbidden",
    )

    return CaseSpec(
        id=case_id,
        kind=kind,
        turns=turns,
        must_detect=must_detect,
        must_not_do=must_not_do,
        modes=_modes(raw.get("modes"), case_id),
        expected_transition=expected_transition,
        fixture_files=fixture_files,
        followup_fixture_files=followup_fixture_files,
    )


def load_catalog(
    cases_path: Optional[Path] = None, lineage_path: Optional[Path] = None
) -> tuple[CaseSpec, ...]:
    """Load the base and lineage catalogs without mutating their source files."""
    base_path = Path(cases_path) if cases_path is not None else _DEFAULT_CASES_PATH
    lineage_catalog_path = Path(lineage_path) if lineage_path is not None else _DEFAULT_LINEAGE_PATH
    cases = tuple(_case_from_raw(raw, lineage=False) for raw in _read_cases(base_path))
    lineage_cases = tuple(
        _case_from_raw(raw, lineage=True) for raw in _read_cases(lineage_catalog_path)
    )
    all_cases = cases + lineage_cases
    ids = [case.id for case in all_cases]
    if len(ids) != len(set(ids)):
        raise CatalogError("catalog contains duplicate case IDs")
    return all_cases


def load_all() -> tuple[CaseSpec, ...]:
    """Load the checked-in evaluation catalog used by installed-client suites."""
    return load_catalog()


def select_suite(cases: Iterable[CaseSpec], suite: str) -> tuple[CaseSpec, ...]:
    """Return a deterministic suite from a validated complete catalog."""
    case_list = tuple(cases)
    by_id = {case.id: case for case in case_list}
    if len(by_id) != len(case_list):
        raise CatalogError("cannot select a suite from duplicate case IDs")

    if suite == "installed-superpowers":
        selected = tuple(
            case
            for case in case_list
            if case.kind in {"positive", "negative", "lineage"} or case.id == "INT-superpowers"
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
            raise CatalogError("smoke suite is missing: {}".format(", ".join(missing)))
        return tuple(by_id[case_id] for case_id in _SMOKE_CASE_IDS)
    raise CatalogError(f"unknown suite: {suite}")
