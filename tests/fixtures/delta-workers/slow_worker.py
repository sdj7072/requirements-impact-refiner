#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def frame(result):
    payload = canonical({"result": result})
    return f"{len(payload):08x}\n".encode("ascii") + payload


parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--sha256", required=True)
parser.add_argument("--token", required=True)
parser.add_argument("--parent-pid", type=int, required=True)
args = parser.parse_args()
payload = args.input.read_bytes()
if hashlib.sha256(payload).hexdigest() != args.sha256:
    raise SystemExit(2)
request = json.loads(payload)
if request.get("worker_token") != args.token or request.get("parent_pid") != args.parent_pid:
    raise SystemExit(2)
scenario = os.environ.get("RIR_DELTA_TEST_SCENARIO", "after-fallback")

changed_paths = request.get("changed_paths", [])
fallback = {
    "status": "partial",
    "scan_id": "1" * 32,
    "receipt_id": "2" * 32,
    "receipt_sha256": "3" * 64,
    "display_text": "trusted previous\n\ndelta deadline fallback",
    "risk_level": "unknown",
    "paths": [],
    "frontier": [
        {
            "id": "DELTA-FRONTIER-001",
            "node": "previous-node",
            "reason": "delta revalidation deadline exhausted",
            "risk_domains": ["regression"],
        }
    ],
    "candidates": [],
    "elapsed_ms": 0,
    "cache_status": "bypassed",
    "can_promote": False,
    "previous_report_id": request.get("previous_report_id"),
    "previous_revision": request.get("previous_revision"),
    "changed_paths": changed_paths,
    "changed_count": len(changed_paths),
    "previous_display_text": "trusted previous",
}

root = Path(request["repo_root"])
token = request["worker_token"]
if scenario == "persist":
    scans = root / ".requirements-impact-refiner" / "scans"
    scans.mkdir(parents=True, exist_ok=True)
    (scans / f".partial.{token}.tmp").write_bytes(b'{"partial":')
elif scenario == "descendant":
    marker = Path(os.environ["RIR_DELTA_TEST_MARKER"])
    pid_path = Path(os.environ["RIR_DELTA_TEST_CHILD_PID"])
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import pathlib,sys,time; time.sleep(2); "
                "pathlib.Path(sys.argv[1]).write_text('survived')"
            ),
            str(marker),
        ]
    )
    pid_path.write_text(str(child.pid), encoding="ascii")
elif scenario == "partial-frame":
    partial = dict(fallback)
    partial["display_text"] = "x" * 100_000
    framed = frame(partial)
    os.write(sys.stdout.fileno(), framed[:70_000])
    time.sleep(10)
elif scenario == "overflow":
    chunk = b"x" * 65_536
    for _ in range(66):
        os.write(sys.stdout.fileno(), chunk)
    time.sleep(10)
elif scenario == "garbage":
    os.write(sys.stdout.fileno(), b"not-a-frame")
    raise SystemExit(0)
elif scenario == "extra-frame":
    os.write(sys.stdout.fileno(), frame(fallback) + frame(fallback))
    raise SystemExit(0)

if scenario in {
    "lookup",
    "hash",
    "provider",
    "persist",
    "render",
    "descendant",
    "after-fallback",
}:
    time.sleep(10)

final = dict(fallback)
final["status"] = "complete"
final["can_promote"] = True
final["receipt_sha256"] = hashlib.sha256(b"complete").hexdigest()
os.write(sys.stdout.fileno(), frame(final))
