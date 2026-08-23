#!/usr/bin/env python3
"""Bounded, detect-only process runner for optional graph providers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from types import MappingProxyType
from typing import Any, Mapping, Sequence


STDOUT_LIMIT = 4 * 1024 * 1024
STDERR_LIMIT = 256 * 1024
MAX_ARGUMENTS = 128
MAX_ARGUMENT_BYTES = 64 * 1024
MAX_EXECUTABLE_BYTES = 64 * 1024 * 1024
PROVIDER_PRIORITY = ("codegraph", "scip", "joern", "ast-grep")
_DISCOVERY_NAMES = {
    "codegraph": ("codegraph",),
    "scip": ("scip",),
    "ast-grep": ("sg", "ast-grep"),
    "joern": ("joern",),
}
_ALIASES = {"sg": "ast-grep", **{name: name for name in PROVIDER_PRIORITY}}
_FORBIDDEN_COMMANDS = frozenset({
    "auth", "authenticate", "connect", "daemon", "fix", "index", "install",
    "joern-parse", "login", "logout", "parse", "publish", "rewrite", "server",
    "setup", "update", "upload", "watch", "watcher",
})
_CREDENTIAL_VALUE = re.compile(
    r"(?i)\b[a-z0-9_-]*(?:api[_-]?key|token|password|secret)"
    r"\b\s*[:=]\s*[^\s,;]+"
)


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class Deadline:
    """One monotonic deadline shared by discovery and all provider queries."""

    clock: Any
    max_seconds: float
    started: float = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_seconds, (int, float))
            or isinstance(self.max_seconds, bool)
            or self.max_seconds < 0
            or self.max_seconds > 30
        ):
            raise ValueError("deadline seconds must be between 0 and 30")
        monotonic = getattr(self.clock, "monotonic", None)
        if not callable(monotonic):
            raise TypeError("deadline clock must provide monotonic()")
        if self.started is None:
            object.__setattr__(self, "started", float(monotonic()))

    @property
    def expires(self) -> float:
        return self.started + float(self.max_seconds)

    def remaining(self, cap=None) -> float:
        remaining = max(0.0, self.expires - float(self.clock.monotonic()))
        if cap is not None:
            if not isinstance(cap, (int, float)) or isinstance(cap, bool) or cap < 0:
                raise ValueError("deadline cap must be non-negative")
            remaining = min(remaining, float(cap))
        return remaining

    def expired(self) -> bool:
        return self.remaining() <= 0.0

    def elapsed_ms(self) -> int:
        return max(0, int(round((float(self.clock.monotonic()) - self.started) * 1000)))


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    executable: Path = None

    def __post_init__(self) -> None:
        canonical = _ALIASES.get(self.name)
        if canonical is None:
            raise ValueError("provider name is not in the fixed provider allowlist")
        object.__setattr__(self, "name", canonical)
        if self.executable is not None:
            executable = Path(self.executable)
            if not executable.is_absolute():
                raise ValueError("configured provider executable must be absolute")
            object.__setattr__(self, "executable", executable)


@dataclass(frozen=True)
class ProviderProbe:
    name: str
    status: str
    confidence: str = "lexical"
    executable: Path = None
    version: str = None
    executable_sha256: str = None
    capabilities: tuple = ()
    detail: str = None
    repo_root: Path = None
    metadata: Mapping[str, Any] = None

    def __post_init__(self) -> None:
        canonical = _ALIASES.get(self.name)
        if canonical is None:
            raise ValueError("provider probe name is not allowed")
        object.__setattr__(self, "name", canonical)
        if self.status not in {
            "ready", "missing", "stale", "unsafe", "unsupported", "failed", "timed_out",
        }:
            raise ValueError("invalid provider probe status")
        if self.confidence not in {
            "verified-provider", "verified-source", "structural-inferred", "lexical",
        }:
            raise ValueError("invalid provider probe confidence")
        if self.executable is not None:
            object.__setattr__(self, "executable", Path(self.executable))
        if self.repo_root is not None:
            object.__setattr__(self, "repo_root", Path(self.repo_root))
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(
            self, "metadata", _freeze(dict(self.metadata or {})),
        )


@dataclass(frozen=True)
class ProviderQuery:
    """A bounded subprocess observation; raw bytes never leave the runner."""

    provider: str
    status: str
    argv: tuple
    environment: Mapping[str, str]
    stdout: str = ""
    stderr: str = ""
    returncode: int = None
    executable_sha256: str = None
    parsed_json: Any = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    detail: str = None

    def __post_init__(self) -> None:
        canonical = _ALIASES.get(self.provider)
        if canonical is None:
            raise ValueError("provider query name is not allowed")
        object.__setattr__(self, "provider", canonical)
        if self.status not in {
            "ready", "missing", "stale", "unsafe", "unsupported", "failed", "timed_out",
        }:
            raise ValueError("invalid provider query status")
        object.__setattr__(self, "argv", tuple(self.argv))
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))


@dataclass(frozen=True)
class ProviderResult:
    """Adapter output before the coordinator assigns receipt-local graph IDs."""

    provider: str
    status: str
    confidence: str
    nodes: tuple = ()
    edges: tuple = ()
    frontier: tuple = ()
    raw_receipt_sha256: tuple = ()
    detail: str = None
    metadata: Mapping[str, Any] = None

    def __post_init__(self) -> None:
        canonical = _ALIASES.get(self.provider)
        if canonical is None:
            raise ValueError("provider result name is not allowed")
        object.__setattr__(self, "provider", canonical)
        if self.status not in {
            "ready", "missing", "stale", "unsafe", "unsupported", "failed", "timed_out",
        }:
            raise ValueError("invalid provider result status")
        if self.confidence not in {
            "verified-provider", "verified-source", "structural-inferred", "lexical",
        }:
            raise ValueError("invalid provider result confidence")
        object.__setattr__(self, "nodes", tuple(_freeze(item) for item in self.nodes))
        object.__setattr__(self, "edges", tuple(_freeze(item) for item in self.edges))
        object.__setattr__(self, "frontier", tuple(_freeze(item) for item in self.frontier))
        object.__setattr__(self, "raw_receipt_sha256", tuple(self.raw_receipt_sha256))
        object.__setattr__(
            self, "metadata", _freeze(dict(self.metadata or {})),
        )


@dataclass(frozen=True)
class _ProcessOutcome:
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class UnsafeExecutableError(ValueError):
    """The checked executable cannot be launched through its private snapshot."""


@dataclass(frozen=True)
class _ExecutableSnapshot:
    directory: Path
    path: Path
    sha256: str
    device: int
    inode: int
    size: int
    modified_ns: int


def _bounded_detail(value: object) -> str:
    text = _CREDENTIAL_VALUE.sub("[REDACTED]", str(value).replace("\x00", ""))
    return text[:512]


def _empty_query(spec, status, argv, environment, detail=None, digest=None):
    return ProviderQuery(
        spec.name, status, argv, environment, executable_sha256=digest,
        detail=_bounded_detail(detail) if detail else None,
    )


def _validate_arguments(arguments: Sequence[str]) -> tuple:
    if not isinstance(arguments, (tuple, list)) or len(arguments) > MAX_ARGUMENTS:
        raise ValueError("provider argv must be a bounded sequence")
    normalized = []
    total = 0
    for argument in arguments:
        if not isinstance(argument, str) or not argument or "\x00" in argument:
            raise ValueError("provider arguments must be non-empty strings without NUL")
        total += len(argument.encode("utf-8"))
        command = argument.lower().lstrip("-").split("=", 1)[0]
        if command in _FORBIDDEN_COMMANDS:
            raise PermissionError("provider command is outside the read-only allowlist")
        normalized.append(argument)
    if total > MAX_ARGUMENT_BYTES:
        raise ValueError("provider argv exceeds maximum size")
    return tuple(normalized)


def _open_executable(path: Path):
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ValueError("provider executable is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("provider executable must be a regular non-symlink file")
    if metadata.st_size > MAX_EXECUTABLE_BYTES:
        raise ValueError("provider executable exceeds maximum byte size")
    if metadata.st_mode & 0o111 == 0:
        raise ValueError("provider executable must have an execute bit")
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(str(path), flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError("provider executable descriptor must be a regular file")
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise ValueError("provider executable changed while opening")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor, opened, digest.hexdigest()
    except Exception:
        os.close(descriptor)
        raise


def _append_bounded(target: bytearray, chunk: bytes, limit: int) -> bool:
    room = max(0, limit - len(target))
    target.extend(chunk[:room])
    return len(chunk) > room


def _terminate_process_group(process, process_group_id=None) -> None:
    group_id = process.pid if process_group_id is None else process_group_id
    try:
        os.killpg(group_id, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        try:
            process.kill()
        except ProcessLookupError:
            pass


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("snapshot write made no progress")
        offset += written


def _snapshot_matches(snapshot: _ExecutableSnapshot) -> bool:
    try:
        metadata = snapshot.path.lstat()
    except OSError:
        return False
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_size != snapshot.size
        or metadata.st_size > MAX_EXECUTABLE_BYTES
        or (metadata.st_dev, metadata.st_ino, metadata.st_mtime_ns)
        != (snapshot.device, snapshot.inode, snapshot.modified_ns)
    ):
        return False
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(snapshot.path), flags)
    except OSError:
        return False
    digest = hashlib.sha256()
    total = 0
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (snapshot.device, snapshot.inode)
        ):
            return False
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_EXECUTABLE_BYTES:
                return False
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return total == snapshot.size and digest.hexdigest() == snapshot.sha256


def _create_executable_snapshot(
    executable_fd: int, opened, expected_sha256: str,
) -> _ExecutableSnapshot:
    directory = Path(tempfile.mkdtemp(prefix="rir-provider-"))
    snapshot = None
    try:
        os.chmod(directory, 0o700)
        directory_metadata = directory.lstat()
        if (
            stat.S_ISLNK(directory_metadata.st_mode)
            or not stat.S_ISDIR(directory_metadata.st_mode)
            or stat.S_IMODE(directory_metadata.st_mode) != 0o700
        ):
            raise UnsafeExecutableError("provider snapshot directory is unsafe")
        path = directory / "provider-executable"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(str(path), flags, 0o700)
        digest = hashlib.sha256()
        total = 0
        try:
            os.fchmod(descriptor, 0o700)
            os.lseek(executable_fd, 0, os.SEEK_SET)
            while True:
                chunk = os.read(executable_fd, 64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_EXECUTABLE_BYTES:
                    raise UnsafeExecutableError(
                        "provider executable exceeds maximum byte size"
                    )
                _write_all(descriptor, chunk)
                digest.update(chunk)
            os.fsync(descriptor)
            metadata = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if (
            total != opened.st_size
            or digest.hexdigest() != expected_sha256
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise UnsafeExecutableError(
                "provider snapshot does not match validated executable identity"
            )
        directory_fd = os.open(
            str(directory), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        snapshot = _ExecutableSnapshot(
            directory, path, expected_sha256, metadata.st_dev, metadata.st_ino,
            total, metadata.st_mtime_ns,
        )
        if not _snapshot_matches(snapshot):
            raise UnsafeExecutableError("provider snapshot failed identity verification")
        return snapshot
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


def _cleanup_snapshot(snapshot: _ExecutableSnapshot) -> None:
    shutil.rmtree(snapshot.directory, ignore_errors=True)


def _bounded_subprocess(
    argv, *, cwd, env, timeout, shell, start_new_session, stdout_limit, stderr_limit,
    executable_snapshot, snapshot_sha256, snapshot_identity,
):
    if shell or not start_new_session:
        raise ValueError("provider subprocess security options are mandatory")
    snapshot = _ExecutableSnapshot(
        Path(executable_snapshot).parent, Path(executable_snapshot), snapshot_sha256,
        *snapshot_identity,
    )
    if not _snapshot_matches(snapshot):
        raise UnsafeExecutableError(
            "provider snapshot changed before process spawn"
        )
    execution_argv = (str(snapshot.path),) + tuple(argv[1:])
    process = subprocess.Popen(
        execution_argv, executable=str(snapshot.path), cwd=cwd, env=env, shell=False,
        start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        close_fds=True,
    )
    process_group_id = process.pid
    selector = selectors.DefaultSelector()
    assert process.stdout is not None and process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ, (bytearray(), stdout_limit))
    selector.register(process.stderr, selectors.EVENT_READ, (bytearray(), stderr_limit))
    buffers = {process.stdout: bytearray(), process.stderr: bytearray()}
    truncated = {process.stdout: False, process.stderr: False}
    expires = time.monotonic() + timeout
    timed_out = False
    post_kill_expires = None
    try:
        while selector.get_map():
            now = time.monotonic()
            if now >= expires and not timed_out:
                timed_out = True
                post_kill_expires = now + 0.25
                _terminate_process_group(process, process_group_id)
            if timed_out and now >= post_kill_expires:
                for stream in tuple(buffers):
                    try:
                        selector.unregister(stream)
                    except (KeyError, ValueError):
                        pass
                break
            wait_until = post_kill_expires if timed_out else expires
            events = selector.select(max(0.0, min(wait_until - now, 0.05)))
            for key, _ in events:
                stream = key.fileobj
                chunk = os.read(stream.fileno(), 64 * 1024)
                if not chunk:
                    selector.unregister(stream)
                    continue
                truncated[stream] |= _append_bounded(buffers[stream], chunk, key.data[1])
        returncode = process.wait(timeout=1)
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
    if not _snapshot_matches(snapshot):
        raise UnsafeExecutableError("provider snapshot changed during execution")
    return _ProcessOutcome(
        returncode, bytes(buffers[process.stdout]), bytes(buffers[process.stderr]),
        timed_out, truncated[process.stdout], truncated[process.stderr],
    )


def run_provider(
    spec: ProviderSpec,
    arguments: Sequence[str],
    repo_root,
    deadline: Deadline,
    *,
    runner=None,
    expect_json: bool = False,
) -> ProviderQuery:
    """Run one fixed executable without a shell or inherited process environment."""
    if not isinstance(spec, ProviderSpec):
        raise TypeError("spec must be ProviderSpec")
    if not isinstance(deadline, Deadline):
        raise TypeError("deadline must be Deadline")
    try:
        safe_arguments = _validate_arguments(arguments)
    except PermissionError as error:
        executable = str(spec.executable) if spec.executable else spec.name
        return _empty_query(spec, "unsafe", (executable,) + tuple(arguments), {}, error)
    root = Path(repo_root)
    if root.is_symlink() or not root.is_dir():
        executable = str(spec.executable) if spec.executable else spec.name
        return _empty_query(spec, "unsafe", (executable,) + safe_arguments, {}, "unsafe repo_root")
    root = root.resolve()
    if spec.executable is None:
        return _empty_query(spec, "missing", (spec.name,) + safe_arguments, {}, "missing executable")
    executable = spec.executable
    environment = {
        "PATH": str(executable.parent),
        "CODEGRAPH_TELEMETRY": "0",
        "NO_COLOR": "1",
    }
    argv = (str(executable),) + safe_arguments
    remaining = deadline.remaining()
    if remaining <= 0:
        return _empty_query(spec, "timed_out", argv, environment, "shared deadline exhausted")
    try:
        descriptor, opened, digest = _open_executable(executable)
    except (OSError, ValueError) as error:
        return _empty_query(spec, "unsafe", argv, environment, error)
    try:
        snapshot = _create_executable_snapshot(descriptor, opened, digest)
    except (OSError, ValueError) as error:
        return _empty_query(spec, "unsafe", argv, environment, error, digest)
    finally:
        os.close(descriptor)
    execute = runner or _bounded_subprocess
    try:
        if not _snapshot_matches(snapshot):
            return _empty_query(
                spec, "unsafe", argv, environment,
                "provider snapshot changed before runner invocation", digest,
            )
        try:
            outcome = execute(
                argv, cwd=str(root), env=dict(environment), timeout=remaining,
                shell=False, start_new_session=True, stdout_limit=STDOUT_LIMIT,
                stderr_limit=STDERR_LIMIT,
                executable_snapshot=str(snapshot.path),
                snapshot_sha256=snapshot.sha256,
                snapshot_identity=(
                    snapshot.device, snapshot.inode, snapshot.size,
                    snapshot.modified_ns,
                ),
            )
        except subprocess.TimeoutExpired as error:
            return _empty_query(spec, "timed_out", argv, environment, error, digest)
        except UnsafeExecutableError as error:
            return _empty_query(spec, "unsafe", argv, environment, error, digest)
        except (OSError, ValueError) as error:
            return _empty_query(spec, "failed", argv, environment, error, digest)
        if not _snapshot_matches(snapshot):
            return _empty_query(
                spec, "unsafe", argv, environment,
                "provider snapshot changed after runner completion", digest,
            )
    finally:
        _cleanup_snapshot(snapshot)

    stdout_raw = getattr(outcome, "stdout", b"")
    stderr_raw = getattr(outcome, "stderr", b"")
    if not isinstance(stdout_raw, bytes) or not isinstance(stderr_raw, bytes):
        return _empty_query(spec, "failed", argv, environment, "provider output must be bytes", digest)
    stdout_truncated = bool(getattr(outcome, "stdout_truncated", False)) or len(stdout_raw) > STDOUT_LIMIT
    stderr_truncated = bool(getattr(outcome, "stderr_truncated", False)) or len(stderr_raw) > STDERR_LIMIT
    stdout_raw = stdout_raw[:STDOUT_LIMIT]
    stderr_raw = stderr_raw[:STDERR_LIMIT]
    try:
        stdout = stdout_raw.decode("utf-8")
        stderr = stderr_raw.decode("utf-8")
    except UnicodeDecodeError:
        return _empty_query(spec, "failed", argv, environment, "provider output must be UTF-8", digest)
    timed_out = bool(getattr(outcome, "timed_out", False))
    returncode = getattr(outcome, "returncode", None)
    status = "timed_out" if timed_out else "ready"
    detail = None
    parsed = None
    if not timed_out and (returncode != 0 or stdout_truncated or stderr_truncated):
        status = "failed"
        detail = "provider process failed or exceeded an output bound"
    elif expect_json:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            status = "failed"
            detail = "provider output must contain valid JSON"
    return ProviderQuery(
        spec.name, status, argv, environment, stdout, stderr, returncode, digest,
        parsed, stdout_truncated, stderr_truncated, detail,
    )


def _unsafe_probe(configured, detail):
    name = _ALIASES.get(Path(str(configured)).name, "codegraph")
    return ProviderProbe(name, "unsafe", detail=_bounded_detail(detail))


def _configured_specs(requested, search_path, deep):
    values = tuple(requested)
    if not values:
        return (), ()
    if values == ("auto",):
        names = (
            ("codegraph", "scip", "joern", "ast-grep")
            if deep else ("codegraph", "scip", "ast-grep")
        )
        specs = []
        for name in names:
            executable = None
            for candidate in _DISCOVERY_NAMES[name]:
                found = shutil.which(candidate, path=search_path)
                if found:
                    executable = Path(found).absolute()
                    break
            specs.append(ProviderSpec(name, executable) if executable else ProviderSpec(name))
        return tuple(specs), ()
    specs = []
    unsafe = []
    for value in values:
        path = Path(value)
        if path.is_absolute():
            name = _ALIASES.get(path.name)
            if name is None:
                unsafe.append(_unsafe_probe(value, "absolute path basename is not allowed"))
            else:
                specs.append(ProviderSpec(name, path))
        elif value in _ALIASES:
            name = _ALIASES[value]
            found = None
            for candidate in _DISCOVERY_NAMES[name]:
                current = shutil.which(candidate, path=search_path)
                if current:
                    found = Path(current).absolute()
                    break
            specs.append(ProviderSpec(name, found) if found else ProviderSpec(name))
        else:
            unsafe.append(_unsafe_probe(value, "configured provider must be a fixed name or absolute path"))
    order = {name: index for index, name in enumerate(PROVIDER_PRIORITY)}
    return tuple(sorted(specs, key=lambda item: order[item.name])), tuple(unsafe)


def discover_providers(
    repo_root,
    requested=("auto",),
    deadline=None,
    *,
    runner=None,
    search_path=None,
    deep=False,
):
    """Detect fixed local providers using only exact version and bounded help probes."""
    if hasattr(requested, "providers"):
        deep = bool(getattr(requested, "deep", deep))
        requested = requested.providers
    if deadline is None:
        deadline = Deadline(time, 30)
    if not isinstance(deadline, Deadline):
        raise TypeError("deadline must be Deadline")
    if search_path is None:
        search_path = os.environ.get("PATH", os.defpath)
    root = Path(repo_root).resolve() if Path(repo_root).is_dir() else Path(repo_root).absolute()
    specs, unsafe = _configured_specs(requested, search_path, deep)
    probes = []
    for spec in specs:
        if spec.executable is None:
            probes.append(ProviderProbe(
                spec.name, "missing", detail="executable not found", repo_root=root,
            ))
            continue
        version_result = run_provider(
            spec, ("--version",), repo_root, deadline, runner=runner,
        )
        if version_result.status != "ready":
            probes.append(ProviderProbe(
                spec.name, version_result.status, "lexical", spec.executable,
                executable_sha256=version_result.executable_sha256,
                detail=version_result.detail, repo_root=root,
            ))
            continue
        version = next(
            (
                _bounded_detail(line.strip())[:256]
                for line in version_result.stdout.splitlines() if line.strip()
            ),
            "unknown",
        )
        help_result = run_provider(
            spec, ("--help",), repo_root, deadline, runner=runner,
        )
        if (
            help_result.executable_sha256 is not None
            and help_result.executable_sha256 != version_result.executable_sha256
        ):
            probes.append(ProviderProbe(
                spec.name, "unsafe", "lexical", spec.executable, version,
                version_result.executable_sha256,
                detail="provider executable changed between probes", repo_root=root,
            ))
            continue
        if help_result.status != "ready":
            status = (
                help_result.status
                if help_result.status in {"timed_out", "unsafe"}
                else "unsupported"
            )
            probes.append(ProviderProbe(
                spec.name, status, "lexical", spec.executable, version,
                version_result.executable_sha256, detail=help_result.detail,
                repo_root=root,
            ))
            continue
        capabilities = tuple(
            _bounded_detail(line.strip())[:256]
            for line in help_result.stdout.splitlines()[:64]
            if line.strip()
        )
        probes.append(ProviderProbe(
            spec.name, "ready", "verified-provider", spec.executable, version,
            version_result.executable_sha256, capabilities, repo_root=root,
        ))
    return tuple(probes) + unsafe


__all__ = [
    "Deadline", "ProviderProbe", "ProviderQuery", "ProviderResult", "ProviderSpec",
    "PROVIDER_PRIORITY", "STDERR_LIMIT", "STDOUT_LIMIT", "discover_providers",
    "run_provider",
]
