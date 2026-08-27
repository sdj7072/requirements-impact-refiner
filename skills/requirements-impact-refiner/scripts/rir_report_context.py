#!/usr/bin/env python3
"""Immutable, private identity sidecars for published impact reports."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import selectors
import signal
import stat
import subprocess
import tempfile
import time
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import MappingProxyType

REPORT_ID_PATTERN = re.compile(r"RPT-\d{3}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z")
MAX_REQUIREMENT_INPUT_BYTES = 256 * 1024
MAX_REQUIREMENT_BYTES = 64 * 1024
MAX_EVIDENCE_BYTES = 256 * 1024
MAX_EVIDENCE_ROW_BYTES = 64 * 1024
MAX_CONTEXT_BYTES = 80 * 1024
MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_MARKDOWN_BYTES = 4 * 1024 * 1024
MAX_GIT_OUTPUT_BYTES = 256 * 1024
MAX_GIT_TREE_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_GIT_BLOB_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_REQUIRED_SOURCE_DIGESTS = 64
MAX_REQUIRED_SOURCE_PATH_BYTES = 1024
MAX_REQUIRED_SOURCE_MAP_BYTES = 64 * 1024
MAX_REQUIRED_SOURCE_QUERY_BYTES = 64 * 1024
MAX_SOURCE_RECHECK_BYTES = 4 * 1024 * 1024
GIT_SOURCE_PROOF_TIMEOUT_SECONDS = 5.0
GIT_TIMEOUT_SECONDS = 0.25
_DELTA_WORKER_SHARED_GROUP = False


def _configure_delta_worker(enabled=True):
    global _DELTA_WORKER_SHARED_GROUP
    if not isinstance(enabled, bool):
        raise TypeError("delta worker group flag must be boolean")
    _DELTA_WORKER_SHARED_GROUP = enabled


MAX_CONTEXT_STAGE_CANDIDATES = 8
_TRANSFORM_CONFIG_PATTERN = r"^(core\.autocrlf|core\.eol|core\.attributesfile)"
_PRE_SOURCE_RECHECK_CONTEXT_FIELDS = frozenset(
    {
        "schema_version",
        "report_id",
        "revision",
        "markdown_sha256",
        "state_sha256",
        "repo_root_sha256",
        "requirement_sha256",
        "repository_evidence_sha256",
        "source_inventory_sha256",
        "source_inventory_available",
        "source_inventory_complete",
        "source_inventory_git_tracked_only",
        "payload_sha256",
        "created_at",
        "baseline_commit",
        "baseline_clean",
    }
)
_CONTEXT_FIELDS = _PRE_SOURCE_RECHECK_CONTEXT_FIELDS | {
    "required_source_digests",
    "source_recheck_complete",
}


def _canonical_required_source_path(value: str) -> str:
    if type(value) is not str or not value or "\\" in value:
        raise ValueError("required source digest path is unsafe")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("required source digest path is not UTF-8") from error
    if len(encoded) > MAX_REQUIRED_SOURCE_PATH_BYTES:
        raise ValueError("required source digest path exceeds its path byte limit")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("required source digest path is unsafe")
    return value


def canonical_required_source_digests(value: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError("required source digests must be a mapping")
    if len(value) > MAX_REQUIRED_SOURCE_DIGESTS:
        raise ValueError("required source digest map exceeds its count limit")
    normalized: dict[str, str] = {}
    for path, digest in value.items():
        relative = _canonical_required_source_path(path)
        if type(digest) is not str or SHA256_PATTERN.fullmatch(digest) is None:
            raise ValueError("required source digest map contains an invalid SHA-256 digest")
        normalized[relative] = digest
    normalized = dict(sorted(normalized.items()))
    payload = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if len(payload) > MAX_REQUIRED_SOURCE_MAP_BYTES:
        raise ValueError("required source digest map exceeds its serialized byte limit")
    return normalized


@dataclass(frozen=True)
class ReportContext:
    schema_version: int
    report_id: str
    revision: int
    markdown_sha256: str
    state_sha256: str
    repo_root_sha256: str
    requirement_sha256: str
    repository_evidence_sha256: str
    source_inventory_sha256: str | None
    payload_sha256: str
    created_at: str
    baseline_commit: str | None
    baseline_clean: bool
    source_inventory_available: bool = True
    source_inventory_complete: bool = True
    source_inventory_git_tracked_only: bool = False
    required_source_digests: Mapping[str, str] | None = None
    source_recheck_complete: bool = False

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 2:
            raise ValueError("report context schema_version must be 2")
        if type(self.report_id) is not str or REPORT_ID_PATTERN.fullmatch(self.report_id) is None:
            raise ValueError("report context report_id is invalid")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("report context revision is invalid")
        for label, value in (
            ("markdown_sha256", self.markdown_sha256),
            ("state_sha256", self.state_sha256),
            ("repo_root_sha256", self.repo_root_sha256),
            ("requirement_sha256", self.requirement_sha256),
            ("repository_evidence_sha256", self.repository_evidence_sha256),
            ("payload_sha256", self.payload_sha256),
        ):
            if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
                raise ValueError(f"report context {label} is invalid")
        if type(self.source_inventory_available) is not bool:
            raise TypeError("report context source_inventory_available must be boolean")
        if type(self.source_inventory_complete) is not bool:
            raise TypeError("report context source_inventory_complete must be boolean")
        if type(self.source_inventory_git_tracked_only) is not bool:
            raise TypeError("report context source_inventory_git_tracked_only must be boolean")
        if type(self.source_recheck_complete) is not bool:
            raise TypeError("report context source_recheck_complete must be boolean")
        if self.required_source_digests is None:
            if self.source_recheck_complete:
                raise ValueError("complete source recheck requires a required source digest map")
        else:
            normalized = canonical_required_source_digests(self.required_source_digests)
            object.__setattr__(self, "required_source_digests", MappingProxyType(normalized))
        if self.source_inventory_available:
            if (
                type(self.source_inventory_sha256) is not str
                or SHA256_PATTERN.fullmatch(self.source_inventory_sha256) is None
            ):
                raise ValueError("available source inventory requires a SHA-256 digest")
        elif self.source_inventory_sha256 is not None:
            raise ValueError("unavailable source inventory cannot have a digest")
        if self.source_inventory_complete and not self.source_inventory_available:
            raise ValueError("complete source inventory must be available")
        if self.source_inventory_git_tracked_only and (
            not self.source_inventory_available or not self.source_inventory_complete
        ):
            raise ValueError("tracked-only source inventory must be available and complete")
        if self.source_recheck_complete and (
            not self.source_inventory_available or not self.source_inventory_complete
        ):
            raise ValueError("complete source recheck requires a complete source inventory")
        if (
            type(self.created_at) is not str
            or len(self.created_at.encode("utf-8")) > 64
            or TIMESTAMP_PATTERN.fullmatch(self.created_at) is None
        ):
            raise ValueError("report context created_at must be bounded RFC 3339 UTC text")
        if self.baseline_commit is not None and (
            type(self.baseline_commit) is not str
            or COMMIT_PATTERN.fullmatch(self.baseline_commit) is None
        ):
            raise ValueError("report context baseline_commit is invalid")
        if type(self.baseline_clean) is not bool:
            raise TypeError("report context baseline_clean must be boolean")
        if self.baseline_clean and self.baseline_commit is None:
            raise ValueError("clean Git baseline requires a commit")
        if self.source_inventory_git_tracked_only and not self.baseline_clean:
            raise ValueError("tracked-only source inventory requires a clean Git baseline")


class UnsafeGitOutput(ValueError):
    """Git emitted output that cannot safely participate in report identity."""


def canonical_requirement_text(request: str) -> str:
    if type(request) is not str:
        raise TypeError("requirement must be text")
    if len(request.encode("utf-8")) > MAX_REQUIREMENT_INPUT_BYTES:
        raise ValueError("requirement input exceeds 256 KiB")
    normalized = unicodedata.normalize("NFC", " ".join(request.split()))
    if not normalized:
        raise ValueError("requirement must be nonblank")
    if len(normalized.encode("utf-8")) > MAX_REQUIREMENT_BYTES:
        raise ValueError("normalized requirement exceeds 64 KiB")
    return normalized


def canonical_requirement_sha256(request: str) -> str:
    normalized = canonical_requirement_text(request)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def canonical_repository_evidence_sha256(evidence: Sequence[str]) -> str:
    if isinstance(evidence, (str, bytes)) or not isinstance(evidence, Sequence):
        raise TypeError("repository evidence must be a sequence of text rows")
    rows = list(evidence)
    if any(type(row) is not str or not row.strip() for row in rows):
        raise ValueError("repository evidence must contain nonblank text rows")
    if any(len(row.encode("utf-8")) > MAX_EVIDENCE_ROW_BYTES for row in rows):
        raise ValueError("repository evidence contains a row larger than 64 KiB")
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_EVIDENCE_BYTES:
        raise ValueError("repository evidence exceeds 256 KiB")
    return hashlib.sha256(payload).hexdigest()


def repo_root_sha256(root: Path) -> str:
    return hashlib.sha256(str(_root(root)).encode("utf-8")).hexdigest()


def created_at_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _root(value: Path) -> Path:
    path = Path(value)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError(f"repository root is unavailable: {error}") from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or not resolved.is_dir()
    ):
        raise ValueError("repository root must be a real directory")
    return resolved


def _validate_identity(report_id: str, revision: int) -> None:
    if type(report_id) is not str or REPORT_ID_PATTERN.fullmatch(report_id) is None:
        raise ValueError("invalid report ID")
    if type(revision) is not int or revision < 1:
        raise ValueError("invalid report revision")


def _directory_flags() -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    return flags | getattr(os, "O_NOFOLLOW", 0)


def _open_report_directory(root: Path, report_id: str, *, missing_ok: bool) -> int | None:
    descriptor: int | None = None
    try:
        descriptor = os.open(root, _directory_flags())
        for component in (".requirements-impact-refiner", "reports", report_id):
            try:
                child = os.open(component, _directory_flags(), dir_fd=descriptor)
            except FileNotFoundError:
                if missing_ok:
                    os.close(descriptor)
                    return None
                raise ValueError("published report directory is unavailable") from None
            except OSError as error:
                raise ValueError("published report directory is unsafe") from error
            os.close(descriptor)
            descriptor = child
        return descriptor
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        raise ValueError("repository root is unsafe") from error
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        raise


def _read_bounded_file(
    directory_fd: int,
    name: str,
    maximum: int,
    *,
    private: bool,
    allowed_links: frozenset[int] = frozenset({1}),
    expected_owner: int | None = None,
) -> bytes:
    payload, _metadata = _read_bounded_artifact(
        directory_fd,
        name,
        maximum,
        private=private,
        allowed_links=allowed_links,
        expected_owner=expected_owner,
    )
    return payload


def _read_bounded_artifact(
    directory_fd: int,
    name: str,
    maximum: int,
    *,
    private: bool,
    allowed_links: frozenset[int],
    expected_owner: int | None,
) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as error:
        raise ValueError(f"report artifact is unsafe: {name}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size < 0 or metadata.st_size > maximum:
            raise ValueError(f"report artifact is unsafe: {name}")
        if private:
            if (
                stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink not in allowed_links
                or (expected_owner is not None and metadata.st_uid != expected_owner)
            ):
                raise ValueError(f"report context is not private: {name}")
        payload = bytearray()
        while len(payload) <= maximum:
            chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) > maximum:
            raise ValueError(f"report artifact exceeds its byte limit: {name}")
        return bytes(payload), metadata
    finally:
        os.close(descriptor)


def _markdown_sha256(directory_fd: int, revision: int) -> str:
    payload = _read_bounded_file(
        directory_fd,
        f"revision-{revision:04d}.md",
        MAX_MARKDOWN_BYTES,
        private=False,
    )
    return hashlib.sha256(payload).hexdigest()


def _state_sha256(directory_fd: int, revision: int) -> str:
    payload = _read_bounded_file(
        directory_fd,
        f"revision-{revision:04d}.json",
        MAX_STATE_BYTES,
        private=False,
    )
    return hashlib.sha256(payload).hexdigest()


def _context_name(revision: int) -> str:
    return f"revision-{revision:04d}.context-v2.json"


def _mapping(context: ReportContext) -> dict[str, object]:
    return {
        "schema_version": context.schema_version,
        "report_id": context.report_id,
        "revision": context.revision,
        "markdown_sha256": context.markdown_sha256,
        "state_sha256": context.state_sha256,
        "repo_root_sha256": context.repo_root_sha256,
        "requirement_sha256": context.requirement_sha256,
        "repository_evidence_sha256": context.repository_evidence_sha256,
        "source_inventory_sha256": context.source_inventory_sha256,
        "source_inventory_available": context.source_inventory_available,
        "source_inventory_complete": context.source_inventory_complete,
        "source_inventory_git_tracked_only": context.source_inventory_git_tracked_only,
        "required_source_digests": (
            None
            if context.required_source_digests is None
            else dict(context.required_source_digests)
        ),
        "source_recheck_complete": context.source_recheck_complete,
        "payload_sha256": context.payload_sha256,
        "created_at": context.created_at,
        "baseline_commit": context.baseline_commit,
        "baseline_clean": context.baseline_clean,
    }


def _canonical_bytes(context: ReportContext) -> bytes:
    payload = (
        json.dumps(_mapping(context), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    if len(payload) > MAX_CONTEXT_BYTES:
        raise ValueError("report context exceeds its byte limit")
    return payload


def _from_payload(payload: bytes) -> ReportContext:
    if not payload or len(payload) > MAX_CONTEXT_BYTES:
        raise ValueError("report context payload is invalid")
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("report context payload is invalid") from error
    fields = frozenset(value) if isinstance(value, Mapping) else frozenset()
    if not isinstance(value, Mapping) or fields not in (
        _CONTEXT_FIELDS,
        _PRE_SOURCE_RECHECK_CONTEXT_FIELDS,
    ):
        raise ValueError("report context payload has an invalid schema")
    legacy_recheck_shape = fields == _PRE_SOURCE_RECHECK_CONTEXT_FIELDS
    if (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    ) != payload:
        raise ValueError("report context payload is not canonical")
    try:
        context = ReportContext(
            schema_version=value["schema_version"],
            report_id=value["report_id"],
            revision=value["revision"],
            markdown_sha256=value["markdown_sha256"],
            state_sha256=value["state_sha256"],
            repo_root_sha256=value["repo_root_sha256"],
            requirement_sha256=value["requirement_sha256"],
            repository_evidence_sha256=value["repository_evidence_sha256"],
            source_inventory_sha256=value["source_inventory_sha256"],
            payload_sha256=value["payload_sha256"],
            created_at=value["created_at"],
            baseline_commit=value["baseline_commit"],
            baseline_clean=value["baseline_clean"],
            source_inventory_available=value["source_inventory_available"],
            source_inventory_complete=value["source_inventory_complete"],
            source_inventory_git_tracked_only=value["source_inventory_git_tracked_only"],
            required_source_digests=(
                None if legacy_recheck_shape else value["required_source_digests"]
            ),
            source_recheck_complete=(
                False if legacy_recheck_shape else value["source_recheck_complete"]
            ),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("report context payload has invalid values") from error
    if not legacy_recheck_shape and _canonical_bytes(context) != payload:
        raise ValueError("report context payload is not canonical")
    return context


def _load_context_artifact(
    directory_fd: int,
    report_id: str,
    revision: int,
    *,
    name: str | None = None,
    allowed_links: frozenset[int] = frozenset({1}),
) -> tuple[ReportContext, bytes, os.stat_result]:
    selected_name = name or _context_name(revision)
    expected_owner = os.fstat(directory_fd).st_uid
    payload, metadata = _read_bounded_artifact(
        directory_fd,
        selected_name,
        MAX_CONTEXT_BYTES,
        private=True,
        allowed_links=allowed_links,
        expected_owner=expected_owner,
    )
    context = _from_payload(payload)
    if context.report_id != report_id or context.revision != revision:
        raise ValueError("report context identity does not match its filename")
    return context, payload, metadata


def _load_from_directory(directory_fd: int, report_id: str, revision: int) -> ReportContext:
    context, _payload, _metadata = _load_context_artifact(directory_fd, report_id, revision)
    return context


def _context_pending_name(name: str) -> str:
    return f".{name}.pending"


def _context_stage_prefix(name: str) -> str:
    return f".{name}.stage-"


def _fsync_context_directory(directory_fd: int) -> None:
    try:
        os.fsync(directory_fd)
    except OSError as error:
        raise ValueError("cannot fsync report context directory") from error


def _unlink_context_pending(directory_fd: int, pending: str) -> None:
    try:
        os.unlink(pending, dir_fd=directory_fd)
    except OSError as error:
        raise ValueError("cannot cleanup report context pending artifact") from error


def _open_context_stage(directory_fd: int, name: str) -> tuple[str, int, os.stat_result]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    prefix = _context_stage_prefix(name)
    for _candidate in range(MAX_CONTEXT_STAGE_CANDIDATES):
        stage = f"{prefix}{secrets.token_hex(8)}"
        try:
            descriptor = os.open(stage, flags, 0o600, dir_fd=directory_fd)
        except FileExistsError:
            continue
        except OSError as error:
            raise ValueError("cannot create report context stage") from error
        try:
            os.fchmod(descriptor, 0o600)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.fstat(directory_fd).st_uid
                or metadata.st_nlink != 1
                or metadata.st_size != 0
            ):
                raise ValueError("report context stage is unsafe")
            return stage, descriptor, metadata
        except BaseException:
            _cleanup_context_stage(directory_fd, stage, descriptor)
            os.close(descriptor)
            raise
    raise ValueError("report context stage candidate limit exhausted")


def _cleanup_context_stage(
    directory_fd: int,
    stage: str,
    descriptor: int,
) -> None:
    try:
        descriptor_metadata = os.fstat(descriptor)
        path_metadata = os.stat(stage, dir_fd=directory_fd, follow_symlinks=False)
    except (FileNotFoundError, OSError):
        return
    if (
        descriptor_metadata.st_dev != path_metadata.st_dev
        or descriptor_metadata.st_ino != path_metadata.st_ino
        or not stat.S_ISREG(path_metadata.st_mode)
        or stat.S_IMODE(path_metadata.st_mode) != 0o600
        or path_metadata.st_uid != os.fstat(directory_fd).st_uid
        or path_metadata.st_nlink != 1
    ):
        return
    try:
        os.unlink(stage, dir_fd=directory_fd)
    except OSError:
        return


def _verify_context_stage(
    directory_fd: int,
    stage: str,
    descriptor: int,
    initial_metadata: os.stat_result,
    context: ReportContext,
    payload: bytes,
) -> os.stat_result:
    metadata = os.fstat(descriptor)
    if (
        metadata.st_dev != initial_metadata.st_dev
        or metadata.st_ino != initial_metadata.st_ino
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.fstat(directory_fd).st_uid
        or metadata.st_nlink != 1
        or metadata.st_size != len(payload)
    ):
        raise ValueError("report context stage identity is invalid")
    staged_context, staged_payload, staged_metadata = _load_context_artifact(
        directory_fd,
        context.report_id,
        context.revision,
        name=stage,
    )
    if (
        staged_context != context
        or staged_payload != payload
        or staged_metadata.st_dev != metadata.st_dev
        or staged_metadata.st_ino != metadata.st_ino
    ):
        raise ValueError("report context stage verification failed")
    return metadata


def _replace_context_stage_with_pending(
    directory_fd: int,
    stage: str,
    pending: str,
    stage_metadata: os.stat_result,
    context: ReportContext,
    payload: bytes,
) -> None:
    os.replace(
        stage,
        pending,
        src_dir_fd=directory_fd,
        dst_dir_fd=directory_fd,
    )
    pending_context, pending_payload, pending_metadata = _load_context_artifact(
        directory_fd,
        context.report_id,
        context.revision,
        name=pending,
    )
    if (
        pending_context != context
        or pending_payload != payload
        or pending_metadata.st_dev != stage_metadata.st_dev
        or pending_metadata.st_ino != stage_metadata.st_ino
        or pending_metadata.st_nlink != 1
    ):
        raise ValueError("report context pending publication verification failed")
    _fsync_context_directory(directory_fd)


def _context_artifact_exists(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise ValueError("report context pending state is unsafe") from error
    return True


def _validate_context_state_identity(
    context: ReportContext,
    *,
    expected: ReportContext | None,
    repo_root_sha256: str,
    markdown_sha256: str,
    state_sha256: str,
) -> None:
    if (
        context.repo_root_sha256 != repo_root_sha256
        or context.markdown_sha256 != markdown_sha256
        or context.state_sha256 != state_sha256
    ):
        raise ValueError("report context pending identity is invalid")
    if expected is not None and context != expected:
        raise FileExistsError(_context_name(context.revision))


def _load_or_recover_context(
    directory_fd: int,
    report_id: str,
    revision: int,
    *,
    expected: ReportContext | None,
    repo_root_sha256: str,
    markdown_sha256: str,
    state_sha256: str,
) -> ReportContext | None:
    name = _context_name(revision)
    pending = _context_pending_name(name)
    target_exists = _context_artifact_exists(directory_fd, name)
    pending_exists = _context_artifact_exists(directory_fd, pending)
    if not target_exists and not pending_exists:
        return None
    target_value = target_payload = target_metadata = None
    pending_value = pending_payload = pending_metadata = None
    if target_exists:
        target_value, target_payload, target_metadata = _load_context_artifact(
            directory_fd,
            report_id,
            revision,
            allowed_links=frozenset({1, 2}),
        )
        _validate_context_state_identity(
            target_value,
            expected=expected,
            repo_root_sha256=repo_root_sha256,
            markdown_sha256=markdown_sha256,
            state_sha256=state_sha256,
        )
    if pending_exists:
        pending_value, pending_payload, pending_metadata = _load_context_artifact(
            directory_fd,
            report_id,
            revision,
            name=pending,
            allowed_links=frozenset({1, 2}),
        )
        _validate_context_state_identity(
            pending_value,
            expected=expected,
            repo_root_sha256=repo_root_sha256,
            markdown_sha256=markdown_sha256,
            state_sha256=state_sha256,
        )
    if not target_exists:
        if pending_metadata is None or pending_metadata.st_nlink != 1:
            raise ValueError("report context pending state is invalid")
        try:
            os.link(
                pending,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except OSError as error:
            raise ValueError("cannot publish report context pending artifact") from error
        target_value, target_payload, target_metadata = _load_context_artifact(
            directory_fd,
            report_id,
            revision,
            allowed_links=frozenset({2}),
        )
        linked_pending, linked_payload, linked_metadata = _load_context_artifact(
            directory_fd,
            report_id,
            revision,
            name=pending,
            allowed_links=frozenset({2}),
        )
        if (
            linked_metadata.st_dev != target_metadata.st_dev
            or linked_metadata.st_ino != target_metadata.st_ino
            or linked_payload != target_payload
            or linked_pending != target_value
        ):
            raise ValueError("report context pending state is invalid")
    elif pending_exists:
        if target_metadata is None or pending_metadata is None:
            raise ValueError("report context pending state is invalid")
        same_inode = (
            target_metadata.st_dev == pending_metadata.st_dev
            and target_metadata.st_ino == pending_metadata.st_ino
        )
        linked_state = (
            same_inode and target_metadata.st_nlink == 2 and pending_metadata.st_nlink == 2
        )
        leftover_state = (
            not same_inode
            and target_metadata.st_nlink == 1
            and pending_metadata.st_nlink == 1
            and target_value == pending_value
            and target_payload == pending_payload
        )
        if not linked_state and not leftover_state:
            raise ValueError("report context pending state is invalid")
    elif target_metadata is None or target_metadata.st_nlink != 1:
        raise ValueError("report context pending state is invalid")
    if not pending_exists:
        return target_value
    _unlink_context_pending(directory_fd, pending)
    _fsync_context_directory(directory_fd)
    recovered, recovered_payload, recovered_metadata = _load_context_artifact(
        directory_fd, report_id, revision
    )
    if (
        recovered != target_value
        or recovered_payload != target_payload
        or recovered_metadata.st_nlink != 1
    ):
        raise ValueError("report context recovery verification failed")
    return recovered


def publish_report_context(root: Path, context: ReportContext) -> Path:
    if not isinstance(context, ReportContext):
        raise TypeError("context must be ReportContext")
    resolved = _root(root)
    _validate_identity(context.report_id, context.revision)
    if context.repo_root_sha256 != hashlib.sha256(str(resolved).encode("utf-8")).hexdigest():
        raise ValueError("report context repository identity is invalid")
    directory_fd = _open_report_directory(resolved, context.report_id, missing_ok=False)
    if directory_fd is None:  # pragma: no cover - missing_ok=False is exhaustive
        raise ValueError("published report directory is unavailable")
    name = _context_name(context.revision)
    pending = _context_pending_name(name)
    stage: str | None = None
    stage_created = False
    stage_metadata: os.stat_result | None = None
    descriptor: int | None = None
    payload = _canonical_bytes(context)
    try:
        markdown_sha256 = _markdown_sha256(directory_fd, context.revision)
        state_sha256 = _state_sha256(directory_fd, context.revision)
        repo_sha256 = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()
        if markdown_sha256 != context.markdown_sha256:
            raise ValueError("report context Markdown digest is invalid")
        if state_sha256 != context.state_sha256:
            raise ValueError("report context state digest is invalid")
        existing = _load_or_recover_context(
            directory_fd,
            context.report_id,
            context.revision,
            expected=context,
            repo_root_sha256=repo_sha256,
            markdown_sha256=markdown_sha256,
            state_sha256=state_sha256,
        )
        if existing is not None:
            _fsync_context_directory(directory_fd)
            return resolved / ".requirements-impact-refiner" / "reports" / context.report_id / name
        stage, descriptor, initial_metadata = _open_context_stage(directory_fd, name)
        stage_created = True
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("report context stage write made no progress")
            offset += written
        os.fsync(descriptor)
        stage_metadata = _verify_context_stage(
            directory_fd,
            stage,
            descriptor,
            initial_metadata,
            context,
            payload,
        )
        _replace_context_stage_with_pending(
            directory_fd,
            stage,
            pending,
            stage_metadata,
            context,
            payload,
        )
        stage_created = False
        recovered = _load_or_recover_context(
            directory_fd,
            context.report_id,
            context.revision,
            expected=context,
            repo_root_sha256=repo_sha256,
            markdown_sha256=markdown_sha256,
            state_sha256=state_sha256,
        )
        if recovered != context:
            raise ValueError("published report context could not be verified")
    except FileExistsError:
        raise
    except (OSError, ValueError) as error:
        if descriptor is not None and stage is not None and stage_created:
            _cleanup_context_stage(directory_fd, stage, descriptor)
        if isinstance(error, ValueError):
            raise
        raise ValueError(f"cannot publish report context: {error}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_fd)
    return resolved / ".requirements-impact-refiner" / "reports" / context.report_id / name


def load_report_context(root: Path, report_id: str, revision: int) -> ReportContext | None:
    _validate_identity(report_id, revision)
    resolved = _root(root)
    directory_fd = _open_report_directory(resolved, report_id, missing_ok=True)
    if directory_fd is None:
        return None
    try:
        expected_root = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()
        markdown_sha256 = _markdown_sha256(directory_fd, revision)
        state_sha256 = _state_sha256(directory_fd, revision)
        return _load_or_recover_context(
            directory_fd,
            report_id,
            revision,
            expected=None,
            repo_root_sha256=expected_root,
            markdown_sha256=markdown_sha256,
            state_sha256=state_sha256,
        )
    finally:
        os.close(directory_fd)


def _git_environment() -> dict[str, str]:
    environment = {
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", ""),
    }
    system_root = os.environ.get("SYSTEMROOT")
    if system_root:
        environment["SYSTEMROOT"] = system_root
    return environment


def _git_configuration_environment() -> dict[str, str]:
    environment = _git_environment()
    environment.pop("GIT_CONFIG_GLOBAL", None)
    environment.pop("GIT_CONFIG_NOSYSTEM", None)
    for name in ("HOME", "XDG_CONFIG_HOME", "PROGRAMDATA"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    return environment


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    group_signaled = False
    if hasattr(os, "killpg"):
        try:
            os.killpg(process.pid, signal.SIGTERM)
            group_signaled = True
        except OSError:
            pass
    if not group_signaled and process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.wait(timeout=0.05)
    except (OSError, subprocess.TimeoutExpired):
        pass
    if hasattr(os, "killpg"):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
    elif process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=0.05)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _run_git(
    root: Path,
    arguments: Sequence[str],
    *,
    input_payload: bytes | None = None,
    maximum_output: int = MAX_GIT_OUTPUT_BYTES,
    environment: Mapping[str, str] | None = None,
) -> tuple[int, bytes] | None:
    command = (
        "git",
        "--no-pager",
        "--no-replace-objects",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "color.ui=false",
        "-c",
        "core.quotePath=true",
        *arguments,
    )
    input_stream = None
    try:
        if input_payload is not None:
            if len(input_payload) > MAX_REQUIRED_SOURCE_QUERY_BYTES:
                raise UnsafeGitOutput("Git input exceeds its byte limit")
            input_stream = tempfile.TemporaryFile()
            input_stream.write(input_payload)
            input_stream.seek(0)
        process = subprocess.Popen(
            command,
            cwd=str(root),
            env=dict(environment) if environment is not None else _git_environment(),
            stdin=subprocess.DEVNULL if input_stream is None else input_stream,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=not _DELTA_WORKER_SHARED_GROUP,
        )
    except OSError:
        if input_stream is not None:
            input_stream.close()
        return None
    if process.stdout is None:  # pragma: no cover - PIPE guarantees stdout
        _stop_process(process)
        if input_stream is not None:
            input_stream.close()
        return None
    try:
        descriptor = process.stdout.fileno()
        selector = selectors.DefaultSelector()
    except OSError:
        _stop_process(process)
        try:
            process.stdout.close()
        except OSError:
            pass
        if input_stream is not None:
            input_stream.close()
        return None
    payload = bytearray()
    deadline = time.monotonic() + GIT_TIMEOUT_SECONDS
    try:
        os.set_blocking(descriptor, False)
        selector.register(descriptor, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _stop_process(process)
                return None
            events = selector.select(remaining)
            if not events:
                _stop_process(process)
                return None
            try:
                chunk = os.read(
                    descriptor,
                    min(64 * 1024, maximum_output + 1 - len(payload)),
                )
            except BlockingIOError:
                continue
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > maximum_output:
                _stop_process(process)
                raise UnsafeGitOutput("Git baseline output exceeds its byte limit")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _stop_process(process)
            return None
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            _stop_process(process)
            return None
        if returncode != 0:
            _stop_process(process)
        return returncode, bytes(payload)
    except OSError:
        _stop_process(process)
        return None
    finally:
        try:
            selector.close()
        except OSError:
            pass
        try:
            process.stdout.close()
        except OSError:
            pass
        if input_stream is not None:
            input_stream.close()


def probe_git_baseline(root: Path) -> tuple[str | None, bool]:
    resolved = _root(root)
    commit_result = _run_git(resolved, ("rev-parse", "--verify", "HEAD^{commit}"))
    if commit_result is None or commit_result[0] != 0:
        return None, False
    commit_payload = commit_result[1]
    if b"\0" in commit_payload:
        raise UnsafeGitOutput("Git commit output contains NUL")
    try:
        commit = commit_payload.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise UnsafeGitOutput("Git commit output is not ASCII") from error
    if COMMIT_PATTERN.fullmatch(commit) is None:
        return None, False
    try:
        deadline = time.monotonic() + GIT_SOURCE_PROOF_TIMEOUT_SECONDS
        before = _capture_repository_git_state(resolved, commit, deadline)
        after = _capture_repository_git_state(resolved, commit, deadline)
        if before[1:] != after[1:]:
            return commit, False
        return commit, True
    except UnsafeGitOutput:
        raise
    except (OSError, TimeoutError, ValueError):
        return commit, False


def _tracked_paths_from_flags(payload: bytes) -> tuple[set[str], bool]:
    if not payload:
        return set(), True
    records = payload.split(b"\0")
    if records[-1] != b"":
        raise UnsafeGitOutput("Git tracked-path output is incomplete")
    paths: set[str] = set()
    flags_clean = True
    for record in records[:-1]:
        if len(record) < 3 or record[1:2] != b" ":
            raise UnsafeGitOutput("Git tracked-path output is malformed")
        try:
            path = record[2:].decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise UnsafeGitOutput("Git tracked path is not UTF-8") from error
        if not path or path.startswith("/") or ".." in Path(path).parts or "\x00" in path:
            raise UnsafeGitOutput("Git tracked path is unsafe")
        paths.add(Path(path).as_posix())
        if record[:1] != b"H":
            flags_clean = False
    return paths, flags_clean


def _index_paths_without_unsupported_entries(payload: bytes) -> set[str]:
    if payload and not payload.endswith(b"\0"):
        raise UnsafeGitOutput("Git index output is incomplete")
    paths: set[str] = set()
    for record in payload.split(b"\0")[:-1]:
        header, separator, path_payload = record.partition(b"\t")
        fields = header.split(b" ")
        if not separator or len(fields) != 3:
            raise UnsafeGitOutput("Git index output is malformed")
        try:
            mode, object_id, stage = (field.decode("ascii", errors="strict") for field in fields)
            path = _required_path(path_payload.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, ValueError) as error:
            raise UnsafeGitOutput("Git index output is unsafe") from error
        if mode == "160000":
            raise ValueError("Git gitlinks are outside the freshness proof scope")
        if path == ".gitattributes" or path.endswith("/.gitattributes"):
            raise ValueError("tracked Git attributes are outside the freshness proof scope")
        if not re.fullmatch(r"[0-7]{6}", mode) or not object_id or not stage.isdigit():
            raise UnsafeGitOutput("Git index output is malformed")
        if path in paths:
            raise UnsafeGitOutput("Git index output contains duplicate paths")
        paths.add(path)
    return paths


def _git_single_path(payload: bytes, label: str) -> Path:
    if b"\0" in payload:
        raise UnsafeGitOutput(f"{label} output contains NUL")
    try:
        value = payload.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise UnsafeGitOutput(f"{label} output is not UTF-8") from error
    if not value or "\n" in value or "\r" in value:
        raise UnsafeGitOutput(f"{label} output is invalid")
    return Path(value)


def _git_worktree_scope(root: Path) -> tuple[str, str] | None:
    discovered = _run_git(root, ("rev-parse", "--absolute-git-dir"))
    if discovered is None or discovered[0] != 0:
        return None
    git_dir = _git_single_path(discovered[1], "Git directory")
    try:
        git_dir = git_dir.resolve(strict=True)
    except OSError:
        return None
    if not git_dir.is_dir():
        return None
    scope = (f"--git-dir={git_dir}", f"--work-tree={root}")
    configured = _run_git(root, (*scope, "config", "--local", "--get", "core.worktree"))
    if configured is None:
        return None
    if configured[0] == 0:
        configured_path = _git_single_path(configured[1], "Git core.worktree")
        configured_root = (
            configured_path if configured_path.is_absolute() else git_dir / configured_path
        ).resolve()
        if configured_root != root:
            return None
    elif configured[0] != 1:
        return None
    top = _run_git(root, (*scope, "rev-parse", "--show-toplevel"))
    if top is None or top[0] != 0:
        return None
    try:
        if _git_single_path(top[1], "Git worktree").resolve(strict=True) != root:
            return None
    except OSError:
        return None
    return scope


def _proof_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise TimeoutError("Git source proof exceeded its deadline")


def _required_path(value: str) -> str:
    try:
        return _canonical_required_source_path(value)
    except (TypeError, ValueError):
        raise ValueError("source inventory contains an unsafe path") from None


def _git_bytes(
    root: Path,
    arguments: Sequence[str],
    label: str,
    *,
    input_payload: bytes | None = None,
    maximum_output: int = MAX_GIT_OUTPUT_BYTES,
) -> bytes:
    result = _run_git(
        root,
        arguments,
        input_payload=input_payload,
        maximum_output=maximum_output,
    )
    if result is None or result[0] != 0:
        raise ValueError(f"{label} is unavailable")
    return result[1]


def _commit_text(payload: bytes, label: str) -> str:
    if b"\0" in payload:
        raise UnsafeGitOutput(f"{label} contains NUL")
    try:
        value = payload.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise UnsafeGitOutput(f"{label} is not ASCII") from error
    if COMMIT_PATTERN.fullmatch(value) is None:
        raise UnsafeGitOutput(f"{label} is invalid")
    return value


def _tree_entries(payload: bytes) -> dict[str, tuple[str, str, str]]:
    if payload and not payload.endswith(b"\0"):
        raise UnsafeGitOutput("Git tree output is incomplete")
    result: dict[str, tuple[str, str, str]] = {}
    for record in payload.split(b"\0")[:-1]:
        header, separator, path_payload = record.partition(b"\t")
        fields = header.split(b" ")
        if not separator or len(fields) != 3:
            raise UnsafeGitOutput("Git tree output is malformed")
        try:
            mode, kind, object_id = (field.decode("ascii", errors="strict") for field in fields)
            path = _required_path(path_payload.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, ValueError) as error:
            raise UnsafeGitOutput("Git tree output is unsafe") from error
        if path in result:
            raise UnsafeGitOutput("Git tree output contains duplicate paths")
        result[path] = (mode, kind, object_id)
    return result


def _batch_blob_sha256(
    root: Path,
    scope: tuple[str, str],
    commit: str,
    paths: Sequence[str],
) -> dict[str, str]:
    if not paths:
        return {}
    queries = b"".join(f"{commit}:{path}\n".encode() for path in paths)
    payload = _git_bytes(
        root,
        (*scope, "cat-file", "--batch"),
        "Git commit blobs",
        input_payload=queries,
        maximum_output=MAX_GIT_BLOB_OUTPUT_BYTES,
    )
    cursor = 0
    result: dict[str, str] = {}
    for path in paths:
        header_end = payload.find(b"\n", cursor)
        if header_end < 0:
            raise UnsafeGitOutput("Git blob output is incomplete")
        header = payload[cursor:header_end].split(b" ")
        if len(header) != 3 or header[1] != b"blob":
            raise UnsafeGitOutput("Git required source is not a commit blob")
        try:
            size = int(header[2].decode("ascii", errors="strict"))
        except (UnicodeDecodeError, ValueError) as error:
            raise UnsafeGitOutput("Git blob size is invalid") from error
        if size < 0 or size > MAX_GIT_BLOB_OUTPUT_BYTES:
            raise UnsafeGitOutput("Git blob exceeds its byte limit")
        start = header_end + 1
        end = start + size
        if end >= len(payload) or payload[end : end + 1] != b"\n":
            raise UnsafeGitOutput("Git blob output is truncated")
        result[path] = hashlib.sha256(payload[start:end]).hexdigest()
        cursor = end + 1
    if cursor != len(payload):
        raise UnsafeGitOutput("Git blob output has trailing bytes")
    return result


def _same_path_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
    )


def _source_file_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _worktree_source_digest(
    root: Path,
    relative: str,
    maximum: int,
    deadline: float,
) -> tuple[str, int]:
    parts = PurePosixPath(relative).parts
    directory_fd = os.open(root, _directory_flags())
    opened = [directory_fd]
    bindings: list[tuple[int, str, int]] = []
    try:
        _proof_deadline(deadline)
        root_fd_metadata = os.fstat(directory_fd)
        root_path_metadata = os.stat(root, follow_symlinks=False)
        if not _same_path_identity(root_fd_metadata, root_path_metadata):
            raise ValueError("required worktree source root identity changed")
        for part in parts[:-1]:
            _proof_deadline(deadline)
            parent_fd = directory_fd
            child_fd = os.open(part, _directory_flags(), dir_fd=parent_fd)
            opened.append(child_fd)
            child_metadata = os.fstat(child_fd)
            path_metadata = os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISDIR(child_metadata.st_mode) or not _same_path_identity(
                child_metadata, path_metadata
            ):
                raise ValueError("required worktree source directory identity changed")
            bindings.append((parent_fd, part, child_fd))
            directory_fd = child_fd
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(parts[-1], flags, dir_fd=directory_fd)
        opened.append(descriptor)
        metadata = os.fstat(descriptor)
        path_metadata = os.stat(parts[-1], dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size < 0
            or metadata.st_size > maximum
            or not _same_path_identity(metadata, path_metadata)
            or _source_file_identity(metadata) != _source_file_identity(path_metadata)
        ):
            raise ValueError("required worktree source is unsafe")
        initial_identity = _source_file_identity(metadata)
        digest = hashlib.sha256()
        remaining = metadata.st_size
        while remaining:
            _proof_deadline(deadline)
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                raise ValueError("required worktree source is truncated")
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError("required worktree source grew during hashing")
        final_metadata = os.fstat(descriptor)
        final_path_metadata = os.stat(parts[-1], dir_fd=directory_fd, follow_symlinks=False)
        if (
            _source_file_identity(final_metadata) != initial_identity
            or _source_file_identity(final_path_metadata) != initial_identity
        ):
            raise ValueError("required worktree source changed during hashing")
        for parent_fd, name, child_fd in reversed(bindings):
            if not _same_path_identity(
                os.fstat(child_fd),
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False),
            ):
                raise ValueError("required worktree source path identity changed")
        if not _same_path_identity(os.fstat(opened[0]), os.stat(root, follow_symlinks=False)):
            raise ValueError("required worktree source root identity changed")
        _proof_deadline(deadline)
        return digest.hexdigest(), metadata.st_size
    except OSError as error:
        raise ValueError("required worktree source is unavailable") from error
    finally:
        for descriptor in reversed(opened):
            os.close(descriptor)


def _hash_worktree_sources(
    root: Path,
    required: Mapping[str, str],
    deadline: float,
) -> dict[str, str]:
    observed: dict[str, str] = {}
    remaining = MAX_SOURCE_RECHECK_BYTES
    for path in sorted(required):
        digest, size = _worktree_source_digest(root, path, remaining, deadline)
        remaining -= size
        observed[path] = digest
    return observed


def _worktree_source_sha256(root: Path, relative: str) -> str:
    digest, _size = _worktree_source_digest(
        root,
        relative,
        MAX_SOURCE_RECHECK_BYTES,
        time.monotonic() + GIT_SOURCE_PROOF_TIMEOUT_SECONDS,
    )
    return digest


def prepare_required_source_recheck(
    root: Path,
    source_digests: Mapping[str, str],
) -> tuple[dict[str, str] | None, bool]:
    try:
        resolved = _root(root)
        normalized = canonical_required_source_digests(source_digests)
    except (OSError, TypeError, ValueError):
        return None, False
    try:
        observed = _hash_worktree_sources(
            resolved,
            normalized,
            time.monotonic() + GIT_SOURCE_PROOF_TIMEOUT_SECONDS,
        )
    except (OSError, TimeoutError, ValueError):
        return normalized, False
    return normalized, observed == normalized


def _read_optional_git_attributes(path: Path) -> bytes | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ValueError("Git info attributes are unavailable") from error
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > MAX_GIT_OUTPUT_BYTES
    ):
        raise ValueError("Git info attributes are unsafe")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            payload = os.read(descriptor, MAX_GIT_OUTPUT_BYTES + 1)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ValueError("Git info attributes are unavailable") from error
    if len(payload) > MAX_GIT_OUTPUT_BYTES:
        raise ValueError("Git info attributes exceed their byte limit")
    return payload


def _checkout_transform_snapshot(
    root: Path,
    scope: tuple[str, str],
    deadline: float,
) -> tuple[tuple[str, bytes | None], ...]:
    _proof_deadline(deadline)
    config = _run_git(
        root,
        (*scope, "config", "--null", "--get-regexp", _TRANSFORM_CONFIG_PATTERN),
        environment=_git_configuration_environment(),
    )
    if config is None or config[0] not in {0, 1}:
        raise ValueError("Git checkout transform configuration is unavailable")
    if config[0] == 0 or config[1]:
        raise ValueError("Git checkout transform configuration is present")

    git_dir = Path(scope[0].split("=", 1)[1])
    common_value = _git_single_path(
        _git_bytes(root, (*scope, "rev-parse", "--git-common-dir"), "Git common directory"),
        "Git common directory",
    )
    try:
        common_dir = (common_value if common_value.is_absolute() else root / common_value).resolve(
            strict=True
        )
    except OSError as error:
        raise ValueError("Git common directory is unavailable") from error
    if not common_dir.is_dir():
        raise ValueError("Git common directory is invalid")

    snapshots: list[tuple[str, bytes | None]] = []
    for directory in dict.fromkeys((git_dir, common_dir)):
        info = directory / "info"
        try:
            info_metadata = info.lstat()
        except FileNotFoundError:
            payload = None
        except OSError as error:
            raise ValueError("Git info attributes are unavailable") from error
        else:
            if info.is_symlink() or not stat.S_ISDIR(info_metadata.st_mode):
                raise ValueError("Git info attributes are unsafe")
            payload = _read_optional_git_attributes(info / "attributes")
        if payload:
            raise ValueError("Git info attributes are present")
        snapshots.append((str(info / "attributes"), payload))
    return tuple(snapshots)


def _capture_repository_git_state(
    root: Path,
    expected_commit: str | None,
    deadline: float,
) -> tuple[
    tuple[str, str],
    str,
    bytes,
    bytes,
    bytes,
    tuple[tuple[str, bytes | None], ...],
]:
    _proof_deadline(deadline)
    scope = _git_worktree_scope(root)
    if scope is None:
        raise ValueError("Git worktree scope is unavailable")
    head = _commit_text(
        _git_bytes(root, (*scope, "rev-parse", "--verify", "HEAD^{commit}"), "Git HEAD"),
        "Git HEAD",
    )
    replacements = _git_bytes(
        root,
        (*scope, "for-each-ref", "--format=%(refname)", "refs/replace"),
        "Git replacement refs",
    )
    if replacements.strip():
        raise ValueError("Git replacement refs are present")
    if expected_commit is not None and head != expected_commit:
        raise ValueError("Git HEAD does not match the captured commit")
    flags = _git_bytes(root, (*scope, "ls-files", "-v", "-z"), "Git index flags")
    _tracked, flags_clean = _tracked_paths_from_flags(flags)
    if not flags_clean:
        raise ValueError("Git index visibility flags are present")
    index = _git_bytes(root, (*scope, "ls-files", "-s", "-z"), "Git index")
    _index_paths_without_unsupported_entries(index)
    status = _git_bytes(
        root,
        (
            *scope,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=normal",
            "--ignore-submodules=none",
            "--no-renames",
        ),
        "Git status",
    )
    if status:
        raise ValueError("Git worktree is not clean")
    transforms = _checkout_transform_snapshot(root, scope, deadline)
    return scope, head, flags, index, status, transforms


def _prove_required_sources(
    root: Path,
    expected_commit: str | None,
    required: Mapping[str, str],
    deadline: float,
) -> str:
    before = _capture_repository_git_state(root, expected_commit, deadline)
    scope, commit, _flags, _index, _status, _transforms = before
    _proof_deadline(deadline)
    tree = _tree_entries(
        _git_bytes(
            root,
            (*scope, "ls-tree", "-r", "-z", commit),
            "Git commit tree",
            maximum_output=MAX_GIT_TREE_OUTPUT_BYTES,
        )
    )
    if any(mode == "160000" and kind == "commit" for mode, kind, _object_id in tree.values()):
        raise ValueError("Git gitlinks are outside the freshness proof scope")
    if _hash_worktree_sources(root, required, deadline) != required:
        raise ValueError("required worktree source digest does not match report evidence")
    observed = _batch_blob_sha256(root, scope, commit, tuple(sorted(required)))
    if observed != required:
        raise ValueError("required source digest does not match the captured commit")
    _proof_deadline(deadline)
    after = _capture_repository_git_state(root, commit, deadline)
    if before[1:] != after[1:]:
        raise ValueError("Git repository state changed during source proof")
    if _hash_worktree_sources(root, required, deadline) != required:
        raise ValueError("required worktree source changed during source proof")
    return commit


def probe_source_inventory_git(
    root: Path, source_digests: Mapping[str, str]
) -> tuple[str | None, bool, bool]:
    resolved = _root(root)
    if not isinstance(source_digests, Mapping) or any(
        not isinstance(path, str)
        or not isinstance(digest, str)
        or SHA256_PATTERN.fullmatch(digest) is None
        for path, digest in source_digests.items()
    ):
        raise ValueError("source inventory must map paths to SHA-256 digests")
    try:
        normalized = canonical_required_source_digests(source_digests)
        commit = _prove_required_sources(
            resolved,
            None,
            normalized,
            time.monotonic() + GIT_SOURCE_PROOF_TIMEOUT_SECONDS,
        )
        return commit, True, True
    except (OSError, TimeoutError, UnsafeGitOutput, ValueError):
        baseline_commit, baseline_clean = probe_git_baseline(resolved)
        return baseline_commit, baseline_clean, False
