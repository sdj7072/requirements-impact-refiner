"""Derive controller-call evidence from immutable Codex JSONL events."""

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Sequence, Tuple, Union


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
    display_text_sha256: Tuple[str, ...]
    final_output_sha256: Tuple[str, ...]

    def to_json(self) -> str:
        payload = asdict(self)
        payload["errors"] = list(self.errors)
        payload["tool_order"] = list(self.tool_order)
        payload["display_text_sha256"] = list(self.display_text_sha256)
        payload["final_output_sha256"] = list(self.final_output_sha256)
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


def _attempted_calls(streams: Sequence[str]):
    calls = {}
    order = []
    malformed = False
    for stream_index, stream in enumerate(streams):
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
                not isinstance(item, dict)
                or item.get("type") != "mcp_tool_call"
                or item.get("server") != _SERVER
                or item.get("tool") not in _TOOLS
            ):
                continue
            identifier = item.get("id")
            if not isinstance(identifier, str) or not identifier:
                malformed = True
                continue
            scoped_identifier = (stream_index, identifier)
            if scoped_identifier not in calls:
                order.append(scoped_identifier)
            calls[scoped_identifier] = item
    return tuple(calls[identifier] for identifier in order), malformed


def analyze_controller_trace(
    jsonl_streams: Sequence[str],
    final_output: Union[str, Sequence[str]],
    *,
    expected_turns: int,
) -> ControllerEvidence:
    """Require exact begin/finalize pairs and renderer-owned final bytes."""
    if isinstance(expected_turns, bool) or not isinstance(expected_turns, int) or expected_turns < 0:
        raise ValueError("expected_turns must be a non-negative integer")
    final_outputs = (final_output,) if isinstance(final_output, str) else tuple(final_output)
    if any(not isinstance(value, str) for value in final_outputs):
        raise TypeError("final outputs must be strings")
    if expected_turns > 0 and len(final_outputs) != expected_turns:
        raise ValueError("final outputs must match expected turns")
    calls, malformed = _attempted_calls(jsonl_streams)
    order = tuple(call["tool"] for call in calls)
    begins = tuple(call for call in calls if call["tool"] == "rir_begin")
    finalizes = tuple(call for call in calls if call["tool"] == "rir_finalize")
    errors = []
    expected_order = _TOOLS * expected_turns
    if malformed:
        errors.append("controller JSONL is malformed")
    if order != expected_order:
        errors.append("controller tool order or count does not match expected turns")
    if any(
        call.get("status") != "completed" or call.get("error") is not None
        for call in calls
    ):
        errors.append("controller tool attempt failed or did not complete")

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
            call.get("status") == "completed"
            and
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
        compared_displays = ()
    else:
        compared_displays = tuple(displays)
        display_matches = (
            len(compared_displays) == expected_turns
            and all(isinstance(value, str) for value in compared_displays)
            and compared_displays == final_outputs
        )
    if not draft_match:
        errors.append("controller draft IDs do not match")
    if not succeeded:
        errors.append("controller finalize did not succeed")
    if not display_matches:
        errors.append("controller display text differs from final output")

    final_digests = tuple(
        hashlib.sha256(value.encode("utf-8")).hexdigest()
        for value in final_outputs
    )
    display_digests = tuple(
        hashlib.sha256(value.encode("utf-8")).hexdigest()
        for value in compared_displays
        if isinstance(value, str)
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
        display_text_sha256=display_digests,
        final_output_sha256=final_digests,
    )
