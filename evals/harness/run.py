"""Command-line orchestration for installed-plugin evaluation batches."""

import argparse
import hashlib
import importlib
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import ModuleType
from typing import Any, Optional

from .adapters.claude import ClaudeAdapter
from .adapters.codex import CodexAdapter
from .catalog import load_all, select_suite
from .controller_evidence import analyze_controller_trace
from .evidence import (
    PotentialSecretError,
    build_manifest,
    record_probe,
    record_run,
    verify_manifest,
)
from .graph_scoring import (
    GRAPH_CASE_IDS,
    GraphScore,
    canonical_receipt_bytes,
    compact_graph,
    graph_run_policy,
    load_graph_cases,
    score_graph,
)
from .models import (
    CaseSpec,
    ClientProbe,
    CommandResult,
    MechanicalScore,
    RunRequest,
    RunResult,
    RunStatus,
)
from .performance import (
    GraphPerformanceObservation,
    GraphSmokeGateResult,
    PerformanceObservation,
    SmokeGateResult,
    evaluate_graph_smoke,
    evaluate_smoke_gate,
)
from .reporting import render_report
from .scoring import score_mechanical

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL_SCRIPT_DIR = _REPO_ROOT / "skills" / "requirements-impact-refiner" / "scripts"
if str(_SKILL_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPT_DIR))
_impact_renderer: ModuleType = importlib.import_module("impact_renderer")
_payload_identity: ModuleType = importlib.import_module("payload_identity")

_RAW_DIRECTORY = "raw"
_DERIVED_ARTIFACTS = frozenset(
    (
        "probes.json",
        "controller.json",
        "report.md",
        "scores.json",
        "graph-scores.json",
        "performance.json",
    )
)
_REPORT_ID_PATTERN = re.compile(r"RPT-\d{3}")
_POINTER_KEYS = {
    "schema_version",
    "report_id",
    "revision",
    "state",
    "markdown",
    "markdown_sha256",
}


@dataclass(frozen=True)
class ScheduledRun:
    """One case/repetition final in deterministic catalog order."""

    case: CaseSpec
    repetition: int


class EvalArgumentParser(argparse.ArgumentParser):
    """Validate controller-only invocation rules after ordinary parsing."""

    def parse_args(self, args: Optional[Sequence[str]] = None, namespace: Any = None):
        parsed = super().parse_args(args, namespace)
        if parsed.repetitions < 1:
            self.error("--repetitions must be a positive integer")
        if parsed.timeout < 0:
            self.error("--timeout must not be negative")
        if not parsed.probe_only and parsed.suite is None:
            self.error("--suite is required unless --probe-only is set")
        if parsed.client == "claude" and (parsed.model is not None or parsed.reasoning is not None):
            self.error("Claude structural mode does not accept --model or --reasoning")
        return parsed


def build_parser() -> argparse.ArgumentParser:
    """Build the public CLI without selecting an implicit model or suite."""
    parser = EvalArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=("codex", "claude"), required=True)
    parser.add_argument("--suite", choices=("smoke", "graph-smoke", "installed-superpowers"))
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--model")
    parser.add_argument("--reasoning")
    parser.add_argument("--expected-plugin-version", default="0.3.0")
    parser.add_argument(
        "--expected-rir-plugin-id",
        default="requirements-impact-refiner@requirements-impact-refiner",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--probe-only", action="store_true")
    return parser


def build_schedule(
    cases: Iterable[CaseSpec], suite: str, repetitions: int
) -> tuple[ScheduledRun, ...]:
    """Select a suite and nest repetitions within each canonical case."""
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    case_values = tuple(cases)
    if suite == "graph-smoke":
        by_id = {case.id: case for case in case_values}
        if len(by_id) != len(case_values) or tuple(by_id) != GRAPH_CASE_IDS:
            raise ValueError("graph-smoke suite must contain the exact six cases")
        selected = tuple(by_id[case_id] for case_id in GRAPH_CASE_IDS)
    else:
        selected = select_suite(case_values, suite)
    return tuple(
        ScheduledRun(case, repetition)
        for case in selected
        for repetition in range(1, repetitions + 1)
    )


def create_adapter(args: argparse.Namespace):
    """Instantiate a real client adapter only for the command-line entry point."""
    if args.client == "codex":
        return CodexAdapter(
            timeout_seconds=args.timeout,
            expected_plugin_version=args.expected_plugin_version,
            expected_rir_plugin_id=args.expected_rir_plugin_id,
        )
    return ClaudeAdapter(executable="claude", timeout_seconds=args.timeout)


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        return digest.hexdigest()
    files = sorted(
        (item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()
    )
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _files_hash(paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        payload = path.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _composition(probe: ClientProbe) -> str:
    plugins = ",".join(sorted(probe.enabled_plugins)) or "none"
    return "{} {} plugins={}".format(probe.client, probe.version or "unavailable", plugins)


def _batch_identity(args: argparse.Namespace, probe: ClientProbe) -> dict[str, object]:
    """Return provenance that must agree before a batch may be extended."""
    return {
        "client": probe.client,
        "version": probe.version,
        "plugin_version": probe.plugin_version,
        "enabled_plugins": sorted(probe.enabled_plugins),
        "model": args.model,
        "reasoning": args.reasoning,
        "enabled_composition": _composition(probe),
        "harness_sha256": _tree_hash(_REPO_ROOT / "evals" / "harness"),
        "catalog_sha256": _files_hash(
            (_REPO_ROOT / "evals" / "graph-cases.json",)
            if args.suite == "graph-smoke"
            else (
                _REPO_ROOT / "evals" / "cases.json",
                _REPO_ROOT / "evals" / "installed-v0.3-lineage-cases.json",
            )
        ),
        "skills_sha256": _tree_hash(_REPO_ROOT / "skills"),
    }


def _attempt_path(raw_root: Path, client: str, slot: ScheduledRun, attempt: int) -> Path:
    directory = raw_root / client / slot.case.id / ("%02d" % slot.repetition)
    return directory if attempt == 1 else directory / ("attempt-%02d" % attempt)


def _command_payload(command: Optional[CommandResult]) -> Optional[dict[str, object]]:
    if command is None:
        return None
    return {
        "argv": list(command.argv),
        "returncode": command.returncode,
        "stdout": command.stdout,
        "stderr": command.stderr,
        "elapsed_seconds": command.elapsed_seconds,
        "timed_out": command.timed_out,
    }


def _result_payload(result: RunResult) -> dict[str, object]:
    return {
        "case_id": result.case_id,
        "repetition": result.repetition,
        "client": result.client,
        "status": result.status.value,
        "reason": result.reason,
        "command": _command_payload(result.command),
        "final_output": result.final_output,
        "session_id": result.session_id,
        "metadata": [list(pair) for pair in result.metadata],
        "attempt": result.attempt,
        "retry_of": result.retry_of,
    }


def _complete_result(result: RunResult) -> bool:
    return (
        isinstance(result.case_id, str)
        and bool(result.case_id)
        and isinstance(result.repetition, int)
        and not isinstance(result.repetition, bool)
        and result.repetition > 0
        and isinstance(result.client, str)
        and bool(result.client)
        and isinstance(result.status, RunStatus)
        and (result.reason is None or isinstance(result.reason, str))
        and (result.final_output is None or isinstance(result.final_output, str))
        and (result.session_id is None or isinstance(result.session_id, str))
        and isinstance(result.attempt, int)
        and not isinstance(result.attempt, bool)
        and result.attempt > 0
        and (result.retry_of is None or isinstance(result.retry_of, str))
        and all(
            isinstance(pair, tuple)
            and len(pair) == 2
            and all(isinstance(value, str) for value in pair)
            for pair in result.metadata
        )
    )


def _result_from_payload(payload: object) -> Optional[RunResult]:
    if not isinstance(payload, dict):
        return None
    try:
        command_raw = payload["command"]
        command = (
            None
            if command_raw is None
            else CommandResult(
                tuple(command_raw["argv"]),
                command_raw["returncode"],
                command_raw["stdout"],
                command_raw["stderr"],
                command_raw["elapsed_seconds"],
                command_raw["timed_out"],
            )
        )
        result = RunResult(
            case_id=payload["case_id"],
            repetition=payload["repetition"],
            client=payload["client"],
            status=RunStatus(payload["status"]),
            reason=payload["reason"],
            command=command,
            final_output=payload["final_output"],
            session_id=payload["session_id"],
            metadata=tuple((pair[0], pair[1]) for pair in payload["metadata"]),
            attempt=payload["attempt"],
            retry_of=payload["retry_of"],
        )
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    return result if _complete_result(result) else None


def _status_stub(raw_root: Path, request: RunRequest) -> bool:
    """Persist a fixed safe state description when an adapter quarantines raw output."""
    try:
        record_run(
            raw_root,
            request.client,
            request.case.id,
            request.repetition,
            {
                "status.json": json.dumps(
                    {
                        "attempt": request.attempt,
                        "reason": "potential secret exposure",
                        "retry_of": request.retry_of,
                        "status": "blocked",
                    },
                    sort_keys=True,
                )
            },
            Path(tempfile.gettempdir()) / "eval-harness-controller-quarantine",
            attempt=request.attempt,
        )
    except (OSError, ValueError, PotentialSecretError):
        return False
    return True


def _safe_evidence_exists(raw_root: Path, request: RunRequest, result: RunResult) -> bool:
    path = _attempt_path(
        raw_root, request.client, ScheduledRun(request.case, request.repetition), request.attempt
    )
    if path.is_dir() and any(item.is_file() and not item.is_symlink() for item in path.rglob("*")):
        return True
    if result.status is RunStatus.BLOCKED and result.reason == "potential secret exposure":
        return _status_stub(raw_root, request)
    return False


def _attempt_row(result: RunResult) -> dict[str, object]:
    return {
        "case_id": result.case_id,
        "repetition": result.repetition,
        "attempt": result.attempt,
        "retry_of": result.retry_of,
        "result": _result_payload(result),
    }


def _final_row(result: RunResult) -> dict[str, object]:
    return {
        "case_id": result.case_id,
        "repetition": result.repetition,
        "selected_attempt": result.attempt,
        "result": _result_payload(result),
    }


def _write_derived(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _finalize(
    output_root: Path,
    ledger: dict[str, object],
    report: str,
    scored_digests: Optional[dict[str, str]] = None,
) -> bool:
    """Replace only derived batch views after raw evidence is append-only recorded."""
    try:
        _write_derived(output_root / "report.md", report)
        _write_derived(
            output_root / "controller.json", json.dumps(ledger, sort_keys=True, indent=2) + "\n"
        )
        return _refresh_manifest(output_root, scored_digests)
    except (OSError, ValueError):
        return False


def _manifest_contains_digests(manifest: str, expected: Optional[dict[str, str]]) -> bool:
    if not expected:
        return True
    rows = {}
    for line in manifest.splitlines():
        try:
            relative, digest = line.rsplit(" ", 1)
        except ValueError:
            return False
        rows[relative] = digest
    return all(rows.get(relative) == digest for relative, digest in expected.items())


def _refresh_manifest(output_root: Path, scored_digests: Optional[dict[str, str]] = None) -> bool:
    try:
        manifest = build_manifest(output_root)
        if not _manifest_contains_digests(manifest, scored_digests):
            return False
        _write_derived(output_root / "manifest.sha256", manifest)
        return _manifest_contains_digests(manifest, scored_digests) and not verify_manifest(
            output_root, manifest
        )
    except (OSError, ValueError):
        return False


def _missing_manifest_with_harness_state(output_root: Path) -> bool:
    """Fail closed rather than blessing existing harness state with a new seal."""
    if not output_root.exists() or (output_root / "manifest.sha256").exists():
        return False
    if (output_root / _RAW_DIRECTORY).exists():
        return True
    names = {path.name for path in output_root.iterdir()}
    return bool(names.intersection(_DERIVED_ARTIFACTS)) or any(
        name.startswith(".") and name.endswith(".tmp") for name in names
    )


def _load_existing(
    output_root: Path, raw_root: Path, identity: dict[str, object], schedule: Sequence[ScheduledRun]
):
    controller = output_root / "controller.json"
    manifest_path = output_root / "manifest.sha256"
    if not controller.exists():
        if not manifest_path.exists():
            return [], [], []
        try:
            return (
                ([], [], [])
                if not verify_manifest(output_root, manifest_path.read_text(encoding="utf-8"))
                else None
            )
        except (OSError, ValueError):
            return None
    if not manifest_path.is_file():
        return None
    try:
        if verify_manifest(output_root, manifest_path.read_text(encoding="utf-8")):
            return None
        ledger = json.loads(controller.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, RecursionError):
        return None
    if not isinstance(ledger, dict) or ledger.get("identity") != identity:
        return None
    attempts = ledger.get("attempts")
    runs = ledger.get("runs")
    if not isinstance(attempts, list) or not isinstance(runs, list):
        return None
    slots: dict[tuple[str, int], ScheduledRun] = {
        (slot.case.id, slot.repetition): slot for slot in schedule
    }
    results: list[RunResult] = []
    seen: set[tuple[str, int]] = set()
    for row in runs:
        if not isinstance(row, dict):
            return None
        result = _result_from_payload(row.get("result"))
        case_id = row.get("case_id")
        repetition = row.get("repetition")
        if (
            not isinstance(case_id, str)
            or isinstance(repetition, bool)
            or not isinstance(repetition, int)
        ):
            return None
        key = (case_id, repetition)
        if (
            result is None
            or key not in slots
            or key in seen
            or key != (result.case_id, result.repetition)
        ):
            return None
        if row.get("selected_attempt") != result.attempt:
            return None
        request = RunRequest(
            slots[key].case,
            result.repetition,
            result.client,
            None,
            None,
            raw_root,
            result.attempt,
            result.retry_of,
        )
        if not _safe_evidence_exists(raw_root, request, result):
            return None
        seen.add(key)
        results.append(result)
    attempt_keys: set[tuple[str, int, int]] = set()
    attempts_by_final: dict[tuple[str, int], dict[int, RunResult]] = {}
    for row in attempts:
        if not isinstance(row, dict):
            return None
        result = _result_from_payload(row.get("result"))
        case_id = row.get("case_id")
        repetition = row.get("repetition")
        attempt = row.get("attempt")
        if (
            not isinstance(case_id, str)
            or isinstance(repetition, bool)
            or not isinstance(repetition, int)
            or isinstance(attempt, bool)
            or not isinstance(attempt, int)
        ):
            return None
        attempt_key = (case_id, repetition, attempt)
        final_key = (case_id, repetition)
        if (
            result is None
            or final_key not in slots
            or attempt_key in attempt_keys
            or attempt_key != (result.case_id, result.repetition, result.attempt)
            or result.attempt not in (1, 2)
        ):
            return None
        if result.attempt == 1 and result.retry_of is not None:
            return None
        if result.attempt == 2 and result.retry_of != "%s/%02d" % final_key:
            return None
        attempt_keys.add(attempt_key)
        attempts_by_final.setdefault(final_key, {})[result.attempt] = result
    for result in results:
        history = attempts_by_final.get((result.case_id, result.repetition))
        if history is None or history.get(result.attempt) != result:
            return None
        if result.attempt == 2 and (
            history.get(1) is None or history[1].status is not RunStatus.INFRA_ERROR
        ):
            return None
    return attempts, runs, results


def _report_metadata(
    args: argparse.Namespace, probe: ClientProbe, results: Sequence[RunResult]
) -> dict[str, object]:
    return {
        "client": probe.client,
        "version": probe.version or "unavailable",
        "plugin_version": probe.plugin_version or "unavailable",
        "enabled_composition": _composition(probe),
        "enabled_plugins": sorted(probe.enabled_plugins),
        "model": args.model or "omitted",
        "reasoning": args.reasoning or "omitted",
        "repetitions": args.repetitions,
    }


def _score_row(score: MechanicalScore) -> dict[str, object]:
    return {
        "case_id": score.case_id,
        "repetition": score.repetition,
        "passed": score.passed,
        "findings": list(score.findings),
    }


def _graph_score_row(score: GraphScore, repetition: int) -> dict[str, object]:
    payload = asdict(score)
    payload["repetition"] = repetition
    payload["findings"] = list(score.findings)
    payload["providers"] = list(score.providers)
    payload["uncovered_high_risk_nodes"] = list(score.uncovered_high_risk_nodes)
    payload["matched_path_ids"] = list(score.matched_path_ids)
    return payload


def _resource_measurement(case: CaseSpec) -> tuple[int, int]:
    paths = [_REPO_ROOT / "skills" / "using-requirements-impact-refiner" / "SKILL.md"]
    if case.kind != "negative":
        adapter = (
            "integration-superpowers.md"
            if case.id == "INT-superpowers"
            else "integration-generic.md"
        )
        core = _REPO_ROOT / "skills" / "requirements-impact-refiner"
        paths.extend(
            (
                core / "SKILL.md",
                core / "references" / "controller-workflow.md",
                core / "references" / adapter,
            )
        )
    payloads = [path.read_bytes() for path in paths]
    words = sum(len(payload.decode("utf-8", errors="strict").split()) for payload in payloads)
    return sum(len(payload) for payload in payloads), words


def _turn_usage(jsonl_payloads: Sequence[bytes]) -> tuple[Optional[int], Optional[int]]:
    usages = []
    for payload in jsonl_payloads:
        for line in payload.decode("utf-8", errors="strict").splitlines():
            event = json.loads(line)
            if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
                usages.append(event["usage"])
    if not usages:
        return None, None
    if any(
        not isinstance(row.get("input_tokens"), int)
        or isinstance(row.get("input_tokens"), bool)
        or not isinstance(row.get("output_tokens"), int)
        or isinstance(row.get("output_tokens"), bool)
        for row in usages
    ):
        return None, None
    return (
        sum(row["input_tokens"] for row in usages),
        sum(row["output_tokens"] for row in usages),
    )


def _smoke_observation(
    raw_root: Path,
    client: str,
    slot: ScheduledRun,
    result: RunResult,
    score: MechanicalScore,
) -> PerformanceObservation:
    attempt_path = _attempt_path(raw_root, client, slot, result.attempt)
    prompt_names = ("first.prompt.txt", "second.prompt.txt")[: len(slot.case.turns)]
    jsonl_names = ("first.jsonl", "second.jsonl")[: len(slot.case.turns)]
    prompts = [
        _read_selected_file(raw_root, attempt_path / name, "smoke prompt")[0]
        for name in prompt_names
    ]
    jsonl_payloads = [
        _read_selected_file(raw_root, attempt_path / name, "smoke JSONL")[0] for name in jsonl_names
    ]
    selected_name = "second.final.txt" if slot.case.kind == "lineage" else "first.final.txt"
    output = _read_selected_file(raw_root, attempt_path / selected_name, "smoke final output")[
        0
    ].decode("utf-8", errors="strict")
    controller_payload = json.loads(
        _read_selected_file(
            raw_root,
            attempt_path / "controller-evidence.json",
            "smoke controller evidence",
        )[0].decode("utf-8", errors="strict")
    )
    metadata = json.loads(
        _read_selected_file(raw_root, attempt_path / "metadata.json", "smoke metadata")[0].decode(
            "utf-8", errors="strict"
        )
    )
    durations = metadata.get("execution_commands", [])
    duration_ms = None
    if isinstance(durations, list) and all(
        isinstance(row, dict) and isinstance(row.get("elapsed_seconds"), (int, float))
        for row in durations
    ):
        duration_ms = round(sum(row["elapsed_seconds"] for row in durations) * 1000)
    input_tokens, output_tokens = _turn_usage(jsonl_payloads)
    impact_ids: tuple[str, ...] = ()
    state_match = slot.case.kind == "negative"
    if slot.case.kind != "negative":
        if _captured_canonical_report(raw_root, attempt_path, slot.case.kind == "lineage") is None:
            raise ValueError("smoke report evidence is missing")
        report_root = attempt_path / "workspace-reports"
        reports = [
            path for path in report_root.iterdir() if path.is_dir() and not path.is_symlink()
        ]
        if len(reports) != 1:
            raise ValueError("smoke report evidence requires exactly one report")
        pointer = json.loads(
            _read_selected_file(raw_root, reports[0] / "current.json", "smoke current pointer")[
                0
            ].decode("utf-8", errors="strict")
        )
        state = json.loads(
            _read_selected_file(raw_root, reports[0] / pointer["state"], "smoke compact state")[
                0
            ].decode("utf-8", errors="strict")
        )
        impacts = state.get("impacts") if isinstance(state, dict) else None
        if not isinstance(impacts, list) or any(
            not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in impacts
        ):
            raise ValueError("smoke compact state impacts are invalid")
        impact_ids = tuple(
            sorted(
                row["id"]
                for row in impacts
                if isinstance(row, dict) and isinstance(row.get("id"), str)
            )
        )
        state_match = bool(impact_ids) and all(identifier in output for identifier in impact_ids)
    routed_bytes, routed_words = _resource_measurement(slot.case)
    return PerformanceObservation(
        case_id=slot.case.id,
        repetition=slot.repetition,
        status=result.status,
        attempt=result.attempt,
        retry_of=result.retry_of,
        prompt_bytes=sum(len(payload) for payload in prompts),
        routed_resource_bytes=routed_bytes,
        routed_resource_words=routed_words,
        output_bytes=len(output.encode("utf-8")),
        output_words=len(output.split()),
        duration_ms=duration_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        impact_ids=impact_ids,
        state_markdown_match=state_match,
        workflow_boundary_passed=score.passed,
        controller_begin_calls=controller_payload.get("begin_calls", -1),
        controller_finalize_calls=controller_payload.get("finalize_calls", -1),
        controller_draft_ids_match=controller_payload.get("draft_ids_match") is True,
        controller_finalize_succeeded=controller_payload.get("finalize_succeeded") is True,
        controller_display_text_exact_match=controller_payload.get("display_text_exact_match")
        is True,
        controller_display_text_presentation_equivalent=controller_payload.get(
            "display_text_presentation_equivalent"
        )
        is True,
        controller_display_comparison=controller_payload.get("display_comparison", ""),
    )


_GRAPH_CONFIDENCE_RANK = {
    "verified-provider": 0,
    "verified-source": 1,
    "structural-inferred": 2,
    "lexical": 3,
}


def _receipt_structured_path(receipt, path):
    nodes = {row["id"]: row for row in receipt["nodes"]}
    edges = {row["id"]: row for row in receipt["edges"]}
    records = [nodes[key] for key in path["nodes"]]
    records.extend(edges[key] for key in path["edges"])
    confidences = [row["confidence"] for row in records]
    return {
        "id": path["id"],
        "labels": [nodes[key]["label"] for key in path["nodes"]],
        "providers": list(dict.fromkeys(row["provider"] for row in records if row.get("provider")))
        or ["unavailable"],
        "confidence": max(confidences, key=lambda value: _GRAPH_CONFIDENCE_RANK[value]),
        "locations": list(dict.fromkeys(row["location"] for row in records if row.get("location"))),
    }


def _graph_state_parity(raw_root, attempt_path, receipt, receipt_digest, score):
    captured = _captured_canonical_report(raw_root, attempt_path, False)
    if captured is None:
        return False
    report_root = attempt_path / "workspace-reports"
    directories = [
        path for path in report_root.iterdir() if path.is_dir() and not path.is_symlink()
    ]
    if len(directories) != 1:
        return False
    pointer = json.loads(
        _read_selected_file(raw_root, directories[0] / "current.json", "graph current pointer")[
            0
        ].decode("utf-8", errors="strict")
    )
    state = json.loads(
        _read_selected_file(raw_root, directories[0] / pointer["state"], "graph compact state")[
            0
        ].decode("utf-8", errors="strict")
    )
    coverage = [
        row
        for row in state.get("scope", ())
        if isinstance(row, dict) and row.get("boundary") == "Impact graph coverage"
    ]
    if len(coverage) != 1 or (
        f"receipt {receipt['receipt_id']}; sha256 {receipt_digest};"
        not in coverage[0].get("confidence", "")
    ):
        return False
    expected_paths: dict[str, object] = {
        identifier: _receipt_structured_path(receipt, path)
        for path in receipt["paths"]
        if isinstance(identifier := path.get("id"), str)
    }
    observed: dict[str, object] = {}
    for row in state.get("graph_paths", ()):
        if not isinstance(row, dict) or not isinstance(row.get("paths"), list):
            return False
        for path in row["paths"]:
            if not isinstance(path, dict):
                return False
            identifier = path.get("id")
            if not isinstance(identifier, str):
                return False
            if identifier in observed and observed[identifier] != path:
                return False
            observed[identifier] = path
    if not set(score.matched_path_ids).intersection(observed):
        return False
    return all(expected_paths.get(key) == value for key, value in observed.items())


def _graph_observation(raw_root, client, slot, result, mechanical_score):
    cases = {case.id: case for case in load_graph_cases()}
    case = cases[slot.case.id]
    attempt_path = _attempt_path(raw_root, client, slot, result.attempt)
    metadata = json.loads(
        _read_selected_file(raw_root, attempt_path / "metadata.json", "graph run metadata")[
            0
        ].decode("utf-8", errors="strict")
    )
    expected_policy = graph_run_policy(case)
    if not isinstance(metadata, dict) or metadata.get("graph_policy") != expected_policy:
        raise ValueError("graph run policy does not match staged builtin policy")
    output_bytes, _, _ = _read_selected_file(
        raw_root, attempt_path / "first.final.txt", "graph final output"
    )
    output = output_bytes.decode("utf-8", errors="strict")
    controller_bytes, controller_digest, controller_relative = _read_selected_file(
        raw_root,
        attempt_path / "controller-evidence.json",
        "graph controller evidence",
    )
    controller = json.loads(controller_bytes.decode("utf-8", errors="strict"))
    jsonl_bytes, _, _ = _read_selected_file(
        raw_root, attempt_path / "first.jsonl", "graph controller JSONL"
    )
    input_tokens, output_tokens = _turn_usage((jsonl_bytes,))
    receipt = None
    receipt_digests: tuple[tuple[str, str], ...] = ((controller_relative, controller_digest),)
    parity = controller.get("valid") is True
    if case.kind == "positive":
        for field in (
            "draft_ids",
            "receipt_ids",
            "receipt_paths",
            "receipt_sha256",
            "trace_compact_graph_sha256",
            "trace_request_sha256",
            "trace_seeds",
        ):
            if not isinstance(controller.get(field), list) or len(controller[field]) != 1:
                raise ValueError(f"graph controller {field} is not exact")
        draft_id = controller["draft_ids"][0]
        receipt_path = controller["receipt_paths"][0]
        if receipt_path != f".requirements-impact-refiner/graph/{draft_id}.json":
            raise ValueError("graph receipt path disagrees with draft ID")
        if controller["trace_seeds"] != [expected_policy["seeds"]]:
            raise ValueError("graph trace arguments do not match catalog seeds")
        payload, digest, relative = _read_selected_file(
            raw_root,
            attempt_path / "workspace-graph" / f"{draft_id}.json",
            "graph receipt",
        )
        receipt_digests = (*receipt_digests, (relative, digest))
        if digest != controller["receipt_sha256"][0]:
            raise ValueError("graph receipt digest disagrees with trace result")
        receipt = json.loads(payload.decode("utf-8", errors="strict"))
        if canonical_receipt_bytes(receipt) != payload:
            raise ValueError("graph receipt bytes are not canonical")
        if (
            receipt.get("draft_id") != draft_id
            or receipt.get("receipt_id") != controller["receipt_ids"][0]
        ):
            raise ValueError("graph receipt identity disagrees with controller trace")
        if receipt.get("request_sha256") != controller["trace_request_sha256"][0]:
            raise ValueError("graph receipt request identity does not match traced catalog seeds")
        provider_inventory = [
            row.get("name") for row in receipt.get("providers", ()) if isinstance(row, dict)
        ]
        if (
            receipt.get("settings") != expected_policy["settings"]
            or provider_inventory != expected_policy["provider_inventory"]
        ):
            raise ValueError("graph receipt does not match staged builtin run policy")
        compact_digest = hashlib.sha256(
            json.dumps(
                compact_graph(receipt),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if compact_digest != controller["trace_compact_graph_sha256"][0]:
            raise ValueError("graph compact trace disagrees with receipt")
    graph_score = score_graph(case, receipt, output)
    if case.kind == "positive":
        parity = parity and _graph_state_parity(
            raw_root,
            attempt_path,
            receipt,
            controller["receipt_sha256"][0],
            graph_score,
        )
    duration = None if receipt is None else receipt.get("timings_ms", {}).get("total")
    _routed_bytes, routed_words = _resource_measurement(slot.case)
    observation = GraphPerformanceObservation(
        case_id=slot.case.id,
        repetition=slot.repetition,
        status=result.status,
        mechanical_passed=mechanical_score.passed,
        graph_passed=graph_score.passed,
        attempt=result.attempt,
        retry_of=result.retry_of,
        graph_duration_ms=duration,
        output_words=len(output.split()),
        routed_resource_words=routed_words,
        receipt_state_provider_parity=parity,
        uncovered_high_risk_nodes=graph_score.uncovered_high_risk_nodes,
        controller_begin_calls=controller.get("begin_calls", -1),
        controller_trace_calls=controller.get("trace_calls", -1),
        controller_finalize_calls=controller.get("finalize_calls", -1),
        controller_evidence_valid=controller.get("valid") is True,
        duplicate_or_error_calls=controller.get("duplicate_or_error_calls") is not False,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    return observation, graph_score, receipt_digests


def _scoring_evidence_failure(
    slot: ScheduledRun, result: RunResult, finding: str
) -> tuple[MechanicalScore, bool, tuple[tuple[str, str], ...]]:
    return (
        MechanicalScore(slot.case.id, slot.repetition, False, (finding,)),
        False,
        (),
    )


def _read_selected_file(raw_root: Path, path: Path, label: str) -> tuple[bytes, str, str]:
    """Read exact bytes through descriptor-relative no-follow traversal."""
    raw_root = Path(raw_root)
    path = Path(path)
    try:
        relative = path.relative_to(raw_root)
    except ValueError as error:
        raise ValueError("selected scoring evidence is outside raw root") from error
    if any(component in ("", ".", "..") for component in relative.parts):
        raise ValueError("selected scoring evidence contains an unsafe path component")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW
    directory_fd = None
    try:
        directory_fd = os.open(raw_root, directory_flags)
        if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
            raise ValueError("raw evidence root must be a regular directory")
        for component in relative.parts[:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            if not stat.S_ISDIR(os.fstat(next_fd).st_mode):
                os.close(next_fd)
                raise ValueError("selected attempt path must contain regular directories")
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(relative.parts[-1], file_flags, dir_fd=directory_fd)
        try:
            before = os.fstat(file_fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError(f"{label} must be a regular non-symlink file")
            chunks = []
            while True:
                chunk = os.read(file_fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(file_fd)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise ValueError(f"{label} changed while being read")
            payload = b"".join(chunks)
        finally:
            os.close(file_fd)
    except OSError as error:
        raise ValueError(f"{label} must be a regular non-symlink file") from error
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
    relative_manifest = f"raw/{relative.as_posix()}"
    return payload, hashlib.sha256(payload).hexdigest(), relative_manifest


def _captured_canonical_report(
    raw_root: Path, attempt_path: Path, lineage: bool
) -> Optional[tuple[bytes, Optional[bytes], tuple[tuple[str, str], ...]]]:
    report_root = attempt_path / "workspace-reports"
    if not report_root.exists():
        return None
    if report_root.is_symlink() or not report_root.is_dir():
        raise ValueError("captured workspace report root must be a regular directory")
    report_directories = [path for path in report_root.iterdir() if path.is_dir()]
    if len(report_directories) != 1 or any(path.is_symlink() for path in report_directories):
        raise ValueError("captured workspace reports require exactly one regular report directory")
    report_directory = report_directories[0]
    if _REPORT_ID_PATTERN.fullmatch(report_directory.name) is None:
        raise ValueError("captured workspace report has an invalid report ID")
    pointer_bytes, pointer_digest, pointer_path = _read_selected_file(
        raw_root, report_directory / "current.json", "captured current pointer"
    )
    try:
        pointer = json.loads(pointer_bytes.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("captured current pointer is not valid UTF-8 JSON") from error
    if not isinstance(pointer, dict) or set(pointer) != _POINTER_KEYS:
        raise ValueError("captured current pointer has an invalid schema")
    report_id = pointer.get("report_id")
    revision = pointer.get("revision")
    if (
        pointer.get("schema_version") != 1
        or report_id != report_directory.name
        or not isinstance(revision, int)
        or isinstance(revision, bool)
        or revision < 1
    ):
        raise ValueError("captured current pointer identity is invalid")
    expected_state = "revision-%04d.json" % revision
    expected_markdown = "revision-%04d.md" % revision
    if pointer.get("state") != expected_state or pointer.get("markdown") != expected_markdown:
        raise ValueError("captured current pointer paths are not canonical")
    state_bytes, state_digest, state_path = _read_selected_file(
        raw_root, report_directory / expected_state, "captured compact state"
    )
    markdown_bytes, markdown_digest, markdown_path = _read_selected_file(
        raw_root, report_directory / expected_markdown, "captured canonical Markdown"
    )
    try:
        state = json.loads(state_bytes.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("captured compact state is not valid UTF-8 JSON") from error
    if not isinstance(state, dict) or not isinstance(state.get("report"), dict):
        raise ValueError("captured compact state report metadata is unavailable")
    if (state["report"].get("id"), state["report"].get("revision")) != (report_id, revision):
        raise ValueError("captured compact state disagrees with current pointer")
    if pointer.get("markdown_sha256") != markdown_digest:
        raise ValueError("captured current pointer Markdown SHA-256 does not match")
    rendered_markdown = _impact_renderer.render_markdown(state).encode("utf-8")
    if rendered_markdown != markdown_bytes:
        raise ValueError("captured compact state and canonical Markdown disagree")
    digests = [
        (pointer_path, pointer_digest),
        (state_path, state_digest),
        (markdown_path, markdown_digest),
    ]
    previous_bytes = None
    if lineage and revision < 2:
        raise ValueError("captured lineage report did not publish a new revision")
    if revision > 1:
        previous_name = "revision-%04d.md" % (revision - 1)
        previous_bytes, previous_digest, previous_path = _read_selected_file(
            raw_root,
            report_directory / previous_name,
            "captured canonical predecessor Markdown",
        )
        digests.append((previous_path, previous_digest))
    return markdown_bytes, previous_bytes, tuple(digests)


def _score_selected_attempt(
    raw_root: Path,
    expected_client: str,
    slot: ScheduledRun,
    result: RunResult,
) -> tuple[MechanicalScore, bool, tuple[tuple[str, str], ...]]:
    """Bind mechanical scoring to the immutable bytes of one selected attempt."""
    expected = (slot.case.id, slot.repetition, expected_client)
    observed = (result.case_id, result.repetition, result.client)
    expected_retry = None if result.attempt == 1 else "%s/%02d" % (slot.case.id, slot.repetition)
    if observed != expected or result.attempt not in (1, 2) or result.retry_of != expected_retry:
        return _scoring_evidence_failure(
            slot, result, "selected scoring result has wrong case, repetition, client, or attempt"
        )
    if result.status is not RunStatus.PASS:
        return score_mechanical(slot.case, result), True, ()

    attempt_path = _attempt_path(raw_root, expected_client, slot, result.attempt)
    digests = []
    try:
        metadata_bytes, metadata_digest, metadata_path = _read_selected_file(
            raw_root, attempt_path / "metadata.json", "selected attempt metadata"
        )
        digests.append((metadata_path, metadata_digest))
        metadata = json.loads(metadata_bytes.decode("utf-8", errors="strict"))
    except UnicodeDecodeError:
        return _scoring_evidence_failure(
            slot, result, "selected attempt metadata is not valid UTF-8"
        )
    except (OSError, ValueError, json.JSONDecodeError, RecursionError) as error:
        return _scoring_evidence_failure(slot, result, str(error))
    if not isinstance(metadata, dict) or (
        metadata.get("attempt"),
        metadata.get("client"),
        metadata.get("retry_of"),
    ) != (result.attempt, expected_client, expected_retry):
        return _scoring_evidence_failure(
            slot, result, "selected attempt metadata does not match result"
        )

    selected_name = "second.final.txt" if slot.case.kind == "lineage" else "first.final.txt"
    try:
        selected_bytes, selected_digest, selected_path = _read_selected_file(
            raw_root, attempt_path / selected_name, "selected final output"
        )
        digests.append((selected_path, selected_digest))
        selected_output = selected_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _scoring_evidence_failure(slot, result, "selected final output is not valid UTF-8")
    except (OSError, ValueError) as error:
        return _scoring_evidence_failure(slot, result, str(error))
    if selected_output != result.final_output:
        return _scoring_evidence_failure(
            slot, result, "selected final output does not match raw evidence"
        )

    if metadata.get("plugin_version") == "0.4.0":
        streams = []
        turn_outputs = []
        turn_names = ("first", "second")[: len(slot.case.turns)]
        try:
            controller_bytes, controller_digest, controller_path = _read_selected_file(
                raw_root,
                attempt_path / "controller-evidence.json",
                "selected controller evidence",
            )
            digests.append((controller_path, controller_digest))
            stored_controller = json.loads(controller_bytes.decode("utf-8", errors="strict"))
            for name in turn_names:
                jsonl_bytes, jsonl_digest, jsonl_path = _read_selected_file(
                    raw_root, attempt_path / f"{name}.jsonl", "selected controller JSONL"
                )
                final_bytes, final_digest, final_path = _read_selected_file(
                    raw_root, attempt_path / f"{name}.final.txt", "selected turn output"
                )
                streams.append(jsonl_bytes.decode("utf-8", errors="strict"))
                turn_outputs.append(final_bytes.decode("utf-8", errors="strict"))
                digests.extend(((jsonl_path, jsonl_digest), (final_path, final_digest)))
            expected_turns = 0 if slot.case.kind == "negative" else len(slot.case.turns)
            derived_controller = analyze_controller_trace(
                streams,
                tuple(turn_outputs) if expected_turns else selected_output,
                expected_turns=expected_turns,
            )
            if stored_controller != json.loads(derived_controller.to_json()):
                raise ValueError("selected controller evidence disagrees with raw JSONL")
            if not derived_controller.valid:
                raise ValueError("selected controller evidence is invalid")
            expected_payload = _payload_identity.payload_sha256(_REPO_ROOT)
            if derived_controller.installed_payload_sha256 != (
                (expected_payload,) * expected_turns
            ):
                raise ValueError("installed controller payload does not match reviewed source")
        except (
            OSError,
            ValueError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            RecursionError,
        ) as error:
            return _scoring_evidence_failure(slot, result, str(error))

    scoring_result = result
    previous_bytes = None
    try:
        captured = _captured_canonical_report(raw_root, attempt_path, slot.case.kind == "lineage")
    except (OSError, ValueError) as error:
        return _scoring_evidence_failure(slot, result, str(error))
    if captured is not None:
        canonical_bytes, previous_bytes, captured_digests = captured
        try:
            canonical_output = canonical_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return _scoring_evidence_failure(
                slot, result, "captured canonical Markdown is not valid UTF-8"
            )
        digests.extend(captured_digests)
        scoring_result = replace(result, final_output=canonical_output)
    elif slot.case.kind == "lineage":
        try:
            previous_bytes, previous_digest, previous_path = _read_selected_file(
                raw_root,
                attempt_path / "first.final.txt",
                "lineage predecessor",
            )
            digests.append((previous_path, previous_digest))
            previous_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return _scoring_evidence_failure(slot, result, "lineage predecessor is not valid UTF-8")
        except (OSError, ValueError) as error:
            return _scoring_evidence_failure(slot, result, str(error))
    return (
        score_mechanical(slot.case, scoring_result, previous_bytes=previous_bytes),
        True,
        tuple(digests),
    )


def _validate_attempt_evidence(
    raw_root: Path,
    expected_client: str,
    slots: dict[tuple[str, int], ScheduledRun],
    attempts: Sequence[dict[str, object]],
) -> tuple[bool, tuple[tuple[str, str], ...]]:
    """Validate every retry-history result and its raw canonical metadata."""
    history: dict[tuple[str, int], dict[int, RunResult]] = {}
    digests: list[tuple[str, str]] = []
    for row in attempts:
        if not isinstance(row, dict):
            return False, ()
        result = _result_from_payload(row.get("result"))
        if result is None:
            return False, ()
        key = (result.case_id, result.repetition)
        slot = slots.get(key)
        expected_retry = (
            None if result.attempt == 1 else "%s/%02d" % (result.case_id, result.repetition)
        )
        if (
            slot is None
            or result.client != expected_client
            or result.attempt not in (1, 2)
            or result.retry_of != expected_retry
            or (row.get("case_id"), row.get("repetition"), row.get("attempt"))
            != (result.case_id, result.repetition, result.attempt)
        ):
            return False, ()
        attempts_for_key = history.setdefault(key, {})
        if result.attempt in attempts_for_key:
            return False, ()
        attempts_for_key[result.attempt] = result
        attempt_path = _attempt_path(raw_root, expected_client, slot, result.attempt)
        try:
            payload, digest, relative = _read_selected_file(
                raw_root,
                attempt_path / "metadata.json",
                "attempt metadata",
            )
            metadata = json.loads(payload.decode("utf-8", errors="strict"))
        except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
            return False, ()
        if not isinstance(metadata, dict) or (
            metadata.get("attempt"),
            metadata.get("client"),
            metadata.get("retry_of"),
        ) != (result.attempt, expected_client, expected_retry):
            return False, ()
        digests.append((relative, digest))

    for attempts_for_key in history.values():
        second = attempts_for_key.get(2)
        if second is not None and (
            attempts_for_key.get(1) is None
            or attempts_for_key[1].status is not RunStatus.INFRA_ERROR
        ):
            return False, ()
    return True, tuple(digests)


def _smoke_performance_payload(
    observations: Sequence[PerformanceObservation], gate: SmokeGateResult
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for observation in observations:
        row = dict(asdict(observation))
        row["status"] = observation.status.value
        row["impact_ids"] = list(observation.impact_ids)
        rows.append(row)
    gate_row = dict(asdict(gate))
    errors = gate_row.get("errors")
    if isinstance(errors, tuple):
        gate_row["errors"] = list(errors)
    return {"observations": rows, "gate": gate_row}


def _graph_performance_payload(
    observations: Sequence[GraphPerformanceObservation], gate: GraphSmokeGateResult
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for observation in observations:
        row = dict(asdict(observation))
        row["status"] = observation.status.value
        row["uncovered_high_risk_nodes"] = list(observation.uncovered_high_risk_nodes)
        rows.append(row)
    gate_row = dict(asdict(gate))
    errors = gate_row.get("errors")
    if isinstance(errors, tuple):
        gate_row["errors"] = list(errors)
    return {"observations": rows, "gate": gate_row}


def run_batch(
    args: argparse.Namespace, adapter: Any, cases: Optional[Iterable[CaseSpec]] = None
) -> int:
    """Append missing finals to a compatible sealed batch and reseal derived views."""
    if args.suite is None or (
        args.client == "claude" and (args.model is not None or args.reasoning is not None)
    ):
        return 2
    output_root = Path(args.output)
    if _missing_manifest_with_harness_state(output_root):
        return 1
    try:
        default_cases = (
            tuple(case.to_case_spec() for case in load_graph_cases())
            if args.suite == "graph-smoke"
            else load_all()
        )
        schedule = build_schedule(
            default_cases if cases is None else cases, args.suite, args.repetitions
        )
        probe = adapter.prepare()
        if not probe.available:
            return 1
        if args.suite == "graph-smoke" and probe.plugin_version != "0.4.0":
            return 1
    except (OSError, ValueError, AttributeError):
        return 1
    raw_root = output_root / _RAW_DIRECTORY
    identity = _batch_identity(args, probe)
    existing = _load_existing(output_root, raw_root, identity, schedule)
    if existing is None:
        return 1
    attempts, finals, results = existing
    final_keys = {(result.case_id, result.repetition) for result in results}
    slots = {(slot.case.id, slot.repetition): slot for slot in schedule}
    for slot in schedule:
        key = (slot.case.id, slot.repetition)
        if key in final_keys:
            continue
        request = RunRequest(
            slot.case, slot.repetition, args.client, args.model, args.reasoning, raw_root
        )
        if _attempt_path(raw_root, args.client, slot, 1).exists():
            return 1
        try:
            first = adapter.execute(request)
        except (OSError, ValueError, AttributeError):
            return 1
        if not _complete_result(first) or (
            first.case_id,
            first.repetition,
            first.client,
            first.attempt,
            first.retry_of,
        ) != (slot.case.id, slot.repetition, args.client, 1, None):
            return 1
        if not _safe_evidence_exists(raw_root, request, first):
            return 1
        attempts.append(_attempt_row(first))
        selected = first
        if first.status is RunStatus.INFRA_ERROR and args.suite != "graph-smoke":
            retry_of = "%s/%02d" % key
            retry_request = RunRequest(
                slot.case,
                slot.repetition,
                args.client,
                args.model,
                args.reasoning,
                raw_root,
                2,
                retry_of,
            )
            if _attempt_path(raw_root, args.client, slot, 2).exists():
                return 1
            try:
                selected = adapter.execute(retry_request)
            except (OSError, ValueError, AttributeError):
                return 1
            if not _complete_result(selected) or (
                selected.case_id,
                selected.repetition,
                selected.client,
                selected.attempt,
                selected.retry_of,
            ) != (slot.case.id, slot.repetition, args.client, 2, retry_of):
                return 1
            if not _safe_evidence_exists(raw_root, retry_request, selected):
                return 1
            attempts.append(_attempt_row(selected))
        finals.append(_final_row(selected))
        results.append(selected)
        final_keys.add(key)
    if final_keys != set(slots):
        return 1
    index = {(slot.case.id, slot.repetition): position for position, slot in enumerate(schedule)}
    results.sort(key=lambda result: index[(result.case_id, result.repetition)])
    finals.sort(key=lambda row: index[(row["case_id"], row["repetition"])])
    attempt_evidence_valid, attempt_digests = _validate_attempt_evidence(
        raw_root, args.client, slots, attempts
    )
    if not attempt_evidence_valid:
        return 1
    scored = [
        _score_selected_attempt(
            raw_root,
            args.client,
            slots[(result.case_id, result.repetition)],
            result,
        )
        for result in results
    ]
    scores = [score for score, _, _ in scored]
    scoring_evidence_valid = all(valid for _, valid, _ in scored)
    scored_digests = {
        relative: digest
        for rows in (attempt_digests, *tuple(rows for _, _, rows in scored))
        for relative, digest in rows
    }
    if not scoring_evidence_valid:
        return 1
    smoke_gate = None
    graph_gate = None
    graph_scores: list[GraphScore] = []
    extraction_errors: list[str] = []
    if args.suite == "smoke" and probe.plugin_version == "0.4.0":
        smoke_observations: list[PerformanceObservation] = []
        for result, score in zip(results, scores):
            slot = slots[(result.case_id, result.repetition)]
            try:
                observation = _smoke_observation(raw_root, args.client, slot, result, score)
                if not isinstance(observation, PerformanceObservation):
                    raise ValueError("smoke observation is missing or invalid")
                smoke_observations.append(observation)
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                RecursionError,
            ) as error:
                extraction_errors.append(f"{result.case_id} performance evidence invalid: {error}")
        smoke_gate = evaluate_smoke_gate(smoke_observations)
        if extraction_errors:
            smoke_gate = replace(
                smoke_gate,
                passed=False,
                errors=tuple(sorted(set(smoke_gate.errors + tuple(extraction_errors)))),
            )
        performance_payload = _smoke_performance_payload(smoke_observations, smoke_gate)
        try:
            _write_derived(
                output_root / "performance.json",
                json.dumps(performance_payload, sort_keys=True, indent=2) + "\n",
            )
        except OSError:
            return 1
    if args.suite == "graph-smoke":
        graph_observations: list[GraphPerformanceObservation] = []
        graph_extraction_errors: list[str] = []
        graph_digest_rows: list[tuple[str, str]] = []
        for result, score in zip(results, scores):
            slot = slots[(result.case_id, result.repetition)]
            try:
                observation, graph_score, digests = _graph_observation(
                    raw_root, args.client, slot, result, score
                )
                graph_observations.append(observation)
                graph_scores.append(graph_score)
                graph_digest_rows.extend(digests)
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                RecursionError,
            ) as error:
                graph_extraction_errors.append(f"{result.case_id} graph evidence invalid: {error}")
        graph_gate = evaluate_graph_smoke(graph_observations)
        if graph_extraction_errors:
            graph_gate = replace(
                graph_gate,
                passed=False,
                errors=tuple(sorted(set(graph_gate.errors + tuple(graph_extraction_errors)))),
            )
        scored_digests.update(graph_digest_rows)
        performance_payload = _graph_performance_payload(graph_observations, graph_gate)
        graph_payload = [
            _graph_score_row(score, result.repetition)
            for score, result in zip(graph_scores, results)
        ]
        try:
            _write_derived(
                output_root / "graph-scores.json",
                json.dumps({"scores": graph_payload}, sort_keys=True, indent=2) + "\n",
            )
            _write_derived(
                output_root / "performance.json",
                json.dumps(performance_payload, sort_keys=True, indent=2) + "\n",
            )
        except OSError:
            return 1
    ledger = {
        "identity": identity,
        "suite": args.suite,
        "repetitions": args.repetitions,
        "attempts": attempts,
        "runs": finals,
        "mechanical_scores": [_score_row(score) for score in scores],
    }
    if smoke_gate is not None:
        ledger["smoke_gate"] = {
            "passed": smoke_gate.passed,
            "errors": list(smoke_gate.errors),
            "median_output_words": smoke_gate.median_output_words,
            "median_routed_resource_words": smoke_gate.median_routed_resource_words,
        }
    if graph_gate is not None:
        ledger["graph_scores"] = [
            _graph_score_row(score, result.repetition)
            for score, result in zip(graph_scores, results)
        ]
        ledger["graph_smoke_gate"] = {
            "passed": graph_gate.passed,
            "errors": list(graph_gate.errors),
            "median_graph_duration_ms": graph_gate.median_graph_duration_ms,
            "median_output_words": graph_gate.median_output_words,
            "median_routed_resource_words": graph_gate.median_routed_resource_words,
        }
    try:
        report = render_report(results, _report_metadata(args, probe, results), scores)
    except (TypeError, ValueError):
        return 1
    if not _finalize(output_root, ledger, report, scored_digests):
        return 1
    return (
        1
        if (
            any(result.status is RunStatus.INVALID_EVIDENCE for result in results)
            or (
                args.suite == "graph-smoke"
                and any(result.status is not RunStatus.PASS for result in results)
            )
            or (smoke_gate is not None and not smoke_gate.passed)
            or (graph_gate is not None and not graph_gate.passed)
        )
        else 0
    )


def _probe_payload(probe: ClientProbe) -> dict[str, object]:
    return {
        "client": probe.client,
        "available": probe.available,
        "version": probe.version,
        "authenticated": probe.authenticated,
        "plugin_version": probe.plugin_version,
        "enabled_plugins": list(probe.enabled_plugins),
        "capabilities": list(probe.capabilities),
        "reason": probe.reason,
    }


def _probe_artifacts(adapter: Any, probe: ClientProbe) -> dict[str, str]:
    commands = getattr(adapter, "probe_results", getattr(adapter, "structural_results", ()))
    artifacts = {"metadata.json": json.dumps(_probe_payload(probe), sort_keys=True)}
    for index, command in enumerate(commands, start=1):
        if not isinstance(command, CommandResult):
            raise ValueError("probe results must be CommandResult values")
        name = "probe-%02d" % index
        artifacts[f"{name}.stdout.txt"] = command.stdout
        artifacts[f"{name}.stderr.txt"] = command.stderr
    return artifacts


def run_probe(args: argparse.Namespace, adapter: Any) -> int:
    """Persist a probe as raw evidence and seal it with controller metadata."""
    output_root = Path(args.output)
    raw_root = output_root / _RAW_DIRECTORY
    probes_path = output_root / "probes.json"
    if _missing_manifest_with_harness_state(output_root):
        return 1
    try:
        if (output_root / "manifest.sha256").exists() and verify_manifest(
            output_root, (output_root / "manifest.sha256").read_text(encoding="utf-8")
        ):
            return 1
        if probes_path.exists():
            probes = json.loads(probes_path.read_text(encoding="utf-8"))
            if not isinstance(probes, dict) or not isinstance(probes.get("probes"), list):
                return 1
            entries = probes["probes"]
        else:
            entries = []
        probe = adapter.probe()
        number = 1 + sum(
            1 for entry in entries if isinstance(entry, dict) and entry.get("client") == args.client
        )
        probe_id = "probe-%02d" % number
        record_probe(
            raw_root,
            args.client,
            probe_id,
            _probe_artifacts(adapter, probe),
            Path(tempfile.gettempdir()) / "eval-harness-controller-quarantine",
        )
    except (
        OSError,
        ValueError,
        PotentialSecretError,
        AttributeError,
        json.JSONDecodeError,
        RecursionError,
    ):
        return 1
    try:
        entries.append(
            {"client": args.client, "probe_id": probe_id, "probe": _probe_payload(probe)}
        )
        _write_derived(
            probes_path, json.dumps({"probes": entries}, sort_keys=True, indent=2) + "\n"
        )
        return 0 if _refresh_manifest(output_root) else 1
    except (OSError, ValueError):
        return 1


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run a probe or batch without equating a completed batch with a verified skill."""
    args = build_parser().parse_args(None if argv is None else tuple(argv))
    adapter = create_adapter(args)
    if args.probe_only:
        return run_probe(args, adapter)
    return run_batch(args, adapter)


if __name__ == "__main__":
    raise SystemExit(main())
