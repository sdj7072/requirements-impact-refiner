#!/usr/bin/env python3
"""Run the pinned, read-only ast-grep provider canary."""

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
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import BinaryIO, TypeVar, cast

CANARY_COMMAND = (
    "ast-grep",
    "scan",
    "--json=stream",
    "--config",
    "evals/ast-grep-canary/sgconfig.yml",
    "evals/ast-grep-canary/fixture",
)
MAX_STDOUT_BYTES = 512 * 1024
MAX_JSONL_LINE_BYTES = 64 * 1024
MAX_JSONL_ROWS = 128
MAX_JSON_DEPTH = 64
PROCESS_TIMEOUT_SECONDS = 10.0
MAX_EXPECTED_BYTES = 128 * 1024
MAX_SOURCE_BYTES = 128 * 1024
MAX_GIT_STATUS_BYTES = 2 * 1024 * 1024
MAX_GIT_STDERR_BYTES = 64 * 1024
MAX_WORKING_FILE_BYTES = 8 * 1024 * 1024
MAX_WORKING_CONTENT_BYTES = 32 * 1024 * 1024
GIT_STATUS_TIMEOUT_SECONDS = 5.0
GIT_STATUS_COMMAND = (
    "git",
    "status",
    "--porcelain=v1",
    "-z",
    "--untracked-files=all",
)
_SCAN_FIELDS = {
    "text",
    "range",
    "file",
    "lines",
    "charCount",
    "language",
    "ruleId",
    "severity",
    "note",
    "message",
    "labels",
}


class CanaryError(RuntimeError):
    """The provider canary failed closed."""


T = TypeVar("T")


def _load_sibling(name: str, filename: str):
    path = Path(__file__).resolve().with_name(filename)
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ImportError("cannot load fixed canary dependency")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


PROVIDERS = _load_sibling("_ast_grep_canary_providers", "graph_providers.py")
ADAPTER = _load_sibling("_ast_grep_canary_adapter", "graph_adapter_ast_grep.py")


def validate_read_only_command(arguments: Sequence[str]) -> tuple[str, ...]:
    command = tuple(arguments)
    fixed = {("--version",), CANARY_COMMAND, CANARY_COMMAND[1:]}
    if command in fixed:
        return command
    if (
        len(command) == 6
        and command[:4] == ("--json=stream", "--lang", "python", "--pattern")
        and isinstance(command[4], str)
        and command[4]
        and len(command[4].encode("utf-8")) <= 256
        and "\x00" not in command[4]
    ):
        try:
            _safe_relative(command[5])
        except CanaryError:
            pass
        else:
            return command
    raise CanaryError("ast-grep canary command must remain read-only")


def _json_depth(text: str) -> int:
    depth = 0
    peak = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            peak = max(peak, depth)
        elif character in "]}":
            depth = max(0, depth - 1)
    return peak


def parse_jsonl(output: str) -> tuple[dict[str, object], ...]:
    if not isinstance(output, str) or len(output.encode("utf-8")) > MAX_STDOUT_BYTES:
        raise CanaryError("ast-grep JSONL output exceeds the byte bound")
    lines = output.splitlines()
    if len(lines) > MAX_JSONL_ROWS:
        raise CanaryError("ast-grep JSONL output exceeds the row bound")
    rows = []
    for line in lines:
        if not line.strip():
            continue
        if len(line.encode("utf-8")) > MAX_JSONL_LINE_BYTES:
            raise CanaryError("ast-grep JSONL row exceeds the byte bound")
        if _json_depth(line) > MAX_JSON_DEPTH:
            raise CanaryError("ast-grep JSONL row exceeds the depth bound")
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, RecursionError) as error:
            raise CanaryError("ast-grep JSONL output is malformed") from error
        if not isinstance(row, dict):
            raise CanaryError("ast-grep JSONL row must be an object")
        rows.append(row)
    return tuple(rows)


def run_bounded(executable: Path, arguments: Sequence[str], cwd: Path):
    resolved = Path(executable).resolve(strict=True)
    safe_arguments = validate_read_only_command(arguments)
    specification = PROVIDERS.ProviderSpec("ast-grep", resolved)
    deadline = PROVIDERS.Deadline(time, PROCESS_TIMEOUT_SECONDS)
    observation = PROVIDERS.run_provider(specification, safe_arguments, cwd, deadline)
    if observation.status != "ready":
        raise CanaryError(observation.detail or "ast-grep provider process failed")
    if len(observation.stdout.encode("utf-8")) > MAX_STDOUT_BYTES:
        raise CanaryError("ast-grep stdout exceeds the canary byte bound")
    if len(observation.stderr.encode("utf-8")) > MAX_JSONL_LINE_BYTES:
        raise CanaryError("ast-grep stderr exceeds the canary byte bound")
    if (
        not isinstance(observation.executable_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", observation.executable_sha256) is None
    ):
        raise CanaryError("ast-grep executable digest is invalid")
    return observation


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()


def _bounded_capture(
    command: Sequence[str],
    cwd: Path,
    *,
    stdout_limit: int,
    stderr_limit: int,
    timeout: float,
) -> tuple[bytes, bytes]:
    process = subprocess.Popen(
        tuple(command),
        cwd=str(cwd),
        env={
            "PATH": str(Path(command[0]).parent),
            "GIT_OPTIONAL_LOCKS": "0",
            "LC_ALL": "C",
            "TMPDIR": tempfile.gettempdir(),
        },
        shell=False,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True,
    )
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
                file_object = key.fileobj
                if not hasattr(file_object, "fileno"):
                    raise CanaryError("working state process stream is invalid")
                stream = cast(BinaryIO, file_object)
                chunk = os.read(stream.fileno(), 64 * 1024)
                if not chunk:
                    selector.unregister(stream)
                    continue
                buffer = buffers[stream]
                allowed = max(0, key.data - len(buffer))
                buffer.extend(chunk[:allowed])
                if len(chunk) > allowed:
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
    except OSError as error:
        _terminate_process_group(process)
        process.wait(timeout=1)
        raise CanaryError("repository working state snapshot failed") from error
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
    if timed_out:
        raise CanaryError("repository working state snapshot timed out")
    if exceeded:
        raise CanaryError("repository working state snapshot exceeded output bounds")
    stdout = bytes(buffers[process.stdout])
    stderr = bytes(buffers[process.stderr])
    if returncode != 0 or stderr:
        raise CanaryError("repository working state snapshot failed")
    return stdout, stderr


def capture_working_state(root: Path) -> bytes:
    git = shutil.which("git")
    if git is None:
        raise CanaryError("repository working state snapshot failed: git not found")
    try:
        stdout, _ = _bounded_capture(
            (git, *GIT_STATUS_COMMAND[1:]),
            Path(root),
            stdout_limit=MAX_GIT_STATUS_BYTES,
            stderr_limit=MAX_GIT_STDERR_BYTES,
            timeout=GIT_STATUS_TIMEOUT_SECONDS,
        )
    except (OSError, ValueError) as error:
        raise CanaryError("repository working state snapshot failed") from error
    paths = _porcelain_paths(stdout)
    rows = []
    total = 0
    for raw_path in sorted(set(paths)):
        identity, size = _working_path_identity(Path(root), raw_path)
        total += size
        if total > MAX_WORKING_CONTENT_BYTES:
            raise CanaryError("repository working state content exceeds byte bounds")
        rows.append(len(raw_path).to_bytes(4, "big") + raw_path + identity)
    return stdout + b"RIR-WORKTREE-CONTENT-v1\x00" + b"".join(rows)


def _porcelain_paths(payload: bytes) -> tuple[bytes, ...]:
    records = payload.split(b"\x00")
    if records[-1] != b"":
        raise CanaryError("repository working state porcelain is malformed")
    paths = []
    index = 0
    while index < len(records) - 1:
        record = records[index]
        if len(record) < 4 or record[2:3] != b" ":
            raise CanaryError("repository working state porcelain is malformed")
        status = record[:2]
        path = record[3:]
        if not path or b"\x00" in path:
            raise CanaryError("repository working state porcelain path is invalid")
        paths.append(path)
        if b"R" in status or b"C" in status:
            index += 1
            if index >= len(records) - 1 or not records[index]:
                raise CanaryError("repository working state rename is malformed")
            paths.append(records[index])
        index += 1
    return tuple(paths)


def _working_path_identity(root: Path, raw_path: bytes) -> tuple[bytes, int]:
    text = os.fsdecode(raw_path)
    relative = PurePosixPath(text)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise CanaryError("repository working state path is unsafe")
    path = root.joinpath(*relative.parts)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return b"MISSING\x00", 0
    except OSError as error:
        raise CanaryError("repository working state content cannot be inspected") from error
    header = (
        f"{metadata.st_mode}:{metadata.st_nlink}:{metadata.st_size}:{metadata.st_mtime_ns}:"
    ).encode("ascii")
    if stat.S_ISLNK(metadata.st_mode):
        try:
            target = os.readlink(path).encode(sys.getfilesystemencoding(), "surrogateescape")
        except OSError as error:
            raise CanaryError("repository working state symlink cannot be inspected") from error
        return b"LINK:" + header + hashlib.sha256(target).digest(), len(target)
    if stat.S_ISDIR(metadata.st_mode):
        return b"DIRECTORY:" + header, 0
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_WORKING_FILE_BYTES:
        raise CanaryError("repository working state content exceeds byte bounds")
    descriptor = None
    try:
        descriptor = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if _file_identity(opened) != _file_identity(metadata):
            raise CanaryError("repository working state content changed while opening")
        digest = hashlib.sha256()
        total = 0
        while total <= MAX_WORKING_FILE_BYTES:
            chunk = os.read(descriptor, min(64 * 1024, MAX_WORKING_FILE_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        if total > MAX_WORKING_FILE_BYTES:
            raise CanaryError("repository working state content exceeds byte bounds")
        if _file_identity(after) != _file_identity(opened):
            raise CanaryError("repository working state content changed during read")
        return b"FILE:" + header + digest.digest(), total
    except CanaryError:
        raise
    except OSError as error:
        raise CanaryError("repository working state content cannot be read") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def guard_working_state(root: Path, operation: Callable[[], T]) -> T:
    before = capture_working_state(root)
    operation_error = None
    try:
        result = operation()
    except Exception as error:
        operation_error = error
        result = None
    after = capture_working_state(root)
    if after != before:
        raise CanaryError("ast-grep canary changed repository working state") from operation_error
    if operation_error is not None:
        raise operation_error
    return result  # type: ignore[return-value]


def _safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise CanaryError("ast-grep match path is unsafe")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CanaryError("ast-grep match path is unsafe")
    return path.as_posix()


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def _source_bytes(
    root: Path,
    relative: str,
    *,
    before_read: Callable[[], object] | None = None,
    read_chunk: Callable[[int, int], bytes] = os.read,
) -> bytes:
    safe = _safe_relative(relative)
    base = Path(root)
    descriptors = []
    links = []
    file_descriptor = None
    try:
        root_metadata = base.lstat()
        if base.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
            raise CanaryError("ast-grep match source root is unsafe")
        root_descriptor = os.open(
            str(base),
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        descriptors.append(root_descriptor)
        if _file_identity(os.fstat(root_descriptor)) != _file_identity(root_metadata):
            raise CanaryError("ast-grep match source root changed while opening")
        current = root_descriptor
        parts = PurePosixPath(safe).parts
        for part in parts[:-1]:
            metadata = os.stat(part, dir_fd=current, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise CanaryError("ast-grep match source parent is unsafe")
            descriptor = os.open(
                part,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current,
            )
            descriptors.append(descriptor)
            opened = os.fstat(descriptor)
            if _file_identity(opened) != _file_identity(metadata):
                raise CanaryError("ast-grep match source parent changed while opening")
            links.append((current, part, descriptor, metadata))
            current = descriptor
        filename = parts[-1]
        metadata = os.stat(filename, dir_fd=current, follow_symlinks=False)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size > MAX_SOURCE_BYTES
        ):
            raise CanaryError("ast-grep match source is unsafe")
        file_descriptor = os.open(
            filename,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=current,
        )
        opened = os.fstat(file_descriptor)
        if _file_identity(opened) != _file_identity(metadata):
            raise CanaryError("ast-grep match source changed while opening")
        if before_read is not None:
            before_read()
        payload = bytearray()
        try:
            while len(payload) <= MAX_SOURCE_BYTES:
                chunk = read_chunk(
                    file_descriptor,
                    min(64 * 1024, MAX_SOURCE_BYTES + 1 - len(payload)),
                )
                if not chunk:
                    break
                payload.extend(chunk)
        except OSError as error:
            raise CanaryError("ast-grep match source cannot be read safely") from error
        if len(payload) > MAX_SOURCE_BYTES:
            raise CanaryError("ast-grep match source exceeds the byte bound")
        after = os.fstat(file_descriptor)
        path_after = os.stat(filename, dir_fd=current, follow_symlinks=False)
        if not (
            _file_identity(metadata)
            == _file_identity(opened)
            == _file_identity(after)
            == _file_identity(path_after)
        ):
            raise CanaryError("ast-grep match source changed during bounded read")
        for parent, name, descriptor, before in links:
            if not (
                _file_identity(before)
                == _file_identity(os.fstat(descriptor))
                == _file_identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
            ):
                raise CanaryError("ast-grep match source parent changed during bounded read")
        if _file_identity(base.lstat()) != _file_identity(root_metadata):
            raise CanaryError("ast-grep match source root changed during bounded read")
        return bytes(payload)
    except CanaryError:
        raise
    except (OSError, ValueError, RuntimeError) as error:
        raise CanaryError("ast-grep match source cannot be opened safely") from error
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _match_range(value: object) -> tuple[int, int, int, int, int, int]:
    if not isinstance(value, dict) or set(value) != {"byteOffset", "start", "end"}:
        raise CanaryError("ast-grep match range schema drifted")
    byte_offset = value["byteOffset"]
    start = value["start"]
    end = value["end"]
    if not isinstance(byte_offset, dict) or set(byte_offset) != {"start", "end"}:
        raise CanaryError("ast-grep byte range schema drifted")
    if not isinstance(start, dict) or set(start) != {"line", "column"}:
        raise CanaryError("ast-grep start range schema drifted")
    if not isinstance(end, dict) or set(end) != {"line", "column"}:
        raise CanaryError("ast-grep end range schema drifted")
    values = (
        byte_offset["start"],
        byte_offset["end"],
        start["line"],
        start["column"],
        end["line"],
        end["column"],
    )
    if any(type(item) is not int or item < 0 for item in values):
        raise CanaryError("ast-grep match range values are invalid")
    if values[1] <= values[0] or (values[4], values[5]) <= (values[2], values[3]):
        raise CanaryError("ast-grep match range is empty or reversed")
    return values


def project_scan_matches(
    rows: Sequence[Mapping[str, object]], root: Path
) -> tuple[dict[str, object], ...]:
    projected = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != _SCAN_FIELDS:
            raise CanaryError("ast-grep scan output schema drifted")
        relative = _safe_relative(row["file"])
        text = row["text"]
        if (
            not isinstance(text, str)
            or not text
            or len(text.encode("utf-8")) > MAX_JSONL_LINE_BYTES
        ):
            raise CanaryError("ast-grep scan match text is invalid")
        byte_start, byte_end, start_line, start_column, end_line, end_column = _match_range(
            row["range"]
        )
        payload = _source_bytes(root, relative)
        try:
            excerpt = payload[byte_start:byte_end].decode("utf-8", errors="strict")
            source = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise CanaryError("ast-grep scan source is not UTF-8") from error
        physical_lines = source.splitlines()
        if (
            excerpt != text
            or start_line >= len(physical_lines)
            or end_line >= len(physical_lines)
            or start_line != end_line
            or physical_lines[start_line][start_column:end_column] != text
            or row["lines"] != physical_lines[start_line]
        ):
            raise CanaryError("ast-grep scan match does not bind to its source")
        counts = row["charCount"]
        if not isinstance(counts, dict) or counts != {
            "leading": start_column,
            "trailing": len(physical_lines[end_line]) - end_column,
        }:
            raise CanaryError("ast-grep scan character counts drifted")
        if (
            row["language"] != "Python"
            or row["ruleId"] != "python-import"
            or row["severity"] != "warning"
            or row["note"] is not None
            or row["message"] != "Python import is structurally visible"
        ):
            raise CanaryError("ast-grep scan rule metadata drifted")
        labels = row["labels"]
        if (
            not isinstance(labels, list)
            or len(labels) != 1
            or not isinstance(labels[0], dict)
            or labels[0] != {"text": text, "range": row["range"], "style": "primary"}
        ):
            raise CanaryError("ast-grep scan labels drifted")
        projected.append(
            {
                "rule_id": row["ruleId"],
                "file": relative,
                "text": text,
                "start": [start_line, start_column],
                "end": [end_line, end_column],
                "source_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return tuple(sorted(projected, key=lambda item: (str(item["file"]), str(item["text"]))))


def _load_expected(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    if len(payload) > MAX_EXPECTED_BYTES:
        raise CanaryError("canary expected data exceeds the byte bound")
    try:
        text = payload.decode("utf-8", errors="strict")
        if _json_depth(text) > MAX_JSON_DEPTH:
            raise CanaryError("canary expected data exceeds the depth bound")
        expected = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise CanaryError("canary expected data is malformed") from error
    if not isinstance(expected, dict) or set(expected) != {"version", "scan_matches", "adapter"}:
        raise CanaryError("canary expected data schema drifted")
    return expected


def _jsonable(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _jsonable_rows(value: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    return [{str(key): _jsonable(item) for key, item in row.items()} for row in value]


def resolve_executable(configured: str) -> Path:
    candidate = Path(configured)
    located = None
    if candidate.is_absolute() or len(candidate.parts) > 1:
        located = candidate
    else:
        interpreter_sibling = Path(sys.executable).absolute().with_name(configured)
        if interpreter_sibling.is_file():
            located = interpreter_sibling
        else:
            discovered = shutil.which(configured)
            if discovered is not None:
                located = Path(discovered)
    if located is None:
        raise CanaryError("ast-grep executable not found")
    try:
        resolved = located.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise CanaryError("ast-grep executable not found") from error
    if not resolved.is_file():
        raise CanaryError("ast-grep executable not found")
    return resolved


def _execute_canary(executable: Path, root: Path) -> dict[str, object]:
    expected_path = root / "evals/ast-grep-canary/expected.json"
    fixture_root = root / "evals/ast-grep-canary/fixture"
    expected = _load_expected(expected_path)

    version_observation = run_bounded(executable, ("--version",), root)
    version = version_observation.stdout.strip()
    if version != "ast-grep 0.45.0" or version != expected["version"]:
        raise CanaryError("ast-grep 0.45.0 is required")
    executable_sha256 = version_observation.executable_sha256

    scan_arguments = CANARY_COMMAND[1:]
    scan_observation = run_bounded(executable, scan_arguments, root)
    if scan_observation.executable_sha256 != executable_sha256:
        raise CanaryError("ast-grep executable changed between canary commands")
    scan_rows = parse_jsonl(scan_observation.stdout)
    scan_matches = project_scan_matches(scan_rows, root)
    if list(scan_matches) != expected["scan_matches"]:
        raise CanaryError("ast-grep structural matches differ from literal expected data")

    adapter_expected = expected["adapter"]
    if not isinstance(adapter_expected, dict) or set(adapter_expected) != {
        "seed",
        "nodes",
        "edges",
    }:
        raise CanaryError("canary adapter expected data schema drifted")
    seed = adapter_expected["seed"]
    if not isinstance(seed, dict) or set(seed) != {"term", "location"}:
        raise CanaryError("canary adapter seed schema drifted")
    term = seed["term"]
    location = seed["location"]
    if not isinstance(term, str) or not isinstance(location, str):
        raise CanaryError("canary adapter seed is invalid")

    adapter_arguments = ("--json=stream", "--lang", "python", "--pattern", term, location)
    direct_observation = run_bounded(executable, adapter_arguments, fixture_root)
    if direct_observation.executable_sha256 != executable_sha256:
        raise CanaryError("ast-grep executable changed before adapter comparison")
    parse_jsonl(direct_observation.stdout)
    direct_digest = hashlib.sha256(direct_observation.stdout.encode("utf-8")).hexdigest()

    fingerprint = ADAPTER.source_fingerprint(fixture_root)
    if not isinstance(fingerprint, str):
        raise CanaryError("adapter fixture source fingerprint is unavailable")
    probe = ADAPTER.ProviderProbe(
        "ast-grep",
        "ready",
        "structural-inferred",
        executable,
        version,
        executable_sha256,
        ("json-stream", "language", "pattern"),
        repo_root=fixture_root.resolve(),
        metadata={"source_fingerprint": fingerprint},
    )
    result = ADAPTER.query(
        probe,
        (SimpleNamespace(term=term, location=location),),
        ADAPTER.PROVIDERS.Deadline(time, PROCESS_TIMEOUT_SECONDS),
        None,
    )
    if result.status != "ready" or result.confidence != "structural-inferred":
        raise CanaryError(result.detail or "ast-grep adapter comparison failed")
    if result.raw_receipt_sha256 != (direct_digest,):
        raise CanaryError("ast-grep adapter provenance digest differs from direct output")
    nodes = _jsonable_rows(result.nodes)
    edges = _jsonable_rows(result.edges)
    if nodes != adapter_expected["nodes"] or edges != adapter_expected["edges"]:
        raise CanaryError("ast-grep adapter output differs from literal expected data")
    expected_source_hashes = {
        row["source_sha256"]
        for row in (*adapter_expected["nodes"], *adapter_expected["edges"])
        if isinstance(row, dict) and isinstance(row.get("source_sha256"), str)
    }
    observed_source_hashes = {
        row["source_sha256"]
        for row in (*nodes, *edges)
        if isinstance(row, dict) and isinstance(row.get("source_sha256"), str)
    }
    if observed_source_hashes != expected_source_hashes:
        raise CanaryError("ast-grep adapter source provenance differs from expected data")
    return {
        "status": "ok",
        "version": version,
        "matches": len(scan_matches),
        "adapter": {
            "nodes": len(result.nodes),
            "edges": len(result.edges),
            "receipts": len(result.raw_receipt_sha256),
        },
        "executable_sha256": executable_sha256,
    }


def run_canary(executable: Path, root: Path | None = None) -> dict[str, object]:
    repository = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    return guard_working_state(repository, lambda: _execute_canary(executable, repository))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-command", action="store_true")
    parser.add_argument("--ast-grep", default="ast-grep")
    arguments, extra = parser.parse_known_args(argv)
    try:
        if extra:
            validate_read_only_command(extra)
            raise CanaryError("unsupported canary arguments")
        validate_read_only_command(CANARY_COMMAND)
        if arguments.print_command:
            print(" ".join(CANARY_COMMAND))
            return 0
        executable = resolve_executable(arguments.ast_grep)
        summary = run_canary(executable)
    except CanaryError as error:
        print(f"ast-grep canary: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
