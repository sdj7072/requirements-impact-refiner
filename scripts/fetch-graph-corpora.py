#!/usr/bin/env python3
"""Fetch and verify the exact licensed graph corpora outside the repository."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import BinaryIO, cast
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "evals" / "corpora" / "catalog.json"
MAX_CATALOG_BYTES = 64 * 1024
MAX_LICENSE_BYTES = 64 * 1024
MAX_GIT_STDOUT_BYTES = 16 * 1024 * 1024
MAX_GIT_STDERR_BYTES = 256 * 1024
MAX_CHECKOUT_ENTRIES = 20_000
MAX_CHECKOUT_FILE_BYTES = 8 * 1024 * 1024
MAX_CHECKOUT_TOTAL_BYTES = 64 * 1024 * 1024
GIT_LOCAL_TIMEOUT_SECONDS = 10.0
GIT_FETCH_TIMEOUT_SECONDS = 60.0
_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_CORPUS_KEYS = frozenset(
    {
        "id",
        "checkout",
        "repository",
        "commit",
        "license",
        "license_path",
        "license_sha256",
        "preserved_license",
        "provenance",
    }
)
_PROVENANCE_KEYS = frozenset({"repository", "commit", "license_path"})
_ALLOWED_LICENSES = frozenset({"Apache-2.0", "BSD-3-Clause", "MIT"})
_ALLOWED_TREE_MODES = frozenset({"100644", "100755"})
_SAFE_GIT_OPTIONS = (
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.attributesFile=/dev/null",
    "-c",
    "core.excludesFile=/dev/null",
    "-c",
    "core.filemode=true",
    "-c",
    "status.showUntrackedFiles=all",
    "-c",
    "submodule.recurse=false",
    "-c",
    "diff.ignoreSubmodules=none",
)
_OFFICIAL_CORPORA = (
    (
        "pallets-click",
        "https://github.com/pallets/click.git",
        "68e7ea7228ca144c52e4d1d282cc09da59f7771f",
        "BSD-3-Clause",
    ),
    (
        "sindresorhus-slugify",
        "https://github.com/sindresorhus/slugify.git",
        "7c318bd1aa4b4affab29761f15a9604323fe2a3b",
        "MIT",
    ),
)


class CorpusError(RuntimeError):
    """A corpus failed a provenance, process, or filesystem boundary."""


@dataclass(frozen=True)
class CorpusSpec:
    id: str
    checkout: str
    repository: str
    commit: str
    license: str
    license_path: str
    license_sha256: str
    preserved_license: Path
    license_bytes: bytes


@dataclass
class DestinationHandle:
    path: Path
    parent_path: Path
    name: str
    parent_fd: int
    child_fd: int
    parent_identity: tuple[int, int]
    child_identity: tuple[int, int]
    closed: bool = False


def _contains(parent: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath((str(parent), str(candidate))) == str(parent)
    except ValueError:
        return False


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def _safe_relative(value: object, label: str, *, single_component: bool = False) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise CorpusError(f"{label} must be a safe relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CorpusError(f"{label} must be a safe relative POSIX path")
    if single_component and len(path.parts) != 1:
        raise CorpusError(f"{label} must be one path component")
    return path.as_posix()


def _read_regular(path: Path, maximum: int, label: str) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise CorpusError(f"{label} is unavailable") from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size > maximum
    ):
        raise CorpusError(f"{label} must be one bounded regular non-symlink file")
    descriptor = None
    try:
        descriptor = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(metadata):
            raise CorpusError(f"{label} changed while opening")
        payload = bytearray()
        while len(payload) <= maximum:
            chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(descriptor)
        if len(payload) > maximum:
            raise CorpusError(f"{label} exceeds the byte bound")
        if _identity(after) != _identity(opened) or _identity(path.lstat()) != _identity(opened):
            raise CorpusError(f"{label} changed during read")
        return bytes(payload)
    except CorpusError:
        raise
    except OSError as error:
        raise CorpusError(f"{label} cannot be read safely") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _validated_repository(value: object, *, allow_local: bool) -> str:
    if not isinstance(value, str) or len(value) > 2048 or "\x00" in value:
        raise CorpusError("corpus repository URL is invalid")
    parsed = urlsplit(value)
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise CorpusError("corpus repository URL is invalid")
    if parsed.scheme == "https":
        if parsed.netloc != "github.com" or not parsed.path.endswith(".git"):
            raise CorpusError("corpus repository must be an exact GitHub HTTPS URL")
    elif not allow_local or parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise CorpusError("local corpus repositories are disabled")
    return value


def load_catalog(
    path: Path = CATALOG_PATH,
    *,
    allow_local_repositories: bool = False,
) -> tuple[CorpusSpec, ...]:
    selected = Path(path).resolve(strict=True)
    raw = _read_regular(selected, MAX_CATALOG_BYTES, "corpus catalog")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise CorpusError("corpus catalog is malformed") from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "corpora"}
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("corpora"), list)
        or not payload["corpora"]
        or len(payload["corpora"]) > 16
    ):
        raise CorpusError("corpus catalog envelope is invalid")
    rows = []
    seen_ids = set()
    seen_checkouts = set()
    for raw_row in payload["corpora"]:
        if not isinstance(raw_row, dict) or set(raw_row) != _CORPUS_KEYS:
            raise CorpusError("corpus catalog row has unknown or missing fields")
        corpus_id = _safe_relative(raw_row["id"], "corpus id", single_component=True)
        checkout = _safe_relative(raw_row["checkout"], "corpus checkout", single_component=True)
        if corpus_id in seen_ids or checkout in seen_checkouts:
            raise CorpusError("corpus catalog identifiers must be unique")
        seen_ids.add(corpus_id)
        seen_checkouts.add(checkout)
        repository = _validated_repository(
            raw_row["repository"], allow_local=allow_local_repositories
        )
        commit = raw_row["commit"]
        digest = raw_row["license_sha256"]
        license_name = raw_row["license"]
        if not isinstance(commit, str) or _HEX40.fullmatch(commit) is None:
            raise CorpusError("corpus commit must be a full lowercase Git SHA-1")
        if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
            raise CorpusError("corpus license digest must be lowercase SHA-256")
        if license_name not in _ALLOWED_LICENSES:
            raise CorpusError("corpus license is outside the approved SPDX allowlist")
        license_path = _safe_relative(raw_row["license_path"], "corpus license path")
        preserved_relative = _safe_relative(
            raw_row["preserved_license"], "preserved corpus license"
        )
        provenance = raw_row["provenance"]
        if (
            not isinstance(provenance, dict)
            or set(provenance) != _PROVENANCE_KEYS
            or provenance
            != {
                "repository": repository,
                "commit": commit,
                "license_path": license_path,
            }
        ):
            raise CorpusError("corpus license provenance does not match the pin")
        preserved = selected.parent.joinpath(*PurePosixPath(preserved_relative).parts)
        if not _contains(selected.parent, preserved.resolve(strict=False)):
            raise CorpusError("preserved corpus license escapes the catalog directory")
        license_bytes = _read_regular(preserved, MAX_LICENSE_BYTES, "preserved corpus license")
        if hashlib.sha256(license_bytes).hexdigest() != digest:
            raise CorpusError("preserved corpus license digest does not match the catalog")
        rows.append(
            CorpusSpec(
                corpus_id,
                checkout,
                repository,
                commit,
                cast(str, license_name),
                license_path,
                digest,
                preserved,
                license_bytes,
            )
        )
    result = tuple(rows)
    if (
        selected == CATALOG_PATH.resolve()
        and tuple((row.id, row.repository, row.commit, row.license) for row in result)
        != _OFFICIAL_CORPORA
    ):
        raise CorpusError("checked-in corpus catalog does not match the approved pins")
    return result


def _lexical_ancestors(path: Path) -> tuple[Path, ...]:
    current = Path(os.path.abspath(path))
    rows = []
    while True:
        rows.append(current)
        if current == current.parent:
            return tuple(rows)
        current = current.parent


def _validate_destination_boundary(
    destination: Path,
    repository_root: Path,
    *,
    must_exist: bool,
) -> Path:
    raw_selected = Path(destination)
    if not raw_selected.is_absolute() or raw_selected.name in {"", ".", ".."}:
        raise CorpusError("corpus destination must be an absolute path")
    root = Path(repository_root).resolve(strict=True)
    for ancestor in _lexical_ancestors(raw_selected.parent):
        if not os.path.lexists(ancestor):
            continue
        try:
            metadata = ancestor.lstat()
        except OSError as error:
            raise CorpusError("corpus destination parent is unavailable") from error
        if stat.S_ISLNK(metadata.st_mode):
            portable_tmp_alias = ancestor == Path(os.sep) / "tmp"
            if portable_tmp_alias:
                continue
            raise CorpusError("corpus destination parent must not contain symlinks")
        if not stat.S_ISDIR(metadata.st_mode):
            raise CorpusError("corpus destination parent must contain only directories")
    try:
        canonical_parent = raw_selected.parent.resolve(strict=True)
    except OSError as error:
        raise CorpusError("corpus destination parent is unavailable") from error
    selected = canonical_parent / raw_selected.name
    if _contains(root, selected):
        raise CorpusError("corpus destination must remain outside the repository")
    for ancestor in _lexical_ancestors(canonical_parent):
        if not os.path.lexists(ancestor):
            continue
        try:
            metadata = ancestor.lstat()
        except OSError as error:
            raise CorpusError("corpus destination parent is unavailable") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise CorpusError("corpus destination parent must not contain symlinks")
        if not stat.S_ISDIR(metadata.st_mode):
            raise CorpusError("corpus destination parent must contain only directories")
        if os.path.lexists(ancestor / ".git"):
            raise CorpusError("corpus destination must not be inside any Git repository")
    exists = os.path.lexists(selected)
    if must_exist and not exists:
        raise CorpusError("corpus destination is missing")
    if not must_exist and exists:
        raise CorpusError("corpus destination must not already exist")
    if must_exist:
        metadata = selected.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise CorpusError("corpus destination must be a regular non-symlink directory")
        if os.path.lexists(selected / ".git"):
            raise CorpusError("corpus destination itself must not be a Git repository")
    return selected


def validate_destination(
    destination: Path,
    repository_root: Path = ROOT,
) -> Path:
    """Return a canonical absent destination outside every Git repository."""
    return _validate_destination_boundary(
        destination,
        repository_root,
        must_exist=False,
    )


def _directory_flags() -> int:
    directory = getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not directory or not nofollow:
        raise CorpusError("descriptor-owned corpus directories are unsupported")
    return os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0)


def _same_directory(metadata: os.stat_result, identity: tuple[int, int]) -> bool:
    return stat.S_ISDIR(metadata.st_mode) and (metadata.st_dev, metadata.st_ino) == identity


def _fd_path(descriptor: int) -> Path:
    for root in (Path(os.sep) / "dev" / "fd", Path(os.sep) / "proc" / "self" / "fd"):
        if root.is_dir():
            return root / str(descriptor)
    raise CorpusError("descriptor filesystem paths are unavailable")


def _open_destination_handle(
    destination: Path,
    repository_root: Path,
    *,
    create: bool,
) -> DestinationHandle:
    selected = (
        validate_destination(destination, repository_root)
        if create
        else _validate_destination_boundary(destination, repository_root, must_exist=True)
    )
    parent_path = selected.parent
    try:
        parent_metadata = parent_path.lstat()
        parent_fd = os.open(str(parent_path), _directory_flags())
    except OSError as error:
        raise CorpusError("corpus destination parent cannot be opened safely") from error
    child_fd = None
    created = False
    try:
        opened_parent = os.fstat(parent_fd)
        parent_identity = (opened_parent.st_dev, opened_parent.st_ino)
        if not _same_directory(parent_metadata, parent_identity):
            raise CorpusError("corpus destination parent identity changed while opening")
        if create:
            os.mkdir(selected.name, mode=0o700, dir_fd=parent_fd)
            created = True
        child_metadata = os.stat(selected.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(child_metadata.st_mode) or stat.S_ISLNK(child_metadata.st_mode):
            raise CorpusError("corpus destination must be a real directory")
        child_fd = os.open(selected.name, _directory_flags(), dir_fd=parent_fd)
        if create:
            os.fchmod(child_fd, 0o700)
        opened_child = os.fstat(child_fd)
        child_identity = (opened_child.st_dev, opened_child.st_ino)
        named_child = os.stat(selected.name, dir_fd=parent_fd, follow_symlinks=False)
        if not (
            _same_directory(child_metadata, child_identity)
            and _same_directory(named_child, child_identity)
            and stat.S_IMODE(opened_child.st_mode) == 0o700
        ):
            raise CorpusError("corpus destination identity changed while opening")
        return DestinationHandle(
            selected,
            parent_path,
            selected.name,
            parent_fd,
            child_fd,
            parent_identity,
            child_identity,
        )
    except Exception as error:
        if child_fd is not None:
            os.close(child_fd)
        if created:
            try:
                os.rmdir(selected.name, dir_fd=parent_fd)
            except OSError:
                os.close(parent_fd)
                raise CorpusError("failed corpus destination cannot be removed safely") from error
        os.close(parent_fd)
        if isinstance(error, CorpusError):
            raise
        raise CorpusError("corpus destination cannot be opened safely") from error


def _create_destination(destination: Path, repository_root: Path = ROOT) -> DestinationHandle:
    return _open_destination_handle(destination, repository_root, create=True)


def _open_destination(destination: Path, repository_root: Path = ROOT) -> DestinationHandle:
    return _open_destination_handle(destination, repository_root, create=False)


def _verify_destination_handle(handle: DestinationHandle) -> None:
    if handle.closed:
        raise CorpusError("corpus destination descriptor is closed")
    try:
        opened_parent = os.fstat(handle.parent_fd)
        opened_child = os.fstat(handle.child_fd)
        named_parent = handle.parent_path.lstat()
        named_child = os.stat(handle.name, dir_fd=handle.parent_fd, follow_symlinks=False)
    except OSError as error:
        raise CorpusError("corpus destination identity cannot be verified") from error
    if not (
        _same_directory(opened_parent, handle.parent_identity)
        and _same_directory(named_parent, handle.parent_identity)
        and _same_directory(opened_child, handle.child_identity)
        and _same_directory(named_child, handle.child_identity)
    ):
        raise CorpusError("corpus destination identity changed")


def _close_destination(handle: DestinationHandle) -> None:
    if handle.closed:
        return
    handle.closed = True
    os.close(handle.child_fd)
    os.close(handle.parent_fd)


def _remove_tree_fd(directory_fd: int) -> None:
    opened_directory = os.fstat(directory_fd)
    if not stat.S_ISDIR(opened_directory.st_mode):
        raise CorpusError("cleanup descriptor is not a directory")
    os.fchmod(directory_fd, 0o700)
    try:
        with os.scandir(directory_fd) as entries:
            names = sorted(entry.name for entry in entries)
    except OSError as error:
        raise CorpusError("corpus cleanup cannot enumerate held directory") from error
    for name in names:
        if not isinstance(name, str) or not name or name in {".", ".."} or "/" in name:
            raise CorpusError("corpus cleanup entry name is unsafe")
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = os.open(name, _directory_flags(), dir_fd=directory_fd)
            try:
                child_identity = (metadata.st_dev, metadata.st_ino)
                if not _same_directory(os.fstat(child_fd), child_identity):
                    raise CorpusError("corpus cleanup child changed while opening")
                _remove_tree_fd(child_fd)
                named_after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if not _same_directory(named_after, child_identity):
                    raise CorpusError("corpus cleanup child changed during removal")
                os.rmdir(name, dir_fd=directory_fd)
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            os.unlink(name, dir_fd=directory_fd)
        else:
            raise CorpusError("corpus cleanup encountered an unsupported entry")


def _locate_held_child(handle: DestinationHandle) -> str:
    try:
        with os.scandir(handle.parent_fd) as entries:
            names = sorted(entry.name for entry in entries)
    except OSError as error:
        raise CorpusError("corpus cleanup cannot enumerate held parent") from error
    matches = []
    for name in names:
        metadata = os.stat(name, dir_fd=handle.parent_fd, follow_symlinks=False)
        if _same_directory(metadata, handle.child_identity):
            matches.append(name)
    if len(matches) != 1:
        raise CorpusError("corpus cleanup cannot locate the held destination inode")
    return matches[0]


def _cleanup_destination(
    handle: DestinationHandle,
    *,
    before_root_remove: Callable[[DestinationHandle, str], object] | None = None,
) -> None:
    if handle.closed:
        raise CorpusError("corpus destination descriptor is closed")
    cleanup_error = None
    try:
        if not _same_directory(os.fstat(handle.child_fd), handle.child_identity):
            raise CorpusError("corpus cleanup destination identity changed")
        _remove_tree_fd(handle.child_fd)
        retained_name = _locate_held_child(handle)
        if before_root_remove is not None:
            before_root_remove(handle, retained_name)
        retained_name = _locate_held_child(handle)
        named = os.stat(retained_name, dir_fd=handle.parent_fd, follow_symlinks=False)
        if not _same_directory(named, handle.child_identity):
            raise CorpusError("corpus cleanup destination changed before rmdir")
        os.rmdir(retained_name, dir_fd=handle.parent_fd)
    except Exception as error:
        cleanup_error = error
    finally:
        _close_destination(handle)
    if cleanup_error is not None:
        if isinstance(cleanup_error, CorpusError):
            raise cleanup_error
        raise CorpusError("corpus destination cleanup failed") from cleanup_error


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        try:
            process.kill()
        except ProcessLookupError:
            pass


def run_bounded(
    command: Sequence[str],
    cwd: Path,
    *,
    timeout: float,
    stdout_limit: int,
    stderr_limit: int,
    environment: Mapping[str, str] | None = None,
    pass_fds: Sequence[int] = (),
) -> tuple[bytes, bytes]:
    """Run one no-shell subprocess with time and byte bounds."""
    if (
        not isinstance(command, (tuple, list))
        or not command
        or any(not isinstance(item, str) or not item or "\x00" in item for item in command)
    ):
        raise CorpusError("bounded command arguments are invalid")
    if timeout <= 0 or stdout_limit < 0 or stderr_limit < 0:
        raise CorpusError("bounded command limits are invalid")
    selected_cwd = Path(cwd)
    cwd_descriptor = None
    if pass_fds and selected_cwd.name.isdigit() and int(selected_cwd.name) in pass_fds:
        candidate_fd = int(selected_cwd.name)
        if stat.S_ISDIR(os.fstat(candidate_fd).st_mode):
            cwd_descriptor = candidate_fd
    if cwd_descriptor is None and (
        not selected_cwd.is_dir() or (selected_cwd.is_symlink() and not pass_fds)
    ):
        raise CorpusError("bounded command working directory is unsafe")
    process_environment = (
        dict(environment)
        if environment is not None
        else {"LC_ALL": "C", "PATH": os.defpath, "TMPDIR": tempfile.gettempdir()}
    )
    try:

        def enter_held_directory() -> None:
            assert cwd_descriptor is not None
            os.fchdir(cwd_descriptor)

        process = subprocess.Popen(
            tuple(command),
            cwd=None if cwd_descriptor is not None else str(selected_cwd),
            env=process_environment,
            shell=False,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            pass_fds=tuple(pass_fds),
            preexec_fn=enter_held_directory if cwd_descriptor is not None else None,
        )
    except OSError as error:
        raise CorpusError("bounded command could not start") from error
    assert process.stdout is not None and process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, stdout_limit)
    selector.register(process.stderr, selectors.EVENT_READ, stderr_limit)
    buffers = {process.stdout: bytearray(), process.stderr: bytearray()}
    exceeded = False
    timed_out = False
    expires = time.monotonic() + timeout
    try:
        while selector.get_map():
            remaining = expires - time.monotonic()
            if remaining <= 0:
                timed_out = True
                _terminate_process_group(process)
                break
            for key, _ in selector.select(min(remaining, 0.05)):
                stream = cast(BinaryIO, key.fileobj)
                chunk = os.read(stream.fileno(), 64 * 1024)
                if not chunk:
                    selector.unregister(stream)
                    continue
                buffer = buffers[stream]
                room = max(0, key.data - len(buffer))
                buffer.extend(chunk[:room])
                if len(chunk) > room:
                    exceeded = True
                    _terminate_process_group(process)
                    break
            if exceeded:
                break
        try:
            returncode = process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            _terminate_process_group(process)
            process.wait(timeout=1)
            timed_out = True
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
    if timed_out:
        raise CorpusError("bounded command timed out")
    if exceeded:
        raise CorpusError("bounded command exceeded its output bound")
    stdout = bytes(buffers[process.stdout])
    stderr = bytes(buffers[process.stderr])
    if returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()[:512]
        raise CorpusError("bounded command failed" + (f": {detail}" if detail else ""))
    return stdout, stderr


def _git_environment(git: Path, *, allow_local: bool) -> dict[str, str]:
    return {
        "GIT_ALLOW_PROTOCOL": "file" if allow_local else "https",
        "GIT_ASKPASS": "/usr/bin/false",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "PATH": os.pathsep.join((str(git.parent), "/usr/bin", "/bin")),
        "TMPDIR": tempfile.gettempdir(),
    }


def _git(
    git: Path,
    arguments: Sequence[str],
    cwd: Path,
    *,
    allow_local: bool,
    timeout: float = GIT_LOCAL_TIMEOUT_SECONDS,
    pass_fds: Sequence[int] = (),
) -> bytes:
    retained_fds = tuple(pass_fds)
    cwd_path = Path(cwd)
    if (
        not retained_fds
        and cwd_path.name.isdigit()
        and cwd_path.parent
        in {
            Path(os.sep) / "dev" / "fd",
            Path(os.sep) / "proc" / "self" / "fd",
        }
    ):
        retained_fds = (int(cwd_path.name),)
    stdout, _ = run_bounded(
        (str(git), *_SAFE_GIT_OPTIONS, *tuple(arguments)),
        cwd,
        timeout=timeout,
        stdout_limit=MAX_GIT_STDOUT_BYTES,
        stderr_limit=MAX_GIT_STDERR_BYTES,
        environment=_git_environment(git, allow_local=allow_local),
        pass_fds=retained_fds,
    )
    return stdout


def _find_git(git_executable: Path | None) -> Path:
    selected = str(git_executable) if git_executable is not None else shutil.which("git")
    if selected is None:
        raise CorpusError("git executable is unavailable")
    path = Path(selected)
    try:
        metadata = path.lstat()
    except OSError as error:
        raise CorpusError("git executable is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise CorpusError("git executable must be a regular non-symlink file")
    if metadata.st_mode & 0o111 == 0:
        raise CorpusError("git executable is not executable")
    return path.resolve(strict=True)


def _assert_symlink_free(root: Path) -> None:
    count = 0
    try:
        for current, directories, files in os.walk(root, topdown=True, followlinks=False):
            for name in (*directories, *files):
                count += 1
                if count > MAX_CHECKOUT_ENTRIES:
                    raise CorpusError("corpus checkout exceeds the entry bound")
                path = Path(current) / name
                if path.is_symlink():
                    raise CorpusError("corpus checkout contains a symlink")
    except OSError as error:
        raise CorpusError("corpus checkout cannot be traversed safely") from error


def _nul_records(payload: bytes, label: str) -> tuple[bytes, ...]:
    records = payload.split(b"\x00")
    if not records or records[-1] != b"":
        raise CorpusError(f"{label} output is malformed")
    return tuple(records[:-1])


def _decode_tree_path(payload: bytes, label: str) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CorpusError(f"{label} path is not UTF-8") from error
    return _safe_relative(text, f"{label} path")


def _head_tree(
    git: Path,
    checkout: Path,
    *,
    allow_local: bool,
) -> dict[str, tuple[str, str]]:
    output = _git(
        git,
        ("ls-tree", "-rz", "--full-tree", "HEAD"),
        checkout,
        allow_local=allow_local,
    )
    tree: dict[str, tuple[str, str]] = {}
    for record in _nul_records(output, "HEAD tree"):
        metadata, separator, raw_path = record.partition(b"\t")
        fields = metadata.split(b" ")
        if not separator or len(fields) != 3:
            raise CorpusError("HEAD tree output is malformed")
        mode, object_type, raw_oid = fields
        path = _decode_tree_path(raw_path, "HEAD tree")
        try:
            mode_text = mode.decode("ascii")
            object_type_text = object_type.decode("ascii")
            oid = raw_oid.decode("ascii")
        except UnicodeDecodeError as error:
            raise CorpusError("HEAD tree metadata is malformed") from error
        if mode_text not in _ALLOWED_TREE_MODES or object_type_text != "blob":
            raise CorpusError(f"HEAD tree mode is not allowed for {path}")
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid):
            raise CorpusError("HEAD tree object identity is invalid")
        if path in tree:
            raise CorpusError("HEAD tree contains duplicate paths")
        tree[path] = (mode_text, oid)
        if len(tree) > MAX_CHECKOUT_ENTRIES:
            raise CorpusError("HEAD tree exceeds the entry bound")
    if not tree:
        raise CorpusError("HEAD tree must not be empty")
    return tree


def _verify_index(
    git: Path,
    checkout: Path,
    tree: Mapping[str, tuple[str, str]],
    *,
    allow_local: bool,
) -> None:
    stage_output = _git(
        git,
        ("ls-files", "--stage", "-z"),
        checkout,
        allow_local=allow_local,
    )
    index: dict[str, tuple[str, str]] = {}
    for record in _nul_records(stage_output, "Git index"):
        metadata, separator, raw_path = record.partition(b"\t")
        fields = metadata.split(b" ")
        if not separator or len(fields) != 3 or fields[2] != b"0":
            raise CorpusError("Git index stage is not exactly HEAD")
        path = _decode_tree_path(raw_path, "Git index")
        try:
            mode = fields[0].decode("ascii")
            oid = fields[1].decode("ascii")
        except UnicodeDecodeError as error:
            raise CorpusError("Git index metadata is malformed") from error
        index[path] = (mode, oid)
    if index != dict(tree):
        raise CorpusError("Git index does not exactly match HEAD tree")
    flag_output = _git(
        git,
        ("ls-files", "-v", "-z"),
        checkout,
        allow_local=allow_local,
    )
    flagged_paths = set()
    for record in _nul_records(flag_output, "Git index flags"):
        if len(record) < 3 or record[1:2] != b" ":
            raise CorpusError("Git index flags output is malformed")
        path = _decode_tree_path(record[2:], "Git index flags")
        flagged_paths.add(path)
        if record[:1] != b"H":
            raise CorpusError(f"Git index flags hide worktree state for {path}")
    if flagged_paths != set(tree):
        raise CorpusError("Git index flags path set does not match HEAD tree")


def _read_worktree_file(
    directory_fd: int,
    name: str,
    metadata: os.stat_result,
    relative: str,
) -> bytes:
    if metadata.st_nlink != 1 or metadata.st_size > MAX_CHECKOUT_FILE_BYTES:
        raise CorpusError(f"worktree file is unsafe or oversized: {relative}")
    descriptor = None
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(metadata):
            raise CorpusError(f"worktree file changed while opening: {relative}")
        payload = bytearray()
        while len(payload) <= MAX_CHECKOUT_FILE_BYTES:
            chunk = os.read(
                descriptor,
                min(64 * 1024, MAX_CHECKOUT_FILE_BYTES + 1 - len(payload)),
            )
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(descriptor)
        named_after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if len(payload) > MAX_CHECKOUT_FILE_BYTES:
            raise CorpusError(f"worktree file exceeds the byte bound: {relative}")
        if not (
            _identity(metadata) == _identity(opened) == _identity(after) == _identity(named_after)
        ):
            raise CorpusError(f"worktree file changed during read: {relative}")
        return bytes(payload)
    except CorpusError:
        raise
    except OSError as error:
        raise CorpusError(f"worktree file cannot be read safely: {relative}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _walk_worktree(
    root: Path,
    tree: Mapping[str, tuple[str, str]],
    *,
    root_fd: int | None = None,
) -> dict[str, tuple[str, bytes]]:
    expected_files = set(tree)
    expected_directories = {
        parent.as_posix()
        for path in expected_files
        for parent in PurePosixPath(path).parents
        if parent.as_posix() != "."
    }
    if root_fd is None:
        root_metadata = root.lstat()
        if root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
            raise CorpusError("corpus checkout root is unsafe")
        owned_root_fd = os.open(str(root), _directory_flags())
        named_root = True
    else:
        root_metadata = os.fstat(root_fd)
        if not stat.S_ISDIR(root_metadata.st_mode):
            raise CorpusError("corpus checkout root descriptor is unsafe")
        owned_root_fd = os.dup(root_fd)
        named_root = False
    files: dict[str, tuple[str, bytes]] = {}
    total_bytes = 0

    def visit(directory_fd: int, prefix: str) -> None:
        nonlocal total_bytes
        try:
            with os.scandir(directory_fd) as entries:
                names = sorted(entry.name for entry in entries)
        except OSError as error:
            raise CorpusError("worktree directory cannot be enumerated safely") from error
        for name in names:
            if not isinstance(name, str) or not name or name in {".", ".."} or "/" in name:
                raise CorpusError("worktree entry name is unsafe")
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if not prefix and name == ".git":
                if not stat.S_ISDIR(metadata.st_mode):
                    raise CorpusError("worktree .git entry must be a real directory")
                continue
            relative = f"{prefix}/{name}" if prefix else name
            if stat.S_ISDIR(metadata.st_mode):
                if relative not in expected_directories:
                    raise CorpusError("worktree path set differs from HEAD tree")
                child_fd = os.open(
                    name,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                try:
                    opened = os.fstat(child_fd)
                    if _identity(opened) != _identity(metadata):
                        raise CorpusError("worktree directory changed while opening")
                    visit(child_fd, relative)
                    after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if _identity(after) != _identity(opened):
                        raise CorpusError("worktree directory changed during traversal")
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise CorpusError(f"worktree mode is not allowed for {relative}")
            if relative not in expected_files:
                raise CorpusError("worktree path set differs from HEAD tree")
            expected_mode = tree[relative][0]
            executable = bool(metadata.st_mode & 0o111)
            if executable != (expected_mode == "100755"):
                raise CorpusError(f"worktree mode does not match HEAD tree for {relative}")
            payload = _read_worktree_file(directory_fd, name, metadata, relative)
            total_bytes += len(payload)
            if total_bytes > MAX_CHECKOUT_TOTAL_BYTES:
                raise CorpusError("worktree content exceeds the total byte bound")
            files[relative] = (expected_mode, payload)

    try:
        if _identity(os.fstat(owned_root_fd)) != _identity(root_metadata):
            raise CorpusError("corpus checkout root changed while opening")
        visit(owned_root_fd, "")
        if named_root:
            root_after = root.lstat()
        else:
            assert root_fd is not None
            root_after = os.fstat(root_fd)
        if _identity(root_after) != _identity(root_metadata):
            raise CorpusError("corpus checkout root changed during traversal")
    finally:
        os.close(owned_root_fd)
    if set(files) != expected_files:
        raise CorpusError("worktree path set differs from HEAD tree")
    return files


def _verify_blob_bytes(
    git: Path,
    checkout: Path,
    tree: Mapping[str, tuple[str, str]],
    files: Mapping[str, tuple[str, bytes]],
    *,
    allow_local: bool,
) -> None:
    object_format = os.fsdecode(
        _git(
            git,
            ("rev-parse", "--show-object-format"),
            checkout,
            allow_local=allow_local,
        )
    ).strip()
    if object_format not in {"sha1", "sha256"}:
        raise CorpusError("Git object format is unsupported")
    for path in sorted(tree):
        _mode, expected_oid = tree[path]
        payload = files[path][1]
        digest = hashlib.new(object_format)
        digest.update(f"blob {len(payload)}\0".encode("ascii"))
        digest.update(payload)
        if digest.hexdigest() != expected_oid:
            raise CorpusError(f"worktree blob identity differs from HEAD for {path}")
        blob = _git(
            git,
            ("cat-file", "blob", expected_oid),
            checkout,
            allow_local=allow_local,
        )
        if blob != payload:
            raise CorpusError(f"worktree bytes differ from HEAD blob for {path}")


def _summary(destination: Path, rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "destination": str(destination),
        "corpora": [dict(row) for row in rows],
    }


def _verify_checkout(
    spec: CorpusSpec,
    checkout: Path,
    git: Path,
    *,
    allow_local: bool,
    checkout_fd: int | None = None,
) -> dict[str, object]:
    if checkout_fd is None:
        if checkout.is_symlink() or not checkout.is_dir():
            raise CorpusError(f"{spec.id} checkout is not a regular directory")
        cwd = checkout
    else:
        if not stat.S_ISDIR(os.fstat(checkout_fd).st_mode):
            raise CorpusError(f"{spec.id} checkout descriptor is not a directory")
        cwd = _fd_path(checkout_fd)
    top = _git(git, ("rev-parse", "--show-toplevel"), cwd, allow_local=allow_local)
    top_path = Path(os.fsdecode(top).strip())
    if checkout_fd is None:
        if top_path.resolve(strict=True) != checkout.resolve(strict=True):
            raise CorpusError(f"{spec.id} checkout has an unexpected Git root")
    else:
        try:
            top_fd = os.open(str(top_path), _directory_flags())
        except OSError as error:
            raise CorpusError(f"{spec.id} Git root cannot be opened safely") from error
        try:
            expected_identity = (os.fstat(checkout_fd).st_dev, os.fstat(checkout_fd).st_ino)
            if not _same_directory(os.fstat(top_fd), expected_identity):
                raise CorpusError(f"{spec.id} checkout has an unexpected Git root")
        finally:
            os.close(top_fd)
    remote_output = os.fsdecode(
        _git(
            git,
            ("config", "--local", "--get-all", "remote.origin.url"),
            cwd,
            allow_local=allow_local,
        )
    )
    remotes = tuple(line for line in remote_output.splitlines() if line)
    if remotes != (spec.repository,):
        raise CorpusError(f"{spec.id} remote URL does not match the catalog")
    head = os.fsdecode(
        _git(
            git,
            ("rev-parse", "--verify", "HEAD^{commit}"),
            cwd,
            allow_local=allow_local,
        )
    ).strip()
    if head != spec.commit:
        raise CorpusError(f"{spec.id} HEAD does not match the pinned commit")
    branch = os.fsdecode(
        _git(git, ("branch", "--show-current"), cwd, allow_local=allow_local)
    ).strip()
    if branch:
        raise CorpusError(f"{spec.id} checkout must have a detached HEAD")
    commit_count = os.fsdecode(
        _git(git, ("rev-list", "--count", "HEAD"), cwd, allow_local=allow_local)
    ).strip()
    if commit_count != "1":
        raise CorpusError(f"{spec.id} checkout must contain only the pinned shallow commit")
    tree = _head_tree(git, cwd, allow_local=allow_local)
    _verify_index(git, cwd, tree, allow_local=allow_local)
    files = _walk_worktree(cwd, tree, root_fd=checkout_fd)
    _verify_blob_bytes(git, cwd, tree, files, allow_local=allow_local)
    license_row = files.get(spec.license_path)
    if license_row is None:
        raise CorpusError(f"{spec.id} license is absent from HEAD tree")
    license_bytes = license_row[1]
    if license_bytes != spec.license_bytes:
        actual_digest = hashlib.sha256(license_bytes).hexdigest()
        raise CorpusError(
            f"{spec.id} license bytes do not match the preserved license: "
            f"expected {spec.license_sha256}, got {actual_digest}"
        )
    if hashlib.sha256(license_bytes).hexdigest() != spec.license_sha256:
        raise CorpusError(f"{spec.id} license digest does not match the catalog")
    return {
        "id": spec.id,
        "repository": spec.repository,
        "commit": spec.commit,
        "license": spec.license,
        "license_sha256": spec.license_sha256,
        "clean": True,
    }


def fetch_corpora(
    catalog_path: Path,
    destination: Path,
    *,
    repository_root: Path = ROOT,
    allow_local_repositories: bool = False,
    git_executable: Path | None = None,
    after_destination_open: Callable[[DestinationHandle], object] | None = None,
) -> dict[str, object]:
    """Fetch every catalog row as one shallow detached verified checkout."""
    specs = load_catalog(
        catalog_path,
        allow_local_repositories=allow_local_repositories,
    )
    git = _find_git(git_executable)
    handle = _create_destination(destination, repository_root)
    operation_error = None
    try:
        if after_destination_open is not None:
            after_destination_open(handle)
        rows = []
        for spec in specs:
            os.mkdir(spec.checkout, mode=0o700, dir_fd=handle.child_fd)
            checkout_fd = os.open(spec.checkout, _directory_flags(), dir_fd=handle.child_fd)
            checkout_identity = (os.fstat(checkout_fd).st_dev, os.fstat(checkout_fd).st_ino)
            checkout_cwd = _fd_path(checkout_fd)
            try:
                _git(
                    git,
                    ("init", "--quiet"),
                    checkout_cwd,
                    allow_local=allow_local_repositories,
                )
                _git(
                    git,
                    ("remote", "add", "origin", spec.repository),
                    checkout_cwd,
                    allow_local=allow_local_repositories,
                )
                configured = os.fsdecode(
                    _git(
                        git,
                        ("config", "--local", "--get", "remote.origin.url"),
                        checkout_cwd,
                        allow_local=allow_local_repositories,
                    )
                ).strip()
                if configured != spec.repository:
                    raise CorpusError(f"{spec.id} remote URL changed before fetch")
                _git(
                    git,
                    ("fetch", "--quiet", "--depth=1", "--no-tags", "origin", spec.commit),
                    checkout_cwd,
                    allow_local=allow_local_repositories,
                    timeout=GIT_FETCH_TIMEOUT_SECONDS,
                )
                _git(
                    git,
                    ("checkout", "--quiet", "--detach", spec.commit),
                    checkout_cwd,
                    allow_local=allow_local_repositories,
                )
                rows.append(
                    _verify_checkout(
                        spec,
                        handle.path / spec.checkout,
                        git,
                        allow_local=allow_local_repositories,
                        checkout_fd=checkout_fd,
                    )
                )
                named_checkout = os.stat(
                    spec.checkout, dir_fd=handle.child_fd, follow_symlinks=False
                )
                if not _same_directory(named_checkout, checkout_identity):
                    raise CorpusError(f"{spec.id} checkout destination identity changed")
            finally:
                os.close(checkout_fd)
        actual = set()
        with os.scandir(handle.child_fd) as entries:
            for entry in entries:
                actual.add(entry.name)
        if actual != {spec.checkout for spec in specs}:
            raise CorpusError("corpus destination contains unknown or missing checkouts")
        _verify_destination_handle(handle)
        summary = _summary(handle.path, rows)
    except Exception as error:
        operation_error = error
        summary = None
    if operation_error is not None:
        try:
            _cleanup_destination(handle)
        except CorpusError as cleanup_error:
            raise cleanup_error from operation_error
        if isinstance(operation_error, CorpusError):
            raise operation_error
        raise CorpusError("corpus fetch failed") from operation_error
    _close_destination(handle)
    assert summary is not None
    return summary


def verify_corpora(
    catalog_path: Path,
    destination: Path,
    *,
    repository_root: Path = ROOT,
    allow_local_repositories: bool = False,
    git_executable: Path | None = None,
) -> dict[str, object]:
    """Verify existing checkouts without fetching or mutating them."""
    specs = load_catalog(
        catalog_path,
        allow_local_repositories=allow_local_repositories,
    )
    git = _find_git(git_executable)
    handle = _open_destination(destination, repository_root)
    try:
        actual = set()
        with os.scandir(handle.child_fd) as entries:
            for entry in entries:
                actual.add(entry.name)
        expected = {spec.checkout for spec in specs}
        if actual != expected:
            raise CorpusError("corpus destination contains unknown or missing checkouts")
        rows = []
        for spec in specs:
            checkout_metadata = os.stat(
                spec.checkout, dir_fd=handle.child_fd, follow_symlinks=False
            )
            if not stat.S_ISDIR(checkout_metadata.st_mode):
                raise CorpusError(f"{spec.id} checkout is not a real directory")
            checkout_fd = os.open(spec.checkout, _directory_flags(), dir_fd=handle.child_fd)
            checkout_identity = (checkout_metadata.st_dev, checkout_metadata.st_ino)
            try:
                if not _same_directory(os.fstat(checkout_fd), checkout_identity):
                    raise CorpusError(f"{spec.id} checkout changed while opening")
                rows.append(
                    _verify_checkout(
                        spec,
                        handle.path / spec.checkout,
                        git,
                        allow_local=allow_local_repositories,
                        checkout_fd=checkout_fd,
                    )
                )
                named_after = os.stat(spec.checkout, dir_fd=handle.child_fd, follow_symlinks=False)
                if not _same_directory(named_after, checkout_identity):
                    raise CorpusError(f"{spec.id} checkout changed during verification")
            finally:
                os.close(checkout_fd)
        _verify_destination_handle(handle)
        return _summary(handle.path, rows)
    except Exception as error:
        if isinstance(error, CorpusError):
            raise
        raise CorpusError("corpus verification failed") from error
    finally:
        _close_destination(handle)


def _load_working_state_guard() -> ModuleType:
    path = Path(__file__).with_name("run-ast-grep-canary.py")
    name = "_rir_graph_corpus_working_state_guard"
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise CorpusError("repository working-state guard is unavailable")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    if not callable(getattr(module, "guard_working_state", None)):
        raise CorpusError("repository working-state guard is incomplete")
    return module


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(arguments)
    try:
        guard = _load_working_state_guard()
        summary = guard.guard_working_state(
            ROOT,
            lambda: fetch_corpora(CATALOG_PATH, args.destination),
        )
    except (CorpusError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
