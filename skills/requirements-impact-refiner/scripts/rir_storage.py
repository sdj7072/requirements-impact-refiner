#!/usr/bin/env python3
"""Private controller storage, locking, CAS, and recovery primitives."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Protocol, SupportsInt, cast

if TYPE_CHECKING:
    from typing_extensions import TypeGuard


class _FcntlContract(Protocol):
    LOCK_EX: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, fd: int, operation: int) -> None: ...


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


def _is_fcntl_contract(value: object) -> TypeGuard[_FcntlContract]:
    return all(
        isinstance(getattr(value, name, None), int) for name in ("LOCK_EX", "LOCK_NB", "LOCK_UN")
    ) and callable(getattr(value, "flock", None))


try:
    import fcntl as _loaded_fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback is serialized per process
    fcntl: _FcntlContract | None = None
else:
    if not _is_fcntl_contract(_loaded_fcntl):  # pragma: no cover - standard-library contract
        raise ImportError("fcntl contract is incomplete")
    fcntl = _loaded_fcntl


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
        raise ImportError(f"cannot load fixed storage {label} sibling")
    module = importlib.util.module_from_spec(specification)
    previous = {name: (name in sys.modules, sys.modules.get(name)) for name in (aliases or {})}
    sys.modules[module_name] = module
    try:
        if aliases:
            sys.modules.update(aliases)
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError(f"cannot load fixed storage {label} sibling") from error
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
        raise ImportError(f"storage {label} sibling contract is incomplete")
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
        raise ImportError(f"storage {label} sibling is unsafe")
    hashed_name = prefix + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    hashed_present = hashed_name in sys.modules
    hashed = sys.modules.get(hashed_name)
    if canonical_name not in sys.modules:
        if hashed_present:
            if not _module_uses_sibling(hashed, expected):
                raise ImportError(f"storage {label} sibling is unsafe")
            if not validator(hashed):
                raise ImportError(f"storage {label} sibling contract is incomplete")
            sys.modules[canonical_name] = cast(ModuleType, hashed)
            return hashed
        return _execute_registered(canonical_name, expected, validator, label, aliases=aliases)
    canonical = sys.modules.get(canonical_name)
    if _module_uses_sibling(canonical, expected):
        if validator(canonical) and not hashed_present:
            return canonical
        if hashed_present:
            if not _module_uses_sibling(hashed, expected):
                raise ImportError(f"storage {label} sibling is unsafe")
            if not validator(hashed):
                raise ImportError(f"storage {label} sibling contract is incomplete")
            return hashed
        if aliases is not None:
            return _execute_registered(hashed_name, expected, validator, label, aliases=aliases)
        raise ImportError(f"storage {label} sibling contract is incomplete")
    if hashed_present:
        if not _module_uses_sibling(hashed, expected):
            raise ImportError(f"storage {label} sibling is unsafe")
        if not validator(hashed):
            raise ImportError(f"storage {label} sibling contract is incomplete")
        return hashed
    return _execute_registered(hashed_name, expected, validator, label, aliases=aliases)


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
report_store = REPORT_STORE


MAX_DRAFT_BYTES = 4 * 1024 * 1024
MAX_CONTROLLER_METADATA_BYTES = 256 * 1024
MAX_CONTROLLER_METADATA_DEPTH = 64
DRAFT_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_RECEIPT_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_CONTROLLER_METADATA_BASE_FIELDS = frozenset(
    {"schema_version", "draft_id", "report_id", "revision", "state_sha256", "key_map"}
)
_CONTEXT_IDENTITY_FIELDS = frozenset(
    {
        "repo_root_sha256",
        "requirement_sha256",
        "source_inventory_sha256",
        "source_inventory_available",
        "source_inventory_complete",
        "payload_sha256",
    }
)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _is_int_input(value: object) -> TypeGuard[str | bytes | bytearray | SupportsInt]:
    return isinstance(value, (str, bytes, bytearray)) or callable(getattr(value, "__int__", None))


def _int_value(value: object) -> int:
    if not _is_int_input(value):
        raise TypeError(
            "int() argument must be a string, a bytes-like object or a real number, "
            f"not '{type(value).__name__}'"
        )
    return int(value)


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


def _controller_metadata_path(report_id: str, revision: int, root: Path) -> Path:
    report_dir = report_store.report_directory(root, report_id, create=True)
    return report_dir / f"revision-{revision:04d}.controller.json"


def _valid_context_identity(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != _CONTEXT_IDENTITY_FIELDS:
        return False
    for key in ("repo_root_sha256", "requirement_sha256", "payload_sha256"):
        digest = value.get(key)
        if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
            return False
    available = value.get("source_inventory_available")
    complete = value.get("source_inventory_complete")
    inventory_digest = value.get("source_inventory_sha256")
    if not isinstance(available, bool) or not isinstance(complete, bool):
        return False
    if complete and not available:
        return False
    if available:
        return (
            isinstance(inventory_digest, str)
            and _SHA256_PATTERN.fullmatch(inventory_digest) is not None
        )
    return inventory_digest is None


def _json_depth(text: str) -> int:
    depth = 0
    peak = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            peak = max(peak, depth)
        elif char in "]}":
            depth = max(0, depth - 1)
    return peak


def _validate_controller_metadata_bytes(
    raw: bytes,
    *,
    report_id: str,
    revision: int,
    state_sha256: str | None,
) -> dict[str, object]:
    if not raw or len(raw) > MAX_CONTROLLER_METADATA_BYTES:
        raise ValueError("controller lineage metadata exceeds 256 KiB")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("controller lineage metadata is invalid") from error
    if _json_depth(text) > MAX_CONTROLLER_METADATA_DEPTH:
        raise ValueError("controller lineage metadata exceeds its depth limit")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("controller lineage metadata is invalid") from error
    allowed_fields = _CONTROLLER_METADATA_BASE_FIELDS | {
        "graph_receipt",
        "analysis_sha256",
        "context_identity",
    }
    fields = set(payload) if isinstance(payload, dict) else set()
    completion_fields = {"analysis_sha256", "context_identity"}
    graph_receipt = payload.get("graph_receipt") if isinstance(payload, dict) else None
    graph_valid = "graph_receipt" not in fields or (
        isinstance(graph_receipt, dict)
        and set(graph_receipt) == {"receipt_id", "sha256"}
        and isinstance(graph_receipt.get("receipt_id"), str)
        and _RECEIPT_ID_PATTERN.fullmatch(graph_receipt["receipt_id"]) is not None
        and isinstance(graph_receipt.get("sha256"), str)
        and _SHA256_PATTERN.fullmatch(graph_receipt["sha256"]) is not None
    )
    if (
        not isinstance(payload, dict)
        or not _CONTROLLER_METADATA_BASE_FIELDS <= fields <= allowed_fields
        or bool(fields & completion_fields) != (completion_fields <= fields)
        or _canonical_bytes(payload) != raw
        or type(payload.get("schema_version")) is not int
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("draft_id"), str)
        or DRAFT_ID_PATTERN.fullmatch(payload["draft_id"]) is None
        or payload.get("report_id") != report_id
        or payload.get("revision") != revision
        or type(payload.get("revision")) is not int
        or revision < 1
        or (state_sha256 is not None and payload.get("state_sha256") != state_sha256)
        or _SHA256_PATTERN.fullmatch(str(payload.get("state_sha256"))) is None
        or not isinstance(payload.get("key_map"), dict)
        or not graph_valid
        or (
            completion_fields <= fields
            and (
                not isinstance(payload.get("analysis_sha256"), str)
                or _SHA256_PATTERN.fullmatch(payload["analysis_sha256"]) is None
                or not _valid_context_identity(payload.get("context_identity"))
            )
        )
    ):
        raise ValueError("controller lineage metadata identity is invalid")
    return payload


def _controller_metadata_directory_fd(path: Path) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path.parent, flags)
    except OSError as error:
        raise ValueError("controller lineage metadata directory is unsafe") from error


def _read_controller_metadata_artifact(
    directory_fd: int,
    name: str,
    *,
    report_id: str,
    revision: int,
    state_sha256: str | None,
    allowed_links: frozenset[int],
) -> tuple[dict[str, object], bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as error:
        raise ValueError("controller lineage metadata recovery alias is invalid") from error
    try:
        metadata = os.fstat(descriptor)
        expected_owner = os.fstat(directory_fd).st_uid
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != expected_owner
            or metadata.st_nlink not in allowed_links
            or metadata.st_size <= 0
            or metadata.st_size > MAX_CONTROLLER_METADATA_BYTES
        ):
            raise ValueError("controller lineage metadata is unsafe")
        raw = _read_bounded_descriptor(
            descriptor, MAX_CONTROLLER_METADATA_BYTES, "controller lineage metadata"
        )
    finally:
        os.close(descriptor)
    value = _validate_controller_metadata_bytes(
        raw,
        report_id=report_id,
        revision=revision,
        state_sha256=state_sha256,
    )
    return value, raw, metadata


def _fsync_controller_metadata_directory(directory_fd: int) -> None:
    try:
        os.fsync(directory_fd)
    except OSError as error:
        raise ValueError("cannot fsync controller lineage metadata directory") from error


def _unlink_controller_metadata_temporary(directory_fd: int, temporary: str) -> None:
    try:
        os.unlink(temporary, dir_fd=directory_fd)
    except OSError as error:
        raise ValueError("cannot cleanup controller lineage metadata temporary") from error


def _load_or_recover_controller_metadata(
    directory_fd: int,
    name: str,
    *,
    report_id: str,
    revision: int,
    state_sha256: str | None,
) -> tuple[dict[str, object], bytes]:
    value, raw, target = _read_controller_metadata_artifact(
        directory_fd,
        name,
        report_id=report_id,
        revision=revision,
        state_sha256=state_sha256,
        allowed_links=frozenset({1, 2}),
    )
    if target.st_nlink == 1:
        return value, raw
    temporary = f".{name}.{value['draft_id']}.tmp"
    alias_value, alias_raw, alias = _read_controller_metadata_artifact(
        directory_fd,
        temporary,
        report_id=report_id,
        revision=revision,
        state_sha256=state_sha256,
        allowed_links=frozenset({2}),
    )
    if (
        alias.st_dev != target.st_dev
        or alias.st_ino != target.st_ino
        or alias_raw != raw
        or alias_value != value
    ):
        raise ValueError("controller lineage metadata recovery alias is invalid")
    _unlink_controller_metadata_temporary(directory_fd, temporary)
    _fsync_controller_metadata_directory(directory_fd)
    recovered, recovered_raw, recovered_metadata = _read_controller_metadata_artifact(
        directory_fd,
        name,
        report_id=report_id,
        revision=revision,
        state_sha256=state_sha256,
        allowed_links=frozenset({1}),
    )
    if recovered != value or recovered_raw != raw or recovered_metadata.st_nlink != 1:
        raise ValueError("controller lineage metadata recovery verification failed")
    return recovered, recovered_raw


def _load_controller_completion_metadata(current) -> dict[str, object] | None:
    path = current.state_path.with_name(f"revision-{current.revision:04d}.controller.json")
    if not path.exists():
        return None
    try:
        current_state_sha256 = hashlib.sha256(current.state_path.read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError(f"controller lineage metadata is invalid: {error}") from error
    directory_fd = _controller_metadata_directory_fd(path)
    try:
        value, _raw = _load_or_recover_controller_metadata(
            directory_fd,
            path.name,
            report_id=current.report_id,
            revision=current.revision,
            state_sha256=current_state_sha256,
        )
    finally:
        os.close(directory_fd)
    return value


def _load_controller_metadata(current) -> dict[str, object] | None:
    metadata = _load_controller_completion_metadata(current)
    if metadata is None:
        return None
    return cast(dict[str, object], metadata["key_map"])


def _draft_path(root: Path, draft_id: str) -> Path:
    if DRAFT_ID_PATTERN.fullmatch(draft_id) is None:
        raise ValueError("invalid draft ID")
    return root / ".requirements-impact-refiner" / "drafts" / f"{draft_id}.json"


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


def _replace_private_draft(root: Path, draft_id: str, value: Mapping[str, object]) -> None:
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
            temporary_name,
            f"{draft_id}.json",
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
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


def _read_bounded_descriptor(descriptor: int, maximum: int, label: str) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    payload = bytearray()
    while len(payload) <= maximum:
        chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - len(payload)))
        if not chunk:
            break
        payload.extend(chunk)
    if len(payload) > maximum:
        raise ValueError(f"{label} exceeds maximum byte size")
    return bytes(payload)


_DRAFT_TRANSACTION_KEYS = {
    "schema_version",
    "draft_id",
    "repo_root_sha256",
    "transaction_id",
    "expected_sha256",
    "expected_dev",
    "expected_ino",
    "replacement_sha256",
    "replacement_dev",
    "replacement_ino",
}
_DRAFT_TRANSACTION_MAX_BYTES = 16 * 1024


@contextmanager
def _draft_transaction_lock(directory_fd: int):
    descriptor = None
    locked = False
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(".draft-transaction.lock", flags, 0o600, dir_fd=directory_fd)
    except OSError as error:
        raise ValueError(f"draft transaction lock is unavailable: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise ValueError("draft transaction lock is unsafe")
        current_fcntl = fcntl
        if current_fcntl is not None:
            try:
                current_fcntl.flock(descriptor, current_fcntl.LOCK_EX | current_fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("draft transaction recovery is busy; retry") from error
            locked = True
        yield
    finally:
        if descriptor is not None:
            if locked and current_fcntl is not None:
                current_fcntl.flock(descriptor, current_fcntl.LOCK_UN)
            os.close(descriptor)


def _write_private_transaction_component(directory_fd: int, name: str, payload: bytes, label: str):
    descriptor = None
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise ValueError(f"{label} is unsafe")
        return descriptor, metadata
    except BaseException as error:
        cleanup_error = None
        if descriptor is not None:
            try:
                metadata = os.fstat(descriptor)
                actual_payload = _read_bounded_descriptor(descriptor, max(len(payload), 1), label)
                _unlink_transaction_component(
                    directory_fd,
                    name,
                    (descriptor, metadata, actual_payload),
                    payload,
                    max(len(payload), 1),
                    label,
                )
            except (OSError, ValueError) as cleanup_failure:
                cleanup_error = cleanup_failure
            os.close(descriptor)
        if cleanup_error is not None:
            raise ValueError(
                f"cannot persist {label}; cleanup is uncertain: {cleanup_error}"
            ) from error
        if isinstance(error, OSError):
            raise ValueError(f"cannot persist {label}: {error}") from error
        raise


def _open_optional_transaction_component(directory_fd: int, name: str, maximum: int, label: str):
    descriptor = None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ValueError(f"{label} is unavailable or unsafe: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ValueError(f"{label} is not a private regular file")
        payload = _read_bounded_descriptor(descriptor, maximum, label)
        return descriptor, metadata, payload
    except BaseException:
        os.close(descriptor)
        raise


def _transaction_removing_name(name: str) -> str:
    return f"{name}.removing"


def _open_transaction_component_for_cleanup(directory_fd: int, name: str, maximum: int, label: str):
    removing_name = _transaction_removing_name(name)
    original = _open_optional_transaction_component(directory_fd, name, maximum, label)
    try:
        removing = _open_optional_transaction_component(
            directory_fd,
            removing_name,
            maximum,
            f"{label} removal quarantine",
        )
    except BaseException:
        if original is not None:
            os.close(original[0])
        raise
    if original is not None and removing is not None:
        os.close(original[0])
        os.close(removing[0])
        raise ValueError(f"{label} and its removal quarantine both exist; recovery is uncertain")
    if removing is not None:
        return removing, removing_name
    return original, name


def _draft_transaction_phase_payload(
    draft_id: str, transaction_id: str, phase: str, manifest_sha256: str
) -> bytes:
    return _canonical_bytes(
        {
            "draft_id": draft_id,
            "manifest_sha256": manifest_sha256,
            "phase": phase,
            "schema_version": 1,
            "transaction_id": transaction_id,
        }
    )


_DRAFT_CLEANUP_KEYS = {
    "draft_id",
    "kind",
    "manifest_sha256",
    "replacement_dev",
    "replacement_ino",
    "replacement_sha256",
    "repo_root_sha256",
    "schema_version",
    "transaction_id",
}


def _draft_transaction_cleanup_payload(
    root: Path,
    draft_id: str,
    manifest: Mapping[str, object],
    manifest_payload: bytes,
) -> bytes:
    return _canonical_bytes(
        {
            "draft_id": draft_id,
            "kind": "draft-transaction-cleanup",
            "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
            "replacement_dev": manifest["replacement_dev"],
            "replacement_ino": manifest["replacement_ino"],
            "replacement_sha256": manifest["replacement_sha256"],
            "repo_root_sha256": hashlib.sha256(str(root).encode("utf-8")).hexdigest(),
            "schema_version": 1,
            "transaction_id": manifest["transaction_id"],
        }
    )


def _validate_draft_transaction_cleanup(
    root: Path,
    draft_id: str,
    cleanup_component,
    canonical_component,
    *,
    manifest: Mapping[str, object] | None = None,
    manifest_payload: bytes | None = None,
) -> Mapping[str, object]:
    try:
        cleanup = json.loads(cleanup_component[2].decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"draft transaction cleanup phase is invalid: {error}") from error
    if (
        not isinstance(cleanup, dict)
        or set(cleanup) != _DRAFT_CLEANUP_KEYS
        or cleanup.get("schema_version") != 1
        or cleanup.get("kind") != "draft-transaction-cleanup"
        or cleanup.get("draft_id") != draft_id
        or cleanup.get("repo_root_sha256") != hashlib.sha256(str(root).encode("utf-8")).hexdigest()
        or not isinstance(cleanup.get("transaction_id"), str)
        or DRAFT_ID_PATTERN.fullmatch(cleanup["transaction_id"]) is None
        or any(
            not isinstance(cleanup.get(key), int) or cleanup[key] < 0
            for key in ("replacement_dev", "replacement_ino")
        )
        or any(
            not isinstance(cleanup.get(key), str)
            or re.fullmatch(r"[0-9a-f]{64}", cleanup[key]) is None
            for key in ("manifest_sha256", "replacement_sha256")
        )
        or _canonical_bytes(cleanup) != cleanup_component[2]
        or cleanup_component[1].st_nlink != 1
    ):
        raise ValueError("draft transaction cleanup phase identity is invalid")
    if manifest is not None:
        if manifest_payload is None or cleanup_component[2] != (
            _draft_transaction_cleanup_payload(root, draft_id, manifest, manifest_payload)
        ):
            raise ValueError("draft transaction cleanup phase does not match its manifest")
    if canonical_component is None:
        raise ValueError("draft transaction cleanup phase lost canonical draft")
    canonical_info = canonical_component[1]
    canonical_payload = canonical_component[2]
    if (
        not stat.S_ISREG(canonical_info.st_mode)
        or stat.S_IMODE(canonical_info.st_mode) != 0o600
        or canonical_info.st_nlink != 1
        or (canonical_info.st_dev, canonical_info.st_ino)
        != (cleanup["replacement_dev"], cleanup["replacement_ino"])
        or hashlib.sha256(canonical_payload).hexdigest() != cleanup["replacement_sha256"]
    ):
        raise ValueError("draft transaction cleanup canonical identity is invalid")
    _validate_transaction_draft_payload(
        canonical_payload,
        root,
        draft_id,
        "draft transaction cleanup canonical",
    )
    return cleanup


def _validate_transaction_draft_payload(
    payload: bytes, root: Path, draft_id: str, label: str
) -> None:
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not a valid draft: {error}") from error
    if (
        not isinstance(value, dict)
        or value.get("draft_id") != draft_id
        or value.get("repo_root") != str(root)
        or _canonical_bytes(value) != payload
    ):
        raise ValueError(f"{label} draft identity is invalid")


def _same_inode(first, second) -> bool:
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


def _rename_noreplace(directory_fd: int, source: str, destination: str) -> None:
    """Atomically move one parent-fd-relative name without clobbering another."""
    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if sys.platform == "darwin":
        operation = library.renameatx_np
        operation.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        operation.restype = ctypes.c_int
        result = operation(
            directory_fd,
            source_bytes,
            directory_fd,
            destination_bytes,
            0x00000004,  # RENAME_EXCL
        )
    elif sys.platform.startswith("linux"):
        try:
            operation = library.renameat2
        except AttributeError as error:
            raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable") from error
        operation.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        operation.restype = ctypes.c_int
        result = operation(
            directory_fd,
            source_bytes,
            directory_fd,
            destination_bytes,
            0x00000001,  # RENAME_NOREPLACE
        )
    else:
        raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable")
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise FileExistsError(error_number, os.strerror(error_number), destination)
    raise OSError(error_number, os.strerror(error_number), source)


def _restore_quarantined_path(directory_fd: int, quarantine_name: str, original_name: str) -> bool:
    try:
        os.link(
            quarantine_name,
            original_name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
    except (FileExistsError, OSError):
        return False
    try:
        quarantine_info = os.stat(quarantine_name, dir_fd=directory_fd, follow_symlinks=False)
        restored_info = os.stat(original_name, dir_fd=directory_fd, follow_symlinks=False)
        if not _same_inode(quarantine_info, restored_info):
            return False
        os.unlink(quarantine_name, dir_fd=directory_fd)
        return True
    except OSError:
        return False


def _unlink_transaction_component(
    directory_fd: int,
    name: str,
    component,
    expected_payload: bytes,
    maximum: int,
    label: str,
    *,
    selected_name: str | None = None,
) -> None:
    if component is None:
        return
    descriptor, metadata, payload = component
    selected = name if selected_name is None else selected_name
    removing_name = _transaction_removing_name(name)
    if selected not in {name, removing_name}:
        raise ValueError(f"{label} cleanup path is invalid")
    if payload != expected_payload:
        raise ValueError(f"{label} changed before cleanup")
    try:
        current = os.stat(selected, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as error:
        raise ValueError(f"{label} is unavailable before cleanup: {error}") from error
    if (
        not _same_inode(current, metadata)
        or _read_bounded_descriptor(descriptor, maximum, label) != expected_payload
    ):
        raise ValueError(f"{label} identity changed before cleanup")

    if selected == name:
        try:
            _rename_noreplace(directory_fd, name, removing_name)
        except FileExistsError as error:
            raise ValueError(
                f"{label} removal quarantine already exists; recovery is uncertain"
            ) from error
        except OSError as error:
            raise ValueError(f"{label} cannot be quarantined: {error}") from error
        selected = removing_name

    try:
        quarantined = _open_optional_transaction_component(
            directory_fd,
            selected,
            maximum,
            f"{label} removal quarantine",
        )
    except ValueError as error:
        restored = _restore_quarantined_path(directory_fd, selected, name)
        qualifier = "restored" if restored else "restoration is uncertain"
        raise ValueError(f"{label} replacement was quarantined and {qualifier}") from error
    if quarantined is None:
        raise ValueError(f"{label} removal quarantine disappeared")
    quarantine_fd = quarantined[0]
    try:
        if (
            not _same_inode(quarantined[1], metadata)
            or quarantined[2] != expected_payload
            or _read_bounded_descriptor(descriptor, maximum, label) != expected_payload
        ):
            restored = _restore_quarantined_path(directory_fd, selected, name)
            qualifier = "restored" if restored else "restoration is uncertain"
            raise ValueError(f"{label} replacement was quarantined and {qualifier}")
        try:
            os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError as error:
            raise ValueError(f"{label} canonical cleanup namespace is unsafe: {error}") from error
        else:
            raise ValueError(f"{label} replacement preserved; recovery is uncertain")
        os.unlink(selected, dir_fd=directory_fd)
        try:
            os.stat(selected, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError(f"{label} quarantine replacement preserved; recovery is uncertain")
        try:
            os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError(f"{label} late replacement preserved; recovery is uncertain")
        os.fsync(directory_fd)
    finally:
        os.close(quarantine_fd)


def _recover_private_draft_transaction_at(root: Path, draft_id: str, directory_fd: int) -> None:
    manifest_name = f".{draft_id}.transaction"
    cleanup_name = f".{draft_id}.cleanup"
    manifest_component, manifest_selected_name = _open_transaction_component_for_cleanup(
        directory_fd,
        manifest_name,
        _DRAFT_TRANSACTION_MAX_BYTES,
        "draft transaction manifest",
    )
    try:
        cleanup_component, cleanup_selected_name = _open_transaction_component_for_cleanup(
            directory_fd,
            cleanup_name,
            _DRAFT_TRANSACTION_MAX_BYTES,
            "draft transaction cleanup phase",
        )
    except BaseException:
        if manifest_component is not None:
            os.close(manifest_component[0])
        raise
    opened = []
    if manifest_component is None:
        if cleanup_component is None:
            return
        opened.append(cleanup_component[0])
        canonical = _open_optional_transaction_component(
            directory_fd,
            f"{draft_id}.json",
            MAX_DRAFT_BYTES,
            "draft transaction cleanup canonical draft",
        )
        if canonical is not None:
            opened.append(canonical[0])
        try:
            _validate_draft_transaction_cleanup(root, draft_id, cleanup_component, canonical)
            _unlink_transaction_component(
                directory_fd,
                cleanup_name,
                cleanup_component,
                cleanup_component[2],
                _DRAFT_TRANSACTION_MAX_BYTES,
                "draft transaction cleanup phase",
                selected_name=cleanup_selected_name,
            )
            os.fsync(directory_fd)
            return
        finally:
            for descriptor in reversed(opened):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
    opened = [manifest_component[0]]
    if cleanup_component is not None:
        opened.append(cleanup_component[0])
    try:
        manifest_payload = manifest_component[2]
        try:
            manifest = json.loads(manifest_payload.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"draft transaction manifest is invalid: {error}") from error
        if (
            not isinstance(manifest, dict)
            or set(manifest) != _DRAFT_TRANSACTION_KEYS
            or manifest.get("schema_version") != 1
            or manifest.get("draft_id") != draft_id
            or manifest.get("repo_root_sha256")
            != hashlib.sha256(str(root).encode("utf-8")).hexdigest()
            or not isinstance(manifest.get("transaction_id"), str)
            or DRAFT_ID_PATTERN.fullmatch(manifest["transaction_id"]) is None
            or any(
                not isinstance(manifest.get(key), int) or manifest[key] < 0
                for key in (
                    "expected_dev",
                    "expected_ino",
                    "replacement_dev",
                    "replacement_ino",
                )
            )
            or any(
                not isinstance(manifest.get(key), str)
                or re.fullmatch(r"[0-9a-f]{64}", manifest[key]) is None
                for key in ("expected_sha256", "replacement_sha256")
            )
            or _canonical_bytes(manifest) != manifest_payload
            or manifest_component[1].st_nlink != 1
        ):
            raise ValueError("draft transaction manifest identity is invalid")

        transaction_id = manifest["transaction_id"]
        manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
        filename = f"{draft_id}.json"
        names = {
            "anchor": f".{draft_id}.{transaction_id}.anchor",
            "replacement": f".{draft_id}.{transaction_id}.new",
            "quarantine": f".{draft_id}.{transaction_id}.quarantine",
            "swap": f".{draft_id}.{transaction_id}.swap",
            "commit": f".{draft_id}.{transaction_id}.commit",
        }
        swap_payload = _draft_transaction_phase_payload(
            draft_id, transaction_id, "swap", manifest_sha256
        )
        commit_payload = _draft_transaction_phase_payload(
            draft_id, transaction_id, "commit", manifest_sha256
        )
        components = {
            "canonical": _open_optional_transaction_component(
                directory_fd,
                filename,
                MAX_DRAFT_BYTES,
                "draft transaction canonical draft",
            )
        }
        component_paths = {"canonical": filename}
        if components["canonical"] is not None:
            opened.append(components["canonical"][0])
        for component_name, maximum, label in (
            ("anchor", MAX_DRAFT_BYTES, "draft transaction expected anchor"),
            ("replacement", MAX_DRAFT_BYTES, "draft transaction replacement"),
            ("quarantine", MAX_DRAFT_BYTES, "draft transaction quarantine"),
            ("swap", 1024, "draft transaction swap phase"),
            ("commit", 1024, "draft transaction commit phase"),
        ):
            component, selected_name = _open_transaction_component_for_cleanup(
                directory_fd,
                names[component_name],
                maximum,
                label,
            )
            components[component_name] = component
            component_paths[component_name] = selected_name
            if component is not None:
                opened.append(component[0])
        if components["swap"] is not None and (
            components["swap"][2] != swap_payload or components["swap"][1].st_nlink != 1
        ):
            raise ValueError("draft transaction swap phase identity is invalid")
        if components["commit"] is not None and (
            components["commit"][2] != commit_payload or components["commit"][1].st_nlink != 1
        ):
            raise ValueError("draft transaction commit phase identity is invalid")
        if (
            cleanup_component is None
            and components["commit"] is not None
            and components["swap"] is None
        ):
            raise ValueError("draft transaction commit phase has no durable swap phase")

        expected_inode = (manifest["expected_dev"], manifest["expected_ino"])
        replacement_inode = (manifest["replacement_dev"], manifest["replacement_ino"])
        expected_payload = replacement_payload = None
        canonical_kind = None
        for name in ("canonical", "anchor", "replacement", "quarantine"):
            component = components[name]
            if component is None:
                continue
            inode = (component[1].st_dev, component[1].st_ino)
            digest = hashlib.sha256(component[2]).hexdigest()
            if inode == expected_inode and digest == manifest["expected_sha256"]:
                kind = "expected"
                if expected_payload is None:
                    expected_payload = component[2]
                elif expected_payload != component[2]:
                    raise ValueError("draft transaction expected bytes disagree")
            elif inode == replacement_inode and digest == manifest["replacement_sha256"]:
                kind = "replacement"
                if replacement_payload is None:
                    replacement_payload = component[2]
                elif replacement_payload != component[2]:
                    raise ValueError("draft transaction replacement bytes disagree")
            else:
                raise ValueError(f"draft transaction {name} identity is invalid")
            if name in {"anchor", "quarantine"} and kind != "expected":
                raise ValueError(f"draft transaction {name} is cross-transaction")
            if name == "replacement" and kind != "replacement":
                raise ValueError("draft transaction replacement is cross-transaction")
            if name == "canonical":
                canonical_kind = kind

        for payload, label in (
            (expected_payload, "draft transaction expected artifact"),
            (replacement_payload, "draft transaction replacement artifact"),
        ):
            if payload is not None:
                _validate_transaction_draft_payload(payload, root, draft_id, label)

        expected_links = sum(
            1
            for name in ("canonical", "anchor", "quarantine")
            if components[name] is not None
            and (components[name][1].st_dev, components[name][1].st_ino) == expected_inode
        )
        replacement_links = sum(
            1
            for name in ("canonical", "replacement")
            if components[name] is not None
            and (components[name][1].st_dev, components[name][1].st_ino) == replacement_inode
        )
        for name in ("canonical", "anchor", "replacement", "quarantine"):
            component = components[name]
            if component is None:
                continue
            inode = (component[1].st_dev, component[1].st_ino)
            expected_count = expected_links if inode == expected_inode else replacement_links
            if component[1].st_nlink != expected_count:
                raise ValueError(f"draft transaction {name} has an unbound hard-link identity")

        def remove(name: str, payload: bytes, maximum: int, label: str) -> None:
            _unlink_transaction_component(
                directory_fd,
                names[name],
                components[name],
                payload,
                maximum,
                label,
                selected_name=component_paths[name],
            )
            components[name] = None

        def remove_manifest() -> None:
            _unlink_transaction_component(
                directory_fd,
                manifest_name,
                manifest_component,
                manifest_payload,
                _DRAFT_TRANSACTION_MAX_BYTES,
                "draft transaction manifest",
                selected_name=manifest_selected_name,
            )

        def remove_cleanup() -> None:
            if cleanup_component is None:
                return
            _unlink_transaction_component(
                directory_fd,
                cleanup_name,
                cleanup_component,
                cleanup_component[2],
                _DRAFT_TRANSACTION_MAX_BYTES,
                "draft transaction cleanup phase",
                selected_name=cleanup_selected_name,
            )

        def finish_rollback() -> None:
            if components["replacement"] is not None:
                remove(
                    "replacement",
                    components["replacement"][2],
                    MAX_DRAFT_BYTES,
                    "draft transaction replacement",
                )
            if components["quarantine"] is not None:
                remove(
                    "quarantine",
                    components["quarantine"][2],
                    MAX_DRAFT_BYTES,
                    "draft transaction quarantine",
                )
            if components["anchor"] is not None:
                remove(
                    "anchor",
                    components["anchor"][2],
                    MAX_DRAFT_BYTES,
                    "draft transaction expected anchor",
                )
            if components["commit"] is not None:
                remove(
                    "commit",
                    commit_payload,
                    1024,
                    "draft transaction commit phase",
                )
            if components["swap"] is not None:
                remove(
                    "swap",
                    swap_payload,
                    1024,
                    "draft transaction swap phase",
                )
            canonical = _open_optional_transaction_component(
                directory_fd,
                filename,
                MAX_DRAFT_BYTES,
                "restored canonical draft",
            )
            if canonical is None:
                raise ValueError("draft transaction rollback lost canonical draft")
            opened.append(canonical[0])
            if (
                (canonical[1].st_dev, canonical[1].st_ino) != expected_inode
                or hashlib.sha256(canonical[2]).hexdigest() != manifest["expected_sha256"]
                or canonical[1].st_nlink != 1
            ):
                raise ValueError("draft transaction rollback identity is uncertain")
            remove_manifest()
            os.fsync(directory_fd)

        if cleanup_component is not None:
            _validate_draft_transaction_cleanup(
                root,
                draft_id,
                cleanup_component,
                components["canonical"],
                manifest=manifest,
                manifest_payload=manifest_payload,
            )
            if canonical_kind != "replacement" or any(
                components[name] is not None for name in ("replacement", "quarantine", "anchor")
            ):
                raise ValueError("draft transaction cleanup phase artifacts are inconsistent")
            if components["commit"] is not None:
                remove(
                    "commit",
                    commit_payload,
                    1024,
                    "draft transaction commit phase",
                )
            if components["swap"] is not None:
                remove(
                    "swap",
                    swap_payload,
                    1024,
                    "draft transaction swap phase",
                )
            remove_manifest()
            remove_cleanup()
            os.fsync(directory_fd)
            return

        if components["swap"] is None:
            if canonical_kind != "expected" or components["quarantine"] is not None:
                raise ValueError("draft transaction prepared phase is inconsistent")
            finish_rollback()
            return

        if canonical_kind == "expected":
            finish_rollback()
            return

        if canonical_kind is None:
            if components["replacement"] is not None:
                replacement = components["replacement"]
                current = os.stat(
                    component_paths["replacement"],
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                if not _same_inode(current, replacement[1]):
                    raise ValueError("draft transaction replacement changed before recovery")
                try:
                    os.link(
                        component_paths["replacement"],
                        filename,
                        src_dir_fd=directory_fd,
                        dst_dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                except FileExistsError as error:
                    raise ValueError(
                        "competing canonical draft preserved; recovery is uncertain"
                    ) from error
                canonical = _open_optional_transaction_component(
                    directory_fd,
                    filename,
                    MAX_DRAFT_BYTES,
                    "recovered canonical draft",
                )
                if canonical is None:
                    raise ValueError("replacement publication recovery failed")
                opened.append(canonical[0])
                if not _same_inode(canonical[1], replacement[1]) or canonical[2] != replacement[2]:
                    raise ValueError("replacement publication recovery is uncertain")
                components["canonical"] = canonical
                canonical_kind = "replacement"
                os.fsync(directory_fd)
            else:
                source_name = (
                    "quarantine"
                    if components["quarantine"] is not None
                    else "anchor"
                    if components["anchor"] is not None
                    else None
                )
                if source_name is None:
                    raise ValueError("draft transaction has no exact recovery artifact")
                source = components[source_name]
                try:
                    os.link(
                        component_paths[source_name],
                        filename,
                        src_dir_fd=directory_fd,
                        dst_dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                except FileExistsError as error:
                    raise ValueError(
                        "competing canonical draft preserved; recovery is uncertain"
                    ) from error
                restored = _open_optional_transaction_component(
                    directory_fd,
                    filename,
                    MAX_DRAFT_BYTES,
                    "restored canonical draft",
                )
                if restored is None or not _same_inode(restored[1], source[1]):
                    raise ValueError("canonical draft restoration is uncertain")
                opened.append(restored[0])
                components["canonical"] = restored
                canonical_kind = "expected"
                os.fsync(directory_fd)
                finish_rollback()
                return

        if canonical_kind != "replacement":
            raise ValueError("draft transaction canonical phase is invalid")
        canonical = components["canonical"]
        if replacement_payload is None:
            replacement_payload = canonical[2]
            _validate_transaction_draft_payload(
                replacement_payload,
                root,
                draft_id,
                "draft transaction replacement artifact",
            )
        if components["commit"] is None:
            commit_fd, commit_info = _write_private_transaction_component(
                directory_fd,
                names["commit"],
                commit_payload,
                "draft transaction commit phase",
            )
            opened.append(commit_fd)
            components["commit"] = (commit_fd, commit_info, commit_payload)
            os.fsync(directory_fd)
        for name, payload, maximum, label in (
            (
                "replacement",
                components["replacement"][2] if components["replacement"] is not None else b"",
                MAX_DRAFT_BYTES,
                "draft transaction replacement",
            ),
            (
                "quarantine",
                components["quarantine"][2] if components["quarantine"] is not None else b"",
                MAX_DRAFT_BYTES,
                "draft transaction quarantine",
            ),
            (
                "anchor",
                components["anchor"][2] if components["anchor"] is not None else b"",
                MAX_DRAFT_BYTES,
                "draft transaction expected anchor",
            ),
        ):
            if components[name] is not None:
                remove(name, payload, maximum, label)
        final_canonical = _open_optional_transaction_component(
            directory_fd,
            filename,
            MAX_DRAFT_BYTES,
            "committed canonical draft",
        )
        if final_canonical is None:
            raise ValueError("draft transaction commit lost canonical draft")
        opened.append(final_canonical[0])
        if (
            (final_canonical[1].st_dev, final_canonical[1].st_ino) != replacement_inode
            or hashlib.sha256(final_canonical[2]).hexdigest() != manifest["replacement_sha256"]
            or final_canonical[1].st_nlink != 1
        ):
            raise ValueError("draft transaction committed identity is uncertain")
        cleanup_payload = _draft_transaction_cleanup_payload(
            root, draft_id, manifest, manifest_payload
        )
        cleanup_fd, cleanup_info = _write_private_transaction_component(
            directory_fd,
            cleanup_name,
            cleanup_payload,
            "draft transaction cleanup phase",
        )
        opened.append(cleanup_fd)
        cleanup_component = (cleanup_fd, cleanup_info, cleanup_payload)
        cleanup_selected_name = cleanup_name
        os.fsync(directory_fd)
        remove("commit", commit_payload, 1024, "draft transaction commit phase")
        remove("swap", swap_payload, 1024, "draft transaction swap phase")
        remove_manifest()
        remove_cleanup()
        os.fsync(directory_fd)
    finally:
        for descriptor in reversed(opened):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _recover_private_draft_transaction(root: Path, draft_id: str) -> None:
    directory_fd = _private_draft_directory_fd(root)
    try:
        with _draft_transaction_lock(directory_fd):
            _recover_private_draft_transaction_at(root, draft_id, directory_fd)
    finally:
        os.close(directory_fd)


def _cas_replace_private_draft(
    root: Path,
    draft_id: str,
    expected: bytes,
    replacement: bytes,
) -> None:
    directory_fd = _private_draft_directory_fd(root)
    token = secrets.token_hex(16)
    filename = f"{draft_id}.json"
    temporary_name = f".{draft_id}.{token}.new"
    anchor_name = f".{draft_id}.{token}.anchor"
    quarantine_name = f".{draft_id}.{token}.quarantine"
    manifest_name = f".{draft_id}.transaction"
    swap_name = f".{draft_id}.{token}.swap"
    current_fd = temporary_fd = anchor_fd = quarantine_fd = None
    manifest_fd = swap_fd = None
    anchor_info = None
    transaction_durable = False
    try:
        with _draft_transaction_lock(directory_fd):
            _recover_private_draft_transaction_at(root, draft_id, directory_fd)
            read_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            current_fd = os.open(filename, read_flags, dir_fd=directory_fd)
            current_info = os.fstat(current_fd)
            expected_payload = expected
            replacement_payload = replacement
            if (
                not stat.S_ISREG(current_info.st_mode)
                or stat.S_IMODE(current_info.st_mode) != 0o600
                or current_info.st_nlink != 1
                or _read_bounded_descriptor(current_fd, MAX_DRAFT_BYTES, "trace transaction draft")
                != expected_payload
            ):
                raise ValueError("trace transaction changed before receipt binding")
            _validate_transaction_draft_payload(
                expected_payload, root, draft_id, "trace transaction expected"
            )
            _validate_transaction_draft_payload(
                replacement_payload,
                root,
                draft_id,
                "trace transaction replacement",
            )

            temporary_fd, temporary_info = _write_private_transaction_component(
                directory_fd,
                temporary_name,
                replacement_payload,
                "draft transaction replacement",
            )
            os.link(
                filename,
                anchor_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            anchor = _open_optional_transaction_component(
                directory_fd,
                anchor_name,
                MAX_DRAFT_BYTES,
                "draft transaction expected anchor",
            )
            if (
                anchor is None
                or not _same_inode(anchor[1], current_info)
                or anchor[2] != expected_payload
            ):
                raise ValueError("trace transaction changed before receipt binding")
            anchor_fd, anchor_info = anchor[0], anchor[1]
            manifest = {
                "schema_version": 1,
                "draft_id": draft_id,
                "repo_root_sha256": hashlib.sha256(str(root).encode("utf-8")).hexdigest(),
                "transaction_id": token,
                "expected_sha256": hashlib.sha256(expected_payload).hexdigest(),
                "expected_dev": current_info.st_dev,
                "expected_ino": current_info.st_ino,
                "replacement_sha256": hashlib.sha256(replacement_payload).hexdigest(),
                "replacement_dev": temporary_info.st_dev,
                "replacement_ino": temporary_info.st_ino,
            }
            manifest_payload = _canonical_bytes(manifest)
            manifest_fd, _ = _write_private_transaction_component(
                directory_fd,
                manifest_name,
                manifest_payload,
                "draft transaction manifest",
            )
            os.fsync(directory_fd)
            transaction_durable = True
            swap_payload = _draft_transaction_phase_payload(
                draft_id,
                token,
                "swap",
                hashlib.sha256(manifest_payload).hexdigest(),
            )
            swap_fd, _ = _write_private_transaction_component(
                directory_fd,
                swap_name,
                swap_payload,
                "draft transaction swap phase",
            )
            os.fsync(directory_fd)

            current_path_info = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
            if (
                not _same_inode(current_path_info, current_info)
                or _read_bounded_descriptor(current_fd, MAX_DRAFT_BYTES, "trace transaction draft")
                != expected_payload
            ):
                raise ValueError("trace transaction changed before receipt binding")
            _rename_noreplace(directory_fd, filename, quarantine_name)
            quarantine_fd = os.open(quarantine_name, read_flags, dir_fd=directory_fd)
            quarantine_info = os.fstat(quarantine_fd)
            if (
                not _same_inode(quarantine_info, current_info)
                or _read_bounded_descriptor(
                    quarantine_fd, MAX_DRAFT_BYTES, "trace transaction draft"
                )
                != expected_payload
            ):
                raise ValueError("trace transaction changed after durable quarantine")
            replacement_path_info = os.stat(
                temporary_name, dir_fd=directory_fd, follow_symlinks=False
            )
            if (
                not _same_inode(replacement_path_info, temporary_info)
                or _read_bounded_descriptor(
                    temporary_fd,
                    MAX_DRAFT_BYTES,
                    "draft transaction replacement",
                )
                != replacement_payload
            ):
                raise ValueError("draft transaction replacement changed")
            try:
                os.link(
                    temporary_name,
                    filename,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except FileExistsError as error:
                raise ValueError(
                    "competing trace transaction preserved; recovery is uncertain"
                ) from error
            published = _open_optional_transaction_component(
                directory_fd,
                filename,
                MAX_DRAFT_BYTES,
                "published transaction draft",
            )
            if (
                published is None
                or not _same_inode(published[1], temporary_info)
                or published[2] != replacement_payload
            ):
                raise ValueError("published transaction draft identity is uncertain")
            os.close(published[0])
            os.fsync(directory_fd)
            _recover_private_draft_transaction_at(root, draft_id, directory_fd)
            transaction_durable = False
    except OSError as error:
        raise ValueError(f"cannot compare-and-swap trace transaction: {error}") from error
    finally:
        cleanup_error = None
        if not transaction_durable:
            for name, descriptor, metadata, payload, label in (
                (
                    temporary_name,
                    temporary_fd,
                    temporary_info if temporary_fd is not None else None,
                    replacement_payload if temporary_fd is not None else b"",
                    "draft transaction replacement",
                ),
                (
                    anchor_name,
                    anchor_fd,
                    anchor_info,
                    expected_payload if anchor_fd is not None else b"",
                    "draft transaction expected anchor",
                ),
            ):
                if descriptor is None or metadata is None:
                    continue
                selected_name = name
                try:
                    os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except FileNotFoundError:
                    selected_name = _transaction_removing_name(name)
                    try:
                        os.stat(
                            selected_name,
                            dir_fd=directory_fd,
                            follow_symlinks=False,
                        )
                    except FileNotFoundError:
                        continue
                try:
                    _unlink_transaction_component(
                        directory_fd,
                        name,
                        (descriptor, metadata, payload),
                        payload,
                        MAX_DRAFT_BYTES,
                        label,
                        selected_name=selected_name,
                    )
                except (OSError, ValueError) as failure:
                    cleanup_error = failure
                    break
        for descriptor in (
            swap_fd,
            manifest_fd,
            quarantine_fd,
            anchor_fd,
            temporary_fd,
            current_fd,
        ):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        os.close(directory_fd)
        if cleanup_error is not None:
            raise ValueError(
                f"pre-manifest draft transaction cleanup is uncertain: {cleanup_error}"
            )


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
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=".draft-", delete=False
        ) as stream:
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
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        locked = True
                        break
                    except BlockingIOError:
                        time.sleep(min(0.01, deadline.remaining()))
        if deadline is not None and deadline.expired():
            raise ValueError("graph trace deadline exhausted waiting for controller lock")
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
    graph_receipt: Mapping[str, object] | None = None,
    analysis_sha256: str | None = None,
    context_identity: Mapping[str, object] | None = None,
) -> None:
    revision_value = _int_value(draft["revision"])
    report_id = str(draft["report_id"])
    state_sha256 = hashlib.sha256(state_bytes).hexdigest()
    metadata = {
        "schema_version": 1,
        "draft_id": draft["draft_id"],
        "report_id": draft["report_id"],
        "revision": draft["revision"],
        "state_sha256": state_sha256,
        "key_map": key_map,
    }
    if graph_receipt is not None:
        metadata["graph_receipt"] = dict(graph_receipt)
    if (analysis_sha256 is None) != (context_identity is None):
        raise ValueError("controller completion identity must be complete")
    if analysis_sha256 is not None and context_identity is not None:
        if (
            not isinstance(analysis_sha256, str)
            or _SHA256_PATTERN.fullmatch(analysis_sha256) is None
            or not _valid_context_identity(dict(context_identity))
        ):
            raise ValueError("controller completion identity is invalid")
        metadata["analysis_sha256"] = analysis_sha256
        metadata["context_identity"] = dict(context_identity)
    try:
        payload = _canonical_bytes(metadata)
    except (RecursionError, TypeError, ValueError) as error:
        raise ValueError("controller lineage metadata is invalid") from error
    _validate_controller_metadata_bytes(
        payload,
        report_id=report_id,
        revision=revision_value,
        state_sha256=state_sha256,
    )
    path = _controller_metadata_path(report_id, revision_value, root)
    directory_fd = _controller_metadata_directory_fd(path)
    name = path.name
    temporary = f".{name}.{draft['draft_id']}.tmp"
    temporary_created = False
    descriptor = None
    try:
        try:
            os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
            existing_bytes = None
        except OSError as error:
            raise ValueError("controller lineage metadata is unsafe") from error
        else:
            existing, existing_bytes = _load_or_recover_controller_metadata(
                directory_fd,
                name,
                report_id=report_id,
                revision=revision_value,
                state_sha256=None,
            )
            if existing_bytes == payload:
                _fsync_controller_metadata_directory(directory_fd)
                return
            same_draft = existing.get("draft_id") == draft["draft_id"]
            artifacts_exist = any(
                (path.parent / f"revision-{revision_value:04d}.{suffix}").exists()
                for suffix in ("json", "md")
            )
            current = report_store.load_current(root, report_id)
            if (
                not same_draft
                or artifacts_exist
                or (current is not None and current.revision >= revision_value)
            ):
                raise ValueError("controller revision belongs to another draft")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        temporary_created = True
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        if existing is not None:
            os.replace(
                temporary,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            temporary_created = False
            _fsync_controller_metadata_directory(directory_fd)
        else:
            try:
                os.link(
                    temporary,
                    name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                _unlink_controller_metadata_temporary(directory_fd, temporary)
                temporary_created = False
                _fsync_controller_metadata_directory(directory_fd)
                raced, raced_bytes = _load_or_recover_controller_metadata(
                    directory_fd,
                    name,
                    report_id=report_id,
                    revision=revision_value,
                    state_sha256=state_sha256,
                )
                if raced_bytes != payload or raced.get("draft_id") != draft["draft_id"]:
                    raise ValueError("controller revision belongs to another draft") from None
            else:
                _unlink_controller_metadata_temporary(directory_fd, temporary)
                temporary_created = False
                _fsync_controller_metadata_directory(directory_fd)
        verified, verified_bytes = _load_or_recover_controller_metadata(
            directory_fd,
            name,
            report_id=report_id,
            revision=revision_value,
            state_sha256=state_sha256,
        )
        if verified_bytes != payload or verified.get("draft_id") != draft["draft_id"]:
            raise ValueError("controller lineage metadata publication could not be verified")
    except (OSError, ValueError) as error:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        if temporary_created:
            _unlink_controller_metadata_temporary(directory_fd, temporary)
            temporary_created = False
            _fsync_controller_metadata_directory(directory_fd)
        if isinstance(error, ValueError):
            raise
        raise ValueError(f"cannot write controller lineage: {error}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_fd)


root_path = _root
write_private_draft = _write_private_draft
controller_metadata_path = _controller_metadata_path
load_controller_metadata = _load_controller_metadata
load_controller_completion_metadata = _load_controller_completion_metadata
draft_path = _draft_path
load_private_draft = load_draft
replace_private_draft = _replace_private_draft
recover_private_draft_transaction = _recover_private_draft_transaction
cas_replace_private_draft = _cas_replace_private_draft
consume_draft = _consume
report_lock = _report_lock
write_controller_metadata = _write_controller_metadata
