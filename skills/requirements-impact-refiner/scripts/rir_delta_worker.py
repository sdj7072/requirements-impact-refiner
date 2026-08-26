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


def _emit(kind: str, result: Mapping[str, object]) -> None:
    payload = json.dumps(
        {"kind": kind, "result": result},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    sys.stdout.write(payload + "\n")
    sys.stdout.flush()


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
    args = parser.parse_args(argv)
    if (
        os.environ.get("RIR_DELTA_WORKER") != "1"
        or re.fullmatch(r"[0-9a-f]{32}", os.environ.get("RIR_DELTA_WORKER_TOKEN", "")) is None
    ):
        raise ValueError("delta worker environment is invalid")
    if re.fullmatch(r"[0-9a-f]{64}", args.sha256) is None:
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
    ):
        raise ValueError("delta worker deadline is invalid")
    request = _request(value)
    result = rir_controller._scan_impact_in_process(
        request,
        operation_started=float(operation_started),
        fallback_callback=lambda fallback: _emit("fallback", fallback),
    )
    _emit("result", rir_controller._scan_result_mapping(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError):
        print("delta worker operation failed", file=sys.stderr)
        raise SystemExit(1) from None
