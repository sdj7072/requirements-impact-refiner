#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import compact_state
import impact_renderer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render or convert an impact report")
    parser.add_argument("state", nargs="?", type=Path)
    parser.add_argument("--from-markdown", type=Path)
    parser.add_argument("--format", choices=("markdown", "compact"), default="markdown")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser


def _publish(text: str, output: Path | None, force: bool) -> int:
    if output is None:
        print(text, end="" if text.endswith("\n") else "\n")
        return 0
    if output.exists() and not force:
        print(f"output already exists: {output}", file=sys.stderr)
        return 2
    try:
        output.write_text(text, encoding="utf-8")
    except OSError as error:
        print(f"cannot write output: {error}", file=sys.stderr)
        return 2
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if (args.state is None) == (args.from_markdown is None):
        print("provide exactly one state path or --from-markdown", file=sys.stderr)
        return 2
    try:
        if args.from_markdown is not None:
            markdown = args.from_markdown.read_text(encoding="utf-8")
            state, errors = impact_renderer.state_from_markdown(markdown)
            if errors or state is None:
                for error in errors:
                    print(error, file=sys.stderr)
                return 1
            rendered = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        else:
            assert args.state is not None
            state, errors = compact_state.load_state_bytes(args.state.read_bytes())
            if errors or state is None:
                for error in errors:
                    print(error, file=sys.stderr)
                return 1
            rendered = (
                impact_renderer.render_markdown(state)
                if args.format == "markdown"
                else impact_renderer.render_compact(state)
            )
    except (OSError, UnicodeDecodeError) as error:
        print(f"cannot read input: {error}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    return _publish(rendered, args.output, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
