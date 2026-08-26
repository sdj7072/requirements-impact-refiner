#!/usr/bin/env python3
"""Trusted stale-report binding and deterministic delta-scan seed derivation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Callable, cast

MAX_DELTA_SECONDS = 3
MAX_DELTA_SEEDS = 512
MAX_SOURCE_FILES = 500
MAX_SOURCE_BYTES = 8_000_000
MAX_FILE_BYTES = 1_048_576
MAX_POINTER_BYTES = 8 * 1024
MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_MARKDOWN_BYTES = 4 * 1024 * 1024
MAX_CONTROLLER_BYTES = 256 * 1024

REPORT_ID_PATTERN = re.compile(r"RPT-\d{3}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_PATH = re.compile(r"(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+")
_BARE_SOURCE = re.compile(
    r"(?<![A-Za-z0-9_./-])[A-Za-z0-9_-]+"
    r"\.(?:c|cc|cpp|cs|go|h|hpp|java|js|jsx|json|kt|kts|m|mm|php|py|rb|rs|"
    r"scala|sh|sql|swift|toml|ts|tsx|vue|xml|yaml|yml)"
    r"(?![A-Za-z0-9_./-])",
    re.IGNORECASE,
)

DEFAULT_EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".quality-venv",
        ".requirements-impact-refiner",
        ".pytest_cache",
        "__pycache__",
        ".next",
        ".venv",
        "venv",
        "build",
        "coverage",
        "dist",
        "generated",
        "node_modules",
        "target",
        "vendor",
    }
)


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and len(value.encode("utf-8")) <= 4096
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _root(value: Path | str) -> Path:
    path = Path(value)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError("delta repository root is unavailable") from error
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode) or not resolved.is_dir():
        raise ValueError("delta repository root must be a real directory")
    return resolved


def _open_below_root(root: Path, relative: str) -> int:
    if not _safe_relative(relative):
        raise ValueError("delta source path is unsafe")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    parts = PurePosixPath(relative).parts
    parent = os.open(root, directory_flags)
    try:
        for part in parts[:-1]:
            child = os.open(part, directory_flags, dir_fd=parent)
            os.close(parent)
            parent = child
        return os.open(parts[-1], file_flags, dir_fd=parent)
    finally:
        os.close(parent)


def _read_source(root: Path, relative: str) -> tuple[bytes | None, str | None]:
    descriptor = None
    try:
        descriptor = _open_below_root(root, relative)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return None, "not-regular"
        if before.st_size > MAX_FILE_BYTES:
            return None, "oversized"
        payload = bytearray()
        while len(payload) <= MAX_FILE_BYTES:
            chunk = os.read(descriptor, min(65_536, MAX_FILE_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            return None, "unreadable-source"
        if len(payload) > MAX_FILE_BYTES:
            return None, "oversized"
        raw = bytes(payload)
        if b"\x00" in raw:
            return None, "binary"
        try:
            raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return None, "encoding"
        return raw, None
    except (OSError, ValueError):
        return None, "unreadable-source"
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _open_directory_at(parent: int, name: str, label: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(name, flags, dir_fd=parent)
    except OSError as error:
        raise ValueError(f"delta {label} directory is unsafe") from error


def _read_artifact_at(
    parent: int,
    name: str,
    maximum: int,
    label: str,
    *,
    private: bool = False,
) -> bytes:
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError(f"delta {label} artifact name is unsafe")
    descriptor = None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or before.st_size > maximum
            or (private and stat.S_IMODE(before.st_mode) != 0o600)
            or (private and before.st_nlink != 1)
            or (private and before.st_uid != os.fstat(parent).st_uid)
        ):
            raise ValueError(f"delta {label} artifact is unsafe")
        payload = bytearray()
        while len(payload) <= maximum:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or len(payload) > maximum:
            raise ValueError(f"delta {label} artifact changed while reading")
        return bytes(payload)
    except OSError as error:
        raise ValueError(f"delta {label} artifact is unavailable or unsafe") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _entry_exists_at(parent: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise ValueError("delta artifact identity is unsafe") from error
    return True


def _json_object(payload: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError(f"delta {label} artifact is invalid") from error
    if not isinstance(value, dict):
        raise ValueError(f"delta {label} artifact must be an object")
    return value


def _canonical_json_variants(value: object) -> tuple[bytes, bytes]:
    base = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return base, base + b"\n"


def load_trusted_previous_artifacts(
    repo_root: Path | str,
    trusted_previous: object,
    *,
    state_loader: Callable[[bytes], tuple[dict[str, object] | None, Sequence[str]]],
    receipt_loader: Callable[[bytes], tuple[dict[str, object] | None, Sequence[str]]],
    canonical_receipt_bytes: Callable[[Mapping[str, object]], bytes],
    max_receipt_bytes: int,
    expected_payload_sha256: str,
    expected_repository_evidence_sha256: str,
) -> tuple[dict[str, object], dict[str, object], str, str]:
    """Read one selected revision and historical graph through descriptor-bound paths."""
    root = _root(repo_root)
    report_id = _trusted_value(trusted_previous, "report_id")
    revision = _trusted_value(trusted_previous, "revision")
    markdown_sha256 = _trusted_value(trusted_previous, "markdown_sha256")
    requirement_sha256 = _trusted_value(trusted_previous, "requirement_sha256")
    source_inventory_sha256 = _trusted_value(trusted_previous, "source_inventory_sha256")
    if (
        _trusted_value(trusted_previous, "status") != "stale"
        or not isinstance(report_id, str)
        or REPORT_ID_PATTERN.fullmatch(report_id) is None
        or type(revision) is not int
        or revision < 1
        or not isinstance(markdown_sha256, str)
        or SHA256_PATTERN.fullmatch(markdown_sha256) is None
        or not isinstance(requirement_sha256, str)
        or SHA256_PATTERN.fullmatch(requirement_sha256) is None
        or (
            source_inventory_sha256 is not None
            and (
                not isinstance(source_inventory_sha256, str)
                or SHA256_PATTERN.fullmatch(source_inventory_sha256) is None
            )
        )
        or SHA256_PATTERN.fullmatch(expected_payload_sha256) is None
        or SHA256_PATTERN.fullmatch(expected_repository_evidence_sha256) is None
    ):
        raise ValueError("delta trusted previous identity is invalid")
    if type(max_receipt_bytes) is not int or max_receipt_bytes < 1:
        raise ValueError("delta graph receipt byte limit is invalid")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    root_fd = os.open(root, directory_flags)
    private_fd = reports_fd = report_fd = graph_fd = drafts_fd = scans_fd = None
    try:
        private_fd = _open_directory_at(root_fd, ".requirements-impact-refiner", "private")
        reports_fd = _open_directory_at(private_fd, "reports", "reports")
        report_fd = _open_directory_at(reports_fd, report_id, "report")
        pointer_before = _read_artifact_at(
            report_fd, "current.json", MAX_POINTER_BYTES, "report pointer"
        )
        pointer = _json_object(pointer_before, "report pointer")
        expected_pointer_keys = {
            "schema_version",
            "report_id",
            "revision",
            "state",
            "markdown",
            "markdown_sha256",
        }
        state_name = f"revision-{revision:04d}.json"
        markdown_name = f"revision-{revision:04d}.md"
        if (
            set(pointer) != expected_pointer_keys
            or pointer.get("schema_version") != 1
            or pointer.get("report_id") != report_id
            or pointer.get("revision") != revision
            or pointer.get("state") != state_name
            or pointer.get("markdown") != markdown_name
            or pointer.get("markdown_sha256") != markdown_sha256
        ):
            raise ValueError("delta report pointer does not match trusted previous identity")
        state_payload = _read_artifact_at(report_fd, state_name, MAX_STATE_BYTES, "state")
        markdown_payload = _read_artifact_at(
            report_fd, markdown_name, MAX_MARKDOWN_BYTES, "Markdown"
        )
        if hashlib.sha256(markdown_payload).hexdigest() != markdown_sha256:
            raise ValueError("delta Markdown artifact does not match trusted previous identity")
        state, state_errors = state_loader(state_payload)
        if state is None or state_errors or not isinstance(state, dict):
            raise ValueError("delta state artifact is invalid")
        state_report = state.get("report")
        if (
            not isinstance(state_report, Mapping)
            or state_report.get("id") != report_id
            or state_report.get("revision") != revision
        ):
            raise ValueError("delta state artifact identity is invalid")
        state_sha256 = hashlib.sha256(state_payload).hexdigest()
        controller_name = f"revision-{revision:04d}.controller.json"
        controller_payload = _read_artifact_at(
            report_fd,
            controller_name,
            MAX_CONTROLLER_BYTES,
            "controller",
            private=True,
        )
        controller = _json_object(controller_payload, "controller")
        if controller_payload not in _canonical_json_variants(controller):
            raise ValueError("delta controller artifact is not canonical")
        expected_controller_fields = {
            "schema_version",
            "draft_id",
            "report_id",
            "revision",
            "state_sha256",
            "key_map",
            "graph_receipt",
            "analysis_sha256",
            "context_identity",
        }
        draft_id = controller.get("draft_id")
        context_identity = controller.get("context_identity")
        expected_context_fields = {
            "payload_sha256",
            "repo_root_sha256",
            "requirement_sha256",
            "state_sha256",
            "repository_evidence_sha256",
            "source_inventory_available",
            "source_inventory_complete",
            "source_inventory_git_tracked_only",
            "source_inventory_sha256",
        }
        expected_root_sha256 = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
        if (
            set(controller) != expected_controller_fields
            or controller.get("schema_version") != 2
            or not isinstance(draft_id, str)
            or re.fullmatch(r"[0-9a-f]{32}", draft_id) is None
            or controller.get("report_id") != report_id
            or controller.get("revision") != revision
            or controller.get("state_sha256") != state_sha256
            or not isinstance(controller.get("key_map"), Mapping)
            or not isinstance(controller.get("analysis_sha256"), str)
            or SHA256_PATTERN.fullmatch(str(controller.get("analysis_sha256"))) is None
            or not isinstance(context_identity, Mapping)
            or set(context_identity) != expected_context_fields
        ):
            if controller.get("schema_version") != 2:
                raise ValueError("delta requires controller metadata schema version 2")
            raise ValueError("delta controller artifact identity is invalid")
        trusted_context_identity = cast(Mapping[str, object], context_identity)
        if (
            trusted_context_identity.get("payload_sha256") != expected_payload_sha256
            or trusted_context_identity.get("repo_root_sha256") != expected_root_sha256
            or trusted_context_identity.get("requirement_sha256") != requirement_sha256
            or trusted_context_identity.get("state_sha256") != state_sha256
            or trusted_context_identity.get("repository_evidence_sha256")
            != expected_repository_evidence_sha256
            or trusted_context_identity.get("source_inventory_sha256") != source_inventory_sha256
            or not isinstance(trusted_context_identity.get("source_inventory_available"), bool)
            or not isinstance(trusted_context_identity.get("source_inventory_complete"), bool)
            or not isinstance(
                trusted_context_identity.get("source_inventory_git_tracked_only"), bool
            )
            or (
                trusted_context_identity.get("source_inventory_complete") is True
                and trusted_context_identity.get("source_inventory_available") is not True
            )
            or (
                trusted_context_identity.get("source_inventory_git_tracked_only") is True
                and (
                    trusted_context_identity.get("source_inventory_available") is not True
                    or trusted_context_identity.get("source_inventory_complete") is not True
                )
            )
        ):
            raise ValueError("delta controller context/payload identity is invalid")
        graph_binding = controller.get("graph_receipt")
        graph: dict[str, object] = {}
        if (
            not isinstance(graph_binding, Mapping)
            or set(graph_binding) != {"receipt_id", "sha256"}
            or not isinstance(graph_binding.get("receipt_id"), str)
            or re.fullmatch(r"[0-9a-f]{32}", graph_binding["receipt_id"]) is None
            or not isinstance(graph_binding.get("sha256"), str)
            or SHA256_PATTERN.fullmatch(graph_binding["sha256"]) is None
        ):
            raise ValueError("delta graph binding identity is invalid")
        if isinstance(graph_binding, Mapping):
            graph_payload = None
            graph_name = f"{draft_id}.json"
            expected_graph_draft_id = draft_id
            if _entry_exists_at(private_fd, "graph"):
                graph_fd = _open_directory_at(private_fd, "graph", "graph")
                if _entry_exists_at(graph_fd, graph_name):
                    graph_payload = _read_artifact_at(
                        graph_fd,
                        graph_name,
                        max_receipt_bytes,
                        "graph artifact",
                        private=True,
                    )
            if graph_payload is not None:
                loaded, receipt_errors = receipt_loader(graph_payload)
                if loaded is None or receipt_errors or not isinstance(loaded, dict):
                    raise ValueError("delta graph artifact is invalid")
                graph = loaded
                try:
                    canonical_graph = canonical_receipt_bytes(graph)
                except (RecursionError, TypeError, ValueError) as error:
                    raise ValueError("delta graph artifact is not canonical") from error
                if canonical_graph != graph_payload:
                    raise ValueError("delta graph artifact is not canonical")
            else:
                drafts_fd = _open_directory_at(private_fd, "drafts", "drafts")
                draft_payload = _read_artifact_at(
                    drafts_fd,
                    f"{draft_id}.json",
                    MAX_STATE_BYTES,
                    "completed draft",
                    private=True,
                )
                draft = _json_object(draft_payload, "completed draft")
                if draft_payload not in _canonical_json_variants(draft):
                    raise ValueError("delta completed draft artifact is not canonical")
                promoted = draft.get("promoted_scan")
                if (
                    draft.get("draft_id") != draft_id
                    or draft.get("repo_root") != str(root)
                    or draft.get("report_id") != report_id
                    or draft.get("revision") != revision
                    or not isinstance(promoted, Mapping)
                    or set(promoted)
                    != {
                        "scan_id",
                        "sha256",
                        "receipt_id",
                        "receipt_sha256",
                    }
                ):
                    raise ValueError("delta promoted scan binding is invalid")
                scan_id = promoted.get("scan_id")
                if (
                    not isinstance(scan_id, str)
                    or re.fullmatch(r"[0-9a-f]{32}", scan_id) is None
                    or not isinstance(promoted.get("sha256"), str)
                    or SHA256_PATTERN.fullmatch(str(promoted.get("sha256"))) is None
                    or promoted.get("receipt_id") != graph_binding["receipt_id"]
                    or promoted.get("receipt_sha256") != graph_binding["sha256"]
                ):
                    raise ValueError("delta promoted scan binding is invalid")
                expected_graph_draft_id = scan_id
                scans_fd = _open_directory_at(private_fd, "scans", "scans")
                wrapper_payload = _read_artifact_at(
                    scans_fd,
                    f"{scan_id}.json",
                    max_receipt_bytes,
                    "promoted scan",
                    private=True,
                )
                wrapper = _json_object(wrapper_payload, "promoted scan")
                wrapper_graph = wrapper.get("graph_receipt")
                if (
                    wrapper_payload != _canonical_json_variants(wrapper)[0]
                    or hashlib.sha256(wrapper_payload).hexdigest() != promoted["sha256"]
                    or wrapper.get("scan_id") != scan_id
                ):
                    raise ValueError("delta promoted scan artifact is invalid")
                if not isinstance(wrapper_graph, Mapping):
                    raise ValueError("delta promoted scan artifact is invalid")
                try:
                    canonical_graph = canonical_receipt_bytes(wrapper_graph)
                except (RecursionError, TypeError, ValueError) as error:
                    raise ValueError("delta promoted graph artifact is invalid") from error
                loaded, receipt_errors = receipt_loader(canonical_graph)
                if loaded is None or receipt_errors or not isinstance(loaded, dict):
                    raise ValueError("delta promoted graph artifact is invalid")
                graph = loaded
            if (
                hashlib.sha256(canonical_graph).hexdigest() != graph_binding["sha256"]
                or graph.get("receipt_id") != graph_binding["receipt_id"]
                or graph.get("draft_id") != expected_graph_draft_id
                or graph.get("repo_root_sha256") != expected_root_sha256
            ):
                raise ValueError("delta graph artifact identity is invalid")
            state_settings = state.get("settings")
            state_graph_settings = (
                state_settings.get("impact_graph") if isinstance(state_settings, Mapping) else None
            )
            if state_graph_settings is not None and graph.get("settings") != state_graph_settings:
                raise ValueError("delta graph settings do not match previous state")
        pointer_after = _read_artifact_at(
            report_fd, "current.json", MAX_POINTER_BYTES, "report pointer"
        )
        if pointer_after != pointer_before:
            raise ValueError("delta report pointer changed while binding artifacts")
        trusted_graph_binding = cast(Mapping[str, object], graph_binding)
        return (
            state,
            graph,
            str(trusted_graph_binding["receipt_id"]),
            str(trusted_graph_binding["sha256"]),
        )
    except OSError as error:
        raise ValueError("delta artifact root is unavailable or unsafe") from error
    finally:
        for descriptor in (
            scans_fd,
            drafts_fd,
            graph_fd,
            report_fd,
            reports_fd,
            private_fd,
            root_fd,
        ):
            if descriptor is not None:
                os.close(descriptor)


def _source_sha256(root: Path, relative: str) -> str | None:
    payload, reason = _read_source(root, relative)
    return None if payload is None or reason is not None else hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class DeltaSeed:
    term: str
    location: str | None
    derivation: str
    source_sha256: str | None
    provenance: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.term, str) or not self.term.strip() or len(self.term) > 4096:
            raise ValueError("delta seed term must be bounded nonblank text")
        if self.location is not None and not _safe_relative(self.location):
            raise ValueError("delta seed location must be a safe repository-relative path")
        if (
            not isinstance(self.derivation, str)
            or not self.derivation.strip()
            or len(self.derivation) > 128
        ):
            raise ValueError("delta seed derivation must be bounded nonblank text")
        if self.source_sha256 is not None and SHA256_PATTERN.fullmatch(self.source_sha256) is None:
            raise ValueError("delta seed source digest is invalid")
        if not isinstance(self.provenance, Mapping):
            raise TypeError("delta seed provenance must be an object")
        object.__setattr__(self, "provenance", _freeze(self.provenance))

    def to_mapping(self) -> dict[str, object]:
        return {
            "term": self.term,
            "location": self.location,
            "derivation": self.derivation,
            "source_sha256": self.source_sha256,
        }

    def provenance_mapping(self) -> dict[str, object]:
        return {
            "term": self.term,
            "location": self.location,
            "derivation": self.derivation,
            "provenance": _thaw(self.provenance),
        }


@dataclass(frozen=True)
class DeltaSeedSelection:
    seeds: tuple[DeltaSeed, ...]
    omitted_count: int
    omitted_by_source: Mapping[str, int]

    def __post_init__(self) -> None:
        if not isinstance(self.seeds, tuple) or any(
            not isinstance(seed, DeltaSeed) for seed in self.seeds
        ):
            raise TypeError("delta seed selection seeds must be a tuple")
        if type(self.omitted_count) is not int or self.omitted_count < 0:
            raise ValueError("delta omitted seed count is invalid")
        if (
            not isinstance(self.omitted_by_source, Mapping)
            or any(
                not isinstance(source, str) or not source or type(count) is not int or count < 1
                for source, count in self.omitted_by_source.items()
            )
            or sum(self.omitted_by_source.values()) != self.omitted_count
        ):
            raise ValueError("delta omitted seed provenance is invalid")
        object.__setattr__(
            self,
            "omitted_by_source",
            MappingProxyType(dict(sorted(self.omitted_by_source.items()))),
        )


@dataclass(frozen=True)
class DeltaSourceInventory:
    digests: Mapping[str, str]
    complete: bool
    reason: str | None

    def __post_init__(self) -> None:
        normalized: dict[str, str] = {}
        for location, digest in self.digests.items():
            if not _safe_relative(location) or SHA256_PATTERN.fullmatch(digest) is None:
                raise ValueError("delta source inventory contains an unsafe identity")
            normalized[location] = digest
        if not isinstance(self.complete, bool):
            raise TypeError("delta source inventory completeness must be boolean")
        if self.complete != (self.reason is None):
            raise ValueError("delta source inventory reason is inconsistent")
        object.__setattr__(self, "digests", MappingProxyType(dict(sorted(normalized.items()))))


@dataclass(frozen=True)
class DeltaScanContext:
    repo_root: Path
    previous_report_id: str
    previous_revision: int
    previous_markdown_sha256: str
    previous_state_sha256: str
    previous_display_text: str
    changed_paths: tuple[str, ...]
    changed_count: int | None
    previous_state: Mapping[str, object]
    previous_graph_receipt: Mapping[str, object]
    previous_graph_receipt_id: str
    previous_graph_sha256: str
    max_seconds: int

    def __post_init__(self) -> None:
        root = _root(self.repo_root)
        if REPORT_ID_PATTERN.fullmatch(self.previous_report_id) is None:
            raise ValueError("delta previous report ID is invalid")
        if type(self.previous_revision) is not int or self.previous_revision < 1:
            raise ValueError("delta previous revision is invalid")
        for label, digest in (
            ("Markdown", self.previous_markdown_sha256),
            ("state", self.previous_state_sha256),
        ):
            if SHA256_PATTERN.fullmatch(digest) is None:
                raise ValueError(f"delta previous {label} digest is invalid")
        if (
            not isinstance(self.previous_display_text, str)
            or not self.previous_display_text.strip()
        ):
            raise ValueError("delta previous display text is required")
        if (
            not isinstance(self.changed_paths, tuple)
            or any(not _safe_relative(path) for path in self.changed_paths)
            or tuple(sorted(set(self.changed_paths))) != self.changed_paths
        ):
            raise ValueError("delta changed paths must be unique sorted safe paths")
        if self.changed_count is not None and (
            type(self.changed_count) is not int or self.changed_count < len(self.changed_paths)
        ):
            raise ValueError("delta changed count is invalid")
        if not isinstance(self.previous_state, Mapping) or not isinstance(
            self.previous_graph_receipt, Mapping
        ):
            raise TypeError("delta previous state and graph must be objects")
        if (
            re.fullmatch(r"[0-9a-f]{32}", self.previous_graph_receipt_id) is None
            or SHA256_PATTERN.fullmatch(self.previous_graph_sha256) is None
        ):
            raise ValueError("delta previous graph binding is invalid")
        canonical_graph = _canonical_graph_bytes(self.previous_graph_receipt)
        if (
            self.previous_graph_receipt.get("receipt_id") != self.previous_graph_receipt_id
            or hashlib.sha256(canonical_graph).hexdigest() != self.previous_graph_sha256
        ):
            raise ValueError("delta previous graph does not match exact prior graph binding")
        if type(self.max_seconds) is not int or not 1 <= self.max_seconds <= MAX_DELTA_SECONDS:
            raise ValueError("delta max_seconds must be an integer from 1 to 3")
        object.__setattr__(self, "repo_root", root)
        object.__setattr__(self, "previous_state", _freeze(self.previous_state))
        object.__setattr__(self, "previous_graph_receipt", _freeze(self.previous_graph_receipt))

    @property
    def previous_frontier(self) -> tuple[Mapping[str, object], ...]:
        value = self.previous_graph_receipt.get("frontier", ())
        if not isinstance(value, (tuple, list)):
            return ()
        return tuple(row for row in value if isinstance(row, Mapping))

    def derive_seeds(self, request_seeds: Sequence[object] = ()) -> tuple[DeltaSeed, ...]:
        return derive_delta_seeds(self, request_seeds=request_seeds)

    def derive_seed_selection(self, request_seeds: Sequence[object] = ()) -> DeltaSeedSelection:
        return derive_delta_seed_selection(self, request_seeds=request_seeds)

    def to_mapping(self, selection: DeltaSeedSelection | Sequence[DeltaSeed]) -> dict[str, object]:
        return context_mapping(self, selection)

    def merge_frontier(
        self,
        graph: Mapping[str, object],
        selection: DeltaSeedSelection | None = None,
    ) -> tuple[Mapping[str, object], ...]:
        return surviving_frontier(self, graph, selection)


def _trusted_value(result: object, name: str) -> object:
    if isinstance(result, Mapping):
        return result.get(name)
    return getattr(result, name, None)


def validate_delta_hints(
    trusted_previous: object,
    previous_report_id: str,
    previous_revision: int,
    changed_paths: Sequence[str],
) -> tuple[str, ...]:
    hint_paths = tuple(changed_paths)
    if (
        _trusted_value(trusted_previous, "status") != "stale"
        or _trusted_value(trusted_previous, "report_id") != previous_report_id
        or _trusted_value(trusted_previous, "revision") != previous_revision
        or _trusted_value(trusted_previous, "changed_paths") != hint_paths
    ):
        raise ValueError("delta hints do not match one trusted stale previous lookup")
    return hint_paths


def _canonical_state_bytes(value: Mapping[str, object]) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
    except (RecursionError, TypeError, ValueError) as error:
        raise ValueError("delta previous state is not canonical JSON") from error


def _canonical_graph_bytes(value: Mapping[str, object]) -> bytes:
    try:
        return json.dumps(
            _thaw(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (RecursionError, TypeError, ValueError) as error:
        raise ValueError("delta previous graph is not canonical JSON") from error


def bind_delta_context(
    repo_root: Path | str,
    trusted_previous: object,
    previous_state: Mapping[str, object],
    previous_graph_receipt: Mapping[str, object],
    *,
    previous_report_id: str,
    previous_revision: int,
    changed_paths: Sequence[str],
    configured_max_seconds: object = MAX_DELTA_SECONDS,
    previous_graph_receipt_id: str | None = None,
    previous_graph_sha256: str | None = None,
) -> DeltaScanContext:
    """Bind untrusted client hints to one backend-owned stale lookup and its artifacts."""
    root = _root(repo_root)
    hint_paths = validate_delta_hints(
        trusted_previous, previous_report_id, previous_revision, changed_paths
    )
    if type(configured_max_seconds) is not int or configured_max_seconds < 1:
        raise ValueError("delta_max_seconds must be a positive integer")
    if not isinstance(previous_state, Mapping):
        raise ValueError("delta previous state identity is invalid")
    state_report = previous_state.get("report")
    if (
        not isinstance(state_report, Mapping)
        or state_report.get("id") != previous_report_id
        or state_report.get("revision") != previous_revision
    ):
        raise ValueError("delta previous state identity is invalid")
    if not isinstance(previous_graph_receipt, Mapping):
        raise ValueError("delta previous graph identity is invalid")
    if previous_graph_receipt:
        expected_root = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
        if previous_graph_receipt.get("repo_root_sha256") != expected_root:
            raise ValueError("delta previous graph identity is invalid")
    if not isinstance(previous_graph_receipt_id, str) or not isinstance(previous_graph_sha256, str):
        raise ValueError("delta exact prior graph binding is required")
        if not isinstance(previous_graph_receipt.get("nodes"), (list, tuple)) or not isinstance(
            previous_graph_receipt.get("paths"), (list, tuple)
        ):
            raise ValueError("delta previous graph identity is invalid")
    markdown_sha256 = _trusted_value(trusted_previous, "markdown_sha256")
    display_text = _trusted_value(trusted_previous, "display_text")
    changed_count = _trusted_value(trusted_previous, "changed_count")
    if not isinstance(markdown_sha256, str) or SHA256_PATTERN.fullmatch(markdown_sha256) is None:
        raise ValueError("delta trusted previous Markdown identity is invalid")
    if not isinstance(display_text, str) or not display_text.strip():
        raise ValueError("delta trusted previous display is unavailable")
    if changed_count is not None and type(changed_count) is not int:
        raise ValueError("delta trusted previous changed count is invalid")
    return DeltaScanContext(
        root,
        previous_report_id,
        previous_revision,
        markdown_sha256,
        hashlib.sha256(_canonical_state_bytes(previous_state)).hexdigest(),
        display_text,
        hint_paths,
        changed_count,
        previous_state,
        previous_graph_receipt,
        previous_graph_receipt_id,
        previous_graph_sha256,
        min(configured_max_seconds, MAX_DELTA_SECONDS),
    )


def _evidence_paths(text: object) -> tuple[str, ...]:
    if not isinstance(text, str):
        return ()
    matches: list[tuple[int, str]] = []
    for pattern in (_PATH, _BARE_SOURCE):
        for match in pattern.finditer(text):
            value = match.group(0).rstrip(".,:;)")
            if _safe_relative(value):
                matches.append((match.start(), value))
    values: list[str] = []
    for _offset, value in sorted(matches):
        if value not in values:
            values.append(value)
    return tuple(values)


def derive_delta_seed_selection(
    previous: DeltaScanContext,
    changed_paths: Sequence[str] | None = None,
    *,
    request_seeds: Sequence[object] = (),
) -> DeltaSeedSelection:
    """Select the first 512 unique trusted seeds and account for every omission."""
    if not isinstance(previous, DeltaScanContext):
        raise TypeError("previous must be a trusted DeltaScanContext")
    selected_changed_paths = (
        previous.changed_paths if changed_paths is None else tuple(changed_paths)
    )
    if selected_changed_paths != previous.changed_paths:
        raise ValueError("delta changed paths do not match trusted previous lookup")
    ordered: list[DeltaSeed] = []
    seen: dict[tuple[str, str | None], int] = {}
    omitted_by_source: dict[str, int] = {}

    def add(
        term: object,
        location: object,
        derivation: str,
        provenance: Mapping[str, object],
    ) -> None:
        safe_location: str | None = (
            location if isinstance(location, str) and _safe_relative(location) else None
        )
        safe_term = term if isinstance(term, str) and term.strip() else safe_location
        if not isinstance(safe_term, str) or not safe_term.strip():
            return
        identity: tuple[str, str | None] = (
            ("location", safe_location) if safe_location is not None else ("term", safe_term)
        )
        if identity in seen:
            index = seen[identity]
            if index < 0:
                return
            existing = ordered[index]
            thawed_existing = _thaw(existing.provenance)
            if not isinstance(thawed_existing, dict):  # pragma: no cover - frozen mapping invariant
                raise TypeError("delta seed provenance is invalid")
            merged = dict(thawed_existing)
            additional_value = merged.get("additional", [])
            additional = list(additional_value) if isinstance(additional_value, list) else []
            thawed_candidate = _thaw(provenance)
            if not isinstance(thawed_candidate, dict):  # pragma: no cover - mapping invariant
                raise TypeError("delta seed provenance is invalid")
            candidate = dict(thawed_candidate)
            serialized = {
                json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                for item in additional
            }
            candidate_key = json.dumps(
                candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            primary_key = json.dumps(
                {key: item for key, item in merged.items() if key != "additional"},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if candidate_key != primary_key and candidate_key not in serialized:
                additional.append(candidate)
                merged["additional"] = additional
                ordered[index] = DeltaSeed(
                    existing.term,
                    existing.location,
                    existing.derivation,
                    existing.source_sha256,
                    merged,
                )
            return
        if len(ordered) >= MAX_DELTA_SEEDS:
            seen[identity] = -1
            source = str(provenance.get("source") or derivation.split(":", 1)[0])
            omitted_by_source[source] = omitted_by_source.get(source, 0) + 1
            return
        seen[identity] = len(ordered)
        ordered.append(
            DeltaSeed(
                safe_term[:4096],
                safe_location,
                derivation[:128],
                None
                if safe_location is None
                else _source_sha256(previous.repo_root, safe_location),
                provenance,
            )
        )

    for location in selected_changed_paths:
        add(location, location, "trusted-changed-path", {"source": "previous-lookup"})

    graph = previous.previous_graph_receipt
    node_rows = graph.get("nodes", ())
    path_rows = graph.get("paths", ())
    nodes: dict[str, Mapping[str, object]] = {}
    if isinstance(node_rows, (tuple, list)):
        for row in node_rows:
            if isinstance(row, Mapping) and isinstance(row.get("id"), str):
                nodes[str(row["id"])] = row
    if isinstance(path_rows, (tuple, list)):
        for path in path_rows:
            if not isinstance(path, Mapping) or not isinstance(path.get("nodes"), (tuple, list)):
                continue
            path_id = path.get("id")
            for node_id in path["nodes"]:
                node = nodes.get(node_id)
                if not isinstance(node, Mapping):
                    continue
                node_location = node.get("location")
                term = node.get("label") or node_location
                add(
                    term,
                    node_location,
                    f"previous-graph-path:{path_id}:{node_id}",
                    {"source": "previous-graph-path", "path_id": path_id, "node_id": node_id},
                )

    state = previous.previous_state
    for field, derivation, identifier in (
        ("preserved_invariants", "preserved-invariant-evidence", "invariant_id"),
        ("criteria", "criterion-evidence", "criterion_id"),
    ):
        rows = state.get(field, ())
        if not isinstance(rows, (tuple, list)):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            row_id = row.get("id")
            for evidence_location in _evidence_paths(row.get("evidence")):
                add(
                    row_id or evidence_location,
                    evidence_location,
                    f"{derivation}:{row_id}",
                    {"source": derivation, identifier: row_id},
                )

    for seed in request_seeds:
        term = getattr(seed, "term", None)
        request_location = getattr(seed, "location", None)
        derivation = getattr(seed, "derivation", "request-term")
        add(
            term,
            request_location,
            str(derivation),
            {"source": "request", "derivation": str(derivation)},
        )
    return DeltaSeedSelection(
        tuple(ordered),
        sum(omitted_by_source.values()),
        omitted_by_source,
    )


def derive_delta_seeds(
    previous: DeltaScanContext,
    changed_paths: Sequence[str] | None = None,
    *,
    request_seeds: Sequence[object] = (),
) -> tuple[DeltaSeed, ...]:
    return derive_delta_seed_selection(
        previous,
        changed_paths,
        request_seeds=request_seeds,
    ).seeds


def _expired(deadline: object | None) -> bool:
    if deadline is None:
        return False
    method = getattr(deadline, "expired", None)
    if not callable(method):
        raise TypeError("delta source deadline must provide expired()")
    return bool(method())


def _excluded_directory(relative: str, name: str) -> bool:
    return name in DEFAULT_EXCLUDED_DIRECTORIES or relative == "evals/results"


def _walk_default_sources(root: Path, deadline: object | None):
    pending = [root]
    while pending:
        if _expired(deadline):
            return
        directory = pending.pop(0)
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            yield None, "traversal"
            continue
        children = []
        for entry in entries:
            relative = Path(entry.path).relative_to(root).as_posix()
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if not _excluded_directory(relative, entry.name):
                        children.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    yield relative, None
            except OSError:
                yield None, "traversal"
        pending[0:0] = children


def collect_sources(
    repo_root: Path | str,
    explicit_seeds: Sequence[object],
    *,
    deadline: object | None = None,
) -> DeltaSourceInventory:
    """Collect default text sources before budgeting, then exact explicit overrides."""
    root = _root(repo_root)
    explicit: list[str] = []
    for seed in explicit_seeds:
        location = seed if isinstance(seed, str) else getattr(seed, "location", None)
        if location is not None and not _safe_relative(location):
            raise ValueError("explicit delta source path is unsafe")
        if isinstance(location, str) and location not in explicit:
            explicit.append(location)
    digests: dict[str, str] = {}
    file_count = 0
    byte_count = 0
    reason: str | None = None
    seen: set[str] = set()
    for relative, traversal_reason in _walk_default_sources(root, deadline):
        if traversal_reason is not None:
            reason = reason or traversal_reason
            continue
        if relative is None:  # pragma: no cover - traversal rows carry a reason
            reason = reason or "traversal"
            continue
        seen.add(relative)
        if _expired(deadline):
            reason = "deadline"
            break
        if file_count >= MAX_SOURCE_FILES:
            reason = "collection-limit"
            break
        payload, read_reason = _read_source(root, relative)
        if payload is None:
            if read_reason not in {"binary", "encoding", "not-regular"}:
                reason = reason or "unreadable-source"
            continue
        if byte_count + len(payload) > MAX_SOURCE_BYTES:
            reason = "collection-limit"
            break
        file_count += 1
        byte_count += len(payload)
        digests[relative] = hashlib.sha256(payload).hexdigest()
    for relative in explicit:
        if relative in digests:
            continue
        if _expired(deadline):
            reason = "deadline"
            break
        payload, read_reason = _read_source(root, relative)
        if payload is None:
            if read_reason not in {"binary", "encoding", "not-regular"}:
                reason = reason or "unreadable-source"
            continue
        if relative not in seen and (
            file_count >= MAX_SOURCE_FILES or byte_count + len(payload) > MAX_SOURCE_BYTES
        ):
            reason = "collection-limit"
            break
        if relative not in seen:
            file_count += 1
            byte_count += len(payload)
        digests[relative] = hashlib.sha256(payload).hexdigest()
    if _expired(deadline):
        reason = "deadline"
    return DeltaSourceInventory(digests, reason is None, reason)


def _seed_selection(
    value: DeltaSeedSelection | Sequence[DeltaSeed],
) -> DeltaSeedSelection:
    if isinstance(value, DeltaSeedSelection):
        return value
    return DeltaSeedSelection(tuple(value), 0, {})


def context_mapping(
    context: DeltaScanContext,
    selection: DeltaSeedSelection | Sequence[DeltaSeed],
) -> dict[str, object]:
    if not isinstance(context, DeltaScanContext):
        raise TypeError("delta context must be trusted")
    selected = _seed_selection(selection)
    return {
        "previous_report_id": context.previous_report_id,
        "previous_revision": context.previous_revision,
        "previous_markdown_sha256": context.previous_markdown_sha256,
        "previous_state_sha256": context.previous_state_sha256,
        "previous_graph_receipt_id": context.previous_graph_receipt_id,
        "previous_graph_sha256": context.previous_graph_sha256,
        "previous_display_text": context.previous_display_text,
        "changed_paths": list(context.changed_paths),
        "changed_count": context.changed_count,
        "max_seconds": context.max_seconds,
        "seed_provenance": [seed.provenance_mapping() for seed in selected.seeds],
        "omitted_seed_count": selected.omitted_count,
        "omitted_seed_provenance": dict(selected.omitted_by_source),
        "previous_frontier": [_thaw(row) for row in context.previous_frontier],
    }


def _mapping_rows(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(row for row in value if isinstance(row, Mapping))


def _rows_by_id(value: object) -> dict[str, Mapping[str, object]]:
    return {str(row["id"]): row for row in _mapping_rows(value) if isinstance(row.get("id"), str)}


def _ordered_prior_path_nodes(
    path: Mapping[str, object],
    nodes: Mapping[str, Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    node_ids = path.get("nodes")
    if not isinstance(node_ids, (tuple, list)):
        return ()
    result = []
    for node_id in node_ids:
        node = nodes.get(str(node_id))
        if node is None:
            return ()
        result.append(node)
    return tuple(result)


def _current_path_chain(
    path: Mapping[str, object],
    nodes: Mapping[str, Mapping[str, object]],
    edges: Mapping[str, Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    node_ids = path.get("nodes")
    edge_ids = path.get("edges")
    if (
        not isinstance(node_ids, (tuple, list))
        or not isinstance(edge_ids, (tuple, list))
        or len(node_ids) < 2
        or len(edge_ids) != len(node_ids) - 1
    ):
        return ()
    chain = []
    for index, node_id in enumerate(node_ids):
        node = nodes.get(str(node_id))
        if node is None:
            return ()
        chain.append(node)
        if index >= len(edge_ids):
            continue
        edge = edges.get(str(edge_ids[index]))
        if (
            edge is None
            or edge.get("source") != node_id
            or edge.get("target") != node_ids[index + 1]
        ):
            return ()
    return tuple(chain)


def _current_matches_prior_identity(
    prior: Mapping[str, object], current: Mapping[str, object]
) -> bool:
    location = prior.get("location")
    prior_label = prior.get("label")
    return current.get("location") == location or (
        current.get("confidence") in {"verified-provider", "verified-source"}
        and isinstance(prior_label, str)
        and bool(prior_label)
        and current.get("label") == prior_label
    )


def _matching_current_nodes(
    prior_nodes: Sequence[Mapping[str, object]],
    current_chain: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    matched = []
    cursor = 0
    for prior in prior_nodes:
        location = prior.get("location")
        if not isinstance(location, str):
            return ()
        while cursor < len(current_chain) and not _current_matches_prior_identity(
            prior, current_chain[cursor]
        ):
            cursor += 1
        if cursor >= len(current_chain):
            return ()
        matched.append(current_chain[cursor])
        cursor += 1
    return tuple(matched)


def _current_node_verifies_prior(
    context: DeltaScanContext,
    prior: Mapping[str, object],
    current: Mapping[str, object],
) -> bool:
    location = prior.get("location")
    current_location = current.get("location")
    prior_sha256 = prior.get("source_sha256")
    current_sha256 = current.get("source_sha256")
    if (
        not isinstance(location, str)
        or not isinstance(prior_sha256, str)
        or SHA256_PATTERN.fullmatch(prior_sha256) is None
        or not isinstance(current_sha256, str)
        or SHA256_PATTERN.fullmatch(current_sha256) is None
        or not isinstance(current_location, str)
        or _source_sha256(context.repo_root, current_location) != current_sha256
    ):
        return False
    if current_location != location:
        return (
            current.get("confidence") in {"verified-provider", "verified-source"}
            and isinstance(prior.get("label"), str)
            and current.get("label") == prior.get("label")
        )
    if current_sha256 == prior_sha256 or location in context.changed_paths:
        return True
    return current.get("confidence") in {"verified-provider", "verified-source"}


def _verified_current_locations(
    context: DeltaScanContext,
    nodes: Mapping[str, Mapping[str, object]],
) -> set[str]:
    verified = set()
    for node in nodes.values():
        location = node.get("location")
        source_sha256 = node.get("source_sha256")
        if (
            isinstance(location, str)
            and isinstance(source_sha256, str)
            and SHA256_PATTERN.fullmatch(source_sha256) is not None
            and _source_sha256(context.repo_root, location) == source_sha256
        ):
            verified.add(location)
    return verified


def surviving_frontier(
    context: DeltaScanContext,
    graph: Mapping[str, object],
    selection: DeltaSeedSelection | None = None,
) -> tuple[Mapping[str, object], ...]:
    """Keep unknowns until receipt-local paths and current source bytes revalidate them."""
    rows: list[Mapping[str, object]] = []
    identities: set[str] = set()

    def add(row: Mapping[str, object]) -> None:
        key = json.dumps(_thaw(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if key not in identities:
            identities.add(key)
            thawed = _thaw(row)
            if not isinstance(thawed, dict):  # pragma: no cover - mapping invariant
                raise TypeError("delta frontier row is invalid")
            rows.append(MappingProxyType(dict(thawed)))

    for row in context.previous_frontier:
        add(row)
    graph_frontier = graph.get("frontier", ())
    if isinstance(graph_frontier, (tuple, list)):
        for row in graph_frontier:
            if isinstance(row, Mapping):
                add(row)
    prior_nodes = _rows_by_id(context.previous_graph_receipt.get("nodes"))
    prior_paths = _mapping_rows(context.previous_graph_receipt.get("paths"))
    current_nodes = _rows_by_id(graph.get("nodes"))
    current_edges = _rows_by_id(graph.get("edges"))
    current_paths = _mapping_rows(graph.get("paths"))
    verified_prior_locations: set[str] = set()

    for prior_path in prior_paths:
        path_id = str(prior_path.get("id") or "previous-path")
        ordered_prior = _ordered_prior_path_nodes(prior_path, prior_nodes)
        survived = False
        if ordered_prior:
            for current_path in current_paths:
                chain = _current_path_chain(current_path, current_nodes, current_edges)
                matched = _matching_current_nodes(ordered_prior, chain)
                if (
                    matched
                    and len(matched) == len(ordered_prior)
                    and all(
                        _current_node_verifies_prior(context, prior, current)
                        for prior, current in zip(ordered_prior, matched)
                    )
                ):
                    verified_prior_locations.update(
                        str(node["location"])
                        for node in ordered_prior
                        if isinstance(node.get("location"), str)
                    )
                    survived = True
                    break
        if survived:
            continue
        prior_path_node_ids = prior_path.get("nodes")
        frontier_node = (
            str(prior_path_node_ids[0])
            if isinstance(prior_path_node_ids, (tuple, list)) and prior_path_node_ids
            else "previous-node"
        )
        path_risks = prior_path.get("risk_domains")
        path_risk_domains = (
            [str(value) for value in path_risks]
            if isinstance(path_risks, (tuple, list))
            else ["regression"]
        )
        add(
            {
                "id": f"DELTA-FRONTIER-{len(rows) + 1:03d}",
                "node": frontier_node,
                "reason": f"previous selected path remains unverified: {path_id}",
                "risk_domains": path_risk_domains,
                "path_id": path_id,
                "provenance": "previous-graph-path",
            }
        )
        for prior_node in ordered_prior:
            location = prior_node.get("location")
            label = str(location or prior_node.get("id") or "previous-node")
            node_risks = prior_node.get("risk_domains")
            node_risk_domains = (
                [str(value) for value in node_risks]
                if isinstance(node_risks, (tuple, list))
                else ["regression"]
            )
            add(
                {
                    "id": f"DELTA-FRONTIER-{len(rows) + 1:03d}",
                    "node": str(prior_node.get("id") or "previous-node"),
                    "reason": (
                        f"previous selected path node remains unverified: {path_id}:{label}"
                    ),
                    "risk_domains": node_risk_domains,
                    "location": location,
                    "path_id": path_id,
                    "provenance": "previous-graph-path",
                }
            )

    selected = selection or derive_delta_seed_selection(context)
    current_locations = _verified_current_locations(context, current_nodes)
    trusted_seeds: list[tuple[DeltaSeed, Mapping[str, object]]] = []
    for seed in selected.seeds:
        primary = {key: item for key, item in seed.provenance.items() if key != "additional"}
        additional = seed.provenance.get("additional", ())
        origins: list[Mapping[str, object]] = [primary]
        if isinstance(additional, (tuple, list)):
            origins.extend(row for row in additional if isinstance(row, Mapping))
        origin: Mapping[str, object] | None = next(
            (row for row in origins if row.get("source") == "previous-graph-path"),
            origins[0] if origins else None,
        )
        if origin is not None and seed.location is not None:
            trusted_seeds.append((seed, origin))
    for seed, origin in trusted_seeds:
        source = str(origin.get("source") or "previous-evidence")
        if source == "previous-graph-path" and seed.location in verified_prior_locations:
            continue
        if source != "previous-graph-path" and seed.location in current_locations:
            continue
        if source == "previous-graph-path":
            reason = f"previous selected impact remains unverified: {seed.location}"
        elif source == "previous-lookup":
            reason = f"changed path remains unverified: {seed.location}"
        else:
            reason = f"previous evidence remains unverified: {seed.location}"
        add(
            {
                "id": f"DELTA-FRONTIER-{len(rows) + 1:03d}",
                "node": str(origin.get("node_id") or "previous-node"),
                "reason": reason,
                "risk_domains": ["regression"],
                "location": seed.location,
                "provenance": source,
            }
        )
    if selected.omitted_count:
        add(
            {
                "id": f"DELTA-FRONTIER-{len(rows) + 1:03d}",
                "node": "previous-seed-selection",
                "reason": f"{selected.omitted_count} trusted delta seeds omitted by capacity",
                "risk_domains": ["regression"],
                "omitted_seed_count": selected.omitted_count,
                "omitted_seed_provenance": dict(selected.omitted_by_source),
                "provenance": "delta-seed-capacity",
            }
        )
    return tuple(rows)


def delta_timeout_fallback(
    context: DeltaScanContext,
    elapsed_ms: int,
    reason: str = "delta revalidation deadline exhausted",
) -> dict[str, object]:
    """Build a bounded immutable fallback without reading current source bytes."""
    if not isinstance(context, DeltaScanContext):
        raise TypeError("delta timeout fallback requires a trusted context")
    if type(elapsed_ms) is not int or elapsed_ms < 0:
        raise ValueError("delta timeout elapsed time is invalid")
    frontier: list[dict[str, object]] = []
    identities = set()

    def add(row: Mapping[str, object]) -> None:
        if len(frontier) >= 1024:
            return
        thawed = _thaw(row)
        if not isinstance(thawed, dict):
            return
        identity = json.dumps(thawed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if identity not in identities:
            identities.add(identity)
            frontier.append(thawed)

    for row in context.previous_frontier:
        add(row)
    prior_nodes = _rows_by_id(context.previous_graph_receipt.get("nodes"))
    for path in _mapping_rows(context.previous_graph_receipt.get("paths")):
        path_id = str(path.get("id") or "previous-path")
        ordered = _ordered_prior_path_nodes(path, prior_nodes)
        add(
            {
                "id": f"DELTA-FRONTIER-{len(frontier) + 1:03d}",
                "node": str(ordered[0].get("id") if ordered else "previous-node"),
                "reason": f"previous selected path remains unverified: {path_id}",
                "risk_domains": ["regression"],
                "path_id": path_id,
                "provenance": "previous-graph-path",
            }
        )
        for node in ordered:
            location = node.get("location")
            add(
                {
                    "id": f"DELTA-FRONTIER-{len(frontier) + 1:03d}",
                    "node": str(node.get("id") or "previous-node"),
                    "reason": (
                        "previous selected path node remains unverified: "
                        f"{path_id}:{location or node.get('id')}"
                    ),
                    "risk_domains": ["regression"],
                    "location": location,
                    "path_id": path_id,
                    "provenance": "previous-graph-path",
                }
            )
    add(
        {
            "id": f"DELTA-FRONTIER-{len(frontier) + 1:03d}",
            "node": "delta-worker",
            "reason": reason,
            "risk_domains": ["regression"],
            "provenance": "delta-worker-deadline",
        }
    )
    identity = _canonical_graph_bytes(
        {
            "report_id": context.previous_report_id,
            "revision": context.previous_revision,
            "graph_receipt_id": context.previous_graph_receipt_id,
            "graph_sha256": context.previous_graph_sha256,
            "changed_paths": list(context.changed_paths),
        }
    )
    scan_id = hashlib.sha256(identity).hexdigest()[:32]
    receipt_id = hashlib.sha256(identity + b":fallback").hexdigest()[:32]
    receipt_sha256 = hashlib.sha256(identity + b":partial").hexdigest()
    display = context.previous_display_text.rstrip() + "\n\n" + reason
    return {
        "status": "partial",
        "scan_id": scan_id,
        "receipt_id": receipt_id,
        "receipt_sha256": receipt_sha256,
        "display_text": display,
        "risk_level": "unknown",
        "paths": [],
        "frontier": frontier,
        "candidates": [],
        "elapsed_ms": elapsed_ms,
        "cache_status": "bypassed",
        "can_promote": False,
        "previous_report_id": context.previous_report_id,
        "previous_revision": context.previous_revision,
        "changed_paths": list(context.changed_paths),
        "changed_count": context.changed_count,
        "previous_display_text": context.previous_display_text,
    }


__all__ = [
    "DEFAULT_EXCLUDED_DIRECTORIES",
    "MAX_DELTA_SECONDS",
    "DeltaScanContext",
    "DeltaSeed",
    "DeltaSeedSelection",
    "DeltaSourceInventory",
    "bind_delta_context",
    "collect_sources",
    "context_mapping",
    "delta_timeout_fallback",
    "derive_delta_seed_selection",
    "derive_delta_seeds",
    "load_trusted_previous_artifacts",
    "surviving_frontier",
    "validate_delta_hints",
]
