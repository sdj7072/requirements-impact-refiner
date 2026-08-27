"""Derive controller-call evidence from immutable Codex JSONL events."""

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Optional, Union

_DRAFT_ID = re.compile(r"\A[0-9a-f]{32}\Z")
_TOOLS = ("rir_begin", "rir_trace_impact", "rir_finalize")
_SERVER = "requirements-impact-refiner"


@dataclass(frozen=True)
class ControllerEvidence:
    valid: bool
    errors: tuple[str, ...]
    tool_order: tuple[str, ...]
    begin_calls: int
    trace_calls: int
    finalize_calls: int
    draft_ids_match: bool
    trace_succeeded: bool
    finalize_receipt_ids_match: bool
    finalize_succeeded: bool
    duplicate_or_error_calls: bool
    display_text_exact_match: bool
    display_text_presentation_equivalent: bool
    display_comparison: str
    display_text_sha256: tuple[str, ...]
    final_output_sha256: tuple[str, ...]
    installed_payload_sha256: tuple[str, ...]
    draft_ids: tuple[str, ...]
    receipt_ids: tuple[str, ...]
    receipt_paths: tuple[str, ...]
    receipt_sha256: tuple[str, ...]
    trace_compact_graph_sha256: tuple[str, ...]
    trace_request_sha256: tuple[str, ...]
    trace_seeds: tuple[tuple[tuple[str, Optional[str]], ...], ...]

    def to_json(self) -> str:
        payload = asdict(self)
        payload["errors"] = list(self.errors)
        payload["tool_order"] = list(self.tool_order)
        payload["display_text_sha256"] = list(self.display_text_sha256)
        payload["final_output_sha256"] = list(self.final_output_sha256)
        payload["installed_payload_sha256"] = list(self.installed_payload_sha256)
        payload["draft_ids"] = list(self.draft_ids)
        payload["receipt_ids"] = list(self.receipt_ids)
        payload["receipt_paths"] = list(self.receipt_paths)
        payload["receipt_sha256"] = list(self.receipt_sha256)
        payload["trace_compact_graph_sha256"] = list(self.trace_compact_graph_sha256)
        payload["trace_request_sha256"] = list(self.trace_request_sha256)
        payload["trace_seeds"] = [
            [{"term": term, "location": location} for term, location in seeds]
            for seeds in self.trace_seeds
        ]
        return json.dumps(payload, sort_keys=True) + "\n"


def _structured(result: object) -> Optional[dict[str, object]]:
    if not isinstance(result, dict):
        return None
    snake = result.get("structured_content")
    camel = result.get("structuredContent")
    if snake is not None and camel is not None and snake != camel:
        return None
    value = snake if snake is not None else camel
    return value if isinstance(value, dict) else None


def _presentation_bytes(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.endswith("\n"):
        normalized = normalized[:-1]
    return "\n".join(line.rstrip(" \t") for line in normalized.split("\n"))


def _normalized_seeds(value: object) -> Optional[tuple[tuple[str, Optional[str]], ...]]:
    if not isinstance(value, list):
        return None
    seeds: list[tuple[str, Optional[str]]] = []
    for row in value:
        if not isinstance(row, dict) or set(row) != {"term", "location"}:
            return None
        term, location = row["term"], row["location"]
        if (
            not isinstance(term, str)
            or not term.strip()
            or (location is not None and not isinstance(location, str))
        ):
            return None
        seeds.append((term, location))
    return tuple(sorted(set(seeds), key=lambda row: (row[1] or "", row[0])))


def _attempted_calls(
    streams: Sequence[str],
) -> tuple[tuple[dict[str, object], ...], bool]:
    calls: dict[tuple[int, str], dict[str, object]] = {}
    order: list[tuple[int, str]] = []
    malformed = False
    for stream_index, stream in enumerate(streams):
        for line in stream.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, RecursionError):
                malformed = True
                continue
            item = event.get("item") if isinstance(event, dict) else None
            tool = item.get("tool") if isinstance(item, dict) else None
            if (
                not isinstance(item, dict)
                or item.get("type") != "mcp_tool_call"
                or item.get("server") != _SERVER
                or not isinstance(tool, str)
                or tool not in _TOOLS
            ):
                continue
            identifier = item.get("id")
            if not isinstance(identifier, str) or not identifier:
                malformed = True
                continue
            scoped_identifier = (stream_index, identifier)
            if scoped_identifier not in calls:
                order.append(scoped_identifier)
            else:
                previous = calls[scoped_identifier]
                if (
                    previous.get("status") in {"completed", "failed"}
                    or previous.get("error") is not None
                ):
                    malformed = True
            calls[scoped_identifier] = item
    return tuple(calls[identifier] for identifier in order), malformed


def analyze_controller_trace(
    jsonl_streams: Sequence[str],
    final_output: Union[str, Sequence[str]],
    *,
    expected_turns: int,
) -> ControllerEvidence:
    """Require exact begin/finalize pairs and renderer-owned final bytes."""
    if (
        isinstance(expected_turns, bool)
        or not isinstance(expected_turns, int)
        or expected_turns < 0
    ):
        raise ValueError("expected_turns must be a non-negative integer")
    final_outputs = (final_output,) if isinstance(final_output, str) else tuple(final_output)
    if any(not isinstance(value, str) for value in final_outputs):
        raise TypeError("final outputs must be strings")
    if expected_turns > 0 and len(final_outputs) != expected_turns:
        raise ValueError("final outputs must match expected turns")
    calls, malformed = _attempted_calls(jsonl_streams)
    order = tuple(tool for call in calls if isinstance((tool := call.get("tool")), str))
    begins = tuple(call for call in calls if call["tool"] == "rir_begin")
    traces = tuple(call for call in calls if call["tool"] == "rir_trace_impact")
    finalizes = tuple(call for call in calls if call["tool"] == "rir_finalize")
    errors: list[str] = []
    expected_order = _TOOLS * expected_turns
    if malformed:
        errors.append("controller JSONL is malformed")
    if order != expected_order:
        errors.append("controller tool order or count does not match expected turns")
    if any(call.get("status") != "completed" or call.get("error") is not None for call in calls):
        errors.append("controller tool attempt failed or did not complete")

    begin_ids: list[Optional[str]] = []
    payload_digests: list[Optional[str]] = []
    for call in begins:
        result = _structured(call.get("result"))
        value = result.get("draft_id") if result is not None else None
        begin_ids.append(value if isinstance(value, str) and _DRAFT_ID.fullmatch(value) else None)
        payload_digest = result.get("installed_payload_sha256") if result is not None else None
        payload_digests.append(
            payload_digest
            if isinstance(payload_digest, str) and re.fullmatch(r"[0-9a-f]{64}", payload_digest)
            else None
        )
    trace_ids: list[Optional[str]] = []
    receipt_ids: list[Optional[str]] = []
    receipt_paths: list[Optional[str]] = []
    receipt_digests: list[Optional[str]] = []
    compact_digests: list[Optional[str]] = []
    request_digests: list[Optional[str]] = []
    trace_seed_values: list[Optional[tuple[tuple[str, Optional[str]], ...]]] = []
    trace_success: list[bool] = []
    for call in traces:
        arguments = call.get("arguments")
        trace_id = arguments.get("draft_id") if isinstance(arguments, dict) else None
        trace_ids.append(
            trace_id if isinstance(trace_id, str) and _DRAFT_ID.fullmatch(trace_id) else None
        )
        result = _structured(call.get("result"))
        receipt_id = result.get("receipt_id") if result is not None else None
        receipt_path = result.get("receipt_path") if result is not None else None
        receipt_digest = result.get("receipt_sha256") if result is not None else None
        compact_graph = result.get("compact_graph") if result is not None else None
        request_digest = result.get("request_sha256") if result is not None else None
        argument_seeds = _normalized_seeds(
            arguments.get("seeds") if isinstance(arguments, dict) else None
        )
        result_seeds = _normalized_seeds(result.get("seeds") if result is not None else None)
        valid_receipt_id = (
            receipt_id if isinstance(receipt_id, str) and _DRAFT_ID.fullmatch(receipt_id) else None
        )
        valid_path = (
            receipt_path
            if isinstance(receipt_path, str)
            and receipt_path == f".requirements-impact-refiner/graph/{trace_id}.json"
            else None
        )
        valid_digest = (
            receipt_digest
            if isinstance(receipt_digest, str) and re.fullmatch(r"[0-9a-f]{64}", receipt_digest)
            else None
        )
        compact_digest = None
        if isinstance(compact_graph, dict):
            try:
                compact_digest = hashlib.sha256(
                    json.dumps(
                        compact_graph,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
            except (TypeError, ValueError, RecursionError):
                compact_digest = None
        receipt_ids.append(valid_receipt_id)
        receipt_paths.append(valid_path)
        receipt_digests.append(valid_digest)
        compact_digests.append(compact_digest)
        valid_request_digest = (
            request_digest
            if isinstance(request_digest, str) and re.fullmatch(r"[0-9a-f]{64}", request_digest)
            else None
        )
        request_digests.append(valid_request_digest)
        trace_seed_values.append(argument_seeds)
        trace_success.append(
            call.get("status") == "completed"
            and call.get("error") is None
            and result is not None
            and all(
                value is not None
                for value in (
                    trace_ids[-1],
                    valid_receipt_id,
                    valid_path,
                    valid_digest,
                    compact_digest,
                    valid_request_digest,
                )
            )
            and argument_seeds is not None
            and result_seeds == argument_seeds
        )
    finalize_ids: list[Optional[str]] = []
    finalize_receipt_ids: list[Optional[str]] = []
    finalize_success: list[bool] = []
    displays: list[Optional[str]] = []
    for call in finalizes:
        arguments = call.get("arguments")
        draft_id = arguments.get("draft_id") if isinstance(arguments, dict) else None
        finalize_ids.append(
            draft_id if isinstance(draft_id, str) and _DRAFT_ID.fullmatch(draft_id) else None
        )
        receipt_id = arguments.get("graph_receipt_id") if isinstance(arguments, dict) else None
        finalize_receipt_ids.append(
            receipt_id if isinstance(receipt_id, str) and _DRAFT_ID.fullmatch(receipt_id) else None
        )
        result = _structured(call.get("result"))
        display = result.get("display_text") if result is not None else None
        displays.append(display if isinstance(display, str) else None)
        finalize_success.append(
            call.get("status") == "completed"
            and call.get("error") is None
            and result is not None
            and result.get("status") == "published"
            and isinstance(display, str)
        )

    draft_match = (
        len(begin_ids) == expected_turns
        and len(trace_ids) == expected_turns
        and len(finalize_ids) == expected_turns
        and all(value is not None for value in begin_ids + trace_ids + finalize_ids)
        and begin_ids == trace_ids == finalize_ids
    )
    traced = len(trace_success) == expected_turns and all(trace_success)
    receipt_match = (
        len(receipt_ids) == expected_turns
        and len(finalize_receipt_ids) == expected_turns
        and all(value is not None for value in receipt_ids + finalize_receipt_ids)
        and receipt_ids == finalize_receipt_ids
    )
    succeeded = len(finalize_success) == expected_turns and all(finalize_success)
    if expected_turns == 0:
        exact_match = not calls
        presentation_equivalent = not calls
        draft_match = not calls
        traced = not calls
        receipt_match = not calls
        succeeded = not calls
        compared_displays: tuple[Optional[str], ...] = ()
    else:
        compared_displays = tuple(displays)
        exact_match = (
            len(compared_displays) == expected_turns
            and all(isinstance(value, str) for value in compared_displays)
            and compared_displays == final_outputs
        )
        presentation_equivalent = (
            len(compared_displays) == expected_turns
            and all(isinstance(value, str) for value in compared_displays)
            and tuple(
                _presentation_bytes(value) for value in compared_displays if isinstance(value, str)
            )
            == tuple(_presentation_bytes(value) for value in final_outputs)
        )
    if not draft_match:
        errors.append("controller draft IDs do not match")
    if not traced:
        errors.append("controller trace did not succeed")
    if not receipt_match:
        errors.append("controller trace/finalize receipt IDs do not match")
    if expected_turns > 0 and (
        len(payload_digests) != expected_turns
        or any(value is None for value in payload_digests)
        or len(set(payload_digests)) != 1
    ):
        errors.append("installed controller payload identity is invalid")
    if not succeeded:
        errors.append("controller finalize did not succeed")
    if not presentation_equivalent:
        errors.append("controller display text differs from final output under codex-markdown-v1")

    final_digests = tuple(
        hashlib.sha256(value.encode("utf-8")).hexdigest() for value in final_outputs
    )
    display_digests = tuple(
        hashlib.sha256(value.encode("utf-8")).hexdigest()
        for value in compared_displays
        if isinstance(value, str)
    )
    unique_errors = tuple(sorted(set(errors)))
    duplicate_or_error = (
        malformed
        or order != expected_order
        or any(call.get("status") != "completed" or call.get("error") is not None for call in calls)
    )
    return ControllerEvidence(
        valid=not unique_errors,
        errors=unique_errors,
        tool_order=order,
        begin_calls=len(begins),
        trace_calls=len(traces),
        finalize_calls=len(finalizes),
        draft_ids_match=draft_match,
        trace_succeeded=traced,
        finalize_receipt_ids_match=receipt_match,
        finalize_succeeded=succeeded,
        duplicate_or_error_calls=duplicate_or_error,
        display_text_exact_match=exact_match,
        display_text_presentation_equivalent=presentation_equivalent,
        display_comparison="codex-markdown-v1",
        display_text_sha256=display_digests,
        final_output_sha256=final_digests,
        installed_payload_sha256=tuple(
            value for value in payload_digests if isinstance(value, str)
        ),
        draft_ids=tuple(value for value in begin_ids if isinstance(value, str)),
        receipt_ids=tuple(value for value in receipt_ids if isinstance(value, str)),
        receipt_paths=tuple(value for value in receipt_paths if isinstance(value, str)),
        receipt_sha256=tuple(value for value in receipt_digests if isinstance(value, str)),
        trace_compact_graph_sha256=tuple(
            value for value in compact_digests if isinstance(value, str)
        ),
        trace_request_sha256=tuple(value for value in request_digests if isinstance(value, str)),
        trace_seeds=tuple(value for value in trace_seed_values if value is not None),
    )
