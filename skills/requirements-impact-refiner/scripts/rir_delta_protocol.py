"""Authenticated bounded frame protocol for the private delta worker."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

MAX_CONTROL_FRAME_BYTES = 1024
MAX_FALLBACK_FRAME_BYTES = 4 * 1024 * 1024
MAX_RESULT_FRAME_BYTES = 4 * 1024 * 1024
MAX_FRAME_BYTES = max(
    MAX_CONTROL_FRAME_BYTES,
    MAX_FALLBACK_FRAME_BYTES,
    MAX_RESULT_FRAME_BYTES,
)

_FRAME_LIMITS = {
    "control": MAX_CONTROL_FRAME_BYTES,
    "trusted_fallback": MAX_FALLBACK_FRAME_BYTES,
    "result": MAX_RESULT_FRAME_BYTES,
}


def encode_frame(kind: str, payload: Mapping[str, object], token: str) -> bytes:
    maximum = _FRAME_LIMITS.get(kind)
    if maximum is None or re.fullmatch(r"[0-9a-f]{32}", token) is None:
        raise ValueError("delta worker output frame type is invalid")
    body = json.dumps(
        {"kind": kind, "payload": payload, "token": token},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if not body or len(body) > maximum:
        raise ValueError("delta worker output frame exceeds its byte limit")
    return f"{len(body):08x}\n".encode("ascii") + body


def decode_body(payload: bytes, token: str) -> tuple[str, Mapping[str, object]]:
    if not payload or len(payload) > MAX_FRAME_BYTES:
        raise ValueError("delta worker frame body size is invalid")
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("delta worker frame payload is invalid") from error
    try:
        canonical = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (RecursionError, TypeError, UnicodeEncodeError, ValueError) as error:
        raise ValueError("delta worker frame payload is invalid") from error
    if (
        not isinstance(value, dict)
        or set(value) != {"kind", "payload", "token"}
        or value.get("token") != token
        or canonical != payload
    ):
        raise ValueError("delta worker frame authentication is invalid")
    kind = value.get("kind")
    frame_payload = value.get("payload")
    if not isinstance(kind, str):
        raise ValueError("delta worker frame type is invalid")
    maximum = _FRAME_LIMITS.get(kind)
    if maximum is None or len(payload) > maximum or not isinstance(frame_payload, Mapping):
        raise ValueError("delta worker frame type or bound is invalid")
    return kind, frame_payload


def decode_frame(payload: bytes, token: str) -> tuple[str, Mapping[str, object]]:
    if len(payload) < 9 or len(payload) > MAX_FRAME_BYTES + 9:
        raise ValueError("delta worker frame size is invalid")
    header = payload[:9]
    if re.fullmatch(rb"[0-9a-f]{8}\n", header) is None:
        raise ValueError("delta worker frame header is invalid")
    declared = int(header[:8], 16)
    body = payload[9:]
    if declared != len(body):
        raise ValueError("delta worker frame length is invalid")
    return decode_body(body, token)
