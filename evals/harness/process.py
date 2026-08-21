"""Safe, deterministic subprocess execution for evaluation adapters."""

import subprocess
import time
from pathlib import Path
from typing import Sequence

from .models import CommandResult


def _decode_output(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def run_command(
    argv: Sequence[str], cwd: Path, timeout_seconds: float
) -> CommandResult:
    """Run an argv command without a shell and preserve timeout output."""
    command = tuple(str(argument) for argument in argv)
    if not command:
        raise ValueError("argv must contain a command")
    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must not be negative")

    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as error:
        return CommandResult(
            argv=command,
            returncode=None,
            stdout=_decode_output(error.stdout),
            stderr=_decode_output(error.stderr),
            elapsed_seconds=time.monotonic() - started,
            timed_out=True,
        )

    return CommandResult(
        argv=command,
        returncode=completed.returncode,
        stdout=_decode_output(completed.stdout),
        stderr=_decode_output(completed.stderr),
        elapsed_seconds=time.monotonic() - started,
        timed_out=False,
    )
