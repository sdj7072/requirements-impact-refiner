#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re


def _json_depth(text: str) -> int:
    """Peak bracket nesting outside strings. CPython 3.13 no longer raises
    RecursionError from json.loads at hostile depths, so the bound must be
    explicit rather than borrowed from the interpreter."""
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
            if depth > peak:
                peak = depth
        elif char in "]}":
            depth = max(0, depth - 1)
    return peak


_MAX_JSON_DEPTH = 64
import os
import stat
import sys
from pathlib import Path, PurePosixPath

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import rir_controller

BEGIN_KEYS = {
    "request",
    "repository_evidence",
    "adapter",
    "audience_override",
    "delivery_override",
    "scan_id",
}
PREVIOUS_KEYS = {"request", "repository_evidence", "report_id"}
PREVIOUS_REQUIRED_KEYS = {"request", "repository_evidence"}
SCAN_KEYS = {
    "change_request",
    "evidence",
    "presentation",
    "previous_report_id",
    "previous_revision",
    "changed_paths",
}
TRACE_KEYS = {"seeds"}
TRACE_SEED_KEYS = {"term", "location"}


def build_parser():
    parser = argparse.ArgumentParser(description="Controller-first impact refinement")
    subparsers = parser.add_subparsers(dest="command", required=True)
    begin = subparsers.add_parser("begin")
    begin.add_argument("--repo-root", type=Path, required=True)
    begin.add_argument("--input", type=Path, required=True)
    begin.add_argument("--scan-id")
    previous = subparsers.add_parser("previous")
    previous.add_argument("--repo-root", type=Path, required=True)
    previous.add_argument("--input", type=Path, required=True)
    previous.add_argument("--report-id")
    scan = subparsers.add_parser("scan")
    scan.add_argument("--repo-root", type=Path, required=True)
    scan.add_argument("--input", type=Path, required=True)
    scan.add_argument("--json", action="store_true")
    trace = subparsers.add_parser("trace")
    trace.add_argument("--repo-root", type=Path, required=True)
    trace.add_argument("--draft-id", required=True)
    trace.add_argument("--input", type=Path, required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--repo-root", type=Path, required=True)
    finalize.add_argument("--draft-id", required=True)
    finalize.add_argument("--graph-receipt-id")
    finalize.add_argument("--input", type=Path, required=True)
    return parser


def _read_object(path: Path, maximum: int, label: str):
    descriptor = None
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError("input must be a regular non-symlink file")
        if metadata.st_size > maximum:
            unit = "256 KiB" if maximum == rir_controller.MAX_BEGIN_BYTES else "2 MiB"
            raise ValueError(f"{label} exceeds {unit}")
        raw = os.read(descriptor, maximum + 1)
        if len(raw) > maximum:
            unit = "256 KiB" if maximum == rir_controller.MAX_BEGIN_BYTES else "2 MiB"
            raise ValueError(f"{label} exceeds {unit}")
        text = raw.decode("utf-8")
        if _json_depth(text) > _MAX_JSON_DEPTH:
            raise json.JSONDecodeError("json nesting depth exceeded", text, 0)
        value = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise OSError(f"cannot read input: {error}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not isinstance(value, dict):
        raise ValueError("input must contain a JSON object")
    return value


def _begin(args) -> int:
    value = _read_object(args.input, rir_controller.MAX_BEGIN_BYTES, "begin input")
    unknown = sorted(set(value) - BEGIN_KEYS)
    if unknown:
        raise ValueError(f"unknown begin key {unknown[0]}")
    missing = sorted({"request", "repository_evidence", "adapter"} - set(value))
    if missing:
        raise ValueError(f"missing begin key {missing[0]}")
    if not isinstance(value["repository_evidence"], list):
        raise ValueError("repository_evidence must be an array")
    result = rir_controller.begin_refinement(
        rir_controller.BeginRequest(
            repo_root=args.repo_root,
            request=value["request"],
            repository_evidence=tuple(value["repository_evidence"]),
            adapter=value["adapter"],
            audience_override=value.get("audience_override"),
            delivery_override=value.get("delivery_override"),
            scan_id=args.scan_id or value.get("scan_id"),
        )
    )
    payload = {
        "draft_id": result.draft_id,
        "draft_path": result.draft_path.relative_to(args.repo_root.resolve()).as_posix(),
        "report_id": result.report_id,
        "revision": result.revision,
        "previous_sha256": result.previous_sha256,
        "audience": result.settings["audience"],
        "delivery": result.settings["delivery"],
        "prior_state": result.prior_state,
        "prior_key_map": result.prior_key_map,
        "scan_id": result.scan_id,
        "graph_receipt_id": result.graph_receipt_id,
        "repository_evidence": value["repository_evidence"],
        "analysis_contract": json.loads(
            (SCRIPT_DIR.parent / "schemas" / "controller-analysis.schema.json").read_text(
                encoding="utf-8"
            )
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def _finalize(args) -> int:
    analysis = _read_object(args.input, rir_controller.MAX_FINALIZE_BYTES, "finalize input")
    result = rir_controller.finalize_refinement(
        rir_controller.FinalizeRequest(
            repo_root=args.repo_root,
            draft_id=args.draft_id,
            analysis=analysis,
            graph_receipt_id=args.graph_receipt_id,
        )
    )
    print(result.display_text, end="" if result.display_text.endswith("\n") else "\n")
    return 0


def _previous(args) -> int:
    value = _read_object(args.input, rir_controller.MAX_BEGIN_BYTES, "previous input")
    unknown = sorted(set(value) - PREVIOUS_KEYS)
    if unknown:
        raise ValueError(f"unknown previous key {unknown[0]}")
    missing = sorted(PREVIOUS_REQUIRED_KEYS - set(value))
    if missing:
        raise ValueError(f"missing previous key {missing[0]}")
    evidence = value["repository_evidence"]
    if not isinstance(evidence, list):
        raise ValueError("previous repository_evidence must be an array")
    input_report_id = value.get("report_id")
    if (
        args.report_id is not None
        and input_report_id is not None
        and args.report_id != input_report_id
    ):
        raise ValueError("previous report_id flag conflicts with input")
    report_id = args.report_id or input_report_id
    result = rir_controller.lookup_previous(
        rir_controller.PreviousLookupRequest(
            repo_root=args.repo_root,
            request=value["request"],
            repository_evidence=tuple(evidence),
            report_id=report_id,
        )
    )
    payload = {
        "status": result.status,
        "report_id": result.report_id,
        "revision": result.revision,
        "markdown_sha256": result.markdown_sha256,
        "created_at": result.created_at,
        "baseline_commit": result.baseline_commit,
        "changed_paths": list(result.changed_paths),
        "changed_count": result.changed_count,
        "requirement_sha256": result.requirement_sha256,
        "source_inventory_sha256": result.source_inventory_sha256,
        "display_text": result.display_text,
        "reason": result.reason,
        "elapsed_ms": result.elapsed_ms,
        "candidates": [
            {
                "report_id": candidate.report_id,
                "revision": candidate.revision,
                "created_at": candidate.created_at,
            }
            for candidate in result.candidates
        ],
    }
    performance_metrics = getattr(result, "performance_metrics", None)
    metrics_mapping = getattr(performance_metrics, "to_mapping", None)
    if callable(metrics_mapping):
        payload["performance_metrics"] = metrics_mapping()
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def _scan(args) -> int:
    value = _read_object(args.input, rir_controller.MAX_BEGIN_BYTES, "scan input")
    unknown = sorted(set(value) - SCAN_KEYS)
    if unknown:
        raise ValueError(f"unknown scan key {unknown[0]}")
    if "change_request" not in value:
        raise ValueError("missing scan key change_request")
    evidence = value.get("evidence", [])
    if not isinstance(evidence, list):
        raise ValueError("scan evidence must be an array")
    delta_keys = {"previous_report_id", "previous_revision", "changed_paths"}
    present_delta = set(value) & delta_keys
    if present_delta and present_delta != delta_keys:
        raise ValueError("scan delta fields must be provided together")
    changed_paths = value.get("changed_paths", [])
    if present_delta:
        report_id = value["previous_report_id"]
        revision = value["previous_revision"]
        if not isinstance(report_id, str) or re.fullmatch(r"RPT-\d{3}", report_id) is None:
            raise ValueError("scan previous_report_id is invalid")
        if type(revision) is not int or revision < 1:
            raise ValueError("scan previous_revision is invalid")
        if not isinstance(changed_paths, list) or len(changed_paths) > 4096:
            raise ValueError("scan changed_paths must be a bounded array")
        for path in changed_paths:
            if not isinstance(path, str) or len(path.encode("utf-8")) > 4096:
                raise ValueError("scan changed path is invalid")
            pure = PurePosixPath(path)
            if (
                not path
                or "\\" in path
                or "\x00" in path
                or pure.is_absolute()
                or pure.as_posix() != path
                or any(part in {"", ".", ".."} for part in pure.parts)
            ):
                raise ValueError("scan changed path is invalid")
        if sorted(set(changed_paths)) != changed_paths:
            raise ValueError("scan changed_paths must be unique and sorted")
    result = rir_controller.scan_impact(
        rir_controller.ScanRequest(
            args.repo_root,
            value["change_request"],
            tuple(evidence),
            value.get("presentation"),
            value.get("previous_report_id"),
            value.get("previous_revision"),
            tuple(changed_paths),
        )
    )
    if args.json:
        payload = {
            "status": result.status,
            "scan_id": result.scan_id,
            "receipt_id": result.receipt_id,
            "receipt_sha256": result.receipt_sha256,
            "display_text": result.display_text,
            "risk_level": result.risk_level,
            "paths": list(result.paths),
            "frontier": list(result.frontier),
            "candidates": list(result.candidates),
            "elapsed_ms": result.elapsed_ms,
            "cache_status": result.cache_status,
            "can_promote": result.can_promote,
        }
        performance_metrics = getattr(result, "performance_metrics", None)
        metrics_mapping = getattr(performance_metrics, "to_mapping", None)
        if callable(metrics_mapping):
            payload["performance_metrics"] = metrics_mapping()
        previous_report_id = getattr(result, "previous_report_id", None)
        if previous_report_id is not None:
            payload.update(
                {
                    "previous_report_id": previous_report_id,
                    "previous_revision": getattr(result, "previous_revision", None),
                    "changed_paths": list(getattr(result, "changed_paths", ())),
                    "changed_count": getattr(result, "changed_count", None),
                    "previous_display_text": getattr(result, "previous_display_text", None),
                }
            )
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(result.display_text, end="" if result.display_text.endswith("\n") else "\n")
    return 0


def _trace(args) -> int:
    value = _read_object(args.input, rir_controller.MAX_TRACE_BYTES, "trace input")
    unknown = sorted(set(value) - TRACE_KEYS)
    if unknown:
        raise ValueError(f"unknown trace key {unknown[0]}")
    if "seeds" not in value:
        raise ValueError("missing trace key seeds")
    rows = value["seeds"]
    if not isinstance(rows, list):
        raise ValueError("trace seeds must be an array")
    seeds = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("trace seed must be an object")
        missing = sorted(TRACE_SEED_KEYS - set(row))
        extra = sorted(set(row) - TRACE_SEED_KEYS)
        if missing:
            raise ValueError(f"missing trace seed key {missing[0]}")
        if extra:
            raise ValueError(f"unknown trace seed key {extra[0]}")
        seeds.append(rir_controller.TraceSeed(row["term"], row["location"]))
    result = rir_controller.trace_impact(
        rir_controller.TraceRequest(args.repo_root, args.draft_id, tuple(seeds))
    )
    root = args.repo_root.resolve()
    payload = {
        "receipt_id": result.receipt_id,
        "receipt_path": result.receipt_path.relative_to(root).as_posix(),
        "receipt_sha256": result.receipt_sha256,
        "compact_graph": result.compact_graph,
        "budget_status": result.budget_status,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "previous":
            return _previous(args)
        if args.command == "scan":
            return _scan(args)
        if args.command == "begin":
            return _begin(args)
        if args.command == "trace":
            return _trace(args)
        return _finalize(args)
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (TypeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
