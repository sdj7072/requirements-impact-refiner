#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path


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
}


def build_parser():
    parser = argparse.ArgumentParser(description="Controller-first impact refinement")
    subparsers = parser.add_subparsers(dest="command", required=True)
    begin = subparsers.add_parser("begin")
    begin.add_argument("--repo-root", type=Path, required=True)
    begin.add_argument("--input", type=Path, required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--repo-root", type=Path, required=True)
    finalize.add_argument("--draft-id", required=True)
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
    analysis = _read_object(
        args.input, rir_controller.MAX_FINALIZE_BYTES, "finalize input"
    )
    result = rir_controller.finalize_refinement(
        rir_controller.FinalizeRequest(
            repo_root=args.repo_root,
            draft_id=args.draft_id,
            analysis=analysis,
        )
    )
    print(result.display_text, end="" if result.display_text.endswith("\n") else "\n")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _begin(args) if args.command == "begin" else _finalize(args)
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (TypeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
