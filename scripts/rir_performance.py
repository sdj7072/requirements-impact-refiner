"""Deterministic, observational performance and token metrics."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace

MAX_ELAPSED_MS = 30_000
MAX_METRIC_BYTES = 16 * 1024 * 1024
MAX_ESTIMATED_TOKENS = MAX_METRIC_BYTES // 4
MAX_ACTUAL_TOKENS = 2_147_483_647
CACHE_STATUSES = frozenset({"hit", "miss", "bypassed"})
_PHASE_KEYS = frozenset({"elapsed_ms", "bytes_read", "serialized_bytes", "cache_status"})
_METRIC_KEYS = frozenset(
    {
        "previous_lookup",
        "inventory_delta",
        "compact_graph",
        "reused_previous_bytes",
        "new_evidence_bytes",
        "estimated_input_tokens",
        "estimated_output_tokens",
        "actual_input_tokens",
        "actual_output_tokens",
        "cache_status",
        "total_elapsed_ms",
    }
)


def _bounded_int(value: object, maximum: int, label: str) -> int:
    if type(value) is not int or value < 0 or value > maximum:
        raise ValueError(f"{label} must be an integer from 0 to {maximum}")
    return value


def _payload(value: object, label: str) -> bytes:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, (bytearray, memoryview)):
        payload = bytes(value)
    else:
        raise TypeError(f"{label} must be bytes")
    if len(payload) > MAX_METRIC_BYTES:
        raise ValueError(f"{label} exceeds the metric byte limit")
    return payload


def estimate_tokens(payload: bytes) -> int:
    """Estimate tokens as ceil(len(UTF-8 bytes) / 4)."""

    raw = _payload(payload, "payload")
    return (len(raw) + 3) // 4


@dataclass(frozen=True)
class PhaseMetric:
    elapsed_ms: int = 0
    bytes_read: int = 0
    serialized_bytes: int = 0
    cache_status: str | None = None

    def __post_init__(self) -> None:
        _bounded_int(self.elapsed_ms, MAX_ELAPSED_MS, "elapsed_ms")
        _bounded_int(self.bytes_read, MAX_METRIC_BYTES, "bytes_read")
        _bounded_int(self.serialized_bytes, MAX_METRIC_BYTES, "serialized_bytes")
        if self.cache_status is not None and (
            not isinstance(self.cache_status, str) or self.cache_status not in CACHE_STATUSES
        ):
            raise ValueError("cache_status is invalid")

    def to_mapping(self) -> dict[str, object]:
        return {
            "elapsed_ms": self.elapsed_ms,
            "bytes_read": self.bytes_read,
            "serialized_bytes": self.serialized_bytes,
            "cache_status": self.cache_status,
        }

    @classmethod
    def from_mapping(cls, value: object) -> PhaseMetric:
        if not isinstance(value, Mapping) or set(value) != _PHASE_KEYS:
            raise ValueError("phase metric must have exact fields")
        return cls(
            value["elapsed_ms"],
            value["bytes_read"],
            value["serialized_bytes"],
            value["cache_status"],
        )


class PhaseTimer:
    """One-shot phase timer with an injectable monotonic nanosecond clock."""

    def __init__(self, *, clock=time) -> None:
        monotonic_ns = getattr(clock, "monotonic_ns", None)
        if not callable(monotonic_ns):
            raise TypeError("clock must expose monotonic_ns")
        self._clock = clock
        self._started_ns = monotonic_ns()
        self._finished = False

    def finish(
        self,
        *,
        bytes_read: int = 0,
        serialized_bytes: int = 0,
        cache_status: str | None = None,
    ) -> PhaseMetric:
        if self._finished:
            raise RuntimeError("phase timer is already finished")
        self._finished = True
        elapsed_ns = max(0, self._clock.monotonic_ns() - self._started_ns)
        return PhaseMetric(
            min(MAX_ELAPSED_MS, elapsed_ns // 1_000_000),
            bytes_read,
            serialized_bytes,
            cache_status,
        )


@dataclass(frozen=True)
class PerformanceMetrics:
    previous_lookup: PhaseMetric = PhaseMetric()
    inventory_delta: PhaseMetric = PhaseMetric()
    compact_graph: PhaseMetric = PhaseMetric()
    reused_previous_bytes: int = 0
    new_evidence_bytes: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    actual_input_tokens: int | None = None
    actual_output_tokens: int | None = None
    cache_status: str = "bypassed"
    total_elapsed_ms: int = 0

    def __post_init__(self) -> None:
        for name in ("previous_lookup", "inventory_delta", "compact_graph"):
            if not isinstance(getattr(self, name), PhaseMetric):
                raise TypeError(f"{name} must be a PhaseMetric")
        _bounded_int(self.reused_previous_bytes, MAX_METRIC_BYTES, "reused_previous_bytes")
        _bounded_int(self.new_evidence_bytes, MAX_METRIC_BYTES, "new_evidence_bytes")
        _bounded_int(self.estimated_input_tokens, MAX_ESTIMATED_TOKENS, "estimated_input_tokens")
        _bounded_int(self.estimated_output_tokens, MAX_ESTIMATED_TOKENS, "estimated_output_tokens")
        if (self.actual_input_tokens is None) != (self.actual_output_tokens is None):
            raise ValueError("actual token usage must be complete or absent")
        if self.actual_input_tokens is not None:
            _bounded_int(self.actual_input_tokens, MAX_ACTUAL_TOKENS, "actual_input_tokens")
            _bounded_int(self.actual_output_tokens, MAX_ACTUAL_TOKENS, "actual_output_tokens")
        if not isinstance(self.cache_status, str) or self.cache_status not in CACHE_STATUSES:
            raise ValueError("cache_status is invalid")
        _bounded_int(self.total_elapsed_ms, MAX_ELAPSED_MS, "total_elapsed_ms")

    @classmethod
    def from_payloads(cls, **kwargs) -> PerformanceMetrics:
        return measure(**kwargs)

    def to_mapping(self) -> dict[str, object]:
        return {
            "previous_lookup": self.previous_lookup.to_mapping(),
            "inventory_delta": self.inventory_delta.to_mapping(),
            "compact_graph": self.compact_graph.to_mapping(),
            "reused_previous_bytes": self.reused_previous_bytes,
            "new_evidence_bytes": self.new_evidence_bytes,
            "estimated_input_tokens": self.estimated_input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
            "actual_input_tokens": self.actual_input_tokens,
            "actual_output_tokens": self.actual_output_tokens,
            "cache_status": self.cache_status,
            "total_elapsed_ms": self.total_elapsed_ms,
        }

    @classmethod
    def from_mapping(cls, value: object) -> PerformanceMetrics:
        if not isinstance(value, Mapping) or set(value) != _METRIC_KEYS:
            raise ValueError("performance metrics must have exact fields")
        return cls(
            previous_lookup=PhaseMetric.from_mapping(value["previous_lookup"]),
            inventory_delta=PhaseMetric.from_mapping(value["inventory_delta"]),
            compact_graph=PhaseMetric.from_mapping(value["compact_graph"]),
            reused_previous_bytes=value["reused_previous_bytes"],
            new_evidence_bytes=value["new_evidence_bytes"],
            estimated_input_tokens=value["estimated_input_tokens"],
            estimated_output_tokens=value["estimated_output_tokens"],
            actual_input_tokens=value["actual_input_tokens"],
            actual_output_tokens=value["actual_output_tokens"],
            cache_status=value["cache_status"],
            total_elapsed_ms=value["total_elapsed_ms"],
        )


def measure(
    *,
    previous: bytes | None = None,
    delta: bytes | None = None,
    compact_graph_payload: bytes | None = None,
    state: bytes | None = None,
    report: bytes | None = None,
    output: bytes | None = None,
    reused_sha256: str | None = None,
    previous_lookup: PhaseMetric | None = None,
    inventory_delta: PhaseMetric | None = None,
    compact_graph: PhaseMetric | None = None,
    cache_status: str = "bypassed",
    total_elapsed_ms: int = 0,
) -> PerformanceMetrics:
    if reused_sha256 is not None and (
        not isinstance(reused_sha256, str)
        or len(reused_sha256) != 64
        or any(character not in "0123456789abcdef" for character in reused_sha256)
    ):
        raise ValueError("reused_sha256 must be 64 lowercase hex characters")
    unique: dict[str, bytes] = {}
    for label, value in (
        ("previous", previous),
        ("delta", delta),
        ("compact_graph_payload", compact_graph_payload),
        ("state", state),
        ("report", report),
    ):
        if value is None:
            continue
        raw = _payload(value, label)
        if raw:
            unique.setdefault(hashlib.sha256(raw).hexdigest(), raw)
    reused = sum(len(raw) for digest, raw in unique.items() if digest == reused_sha256)
    new = sum(len(raw) for digest, raw in unique.items() if digest != reused_sha256)
    if reused > MAX_METRIC_BYTES or new > MAX_METRIC_BYTES:
        raise ValueError("deduplicated metric payload exceeds the metric byte limit")
    output_payload = b"" if output is None else _payload(output, "output")
    return PerformanceMetrics(
        previous_lookup=PhaseMetric() if previous_lookup is None else previous_lookup,
        inventory_delta=PhaseMetric() if inventory_delta is None else inventory_delta,
        compact_graph=PhaseMetric() if compact_graph is None else compact_graph,
        reused_previous_bytes=reused,
        new_evidence_bytes=new,
        estimated_input_tokens=(new + 3) // 4,
        estimated_output_tokens=estimate_tokens(output_payload),
        cache_status=cache_status,
        total_elapsed_ms=total_elapsed_ms,
    )


def with_actual_usage(
    metrics: PerformanceMetrics, *, input_tokens: int, output_tokens: int
) -> PerformanceMetrics:
    """Attach usage only at a trusted client/evaluation result boundary."""

    if not isinstance(metrics, PerformanceMetrics):
        raise TypeError("metrics must be PerformanceMetrics")
    return replace(metrics, actual_input_tokens=input_tokens, actual_output_tokens=output_tokens)


__all__ = [
    "PerformanceMetrics",
    "PhaseMetric",
    "PhaseTimer",
    "estimate_tokens",
    "measure",
    "with_actual_usage",
]
