"""Derive controller-call evidence from immutable Codex JSONL events."""

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Optional, Sequence, Tuple


_DRAFT_ID = re.compile(r"\A[0-9a-f]{32}\Z")
_TOOLS = ("rir_begin", "rir_finalize")
_SERVER = "requirements-impact-refiner"


@dataclass(frozen=True)
class ControllerEvidence:
    valid: bool
    errors: Tuple[str, ...]
    tool_order: Tuple[str, ...]
    begin_calls: int
    finalize_calls: int
    draft_ids_match: bool
    finalize_succeeded: bool
    display_text_matches: bool
    display_text_sha256: Optional[str]
    final_output_sha256: str

    def to_json(self) -> str:
        payload = asdict(self)
        payload["errors"] = list(self.errors)
        payload["tool_order"] = list(self.tool_order)
        return json.dumps(payload, sort_keys=True) + "\n"


def _structured(result):
    if not isinstance(result, dict):
        return None
    snake = result.get("structured_content")
    camel = result.get("structuredContent")
    if snake is not None and camel is not None and snake != camel:
        return None
    value = snake if snake is not None else camel
    return value if isinstance(value, dict) else None


def _completed_calls(streams: Sequence[str]):
    calls = []
    malformed = False
    for stream in streams:
        for line in stream.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                malformed = True
                continue
            item = event.get("item") if isinstance(event, dict) else None
            if (
                event.get("type") != "item.completed"
                or not isinstance(item, dict)
                or item.get("type") != "mcp_tool_call"
                or item.get("server") != _SERVER
                or item.get("tool") not in _TOOLS
                or item.get("status") != "completed"
            ):
                continue
            calls.append(item)
    return tuple(calls), malformed


def analyze_controller_trace(
    jsonl_streams: Sequence[str], final_output: str, *, expected_turns: int
) -> ControllerEvidence:
    """Require exact begin/finalize pairs and renderer-owned final bytes."""
    if isinstance(expected_turns, bool) or not isinstance(expected_turns, int) or expected_turns < 0:
        raise ValueError("expected_turns must be a non-negative integer")
    if not isinstance(final_output, str):
        raise TypeError("final_output must be a string")
    calls, malformed = _completed_calls(jsonl_streams)
    order = tuple(call["tool"] for call in calls)
    begins = tuple(call for call in calls if call["tool"] == "rir_begin")
    finalizes = tuple(call for call in calls if call["tool"] == "rir_finalize")
    errors = []
    expected_order = _TOOLS * expected_turns
    if malformed:
        errors.append("controller JSONL is malformed")
    if order != expected_order:
        errors.append("controller tool order or count does not match expected turns")

    begin_ids = []
    for call in begins:
        result = _structured(call.get("result"))
        value = result.get("draft_id") if result is not None else None
        begin_ids.append(value if isinstance(value, str) and _DRAFT_ID.fullmatch(value) else None)
    finalize_ids = []
    finalize_success = []
    displays = []
    for call in finalizes:
        arguments = call.get("arguments")
        draft_id = arguments.get("draft_id") if isinstance(arguments, dict) else None
        finalize_ids.append(draft_id if isinstance(draft_id, str) and _DRAFT_ID.fullmatch(draft_id) else None)
        result = _structured(call.get("result"))
        display = result.get("display_text") if result is not None else None
        displays.append(display if isinstance(display, str) else None)
        finalize_success.append(
            call.get("error") is None
            and result is not None
            and result.get("status") == "published"
            and isinstance(display, str)
        )

    draft_match = (
        len(begin_ids) == expected_turns
        and len(finalize_ids) == expected_turns
        and all(value is not None for value in begin_ids + finalize_ids)
        and begin_ids == finalize_ids
    )
    succeeded = len(finalize_success) == expected_turns and all(finalize_success)
    if expected_turns == 0:
        display_matches = not calls
        draft_match = not calls
        succeeded = not calls
        display = None
    else:
        display = displays[-1] if displays else None
        display_matches = isinstance(display, str) and display == final_output
    if not draft_match:
        errors.append("controller draft IDs do not match")
    if not succeeded:
        errors.append("controller finalize did not succeed")
    if not display_matches:
        errors.append("controller display text differs from final output")

    final_digest = hashlib.sha256(final_output.encode("utf-8")).hexdigest()
    display_digest = (
        hashlib.sha256(display.encode("utf-8")).hexdigest()
        if isinstance(display, str)
        else None
    )
    unique_errors = tuple(sorted(set(errors)))
    return ControllerEvidence(
        valid=not unique_errors,
        errors=unique_errors,
        tool_order=order,
        begin_calls=len(begins),
        finalize_calls=len(finalizes),
        draft_ids_match=draft_match,
        finalize_succeeded=succeeded,
        display_text_matches=display_matches,
        display_text_sha256=display_digest,
        final_output_sha256=final_digest,
    )
