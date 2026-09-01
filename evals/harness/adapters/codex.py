"""Installed Codex composition adapter for deterministic evaluation runs."""

import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Optional

from ..catalog import (
    MAX_FIXTURE_CONTENT_BYTES,
    MAX_FIXTURE_FILES,
    MAX_FIXTURE_PATH_BYTES,
    MAX_FIXTURE_TOTAL_BYTES,
)
from ..controller_evidence import analyze_controller_trace, analyze_terminal_delivery
from ..evidence import Artifact, PotentialSecretError, record_run
from ..graph_scoring import graph_run_policy, load_graph_cases
from ..models import (
    CaseSpec,
    CaseTurn,
    ClientProbe,
    CommandResult,
    RunRequest,
    RunResult,
    RunStatus,
)
from ..process import run_command
from .base import ClientAdapter

_UUID = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)
_COMPOSITION_LABEL = "Codex with Superpowers"
_CANONICAL_RIR_PLUGIN_ID = "requirements-impact-refiner@requirements-impact-refiner"
_SUPERPOWERS_PLUGIN_ID = "superpowers@openai-curated"
_SEMANTIC_VERSION = re.compile(r"\A(\d+)\.(\d+)(?:\.|-|\Z)")
_MAX_GUARDED_ENTRIES = 2048
_MAX_GUARDED_FILE_BYTES = 8 * 1024 * 1024
_MAX_GUARDED_TOTAL_BYTES = 32 * 1024 * 1024
_MAX_CAPTURED_REPORT_FILES = 128
_MAX_CAPTURED_REPORT_FILE_BYTES = 4 * 1024 * 1024
_MAX_CAPTURED_REPORT_TOTAL_BYTES = 24 * 1024 * 1024
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
        self.probe_results: tuple[CommandResult, ...] = ()

    def probe(self) -> ClientProbe:
        """Inspect the installed CLI and enabled plugin inventory without mutation."""
        probe, commands = self._probe_with_commands()
        self.probe_results = commands
        return probe

    def prepare(self) -> ClientProbe:
        """Require the intended installed composition without changing it."""
        return self.probe()

    def build_first_turn_command(self, request: RunRequest, final_path: Path) -> tuple[str, ...]:
        """Build a fresh Codex command, persisted only for multi-turn cases."""
        command = [self.executable, "exec"]
        if len(request.case.turns) == 1:
            command.append("--ephemeral")
        command.extend(
            (
                "--json",
                "--skip-git-repo-check",
                "--approve-for-me",
                "-o",
                str(final_path),
            )
        )
        self._append_run_options(command, request)
        command.append(
            self._turn_prompt(
                request.case.turns[0].prompt, request.case.turns[0].repository_evidence
            )
        )
        return tuple(command)

    def build_resume_command(
        self,
        request: RunRequest,
        thread_id: str,
        turn: CaseTurn,
        final_path: Path,
        rendered_prompt: Optional[str] = None,
    ) -> tuple[str, ...]:
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
            try:
                self._stage_catalog_fixture(request.case, temporary_root)
                self._stage_graph_fixture(request.case.id, temporary_root)
            except (OSError, ValueError) as error:
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.INFRA_ERROR,
                    f"fixture staging failed: {error}",
                    None,
                    None,
                    None,
                    probe,
                    None,
                )
            integrity_checks: list[dict[str, object]] = []
            try:
                first_baseline = self._snapshot_guarded_workspace(temporary_root)
            except (OSError, ValueError) as error:
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.INFRA_ERROR,
                    f"workspace mutation check failed: {error}",
                    None,
                    None,
                    None,
                    probe,
                    None,
                )
            first_final = temporary_root / "first.final.txt"
            first_prompt = self._turn_prompt(
                request.case.turns[0].prompt, request.case.turns[0].repository_evidence
            )
            first_command = run_command(
                self.build_first_turn_command(request, first_final),
                temporary_root,
                self.timeout_seconds,
            )
            first_payload, first_read_problem = self._final_artifact(first_final)
            artifacts.update(
                self._turn_artifacts("first", first_prompt, first_command, first_payload)
            )
            commands: tuple[CommandResult, ...] = (first_command,)
            artifacts["metadata.json"] = self._metadata_json(
                probe, probe_commands, commands, request
            )
            capture_problem = self._capture_workspace_reports(artifacts, temporary_root)
            if capture_problem is None:
                capture_problem = self._capture_workspace_graph(artifacts, temporary_root)
            if capture_problem is not None:
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.INFRA_ERROR,
                    capture_problem,
                    first_command,
                    None,
                    None,
                    probe,
                    first_command,
                )
            try:
                first_integrity = self._workspace_integrity(
                    temporary_root, first_baseline, first_final
                )
            except (OSError, ValueError) as error:
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.INFRA_ERROR,
                    f"workspace mutation check failed: {error}",
                    first_command,
                    None,
                    None,
                    probe,
                    first_command,
                )
            integrity_checks.append(first_integrity)
            artifacts["workspace-integrity.json"] = self._workspace_integrity_artifact(
                integrity_checks
            )
            if first_integrity["status"] == "mutated":
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.INVALID_EVIDENCE,
                    "workspace mutation detected after first turn",
                    first_command,
                    None,
                    None,
                    probe,
                    first_command,
                )
            problem, first_output = self._command_problem(
                first_command, first_payload, first_read_problem
            )
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
            try:
                self._stage_followup_fixture(request.case, temporary_root)
            except (OSError, ValueError) as error:
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.INFRA_ERROR,
                    f"follow-up fixture staging failed: {error}",
                    first_command,
                    None,
                    thread_id,
                    probe,
                    first_command,
                )
            try:
                second_baseline = self._snapshot_guarded_workspace(temporary_root)
            except (OSError, ValueError) as error:
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.INFRA_ERROR,
                    f"workspace mutation check failed: {error}",
                    first_command,
                    None,
                    thread_id,
                    probe,
                    first_command,
                )
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
            second_payload, second_read_problem = self._final_artifact(second_final)
            artifacts.update(
                self._turn_artifacts("second", second_prompt, second_command, second_payload)
            )
            commands = (first_command, second_command)
            artifacts["metadata.json"] = self._metadata_json(
                probe, probe_commands, commands, request
            )
            capture_problem = self._capture_workspace_reports(artifacts, temporary_root)
            if capture_problem is None:
                capture_problem = self._capture_workspace_graph(artifacts, temporary_root)
            if capture_problem is not None:
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.INFRA_ERROR,
                    capture_problem,
                    second_command,
                    None,
                    thread_id,
                    probe,
                    first_command,
                )
            try:
                second_integrity = self._workspace_integrity(
                    temporary_root, second_baseline, second_final
                )
            except (OSError, ValueError) as error:
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.INFRA_ERROR,
                    f"workspace mutation check failed: {error}",
                    second_command,
                    None,
                    thread_id,
                    probe,
                    first_command,
                )
            integrity_checks.append(second_integrity)
            artifacts["workspace-integrity.json"] = self._workspace_integrity_artifact(
                integrity_checks
            )
            if second_integrity["status"] == "mutated":
                return self._record_result(
                    request,
                    artifacts,
                    RunStatus.INVALID_EVIDENCE,
                    "workspace mutation detected after second turn",
                    second_command,
                    None,
                    thread_id,
                    probe,
                    first_command,
                )
            problem, second_output = self._command_problem(
                second_command, second_payload, second_read_problem
            )
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

    def _probe_with_commands(self) -> tuple[ClientProbe, tuple[CommandResult, ...]]:
        try:
            version = run_command((self.executable, "--version"), self.cwd, self.timeout_seconds)
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
            return self._unavailable_probe(
                "codex plugin list returned nonzero exit", version.stdout
            ), commands

        entries = self._plugin_entries(plugins.stdout)
        if entries is None:
            return self._unavailable_probe(
                "codex plugin list returned malformed JSON", version.stdout
            ), commands
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
                "enabled Requirements Impact Refiner {} is required (observed: {})".format(
                    self.expected_plugin_version,
                    observed_plugin_version or "none",
                ),
                version.stdout,
                enabled,
                observed_plugin_version,
            ), commands
        if superpowers is None or superpowers.get("enabled") is not True:
            return self._unavailable_probe(
                "enabled Superpowers is required", version.stdout, enabled
            ), commands
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
    def _plugin_entries(payload: str) -> Optional[tuple[dict[str, object], ...]]:
        try:
            decoded = json.loads(payload)
        except (json.JSONDecodeError, RecursionError):
            return None
        if isinstance(decoded, dict):
            decoded = decoded.get("installed", decoded.get("plugins"))
        if not isinstance(decoded, list):
            return None
        entries: list[dict[str, object]] = []
        for item in decoded:
            if not isinstance(item, dict):
                return None
            entry = item
            plugin = item.get("plugin")
            if isinstance(plugin, dict):
                entry = plugin
            if any(not isinstance(key, str) for key in entry):
                return None
            entries.append({key: value for key, value in entry.items() if isinstance(key, str)})
        return tuple(entries)

    @staticmethod
    def _plugin_id(entry: dict[str, object]) -> str:
        value = entry.get("pluginId") or entry.get("id")
        return value if isinstance(value, str) else ""

    @staticmethod
    def _plugin_version(entry: dict[str, object]) -> Optional[str]:
        value = entry.get("version")
        manifest = entry.get("manifest")
        if value is None and isinstance(manifest, dict):
            value = manifest.get("version")
        return str(value) if value is not None else None

    def _is_rir(self, entry: dict[str, object]) -> bool:
        return self._plugin_id(entry) == self.expected_rir_plugin_id

    def _is_superpowers(self, entry: dict[str, object]) -> bool:
        return self._plugin_id(entry) == _SUPERPOWERS_PLUGIN_ID

    @staticmethod
    def _requires_terminal_delivery(version: str) -> bool:
        match = _SEMANTIC_VERSION.match(version)
        return match is not None and tuple(map(int, match.groups())) >= (0, 6)

    @staticmethod
    def _turn_prompt(prompt: str, repository_evidence: Sequence[str]) -> str:
        return "{}\n\nRepository evidence:\n{}".format(
            prompt,
            "\n".join(f"- {item}" for item in repository_evidence),
        )

    @classmethod
    def _resume_prompt(cls, turn: CaseTurn) -> str:
        """Append environment continuity evidence without changing the case contract."""
        return (
            f"{cls._turn_prompt(turn.prompt, turn.repository_evidence)}\n\n{_PREDECESSOR_HANDOFF}"
        )

    @staticmethod
    def _append_run_options(command: list[str], request: RunRequest) -> None:
        if request.model is not None:
            command.extend(("-m", request.model))
        if request.reasoning is not None:
            command.extend(("-c", f'model_reasoning_effort="{request.reasoning}"'))

    @staticmethod
    def _parse_jsonl(text: str) -> Optional[tuple[dict[str, object], ...]]:
        if not text.strip():
            return None
        events: list[dict[str, object]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, RecursionError):
                return None
            if not isinstance(event, dict):
                return None
            if any(not isinstance(key, str) for key in event):
                return None
            events.append({key: value for key, value in event.items() if isinstance(key, str)})
        return tuple(events) if events else None

    @staticmethod
    def _read_final_bytes(final_path: Path) -> bytes:
        path = Path(final_path)
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        directory_fd = None
        descriptor = None
        try:
            directory_fd = os.open(path.parent, directory_flags)
            descriptor = os.open(path.name, file_flags, dir_fd=directory_fd)
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("final output must be a regular non-symlink file")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
            if (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_size,
                before.st_mtime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise ValueError("final output changed while being read")
            return b"".join(chunks)
        except FileNotFoundError:
            raise
        except OSError as error:
            raise ValueError("final output must be a regular non-symlink file") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if directory_fd is not None:
                os.close(directory_fd)

    @classmethod
    def _final_artifact(cls, final_path: Path) -> tuple[bytes, Optional[str]]:
        try:
            payload = cls._read_final_bytes(final_path)
        except FileNotFoundError:
            return b"", "missing final output"
        except ValueError:
            return b"", "unsafe final output"
        try:
            payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return payload, "invalid UTF-8 final output"
        return payload, None

    @classmethod
    def _command_problem(
        cls,
        command: CommandResult,
        final_payload: bytes,
        read_problem: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        if command.timed_out:
            return "timeout", None
        if command.returncode != 0:
            return "nonzero exit", None
        if cls._parse_jsonl(command.stdout) is None:
            return "malformed JSONL", None
        if read_problem is not None:
            return read_problem, None
        final_output = final_payload.decode("utf-8", errors="strict")
        if not final_output:
            return "missing final output", None
        return None, final_output

    @staticmethod
    def _turn_artifacts(
        name: str, prompt: str, command: CommandResult, final_output: bytes
    ) -> dict[str, Artifact]:
        return {
            f"{name}.prompt.txt": prompt,
            f"{name}.jsonl": command.stdout,
            f"{name}.stderr.txt": command.stderr,
            f"{name}.final.txt": final_output,
        }

    @staticmethod
    def _snapshot_guarded_workspace(
        workspace_root: Path,
        expected: Optional[tuple[tuple[str, str, int, int, int, str], ...]] = None,
    ) -> tuple[tuple[str, str, int, int, int, str], ...]:
        """Fingerprint the isolated workspace without following any symlink."""
        root = Path(workspace_root)
        root_metadata = root.lstat()
        if root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
            raise ValueError("workspace mutation root must be a real directory")
        rows: list[tuple[str, str, int, int, int, str]] = []
        expected_map = {} if expected is None else {row[0]: row for row in expected}
        entry_count = 0
        total_bytes = 0
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)

        def same_identity(left: os.stat_result, right: os.stat_result) -> bool:
            return (left.st_dev, left.st_ino, left.st_mode) == (
                right.st_dev,
                right.st_ino,
                right.st_mode,
            )

        def visit(directory_fd: int, relative_parent: PurePosixPath) -> None:
            nonlocal entry_count, total_bytes
            try:
                with os.scandir(directory_fd) as iterator:
                    entries = sorted(iterator, key=lambda entry: entry.name)
            except OSError as error:
                raise ValueError("workspace mutation snapshot is unavailable") from error
            for entry in entries:
                entry_count += 1
                if entry_count > _MAX_GUARDED_ENTRIES:
                    raise ValueError("workspace mutation snapshot exceeds entry limit")
                relative = relative_parent / entry.name
                relative_text = relative.as_posix()
                try:
                    metadata = entry.stat(follow_symlinks=False)
                except OSError as error:
                    raise ValueError("workspace mutation entry is unavailable") from error
                if relative.parts[0] == ".requirements-impact-refiner":
                    if len(relative.parts) == 1 and (
                        entry.is_symlink() or not stat.S_ISDIR(metadata.st_mode)
                    ):
                        raise ValueError(
                            "workspace mutation reserved root must be a real directory"
                        )
                    continue
                permissions = stat.S_IMODE(metadata.st_mode)
                expected_row = expected_map.get(relative_text)
                if expected is not None and expected_row is None:
                    rows.append(
                        (
                            relative_text,
                            "unexpected",
                            permissions,
                            metadata.st_size,
                            metadata.st_ino,
                            "",
                        )
                    )
                    continue
                if stat.S_ISDIR(metadata.st_mode):
                    current_row = (
                        relative_text,
                        "directory",
                        permissions,
                        0,
                        metadata.st_ino,
                        "",
                    )
                    if expected_row is not None and current_row != expected_row:
                        rows.append(current_row)
                        continue
                    try:
                        child_fd = os.open(entry.name, directory_flags, dir_fd=directory_fd)
                    except OSError as error:
                        raise ValueError("workspace mutation directory is unavailable") from error
                    try:
                        opened = os.fstat(child_fd)
                        if not same_identity(metadata, opened):
                            raise ValueError("workspace mutation directory identity changed")
                        rows.append(current_row)
                        visit(child_fd, relative)
                    finally:
                        os.close(child_fd)
                elif stat.S_ISREG(metadata.st_mode):
                    current_prefix = (
                        relative_text,
                        "file",
                        permissions,
                        metadata.st_size,
                        metadata.st_ino,
                    )
                    if expected_row is not None and current_prefix != expected_row[:5]:
                        rows.append((*current_prefix, ""))
                        continue
                    if metadata.st_size > _MAX_GUARDED_FILE_BYTES:
                        raise ValueError("workspace mutation file exceeds byte limit")
                    total_bytes += metadata.st_size
                    if total_bytes > _MAX_GUARDED_TOTAL_BYTES:
                        raise ValueError("workspace mutation snapshot exceeds total byte limit")
                    try:
                        descriptor = os.open(entry.name, file_flags, dir_fd=directory_fd)
                    except OSError as error:
                        raise ValueError("workspace mutation file is unavailable") from error
                    digest = hashlib.sha256()
                    try:
                        before = os.fstat(descriptor)
                        if not same_identity(metadata, before):
                            raise ValueError("workspace mutation file identity changed")
                        while True:
                            chunk = os.read(descriptor, 64 * 1024)
                            if not chunk:
                                break
                            digest.update(chunk)
                        after = os.fstat(descriptor)
                    finally:
                        os.close(descriptor)
                    if (
                        before.st_dev,
                        before.st_ino,
                        before.st_mode,
                        before.st_size,
                        before.st_mtime_ns,
                    ) != (
                        after.st_dev,
                        after.st_ino,
                        after.st_mode,
                        after.st_size,
                        after.st_mtime_ns,
                    ):
                        raise ValueError("workspace mutation file changed while being read")
                    rows.append(
                        (
                            relative_text,
                            "file",
                            permissions,
                            after.st_size,
                            after.st_ino,
                            digest.hexdigest(),
                        )
                    )
                elif stat.S_ISLNK(metadata.st_mode):
                    try:
                        target = os.readlink(entry.name, dir_fd=directory_fd)
                        after = os.stat(entry.name, dir_fd=directory_fd, follow_symlinks=False)
                    except OSError as error:
                        raise ValueError("workspace mutation symlink is unavailable") from error
                    if not same_identity(metadata, after):
                        raise ValueError("workspace mutation symlink identity changed")
                    rows.append(
                        (
                            relative_text,
                            "symlink",
                            permissions,
                            len(target.encode("utf-8", errors="surrogatepass")),
                            metadata.st_ino,
                            hashlib.sha256(
                                target.encode("utf-8", errors="surrogatepass")
                            ).hexdigest(),
                        )
                    )
                else:
                    raise ValueError("workspace mutation entry type is unsupported")

        root_fd = None
        try:
            root_fd = os.open(root, directory_flags)
            opened_root = os.fstat(root_fd)
            if not same_identity(root_metadata, opened_root):
                raise ValueError("workspace mutation root identity changed")
            visit(root_fd, PurePosixPath())
        except OSError as error:
            raise ValueError("workspace mutation root is unavailable") from error
        finally:
            if root_fd is not None:
                os.close(root_fd)
        return tuple(rows)

    @classmethod
    def _workspace_integrity(
        cls,
        workspace_root: Path,
        expected: tuple[tuple[str, str, int, int, int, str], ...],
        allowed_output: Path,
    ) -> dict[str, object]:
        root = Path(workspace_root)
        output = Path(allowed_output)
        if output.parent != root or output.name not in {"first.final.txt", "second.final.txt"}:
            raise ValueError("workspace mutation output path is invalid")
        if output.exists():
            metadata = output.lstat()
            if output.is_symlink() or not stat.S_ISREG(metadata.st_mode):
                raise ValueError("workspace mutation output must be a regular file")
        current = cls._snapshot_guarded_workspace(root, expected)
        expected_map = {row[0]: row for row in expected if row[0] != output.name}
        current_map = {row[0]: row for row in current if row[0] != output.name}
        expected_paths = set(expected_map)
        current_paths = set(current_map)
        added = current_paths - expected_paths
        removed = expected_paths - current_paths
        changed = {
            path
            for path in expected_paths.intersection(current_paths)
            if expected_map[path] != current_map[path]
        }
        return {
            "schema_version": 1,
            "status": "mutated" if added or removed or changed else "clean",
            "added_count": len(added),
            "removed_count": len(removed),
            "changed_count": len(changed),
        }

    @staticmethod
    def _workspace_integrity_artifact(checks: Sequence[dict[str, object]]) -> str:
        return json.dumps({"schema_version": 1, "checks": list(checks)}, sort_keys=True)

    @staticmethod
    def _workspace_report_artifacts(workspace_root: Path) -> dict[str, bytes]:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        artifacts: dict[str, bytes] = {}
        workspace_fd = None
        base_fd = None
        reports_fd = None
        captured_files = 0
        captured_bytes = 0

        def same_identity(left: os.stat_result, right: os.stat_result) -> bool:
            return (left.st_dev, left.st_ino, left.st_mode) == (
                right.st_dev,
                right.st_ino,
                right.st_mode,
            )

        def visit(directory_fd: int, relative_parent: PurePosixPath) -> None:
            nonlocal captured_files, captured_bytes
            try:
                names = sorted(os.listdir(directory_fd))
            except OSError as error:
                raise ValueError("workspace report directory is unavailable") from error
            for name in names:
                if not name or name in {".", ".."} or "/" in name or "\\" in name:
                    raise ValueError("workspace report artifact path is unsafe")
                relative = relative_parent / name
                try:
                    metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError as error:
                    raise ValueError("workspace report artifact is unavailable") from error
                if stat.S_ISDIR(metadata.st_mode):
                    try:
                        child_fd = os.open(name, directory_flags, dir_fd=directory_fd)
                    except OSError as error:
                        raise ValueError(
                            "workspace report artifacts must not use symlinks"
                        ) from error
                    try:
                        opened = os.fstat(child_fd)
                        if not same_identity(metadata, opened):
                            raise ValueError("workspace report directory identity changed")
                        visit(child_fd, relative)
                    finally:
                        os.close(child_fd)
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    raise ValueError("workspace report artifacts must be regular files")
                captured_files += 1
                if captured_files > _MAX_CAPTURED_REPORT_FILES:
                    raise ValueError("workspace report capture exceeds file count limit")
                if metadata.st_size > _MAX_CAPTURED_REPORT_FILE_BYTES:
                    raise ValueError("workspace report artifact exceeds per-file byte limit")
                captured_bytes += metadata.st_size
                if captured_bytes > _MAX_CAPTURED_REPORT_TOTAL_BYTES:
                    raise ValueError("workspace report capture exceeds total byte limit")
                try:
                    descriptor = os.open(name, file_flags, dir_fd=directory_fd)
                except OSError as error:
                    raise ValueError("workspace report artifacts must not use symlinks") from error
                try:
                    before = os.fstat(descriptor)
                    if not same_identity(metadata, before):
                        raise ValueError("workspace report artifact identity changed")
                    chunks: list[bytes] = []
                    while True:
                        chunk = os.read(descriptor, 64 * 1024)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    after = os.fstat(descriptor)
                    if (
                        before.st_dev,
                        before.st_ino,
                        before.st_mode,
                        before.st_size,
                        before.st_mtime_ns,
                    ) != (
                        after.st_dev,
                        after.st_ino,
                        after.st_mode,
                        after.st_size,
                        after.st_mtime_ns,
                    ):
                        raise ValueError("workspace report artifact changed while captured")
                finally:
                    os.close(descriptor)
                artifacts[(PurePosixPath("workspace-reports") / relative).as_posix()] = b"".join(
                    chunks
                )

        try:
            workspace_fd = os.open(workspace_root, directory_flags)
            try:
                base_fd = os.open(
                    ".requirements-impact-refiner", directory_flags, dir_fd=workspace_fd
                )
            except FileNotFoundError:
                return {}
            try:
                reports_fd = os.open("reports", directory_flags, dir_fd=base_fd)
            except FileNotFoundError:
                return {}
            visit(reports_fd, PurePosixPath())
            return artifacts
        except OSError as error:
            raise ValueError("workspace report root must be a real directory") from error
        finally:
            for descriptor in (reports_fd, base_fd, workspace_fd):
                if descriptor is not None:
                    os.close(descriptor)

    @classmethod
    def _capture_workspace_reports(
        cls, artifacts: dict[str, Artifact], workspace_root: Path
    ) -> Optional[str]:
        try:
            artifacts.update(cls._workspace_report_artifacts(workspace_root))
        except (OSError, ValueError) as error:
            return f"workspace report capture failed: {error}"
        return None

    @staticmethod
    def _write_fixture_files(
        workspace_root: Path,
        fixture_files: tuple[tuple[str, str], ...],
    ) -> None:
        root = Path(workspace_root)
        if root.is_symlink() or not root.is_dir():
            raise ValueError("fixture workspace must be a real directory")
        if len(fixture_files) > MAX_FIXTURE_FILES:
            raise ValueError("fixture file count is unsafe")
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        total_bytes = 0

        def write_file(relative: str, payload: bytes) -> None:
            current_fd = os.open(root, directory_flags)
            try:
                parts = relative.split("/")
                for part in parts[:-1]:
                    try:
                        os.mkdir(part, 0o700, dir_fd=current_fd)
                    except FileExistsError:
                        pass
                    next_fd = os.open(part, directory_flags, dir_fd=current_fd)
                    os.close(current_fd)
                    current_fd = next_fd
                descriptor = os.open(parts[-1], file_flags, 0o600, dir_fd=current_fd)
                try:
                    offset = 0
                    while offset < len(payload):
                        written = os.write(descriptor, payload[offset:])
                        if written <= 0:
                            raise OSError("graph fixture write made no progress")
                        offset += written
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.fsync(current_fd)
            except OSError as error:
                raise ValueError(
                    "fixture path is unsafe or would overwrite workspace state"
                ) from error
            finally:
                os.close(current_fd)

        for relative, content in fixture_files:
            if not isinstance(relative, str) or not isinstance(content, str) or not content.strip():
                raise ValueError("fixture path or content is unsafe")
            pure = PurePosixPath(relative)
            if (
                pure.is_absolute()
                or relative != pure.as_posix()
                or "\\" in relative
                or any(part in {"", ".", ".."} for part in pure.parts)
                or (pure.parts and pure.parts[0] == ".requirements-impact-refiner")
                or any(ord(character) < 32 or ord(character) == 127 for character in relative)
            ):
                raise ValueError("fixture path is unsafe")
            try:
                path_bytes = len(relative.encode("utf-8"))
                payload = content.encode("utf-8")
            except UnicodeEncodeError as error:
                raise ValueError("fixture path or content is unsafe") from error
            if path_bytes > MAX_FIXTURE_PATH_BYTES or len(payload) > MAX_FIXTURE_CONTENT_BYTES:
                raise ValueError("fixture path or content is unsafe")
            total_bytes += path_bytes + len(payload)
            if total_bytes > MAX_FIXTURE_TOTAL_BYTES:
                raise ValueError("fixture total bytes are unsafe")
            write_file(relative, payload)

    @classmethod
    def _stage_catalog_fixture(cls, case: CaseSpec, workspace_root: Path) -> None:
        cls._write_fixture_files(workspace_root, case.fixture_files)

    @classmethod
    def _stage_followup_fixture(cls, case: CaseSpec, workspace_root: Path) -> None:
        cls._write_fixture_files(workspace_root, case.followup_fixture_files)

    @classmethod
    def _stage_graph_fixture(cls, case_id: str, workspace_root: Path) -> None:
        matches = tuple(case for case in load_graph_cases() if case.id == case_id)
        if not matches:
            return
        case = matches[0]
        if case.kind == "negative":
            return
        policy = graph_run_policy(case)
        settings = {
            "impact_graph": policy["settings"],
            "audience": "technical",
            "delivery": "compact",
        }
        cls._write_fixture_files(
            workspace_root,
            (
                (
                    ".requirements-impact-refiner.json",
                    json.dumps(settings, sort_keys=True) + "\n",
                ),
                *case.fixture_files,
            ),
        )

    @staticmethod
    def _workspace_graph_artifacts(workspace_root: Path) -> dict[str, bytes]:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        workspace_fd: Optional[int] = None
        base_fd: Optional[int] = None
        graph_fd: Optional[int] = None
        try:
            workspace_fd = os.open(workspace_root, directory_flags)
            try:
                base_fd = os.open(
                    ".requirements-impact-refiner",
                    directory_flags,
                    dir_fd=workspace_fd,
                )
            except FileNotFoundError:
                return {}
            try:
                graph_fd = os.open("graph", directory_flags, dir_fd=base_fd)
            except FileNotFoundError:
                return {}
            artifacts: dict[str, bytes] = {}
            for name in sorted(os.listdir(graph_fd)):
                if re.fullmatch(r"[0-9a-f]{32}\.json", name) is None:
                    raise ValueError("workspace graph receipt name is invalid")
                try:
                    descriptor = os.open(name, file_flags, dir_fd=graph_fd)
                except OSError as error:
                    raise ValueError("workspace graph artifacts must not use symlinks") from error
                try:
                    before = os.fstat(descriptor)
                    if not stat.S_ISREG(before.st_mode):
                        raise ValueError("workspace graph artifacts must be regular files")
                    if before.st_size > 1_048_576:
                        raise ValueError("workspace graph receipt exceeds maximum byte size")
                    chunks: list[bytes] = []
                    remaining = 1_048_576 + 1
                    while remaining:
                        chunk = os.read(descriptor, min(64 * 1024, remaining))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    payload = b"".join(chunks)
                    after = os.fstat(descriptor)
                    if len(payload) > 1_048_576:
                        raise ValueError("workspace graph receipt exceeds maximum byte size")
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
                        raise ValueError("workspace graph receipt changed while captured")
                finally:
                    os.close(descriptor)
                artifacts[f"workspace-graph/{name}"] = payload
            return artifacts
        finally:
            for open_descriptor in (graph_fd, base_fd, workspace_fd):
                if open_descriptor is not None:
                    os.close(open_descriptor)

    @classmethod
    def _capture_workspace_graph(
        cls, artifacts: dict[str, Artifact], workspace_root: Path
    ) -> Optional[str]:
        try:
            artifacts.update(cls._workspace_graph_artifacts(workspace_root))
        except (OSError, ValueError) as error:
            return f"workspace graph capture failed: {error}"
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
        if (
            self._requires_terminal_delivery(self.expected_plugin_version)
            and request.case.kind != "negative"
            and final_output is not None
        ):
            streams = tuple(
                value
                for name, value in sorted(artifacts.items())
                if name in ("first.jsonl", "second.jsonl") and isinstance(value, str)
            )
            turn_outputs = tuple(
                value if isinstance(value, str) else value.decode("utf-8", errors="strict")
                for name, value in sorted(artifacts.items())
                if name in ("first.final.txt", "second.final.txt")
                and isinstance(value, (str, bytes))
            )
            terminal = analyze_terminal_delivery(streams, turn_outputs)
            artifacts["terminal-delivery-evidence.json"] = terminal.to_json()
            if not terminal.valid:
                status = RunStatus.INVALID_EVIDENCE
                reason = "terminal delivery evidence invalid"
                final_output = None
        elif self.expected_plugin_version.startswith("0.4.") and final_output is not None:
            streams = tuple(
                value
                for name, value in sorted(artifacts.items())
                if name in ("first.jsonl", "second.jsonl") and isinstance(value, str)
            )
            expected_turns = 0 if request.case.kind == "negative" else len(request.case.turns)
            turn_outputs = tuple(
                value if isinstance(value, str) else value.decode("utf-8", errors="strict")
                for name, value in sorted(artifacts.items())
                if name in ("first.final.txt", "second.final.txt")
                and isinstance(value, (str, bytes))
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
            reason = f"evidence recording failed: {error}"
            final_output = None
        plugins = tuple(sorted(probe.enabled_plugins))
        client_version = probe.version or ""
        model = observed_model if provenance_command is not None else request.model
        reasoning = observed_reasoning if provenance_command is not None else request.reasoning
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
                    "codex {} plugins={}".format(
                        client_version or "unavailable", ",".join(plugins) or "none"
                    ),
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
            except (json.JSONDecodeError, RecursionError):
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
        def command_payload(command: CommandResult) -> dict[str, object]:
            return {
                "argv": list(command.argv),
                "returncode": command.returncode,
                "elapsed_seconds": command.elapsed_seconds,
                "timed_out": command.timed_out,
            }

        payload: dict[str, object] = {
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
        }
        graph_case = next(
            (case for case in load_graph_cases() if case.id == request.case.id),
            None,
        )
        if graph_case is not None:
            payload["graph_policy"] = graph_run_policy(graph_case)
        return json.dumps(payload, sort_keys=True)

    @staticmethod
    def _unavailable_probe(
        reason: str,
        version: Optional[str] = None,
        enabled: tuple[str, ...] = (),
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
