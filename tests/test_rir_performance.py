import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "rir_performance.py"
MIRROR_PATH = ROOT / "skills" / "requirements-impact-refiner" / "scripts" / "rir_performance.py"


def load_performance():
    name = "_rir_performance_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeClock:
    def __init__(self, *values):
        self.values = iter(values)

    def monotonic_ns(self):
        return next(self.values)


class RirPerformanceTest(unittest.TestCase):
    def test_estimate_tokens_uses_ceil_of_utf8_bytes_over_four(self):
        performance = load_performance()

        self.assertEqual(performance.estimate_tokens(b""), 0)
        self.assertEqual(performance.estimate_tokens(b"1234"), 1)
        self.assertEqual(performance.estimate_tokens(b"12345678"), 2)
        self.assertEqual(performance.estimate_tokens("한글".encode()), 2)

    def test_serialized_estimates_are_not_model_usage(self):
        performance = load_performance()

        metrics = performance.PerformanceMetrics.from_payloads(previous=b"1234", delta=b"12345678")

        self.assertEqual(metrics.estimated_serialized_input_tokens, 3)
        self.assertEqual(metrics.estimated_serialized_output_tokens, 0)
        self.assertIsNone(metrics.estimated_model_input_tokens)
        self.assertIsNone(metrics.estimated_model_output_tokens)
        self.assertIsNone(metrics.actual_input_tokens)
        self.assertIsNone(metrics.actual_output_tokens)
        self.assertEqual(metrics.model_calls, 0)

        reported = performance.with_actual_usage(
            metrics,
            input_tokens=7,
            output_tokens=2,
            model_calls=1,
            estimated_model_input_tokens=6,
            estimated_model_output_tokens=2,
        )
        self.assertEqual(reported.estimated_serialized_input_tokens, 3)
        self.assertEqual(reported.estimated_model_input_tokens, 6)
        self.assertEqual(reported.actual_input_tokens, 7)
        self.assertEqual(reported.actual_output_tokens, 2)
        self.assertEqual(reported.model_calls, 1)

    def test_identical_payload_digest_is_counted_once_per_operation(self):
        performance = load_performance()
        payload = b"same evidence"

        metrics = performance.measure(previous=payload, delta=payload)

        self.assertEqual(metrics.accounted_new_evidence_bytes, len(payload))
        self.assertEqual(metrics.estimated_serialized_input_tokens, 4)

    def test_reused_bytes_are_not_counted_as_new_evidence(self):
        performance = load_performance()
        payload = b"same evidence"

        metrics = performance.measure(
            previous=payload,
            delta=payload,
            reused_sha256=hashlib.sha256(payload).hexdigest(),
        )

        self.assertEqual(metrics.accounted_reused_bytes, len(payload))
        self.assertEqual(metrics.accounted_new_evidence_bytes, 0)
        self.assertEqual(metrics.estimated_serialized_input_tokens, 0)

    def test_elapsed_phase_metric_uses_injected_monotonic_clock(self):
        performance = load_performance()
        clock = FakeClock(1_000_000_000, 1_007_999_999)

        timer = performance.PhaseTimer(clock=clock)
        metric = timer.finish(bytes_read=9, serialized_bytes=5, cache_status="miss")

        self.assertEqual(metric.elapsed_ms, 7)
        self.assertEqual(metric.bytes_read, 9)
        self.assertEqual(metric.serialized_bytes, 5)
        self.assertEqual(metric.cache_status, "miss")

    def test_mapping_round_trip_is_bounded_and_rejects_malformed_values(self):
        performance = load_performance()
        metrics = performance.PerformanceMetrics.from_payloads(
            previous="이전".encode(),
            delta=b"delta",
            output=b"result",
            previous_lookup=performance.PhaseMetric(12, 8, 0, "hit"),
            inventory_delta=performance.PhaseMetric(31, 19, 0, "miss"),
            compact_graph=performance.PhaseMetric(4, 0, 23, None),
            cache_status="miss",
            analysis_elapsed_ms=47,
            operation_elapsed_ms=53,
            accounting_exclusions=("filesystem metadata",),
        )
        mapping = metrics.to_mapping()

        self.assertEqual(performance.PerformanceMetrics.from_mapping(mapping), metrics)
        self.assertEqual(json.loads(json.dumps(mapping)), mapping)

        malformed = dict(mapping)
        malformed["operation_elapsed_ms"] = True
        with self.assertRaisesRegex(ValueError, "operation_elapsed_ms"):
            performance.PerformanceMetrics.from_mapping(malformed)

        malformed = dict(mapping)
        malformed["surprise"] = 1
        with self.assertRaisesRegex(ValueError, "exact fields"):
            performance.PerformanceMetrics.from_mapping(malformed)

        malformed = dict(mapping)
        malformed["actual_input_tokens"] = 1
        malformed["model_calls"] = 1
        with self.assertRaisesRegex(ValueError, "complete or absent"):
            performance.PerformanceMetrics.from_mapping(malformed)

        malformed = dict(mapping)
        malformed["accounted_new_evidence_bytes"] = 16 * 1024 * 1024 + 1
        with self.assertRaisesRegex(ValueError, "accounted_new_evidence_bytes"):
            performance.PerformanceMetrics.from_mapping(malformed)

    def test_no_clamp_and_unknown_timing_are_preserved(self):
        performance = load_performance()

        unknown = performance.PhaseMetric(elapsed_ms=None, bytes_read=None)
        long = performance.PerformanceMetrics(
            previous_lookup=unknown,
            analysis_elapsed_ms=31_001,
            operation_elapsed_ms=31_123,
        )

        self.assertIsNone(unknown.elapsed_ms)
        self.assertEqual(long.analysis_elapsed_ms, 31_001)
        self.assertEqual(long.operation_elapsed_ms, 31_123)

    def test_actual_usage_requires_a_positive_trusted_model_call_count(self):
        performance = load_performance()
        metrics = performance.PerformanceMetrics()

        with self.assertRaisesRegex(ValueError, "model_calls"):
            performance.with_actual_usage(
                metrics,
                input_tokens=7,
                output_tokens=2,
                model_calls=0,
            )

    def test_model_call_count_rejects_null_bool_negative_and_usage_bypass(self):
        performance = load_performance()
        base = performance.PerformanceMetrics().to_mapping()
        cases = (
            (None, None, None),
            (True, None, None),
            (-1, None, None),
            (None, 10, 2),
        )

        for model_calls, actual_input, actual_output in cases:
            with self.subTest(
                model_calls=model_calls,
                actual_input=actual_input,
                actual_output=actual_output,
            ):
                malformed = dict(base)
                malformed["model_calls"] = model_calls
                malformed["actual_input_tokens"] = actual_input
                malformed["actual_output_tokens"] = actual_output
                with self.assertRaisesRegex(ValueError, "model_calls"):
                    performance.PerformanceMetrics.from_mapping(malformed)

        for model_calls in (None, True, -1):
            with self.subTest(constructor=model_calls):
                with self.assertRaisesRegex(ValueError, "model_calls"):
                    performance.PerformanceMetrics(model_calls=model_calls)

    def test_exclusions_match_schema_cardinality_utf8_and_unique_contract(self):
        performance = load_performance()
        base = performance.PerformanceMetrics().to_mapping()
        too_many = [f"exclusion-{index:02d}" for index in range(17)]
        unicode_257_bytes = "한" * 85 + "é"
        self.assertEqual(len(unicode_257_bytes.encode()), 257)
        invalid = (
            too_many,
            [unicode_257_bytes],
            ["duplicate", "duplicate"],
            [""],
        )

        for exclusions in invalid:
            with self.subTest(exclusions=exclusions):
                malformed = dict(base)
                malformed["accounting_exclusions"] = exclusions
                with self.assertRaisesRegex(ValueError, "accounting_exclusions"):
                    performance.PerformanceMetrics.from_mapping(malformed)

        unsorted = ("z-last", "a-first")
        valid = performance.PerformanceMetrics(accounting_exclusions=unsorted)
        self.assertEqual(valid.accounting_exclusions, unsorted)

    def test_trusted_actual_usage_accepts_bounded_complete_pairs(self):
        performance = load_performance()

        result = performance.with_actual_usage(
            performance.PerformanceMetrics(),
            input_tokens=10,
            output_tokens=2,
            model_calls=1,
            estimated_model_input_tokens=9,
            estimated_model_output_tokens=2,
        )

        self.assertEqual(result.model_calls, 1)
        self.assertEqual(result.actual_input_tokens, 10)
        self.assertEqual(result.estimated_model_input_tokens, 9)

    def test_root_and_installed_skill_implementations_are_byte_identical(self):
        self.assertEqual(MODULE_PATH.read_bytes(), MIRROR_PATH.read_bytes())


if __name__ == "__main__":
    unittest.main()
