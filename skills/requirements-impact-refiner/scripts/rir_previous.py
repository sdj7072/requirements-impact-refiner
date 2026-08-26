#!/usr/bin/env python3
"""Bounded, fail-closed lookup of an immutable previous impact report."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Callable, Literal, Protocol, cast

if TYPE_CHECKING:
    from typing_extensions import TypeGuard


class _ReportContextContract(Protocol):
    ReportContext: type
    REPORT_ID_PATTERN: re.Pattern[str]
    SHA256_PATTERN: re.Pattern[str]
    MAX_REQUIREMENT_INPUT_BYTES: int
    MAX_REQUIREMENT_BYTES: int

    def canonical_requirement_text(self, request: str) -> str: ...

    def canonical_requirement_sha256(self, request: str) -> str: ...

    def canonical_repository_evidence_sha256(self, evidence: Sequence[str]) -> str: ...

    def repo_root_sha256(self, root: Path) -> str: ...

    def load_report_context(self, root: Path, report_id: str, revision: int): ...


class _PayloadIdentityContract(Protocol):
    ROOT_FILES: tuple[str, ...]

    def functional_paths(self, plugin_root: Path) -> tuple[Path, ...]: ...

    def payload_sha256(self, plugin_root: Path) -> str: ...


class _CompactStateContract(Protocol):
    def validate_state(self, value: object) -> list[str]: ...

    def load_state_bytes(self, raw: bytes) -> tuple[dict[str, object] | None, list[str]]: ...


class _ImpactRendererContract(Protocol):
    compact_state: _CompactStateContract

    def render_compact(self, state: Mapping[str, object]) -> str: ...

    def render_markdown(self, state: Mapping[str, object]) -> str: ...


class _PreviousRendererContract(Protocol):
    COMPACT_STATE: _CompactStateContract
    IMPACT_RENDERER: _ImpactRendererContract

    def module_uses_sibling(self, value: object, filename: str) -> bool: ...

    def load_local_module(
        self,
        filename: str,
        canonical_name: str,
        prefix: str,
        validator: Callable[[object], bool],
        label: str,
    ) -> object: ...

    def render_previous(self, result: object, compact_state: Mapping[str, object]) -> str: ...


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

STATUS_VALUES = frozenset({"none", "fresh", "stale", "ambiguous"})
REPORT_ID_PATTERN = re.compile(r"RPT-\d{3}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
POINTER_FIELDS = frozenset(
    {"schema_version", "report_id", "revision", "state", "markdown", "markdown_sha256"}
)
MAX_POINTER_BYTES = 8 * 1024
MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_MARKDOWN_BYTES = 4 * 1024 * 1024
MAX_GIT_OUTPUT_BYTES = 256 * 1024
MAX_CHANGED_PATHS = 4096
MAX_CHANGED_PATH_BYTES = 4096
MAX_REPORT_ENTRIES = 4096
MAX_REPORT_LINEAGES = 1000
OPERATION_TIMEOUT_SECONDS = 0.25


class _UnsafeLookup(ValueError):
    pass


class _LookupDeadline(TimeoutError):
    pass


class _GitUnavailable(RuntimeError):
    pass


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


def _is_previous_renderer_contract(value: object) -> TypeGuard[_PreviousRendererContract]:
    compact_state = getattr(value, "COMPACT_STATE", None)
    impact_renderer = getattr(value, "IMPACT_RENDERER", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "rir_previous_renderer.py")
        and _module_uses_sibling(compact_state, SCRIPT_DIR / "compact_state.py")
        and _module_uses_sibling(impact_renderer, SCRIPT_DIR / "impact_renderer.py")
        and getattr(impact_renderer, "compact_state", None) is compact_state
        and callable(getattr(compact_state, "validate_state", None))
        and callable(getattr(compact_state, "load_state_bytes", None))
        and callable(getattr(impact_renderer, "render_compact", None))
        and callable(getattr(impact_renderer, "render_markdown", None))
        and callable(getattr(value, "module_uses_sibling", None))
        and callable(getattr(value, "load_local_module", None))
        and callable(getattr(value, "render_previous", None))
    )


def _load_previous_renderer() -> _PreviousRendererContract:
    filename = "rir_previous_renderer.py"
    expected = _regular_module_path(SCRIPT_DIR / filename)
    if expected is None or expected != SCRIPT_DIR / filename:
        raise ImportError("previous renderer sibling is unsafe")
    canonical = sys.modules.get("rir_previous_renderer")
    if _module_uses_sibling(canonical, expected) and _is_previous_renderer_contract(canonical):
        return cast(_PreviousRendererContract, canonical)
    module_name = (
        "_rir_previous_renderer_" + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    )
    existing = sys.modules.get(module_name)
    if existing is not None:
        if not _module_uses_sibling(existing, expected) or not _is_previous_renderer_contract(
            existing
        ):
            raise ImportError("previous renderer sibling contract is incomplete")
        return cast(_PreviousRendererContract, existing)
    if canonical is None:
        module_name = "rir_previous_renderer"
    specification = importlib.util.spec_from_file_location(module_name, expected)
    if specification is None or specification.loader is None:
        raise ImportError("cannot load fixed previous renderer sibling")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError("cannot load fixed previous renderer sibling") from error
    if not _is_previous_renderer_contract(module):
        sys.modules.pop(module_name, None)
        raise ImportError("previous renderer sibling contract is incomplete")
    return cast(_PreviousRendererContract, module)


RENDERER = _load_previous_renderer()


def _is_report_context_contract(value: object) -> TypeGuard[_ReportContextContract]:
    return (
        RENDERER.module_uses_sibling(value, "rir_report_context.py")
        and isinstance(getattr(value, "ReportContext", None), type)
        and isinstance(getattr(value, "REPORT_ID_PATTERN", None), re.Pattern)
        and isinstance(getattr(value, "SHA256_PATTERN", None), re.Pattern)
        and all(
            type(getattr(value, name, None)) is int and getattr(value, name) > 0
            for name in ("MAX_REQUIREMENT_INPUT_BYTES", "MAX_REQUIREMENT_BYTES")
        )
        and all(
            callable(getattr(value, name, None))
            for name in (
                "canonical_requirement_text",
                "canonical_requirement_sha256",
                "canonical_repository_evidence_sha256",
                "repo_root_sha256",
                "load_report_context",
            )
        )
    )


def _is_payload_identity_contract(value: object) -> TypeGuard[_PayloadIdentityContract]:
    root_files = getattr(value, "ROOT_FILES", None)
    return (
        RENDERER.module_uses_sibling(value, "payload_identity.py")
        and isinstance(root_files, tuple)
        and all(isinstance(item, str) for item in root_files)
        and {"scripts/rir_previous.py", "scripts/rir_previous_renderer.py"} <= set(root_files)
        and callable(getattr(value, "functional_paths", None))
        and callable(getattr(value, "payload_sha256", None))
    )


REPORT_CONTEXT = cast(
    _ReportContextContract,
    RENDERER.load_local_module(
        "rir_report_context.py",
        "rir_report_context",
        "_rir_previous_report_context_",
        _is_report_context_contract,
        "report context",
    ),
)
PAYLOAD_IDENTITY = cast(
    _PayloadIdentityContract,
    RENDERER.load_local_module(
        "payload_identity.py",
        "payload_identity",
        "_rir_previous_payload_identity_",
        _is_payload_identity_contract,
        "payload identity",
    ),
)


@dataclass(frozen=True)
class PreviousLookupRequest:
    repo_root: Path
    request: str
    repository_evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.repo_root, Path):
            raise TypeError("previous lookup repo_root must be a Path")
        REPORT_CONTEXT.canonical_requirement_text(self.request)
        if not isinstance(self.repository_evidence, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.repository_evidence
        ):
            raise ValueError("previous lookup repository_evidence must contain nonblank text")
        REPORT_CONTEXT.canonical_repository_evidence_sha256(self.repository_evidence)


@dataclass(frozen=True)
class PreviousReportResult:
    status: Literal["none", "fresh", "stale", "ambiguous"]
    report_id: str | None
    revision: int | None
    markdown_sha256: str | None
    created_at: str | None
    baseline_commit: str | None
    changed_paths: tuple[str, ...]
    changed_count: int | None
    requirement_sha256: str
    source_inventory_sha256: str | None
    display_text: str | None
    reason: str
    elapsed_ms: int

    def __post_init__(self) -> None:
        if self.status not in STATUS_VALUES:
            raise ValueError("previous result status is invalid")
        if SHA256_PATTERN.fullmatch(self.requirement_sha256) is None:
            raise ValueError("previous result requirement digest is invalid")
        if not isinstance(self.changed_paths, tuple) or any(
            not isinstance(item, str) for item in self.changed_paths
        ):
            raise TypeError("previous result changed paths must be a text tuple")
        if tuple(sorted(set(self.changed_paths))) != self.changed_paths:
            raise ValueError("previous result changed paths must be unique and sorted")
        if self.changed_count is not None and (
            type(self.changed_count) is not int
            or self.changed_count < len(self.changed_paths)
            or self.changed_count < 0
        ):
            raise ValueError("previous result changed count is invalid")
        if type(self.elapsed_ms) is not int or self.elapsed_ms < 0:
            raise ValueError("previous result elapsed time is invalid")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("previous result reason is required")
        if self.status in {"none", "ambiguous"}:
            if any(
                value is not None
                for value in (
                    self.report_id,
                    self.revision,
                    self.markdown_sha256,
                    self.created_at,
                    self.baseline_commit,
                    self.source_inventory_sha256,
                    self.display_text,
                )
            ):
                raise ValueError("non-selected previous result cannot disclose report identity")
            if self.changed_paths or self.changed_count is not None:
                raise ValueError("non-selected previous result cannot disclose changed paths")
            return
        if self.report_id is None or REPORT_ID_PATTERN.fullmatch(self.report_id) is None:
            raise ValueError("selected previous result report ID is invalid")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("selected previous result revision is invalid")
        if self.markdown_sha256 is None or SHA256_PATTERN.fullmatch(self.markdown_sha256) is None:
            raise ValueError("selected previous result Markdown digest is invalid")
        if (
            self.baseline_commit is not None
            and COMMIT_PATTERN.fullmatch(self.baseline_commit) is None
        ):
            raise ValueError("selected previous result baseline commit is invalid")
        if self.source_inventory_sha256 is not None and (
            SHA256_PATTERN.fullmatch(self.source_inventory_sha256) is None
        ):
            raise ValueError("selected previous result source inventory digest is invalid")
        if self.display_text is not None and not self.display_text.strip():
            raise ValueError("selected previous result display text is invalid")


@dataclass(frozen=True)
class _CurrentCandidate:
    report_id: str
    revision: int
    markdown_sha256: str
    state: Mapping[str, object]
    requirement_sha256: str
    context: object | None


@dataclass(frozen=True)
class _GitCommandResult:
    returncode: int
    output: bytes


@dataclass(frozen=True)
class _GitSnapshot:
    available: bool
    commit: str | None
    changed_paths: tuple[str, ...]
    changed_count: int | None
    worktree_clean: bool
    submodules_clean: bool
    reason: str


def _root(value: Path) -> Path:
    path = Path(value)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError(f"repository root is unavailable: {error}") from error
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode) or not resolved.is_dir():
        raise ValueError("repository root must be a real directory")
    return resolved


def _plugin_root() -> Path:
    candidate = SCRIPT_DIR.parent
    if not (candidate / ".codex-plugin" / "plugin.json").is_file():
        candidate = SCRIPT_DIR.parents[2]
    return candidate


def _payload_sha256() -> str:
    return PAYLOAD_IDENTITY.payload_sha256(_plugin_root())


def _directory_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _open_child_directory(parent: int, name: str, *, missing_ok: bool = False) -> int | None:
    try:
        return os.open(name, _directory_flags(), dir_fd=parent)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise _UnsafeLookup(f"report directory is unavailable: {name}") from None
    except OSError as error:
        raise _UnsafeLookup(f"report directory is unsafe: {name}") from error


def _open_reports_directory(root: Path) -> int | None:
    root_fd: int | None = None
    state_fd: int | None = None
    try:
        root_fd = os.open(root, _directory_flags())
        state_fd = _open_child_directory(root_fd, ".requirements-impact-refiner", missing_ok=True)
        if state_fd is None:
            return None
        reports_fd = _open_child_directory(state_fd, "reports", missing_ok=True)
        return reports_fd
    except OSError as error:
        raise _UnsafeLookup("repository root is unsafe") from error
    finally:
        if state_fd is not None:
            os.close(state_fd)
        if root_fd is not None:
            os.close(root_fd)


def _report_ids(reports_fd: int, deadline: float) -> tuple[str, ...]:
    names: list[str] = []
    entries_seen = 0
    try:
        with os.scandir(reports_fd) as entries:
            for entry in entries:
                _check_deadline(deadline)
                entries_seen += 1
                if entries_seen > MAX_REPORT_ENTRIES:
                    raise _UnsafeLookup("report lineage inventory exceeds its entry limit")
                if REPORT_ID_PATTERN.fullmatch(entry.name) is None:
                    continue
                if len(names) >= MAX_REPORT_LINEAGES:
                    raise _UnsafeLookup("report lineage inventory exceeds its lineage limit")
                try:
                    if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                        raise _UnsafeLookup("report lineage path is unsafe")
                except OSError as error:
                    raise _UnsafeLookup("report lineage path is unsafe") from error
                names.append(entry.name)
    except OSError as error:
        raise _UnsafeLookup("cannot inspect report lineage inventory") from error
    return tuple(sorted(names))


def _read_regular(
    directory_fd: int,
    name: str,
    maximum: int,
    *,
    missing_ok: bool = False,
) -> bytes | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise _UnsafeLookup(f"report artifact is unavailable: {name}") from None
    except OSError as error:
        raise _UnsafeLookup(f"report artifact is unsafe: {name}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size < 0 or metadata.st_size > maximum:
            raise _UnsafeLookup(f"report artifact is unsafe: {name}")
        payload = bytearray()
        while len(payload) <= maximum:
            chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) > maximum:
            raise _UnsafeLookup(f"report artifact exceeds its byte limit: {name}")
        return bytes(payload)
    except OSError as error:
        raise _UnsafeLookup(f"cannot read report artifact: {name}") from error
    finally:
        os.close(descriptor)


def _json_object(payload: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise _UnsafeLookup(f"{label} is invalid") from error
    if not isinstance(value, dict):
        raise _UnsafeLookup(f"{label} is invalid")
    return value


def _context_artifact_present(report_fd: int, revision: int) -> bool:
    names = (
        f"revision-{revision:04d}.context-v2.json",
        f".revision-{revision:04d}.context-v2.json.pending",
    )
    for name in names:
        try:
            os.stat(name, dir_fd=report_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise _UnsafeLookup("report context identity is unsafe") from error
        return True
    return False


def _read_candidate(root: Path, reports_fd: int, report_id: str, deadline: float):
    report_fd = _open_child_directory(reports_fd, report_id)
    if report_fd is None:  # pragma: no cover - missing_ok=False is exhaustive
        raise _UnsafeLookup("report lineage is unavailable")
    try:
        pointer_payload = _read_regular(
            report_fd, "current.json", MAX_POINTER_BYTES, missing_ok=True
        )
        if pointer_payload is None:
            return None
        _check_deadline(deadline)
        pointer = _json_object(pointer_payload, "current report pointer")
        if set(pointer) != POINTER_FIELDS:
            raise _UnsafeLookup("current report pointer schema is invalid")
        schema_version = pointer.get("schema_version")
        revision = pointer.get("revision")
        markdown_sha256 = pointer.get("markdown_sha256")
        if (
            type(schema_version) is not int
            or schema_version != 1
            or pointer.get("report_id") != report_id
            or type(revision) is not int
            or revision < 1
            or not isinstance(markdown_sha256, str)
            or SHA256_PATTERN.fullmatch(markdown_sha256) is None
        ):
            raise _UnsafeLookup("current report pointer identity is invalid")
        state_name = f"revision-{revision:04d}.json"
        markdown_name = f"revision-{revision:04d}.md"
        if pointer.get("state") != state_name or pointer.get("markdown") != markdown_name:
            raise _UnsafeLookup("current report pointer revision paths are invalid")
        state_payload = _read_regular(report_fd, state_name, MAX_STATE_BYTES)
        markdown_payload = _read_regular(report_fd, markdown_name, MAX_MARKDOWN_BYTES)
        assert state_payload is not None and markdown_payload is not None
        if hashlib.sha256(markdown_payload).hexdigest() != markdown_sha256:
            raise _UnsafeLookup("current report Markdown digest is invalid")
        _check_deadline(deadline)
        try:
            state, errors = RENDERER.COMPACT_STATE.load_state_bytes(state_payload)
        except (RecursionError, ValueError, TypeError) as error:
            raise _UnsafeLookup("current compact state is invalid") from error
        if errors or state is None:
            raise _UnsafeLookup("current compact state is invalid")
        report = state.get("report")
        original = state.get("original_requirement")
        if (
            not isinstance(report, Mapping)
            or report.get("id") != report_id
            or report.get("revision") != revision
            or not isinstance(original, Mapping)
            or not isinstance(original.get("request"), str)
        ):
            raise _UnsafeLookup("current compact state identity is invalid")
        try:
            rendered_markdown = RENDERER.IMPACT_RENDERER.render_markdown(state).encode("utf-8")
        except (TypeError, ValueError, RecursionError) as error:
            raise _UnsafeLookup(
                "current compact state cannot reproduce immutable Markdown"
            ) from error
        if rendered_markdown != markdown_payload:
            raise _UnsafeLookup("current compact state does not match immutable Markdown")
        requirement_sha256 = REPORT_CONTEXT.canonical_requirement_sha256(
            cast(str, original["request"])
        )
        context_present = _context_artifact_present(report_fd, revision)
    finally:
        os.close(report_fd)
    _check_deadline(deadline)
    try:
        context = REPORT_CONTEXT.load_report_context(root, report_id, revision)
    except (OSError, TypeError, ValueError) as error:
        raise _UnsafeLookup("report context identity is unsafe") from error
    _check_deadline(deadline)
    if context_present and context is None:
        raise _UnsafeLookup("report context identity is unavailable")
    if context is not None:
        if (
            getattr(context, "schema_version", None) != 2
            or getattr(context, "report_id", None) != report_id
            or getattr(context, "revision", None) != revision
            or getattr(context, "markdown_sha256", None) != markdown_sha256
            or getattr(context, "state_sha256", None) != hashlib.sha256(state_payload).hexdigest()
            or getattr(context, "repo_root_sha256", None) != REPORT_CONTEXT.repo_root_sha256(root)
            or getattr(context, "requirement_sha256", None) != requirement_sha256
        ):
            raise _UnsafeLookup("report context does not match the selected revision")
    return _CurrentCandidate(
        report_id=report_id,
        revision=revision,
        markdown_sha256=markdown_sha256,
        state=state,
        requirement_sha256=requirement_sha256,
        context=context,
    )


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
        process.wait(timeout=0.01)
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
        process.wait(timeout=0.01)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _run_git_command(
    root: Path, arguments: tuple[str, ...], deadline: float
) -> _GitCommandResult | None:
    command = (
        "git",
        "--no-pager",
        "--no-replace-objects",
        "--literal-pathspecs",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "core.preloadIndex=false",
        "-c",
        "color.ui=false",
        "-c",
        "core.quotePath=true",
        "-c",
        "submodule.recurse=false",
        *arguments,
    )
    if deadline <= time.monotonic():
        return None
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
    selector = selectors.DefaultSelector()
    payload = bytearray()
    try:
        descriptor = process.stdout.fileno()
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
                raise _GitUnavailable("Git output exceeds its byte limit")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _stop_process(process)
            return None
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            _stop_process(process)
            return None
        return _GitCommandResult(returncode, bytes(payload))
    except OSError:
        _stop_process(process)
        return None
    finally:
        selector.close()
        process.stdout.close()


def _safe_changed_path(payload: bytes) -> str:
    if not payload or len(payload) > MAX_CHANGED_PATH_BYTES:
        raise _GitUnavailable("Git changed path is invalid")
    try:
        path = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise _GitUnavailable("Git changed path is not UTF-8") from error
    pure = PurePosixPath(path)
    if (
        pure.is_absolute()
        or path in {".", ".."}
        or ".." in pure.parts
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
    ):
        raise _GitUnavailable("Git changed path is unsafe")
    return path


def _status_paths(payload: bytes) -> tuple[str, ...]:
    if not payload:
        return ()
    records = payload.split(b"\0")
    if records[-1] != b"":
        raise _GitUnavailable("Git status output is incomplete")
    paths = set()
    for record in records[:-1]:
        if len(record) < 4 or record[2:3] != b" ":
            raise _GitUnavailable("Git status output is malformed")
        status_code = record[:2]
        if any(character not in b" MADTUXBRC?!" for character in status_code):
            raise _GitUnavailable("Git status code is invalid")
        if b"R" in status_code or b"C" in status_code:
            raise _GitUnavailable("Git rename output is unexpected")
        paths.add(_safe_changed_path(record[3:]))
        if len(paths) > MAX_CHANGED_PATHS:
            raise _GitUnavailable("Git changed path count exceeds its limit")
    return tuple(sorted(paths))


def _diff_paths(payload: bytes) -> tuple[str, ...]:
    if not payload:
        return ()
    records = payload.split(b"\0")
    if records[-1] != b"":
        raise _GitUnavailable("Git diff output is incomplete")
    paths = {_safe_changed_path(record) for record in records[:-1]}
    if len(paths) > MAX_CHANGED_PATHS:
        raise _GitUnavailable("Git changed path count exceeds its limit")
    return tuple(sorted(paths))


def _successful(result: _GitCommandResult | None, label: str) -> bytes:
    if result is None:
        raise _GitUnavailable(f"{label} timed out or is unavailable")
    if result.returncode != 0:
        raise _GitUnavailable(f"{label} failed")
    if b"\0" in result.output and label not in {
        "Git status",
        "Git diff",
        "Git index flags",
    }:
        raise _GitUnavailable(f"{label} output contains NUL")
    return result.output


def _decode_single_path(payload: bytes, label: str) -> Path:
    if b"\0" in payload:
        raise _GitUnavailable(f"{label} output contains NUL")
    try:
        value = payload.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise _GitUnavailable(f"{label} output is not UTF-8") from error
    if not value or "\n" in value or "\r" in value:
        raise _GitUnavailable(f"{label} output is invalid")
    return Path(value)


def _filesystem_git_dir(root: Path) -> Path:
    marker = root / ".git"
    try:
        metadata = marker.lstat()
    except OSError as error:
        raise _GitUnavailable("Git directory is unavailable") from error
    if stat.S_ISDIR(metadata.st_mode) and not marker.is_symlink():
        return marker.resolve()
    if not stat.S_ISREG(metadata.st_mode) or marker.is_symlink() or metadata.st_size > 4096:
        raise _GitUnavailable("Git directory marker is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(marker, flags)
        try:
            payload = os.read(descriptor, 4097)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise _GitUnavailable("Git directory marker is unavailable") from error
    try:
        text = payload.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise _GitUnavailable("Git directory marker is not UTF-8") from error
    prefix = "gitdir: "
    if not text.startswith(prefix) or "\n" in text or "\r" in text:
        raise _GitUnavailable("Git directory marker is invalid")
    value = Path(text[len(prefix) :])
    git_dir = value if value.is_absolute() else marker.parent / value
    try:
        resolved = git_dir.resolve(strict=True)
    except OSError as error:
        raise _GitUnavailable("Git directory is unavailable") from error
    if not resolved.is_dir():
        raise _GitUnavailable("Git directory is invalid")
    return resolved


def _read_git_control_file(path: Path, maximum: int) -> bytes | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise _GitUnavailable("Git control file is unavailable") from error
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
        raise _GitUnavailable("Git control file is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            payload = os.read(descriptor, maximum + 1)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise _GitUnavailable("Git control file is unavailable") from error
    if len(payload) > maximum:
        raise _GitUnavailable("Git control file exceeds its byte limit")
    return payload


def _filesystem_common_dir(git_dir: Path) -> Path:
    common_dir = git_dir
    commondir_payload = _read_git_control_file(git_dir / "commondir", 4096)
    if commondir_payload is not None:
        try:
            value = commondir_payload.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError as error:
            raise _GitUnavailable("Git common directory is not UTF-8") from error
        if not value or "\n" in value or "\r" in value:
            raise _GitUnavailable("Git common directory is invalid")
        candidate = Path(value)
        try:
            common_dir = (candidate if candidate.is_absolute() else git_dir / candidate).resolve(
                strict=True
            )
        except OSError as error:
            raise _GitUnavailable("Git common directory is unavailable") from error
        if not common_dir.is_dir():
            raise _GitUnavailable("Git common directory is invalid")
    return common_dir


def _filesystem_head(git_dir: Path) -> str:
    payload = _read_git_control_file(git_dir / "HEAD", 4096)
    if payload is None:
        raise _GitUnavailable("Git HEAD is unavailable")
    try:
        value = payload.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise _GitUnavailable("Git HEAD is not ASCII") from error
    if COMMIT_PATTERN.fullmatch(value) is not None:
        return value
    prefix = "ref: "
    if not value.startswith(prefix):
        raise _GitUnavailable("Git HEAD is invalid")
    reference = value[len(prefix) :]
    reference_path = PurePosixPath(reference)
    if (
        not reference.startswith("refs/")
        or reference_path.is_absolute()
        or ".." in reference_path.parts
    ):
        raise _GitUnavailable("Git HEAD reference is unsafe")
    common_dir = _filesystem_common_dir(git_dir)
    loose = _read_git_control_file(common_dir.joinpath(*reference_path.parts), 4096)
    if loose is not None:
        try:
            commit = loose.decode("ascii", errors="strict").strip()
        except UnicodeDecodeError as error:
            raise _GitUnavailable("Git HEAD reference is not ASCII") from error
        if COMMIT_PATTERN.fullmatch(commit) is None:
            raise _GitUnavailable("Git HEAD reference is invalid")
        return commit
    packed = _read_git_control_file(common_dir / "packed-refs", 4 * 1024 * 1024)
    if packed is None:
        raise _GitUnavailable("Git HEAD reference is unavailable")
    try:
        lines = packed.decode("ascii", errors="strict").splitlines()
    except UnicodeDecodeError as error:
        raise _GitUnavailable("Git packed refs are not ASCII") from error
    matches = [line.split(" ", 1)[0] for line in lines if line.endswith(" " + reference)]
    if len(matches) != 1 or COMMIT_PATTERN.fullmatch(matches[0]) is None:
        raise _GitUnavailable("Git HEAD reference is unavailable")
    return matches[0]


def _configured_worktree_matches(root: Path, git_dir: Path) -> bool:
    common_dir = _filesystem_common_dir(git_dir)
    configured_paths: list[Path] = []
    for config_path in (common_dir / "config", git_dir / "config.worktree"):
        payload = _read_git_control_file(config_path, 256 * 1024)
        if payload is None:
            continue
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise _GitUnavailable("Git local config is not UTF-8") from error
        section = ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("#", ";")):
                continue
            if line.startswith("["):
                if not line.endswith("]"):
                    raise _GitUnavailable("Git local config is malformed")
                section = line[1:-1].split(maxsplit=1)[0].strip('"').lower()
                if section in {"include", "includeif"}:
                    return False
                continue
            key, separator, value = line.partition("=")
            if section == "core" and key.strip().lower() == "worktree":
                if not separator:
                    return False
                configured = value.strip().strip('"')
                if not configured:
                    return False
                configured_path = Path(configured)
                configured_paths.append(
                    configured_path
                    if configured_path.is_absolute()
                    else config_path.parent / configured_path
                )
    return all(path.resolve() == root for path in configured_paths)


def _replacement_refs_present(git_dir: Path) -> bool:
    common_dir = _filesystem_common_dir(git_dir)
    replace_dir = common_dir / "refs" / "replace"
    try:
        metadata = replace_dir.lstat()
    except FileNotFoundError:
        metadata = None
    except OSError as error:
        raise _GitUnavailable("Git replacement refs are unavailable") from error
    if metadata is not None:
        if replace_dir.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise _GitUnavailable("Git replacement refs are unsafe")
        try:
            with os.scandir(replace_dir) as entries:
                if next(entries, None) is not None:
                    return True
        except OSError as error:
            raise _GitUnavailable("Git replacement refs are unavailable") from error
    packed = _read_git_control_file(common_dir / "packed-refs", 4 * 1024 * 1024)
    return packed is not None and b" refs/replace/" in packed


def _worktree_scope(root: Path, deadline: float) -> tuple[str, str]:
    git_dir = _filesystem_git_dir(root)
    scope = (f"--git-dir={git_dir}", f"--work-tree={root}")
    if not _configured_worktree_matches(root, git_dir):
        raise _GitUnavailable("Git core.worktree redirects outside the repository")
    return scope


def _index_flags_snapshot(root: Path, scope: tuple[str, str], deadline: float) -> bytes:
    payload = _successful(
        _run_git_command(root, (*scope, "ls-files", "-s", "-v", "-z"), deadline),
        "Git index flags",
    )
    if not payload:
        return payload
    records = payload.split(b"\0")
    if records[-1] != b"":
        raise _GitUnavailable("Git index flags output is incomplete")
    for record in records[:-1]:
        header, separator, path = record.partition(b"\t")
        fields = header.split(b" ")
        if not separator or len(fields) != 4 or len(fields[0]) != 1:
            raise _GitUnavailable("Git index flags output is malformed")
        _safe_changed_path(path)
        if fields[0] != b"H":
            raise _GitUnavailable("Git index visibility flags are present")
    return payload


def _gitlinks_from_index(payload: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for record in payload.split(b"\0")[:-1]:
        header, separator, path_payload = record.partition(b"\t")
        fields = header.split(b" ")
        if not separator or len(fields) != 4:
            raise _GitUnavailable("Git index output is malformed")
        if fields[1] != b"160000" or fields[3] != b"0":
            continue
        path = _safe_changed_path(path_payload)
        try:
            commit = fields[2].decode("ascii", errors="strict")
        except UnicodeDecodeError as error:
            raise _GitUnavailable("Git gitlink object is not ASCII") from error
        if COMMIT_PATTERN.fullmatch(commit) is None or path in result:
            raise _GitUnavailable("Git gitlink object is invalid")
        result[path] = commit
    return result


def _submodule_index_snapshots(
    root: Path, flags: bytes, deadline: float
) -> list[tuple[Path, tuple[str, str], str, bytes]]:
    snapshots: list[tuple[Path, tuple[str, str], str, bytes]] = []
    for path, expected_head in sorted(_gitlinks_from_index(flags).items()):
        submodule_root = (root / path).resolve()
        try:
            submodule_root.relative_to(root)
        except ValueError as error:
            raise _GitUnavailable("Git submodule path escapes the repository") from error
        submodule_scope = _worktree_scope(submodule_root, deadline)
        submodule_git_dir = Path(submodule_scope[0].split("=", 1)[1])
        if _filesystem_head(submodule_git_dir) != expected_head:
            raise _GitUnavailable("Git submodule HEAD does not match its gitlink")
        submodule_flags = _index_flags_snapshot(submodule_root, submodule_scope, deadline)
        snapshots.append((submodule_root, submodule_scope, expected_head, submodule_flags))
        snapshots.extend(_submodule_index_snapshots(submodule_root, submodule_flags, deadline))
    return snapshots


def _clean_submodule_paths(payload: bytes) -> tuple[str, ...] | None:
    paths: list[str] = []
    for line in payload.splitlines():
        if not line.startswith(b" "):
            return None
        rest = line[1:]
        commit, separator, path_and_description = rest.partition(b" ")
        if (
            not separator
            or COMMIT_PATTERN.fullmatch(commit.decode("ascii", errors="ignore")) is None
        ):
            raise _GitUnavailable("Git submodule status output is malformed")
        path_payload = path_and_description.split(b" (", 1)[0]
        path = _safe_changed_path(path_payload)
        if path not in paths:
            paths.append(path)
    return tuple(paths)


def _probe_git(root: Path, baseline_commit: str | None, deadline: float) -> _GitSnapshot:
    try:
        scope = _worktree_scope(root, deadline)
        git_dir = Path(scope[0].split("=", 1)[1])
        if _replacement_refs_present(git_dir):
            raise _GitUnavailable("Git replacement refs are present")
        commit = _filesystem_head(git_dir)
        status_payload = _successful(
            _run_git_command(
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
                deadline,
            ),
            "Git status",
        )
        status_paths = _status_paths(status_payload)
        index_flags_before = _index_flags_snapshot(root, scope, deadline)
        submodule_snapshots = _submodule_index_snapshots(root, index_flags_before, deadline)
        submodules_clean = True
        diff_paths: tuple[str, ...] = ()
        if baseline_commit is not None and baseline_commit != commit:
            diff_payload = _successful(
                _run_git_command(
                    root,
                    (
                        *scope,
                        "diff",
                        "--name-only",
                        "--no-renames",
                        "--no-ext-diff",
                        "--no-textconv",
                        "-z",
                        baseline_commit,
                        commit,
                        "--",
                    ),
                    deadline,
                ),
                "Git diff",
            )
            diff_paths = _diff_paths(diff_payload)
        final_status_payload = _successful(
            _run_git_command(
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
                deadline,
            ),
            "Git status",
        )
        if _status_paths(final_status_payload) != status_paths:
            raise _GitUnavailable("Git working tree changed during freshness proof")
        if _index_flags_snapshot(root, scope, deadline) != index_flags_before:
            raise _GitUnavailable("Git index changed during freshness proof")
        for submodule_root, submodule_scope, expected_head, submodule_flags in submodule_snapshots:
            submodule_git_dir = Path(submodule_scope[0].split("=", 1)[1])
            if _filesystem_head(submodule_git_dir) != expected_head:
                raise _GitUnavailable("Git submodule HEAD changed during freshness proof")
            if _index_flags_snapshot(submodule_root, submodule_scope, deadline) != submodule_flags:
                raise _GitUnavailable("Git submodule index changed during freshness proof")
        after_commit = _filesystem_head(git_dir)
        if after_commit != commit:
            raise _GitUnavailable("Git HEAD changed during freshness proof")
        changed = tuple(sorted(set(status_paths) | set(diff_paths)))
        if len(changed) > MAX_CHANGED_PATHS:
            raise _GitUnavailable("Git changed path count exceeds its limit")
        return _GitSnapshot(
            available=True,
            commit=commit,
            changed_paths=changed,
            changed_count=len(changed),
            worktree_clean=not status_paths,
            submodules_clean=submodules_clean,
            reason="Git freshness proof is complete",
        )
    except _GitUnavailable as error:
        return _GitSnapshot(
            available=False,
            commit=None,
            changed_paths=(),
            changed_count=None,
            worktree_clean=False,
            submodules_clean=False,
            reason=str(error),
        )


def _check_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise _LookupDeadline("previous lookup exceeded its operation deadline")


def _elapsed_ms(started_ns: int) -> int:
    return max(0, (time.monotonic_ns() - started_ns) // 1_000_000)


def _unselected(
    status: Literal["none", "ambiguous"],
    requirement_sha256: str,
    reason: str,
    started_ns: int,
) -> PreviousReportResult:
    return PreviousReportResult(
        status=status,
        report_id=None,
        revision=None,
        markdown_sha256=None,
        created_at=None,
        baseline_commit=None,
        changed_paths=(),
        changed_count=None,
        requirement_sha256=requirement_sha256,
        source_inventory_sha256=None,
        display_text=None,
        reason=reason,
        elapsed_ms=_elapsed_ms(started_ns),
    )


def _selected_result(
    status: Literal["fresh", "stale"],
    candidate: _CurrentCandidate,
    requirement_sha256: str,
    snapshot: _GitSnapshot,
    reason: str,
    started_ns: int,
) -> PreviousReportResult:
    context = candidate.context
    base = PreviousReportResult(
        status=status,
        report_id=candidate.report_id,
        revision=candidate.revision,
        markdown_sha256=candidate.markdown_sha256,
        created_at=getattr(context, "created_at", None),
        baseline_commit=getattr(context, "baseline_commit", None),
        changed_paths=snapshot.changed_paths,
        changed_count=snapshot.changed_count,
        requirement_sha256=requirement_sha256,
        source_inventory_sha256=getattr(context, "source_inventory_sha256", None),
        display_text=None,
        reason=reason,
        elapsed_ms=_elapsed_ms(started_ns),
    )
    try:
        display = RENDERER.render_previous(base, candidate.state)
    except (TypeError, ValueError, RecursionError):
        return _unselected(
            "none",
            requirement_sha256,
            "selected previous report could not be rendered safely",
            started_ns,
        )
    return replace(base, display_text=display, elapsed_ms=_elapsed_ms(started_ns))


def lookup_previous(request: PreviousLookupRequest) -> PreviousReportResult:
    """Select and compactly render one exact report lineage within 250 milliseconds."""

    if not isinstance(request, PreviousLookupRequest):
        raise TypeError("request must be PreviousLookupRequest")
    started_ns = time.monotonic_ns()
    deadline = time.monotonic() + OPERATION_TIMEOUT_SECONDS
    requirement_sha256 = REPORT_CONTEXT.canonical_requirement_sha256(request.request)
    repository_evidence_sha256 = REPORT_CONTEXT.canonical_repository_evidence_sha256(
        request.repository_evidence
    )
    root = _root(request.repo_root)
    try:
        payload_sha256 = _payload_sha256()
        _check_deadline(deadline)
        reports_fd = _open_reports_directory(root)
        if reports_fd is None:
            return _unselected(
                "none", requirement_sha256, "no previous report lineage exists", started_ns
            )
        try:
            report_ids = _report_ids(reports_fd, deadline)
            candidates = []
            for report_id in report_ids:
                candidate = _read_candidate(root, reports_fd, report_id, deadline)
                if candidate is not None:
                    candidates.append(candidate)
        finally:
            os.close(reports_fd)
    except _LookupDeadline:
        return _unselected(
            "none",
            requirement_sha256,
            "previous report identity could not be bounded",
            started_ns,
        )
    except (_UnsafeLookup, OSError, TypeError, ValueError):
        return _unselected(
            "none",
            requirement_sha256,
            "previous report identity is unsafe",
            started_ns,
        )
    matching = [
        candidate for candidate in candidates if candidate.requirement_sha256 == requirement_sha256
    ]
    missing_context = [candidate for candidate in matching if candidate.context is None]
    if missing_context:
        return _unselected(
            "none",
            requirement_sha256,
            "previous report context is unavailable",
            started_ns,
        )
    evidence_mismatch = [
        candidate
        for candidate in matching
        if getattr(candidate.context, "repository_evidence_sha256", None)
        != repository_evidence_sha256
    ]
    if evidence_mismatch:
        return _unselected(
            "none",
            requirement_sha256,
            "previous report evidence identity does not match",
            started_ns,
        )
    incompatible = [
        candidate
        for candidate in matching
        if candidate.context is not None
        and getattr(candidate.context, "payload_sha256", None) != payload_sha256
    ]
    if incompatible:
        return _unselected(
            "none",
            requirement_sha256,
            "previous report payload identity does not match",
            started_ns,
        )
    matching = [candidate for candidate in matching if candidate not in incompatible]
    if not matching:
        return _unselected(
            "none",
            requirement_sha256,
            "no previous report lineage matches the normalized requirement",
            started_ns,
        )
    if len(matching) != 1:
        return _unselected(
            "ambiguous",
            requirement_sha256,
            "multiple previous report lineages match the normalized requirement",
            started_ns,
        )
    candidate = matching[0]
    baseline_commit = getattr(candidate.context, "baseline_commit", None)
    snapshot = _probe_git(root, baseline_commit, deadline)
    context = candidate.context
    if context is None:  # pragma: no cover - selected candidates require a v2 context
        return _unselected(
            "none", requirement_sha256, "previous report context is unavailable", started_ns
        )
    if not getattr(context, "source_inventory_available", False) or not getattr(
        context, "source_inventory_complete", False
    ):
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            "source inventory is incomplete",
            started_ns,
        )
    if not getattr(context, "baseline_clean", False) or baseline_commit is None:
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            "report baseline was not clean",
            started_ns,
        )
    if not getattr(context, "source_inventory_git_tracked_only", False):
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            "source inventory is not proven Git-tracked",
            started_ns,
        )
    if not snapshot.available:
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            snapshot.reason,
            started_ns,
        )
    if not snapshot.worktree_clean:
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            "Git working tree contains tracked or untracked changes",
            started_ns,
        )
    if not snapshot.submodules_clean:
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            "Git submodule state is not clean",
            started_ns,
        )
    if snapshot.commit != baseline_commit:
        return _selected_result(
            "stale",
            candidate,
            requirement_sha256,
            snapshot,
            "Git HEAD differs from the report baseline",
            started_ns,
        )
    return _selected_result(
        "fresh",
        candidate,
        requirement_sha256,
        snapshot,
        "repository and report identities match a clean Git baseline",
        started_ns,
    )
