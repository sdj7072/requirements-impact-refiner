#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import report_store


def build_parser():
    parser = argparse.ArgumentParser(description="Publish a validated impact revision")
    parser.add_argument("state", type=Path)
    parser.add_argument("--repo-root", type=Path, required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        state_bytes = args.state.read_bytes()
    except OSError as error:
        print(f"cannot read state: {error}", file=sys.stderr)
        return 2
    try:
        published = report_store.publish_revision(args.repo_root, state_bytes)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (report_store.ReportStoreUnavailable, report_store.UnsafeReportPath) as error:
        print(str(error), file=sys.stderr)
        print(json.dumps({"status": "unavailable", "fallback": "full-inline"}, sort_keys=True))
        return 2
    except (report_store.LineageError, FileExistsError) as error:
        print(str(error), file=sys.stderr)
        return 1
    root = args.repo_root.resolve()
    result = {
        "status": "published",
        "report_id": published.report_id,
        "revision": published.revision,
        "state": published.state_path.relative_to(root).as_posix(),
        "markdown": published.markdown_path.relative_to(root).as_posix(),
        "markdown_sha256": published.markdown_sha256,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
