"""Extract the final assistant text of a subagent JSONL transcript.

Reads the transcript from the tail so a large file never enters the
orchestrator's context; only the final text block is written out.
"""
import json
import sys
from pathlib import Path


def final_text(path: Path) -> str:
    best = None
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = row.get("message") or {}
            if row.get("type") != "assistant":
                continue
            for block in message.get("content") or []:
                if block.get("type") == "text" and block.get("text", "").strip():
                    best = block["text"]
    if best is None:
        raise SystemExit(f"no assistant text in {path}")
    return best


if __name__ == "__main__":
    transcript, destination = Path(sys.argv[1]), Path(sys.argv[2])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(final_text(transcript))
    print(f"{destination} <- {transcript.name} ({destination.stat().st_size}B)")
