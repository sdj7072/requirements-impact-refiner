"""Installed Codex composition adapter for deterministic evaluation runs."""

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple

from .base import ClientAdapter
from ..controller_evidence import analyze_controller_trace
from ..evidence import Artifact, PotentialSecretError, record_run
from ..models import CaseTurn, ClientProbe, CommandResult, RunRequest, RunResult, RunStatus
from ..process import run_command


_UUID = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)
_COMPOSITION_LABEL = "Codex with Superpowers"
_CANONICAL_RIR_PLUGIN_ID = (
    "requirements-impact-refiner@requirements-impact-refiner"
)
_SUPERPOWERS_PLUGIN_ID = "superpowers@openai-curated"
_PREDECESSOR_HANDOFF = (
    "Harness continuity evidence:\n"
    "- In compact delivery, read `.requirements-impact-refiner/reports/RPT-###/current.json` and hash the exact canonical Markdown file it selects.\n"
    "- `first.final.txt` is the chat response, not canonical lineage bytes, unless no persisted report exists and it is itself a complete canonical report.\n"
    "- Do not reconstruct predecessor bytes from conversation text or add, remove, or normalize bytes."
)


class CodexAdapter(ClientAdapter):
    """Run evaluation cases against the installed Codex plugin composition."""

    def __init__(
        self,
        executable: str = "codex",
        cwd: Optional[Path] = None,
        timeout_seconds: float = 300.0,
        quarantine_root: Optional[Path] = None,
        expected_plugin_version: str = "0.3.0",
        expected_rir_plugin_id: str = _CANONICAL_RIR_PLUGIN_ID,
    ) -> None:
        self.executable = executable
        self.cwd = Path.cwd() if cwd is None else Path(cwd)
        self.timeout_seconds = timeout_seconds
        self.expected_plugin_version = expected_plugin_version
        self.expected_rir_plugin_id = expected_rir_plugin_id
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
                "--skip-git-repo-check",
                "-s",
                "workspace-write",
                "-o",
                str(final_path),
            )
        )
        self._append_run_options(command, request)
        command.append(self._turn_prompt(request.case.turns[0].prompt, request.case.turns[0].repository_evidence))
        return tuple(command)

    def build_resume_command(
        self,
        request: RunRequest,
        thread_id: str,
        turn: CaseTurn,
        final_path: Path,
        rendered_prompt: Optional[str] = None,
    ) -> Tuple[str, ...]:
        """Resume the exact session emitted by the supplied persisted turn."""
        if not isinstance(thread_id, str) or not _UUID.fullmatch(thread_id):
            raise ValueError("thread_id must be a parsed UUID")
        if not isinstance(turn, CaseTurn):
            raise TypeError("turn must be a CaseTurn")
        if rendered_prompt is not None and not isinstance(rendered_prompt, str):
            raise TypeError("rendered_prompt must be a string")
        return (
            self.executable,
            "exec",
            "resume",
            "--json",
            "--skip-git-repo-check",
            "-o",
            str(final_path),
            thread_id,
            self._resume_prompt(turn) if rendered_prompt is None else rendered_prompt,
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
        artifacts: dict[str, Artifact] = {
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
                None,
            )

        with tempfile.TemporaryDirectory(prefix="codex-eval-") as temporary:
            temporary_root = Path(temporary)
            first_final = temporary_root / "first.final.txt"
            first_prompt = self._turn_prompt(
                request.case.turns[0].prompt, request.case.turns[0].repository_evidence
            )
            first_command = run_command(
                self.build_first_turn_command(request, first_final),
                temporary_root,
                self.timeout_seconds,
            )
            artifacts.update(self._turn_artifacts("first", first_prompt, first_command, first_final))
            capture_problem = self._capture_workspace_reports(artifacts, temporary_root)
            if capture_problem is not None:
                return self._record_result(
                    request, artifacts, RunStatus.INFRA_ERROR, capture_problem,
                    first_command, None, None, probe, first_command,
                )
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
                    first_command,
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
                    first_command,
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
                    first_command,
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
                    first_command,
                )

            second_turn = request.case.turns[1]
            second_final = temporary_root / "second.final.txt"
            second_prompt = self._resume_prompt(second_turn)
            second_command = run_command(
                self.build_resume_command(
                    request,
                    thread_id,
                    second_turn,
                    second_final,
                    rendered_prompt=second_prompt,
                ),
                temporary_root,
                self.timeout_seconds,
            )
            artifacts.update(self._turn_artifacts("second", second_prompt, second_command, second_final))
            capture_problem = self._capture_workspace_reports(artifacts, temporary_root)
            if capture_problem is not None:
                return self._record_result(
                    request, artifacts, RunStatus.INFRA_ERROR, capture_problem,
                    second_command, None, thread_id, probe, first_command,
                )
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
                    first_command,
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
                first_command,
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
        observed_plugin_version = self._plugin_version(rir) if rir is not None else None
        if (
            rir is None
            or rir.get("enabled") is not True
            or observed_plugin_version != self.expected_plugin_version
        ):
            return self._unavailable_probe(
                "enabled Requirements Impact Refiner %s is required (observed: %s)" % (
                    self.expected_plugin_version, observed_plugin_version or "none",
                ),
                version.stdout,
                enabled,
                observed_plugin_version,
            ), commands
        if superpowers is None or superpowers.get("enabled") is not True:
            return self._unavailable_probe("enabled Superpowers is required", version.stdout, enabled), commands
        return (
            ClientProbe(
                client="codex",
                available=True,
                version=version.stdout.strip() or None,
                authenticated=None,
                plugin_version=observed_plugin_version,
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
        value = entry.get("pluginId") or entry.get("id")
        return value if isinstance(value, str) else ""

    @staticmethod
    def _plugin_version(entry: dict[str, Any]) -> Optional[str]:
        value = entry.get("version")
        if value is None and isinstance(entry.get("manifest"), dict):
            value = entry["manifest"].get("version")
        return str(value) if value is not None else None

    def _is_rir(self, entry: dict[str, Any]) -> bool:
        return self._plugin_id(entry) == self.expected_rir_plugin_id

    def _is_superpowers(self, entry: dict[str, Any]) -> bool:
        return self._plugin_id(entry) == _SUPERPOWERS_PLUGIN_ID

    @staticmethod
    def _turn_prompt(prompt: str, repository_evidence: Sequence[str]) -> str:
        return "%s\n\nRepository evidence:\n%s" % (
            prompt,
            "\n".join("- %s" % item for item in repository_evidence),
        )

    @classmethod
    def _resume_prompt(cls, turn: CaseTurn) -> str:
        """Append environment continuity evidence without changing the case contract."""
        return "%s\n\n%s" % (
            cls._turn_prompt(turn.prompt, turn.repository_evidence),
            _PREDECESSOR_HANDOFF,
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

    @staticmethod
    def _workspace_report_artifacts(workspace_root: Path) -> dict[str, bytes]:
        report_root = workspace_root / ".requirements-impact-refiner" / "reports"
        if not report_root.exists():
            return {}
        if report_root.is_symlink() or not report_root.is_dir():
            raise ValueError("workspace report root must be a real directory")
        artifacts: dict[str, bytes] = {}
        for path in sorted(report_root.rglob("*")):
            if path.is_symlink():
                raise ValueError("workspace report artifacts must not use symlinks")
            if not path.is_file():
                continue
            relative = path.relative_to(report_root)
            if any(part in {"", ".", ".."} for part in relative.parts):
                raise ValueError("workspace report artifact path is unsafe")
            artifacts[(Path("workspace-reports") / relative).as_posix()] = path.read_bytes()
        return artifacts

    @classmethod
    def _capture_workspace_reports(
        cls, artifacts: dict[str, Artifact], workspace_root: Path
    ) -> Optional[str]:
        try:
            artifacts.update(cls._workspace_report_artifacts(workspace_root))
        except (OSError, ValueError) as error:
            return f"workspace report capture failed: {error}"
        return None

    def _record_result(
        self,
        request: RunRequest,
        artifacts: dict[str, Artifact],
        status: RunStatus,
        reason: Optional[str],
        command: Optional[CommandResult],
        final_output: Optional[str],
        session_id: Optional[str],
        probe: ClientProbe,
        provenance_command: Optional[CommandResult],
    ) -> RunResult:
        options_valid, observed_model, observed_reasoning = self._argv_run_options(
            provenance_command.argv if provenance_command is not None else ()
        )
        if provenance_command is not None and (
            not options_valid
            or observed_model != request.model
            or observed_reasoning != request.reasoning
        ):
            status = RunStatus.INVALID_EVIDENCE
            reason = "run options disagree with execution argv"
            final_output = None
        if self.expected_plugin_version.startswith("0.4.") and final_output is not None:
            streams = tuple(
                value
                for name, value in sorted(artifacts.items())
                if name in ("first.jsonl", "second.jsonl") and isinstance(value, str)
            )
            expected_turns = 0 if request.case.kind == "negative" else len(request.case.turns)
            turn_outputs = tuple(
                value
                for name, value in sorted(artifacts.items())
                if name in ("first.final.txt", "second.final.txt")
                and isinstance(value, str)
            )
            controller = analyze_controller_trace(
                streams,
                turn_outputs if expected_turns else final_output,
                expected_turns=expected_turns,
            )
            artifacts["controller-evidence.json"] = controller.to_json()
            if not controller.valid:
                status = RunStatus.INVALID_EVIDENCE
                reason = "controller evidence invalid"
                final_output = None
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
        plugins = tuple(sorted(probe.enabled_plugins))
        client_version = probe.version or ""
        model = observed_model if provenance_command is not None else request.model
        reasoning = (
            observed_reasoning if provenance_command is not None else request.reasoning
        )
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
                ("client_version", client_version),
                ("plugin_version", probe.plugin_version or ""),
                (
                    "enabled_composition",
                    "codex %s plugins=%s"
                    % (client_version or "unavailable", ",".join(plugins) or "none"),
                ),
                ("enabled_plugins", ",".join(plugins)),
                ("model", model or "omitted"),
                ("reasoning", reasoning or "omitted"),
            ),
            attempt=request.attempt,
            retry_of=request.retry_of,
        )

    @staticmethod
    def _argv_run_options(
        argv: Sequence[str],
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Derive the selected model and reasoning from the executed first turn."""
        models = []
        reasonings = []
        for index, argument in enumerate(argv):
            if argument == "-m":
                if index + 1 >= len(argv):
                    return False, None, None
                models.append(argv[index + 1])
            if argument != "-c" or index + 1 >= len(argv):
                continue
            configuration = argv[index + 1]
            prefix = "model_reasoning_effort="
            if not configuration.startswith(prefix):
                continue
            try:
                value = json.loads(configuration[len(prefix) :])
            except json.JSONDecodeError:
                return False, None, None
            if not isinstance(value, str):
                return False, None, None
            reasonings.append(value)
        if len(models) > 1 or len(reasonings) > 1:
            return False, None, None
        return (
            True,
            models[0] if models else None,
            reasonings[0] if reasonings else None,
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
        reason: str,
        version: Optional[str] = None,
        enabled: Tuple[str, ...] = (),
        plugin_version: Optional[str] = None,
    ) -> ClientProbe:
        return ClientProbe(
            client="codex",
            available=False,
            version=version.strip() if version else None,
            authenticated=None,
            plugin_version=plugin_version,
            enabled_plugins=enabled,
            capabilities=(),
            reason=reason,
        )
