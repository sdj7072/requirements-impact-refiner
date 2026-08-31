"""Immutable value types shared by evaluation harness components."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class RunStatus(str, Enum):
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"
    BLOCKED = "blocked"
    INFRA_ERROR = "infra_error"
    INVALID_EVIDENCE = "invalid_evidence"


@dataclass(frozen=True)
class CaseTurn:
    prompt: str
    repository_evidence: tuple[str, ...]


@dataclass(frozen=True)
class CaseSpec:
    id: str
    kind: str
    turns: tuple[CaseTurn, ...]
    must_detect: tuple[str, ...]
    must_not_do: tuple[str, ...]
    modes: tuple[str, ...]
    expected_transition: Optional[str] = None
    fixture_files: tuple[tuple[str, str], ...] = ()
    followup_fixture_files: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RunRequest:
    case: CaseSpec
    repetition: int
    client: str
    model: Optional[str]
    reasoning: Optional[str]
    output_root: Path
    attempt: int = 1
    retry_of: Optional[str] = None


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: Optional[int]
    stdout: str
    stderr: str
    elapsed_seconds: float
    timed_out: bool


@dataclass(frozen=True)
class ClientProbe:
    client: str
    available: bool
    version: Optional[str]
    authenticated: Optional[bool]
    plugin_version: Optional[str]
    enabled_plugins: tuple[str, ...]
    capabilities: tuple[str, ...]
    reason: Optional[str] = None


@dataclass(frozen=True)
class RunResult:
    case_id: str
    repetition: int
    client: str
    status: RunStatus
    reason: Optional[str]
    command: Optional[CommandResult] = None
    final_output: Optional[str] = None
    session_id: Optional[str] = None
    metadata: tuple[tuple[str, str], ...] = ()
    attempt: int = 1
    retry_of: Optional[str] = None


@dataclass(frozen=True)
class MechanicalScore:
    case_id: str
    repetition: int
    passed: bool
    findings: tuple[str, ...]


@dataclass(frozen=True)
class Adjudication:
    case_id: str
    repetition: int
    rubric: str
    passed: bool
    quote: str
    rationale: str
