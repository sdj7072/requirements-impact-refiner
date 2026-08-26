#!/usr/bin/env python3
"""Private subprocess boundary for one whole-call stale delta revalidation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Mapping
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import rir_controller  # noqa: E402

MAX_INPUT_BYTES = 512 * 1024
MAX_CONTROL_FRAME_BYTES = 1024
MAX_FALLBACK_FRAME_BYTES = 4 * 1024 * 1024
MAX_RESULT_FRAME_BYTES = 4 * 1024 * 1024
INPUT_KEYS = {
    "schema_version",
    "repo_root",
    "change_request",
    "evidence",
    "audience_override",
    "previous_report_id",
    "previous_revision",
    "changed_paths",
    "operation_started",
    "max_seconds",
    "worker_token",
    "parent_pid",
}


def _read_input(path: Path, expected_sha256: str) -> dict[str, object]:
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size <= 0
            or metadata.st_size > MAX_INPUT_BYTES
        ):
            raise ValueError("delta worker input artifact is unsafe")
        payload = bytearray()
        while len(payload) <= MAX_INPUT_BYTES:
            chunk = os.read(descriptor, min(65_536, MAX_INPUT_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    raw = bytes(payload)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("delta worker input digest is invalid")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("delta worker input is invalid") from error
    canonical = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if not isinstance(value, dict) or set(value) != INPUT_KEYS or canonical != raw:
        raise ValueError("delta worker input contract is invalid")
    return value


def _emit(kind: str, payload: Mapping[str, object], token: str) -> None:
    maximum = {
        "control": MAX_CONTROL_FRAME_BYTES,
        "trusted_fallback": MAX_FALLBACK_FRAME_BYTES,
        "result": MAX_RESULT_FRAME_BYTES,
    }.get(kind)
    if maximum is None or re.fullmatch(r"[0-9a-f]{32}", token) is None:
        raise ValueError("delta worker output frame type is invalid")
    body = json.dumps(
        {"kind": kind, "payload": payload, "token": token},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if not body or len(body) > maximum:
        raise ValueError("delta worker output frame exceeds its byte limit")
    frame = f"{len(body):08x}\n".encode("ascii") + body
    offset = 0
    while offset < len(frame):
        written = os.write(sys.stdout.fileno(), frame[offset:])
        if written <= 0:
            raise OSError("delta worker output pipe closed")
        offset += written


def _request(value: Mapping[str, object]):
    evidence = value["evidence"]
    changed_paths = value["changed_paths"]
    if (
        value["schema_version"] != 1
        or not isinstance(value["repo_root"], str)
        or not isinstance(value["change_request"], str)
        or not isinstance(evidence, list)
        or any(not isinstance(row, str) for row in evidence)
        or (
            value["audience_override"] is not None
            and not isinstance(value["audience_override"], str)
        )
        or not isinstance(value["previous_report_id"], str)
        or re.fullmatch(r"RPT-\d{3}", value["previous_report_id"]) is None
        or type(value["previous_revision"]) is not int
        or not isinstance(changed_paths, list)
        or any(not isinstance(path, str) for path in changed_paths)
    ):
        raise ValueError("delta worker request is invalid")
    return rir_controller.ScanRequest(
        Path(value["repo_root"]),
        value["change_request"],
        tuple(evidence),
        value["audience_override"],
        value["previous_report_id"],
        value["previous_revision"],
        tuple(changed_paths),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    args = parser.parse_args(argv)
    if (
        re.fullmatch(r"[0-9a-f]{64}", args.sha256) is None
        or re.fullmatch(r"[0-9a-f]{32}", args.token) is None
        or args.parent_pid != os.getppid()
    ):
        raise ValueError("delta worker input digest is invalid")
    value = _read_input(args.input, args.sha256)
    operation_started = value["operation_started"]
    max_seconds = value["max_seconds"]
    if (
        not isinstance(operation_started, (int, float))
        or isinstance(operation_started, bool)
        or not isinstance(max_seconds, (int, float))
        or isinstance(max_seconds, bool)
        or max_seconds <= 0
        or max_seconds > 3
        or value["worker_token"] != args.token
        or value["parent_pid"] != args.parent_pid
    ):
        raise ValueError("delta worker deadline is invalid")
    rir_controller._configure_delta_worker_runtime(args.token)
    request = _request(value)

    def control(effective_max_seconds: int) -> None:
        _emit(
            "control",
            {"effective_max_seconds": effective_max_seconds},
            args.token,
        )

    def fallback(result: Mapping[str, object]) -> None:
        _emit("trusted_fallback", result, args.token)

    scan = rir_controller._scan_impact_in_process(
        request,
        operation_started=float(operation_started),
        _worker_control_callback=control,
        _worker_fallback_callback=fallback,
    )
    result = rir_controller._scan_result_mapping(scan)
    _emit("result", result, args.token)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError):
        print("delta worker operation failed", file=sys.stderr)
        raise SystemExit(1) from None
