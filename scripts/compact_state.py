#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from typing import Mapping, Sequence


TOP_LEVEL_KEYS = {
    "schema_version", "report", "settings", "original_requirement",
    "refined_requirement", "current_behavior", "preserved_invariants",
    "impacts", "decision_needed", "decisions", "delta", "history",
    "criteria", "unresolved", "scope", "handoff", "summary",
}
OPTIONAL_TOP_LEVEL_KEYS = {"graph_paths"}
OBJECT_FIELDS = {
    "report": {"id", "revision", "previous_sha256", "phase"},
    "original_requirement": {"id", "request", "source"},
    "refined_requirement": {"id", "revision", "decision", "supersedes"},
    "handoff": {"refined_requirement", "report_ids", "remaining_risks", "criteria", "workflow"},
}
ROW_FIELDS = {
    "current_behavior": {"id", "behavior", "evidence_level", "evidence"},
    "preserved_invariants": {"id", "requirement", "impacts", "evidence"},
    "impacts": {"id", "requirement", "category", "severity", "state", "evidence_level", "evidence", "invariants", "decisions", "criteria"},
    "decisions": {"id", "choice", "requirement", "accepted_impacts", "rationale"},
    "history": {"requirement", "revision", "decision", "superseded_impacts", "summary"},
    "criteria": {"id", "requirement", "impact", "invariant", "criterion", "evidence"},
    "unresolved": {"impact", "state", "rationale", "decision", "owner"},
    "scope": {"boundary", "evidence", "confidence"},
    "summary": {"impact_id", "changed_feature", "possible_issue", "affected", "trigger", "severity", "prevention", "status"},
}
DECISION_NEEDED_FIELDS = {"question", "options"}
OPTION_FIELDS = {"option", "impacts", "tradeoff"}
DELTA_CATEGORIES = (
    "resolved", "mitigated", "unchanged", "accepted", "deferred",
    "blocked", "superseded", "reopened", "new",
)
IMPACT_CATEGORIES = {
    "functionality", "data", "interfaces", "authorization/privacy",
    "state/concurrency", "operations", "compatibility", "legal/policy",
    "regression",
}
IMPACT_STATES = {
    "detected", "refining", "mitigated", "resolved", "accepted",
    "deferred", "blocked", "superseded",
}
SEVERITIES = {"critical", "high", "medium", "low"}
EVIDENCE_LEVELS = {"verified", "inferred", "unknown"}
AUDIENCES = {"simple", "balanced", "technical"}
DELIVERIES = {"compact", "full"}
SETTING_SOURCES = {"request", "repository", "default"}
SETTING_FIELDS = {"audience", "audience_source", "delivery", "delivery_source"}
OPTIONAL_SETTING_FIELDS = {"impact_graph", "warnings", "flow", "flow_source"}
GRAPH_SETTING_FIELDS = {
    "enabled", "max_seconds", "target_seconds", "providers", "install_policy", "deep",
}
PHASES = {"pre-decision", "post-decision"}
ID_PATTERNS = {
    "report": re.compile(r"RPT-\d{3}"),
    "requirement": re.compile(r"REQ-\d{3}"),
    "invariant": re.compile(r"INV-\d{3}"),
    "impact": re.compile(r"IMP-\d{3}"),
    "decision": re.compile(r"DEC-\d{3}"),
    "criterion": re.compile(r"AC-\d{3}"),
}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
ACCEPTANCE_PATTERN = re.compile(r"\bAC-\d{3}\b")


def _mapping(value: object) -> bool:
    return isinstance(value, dict)


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(_nonempty(item) for item in value)


def _check_keys(label: str, value: object, expected: set[str]) -> list[str]:
    if not _mapping(value):
        return [f"{label} must be an object"]
    errors = [f"{label} missing key {key}" for key in sorted(expected - set(value))]
    errors.extend(f"{label} has unknown key {key}" for key in sorted(set(value) - expected))
    return errors


def _validate_graph_settings(value: object) -> list[str]:
    if not _mapping(value):
        return ["settings impact_graph must be an object"]
    errors = _check_keys("settings impact_graph", value, GRAPH_SETTING_FIELDS)
    if errors:
        return errors
    if not isinstance(value.get("enabled"), bool):
        errors.append("settings impact_graph enabled must be boolean")
    if not isinstance(value.get("deep"), bool):
        errors.append("settings impact_graph deep must be boolean")
    maximum = value.get("max_seconds")
    target = value.get("target_seconds")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or not 1 <= maximum <= 30:
        errors.append("settings impact_graph max_seconds must be an integer from 1 to 30")
    if not isinstance(target, int) or isinstance(target, bool) or target < 1:
        errors.append("settings impact_graph target_seconds must be a positive integer")
    elif isinstance(maximum, int) and not isinstance(maximum, bool) and target > maximum:
        errors.append("settings impact_graph target_seconds must not exceed max_seconds")
    providers = value.get("providers")
    if (
        not isinstance(providers, list)
        or not providers
        or any(not isinstance(provider, str) or not provider for provider in providers)
        or len(set(providers)) != len(providers)
    ):
        errors.append("settings impact_graph providers must be a non-empty list of unique names")
    if value.get("install_policy") != "never":
        errors.append("settings impact_graph install_policy must be never")
    return errors


def validate_structure(value: object) -> list[str]:
    if not _mapping(value):
        return ["state must contain a JSON object"]
    errors = [f"missing top-level key {key}" for key in sorted(TOP_LEVEL_KEYS - set(value))]
    errors.extend(f"unknown top-level key {key}" for key in sorted(set(value) - TOP_LEVEL_KEYS - OPTIONAL_TOP_LEVEL_KEYS))
    if errors:
        return errors
    if value["schema_version"] != 1:
        errors.append("schema_version must be 1")
    for name, fields in OBJECT_FIELDS.items():
        errors.extend(_check_keys(name, value[name], fields))
    settings = value["settings"]
    if not _mapping(settings):
        errors.append("settings must be an object")
    else:
        errors.extend(
            f"settings missing key {key}" for key in sorted(SETTING_FIELDS - set(settings))
        )
        errors.extend(
            f"settings has unknown key {key}"
            for key in sorted(set(settings) - SETTING_FIELDS - OPTIONAL_SETTING_FIELDS)
        )
        if "impact_graph" in settings:
            errors.extend(_validate_graph_settings(settings["impact_graph"]))
        if "warnings" in settings and not _string_list(settings["warnings"]):
            errors.append("settings warnings must be an array of non-empty strings")
    for name, fields in ROW_FIELDS.items():
        rows = value[name]
        if not isinstance(rows, list):
            errors.append(f"{name} must be an array")
            continue
        for index, row in enumerate(rows, start=1):
            errors.extend(_check_keys(f"{name} row {index}", row, fields))
    needed = value["decision_needed"]
    if needed is not None:
        errors.extend(_check_keys("decision_needed", needed, DECISION_NEEDED_FIELDS))
        if _mapping(needed) and "options" in needed:
            options = needed["options"]
            if not isinstance(options, list):
                errors.append("decision_needed options must be an array")
            else:
                for index, option in enumerate(options, start=1):
                    errors.extend(_check_keys(f"decision option {index}", option, OPTION_FIELDS))
    delta = value["delta"]
    errors.extend(_check_keys("delta", delta, set(DELTA_CATEGORIES)))
    if _mapping(delta):
        for category in DELTA_CATEGORIES:
            if category in delta and not _string_list(delta[category]) and delta[category] != []:
                errors.append(f"delta {category} must be an array of identifiers")
    if "graph_paths" in value:
        graph_paths = value["graph_paths"]
        if not isinstance(graph_paths, list) or len(graph_paths) > 128:
            errors.append("graph_paths must be a bounded array")
        else:
            for index, row in enumerate(graph_paths, start=1):
                errors.extend(_check_keys(f"graph path row {index}", row, {"impact", "paths"}))
                if not _mapping(row):
                    continue
                paths = row.get("paths")
                if not isinstance(paths, list) or len(paths) > 128:
                    errors.append(f"graph path row {index} paths must be a bounded array")
                    continue
                for path_index, path in enumerate(paths, start=1):
                    errors.extend(_check_keys(f"graph path {index}.{path_index}", path, {"id", "labels", "providers", "confidence", "locations"}))
                    if not _mapping(path):
                        continue
                    if not isinstance(path.get("id"), str) or re.fullmatch(r"PATH-\d{3}", path["id"]) is None:
                        errors.append(f"graph path {index}.{path_index} has invalid id")
                    if not _string_list(path.get("labels")):
                        errors.append(f"graph path {index}.{path_index} labels must be non-empty strings")
                    if not _string_list(path.get("providers")):
                        errors.append(f"graph path {index}.{path_index} providers must be non-empty strings")
                    if not _nonempty(path.get("confidence")):
                        errors.append(f"graph path {index}.{path_index} confidence must be nonempty")
                    if not isinstance(path.get("locations"), list) or any(not _nonempty(item) for item in path["locations"]):
                        errors.append(f"graph path {index}.{path_index} locations must be strings")
    return errors


def _id(value: object, kind: str) -> bool:
    return isinstance(value, str) and ID_PATTERNS[kind].fullmatch(value) is not None


def _defined_ids(state: Mapping[str, object]) -> dict[str, set[str]]:
    return {
        "requirement": {state["original_requirement"]["id"]},
        "invariant": {row["id"] for row in state["current_behavior"]},
        "impact": {row["id"] for row in state["impacts"]},
        "decision": {row["id"] for row in state["decisions"]},
        "criterion": {row["id"] for row in state["criteria"]},
    }


def _duplicates(values: Sequence[str]) -> set[str]:
    return {value for value in values if values.count(value) > 1}


def validate_definitions(state: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    report = state["report"]
    if not _id(report.get("id"), "report"):
        errors.append("report id must be a canonical RPT identifier")
    revision = report.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        errors.append("report revision must be a positive integer")
    previous = report.get("previous_sha256")
    if revision == 1 and previous != "none":
        errors.append("revision 1 requires previous_sha256 none")
    if isinstance(revision, int) and revision > 1 and not (
        isinstance(previous, str) and SHA256_PATTERN.fullmatch(previous)
    ):
        errors.append("later revision requires a lowercase SHA-256 predecessor")
    if report.get("phase") not in PHASES:
        errors.append("report phase must be pre-decision or post-decision")
    settings = state["settings"]
    for name, allowed in (("audience", AUDIENCES), ("delivery", DELIVERIES)):
        if settings.get(name) not in allowed:
            errors.append(f"invalid {name} {settings.get(name)}")
        if settings.get(f"{name}_source") not in SETTING_SOURCES:
            errors.append(f"invalid {name}_source {settings.get(f'{name}_source')}")
    definitions = (
        ("requirement", [state["original_requirement"].get("id")]),
        ("invariant", [row.get("id") for row in state["current_behavior"]]),
        ("impact", [row.get("id") for row in state["impacts"]]),
        ("decision", [row.get("id") for row in state["decisions"]]),
        ("criterion", [row.get("id") for row in state["criteria"]]),
    )
    for kind, values in definitions:
        for identifier in values:
            if not _id(identifier, kind):
                errors.append(f"invalid {kind} identifier {identifier}")
        for identifier in sorted(_duplicates(values)):
            errors.append(f"duplicate {kind} identifier {identifier}")
    if state["refined_requirement"].get("id") != state["original_requirement"].get("id"):
        errors.append("refined requirement must preserve the original requirement id")
    if not _nonempty(state["original_requirement"].get("request")):
        errors.append("original requirement requires request")
    if not _nonempty(state["original_requirement"].get("source")):
        errors.append("original requirement requires source")
    if not _nonempty(state["refined_requirement"].get("revision")):
        errors.append("refined requirement requires revision")
    return errors


def _current_evidence(value: object) -> bool:
    if not _nonempty(value):
        return False
    remainder = ACCEPTANCE_PATTERN.sub("", str(value))
    return any(character.isalnum() for character in remainder)


def validate_relationships(state: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    known = _defined_ids(state)
    for row in state["current_behavior"]:
        invariant_id = row.get("id")
        level = row.get("evidence_level")
        if level not in EVIDENCE_LEVELS:
            errors.append(f"invariant {invariant_id} has invalid evidence level {level}")
        if not _nonempty(row.get("behavior")):
            errors.append(f"invariant {invariant_id} requires current behavior")
        if not _current_evidence(row.get("evidence")):
            errors.append(f"invariant {invariant_id} {level} evidence requires a current basis")
    for row in state["preserved_invariants"]:
        invariant_id = row.get("id")
        if invariant_id not in known["invariant"]:
            errors.append(f"preserved invariant references unknown invariant {invariant_id}")
        if row.get("requirement") not in known["requirement"]:
            errors.append(f"preserved invariant {invariant_id} references unknown requirement")
        for impact_id in row.get("impacts", []):
            if impact_id not in known["impact"]:
                errors.append(f"preserved invariant {invariant_id} references unknown impact {impact_id}")
        if not _nonempty(row.get("evidence")):
            errors.append(f"preserved invariant {invariant_id} requires evidence")
    for row in state["impacts"]:
        impact_id = row.get("id")
        if row.get("requirement") not in known["requirement"]:
            errors.append(f"impact {impact_id} references unknown requirement")
        if row.get("category") not in IMPACT_CATEGORIES:
            errors.append(f"impact {impact_id} has invalid category {row.get('category')}")
        if row.get("severity") not in SEVERITIES:
            errors.append(f"impact {impact_id} has invalid severity {row.get('severity')}")
        if row.get("state") not in IMPACT_STATES:
            errors.append(f"impact {impact_id} has invalid state {row.get('state')}")
        level = row.get("evidence_level")
        if level not in EVIDENCE_LEVELS:
            errors.append(f"impact {impact_id} has invalid evidence level {level}")
        if not _current_evidence(row.get("evidence")):
            errors.append(f"impact {impact_id} {level} evidence requires a current basis")
        for field, kind in (("invariants", "invariant"), ("decisions", "decision"), ("criteria", "criterion")):
            for identifier in row.get(field, []):
                if identifier not in known[kind]:
                    errors.append(f"impact {impact_id} references unknown {kind} {identifier}")
        if row.get("state") != "superseded" and not row.get("criteria"):
            errors.append(f"impact {impact_id} requires acceptance criteria")
        if row.get("state") == "accepted" and not row.get("decisions"):
            errors.append(f"accepted impact {impact_id} requires a decision")
    for row in state["criteria"]:
        criterion_id = row.get("id")
        for field, kind in (("requirement", "requirement"), ("impact", "impact"), ("invariant", "invariant")):
            if row.get(field) not in known[kind]:
                errors.append(f"criterion {criterion_id} references unknown {kind}")
        if not _nonempty(row.get("criterion")) or not _nonempty(row.get("evidence")):
            errors.append(f"criterion {criterion_id} requires observable criterion and evidence")
    return errors


def validate_phase(state: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    phase = state["report"].get("phase")
    if phase == "pre-decision":
        if state["decisions"] or state["refined_requirement"].get("decision") is not None or any(row.get("decisions") for row in state["impacts"]):
            errors.append("pre-decision state forbids decisions")
        needed = state["decision_needed"]
        if not _mapping(needed):
            errors.append("pre-decision state requires decision_needed")
        else:
            if not _nonempty(needed.get("question")):
                errors.append("decision_needed requires one question")
            options = needed.get("options")
            if not isinstance(options, list) or not 2 <= len(options) <= 3:
                errors.append("decision_needed requires two or three options")
            elif len({option.get("option") for option in options if _mapping(option)}) != len(options):
                errors.append("decision_needed options must be distinct")
            if isinstance(options, list):
                known_impacts = _defined_ids(state)["impact"]
                for option in options:
                    if not _mapping(option):
                        continue
                    if not _nonempty(option.get("option")) or not _nonempty(option.get("tradeoff")):
                        errors.append("decision option requires option and tradeoff")
                    for impact_id in option.get("impacts", []):
                        if impact_id not in known_impacts:
                            errors.append(f"decision option references unknown impact {impact_id}")
    elif phase == "post-decision":
        if state["decision_needed"] is not None:
            errors.append("post-decision state forbids decision_needed")
        if not state["decisions"]:
            errors.append("post-decision state requires a decision")
        if state["refined_requirement"].get("decision") not in _defined_ids(state)["decision"]:
            errors.append("post-decision refined requirement requires a known decision")
    return errors


def validate_supporting_sections(state: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    known = _defined_ids(state)
    for row in state["decisions"]:
        decision_id = row.get("id")
        if not _nonempty(row.get("choice")) or not _nonempty(row.get("rationale")):
            errors.append(f"decision {decision_id} requires choice and rationale")
        if row.get("requirement") not in known["requirement"]:
            errors.append(f"decision {decision_id} references unknown requirement")
        for impact_id in row.get("accepted_impacts", []):
            if impact_id not in known["impact"]:
                errors.append(f"decision {decision_id} references unknown impact {impact_id}")
    for row in state["history"]:
        if row.get("requirement") not in known["requirement"]:
            errors.append("history references unknown requirement")
        decision_id = row.get("decision")
        if decision_id is not None and decision_id not in known["decision"]:
            errors.append(f"history references unknown decision {decision_id}")
        if not _nonempty(row.get("revision")) or not _nonempty(row.get("summary")):
            errors.append("history row requires revision and summary")
    for row in state["scope"]:
        if not all(_nonempty(row.get(field)) for field in ("boundary", "evidence", "confidence")):
            errors.append("scope row requires boundary, evidence, and confidence")
    handoff = state["handoff"]
    for field in ("refined_requirement", "workflow"):
        if not _nonempty(handoff.get(field)):
            errors.append(f"handoff requires {field}")
    for criterion_id in handoff.get("criteria", []):
        if criterion_id not in known["criterion"]:
            errors.append(f"handoff references unknown criterion {criterion_id}")
    remaining = set(handoff.get("remaining_risks", []))
    for impact_id in remaining:
        if impact_id not in known["impact"]:
            errors.append(f"handoff references unknown impact {impact_id}")
    for impact in state["impacts"]:
        if impact.get("state") in {"accepted", "deferred"} and impact["id"] not in remaining:
            errors.append(
                f"handoff remaining risks must name {impact.get('state')} impact {impact['id']}"
            )
    for row in state.get("graph_paths", []):
        if row.get("impact") not in known["impact"]:
            errors.append("graph paths reference unknown impact")
    return errors


def validate_delta(state: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    known = _defined_ids(state)["impact"]
    occurrences: dict[str, int] = {}
    for category in DELTA_CATEGORIES:
        for impact_id in state["delta"].get(category, []):
            occurrences[impact_id] = occurrences.get(impact_id, 0) + 1
            if impact_id not in known:
                errors.append(f"delta references unknown impact {impact_id}")
    for impact_id in sorted(known):
        count = occurrences.get(impact_id, 0)
        if count == 0:
            errors.append(f"delta is missing impact {impact_id}")
        elif count > 1:
            errors.append(f"delta lists {impact_id} more than once")
        if state["report"].get("revision") == 1 and impact_id not in state["delta"].get("new", []):
            errors.append(f"revision 1 impact {impact_id} must be new")
    return errors


def validate_summary(state: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    impacts = {row["id"]: row for row in state["impacts"]}
    counts: dict[str, int] = {}
    for row in state["summary"]:
        impact_id = row.get("impact_id")
        counts[impact_id] = counts.get(impact_id, 0) + 1
        impact = impacts.get(impact_id)
        if impact is None:
            errors.append(f"summary references unknown impact {impact_id}")
            continue
        for field in ("changed_feature", "possible_issue", "affected", "trigger", "prevention"):
            if not _nonempty(row.get(field)):
                errors.append(f"summary {impact_id} requires {field}")
        if row.get("severity") != impact.get("severity"):
            errors.append(f"summary {impact_id} severity {row.get('severity')} disagrees with impact {impact.get('severity')}")
        if row.get("status") != impact.get("state"):
            errors.append(f"summary {impact_id} status {row.get('status')} disagrees with impact {impact.get('state')}")
    for impact_id in sorted(impacts):
        count = counts.get(impact_id, 0)
        if count == 0:
            errors.append(f"summary is missing impact {impact_id}")
        elif count > 1:
            errors.append(f"summary lists {impact_id} more than once")
    return errors


def validate_unresolved(state: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    impacts = {row["id"]: row["state"] for row in state["impacts"]}
    counts: dict[str, int] = {}
    for row in state["unresolved"]:
        impact_id = row.get("impact")
        counts[impact_id] = counts.get(impact_id, 0) + 1
        if impacts.get(impact_id) not in {"blocked", "deferred"}:
            errors.append(f"unresolved impact {impact_id} must be blocked or deferred")
        if row.get("state") != impacts.get(impact_id):
            errors.append(f"unresolved impact {impact_id} state disagrees with impact")
        if not _nonempty(row.get("rationale")) or not _nonempty(row.get("owner")):
            errors.append(f"unresolved impact {impact_id} requires rationale and owner")
    for impact_id, status in impacts.items():
        if status in {"blocked", "deferred"} and counts.get(impact_id, 0) == 0:
            errors.append(f"{status} impact {impact_id} is missing from unresolved items")
        if counts.get(impact_id, 0) > 1:
            errors.append(f"unresolved lists {impact_id} more than once")
    return errors


def validate_state(value: object) -> list[str]:
    errors = validate_structure(value)
    if errors:
        return sorted(set(errors))
    validators = (
        validate_definitions,
        validate_relationships,
        validate_phase,
        validate_supporting_sections,
        validate_delta,
        validate_summary,
        validate_unresolved,
    )
    return sorted({error for validator in validators for error in validator(value)})


def load_state_bytes(raw: bytes) -> tuple[dict[str, object] | None, list[str]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, ["state must be UTF-8"]
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        return None, [f"state must be valid JSON: {error.msg}"]
    if not isinstance(value, dict):
        return None, ["state must contain a JSON object"]
    return value, validate_state(value)
