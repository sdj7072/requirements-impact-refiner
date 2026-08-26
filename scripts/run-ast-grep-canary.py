#!/usr/bin/env python3
"""Run the pinned, read-only ast-grep provider canary."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

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
_FORBIDDEN_FLAGS = frozenset({"interactive", "rewrite", "update", "update-all"})
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
    for argument in command:
        flag = argument.split("=", 1)[0]
        if flag in {"-i", "-U", "-r"} or flag.lstrip("-").lower() in _FORBIDDEN_FLAGS:
            raise CanaryError("ast-grep canary command must remain read-only")
    return command


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


def _safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise CanaryError("ast-grep match path is unsafe")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CanaryError("ast-grep match path is unsafe")
    return path.as_posix()


def _source_bytes(root: Path, relative: str) -> bytes:
    candidate = root / relative
    try:
        metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        common = os.path.commonpath((str(root.resolve()), str(resolved)))
    except (OSError, ValueError, RuntimeError) as error:
        raise CanaryError("ast-grep match source is unavailable") from error
    if (
        candidate.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or common != str(root.resolve())
        or metadata.st_size > MAX_SOURCE_BYTES
    ):
        raise CanaryError("ast-grep match source is unsafe")
    payload = candidate.read_bytes()
    if len(payload) > MAX_SOURCE_BYTES:
        raise CanaryError("ast-grep match source exceeds the byte bound")
    return payload


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


def _canary_manifest(root: Path) -> dict[str, str]:
    relative_paths = (
        "requirements-provider-canary.txt",
        "evals/ast-grep-canary/sgconfig.yml",
        "evals/ast-grep-canary/rules/imports.yml",
        "evals/ast-grep-canary/expected.json",
        "evals/ast-grep-canary/fixture/imports.py",
    )
    return {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in relative_paths
    }


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


def run_canary(executable: Path) -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    expected_path = root / "evals/ast-grep-canary/expected.json"
    fixture_root = root / "evals/ast-grep-canary/fixture"
    before = _canary_manifest(root)
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
    if _canary_manifest(root) != before:
        raise CanaryError("ast-grep canary mutated repository inputs")
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
