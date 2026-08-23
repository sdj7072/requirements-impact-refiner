#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Mapping, Optional, Tuple

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback is serialized per process
    fcntl = None


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import compact_state
import impact_renderer
import report_store


MAX_BEGIN_BYTES = 256 * 1024
MAX_TRACE_BYTES = 256 * 1024
MAX_FINALIZE_BYTES = 2 * 1024 * 1024
MAX_STRING_BYTES = 64 * 1024
MAX_DRAFT_BYTES = 4 * 1024 * 1024
MAX_TRACE_SEEDS = 128
DRAFT_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
LOCAL_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}")
ADAPTERS = {"generic", "superpowers", "claude-feature-dev", "spec-kit"}
SUPERPOWERS_HANDOFF_MARKER = (
    "superpowers:after-approved-brainstorming;impact-refinement;"
    "manual-handoff-before-writing-plans"
)
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
IMPACT_OPTIONAL_KEYS = {"graph_path_keys", "coverage_rationale"}
SUMMARY_KEYS = {"changed_feature", "possible_issue", "affected", "trigger", "prevention"}
HIGH_RISK_DOMAINS = {
    "authorization/privacy", "legal/policy", "data", "interfaces", "operations",
    "state/concurrency",
}
EVIDENCE_RANK = {"verified": 0, "inferred": 1, "unknown": 2}
GRAPH_CONFIDENCE_RANK = {
    "verified-provider": 0, "verified-source": 1,
    "structural-inferred": 2, "lexical": 3,
}


def _load_settings_module():
    path = SCRIPT_DIR / "resolve-settings.py"
    spec = importlib.util.spec_from_file_location("rir_resolve_settings", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETTINGS = _load_settings_module()


def _load_graph_coordinator():
    path = SCRIPT_DIR / "graph_coordinator.py"
    module_name = "_rir_controller_graph_coordinator_" + hashlib.sha256(
        str(path).encode("utf-8")
    ).hexdigest()[:16]
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load fixed graph coordinator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


GRAPH_COORDINATOR = _load_graph_coordinator()
GRAPH = GRAPH_COORDINATOR.GRAPH
TraceSeed = GRAPH_COORDINATOR.ScanSeed


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
    prior_key_map: Optional[Mapping[str, object]]


@dataclass(frozen=True)
class TraceRequest:
    repo_root: Path
    draft_id: str
    seeds: Tuple[TraceSeed, ...]


@dataclass(frozen=True)
class TraceResult:
    receipt_id: str
    receipt_path: Path
    receipt_sha256: str
    compact_graph: Mapping[str, object]
    budget_status: str


@dataclass(frozen=True)
class FinalizeRequest:
    repo_root: Path
    draft_id: str
    analysis: Mapping[str, object]
    graph_receipt_id: Optional[str] = None


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


def _open_directory_at(parent_fd: int, name: str, mode: int) -> int:
    try:
        os.mkdir(name, mode=mode, dir_fd=parent_fd)
    except FileExistsError:
        pass
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except OSError as error:
        raise ValueError(f"controller directory is unsafe: {name}: {error}") from error


def _private_draft_directory_fd(root: Path) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    root_fd = os.open(root, flags)
    base_fd = None
    try:
        base_fd = _open_directory_at(root_fd, ".requirements-impact-refiner", 0o755)
        draft_fd = _open_directory_at(base_fd, "drafts", 0o700)
        os.fchmod(draft_fd, 0o700)
        return draft_fd
    finally:
        if base_fd is not None:
            os.close(base_fd)
        os.close(root_fd)


def _write_private_draft(root: Path, draft_id: str, payload: bytes) -> Path:
    directory_fd = _private_draft_directory_fd(root)
    file_fd = None
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        file_fd = os.open(f"{draft_id}.json", flags, 0o600, dir_fd=directory_fd)
        offset = 0
        while offset < len(payload):
            offset += os.write(file_fd, payload[offset:])
        os.fsync(file_fd)
    except OSError as error:
        raise ValueError(f"cannot create draft: {error}") from error
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(directory_fd)
    return root / ".requirements-impact-refiner" / "drafts" / f"{draft_id}.json"


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
        unit = "256 KiB" if maximum in {MAX_BEGIN_BYTES, MAX_TRACE_BYTES} else "2 MiB"
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
    key_map = _load_controller_metadata(current)
    if key_map is None:
        key_map = _legacy_key_map(prior_state)
    return current, prior_state, key_map


def _legacy_key_map(state: Mapping[str, object]) -> dict[str, dict[str, str]]:
    sections = {
        "invariants": (state.get("current_behavior", []), "inv"),
        "impacts": (state.get("impacts", []), "imp"),
        "decisions": (state.get("decisions", []), "dec"),
        "criteria": (state.get("criteria", []), "ac"),
    }
    result = {}
    for name, (rows, prefix) in sections.items():
        mapping = {}
        for row in rows:
            identifier = row.get("id") if isinstance(row, dict) else None
            if not isinstance(identifier, str):
                raise ValueError("current report cannot derive controller key lineage")
            mapping[f"legacy-{prefix}-{identifier.rsplit('-', 1)[-1].lower()}"] = identifier
        result[name] = mapping
    return result


def _controller_metadata_path(report_id: str, revision: int, root: Path) -> Path:
    report_dir = report_store.report_directory(root, report_id, create=True)
    return report_dir / f"revision-{revision:04d}.controller.json"


def _load_controller_metadata(current) -> Optional[dict[str, object]]:
    path = current.state_path.with_name(
        f"revision-{current.revision:04d}.controller.json"
    )
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError("controller lineage metadata is unsafe")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        current_state_sha256 = hashlib.sha256(
            current.state_path.read_bytes()
        ).hexdigest()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"controller lineage metadata is invalid: {error}") from error
    if (
        not isinstance(payload, dict)
        or payload.get("report_id") != current.report_id
        or payload.get("revision") != current.revision
        or payload.get("state_sha256")
        != current_state_sha256
        or not isinstance(payload.get("key_map"), dict)
    ):
        raise ValueError("controller lineage metadata identity is invalid")
    return payload["key_map"]


def _draft_path(root: Path, draft_id: str) -> Path:
    if DRAFT_ID_PATTERN.fullmatch(draft_id) is None:
        raise ValueError("invalid draft ID")
    return root / ".requirements-impact-refiner" / "drafts" / f"{draft_id}.json"


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
    path = _write_private_draft(root, draft_id, _canonical_bytes(draft))
    return DraftResult(
        draft_id=draft_id,
        draft_path=path,
        report_id=report_id,
        revision=revision,
        previous_sha256=previous_sha256,
        settings=settings,
        prior_state=prior_state,
        prior_key_map=prior_key_map,
    )


def load_draft(repo_root: Path, draft_id: str) -> dict[str, object]:
    root = _root(repo_root)
    if DRAFT_ID_PATTERN.fullmatch(draft_id) is None:
        raise ValueError("invalid draft ID")
    directory_fd = _private_draft_directory_fd(root)
    file_fd = None
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        file_fd = os.open(f"{draft_id}.json", flags, dir_fd=directory_fd)
        chunks = []
        total = 0
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DRAFT_BYTES:
                raise ValueError("draft exceeds 4 MiB")
            chunks.append(chunk)
        value = json.loads(b"".join(chunks).decode("utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"draft is invalid: {error}") from error
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(directory_fd)
    if not isinstance(value, dict) or value.get("draft_id") != draft_id:
        raise ValueError("draft identity is invalid")
    if value.get("repo_root") != str(root):
        raise ValueError("draft repository root does not match")
    return value


def _graph_draft_identity(draft: Mapping[str, object]) -> dict[str, object]:
    keys = (
        "schema_version", "draft_id", "repo_root", "request", "request_sha256",
        "repository_evidence", "adapter", "settings", "report_id", "revision",
        "previous_sha256", "prior_state", "prior_key_map", "created_at",
    )
    try:
        identity = {key: draft[key] for key in keys}
    except KeyError as error:
        raise ValueError(f"draft graph identity is missing {error.args[0]}") from error
    request = identity["request"]
    if (
        not isinstance(request, str)
        or identity["request_sha256"]
        != hashlib.sha256(request.encode("utf-8")).hexdigest()
    ):
        raise ValueError("draft request identity is invalid")
    return identity


def _replace_private_draft(
    root: Path, draft_id: str, value: Mapping[str, object]
) -> None:
    directory_fd = _private_draft_directory_fd(root)
    temporary_name = f".{draft_id}.{secrets.token_hex(8)}.tmp"
    descriptor = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
        payload = _canonical_bytes(value)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(
            temporary_name, f"{draft_id}.json",
            src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    except OSError as error:
        raise ValueError(f"cannot bind graph receipt to draft: {error}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)


def _compact_graph(receipt: Mapping[str, object]) -> dict[str, object]:
    nodes = {row["id"]: row for row in receipt["nodes"]}
    edges = {row["id"]: row for row in receipt["edges"]}
    return {
        "providers": [
            {
                "name": row["name"], "status": row["status"],
                "confidence": row["confidence"], "version": row["version"],
            }
            for row in receipt["providers"]
        ],
        "nodes": [
            {
                "key": row["id"], "kind": row["kind"], "label": row["label"],
                "location": row["location"], "confidence": row["confidence"],
                "risk_domains": list(row["risk_domains"]),
            }
            for row in receipt["nodes"]
        ],
        "paths": [
            {
                "key": row["id"],
                "nodes": [
                    {
                        "key": node_id, "label": nodes[node_id]["label"],
                        "location": nodes[node_id]["location"],
                    }
                    for node_id in row["nodes"]
                ],
                "edges": [
                    {
                        "key": edge_id, "kind": edges[edge_id]["kind"],
                        "confidence": edges[edge_id]["confidence"],
                    }
                    for edge_id in row["edges"]
                ],
                "distance": row["distance"],
                "risk_domains": list(row["risk_domains"]),
            }
            for row in receipt["paths"]
        ],
        "frontier": [
            {
                "key": row["id"], "node_key": row["node"],
                "reason": row["reason"],
                "risk_domains": list(row["risk_domains"]),
            }
            for row in receipt["frontier"]
        ],
        "summary": {
            "nodes": len(receipt["nodes"]), "edges": len(receipt["edges"]),
            "paths": len(receipt["paths"]),
            "unknown_frontiers": len(receipt["frontier"]),
            "timings_ms": dict(receipt["timings_ms"]),
            "budget_status": receipt["budget_status"],
        },
    }


def _source_inventory_sha256(source_digests: Mapping[str, str]) -> str:
    payload = json.dumps(
        source_digests, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _receipt_source_inventory(
    root: Path, receipt: Mapping[str, object]
) -> tuple[str, str]:
    key = receipt.get("cache", {}).get("key")
    if (
        not isinstance(key, str)
        or re.fullmatch(r"[0-9a-f]{64}", key) is None
        or key == "0" * 64
    ):
        raise ValueError("graph receipt has no verifiable source inventory cache")
    cache_dir = GRAPH_COORDINATOR.CACHE._cache_directory(root, False)
    if cache_dir is None:
        raise ValueError("graph source inventory cache is unavailable")
    artifact = GRAPH_COORDINATOR.CACHE._read_artifact(cache_dir / f"{key}.json")
    if artifact is None:
        raise ValueError("graph source inventory cache is invalid")
    try:
        source_digests = GRAPH_COORDINATOR.CACHE._source_digests(
            artifact["source_digests"]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("graph source inventory cache is invalid") from error
    loaded = GRAPH_COORDINATOR.CACHE.load(root, key, source_digests)
    cached_receipt = loaded.receipt
    if loaded.status != "hit" or not isinstance(cached_receipt, Mapping):
        raise ValueError("graph source inventory cache identity is invalid")
    stable_fields = (
        "receipt_id", "draft_id", "repo_root_sha256", "request_sha256",
        "settings", "providers", "nodes", "edges", "paths", "frontier",
        "budget_status",
    )
    if any(cached_receipt.get(name) != receipt.get(name) for name in stable_fields):
        raise ValueError("graph source inventory cache does not match receipt")
    return key, _source_inventory_sha256(source_digests)


def _verify_source_inventory(
    root: Path,
    graph_settings: Mapping[str, object],
    expected_sha256: object,
) -> None:
    if (
        not isinstance(expected_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
    ):
        raise ValueError("graph source inventory identity is invalid")
    deadline = GRAPH_COORDINATOR.Deadline(
        time, int(graph_settings["max_seconds"])
    )
    current = GRAPH_COORDINATOR._collect_source_digests(root, deadline)
    if current is None or _source_inventory_sha256(current) != expected_sha256:
        raise ValueError("graph receipt source inventory is stale")


def _open_existing_directory_at(parent_fd: int, name: str) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except OSError as error:
        raise ValueError(f"graph receipt directory is unsafe: {name}: {error}") from error


def _read_bound_receipt_bytes(root: Path, draft_id: str) -> bytes:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    root_fd = os.open(root, flags)
    base_fd = graph_fd = receipt_fd = None
    try:
        base_fd = _open_existing_directory_at(root_fd, ".requirements-impact-refiner")
        graph_fd = _open_existing_directory_at(base_fd, "graph")
        file_flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW
        receipt_fd = os.open(f"{draft_id}.json", file_flags, dir_fd=graph_fd)
        metadata = os.fstat(receipt_fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise ValueError("graph receipt must be one private regular file")
        if metadata.st_size > GRAPH.MAX_RECEIPT_BYTES:
            raise ValueError("graph receipt exceeds maximum byte size")
        payload = bytearray()
        while len(payload) <= GRAPH.MAX_RECEIPT_BYTES:
            chunk = os.read(
                receipt_fd,
                min(64 * 1024, GRAPH.MAX_RECEIPT_BYTES + 1 - len(payload)),
            )
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) > GRAPH.MAX_RECEIPT_BYTES:
            raise ValueError("graph receipt exceeds maximum byte size")
        return bytes(payload)
    except OSError as error:
        raise ValueError(f"graph receipt is unavailable or unsafe: {error}") from error
    finally:
        for descriptor in (receipt_fd, graph_fd, base_fd, root_fd):
            if descriptor is not None:
                os.close(descriptor)


def _repository_file_sha256(root: Path, relative: str) -> str:
    parts = relative.split("/")
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(root, flags)
    opened = [descriptor]
    try:
        for part in parts[:-1]:
            descriptor = os.open(part, flags, dir_fd=descriptor)
            opened.append(descriptor)
        file_flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW
        file_fd = os.open(parts[-1], file_flags, dir_fd=descriptor)
        opened.append(file_fd)
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("receipt source is not a regular file")
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(file_fd, 64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > 8 * 1024 * 1024:
                raise ValueError("receipt source exceeds verification limit")
            digest.update(chunk)
        return digest.hexdigest()
    except OSError as error:
        raise ValueError(f"graph receipt source is stale or unsafe: {error}") from error
    finally:
        for current in reversed(opened):
            os.close(current)


def _verify_receipt_sources(root: Path, receipt: Mapping[str, object]) -> None:
    observed = {}
    for row in list(receipt["nodes"]) + list(receipt["edges"]):
        location, expected = row.get("location"), row.get("source_sha256")
        if location is None or expected is None:
            continue
        actual = observed.get(location)
        if actual is None:
            actual = _repository_file_sha256(root, location)
            observed[location] = actual
        if actual != expected:
            raise ValueError(f"graph receipt is stale for source {location}")


def _load_graph_context(
    root: Path,
    draft: Mapping[str, object],
    selected_receipt_id: Optional[str],
) -> dict[str, object]:
    binding = draft.get("graph_receipt")
    if not isinstance(binding, dict) or set(binding) != {
        "receipt_id", "sha256", "request_sha256", "settings", "seeds",
        "cache_key", "source_inventory_sha256",
    }:
        raise ValueError("graph receipt is required for this draft")
    if (
        not isinstance(selected_receipt_id, str)
        or DRAFT_ID_PATTERN.fullmatch(selected_receipt_id) is None
    ):
        raise ValueError("valid graph_receipt_id is required")
    if selected_receipt_id != binding.get("receipt_id"):
        raise ValueError("graph receipt does not match selected draft receipt")
    graph_settings = draft["settings"].get("impact_graph")
    if binding.get("settings") != graph_settings:
        raise ValueError("graph receipt settings do not match draft")
    seed_rows = binding.get("seeds")
    if not isinstance(seed_rows, list) or not seed_rows:
        raise ValueError("graph receipt seed identity is invalid")
    seeds = []
    for row in seed_rows:
        if not isinstance(row, dict) or set(row) != {"term", "location"}:
            raise ValueError("graph receipt seed identity is invalid")
        try:
            seeds.append(TraceSeed(row["term"], row["location"]))
        except (TypeError, ValueError) as error:
            raise ValueError("graph receipt seed identity is invalid") from error
    payload = _read_bound_receipt_bytes(root, str(draft["draft_id"]))
    receipt, errors = GRAPH.load_receipt_bytes(payload)
    if receipt is None or errors:
        raise ValueError("graph receipt is invalid or tampered")
    if GRAPH.canonical_receipt_bytes(receipt) != payload:
        raise ValueError("graph receipt is not canonical")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != binding.get("sha256"):
        raise ValueError("graph receipt digest is tampered")
    expected_root = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
    expected_request = GRAPH_COORDINATOR._request_sha256(
        _graph_draft_identity(draft), tuple(seeds),
        GRAPH_COORDINATOR._settings(graph_settings),
    )
    identity_providers = tuple(
        GRAPH.ProviderStatus(
            row["name"], row["status"], row["confidence"],
            row["version"], row["executable_sha256"],
        )
        for row in receipt["providers"] if row["name"] != "builtin"
    )
    expected_receipt_id = GRAPH_COORDINATOR._trace_identity(
        root, str(draft["draft_id"]), expected_request, tuple(seeds),
        GRAPH_COORDINATOR._settings(graph_settings), identity_providers,
    )
    if (
        receipt["receipt_id"] != selected_receipt_id
        or receipt["receipt_id"] != expected_receipt_id
        or receipt["draft_id"] != draft["draft_id"]
        or receipt["repo_root_sha256"] != expected_root
        or receipt["request_sha256"] != expected_request
        or binding.get("request_sha256") != expected_request
        or receipt["settings"] != graph_settings
        or receipt["cache"]["key"] != binding.get("cache_key")
    ):
        raise ValueError("graph receipt identity does not match draft request and settings")
    cache_key, source_inventory_sha256 = _receipt_source_inventory(root, receipt)
    if (
        binding.get("cache_key") != cache_key
        or binding.get("source_inventory_sha256") != source_inventory_sha256
    ):
        raise ValueError("graph source inventory cache does not match binding")
    _verify_receipt_sources(root, receipt)
    _verify_source_inventory(
        root, graph_settings, source_inventory_sha256
    )
    return {"receipt": receipt, "sha256": digest, "binding": binding}


def _path_confidence(path, nodes, edges) -> str:
    values = [nodes[node]["confidence"] for node in path["nodes"]]
    values.extend(edges[edge]["confidence"] for edge in path["edges"])
    return max(values, key=lambda value: GRAPH_CONFIDENCE_RANK[value])


def _validate_graph_coverage(
    analysis: Mapping[str, object], context: dict[str, object]
) -> None:
    receipt = context["receipt"]
    nodes = {row["id"]: row for row in receipt["nodes"]}
    edges = {row["id"]: row for row in receipt["edges"]}
    paths = {row["id"]: row for row in receipt["paths"]}
    frontier_nodes = {row["node"] for row in receipt["frontier"]}
    covered_nodes = set()
    impact_confidences = {}
    for impact in analysis["impacts"]:
        if "graph_path_keys" not in impact:
            raise ValueError("graph_path_keys is required for every graph-enabled impact")
        selected = impact["graph_path_keys"]
        if (
            not isinstance(selected, list)
            or len(selected) > 128
            or len(selected) != len(set(selected))
        ):
            raise ValueError("impact graph_path_keys must be a unique bounded array")
        selected_paths = []
        for key in selected:
            if not isinstance(key, str) or re.fullmatch(r"PATH-\d{3}", key) is None:
                raise ValueError("invalid graph path key")
            if key not in paths:
                raise ValueError(f"unknown graph path key {key}")
            selected_paths.append(paths[key])
            covered_nodes.update(paths[key]["nodes"])
        rationale = impact.get("coverage_rationale")
        if rationale is not None and (
            not isinstance(rationale, str)
            or not rationale.strip()
            or len(rationale.encode("utf-8")) > MAX_STRING_BYTES
        ):
            raise ValueError("coverage_rationale must be bounded nonempty text")
        if not selected_paths:
            if rationale is None or impact.get("evidence_level") != "unknown":
                raise ValueError(
                    "supplied-only or unknown graph coverage requires rationale and unknown evidence"
                )
            if impact.get("state") == "resolved":
                raise ValueError("resolved impact cannot rely on unknown graph evidence")
            impact_confidences[impact["key"]] = "unknown"
            continue
        confidences = [
            _path_confidence(path, nodes, edges) for path in selected_paths
        ]
        strongest = min(confidences, key=lambda value: GRAPH_CONFIDENCE_RANK[value])
        allowed_evidence = (
            "verified" if GRAPH_CONFIDENCE_RANK[strongest] <= 1
            else "inferred" if strongest == "structural-inferred"
            else "unknown"
        )
        if EVIDENCE_RANK.get(impact.get("evidence_level"), -1) < EVIDENCE_RANK[allowed_evidence]:
            raise ValueError("impact evidence confidence upgrades graph path evidence")
        if impact.get("state") == "resolved" and all(
            confidence == "lexical" for confidence in confidences
        ):
            raise ValueError("resolved impact cannot rely solely on lexical graph evidence")
        impact_confidences[impact["key"]] = strongest
    invariant_text = "\n".join(
        f"{row.get('behavior', '')}\n{row.get('evidence', '')}"
        for row in analysis["invariants"]
        if row.get("evidence_level") == "verified"
    )
    invariant_tokens = set(re.findall(r"[A-Za-z0-9_./-]+", invariant_text))
    invariant_nodes = {
        identifier
        for identifier, node in nodes.items()
        if node.get("source_sha256") is not None
        and any(
            isinstance(value, str) and len(value) >= 8 and value in invariant_tokens
            for value in (node.get("label"), node.get("location"))
        )
    }
    for identifier, node in sorted(nodes.items()):
        if (
            set(node["risk_domains"]) & HIGH_RISK_DOMAINS
            and identifier not in covered_nodes
            and identifier not in invariant_nodes
            and identifier not in frontier_nodes
        ):
            raise ValueError(f"uncovered high-risk graph node {identifier}")
    context["impact_paths"] = {
        row["key"]: list(row["graph_path_keys"]) for row in analysis["impacts"]
    }
    context["rationales"] = {
        row["key"]: row.get("coverage_rationale") for row in analysis["impacts"]
    }
    context["impact_confidences"] = impact_confidences


def _validate_persisted_trace_receipt(
    root: Path,
    draft: Mapping[str, object],
    normalized_seeds: Tuple[TraceSeed, ...],
    graph_settings: Mapping[str, object],
    expected_payload: Optional[bytes] = None,
) -> tuple[dict[str, object], bytes, str, str, str]:
    stored = _read_bound_receipt_bytes(root, str(draft["draft_id"]))
    if expected_payload is not None and stored != expected_payload:
        raise ValueError("persisted graph receipt does not match coordinator result")
    receipt_value, errors = GRAPH.load_receipt_bytes(stored)
    if receipt_value is None or errors:
        raise ValueError("persisted graph receipt is invalid")
    if GRAPH.canonical_receipt_bytes(receipt_value) != stored:
        raise ValueError("persisted graph receipt is not canonical")
    graph_draft = _graph_draft_identity(draft)
    settings = GRAPH_COORDINATOR._settings(graph_settings)
    expected_request_sha256 = GRAPH_COORDINATOR._request_sha256(
        graph_draft, normalized_seeds, settings
    )
    expected_root_sha256 = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
    identity_providers = tuple(
        GRAPH.ProviderStatus(
            row["name"], row["status"], row["confidence"],
            row["version"], row["executable_sha256"],
        )
        for row in receipt_value["providers"] if row["name"] != "builtin"
    )
    expected_receipt_id = GRAPH_COORDINATOR._trace_identity(
        root, str(draft["draft_id"]), expected_request_sha256,
        normalized_seeds, settings, identity_providers,
    )
    if (
        receipt_value["draft_id"] != draft["draft_id"]
        or receipt_value["receipt_id"] != expected_receipt_id
        or receipt_value["repo_root_sha256"] != expected_root_sha256
        or receipt_value["request_sha256"] != expected_request_sha256
        or receipt_value["settings"] != graph_settings
    ):
        raise ValueError("graph receipt identity does not match draft request and settings")
    cache_key, source_inventory_sha256 = _receipt_source_inventory(
        root, receipt_value
    )
    return (
        receipt_value, stored, expected_request_sha256,
        cache_key, source_inventory_sha256,
    )


def _bind_trace_receipt(
    root: Path,
    draft: Mapping[str, object],
    normalized_seeds: Tuple[TraceSeed, ...],
    graph_settings: Mapping[str, object],
    receipt_value: Mapping[str, object],
    stored: bytes,
    expected_request_sha256: str,
    cache_key: str,
    source_inventory_sha256: str,
) -> TraceResult:
    updated = dict(draft)
    digest = hashlib.sha256(stored).hexdigest()
    updated["graph_receipt"] = {
        "receipt_id": receipt_value["receipt_id"],
        "sha256": digest,
        "request_sha256": expected_request_sha256,
        "settings": graph_settings,
        "cache_key": cache_key,
        "source_inventory_sha256": source_inventory_sha256,
        "seeds": [
            {"term": seed.term, "location": seed.location}
            for seed in normalized_seeds
        ],
    }
    _replace_private_draft(root, str(draft["draft_id"]), updated)
    receipt_path = (
        root / ".requirements-impact-refiner" / "graph"
        / f"{draft['draft_id']}.json"
    )
    return TraceResult(
        receipt_id=str(receipt_value["receipt_id"]), receipt_path=receipt_path,
        receipt_sha256=digest, compact_graph=_compact_graph(receipt_value),
        budget_status=str(receipt_value["budget_status"]),
    )


def trace_impact(request: TraceRequest) -> TraceResult:
    original_root = Path(request.repo_root)
    if original_root.is_symlink():
        raise ValueError("repository root symlink is unsafe for graph tracing")
    root = _root(original_root)
    if not isinstance(request.seeds, tuple):
        raise ValueError("trace seeds must be a tuple")
    if not request.seeds or len(request.seeds) > MAX_TRACE_SEEDS:
        raise ValueError("trace seeds must contain between 1 and 128 items")
    for seed in request.seeds:
        if not isinstance(seed, TraceSeed):
            raise ValueError("trace seeds must contain TraceSeed values")
        if not isinstance(seed.term, str) or not seed.term.strip():
            raise ValueError("trace seed term must be nonempty")
        if seed.location is not None and not GRAPH._safe_path(seed.location):
            raise ValueError("trace seed location must be a safe repository-relative path")
    normalized_seeds = tuple(
        sorted(set(request.seeds), key=GRAPH_COORDINATOR._seed_key)
    )
    _bounded(
        {"seeds": [
            {"term": seed.term, "location": seed.location}
            for seed in normalized_seeds
        ]},
        MAX_TRACE_BYTES,
        "trace input",
    )
    draft = load_draft(root, request.draft_id)
    settings = draft.get("settings")
    graph_settings = settings.get("impact_graph") if isinstance(settings, dict) else None
    if not isinstance(graph_settings, dict):
        raise ValueError("draft graph settings are invalid")
    if graph_settings.get("enabled") is not True:
        raise ValueError("impact graph is disabled for this draft")
    deadline = GRAPH_COORDINATOR.Deadline(
        time, int(graph_settings["max_seconds"])
    )
    receipt_path = (
        root / ".requirements-impact-refiner" / "graph" / f"{request.draft_id}.json"
    )
    with _report_lock(root, str(draft["report_id"]), deadline=deadline):
        draft = load_draft(root, request.draft_id)
        if draft.get("consumed") is True:
            raise ValueError("draft is already consumed")
        if draft.get("graph_receipt") is not None:
            raise ValueError("draft already has a graph receipt")
        graph_draft = _graph_draft_identity(draft)
        if receipt_path.exists() or receipt_path.is_symlink():
            validated = _validate_persisted_trace_receipt(
                root, draft, normalized_seeds, graph_settings
            )
            return _bind_trace_receipt(
                root, draft, normalized_seeds, graph_settings, *validated
            )
        receipt = GRAPH_COORDINATOR.trace_impact(
            root, graph_draft, normalized_seeds, graph_settings,
            clock=time, deadline=deadline,
        )
        payload = GRAPH.canonical_receipt_bytes(receipt)
        if not receipt_path.is_file() or receipt_path.is_symlink():
            raise ValueError("graph receipt publication failed")
        validated = _validate_persisted_trace_receipt(
            root, draft, normalized_seeds, graph_settings, payload
        )
        return _bind_trace_receipt(
            root, draft, normalized_seeds, graph_settings, *validated
        )


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
        if len(rows) > 128:
            raise ValueError(f"{section} has too many rows")
        keys = []
        for row in rows:
            if section == "impacts":
                if not isinstance(row, dict):
                    raise ValueError("impact must be an object")
                unknown = sorted(set(row) - expected - IMPACT_OPTIONAL_KEYS)
                missing = sorted(expected - set(row))
                if unknown:
                    raise ValueError(f"unknown impact key {unknown[0]}")
                if missing:
                    raise ValueError(f"missing impact key {missing[0]}")
            else:
                _check_keys(section[:-1], row, expected)
            if "key" in row:
                keys.append(_local_key(row["key"], section[:-1]))
            if section == "impacts":
                _check_keys("impact summary", row["summary"], SUMMARY_KEYS)
                for name in ("invariant_keys", "decision_keys", "criterion_keys"):
                    if not isinstance(row[name], list) or len(row[name]) > 128:
                        raise ValueError(f"impact {name} has too many items")
            if section == "decisions" and (
                not isinstance(row["accepted_impact_keys"], list)
                or len(row["accepted_impact_keys"]) > 128
            ):
                raise ValueError("decision accepted_impact_keys has too many items")
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate {section} local key")
    if analysis["phase"] == "pre-decision":
        _check_keys("decision_needed", analysis["decision_needed"], {"question", "options"})
        options = analysis["decision_needed"]["options"]
        if not isinstance(options, list) or not 2 <= len(options) <= 3:
            raise ValueError("decision_needed requires two or three options")
        for option in options:
            _check_keys("decision option", option, {"option", "impact_keys", "tradeoff"})
            if not isinstance(option["impact_keys"], list) or len(option["impact_keys"]) > 128:
                raise ValueError("decision option impact_keys has too many items")
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


def _build_state(draft, analysis, graph_context=None):
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
        {"id": requirement_id, "request": draft["request"], "source": "User request and supplied repository evidence."}
        if prior_state is None
        else prior_state["original_requirement"]
    )
    if draft.get("adapter") == "superpowers":
        handoff_workflow = SUPERPOWERS_HANDOFF_MARKER
    elif analysis["phase"] == "pre-decision" or any(
        row["state"] == "blocked" for row in impacts
    ):
        handoff_workflow = "Not ready"
    else:
        handoff_workflow = analysis["workflow"]
    scope = list(analysis["scope"])
    if graph_context is not None:
        receipt = graph_context["receipt"]
        receipt_nodes = {row["id"]: row for row in receipt["nodes"]}
        receipt_paths = {row["id"]: row for row in receipt["paths"]}
        for row in analysis["impacts"]:
            path_descriptions = []
            for path_key in graph_context["impact_paths"][row["key"]]:
                path = receipt_paths[path_key]
                labels = [receipt_nodes[node]["label"] for node in path["nodes"]]
                path_descriptions.append(f"{path_key}: " + " → ".join(labels))
            rationale = graph_context["rationales"].get(row["key"])
            scope.append({
                "boundary": f"Graph paths for {impact_ids[row['key']]}",
                "evidence": "; ".join(path_descriptions) if path_descriptions else str(rationale),
                "confidence": (
                    f"{graph_context['impact_confidences'][row['key']]}; "
                    "receipt-validated graph evidence; no confidence upgrade."
                ),
            })
        provider_summary = [
            f"{row['name']} ({row['status']})" for row in receipt["providers"]
        ]
        elapsed = int(receipt["timings_ms"].get("total", 0))
        frontier_ids = ",".join(row["id"] for row in receipt["frontier"]) or "none"
        scope.append({
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
        })
        if len(scope) > 128:
            raise ValueError("scope has too many rows after graph coverage injection")
        if any(
            len(value.encode("utf-8")) > MAX_STRING_BYTES
            for row in scope for value in row.values() if isinstance(value, str)
        ):
            raise ValueError("graph coverage scope exceeds string limit")
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
        "scope": scope,
        "handoff": {
            "refined_requirement": requirement_id if analysis["phase"] == "post-decision" else "Not ready until the pending decision is selected.",
            "report_ids": all_report_ids,
            "remaining_risks": remaining,
            "criteria": list(criterion_ids.values()),
            "workflow": handoff_workflow,
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


@contextmanager
def _report_lock(root: Path, report_id: str, deadline=None):
    report_dir = report_store.report_directory(root, report_id, create=True)
    lock_path = report_dir / ".controller.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise ValueError(f"cannot open controller lock: {error}") from error
    locked = False
    try:
        if fcntl is not None:
            if deadline is None:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                locked = True
            else:
                while True:
                    if deadline.expired():
                        raise ValueError(
                            "graph trace deadline exhausted waiting for controller lock"
                        )
                    try:
                        fcntl.flock(
                            descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB
                        )
                        locked = True
                        break
                    except BlockingIOError:
                        time.sleep(min(0.01, deadline.remaining()))
        if deadline is not None and deadline.expired():
            raise ValueError(
                "graph trace deadline exhausted waiting for controller lock"
            )
        yield
    finally:
        if fcntl is not None and locked:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _write_controller_metadata(
    root: Path,
    draft: Mapping[str, object],
    state_bytes: bytes,
    key_map: Mapping[str, object],
    graph_receipt: Optional[Mapping[str, object]] = None,
) -> None:
    path = _controller_metadata_path(
        str(draft["report_id"]), int(draft["revision"]), root
    )
    metadata = {
            "schema_version": 1,
            "draft_id": draft["draft_id"],
            "report_id": draft["report_id"],
            "revision": draft["revision"],
            "state_sha256": hashlib.sha256(state_bytes).hexdigest(),
            "key_map": key_map,
    }
    if graph_receipt is not None:
        metadata["graph_receipt"] = dict(graph_receipt)
    payload = _canonical_bytes(metadata)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=f".{path.name}-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    except FileExistsError:
        try:
            existing_bytes = path.read_bytes() if not path.is_symlink() else b""
            if existing_bytes != payload:
                existing = json.loads(existing_bytes.decode("utf-8", errors="strict"))
                same_draft = (
                    isinstance(existing, dict)
                    and existing.get("draft_id") == draft["draft_id"]
                    and existing.get("report_id") == draft["report_id"]
                    and existing.get("revision") == draft["revision"]
                )
                report_dir = path.parent
                revision = int(draft["revision"])
                artifacts_exist = any(
                    (report_dir / f"revision-{revision:04d}.{suffix}").exists()
                    for suffix in ("json", "md")
                )
                current = report_store.load_current(root, str(draft["report_id"]))
                if not same_draft or artifacts_exist or (
                    current is not None and current.revision >= revision
                ):
                    raise ValueError("controller revision belongs to another draft")
                os.replace(temporary, path)
                temporary = None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"cannot verify controller lineage: {error}") from error
    except OSError as error:
        raise ValueError(f"cannot write controller lineage: {error}") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def finalize_refinement(request: FinalizeRequest) -> FinalizeResult:
    root = _root(request.repo_root)
    _bounded(request.analysis, MAX_FINALIZE_BYTES, "finalize input")
    draft = load_draft(root, request.draft_id)
    if draft.get("consumed") is True:
        raise ValueError("draft is already consumed")
    with _report_lock(root, str(draft["report_id"])):
        draft = load_draft(root, request.draft_id)
        if draft.get("consumed") is True:
            raise ValueError("draft is already consumed")
        graph_settings = draft.get("settings", {}).get("impact_graph", {})
        graph_context = None
        if graph_settings.get("enabled") is True:
            graph_context = _load_graph_context(
                root, draft, request.graph_receipt_id
            )
            _validate_analysis(request.analysis)
            _validate_graph_coverage(request.analysis, graph_context)
        elif request.graph_receipt_id is not None:
            raise ValueError("graph_receipt_id is not allowed when impact graph is disabled")
        state, key_map = _build_state(draft, request.analysis, graph_context)
        state_bytes = _canonical_bytes(state)
        _write_controller_metadata(
            root, draft, state_bytes, key_map,
            None if graph_context is None else {
                "receipt_id": graph_context["receipt"]["receipt_id"],
                "sha256": graph_context["sha256"],
            },
        )
        try:
            published = report_store.publish_revision(
                root, state_bytes, resume_partial=True
            )
        except (FileExistsError, report_store.ReportStoreError) as error:
            raise ValueError(f"controller publication failed: {error}") from error
        stored_state, errors = compact_state.load_state_bytes(
            published.state_path.read_bytes()
        )
        if errors or stored_state is None:
            raise ValueError("published state could not be verified")
        delivery = stored_state["settings"]["delivery"]
        display = (
            impact_renderer.render_compact(stored_state)
            if delivery == "compact"
            else impact_renderer.render_markdown(stored_state)
        )
        if display.endswith("\n"):
            display = display[:-1]
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
