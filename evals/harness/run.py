"""Command-line orchestration for installed-plugin evaluation batches."""

import argparse
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Optional, Tuple

from .adapters.claude import ClaudeAdapter
from .adapters.codex import CodexAdapter
from .catalog import load_all, select_suite
from .evidence import build_manifest, verify_manifest
from .models import CaseSpec, MechanicalScore, RunRequest, RunResult, RunStatus
from .reporting import render_report
from .scoring import score_mechanical


@dataclass(frozen=True)
class ScheduledRun:
    """One case/repetition slot in a deterministic evaluation batch."""

    case: CaseSpec
    repetition: int


class EvalArgumentParser(argparse.ArgumentParser):
    """Parser that keeps client-mode validation at the invocation boundary."""

    def parse_args(self, args: Optional[Iterable[str]] = None, namespace: Any = None):
        parsed = super().parse_args(args, namespace)
        if parsed.repetitions < 1:
            self.error("--repetitions must be a positive integer")
        if parsed.timeout < 0:
            self.error("--timeout must not be negative")
        if parsed.client == "claude" and (parsed.model is not None or parsed.reasoning is not None):
            self.error("Claude structural mode does not accept --model or --reasoning")
        return parsed


def build_parser() -> argparse.ArgumentParser:
    """Build the public controller CLI parser without choosing model defaults."""
    parser = EvalArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=("codex", "claude"), required=True)
    parser.add_argument(
        "--suite", choices=("smoke", "installed-superpowers"), required=True
    )
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--model")
    parser.add_argument("--reasoning")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--probe-only", action="store_true")
    return parser


def build_schedule(
    cases: Iterable[CaseSpec], suite: str, repetitions: int
) -> Tuple[ScheduledRun, ...]:
    """Schedule every selected case in catalog order, then repetitions 1 through N."""
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    selected = select_suite(cases, suite)
    return tuple(
        ScheduledRun(case, repetition)
        for case in selected
        for repetition in range(1, repetitions + 1)
    )


def create_adapter(args: argparse.Namespace):
    """Create the real adapter only when the command-line entry point is used."""
    if args.client == "codex":
        return CodexAdapter(timeout_seconds=args.timeout)
    return ClaudeAdapter(executable="claude", timeout_seconds=args.timeout)


def _evidence_path(output_root: Path, client: str, slot: ScheduledRun, repetition: object) -> Path:
    if isinstance(repetition, int):
        component = "%02d" % repetition
    else:
        component = str(repetition)
    return output_root / client / slot.case.id / component


def _retry_repetition(repetition: int) -> str:
    return "%02d-attempt-02" % repetition


def _run_metadata(result: RunResult) -> dict[str, str]:
    """Keep adapter provenance, including a multi-turn UUID, scoped to this run."""
    metadata = {key: value for key, value in result.metadata}
    if result.session_id is not None:
        metadata["session_id"] = result.session_id
    return metadata


def _run_row(
    slot: ScheduledRun, result: RunResult, attempt_id: str, retry_of: Optional[str] = None
) -> dict[str, object]:
    row: dict[str, object] = {
        "case_id": slot.case.id,
        "repetition": slot.repetition,
        "status": result.status.value,
        "reason": result.reason,
        "attempt_id": attempt_id,
        "metadata": _run_metadata(result),
    }
    if retry_of is not None:
        row["retry_of"] = retry_of
    return row


def _write_new(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(content)


def _score_row(score: MechanicalScore) -> dict[str, object]:
    return {
        "case_id": score.case_id,
        "repetition": score.repetition,
        "passed": score.passed,
        "findings": list(score.findings),
    }


def _report_metadata(args: argparse.Namespace, probe: Any, results: Iterable[RunResult]) -> dict[str, object]:
    environments = {
        value for result in results for key, value in result.metadata if key == "environment"
    }
    return {
        "client": args.client,
        "version": probe.version or "unavailable",
        "enabled_composition": sorted(environments)[0] if len(environments) == 1 else "mixed",
        "model": args.model or "omitted",
        "reasoning": args.reasoning or "omitted",
        "repetitions": args.repetitions,
    }


def _finalize(output_root: Path, ledger: dict[str, object], report: str) -> bool:
    """Publish controller metadata and a manifest exactly once, then verify it."""
    try:
        _write_new(output_root / "report.md", report)
        _write_new(
            output_root / "controller.json",
            json.dumps(ledger, sort_keys=True, indent=2) + "\n",
        )
        manifest = build_manifest(output_root)
        _write_new(output_root / "manifest.sha256", manifest)
        return not verify_manifest(output_root, manifest)
    except (OSError, ValueError):
        return False


def _completed_output_exists(output_root: Path, client: str, schedule: Iterable[ScheduledRun]) -> bool:
    if any(
        (output_root / name).exists()
        for name in ("controller.json", "manifest.sha256", "report.md")
    ):
        return True
    return any(
        _evidence_path(output_root, client, slot, slot.repetition).exists() for slot in schedule
    )


def run_batch(
    args: argparse.Namespace, adapter: Any, cases: Optional[Iterable[CaseSpec]] = None
) -> int:
    """Run a deterministic batch; zero means it completed, never that it scored well."""
    try:
        schedule = build_schedule(load_all() if cases is None else cases, args.suite, args.repetitions)
    except (TypeError, ValueError):
        return 2
    output_root = Path(args.output)
    if _completed_output_exists(output_root, args.client, schedule):
        return 1
    try:
        probe = adapter.prepare()
    except (OSError, ValueError, AttributeError):
        return 1

    rows = []
    results = []
    scores = []
    invalid_evidence = False
    for slot in schedule:
        request = RunRequest(
            case=slot.case,
            repetition=slot.repetition,
            client=args.client,
            model=args.model,
            reasoning=args.reasoning,
            output_root=output_root,
        )
        try:
            result = adapter.execute(request)
        except (OSError, ValueError, AttributeError):
            return 1
        if result.status is RunStatus.INVALID_EVIDENCE:
            invalid_evidence = True

        if result.status is not RunStatus.INFRA_ERROR:
            rows.append(_run_row(slot, result, "attempt-01"))
            final_result = replace(result, repetition=slot.repetition)
            results.append(final_result)
            scores.append(score_mechanical(slot.case, final_result))
            continue

        retry_repetition = _retry_repetition(slot.repetition)
        if _evidence_path(output_root, args.client, slot, retry_repetition).exists():
            return 1
        retry_request = RunRequest(
            case=slot.case,
            repetition=retry_repetition,
            client=args.client,
            model=args.model,
            reasoning=args.reasoning,
            output_root=output_root,
        )
        try:
            retry_result = adapter.execute(retry_request)
        except (OSError, ValueError, AttributeError):
            return 1
        if retry_result.status is RunStatus.INVALID_EVIDENCE:
            invalid_evidence = True
        rows.append(
            _run_row(
                slot,
                retry_result,
                "attempt-02",
                "%s/%02d" % (slot.case.id, slot.repetition),
            )
        )
        final_result = replace(retry_result, repetition=slot.repetition)
        results.append(final_result)
        scores.append(score_mechanical(slot.case, final_result))

    ledger = {
        "client": args.client,
        "suite": args.suite,
        "repetitions": args.repetitions,
        "runs": rows,
        "mechanical_scores": [_score_row(score) for score in scores],
    }
    try:
        report = render_report(results, _report_metadata(args, probe, results), scores)
    except (TypeError, ValueError):
        return 1
    if not _finalize(output_root, ledger, report):
        return 1
    return 1 if invalid_evidence else 0


def _probe_payload(probe: Any) -> str:
    return json.dumps(
        {
            "client": probe.client,
            "available": probe.available,
            "version": probe.version,
            "authenticated": probe.authenticated,
            "plugin_version": probe.plugin_version,
            "enabled_plugins": list(probe.enabled_plugins),
            "capabilities": list(probe.capabilities),
            "reason": probe.reason,
        },
        sort_keys=True,
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run the controller CLI without interpreting a completed batch as a pass."""
    args = build_parser().parse_args(argv)
    adapter = create_adapter(args)
    if args.probe_only:
        try:
            print(_probe_payload(adapter.probe()))
        except (OSError, ValueError, AttributeError):
            return 1
        return 0
    return run_batch(args, adapter)


if __name__ == "__main__":
    raise SystemExit(main())
