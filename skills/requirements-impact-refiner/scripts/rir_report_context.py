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
import time
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPORT_ID_PATTERN = re.compile(r"RPT-\d{3}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z")
MAX_REQUIREMENT_INPUT_BYTES = 256 * 1024
MAX_REQUIREMENT_BYTES = 64 * 1024
MAX_CONTEXT_BYTES = 8 * 1024
MAX_MARKDOWN_BYTES = 4 * 1024 * 1024
MAX_GIT_OUTPUT_BYTES = 256 * 1024
GIT_TIMEOUT_SECONDS = 0.25
MAX_CONTEXT_STAGE_CANDIDATES = 8
_CONTEXT_FIELDS = frozenset(
    {
        "schema_version",
        "report_id",
        "revision",
        "markdown_sha256",
        "repo_root_sha256",
        "requirement_sha256",
        "source_inventory_sha256",
        "source_inventory_available",
        "source_inventory_complete",
        "payload_sha256",
        "created_at",
        "baseline_commit",
        "baseline_clean",
    }
)


@dataclass(frozen=True)
class ReportContext:
    schema_version: int
    report_id: str
    revision: int
    markdown_sha256: str
    repo_root_sha256: str
    requirement_sha256: str
    source_inventory_sha256: str | None
    payload_sha256: str
    created_at: str
    baseline_commit: str | None
    baseline_clean: bool
    source_inventory_available: bool = True
    source_inventory_complete: bool = True

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("report context schema_version must be 1")
        if type(self.report_id) is not str or REPORT_ID_PATTERN.fullmatch(self.report_id) is None:
            raise ValueError("report context report_id is invalid")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("report context revision is invalid")
        for label, value in (
            ("markdown_sha256", self.markdown_sha256),
            ("repo_root_sha256", self.repo_root_sha256),
            ("requirement_sha256", self.requirement_sha256),
            ("payload_sha256", self.payload_sha256),
        ):
            if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
                raise ValueError(f"report context {label} is invalid")
        if type(self.source_inventory_available) is not bool:
            raise TypeError("report context source_inventory_available must be boolean")
        if type(self.source_inventory_complete) is not bool:
            raise TypeError("report context source_inventory_complete must be boolean")
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


def _mapping(context: ReportContext) -> dict[str, object]:
    return {
        "schema_version": context.schema_version,
        "report_id": context.report_id,
        "revision": context.revision,
        "markdown_sha256": context.markdown_sha256,
        "repo_root_sha256": context.repo_root_sha256,
        "requirement_sha256": context.requirement_sha256,
        "source_inventory_sha256": context.source_inventory_sha256,
        "source_inventory_available": context.source_inventory_available,
        "source_inventory_complete": context.source_inventory_complete,
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
    if not isinstance(value, Mapping) or set(value) != _CONTEXT_FIELDS:
        raise ValueError("report context payload has an invalid schema")
    try:
        context = ReportContext(
            schema_version=value["schema_version"],
            report_id=value["report_id"],
            revision=value["revision"],
            markdown_sha256=value["markdown_sha256"],
            repo_root_sha256=value["repo_root_sha256"],
            requirement_sha256=value["requirement_sha256"],
            source_inventory_sha256=value["source_inventory_sha256"],
            payload_sha256=value["payload_sha256"],
            created_at=value["created_at"],
            baseline_commit=value["baseline_commit"],
            baseline_clean=value["baseline_clean"],
            source_inventory_available=value["source_inventory_available"],
            source_inventory_complete=value["source_inventory_complete"],
        )
    except (TypeError, ValueError) as error:
        raise ValueError("report context payload has invalid values") from error
    if _canonical_bytes(context) != payload:
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
    selected_name = name or f"revision-{revision:04d}.context.json"
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
) -> None:
    if context.repo_root_sha256 != repo_root_sha256 or context.markdown_sha256 != markdown_sha256:
        raise ValueError("report context pending identity is invalid")
    if expected is not None and context != expected:
        raise FileExistsError(f"revision-{context.revision:04d}.context.json")


def _load_or_recover_context(
    directory_fd: int,
    report_id: str,
    revision: int,
    *,
    expected: ReportContext | None,
    repo_root_sha256: str,
    markdown_sha256: str,
) -> ReportContext | None:
    name = f"revision-{revision:04d}.context.json"
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
    name = f"revision-{context.revision:04d}.context.json"
    pending = _context_pending_name(name)
    stage: str | None = None
    stage_created = False
    stage_metadata: os.stat_result | None = None
    descriptor: int | None = None
    payload = _canonical_bytes(context)
    try:
        markdown_sha256 = _markdown_sha256(directory_fd, context.revision)
        repo_sha256 = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()
        if markdown_sha256 != context.markdown_sha256:
            raise ValueError("report context Markdown digest is invalid")
        existing = _load_or_recover_context(
            directory_fd,
            context.report_id,
            context.revision,
            expected=context,
            repo_root_sha256=repo_sha256,
            markdown_sha256=markdown_sha256,
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
        return _load_or_recover_context(
            directory_fd,
            report_id,
            revision,
            expected=None,
            repo_root_sha256=expected_root,
            markdown_sha256=markdown_sha256,
        )
    finally:
        os.close(directory_fd)


def _git_environment() -> dict[str, str]:
    environment = {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", ""),
    }
    system_root = os.environ.get("SYSTEMROOT")
    if system_root:
        environment["SYSTEMROOT"] = system_root
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


def _run_git(root: Path, arguments: Sequence[str]) -> tuple[int, bytes] | None:
    command = (
        "git",
        "--no-pager",
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
    try:
        process = subprocess.Popen(
            command,
            cwd=str(root),
            env=_git_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return None
    if process.stdout is None:  # pragma: no cover - PIPE guarantees stdout
        _stop_process(process)
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
                    min(64 * 1024, MAX_GIT_OUTPUT_BYTES + 1 - len(payload)),
                )
            except BlockingIOError:
                continue
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > MAX_GIT_OUTPUT_BYTES:
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
    status_result = _run_git(
        resolved,
        (
            "status",
            "--porcelain=v1",
            "--untracked-files=normal",
            "--ignore-submodules=none",
            "--no-renames",
        ),
    )
    if status_result is None or status_result[0] != 0:
        return commit, False
    if b"\0" in status_result[1]:
        raise UnsafeGitOutput("Git status output contains NUL")
    if status_result[1] != b"":
        return commit, False
    submodule_result = _run_git(resolved, ("submodule", "status", "--recursive"))
    if submodule_result is None or submodule_result[0] != 0:
        return commit, False
    if b"\0" in submodule_result[1]:
        raise UnsafeGitOutput("Git submodule output contains NUL")
    if any(not line.startswith(b" ") for line in submodule_result[1].splitlines()):
        return commit, False
    return commit, True
