"""Unauthenticated structural inspection for the Claude Code CLI."""

import json
import tempfile
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple

from .base import ClientAdapter
from ..evidence import PotentialSecretError, record_run
from ..models import ClientProbe, CommandResult, RunRequest, RunResult, RunStatus
from ..process import run_command


_ENVIRONMENT_LABEL = "Claude Code structural inspection"
_COMMAND_NAMES = (
    "version",
    "doctor",
    "plugin-validate",
    "marketplace-list",
    "plugin-list",
)


class ClaudeAdapter(ClientAdapter):
    """Inspect Claude Code structure without attempting a model request."""

    def __init__(
        self,
        executable: str,
        cwd: Optional[Path] = None,
        timeout_seconds: float = 30.0,
        doctor_timeout_seconds: float = 5.0,
        quarantine_root: Optional[Path] = None,
    ) -> None:
        if doctor_timeout_seconds < 0:
            raise ValueError("doctor_timeout_seconds must not be negative")
        self.executable = executable
        self.cwd = Path.cwd() if cwd is None else Path(cwd)
        self.timeout_seconds = timeout_seconds
        self.doctor_timeout_seconds = doctor_timeout_seconds
        self.quarantine_root = (
            Path(tempfile.gettempdir()) / "claude-eval-quarantine"
            if quarantine_root is None
            else Path(quarantine_root)
        )
        self.structural_results: Tuple[CommandResult, ...] = ()

    def structural_commands(self, root: Path) -> Tuple[Tuple[str, ...], ...]:
        """Return the complete, non-interactive structural command inventory."""
        Path(root)
        return (
            (self.executable, "--version"),
            (self.executable, "doctor"),
            (self.executable, "plugin", "validate", "."),
            (self.executable, "plugin", "marketplace", "list"),
            (self.executable, "plugin", "list", "--json"),
        )

    def probe(self) -> ClientProbe:
        """Record each permitted structural observation independently."""
        probe, _ = self._probe_with_commands()
        return probe

    def prepare(self) -> ClientProbe:
        """Re-run structural inspection without changing the installed client."""
        return self.probe()

    def execute(self, request: RunRequest) -> RunResult:
        """Preserve structural evidence but never start Claude model behavior."""
        probe, commands = self._probe_with_commands()
        artifacts = self._probe_artifacts(commands)
        artifacts["metadata.json"] = self._metadata_json(probe, commands, request)
        status = RunStatus.BLOCKED
        reason = "paid authentication unavailable"
        try:
            record_run(
                request.output_root,
                request.client,
                request.case.id,
                request.repetition,
                artifacts,
                self.quarantine_root,
            )
        except PotentialSecretError:
            reason = "potential secret exposure"
        except (OSError, ValueError) as error:
            status = RunStatus.INVALID_EVIDENCE
            reason = "evidence recording failed: %s" % error
        return RunResult(
            case_id=request.case.id,
            repetition=request.repetition,
            client=request.client,
            status=status,
            reason=reason,
            command=None,
            final_output=None,
            session_id=None,
            metadata=(
                ("environment", _ENVIRONMENT_LABEL),
                ("enabled_plugins", ",".join(probe.enabled_plugins)),
            ),
        )

    def _probe_with_commands(self) -> tuple[ClientProbe, Tuple[CommandResult, ...]]:
        commands = self.structural_commands(self.cwd)
        results = []
        for index, command in enumerate(commands):
            timeout = self.doctor_timeout_seconds if index == 1 else self.timeout_seconds
            try:
                results.append(run_command(command, self.cwd, timeout))
            except OSError:
                break
        self.structural_results = tuple(results)

        version = self._result_at(results, 0)
        plugin_list = self._result_at(results, 4)
        enabled = self._enabled_plugins(plugin_list.stdout) if plugin_list is not None else ()
        version_text = version.stdout.strip() if version is not None else None
        available = bool(
            version is not None and not version.timed_out and version.returncode == 0
        )
        capabilities = ["structural-probes"]
        for name, result in zip(_COMMAND_NAMES, results):
            capabilities.append(name if self._succeeded(result) else "%s-blocked" % name)
        reason = None if available else self._unavailable_reason(version)
        return (
            ClientProbe(
                client="claude",
                available=available,
                version=version_text or None,
                authenticated=None,
                plugin_version=None,
                enabled_plugins=enabled,
                capabilities=tuple(capabilities),
                reason=reason,
            ),
            self.structural_results,
        )

    @staticmethod
    def _result_at(results: Sequence[CommandResult], index: int) -> Optional[CommandResult]:
        return results[index] if len(results) > index else None

    @staticmethod
    def _succeeded(result: CommandResult) -> bool:
        return not result.timed_out and result.returncode == 0

    @staticmethod
    def _unavailable_reason(version: Optional[CommandResult]) -> str:
        if version is None:
            return "claude --version unavailable"
        if version.timed_out:
            return "claude --version timed out"
        return "claude --version returned nonzero exit"

    @staticmethod
    def _enabled_plugins(payload: str) -> Tuple[str, ...]:
        try:
            decoded: Any = json.loads(payload)
        except json.JSONDecodeError:
            return ()
        if isinstance(decoded, dict):
            decoded = decoded.get("plugins", decoded.get("installed", ()))
        if not isinstance(decoded, list):
            return ()
        enabled = []
        for item in decoded:
            if not isinstance(item, dict) or item.get("enabled") is not True:
                continue
            value = item.get("pluginId") or item.get("id") or item.get("name")
            if value is not None:
                enabled.append(str(value))
        return tuple(enabled)

    @staticmethod
    def _probe_artifacts(commands: Sequence[CommandResult]) -> dict[str, str]:
        artifacts = {}
        for name, command in zip(_COMMAND_NAMES, commands):
            artifacts["%s.stdout.txt" % name] = command.stdout
            artifacts["%s.stderr.txt" % name] = command.stderr
        return artifacts

    @staticmethod
    def _metadata_json(
        probe: ClientProbe, commands: Sequence[CommandResult], request: RunRequest
    ) -> str:
        command_rows = []
        for name, command in zip(_COMMAND_NAMES, commands):
            command_rows.append(
                {
                    "name": name,
                    "argv": list(command.argv),
                    "returncode": command.returncode,
                    "elapsed_seconds": command.elapsed_seconds,
                    "timed_out": command.timed_out,
                }
            )
        return json.dumps(
            {
                "client": "claude",
                "environment": _ENVIRONMENT_LABEL,
                "version": probe.version,
                "enabled_plugins": list(probe.enabled_plugins),
                "model": request.model,
                "reasoning": request.reasoning,
                "probe_commands": command_rows,
                "behavior": "blocked",
                "reason": "paid authentication unavailable",
            },
            sort_keys=True,
        )
