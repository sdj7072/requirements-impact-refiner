#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
from datetime import datetime, timezone
from typing import Mapping, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import compact_state
import impact_renderer
import report_store


MAX_BEGIN_BYTES = 256 * 1024
MAX_FINALIZE_BYTES = 2 * 1024 * 1024
MAX_STRING_BYTES = 64 * 1024
DRAFT_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
LOCAL_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}")
ADAPTERS = {"generic", "superpowers", "claude-feature-dev", "spec-kit"}
ANALYSIS_KEYS = {
    "phase", "refined_requirement", "invariants", "impacts",
    "decision_needed", "decisions", "criteria", "unresolved", "scope",
    "workflow",
}
ROW_KEYS = {
    "invariants": {"key", "behavior", "evidence_level", "evidence"},
    "impacts": {"key", "category", "severity", "state", "evidence_level", "evidence", "invariant_keys", "decision_keys", "criterion_keys", "summary"},
    "decisions": {"key", "choice", "accepted_impact_keys", "rationale"},
    "criteria": {"key", "impact_key", "invariant_key", "criterion", "evidence"},
    "unresolved": {"impact_key", "state", "rationale", "decision_key", "owner"},
    "scope": {"boundary", "evidence", "confidence"},
}
SUMMARY_KEYS = {"changed_feature", "possible_issue", "affected", "trigger", "prevention"}


def _load_settings_module():
    path = SCRIPT_DIR / "resolve-settings.py"
    spec = importlib.util.spec_from_file_location("rir_resolve_settings", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETTINGS = _load_settings_module()


@dataclass(frozen=True)
class BeginRequest:
    repo_root: Path
    request: str
    repository_evidence: Tuple[str, ...]
    adapter: str
    audience_override: Optional[str] = None
    delivery_override: Optional[str] = None


@dataclass(frozen=True)
class DraftResult:
    draft_id: str
    draft_path: Path
    report_id: str
    revision: int
    previous_sha256: str
    settings: Mapping[str, str]
    prior_state: Optional[Mapping[str, object]]


@dataclass(frozen=True)
class FinalizeRequest:
    repo_root: Path
    draft_id: str
    analysis: Mapping[str, object]


@dataclass(frozen=True)
class FinalizeResult:
    status: str
    report_id: str
    revision: int
    delivery: str
    display_text: str
    state_path: Path
    markdown_path: Path
    markdown_sha256: str


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _root(path: Path) -> Path:
    try:
        root = Path(path).resolve(strict=True)
    except OSError as error:
        raise ValueError(f"repository root is unavailable: {error}") from error
    if not root.is_dir():
        raise ValueError("repository root must be an existing directory")
    return root


def _safe_directory(root: Path, relative: Path) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"controller path uses a symlink: {current}")
        if current.exists() and not current.is_dir():
            raise ValueError(f"controller path is not a directory: {current}")
        if not current.exists():
            current.mkdir()
    return current


def _all_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _all_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _all_strings(item)


def _bounded(value: object, maximum: int, label: str) -> bytes:
    payload = _canonical_bytes(value)
    if len(payload) > maximum:
        unit = "256 KiB" if maximum == MAX_BEGIN_BYTES else "2 MiB"
        raise ValueError(f"{label} exceeds {unit}")
    if any(len(text.encode("utf-8")) > MAX_STRING_BYTES for text in _all_strings(value)):
        raise ValueError(f"{label} contains a string larger than 64 KiB")
    return payload


def _next_report_id(root: Path) -> str:
    reports = root / ".requirements-impact-refiner" / "reports"
    existing = set()
    if reports.is_dir() and not reports.is_symlink():
        existing = {
            path.name for path in reports.iterdir()
            if path.is_dir() and re.fullmatch(r"RPT-\d{3}", path.name)
        }
    for number in range(1, 1000):
        candidate = f"RPT-{number:03d}"
        if candidate not in existing:
            return candidate
    raise ValueError("no report IDs remain")


def _current_lineage(root: Path):
    reports = root / ".requirements-impact-refiner" / "reports"
    if not reports.exists():
        return None
    if reports.is_symlink() or not reports.is_dir():
        raise ValueError("report root must be a real directory")
    report_ids = sorted(
        path.name
        for path in reports.iterdir()
        if path.is_dir()
        and not path.is_symlink()
        and re.fullmatch(r"RPT-\d{3}", path.name)
        and (path / "current.json").is_file()
    )
    if not report_ids:
        return None
    if len(report_ids) != 1:
        raise ValueError("multiple current reports require an explicit report ID")
    current = report_store.load_current(root, report_ids[0])
    if current is None:
        return None
    prior_state, errors = compact_state.load_state_bytes(current.state_path.read_bytes())
    if errors or prior_state is None:
        raise ValueError("current report state is invalid")
    key_map = None
    drafts = root / ".requirements-impact-refiner" / "drafts"
    if drafts.is_dir() and not drafts.is_symlink():
        for path in sorted(drafts.glob("*.json")):
            if path.is_symlink():
                continue
            try:
                draft = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            published = draft.get("published") if isinstance(draft, dict) else None
            if (
                isinstance(published, dict)
                and draft.get("consumed") is True
                and published.get("report_id") == current.report_id
                and published.get("revision") == current.revision
                and isinstance(draft.get("key_map"), dict)
            ):
                key_map = draft["key_map"]
    if key_map is None:
        raise ValueError("current report is missing controller key lineage")
    return current, prior_state, key_map


def _draft_path(root: Path, draft_id: str) -> Path:
    if DRAFT_ID_PATTERN.fullmatch(draft_id) is None:
        raise ValueError("invalid draft ID")
    directory = _safe_directory(
        root, Path(".requirements-impact-refiner") / "drafts"
    )
    return directory / f"{draft_id}.json"


def begin_refinement(request: BeginRequest) -> DraftResult:
    root = _root(request.repo_root)
    if request.adapter not in ADAPTERS:
        raise ValueError(f"invalid adapter: {request.adapter}")
    if not isinstance(request.request, str) or not request.request.strip():
        raise ValueError("request must be nonempty")
    if not isinstance(request.repository_evidence, tuple) or any(
        not isinstance(item, str) or not item.strip()
        for item in request.repository_evidence
    ):
        raise ValueError("repository_evidence must contain nonempty strings")
    _bounded(
        {"request": request.request, "repository_evidence": request.repository_evidence},
        MAX_BEGIN_BYTES,
        "begin input",
    )
    settings = SETTINGS.resolve(
        root, request.audience_override, request.delivery_override
    )
    current_lineage = _current_lineage(root)
    if current_lineage is None:
        report_id = _next_report_id(root)
        revision = 1
        previous_sha256 = "none"
        prior_state = None
        prior_key_map = None
    else:
        current, prior_state, prior_key_map = current_lineage
        report_id = current.report_id
        revision = current.revision + 1
        previous_sha256 = current.markdown_sha256
    draft_id = secrets.token_hex(16)
    path = _draft_path(root, draft_id)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    draft = {
        "schema_version": 1,
        "draft_id": draft_id,
        "repo_root": str(root),
        "request": request.request,
        "request_sha256": hashlib.sha256(request.request.encode("utf-8")).hexdigest(),
        "repository_evidence": list(request.repository_evidence),
        "adapter": request.adapter,
        "settings": dict(settings),
        "report_id": report_id,
        "revision": revision,
        "previous_sha256": previous_sha256,
        "prior_state": prior_state,
        "prior_key_map": prior_key_map,
        "created_at": now,
        "consumed": False,
    }
    try:
        with path.open("xb") as stream:
            stream.write(_canonical_bytes(draft))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o600)
    except OSError as error:
        raise ValueError(f"cannot create draft: {error}") from error
    return DraftResult(
        draft_id=draft_id,
        draft_path=path,
        report_id=report_id,
        revision=revision,
        previous_sha256=previous_sha256,
        settings=settings,
        prior_state=prior_state,
    )


def load_draft(repo_root: Path, draft_id: str) -> dict[str, object]:
    root = _root(repo_root)
    path = _draft_path(root, draft_id)
    if path.is_symlink() or not path.is_file():
        raise ValueError("draft does not exist")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"draft is invalid: {error}") from error
    if not isinstance(value, dict) or value.get("draft_id") != draft_id:
        raise ValueError("draft identity is invalid")
    if value.get("repo_root") != str(root):
        raise ValueError("draft repository root does not match")
    return value


def _check_keys(label: str, value: object, expected: set[str]) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise ValueError(f"unknown {label} key {unknown[0]}")
    if missing:
        raise ValueError(f"missing {label} key {missing[0]}")


def _local_key(value: object, label: str) -> str:
    if not isinstance(value, str) or LOCAL_KEY_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid {label} local key")
    return value


def _validate_analysis(analysis: Mapping[str, object]) -> None:
    _check_keys("analysis", analysis, ANALYSIS_KEYS)
    if analysis["phase"] not in {"pre-decision", "post-decision"}:
        raise ValueError("invalid analysis phase")
    if not isinstance(analysis["refined_requirement"], str) or not analysis["refined_requirement"].strip():
        raise ValueError("refined_requirement must be nonempty")
    for section, expected in ROW_KEYS.items():
        rows = analysis[section]
        if not isinstance(rows, list):
            raise ValueError(f"{section} must be an array")
        keys = []
        for row in rows:
            _check_keys(section[:-1], row, expected)
            if "key" in row:
                keys.append(_local_key(row["key"], section[:-1]))
            if section == "impacts":
                _check_keys("impact summary", row["summary"], SUMMARY_KEYS)
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate {section} local key")
    if analysis["phase"] == "pre-decision":
        _check_keys("decision_needed", analysis["decision_needed"], {"question", "options"})
        options = analysis["decision_needed"]["options"]
        if not isinstance(options, list) or not 2 <= len(options) <= 3:
            raise ValueError("decision_needed requires two or three options")
        for option in options:
            _check_keys("decision option", option, {"option", "impact_keys", "tradeoff"})
        if analysis["decisions"]:
            raise ValueError("pre-decision analysis forbids decisions")
    else:
        if analysis["decision_needed"] is not None or not analysis["decisions"]:
            raise ValueError("post-decision analysis requires decisions only")
    if not isinstance(analysis["scope"], list) or not analysis["scope"]:
        raise ValueError("scope requires at least one row")
    if not isinstance(analysis["workflow"], str) or not analysis["workflow"].strip():
        raise ValueError("workflow must be nonempty")


def _ids(rows, prefix, prior=None):
    prior = {} if prior is None else dict(prior)
    result = {}
    used_numbers = {
        int(identifier.rsplit("-", 1)[1])
        for identifier in prior.values()
        if isinstance(identifier, str) and re.fullmatch(rf"{prefix}-\d{{3}}", identifier)
    }
    next_number = 1
    for row in rows:
        key = row["key"]
        if key in prior:
            result[key] = prior[key]
            continue
        while next_number in used_numbers:
            next_number += 1
        result[key] = f"{prefix}-{next_number:03d}"
        used_numbers.add(next_number)
        next_number += 1
    return result


def _map_keys(values, mapping, label):
    result = []
    for value in values:
        key = _local_key(value, label)
        if key not in mapping:
            raise ValueError(f"unknown {label} key {key}")
        result.append(mapping[key])
    return result


def _build_state(draft, analysis):
    _validate_analysis(analysis)
    prior_state = draft.get("prior_state")
    prior_key_map = draft.get("prior_key_map") or {}
    requirement_id = (
        prior_state["original_requirement"]["id"]
        if isinstance(prior_state, dict)
        else "REQ-001"
    )
    if prior_key_map:
        missing_impacts = sorted(
            set(prior_key_map.get("impacts", {}))
            - {row["key"] for row in analysis["impacts"]}
        )
        if missing_impacts:
            raise ValueError(f"impact key disappeared: {missing_impacts[0]}")
    invariant_ids = _ids(analysis["invariants"], "INV", prior_key_map.get("invariants"))
    impact_ids = _ids(analysis["impacts"], "IMP", prior_key_map.get("impacts"))
    decision_ids = _ids(analysis["decisions"], "DEC", prior_key_map.get("decisions"))
    criterion_ids = _ids(analysis["criteria"], "AC", prior_key_map.get("criteria"))
    key_map = {
        "invariants": invariant_ids,
        "impacts": impact_ids,
        "decisions": decision_ids,
        "criteria": criterion_ids,
    }
    impacts = []
    for row in analysis["impacts"]:
        impacts.append({
            "id": impact_ids[row["key"]],
            "requirement": requirement_id,
            "category": row["category"],
            "severity": row["severity"],
            "state": row["state"],
            "evidence_level": row["evidence_level"],
            "evidence": row["evidence"],
            "invariants": _map_keys(row["invariant_keys"], invariant_ids, "invariant"),
            "decisions": _map_keys(row["decision_keys"], decision_ids, "decision"),
            "criteria": _map_keys(row["criterion_keys"], criterion_ids, "criterion"),
        })
    current_behavior = [{
        "id": invariant_ids[row["key"]], "behavior": row["behavior"],
        "evidence_level": row["evidence_level"], "evidence": row["evidence"],
    } for row in analysis["invariants"]]
    preserved = []
    for row in analysis["invariants"]:
        affected = [
            impact_ids[impact["key"]] for impact in analysis["impacts"]
            if row["key"] in impact["invariant_keys"]
        ]
        preserved.append({
            "id": invariant_ids[row["key"]], "requirement": requirement_id,
            "impacts": affected, "evidence": row["evidence"],
        })
    decisions = [{
        "id": decision_ids[row["key"]], "choice": row["choice"],
        "requirement": requirement_id,
        "accepted_impacts": _map_keys(row["accepted_impact_keys"], impact_ids, "impact"),
        "rationale": row["rationale"],
    } for row in analysis["decisions"]]
    criteria = [{
        "id": criterion_ids[row["key"]], "requirement": requirement_id,
        "impact": _map_keys([row["impact_key"]], impact_ids, "impact")[0],
        "invariant": _map_keys([row["invariant_key"]], invariant_ids, "invariant")[0],
        "criterion": row["criterion"], "evidence": row["evidence"],
    } for row in analysis["criteria"]]
    decision_needed = None
    if analysis["phase"] == "pre-decision":
        decision_needed = {
            "question": analysis["decision_needed"]["question"],
            "options": [{
                "option": row["option"],
                "impacts": _map_keys(row["impact_keys"], impact_ids, "impact"),
                "tradeoff": row["tradeoff"],
            } for row in analysis["decision_needed"]["options"]],
        }
    unresolved = [{
        "impact": _map_keys([row["impact_key"]], impact_ids, "impact")[0],
        "state": row["state"], "rationale": row["rationale"],
        "decision": None if row["decision_key"] is None else _map_keys([row["decision_key"]], decision_ids, "decision")[0],
        "owner": row["owner"],
    } for row in analysis["unresolved"]]
    remaining = [row["id"] for row in impacts if row["state"] in {"accepted", "deferred", "blocked"}]
    if not remaining:
        remaining = [row["id"] for row in impacts]
    all_report_ids = [requirement_id] + list(invariant_ids.values()) + list(impact_ids.values()) + list(decision_ids.values())
    summary = [{
        "impact_id": impact_ids[row["key"]],
        **row["summary"], "severity": row["severity"], "status": row["state"],
    } for row in analysis["impacts"]]
    first_decision = decisions[0]["id"] if decisions else None
    delta = {category: [] for category in compact_state.DELTA_CATEGORIES}
    if prior_state is None:
        delta["new"] = list(impact_ids.values())
    else:
        previous_states = {row["id"]: row["state"] for row in prior_state["impacts"]}
        terminal = {"resolved", "accepted", "superseded"}
        active = {"detected", "refining", "mitigated", "deferred", "blocked"}
        state_category = {
            "detected": "unchanged", "refining": "unchanged",
            "mitigated": "mitigated", "resolved": "resolved",
            "accepted": "accepted", "deferred": "deferred",
            "blocked": "blocked", "superseded": "superseded",
        }
        for impact in impacts:
            previous = previous_states.get(impact["id"])
            if previous is None:
                category = "new"
            elif previous == impact["state"]:
                category = "unchanged"
            elif previous in terminal and impact["state"] in active:
                category = "reopened"
            else:
                category = state_category[impact["state"]]
            delta[category].append(impact["id"])
    prior_history = [] if prior_state is None else list(prior_state["history"])
    original_requirement = (
        {"id": requirement_id, "request": draft["request"], "source": "User request and supplied repository evidence."}
        if prior_state is None
        else prior_state["original_requirement"]
    )
    state = {
        "schema_version": 1,
        "report": {"id": draft["report_id"], "revision": draft["revision"], "previous_sha256": draft["previous_sha256"], "phase": analysis["phase"]},
        "settings": draft["settings"],
        "original_requirement": original_requirement,
        "refined_requirement": {"id": requirement_id, "revision": analysis["refined_requirement"], "decision": first_decision, "supersedes": []},
        "current_behavior": current_behavior,
        "preserved_invariants": preserved,
        "impacts": impacts,
        "decision_needed": decision_needed,
        "decisions": decisions,
        "delta": delta,
        "history": prior_history + [{"requirement": requirement_id, "revision": analysis["refined_requirement"], "decision": first_decision, "superseded_impacts": [], "summary": "Controller-created refinement revision."}],
        "criteria": criteria,
        "unresolved": unresolved,
        "scope": analysis["scope"],
        "handoff": {
            "refined_requirement": requirement_id if analysis["phase"] == "post-decision" else "Not ready until the pending decision is selected.",
            "report_ids": all_report_ids,
            "remaining_risks": remaining,
            "criteria": list(criterion_ids.values()),
            "workflow": (
                analysis["workflow"]
                if analysis["phase"] == "post-decision"
                else "Not ready"
            ),
        },
        "summary": summary,
    }
    errors = compact_state.validate_state(state)
    if errors:
        raise ValueError("; ".join(errors))
    return state, key_map


def _consume(path: Path, draft: dict[str, object], published, key_map) -> None:
    updated = dict(draft)
    updated["consumed"] = True
    updated["published"] = {
        "report_id": published.report_id,
        "revision": published.revision,
        "markdown_sha256": published.markdown_sha256,
    }
    updated["key_map"] = key_map
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=".draft-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(_canonical_bytes(updated))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError as error:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ValueError(f"cannot consume draft: {error}") from error


def finalize_refinement(request: FinalizeRequest) -> FinalizeResult:
    root = _root(request.repo_root)
    _bounded(request.analysis, MAX_FINALIZE_BYTES, "finalize input")
    draft = load_draft(root, request.draft_id)
    if draft.get("consumed") is True:
        raise ValueError("draft is already consumed")
    state, key_map = _build_state(draft, request.analysis)
    published = report_store.publish_revision(root, _canonical_bytes(state))
    stored_state, errors = compact_state.load_state_bytes(published.state_path.read_bytes())
    if errors or stored_state is None:
        raise ValueError("published state could not be verified")
    delivery = stored_state["settings"]["delivery"]
    display = (
        impact_renderer.render_compact(stored_state)
        if delivery == "compact"
        else impact_renderer.render_markdown(stored_state)
    )
    _consume(_draft_path(root, request.draft_id), draft, published, key_map)
    return FinalizeResult(
        status="published",
        report_id=published.report_id,
        revision=published.revision,
        delivery=delivery,
        display_text=display,
        state_path=published.state_path,
        markdown_path=published.markdown_path,
        markdown_sha256=published.markdown_sha256,
    )
