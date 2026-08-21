"""Immutable value types shared by evaluation harness components."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple


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
    repository_evidence: Tuple[str, ...]


@dataclass(frozen=True)
class CaseSpec:
    id: str
    kind: str
    turns: Tuple[CaseTurn, ...]
    must_detect: Tuple[str, ...]
    must_not_do: Tuple[str, ...]
    modes: Tuple[str, ...]
    expected_transition: Optional[str] = None


@dataclass(frozen=True)
class RunRequest:
    case: CaseSpec
    repetition: int
    client: str
    model: Optional[str]
    reasoning: Optional[str]
    output_root: Path


@dataclass(frozen=True)
class CommandResult:
    argv: Tuple[str, ...]
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
    enabled_plugins: Tuple[str, ...]
    capabilities: Tuple[str, ...]
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
    metadata: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class MechanicalScore:
    case_id: str
    repetition: int
    passed: bool
    findings: Tuple[str, ...]


@dataclass(frozen=True)
class Adjudication:
    case_id: str
    repetition: int
    rubric: str
    passed: bool
    quote: str
    rationale: str
