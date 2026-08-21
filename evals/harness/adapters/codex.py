"""Installed Codex composition adapter for deterministic evaluation runs."""

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple

from .base import ClientAdapter
from ..evidence import PotentialSecretError, record_run
from ..models import CaseTurn, ClientProbe, CommandResult, RunRequest, RunResult, RunStatus
from ..process import run_command


_UUID = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)
_COMPOSITION_LABEL = "Codex with Superpowers"


class CodexAdapter(ClientAdapter):
    """Run evaluation cases against the installed Codex plugin composition."""

    def __init__(
        self,
        executable: str = "codex",
        cwd: Optional[Path] = None,
        timeout_seconds: float = 300.0,
        quarantine_root: Optional[Path] = None,
    ) -> None:
        self.executable = executable
        self.cwd = Path.cwd() if cwd is None else Path(cwd)
        self.timeout_seconds = timeout_seconds
        self.quarantine_root = (
            Path(tempfile.gettempdir()) / "codex-eval-quarantine"
            if quarantine_root is None
            else Path(quarantine_root)
        )
        self.probe_results: Tuple[CommandResult, ...] = ()

    def probe(self) -> ClientProbe:
        """Inspect the installed CLI and enabled plugin inventory without mutation."""
        probe, commands = self._probe_with_commands()
        self.probe_results = commands
        return probe

    def prepare(self) -> ClientProbe:
        """Require the intended installed composition without changing it."""
        return self.probe()

    def build_first_turn_command(
        self, request: RunRequest, final_path: Path
    ) -> Tuple[str, ...]:
        """Build a fresh Codex command, persisted only for multi-turn cases."""
        command = [self.executable, "exec"]
        if len(request.case.turns) == 1:
            command.append("--ephemeral")
        command.extend(
            (
                "--json",
                "-s",
                "read-only",
                "--approve-for-me",
                "-o",
                str(final_path),
            )
        )
        self._append_run_options(command, request)
        command.append(self._turn_prompt(request.case.turns[0].prompt, request.case.turns[0].repository_evidence))
        return tuple(command)

    def build_resume_command(
        self, request: RunRequest, thread_id: str, turn: CaseTurn, final_path: Path
    ) -> Tuple[str, ...]:
        """Resume the exact session emitted by the supplied persisted turn."""
        if not isinstance(thread_id, str) or not _UUID.fullmatch(thread_id):
            raise ValueError("thread_id must be a parsed UUID")
        if not isinstance(turn, CaseTurn):
            raise TypeError("turn must be a CaseTurn")
        prompt = turn.prompt
        evidence = turn.repository_evidence
        return (
            self.executable,
            "exec",
            "resume",
            "--json",
            "-o",
            str(final_path),
            thread_id,
            self._turn_prompt(prompt, evidence),
        )

    def parse_thread_id(self, jsonl: str) -> Optional[str]:
        """Return the canonical ID only from a valid ``thread.started`` event."""
        events = self._parse_jsonl(jsonl)
        if events is None:
            return None
        for event in events:
            if event.get("type") != "thread.started":
                continue
            thread_id = event.get("thread_id")
            if isinstance(thread_id, str) and _UUID.fullmatch(thread_id):
                return thread_id
        return None

    def execute(self, request: RunRequest) -> RunResult:
        """Execute one request and preserve successful and infrastructure attempts."""
        probe, probe_commands = self._probe_with_commands()
        self.probe_results = probe_commands
        artifacts: dict[str, str] = {
            "metadata.json": self._metadata_json(probe, probe_commands, (), request),
        }
        if not probe.available:
            return self._record_result(
                request,
                artifacts,
                RunStatus.INFRA_ERROR,
                probe.reason or "Codex composition unavailable",
                None,
                None,
                None,
                probe,
            )

        with tempfile.TemporaryDirectory(prefix="codex-eval-") as temporary:
            temporary_root = Path(temporary)
            first_final = temporary_root / "first.final.txt"
            first_prompt = self._turn_prompt(
                request.case.turns[0].prompt, request.case.turns[0].repository_evidence
            )
            first_command = run_command(
                self.build_first_turn_command(request, first_final),
                self.cwd,
                self.timeout_seconds,
            )
            artifacts.update(self._turn_artifacts("first", first_prompt, first_command, first_final))
            problem, first_output = self._command_problem(first_command, first_final)
            commands = (first_command,)
            artifacts["metadata.json"] = self._metadata_json(probe, probe_commands, commands, request)
            if problem is not None:
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.INFRA_ERROR,
                    problem,
                    first_command,
                    None,
                    None,
                    probe,
                )

            if len(request.case.turns) == 1:
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.PASS,
                    None,
                    first_command,
                    first_output,
                    None,
                    probe,
                )

            thread_id = self.parse_thread_id(first_command.stdout)
            if thread_id is None:
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.INFRA_ERROR,
                    "missing thread.started UUID",
                    first_command,
                    None,
                    None,
                    probe,
                )

            if len(request.case.turns) != 2:
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.INFRA_ERROR,
                    "unsupported multi-turn case length",
                    first_command,
                    None,
                    thread_id,
                    probe,
                )

            second_turn = request.case.turns[1]
            second_final = temporary_root / "second.final.txt"
            second_prompt = self._turn_prompt(second_turn.prompt, second_turn.repository_evidence)
            second_command = run_command(
                self.build_resume_command(request, thread_id, second_turn, second_final),
                self.cwd,
                self.timeout_seconds,
            )
            artifacts.update(self._turn_artifacts("second", second_prompt, second_command, second_final))
            commands = (first_command, second_command)
            artifacts["metadata.json"] = self._metadata_json(probe, probe_commands, commands, request)
            problem, second_output = self._command_problem(second_command, second_final)
            if problem is not None:
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.INFRA_ERROR,
                    problem,
                    second_command,
                    None,
                    thread_id,
                    probe,
                )
            return self._record_result(
                request,
                artifacts,
                RunStatus.PASS,
                None,
                second_command,
                second_output,
                thread_id,
                probe,
            )

    def _probe_with_commands(self) -> tuple[ClientProbe, Tuple[CommandResult, ...]]:
        try:
            version = run_command(
                (self.executable, "--version"), self.cwd, self.timeout_seconds
            )
        except OSError as error:
            return self._unavailable_probe(str(error)), ()
        if version.timed_out:
            return self._unavailable_probe("codex --version timed out"), (version,)
        if version.returncode != 0:
            return self._unavailable_probe("codex --version returned nonzero exit"), (version,)

        try:
            plugins = run_command(
                (self.executable, "plugin", "list", "--json"), self.cwd, self.timeout_seconds
            )
        except OSError as error:
            return self._unavailable_probe(str(error)), (version,)
        commands = (version, plugins)
        if plugins.timed_out:
            return self._unavailable_probe("codex plugin list timed out", version.stdout), commands
        if plugins.returncode != 0:
            return self._unavailable_probe("codex plugin list returned nonzero exit", version.stdout), commands

        entries = self._plugin_entries(plugins.stdout)
        if entries is None:
            return self._unavailable_probe("codex plugin list returned malformed JSON", version.stdout), commands
        enabled = tuple(self._plugin_id(entry) for entry in entries if entry.get("enabled") is True)
        rir = next((entry for entry in entries if self._is_rir(entry)), None)
        superpowers = next((entry for entry in entries if self._is_superpowers(entry)), None)
        if rir is None or rir.get("enabled") is not True or self._plugin_version(rir) != "0.3.0":
            return self._unavailable_probe(
                "enabled Requirements Impact Refiner 0.3.0 is required", version.stdout, enabled
            ), commands
        if superpowers is None or superpowers.get("enabled") is not True:
            return self._unavailable_probe("enabled Superpowers is required", version.stdout, enabled), commands
        return (
            ClientProbe(
                client="codex",
                available=True,
                version=version.stdout.strip() or None,
                authenticated=None,
                plugin_version="0.3.0",
                enabled_plugins=enabled,
                capabilities=(
                    _COMPOSITION_LABEL,
                    "jsonl",
                    "ephemeral",
                    "explicit-uuid-resume",
                ),
                reason=None,
            ),
            commands,
        )

    @staticmethod
    def _plugin_entries(payload: str) -> Optional[Tuple[dict[str, Any], ...]]:
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if isinstance(decoded, dict):
            decoded = decoded.get("installed", decoded.get("plugins"))
        if not isinstance(decoded, list):
            return None
        entries = []
        for item in decoded:
            if not isinstance(item, dict):
                return None
            entry = item.get("plugin") if isinstance(item.get("plugin"), dict) else item
            entries.append(entry)
        return tuple(entries)

    @staticmethod
    def _plugin_id(entry: dict[str, Any]) -> str:
        value = entry.get("pluginId") or entry.get("id") or entry.get("name")
        return str(value)

    @staticmethod
    def _plugin_version(entry: dict[str, Any]) -> Optional[str]:
        value = entry.get("version")
        if value is None and isinstance(entry.get("manifest"), dict):
            value = entry["manifest"].get("version")
        return str(value) if value is not None else None

    @staticmethod
    def _plugin_name(entry: dict[str, Any]) -> str:
        value = entry.get("name") or entry.get("pluginId") or entry.get("id") or ""
        return str(value).strip().lower().replace("_", "-")

    def _is_rir(self, entry: dict[str, Any]) -> bool:
        return self._plugin_name(entry) in {
            "requirements impact refiner",
            "requirements-impact-refiner",
        }

    def _is_superpowers(self, entry: dict[str, Any]) -> bool:
        return self._plugin_name(entry) == "superpowers"

    @staticmethod
    def _turn_prompt(prompt: str, repository_evidence: Sequence[str]) -> str:
        return "%s\n\nRepository evidence:\n%s" % (
            prompt,
            "\n".join("- %s" % item for item in repository_evidence),
        )

    @staticmethod
    def _append_run_options(command: list[str], request: RunRequest) -> None:
        if request.model is not None:
            command.extend(("-m", request.model))
        if request.reasoning is not None:
            command.extend(("-c", 'model_reasoning_effort="%s"' % request.reasoning))

    @staticmethod
    def _parse_jsonl(text: str) -> Optional[Tuple[dict[str, Any], ...]]:
        if not text.strip():
            return None
        events = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                return None
            if not isinstance(event, dict):
                return None
            events.append(event)
        return tuple(events) if events else None

    def _command_problem(
        self, command: CommandResult, final_path: Path
    ) -> tuple[Optional[str], Optional[str]]:
        if command.timed_out:
            return "timeout", None
        if command.returncode != 0:
            return "nonzero exit", None
        if self._parse_jsonl(command.stdout) is None:
            return "malformed JSONL", None
        if not final_path.is_file():
            return "missing final output", None
        final_output = final_path.read_text(encoding="utf-8", errors="replace")
        if not final_output:
            return "missing final output", None
        return None, final_output

    @staticmethod
    def _turn_artifacts(
        name: str, prompt: str, command: CommandResult, final_path: Path
    ) -> dict[str, str]:
        final_output = ""
        if final_path.is_file():
            final_output = final_path.read_text(encoding="utf-8", errors="replace")
        return {
            "%s.prompt.txt" % name: prompt,
            "%s.jsonl" % name: command.stdout,
            "%s.stderr.txt" % name: command.stderr,
            "%s.final.txt" % name: final_output,
        }

    def _record_result(
        self,
        request: RunRequest,
        artifacts: dict[str, str],
        status: RunStatus,
        reason: Optional[str],
        command: Optional[CommandResult],
        final_output: Optional[str],
        session_id: Optional[str],
        probe: ClientProbe,
    ) -> RunResult:
        try:
            record_run(
                request.output_root,
                request.client,
                request.case.id,
                request.repetition,
                artifacts,
                self.quarantine_root,
                attempt=request.attempt,
            )
        except PotentialSecretError:
            status = RunStatus.BLOCKED
            reason = "potential secret exposure"
            final_output = None
        except (OSError, ValueError) as error:
            status = RunStatus.INFRA_ERROR
            reason = "evidence recording failed: %s" % error
            final_output = None
        return RunResult(
            case_id=request.case.id,
            repetition=request.repetition,
            client=request.client,
            status=status,
            reason=reason,
            command=command,
            final_output=final_output,
            session_id=session_id,
            metadata=(
                ("environment", _COMPOSITION_LABEL),
                ("plugin_version", probe.plugin_version or ""),
                ("enabled_plugins", ",".join(probe.enabled_plugins)),
            ),
            attempt=request.attempt,
            retry_of=request.retry_of,
        )

    @staticmethod
    def _metadata_json(
        probe: ClientProbe,
        probe_commands: Sequence[CommandResult],
        commands: Sequence[CommandResult],
        request: RunRequest,
    ) -> str:
        def command_payload(command: CommandResult) -> dict[str, Any]:
            return {
                "argv": list(command.argv),
                "returncode": command.returncode,
                "elapsed_seconds": command.elapsed_seconds,
                "timed_out": command.timed_out,
            }

        return json.dumps(
            {
                "client": "codex",
                "environment": _COMPOSITION_LABEL,
                "version": probe.version,
                "plugin_version": probe.plugin_version,
                "enabled_plugins": list(probe.enabled_plugins),
                "model": request.model,
                "reasoning": request.reasoning,
                "attempt": request.attempt,
                "retry_of": request.retry_of,
                "probe_commands": [command_payload(command) for command in probe_commands],
                "execution_commands": [command_payload(command) for command in commands],
            },
            sort_keys=True,
        )

    @staticmethod
    def _unavailable_probe(
        reason: str, version: Optional[str] = None, enabled: Tuple[str, ...] = ()
    ) -> ClientProbe:
        return ClientProbe(
            client="codex",
            available=False,
            version=version.strip() if version else None,
            authenticated=None,
            plugin_version=None,
            enabled_plugins=enabled,
            capabilities=(),
            reason=reason,
        )
