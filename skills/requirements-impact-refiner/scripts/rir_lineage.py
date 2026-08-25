#!/usr/bin/env python3
"""Report lineage discovery, stable key allocation, and state projection."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Callable, Protocol, cast

if TYPE_CHECKING:
    from typing_extensions import TypeGuard


class _ContractsContract(Protocol):
    MAX_STRING_BYTES: int
    BeginRequest: type

    def _local_key(self, value: object, label: str) -> str: ...

    def validate_analysis(self, analysis: Mapping[str, object]) -> None: ...


class _CompactStateContract(Protocol):
    DELTA_CATEGORIES: Sequence[str]

    def load_state_bytes(self, raw: bytes) -> tuple[dict[str, object] | None, list[str]]: ...

    def validate_state(self, value: object) -> list[str]: ...


class _ImpactReportContract(Protocol):
    def parse_report(self, text: str): ...

    def validate_semantics(self, report): ...


class _ImpactRendererContract(Protocol):
    compact_state: _CompactStateContract
    impact_report: _ImpactReportContract

    def render_markdown(self, state: Mapping[str, object]) -> str: ...

    def render_compact(self, state: Mapping[str, object]) -> str: ...

    def validate_rendered_markdown(
        self, text: str, previous_bytes: bytes | None = None
    ) -> list[str]: ...


class _ReportStoreContract(Protocol):
    compact_state: _CompactStateContract
    impact_renderer: _ImpactRendererContract
    ReportStoreError: type[Exception]
    CurrentRevision: type

    def load_current(self, repo_root: Path, report_id: str): ...

    def publish_revision(
        self, repo_root: Path, state_bytes: bytes, *, resume_partial: bool = False
    ): ...

    def report_directory(
        self, repo_root: Path, report_id: str, *, create: bool = False
    ) -> Path: ...


class _StorageContract(Protocol):
    report_store: _ReportStoreContract

    def root_path(self, path: Path) -> Path: ...

    def load_private_draft(self, repo_root: Path, draft_id: str) -> dict[str, object]: ...

    def draft_path(self, root: Path, draft_id: str) -> Path: ...

    def load_controller_metadata(self, current: object) -> dict[str, object] | None: ...

    def report_lock(self, root: Path, report_id: str, deadline: object = None): ...

    def write_controller_metadata(
        self,
        root: Path,
        draft: Mapping[str, object],
        state_bytes: bytes,
        key_map: Mapping[str, object],
        graph_receipt: Mapping[str, object] | None = None,
    ) -> None: ...

    def consume_draft(self, path: Path, draft: dict[str, object], published, key_map) -> None: ...


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def _regular_module_path(path: Path) -> Path | None:
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        return None
    return resolved


def _module_uses_sibling(value: object, expected: Path) -> bool:
    module_file = getattr(value, "__file__", None)
    return isinstance(module_file, str) and _regular_module_path(Path(module_file)) == expected


def _callables(value: object, names: Sequence[str]) -> bool:
    return all(callable(getattr(value, name, None)) for name in names)


def _is_contracts_contract(value: object) -> TypeGuard[_ContractsContract]:
    maximum = getattr(value, "MAX_STRING_BYTES", None)
    return (
        type(maximum) is int
        and maximum > 0
        and isinstance(getattr(value, "BeginRequest", None), type)
        and _callables(value, ("_local_key", "validate_analysis"))
    )


def _is_compact_state_contract(value: object) -> TypeGuard[_CompactStateContract]:
    categories = getattr(value, "DELTA_CATEGORIES", None)
    return (
        isinstance(categories, Sequence)
        and not isinstance(categories, (str, bytes))
        and all(isinstance(item, str) for item in categories)
        and _callables(value, ("load_state_bytes", "validate_state"))
    )


def _is_impact_report_contract(value: object) -> TypeGuard[_ImpactReportContract]:
    return _callables(value, ("parse_report", "validate_semantics"))


def _execute_registered(
    module_name: str,
    expected: Path,
    validator: Callable[[object], bool],
    label: str,
    aliases: Mapping[str, ModuleType] | None = None,
) -> object:
    specification = importlib.util.spec_from_file_location(module_name, expected)
    if specification is None or specification.loader is None:
        raise ImportError(f"cannot load fixed lineage {label} sibling")
    module = importlib.util.module_from_spec(specification)
    previous = {name: (name in sys.modules, sys.modules.get(name)) for name in (aliases or {})}
    sys.modules[module_name] = module
    try:
        if aliases:
            sys.modules.update(aliases)
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError(f"cannot load fixed lineage {label} sibling") from error
    finally:
        for name, (present, value) in previous.items():
            if name == module_name:
                continue
            if present:
                sys.modules[name] = cast(ModuleType, value)
            else:
                sys.modules.pop(name, None)
    if not validator(module):
        sys.modules.pop(module_name, None)
        raise ImportError(f"lineage {label} sibling contract is incomplete")
    return module


def _load_fixed_sibling(
    filename: str,
    canonical_name: str,
    prefix: str,
    validator: Callable[[object], bool],
    label: str,
    aliases: Mapping[str, ModuleType] | None = None,
) -> object:
    sibling = SCRIPT_DIR / filename
    expected = _regular_module_path(sibling)
    if expected is None or expected != sibling:
        raise ImportError(f"lineage {label} sibling is unsafe")
    hashed_name = prefix + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    hashed_present = hashed_name in sys.modules
    hashed = sys.modules.get(hashed_name)
    if canonical_name not in sys.modules:
        if hashed_present:
            if not _module_uses_sibling(hashed, expected):
                raise ImportError(f"lineage {label} sibling is unsafe")
            if not validator(hashed):
                raise ImportError(f"lineage {label} sibling contract is incomplete")
            sys.modules[canonical_name] = cast(ModuleType, hashed)
            return hashed
        return _execute_registered(canonical_name, expected, validator, label, aliases=aliases)
    canonical = sys.modules.get(canonical_name)
    if _module_uses_sibling(canonical, expected):
        if validator(canonical) and not hashed_present:
            return canonical
        if hashed_present:
            if not _module_uses_sibling(hashed, expected):
                raise ImportError(f"lineage {label} sibling is unsafe")
            if not validator(hashed):
                raise ImportError(f"lineage {label} sibling contract is incomplete")
            return hashed
        if aliases is not None:
            return _execute_registered(hashed_name, expected, validator, label, aliases=aliases)
        raise ImportError(f"lineage {label} sibling contract is incomplete")
    if hashed_present:
        if not _module_uses_sibling(hashed, expected):
            raise ImportError(f"lineage {label} sibling is unsafe")
        if not validator(hashed):
            raise ImportError(f"lineage {label} sibling contract is incomplete")
        return hashed
    return _execute_registered(hashed_name, expected, validator, label, aliases=aliases)


CONTRACTS = cast(
    _ContractsContract,
    _load_fixed_sibling(
        "rir_contracts.py",
        "rir_contracts",
        "_rir_lineage_contracts_",
        _is_contracts_contract,
        "contracts",
    ),
)
COMPACT_STATE = cast(
    _CompactStateContract,
    _load_fixed_sibling(
        "compact_state.py",
        "compact_state",
        "_rir_lineage_compact_state_",
        _is_compact_state_contract,
        "compact state",
    ),
)
IMPACT_REPORT = cast(
    _ImpactReportContract,
    _load_fixed_sibling(
        "impact_report.py",
        "impact_report",
        "_rir_lineage_impact_report_",
        _is_impact_report_contract,
        "impact report",
    ),
)


def _is_impact_renderer_contract(value: object) -> TypeGuard[_ImpactRendererContract]:
    return (
        getattr(value, "compact_state", None) is COMPACT_STATE
        and getattr(value, "impact_report", None) is IMPACT_REPORT
        and _callables(
            value,
            ("render_markdown", "render_compact", "validate_rendered_markdown"),
        )
    )


IMPACT_RENDERER = cast(
    _ImpactRendererContract,
    _load_fixed_sibling(
        "impact_renderer.py",
        "impact_renderer",
        "_rir_lineage_impact_renderer_",
        _is_impact_renderer_contract,
        "impact renderer",
        aliases={
            "compact_state": cast(ModuleType, COMPACT_STATE),
            "impact_report": cast(ModuleType, IMPACT_REPORT),
        },
    ),
)


def _is_report_store_contract(value: object) -> TypeGuard[_ReportStoreContract]:
    return (
        getattr(value, "compact_state", None) is COMPACT_STATE
        and getattr(value, "impact_renderer", None) is IMPACT_RENDERER
        and isinstance(getattr(value, "ReportStoreError", None), type)
        and isinstance(getattr(value, "CurrentRevision", None), type)
        and _callables(value, ("load_current", "publish_revision", "report_directory"))
    )


REPORT_STORE = cast(
    _ReportStoreContract,
    _load_fixed_sibling(
        "report_store.py",
        "report_store",
        "_rir_lineage_report_store_",
        _is_report_store_contract,
        "report store",
        aliases={
            "compact_state": cast(ModuleType, COMPACT_STATE),
            "impact_renderer": cast(ModuleType, IMPACT_RENDERER),
        },
    ),
)


def _is_storage_contract(value: object) -> TypeGuard[_StorageContract]:
    return getattr(value, "report_store", None) is REPORT_STORE and _callables(
        value,
        (
            "root_path",
            "load_private_draft",
            "draft_path",
            "load_controller_metadata",
            "report_lock",
            "write_controller_metadata",
            "consume_draft",
        ),
    )


STORAGE = cast(
    _StorageContract,
    _load_fixed_sibling(
        "rir_storage.py",
        "rir_storage",
        "_rir_lineage_storage_",
        _is_storage_contract,
        "storage",
        aliases={"report_store": cast(ModuleType, REPORT_STORE)},
    ),
)

BeginRequest = CONTRACTS.BeginRequest
MAX_STRING_BYTES = CONTRACTS.MAX_STRING_BYTES
SUPERPOWERS_HANDOFF_MARKER = (
    "superpowers:after-approved-brainstorming;impact-refinement;manual-handoff-before-writing-plans"
)
GRAPH_CONFIDENCE_RANK = {
    "verified-provider": 0,
    "verified-source": 1,
    "structural-inferred": 2,
    "lexical": 3,
}


def current_lineage(root: Path):
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
    current = REPORT_STORE.load_current(root, report_ids[0])
    if current is None:
        return None
    prior_state, errors = COMPACT_STATE.load_state_bytes(current.state_path.read_bytes())
    if errors or prior_state is None:
        raise ValueError("current report state is invalid")
    key_map: Mapping[str, object] | None = STORAGE.load_controller_metadata(current)
    if key_map is None:
        key_map = legacy_key_map(prior_state)
    return current, prior_state, key_map


def legacy_key_map(state: Mapping[str, object]) -> dict[str, dict[str, str]]:
    sections: dict[str, tuple[object, str]] = {
        "invariants": (state.get("current_behavior", []), "inv"),
        "impacts": (state.get("impacts", []), "imp"),
        "decisions": (state.get("decisions", []), "dec"),
        "criteria": (state.get("criteria", []), "ac"),
    }
    result: dict[str, dict[str, str]] = {}
    for name, (rows, prefix) in sections.items():
        if not isinstance(rows, list):
            raise ValueError("current report cannot derive controller key lineage")
        mapping: dict[str, str] = {}
        for row in rows:
            identifier = row.get("id") if isinstance(row, dict) else None
            if not isinstance(identifier, str):
                raise ValueError("current report cannot derive controller key lineage")
            mapping[f"legacy-{prefix}-{identifier.rsplit('-', 1)[-1].lower()}"] = identifier
        result[name] = mapping
    return result


def allocate_ids(rows, prefix, prior=None):
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


def map_keys(values, mapping, label):
    result = []
    for value in values:
        key = CONTRACTS._local_key(value, label)
        if key not in mapping:
            raise ValueError(f"unknown {label} key {key}")
        result.append(mapping[key])
    return result


def _path_confidence(path, nodes, edges) -> str:
    values = [nodes[node]["confidence"] for node in path["nodes"]]
    values.extend(edges[edge]["confidence"] for edge in path["edges"])
    return max(values, key=lambda value: GRAPH_CONFIDENCE_RANK[value])


def _path_provenance(path, nodes, edges) -> str:
    records = [nodes[node] for node in path["nodes"]]
    records.extend(edges[edge] for edge in path["edges"])
    providers = list(dict.fromkeys(row.get("provider") for row in records if row.get("provider")))
    locations = list(dict.fromkeys(row.get("location") for row in records if row.get("location")))
    provider = " + ".join(providers) if providers else "unavailable"
    location = " + ".join(locations) if locations else "unavailable"
    return (
        f"provider {provider}; confidence {_path_confidence(path, nodes, edges)}; "
        f"location {location}"
    )


def _structured_path(path, nodes, edges) -> dict[str, object]:
    records = [nodes[node] for node in path["nodes"]]
    records.extend(edges[edge] for edge in path["edges"])
    return {
        "id": path["id"],
        "labels": [nodes[node]["label"] for node in path["nodes"]],
        "providers": list(dict.fromkeys(row["provider"] for row in records if row.get("provider")))
        or ["unavailable"],
        "confidence": _path_confidence(path, nodes, edges),
        "locations": list(dict.fromkeys(row["location"] for row in records if row.get("location"))),
    }


def build_state(draft, analysis, graph_context=None):
    CONTRACTS.validate_analysis(analysis)
    prior_state = draft.get("prior_state")
    prior_key_map = draft.get("prior_key_map") or {}
    requirement_id = (
        prior_state["original_requirement"]["id"] if isinstance(prior_state, dict) else "REQ-001"
    )
    if prior_key_map:
        missing_impacts = sorted(
            set(prior_key_map.get("impacts", {})) - {row["key"] for row in analysis["impacts"]}
        )
        if missing_impacts:
            raise ValueError(f"impact key disappeared: {missing_impacts[0]}")
    invariant_ids = allocate_ids(analysis["invariants"], "INV", prior_key_map.get("invariants"))
    impact_ids = allocate_ids(analysis["impacts"], "IMP", prior_key_map.get("impacts"))
    decision_ids = allocate_ids(analysis["decisions"], "DEC", prior_key_map.get("decisions"))
    criterion_ids = allocate_ids(analysis["criteria"], "AC", prior_key_map.get("criteria"))
    key_map = {
        "invariants": invariant_ids,
        "impacts": impact_ids,
        "decisions": decision_ids,
        "criteria": criterion_ids,
    }
    impacts = []
    for row in analysis["impacts"]:
        impacts.append(
            {
                "id": impact_ids[row["key"]],
                "requirement": requirement_id,
                "category": row["category"],
                "severity": row["severity"],
                "state": row["state"],
                "evidence_level": row["evidence_level"],
                "evidence": row["evidence"],
                "invariants": map_keys(row["invariant_keys"], invariant_ids, "invariant"),
                "decisions": map_keys(row["decision_keys"], decision_ids, "decision"),
                "criteria": map_keys(row["criterion_keys"], criterion_ids, "criterion"),
            }
        )
    current_behavior = [
        {
            "id": invariant_ids[row["key"]],
            "behavior": row["behavior"],
            "evidence_level": row["evidence_level"],
            "evidence": row["evidence"],
        }
        for row in analysis["invariants"]
    ]
    preserved = []
    for row in analysis["invariants"]:
        affected = [
            impact_ids[impact["key"]]
            for impact in analysis["impacts"]
            if row["key"] in impact["invariant_keys"]
        ]
        preserved.append(
            {
                "id": invariant_ids[row["key"]],
                "requirement": requirement_id,
                "impacts": affected,
                "evidence": row["evidence"],
            }
        )
    decisions = [
        {
            "id": decision_ids[row["key"]],
            "choice": row["choice"],
            "requirement": requirement_id,
            "accepted_impacts": map_keys(row["accepted_impact_keys"], impact_ids, "impact"),
            "rationale": row["rationale"],
        }
        for row in analysis["decisions"]
    ]
    criteria = [
        {
            "id": criterion_ids[row["key"]],
            "requirement": requirement_id,
            "impact": map_keys([row["impact_key"]], impact_ids, "impact")[0],
            "invariant": map_keys([row["invariant_key"]], invariant_ids, "invariant")[0],
            "criterion": row["criterion"],
            "evidence": row["evidence"],
        }
        for row in analysis["criteria"]
    ]
    decision_needed = None
    if analysis["phase"] == "pre-decision":
        decision_needed = {
            "question": analysis["decision_needed"]["question"],
            "options": [
                {
                    "option": row["option"],
                    "impacts": map_keys(row["impact_keys"], impact_ids, "impact"),
                    "tradeoff": row["tradeoff"],
                }
                for row in analysis["decision_needed"]["options"]
            ],
        }
    unresolved = [
        {
            "impact": map_keys([row["impact_key"]], impact_ids, "impact")[0],
            "state": row["state"],
            "rationale": row["rationale"],
            "decision": None
            if row["decision_key"] is None
            else map_keys([row["decision_key"]], decision_ids, "decision")[0],
            "owner": row["owner"],
        }
        for row in analysis["unresolved"]
    ]
    remaining = [
        row["id"] for row in impacts if row["state"] in {"accepted", "deferred", "blocked"}
    ]
    if not remaining:
        remaining = [row["id"] for row in impacts]
    all_report_ids = [
        requirement_id,
        *list(invariant_ids.values()),
        *list(impact_ids.values()),
        *list(decision_ids.values()),
    ]
    summary = [
        {
            "impact_id": impact_ids[row["key"]],
            **row["summary"],
            "severity": row["severity"],
            "status": row["state"],
        }
        for row in analysis["impacts"]
    ]
    first_decision = decisions[0]["id"] if decisions else None
    delta: dict[str, list[str]] = {category: [] for category in COMPACT_STATE.DELTA_CATEGORIES}
    if prior_state is None:
        delta["new"] = list(impact_ids.values())
    else:
        previous_states = {row["id"]: row["state"] for row in prior_state["impacts"]}
        terminal = {"resolved", "accepted", "superseded"}
        active = {"detected", "refining", "mitigated", "deferred", "blocked"}
        state_category = {
            "detected": "unchanged",
            "refining": "unchanged",
            "mitigated": "mitigated",
            "resolved": "resolved",
            "accepted": "accepted",
            "deferred": "deferred",
            "blocked": "blocked",
            "superseded": "superseded",
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
    prior_history = []
    if prior_state is not None:
        current_decision_ids = set(decision_ids.values())
        for prior_row in prior_state["history"]:
            history_row = dict(prior_row)
            historical_decision = history_row.get("decision")
            if (
                analysis["phase"] == "pre-decision"
                and isinstance(historical_decision, str)
                and historical_decision not in current_decision_ids
            ):
                history_row["decision"] = None
                history_row["summary"] = (
                    f"{history_row['summary']} The historical decision remains "
                    "authoritative in the prior immutable revision."
                )
            prior_history.append(history_row)
    original_requirement = (
        {
            "id": requirement_id,
            "request": draft["request"],
            "source": "User request and supplied repository evidence.",
        }
        if prior_state is None
        else prior_state["original_requirement"]
    )
    if draft.get("adapter") == "superpowers":
        handoff_workflow = SUPERPOWERS_HANDOFF_MARKER
    elif analysis["phase"] == "pre-decision" or any(row["state"] == "blocked" for row in impacts):
        handoff_workflow = "Not ready"
    else:
        handoff_workflow = analysis["workflow"]
    scope = list(analysis["scope"])
    structured_paths = []
    if graph_context is not None:
        receipt = graph_context["receipt"]
        receipt_nodes = {row["id"]: row for row in receipt["nodes"]}
        receipt_edges = {row["id"]: row for row in receipt["edges"]}
        receipt_paths = {row["id"]: row for row in receipt["paths"]}
        for row in analysis["impacts"]:
            path_descriptions = []
            path_provenance = []
            impact_paths = []
            for path_key in graph_context["impact_paths"][row["key"]]:
                path = receipt_paths[path_key]
                labels = [receipt_nodes[node]["label"] for node in path["nodes"]]
                path_descriptions.append(f"{path_key}: " + " → ".join(labels))
                path_provenance.append(
                    f"{path_key}: {_path_provenance(path, receipt_nodes, receipt_edges)}"
                )
                impact_paths.append(_structured_path(path, receipt_nodes, receipt_edges))
            if impact_paths:
                structured_paths.append(
                    {
                        "impact": impact_ids[row["key"]],
                        "paths": impact_paths,
                    }
                )
            rationale = graph_context["rationales"].get(row["key"])
            scope.append(
                {
                    "boundary": f"Graph paths for {impact_ids[row['key']]}",
                    "evidence": " || ".join(path_descriptions)
                    if path_descriptions
                    else str(rationale),
                    "confidence": (
                        " || ".join(path_provenance)
                        if path_provenance
                        else "provider unavailable; confidence unknown; location unavailable"
                    ),
                }
            )
        provider_summary = [f"{row['name']} ({row['status']})" for row in receipt["providers"]]
        elapsed = int(receipt["timings_ms"].get("total", 0))
        frontier_ids = ",".join(row["id"] for row in receipt["frontier"]) or "none"
        scope.append(
            {
                "boundary": "Impact graph coverage",
                "evidence": (
                    f"Impact scan: {elapsed / 1000:.1f} s · "
                    f"{' + '.join(provider_summary) or 'no provider'} · "
                    f"{len(receipt['nodes'])} nodes / {len(receipt['edges'])} edges · "
                    f"{len(receipt['frontier'])} unknown frontiers"
                ),
                "confidence": (
                    f"{receipt['budget_status']}; receipt {receipt['receipt_id']}; "
                    f"sha256 {graph_context['sha256']}; frontier {frontier_ids}"
                ),
            }
        )
        if len(scope) > 128:
            raise ValueError("scope has too many rows after graph coverage injection")
        if any(
            len(value.encode("utf-8")) > MAX_STRING_BYTES
            for row in scope
            for value in row.values()
            if isinstance(value, str)
        ):
            raise ValueError("graph coverage scope exceeds string limit")
    state = {
        "schema_version": 1,
        "report": {
            "id": draft["report_id"],
            "revision": draft["revision"],
            "previous_sha256": draft["previous_sha256"],
            "phase": analysis["phase"],
        },
        "settings": draft["settings"],
        "original_requirement": original_requirement,
        "refined_requirement": {
            "id": requirement_id,
            "revision": analysis["refined_requirement"],
            "decision": first_decision,
            "supersedes": [],
        },
        "current_behavior": current_behavior,
        "preserved_invariants": preserved,
        "impacts": impacts,
        "decision_needed": decision_needed,
        "decisions": decisions,
        "delta": delta,
        "history": [
            *prior_history,
            {
                "requirement": requirement_id,
                "revision": analysis["refined_requirement"],
                "decision": first_decision,
                "superseded_impacts": [],
                "summary": "Controller-created refinement revision.",
            },
        ],
        "criteria": criteria,
        "unresolved": unresolved,
        "scope": scope,
        "handoff": {
            "refined_requirement": requirement_id
            if analysis["phase"] == "post-decision"
            else "Not ready until the pending decision is selected.",
            "report_ids": all_report_ids,
            "remaining_risks": remaining,
            "criteria": list(criterion_ids.values()),
            "workflow": handoff_workflow,
        },
        "summary": summary,
    }
    if structured_paths:
        state["graph_paths"] = structured_paths
    errors = COMPACT_STATE.validate_state(state)
    if errors:
        raise ValueError("; ".join(errors))
    return state, key_map


# Compatibility aliases for the stable controller facade.
_current_lineage = current_lineage
_legacy_key_map = legacy_key_map
_ids = allocate_ids
_map_keys = map_keys
_build_state = build_state
