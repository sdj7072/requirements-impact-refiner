"""Deterministic, observational performance and serialization-size metrics."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

MAX_METRIC_BYTES = 16 * 1024 * 1024
MAX_INTEGER = 2_147_483_647
CACHE_STATUSES = frozenset({"hit", "miss", "bypassed"})
_PHASE_KEYS = frozenset({"elapsed_ms", "bytes_read", "serialized_bytes", "cache_status"})
_METRIC_KEYS = frozenset(
    {
        "previous_lookup",
        "inventory_delta",
        "compact_graph",
        "accounted_reused_bytes",
        "accounted_new_evidence_bytes",
        "accounting_exclusions",
        "estimated_serialized_input_tokens",
        "estimated_serialized_output_tokens",
        "estimated_model_input_tokens",
        "estimated_model_output_tokens",
        "actual_input_tokens",
        "actual_output_tokens",
        "model_calls",
        "cache_status",
        "analysis_elapsed_ms",
        "operation_elapsed_ms",
    }
)


def _bounded_int(value: object, maximum: int, label: str) -> int:
    if type(value) is not int or value < 0 or value > maximum:
        raise ValueError(f"{label} must be an integer from 0 to {maximum}")
    return value


def _optional_int(value: object, maximum: int, label: str) -> int | None:
    if value is None:
        return None
    return _bounded_int(value, maximum, label)


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


def _digest_set(value: str | Sequence[str] | None) -> frozenset[str]:
    rows = () if value is None else ((value,) if isinstance(value, str) else tuple(value))
    if any(
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        for digest in rows
    ):
        raise ValueError("reused_sha256 must contain 64-character lowercase hex digests")
    return frozenset(rows)


def estimate_tokens(payload: bytes) -> int:
    """Hypothetical serialization size: ceil(UTF-8 bytes / 4), never billed usage."""

    raw = _payload(payload, "payload")
    return (len(raw) + 3) // 4


@dataclass(frozen=True)
class PhaseMetric:
    elapsed_ms: int | None = None
    bytes_read: int | None = None
    serialized_bytes: int | None = None
    cache_status: str | None = None

    def __post_init__(self) -> None:
        _optional_int(self.elapsed_ms, MAX_INTEGER, "elapsed_ms")
        _optional_int(self.bytes_read, MAX_METRIC_BYTES, "bytes_read")
        _optional_int(self.serialized_bytes, MAX_METRIC_BYTES, "serialized_bytes")
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
        bytes_read: int | None = None,
        serialized_bytes: int | None = None,
        cache_status: str | None = None,
    ) -> PhaseMetric:
        if self._finished:
            raise RuntimeError("phase timer is already finished")
        self._finished = True
        elapsed_ns = max(0, self._clock.monotonic_ns() - self._started_ns)
        return PhaseMetric(
            elapsed_ns // 1_000_000,
            bytes_read,
            serialized_bytes,
            cache_status,
        )


@dataclass(frozen=True)
class PerformanceMetrics:
    previous_lookup: PhaseMetric = PhaseMetric()
    inventory_delta: PhaseMetric = PhaseMetric()
    compact_graph: PhaseMetric = PhaseMetric()
    accounted_reused_bytes: int | None = 0
    accounted_new_evidence_bytes: int | None = 0
    accounting_exclusions: tuple[str, ...] = ()
    estimated_serialized_input_tokens: int | None = 0
    estimated_serialized_output_tokens: int | None = 0
    estimated_model_input_tokens: int | None = None
    estimated_model_output_tokens: int | None = None
    actual_input_tokens: int | None = None
    actual_output_tokens: int | None = None
    model_calls: int = 0
    cache_status: str = "bypassed"
    analysis_elapsed_ms: int | None = None
    operation_elapsed_ms: int | None = None

    def __post_init__(self) -> None:
        for name in ("previous_lookup", "inventory_delta", "compact_graph"):
            if not isinstance(getattr(self, name), PhaseMetric):
                raise TypeError(f"{name} must be a PhaseMetric")
        _optional_int(self.accounted_reused_bytes, MAX_METRIC_BYTES, "accounted_reused_bytes")
        _optional_int(
            self.accounted_new_evidence_bytes,
            MAX_METRIC_BYTES,
            "accounted_new_evidence_bytes",
        )
        if (
            not isinstance(self.accounting_exclusions, tuple)
            or len(self.accounting_exclusions) > 16
        ):
            raise ValueError("accounting_exclusions violates its collection bound")
        try:
            exclusions_valid = all(
                isinstance(row, str) and row != "" and len(row.encode("utf-8")) <= 256
                for row in self.accounting_exclusions
            ) and len(set(self.accounting_exclusions)) == len(self.accounting_exclusions)
        except (TypeError, UnicodeEncodeError):
            exclusions_valid = False
        if not exclusions_valid:
            raise ValueError("accounting_exclusions contains invalid UTF-8 text")
        for name in (
            "estimated_serialized_input_tokens",
            "estimated_serialized_output_tokens",
        ):
            _optional_int(getattr(self, name), MAX_INTEGER, name)
        _bounded_int(self.model_calls, MAX_INTEGER, "model_calls")
        model_values = (
            self.estimated_model_input_tokens,
            self.estimated_model_output_tokens,
            self.actual_input_tokens,
            self.actual_output_tokens,
        )
        if self.model_calls == 0 and any(value is not None for value in model_values):
            raise ValueError("model token fields require model_calls greater than zero")
        for first, second, label in (
            (
                self.estimated_model_input_tokens,
                self.estimated_model_output_tokens,
                "estimated model token usage",
            ),
            (self.actual_input_tokens, self.actual_output_tokens, "actual token usage"),
        ):
            if (first is None) != (second is None):
                raise ValueError(f"{label} must be complete or absent")
            if first is not None:
                _bounded_int(first, MAX_INTEGER, label)
                _bounded_int(second, MAX_INTEGER, label)
        if not isinstance(self.cache_status, str) or self.cache_status not in CACHE_STATUSES:
            raise ValueError("cache_status is invalid")
        _optional_int(self.analysis_elapsed_ms, MAX_INTEGER, "analysis_elapsed_ms")
        _optional_int(self.operation_elapsed_ms, MAX_INTEGER, "operation_elapsed_ms")
        if (
            self.analysis_elapsed_ms is not None
            and self.operation_elapsed_ms is not None
            and self.operation_elapsed_ms < self.analysis_elapsed_ms
        ):
            raise ValueError("operation_elapsed_ms cannot precede analysis_elapsed_ms")

    @classmethod
    def from_payloads(cls, **kwargs) -> PerformanceMetrics:
        return measure(**kwargs)

    def to_mapping(self) -> dict[str, object]:
        return {
            "previous_lookup": self.previous_lookup.to_mapping(),
            "inventory_delta": self.inventory_delta.to_mapping(),
            "compact_graph": self.compact_graph.to_mapping(),
            "accounted_reused_bytes": self.accounted_reused_bytes,
            "accounted_new_evidence_bytes": self.accounted_new_evidence_bytes,
            "accounting_exclusions": list(self.accounting_exclusions),
            "estimated_serialized_input_tokens": self.estimated_serialized_input_tokens,
            "estimated_serialized_output_tokens": self.estimated_serialized_output_tokens,
            "estimated_model_input_tokens": self.estimated_model_input_tokens,
            "estimated_model_output_tokens": self.estimated_model_output_tokens,
            "actual_input_tokens": self.actual_input_tokens,
            "actual_output_tokens": self.actual_output_tokens,
            "model_calls": self.model_calls,
            "cache_status": self.cache_status,
            "analysis_elapsed_ms": self.analysis_elapsed_ms,
            "operation_elapsed_ms": self.operation_elapsed_ms,
        }

    @classmethod
    def from_mapping(cls, value: object) -> PerformanceMetrics:
        if not isinstance(value, Mapping) or set(value) != _METRIC_KEYS:
            raise ValueError("performance metrics must have exact fields")
        exclusions = value["accounting_exclusions"]
        if not isinstance(exclusions, list):
            raise ValueError("accounting_exclusions must be an array")
        return cls(
            previous_lookup=PhaseMetric.from_mapping(value["previous_lookup"]),
            inventory_delta=PhaseMetric.from_mapping(value["inventory_delta"]),
            compact_graph=PhaseMetric.from_mapping(value["compact_graph"]),
            accounted_reused_bytes=value["accounted_reused_bytes"],
            accounted_new_evidence_bytes=value["accounted_new_evidence_bytes"],
            accounting_exclusions=tuple(exclusions),
            estimated_serialized_input_tokens=value["estimated_serialized_input_tokens"],
            estimated_serialized_output_tokens=value["estimated_serialized_output_tokens"],
            estimated_model_input_tokens=value["estimated_model_input_tokens"],
            estimated_model_output_tokens=value["estimated_model_output_tokens"],
            actual_input_tokens=value["actual_input_tokens"],
            actual_output_tokens=value["actual_output_tokens"],
            model_calls=value["model_calls"],
            cache_status=value["cache_status"],
            analysis_elapsed_ms=value["analysis_elapsed_ms"],
            operation_elapsed_ms=value["operation_elapsed_ms"],
        )


def measure(
    *,
    previous: bytes | None = None,
    delta: bytes | None = None,
    compact_graph_payload: bytes | None = None,
    state: bytes | None = None,
    report: bytes | None = None,
    output: bytes | None = None,
    reused_sha256: str | Sequence[str] | None = None,
    previous_lookup: PhaseMetric | None = None,
    inventory_delta: PhaseMetric | None = None,
    compact_graph: PhaseMetric | None = None,
    cache_status: str = "bypassed",
    analysis_elapsed_ms: int | None = None,
    operation_elapsed_ms: int | None = None,
    accounting_exclusions: tuple[str, ...] = (),
) -> PerformanceMetrics:
    reused_digests = _digest_set(reused_sha256)
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
    reused = sum(len(raw) for digest, raw in unique.items() if digest in reused_digests)
    new = sum(len(raw) for digest, raw in unique.items() if digest not in reused_digests)
    if reused > MAX_METRIC_BYTES or new > MAX_METRIC_BYTES:
        raise ValueError("deduplicated metric payload exceeds the metric byte limit")
    output_payload = b"" if output is None else _payload(output, "output")
    return PerformanceMetrics(
        previous_lookup=PhaseMetric() if previous_lookup is None else previous_lookup,
        inventory_delta=PhaseMetric() if inventory_delta is None else inventory_delta,
        compact_graph=PhaseMetric() if compact_graph is None else compact_graph,
        accounted_reused_bytes=reused,
        accounted_new_evidence_bytes=new,
        accounting_exclusions=accounting_exclusions,
        estimated_serialized_input_tokens=(new + 3) // 4,
        estimated_serialized_output_tokens=estimate_tokens(output_payload),
        cache_status=cache_status,
        analysis_elapsed_ms=analysis_elapsed_ms,
        operation_elapsed_ms=operation_elapsed_ms,
    )


def with_actual_usage(
    metrics: PerformanceMetrics,
    *,
    input_tokens: int,
    output_tokens: int,
    model_calls: int,
    estimated_model_input_tokens: int | None = None,
    estimated_model_output_tokens: int | None = None,
) -> PerformanceMetrics:
    """Attach usage only at a trusted client/evaluation result boundary."""

    if not isinstance(metrics, PerformanceMetrics):
        raise TypeError("metrics must be PerformanceMetrics")
    if type(model_calls) is not int or model_calls < 1:
        raise ValueError("model_calls must be a positive integer at the trusted boundary")
    return replace(
        metrics,
        estimated_model_input_tokens=estimated_model_input_tokens,
        estimated_model_output_tokens=estimated_model_output_tokens,
        actual_input_tokens=input_tokens,
        actual_output_tokens=output_tokens,
        model_calls=model_calls,
    )


__all__ = [
    "PerformanceMetrics",
    "PhaseMetric",
    "PhaseTimer",
    "estimate_tokens",
    "measure",
    "with_actual_usage",
]
