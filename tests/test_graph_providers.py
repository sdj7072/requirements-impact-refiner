import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "skills" / "requirements-impact-refiner" / "scripts" / "graph_providers.py"
)
SPEC = importlib.util.spec_from_file_location("graph_providers", MODULE_PATH)
PROVIDERS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PROVIDERS
SPEC.loader.exec_module(PROVIDERS)


class FakeClock:
    def __init__(self, current=0.0):
        self.current = current

    def monotonic(self):
        return self.current

    def advance(self, seconds):
        self.current += seconds


class Completed:
    def __init__(
        self, returncode=0, stdout=b"ok\n", stderr=b"", *,
        timed_out=False, stdout_truncated=False, stderr_truncated=False,
    ):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.stdout_truncated = stdout_truncated
        self.stderr_truncated = stderr_truncated


class RecordingRunner:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((tuple(argv), kwargs))
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, BaseException):
                raise response
            return response
        return Completed()


class ProviderRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        self.bin = Path(self.temporary.name) / "bin"
        self.bin.mkdir()
        self.fake_binary = self.bin / "sg"
        self.fake_binary.write_bytes(b"#!/bin/sh\nexit 0\n")
        self.fake_binary.chmod(0o700)
        self.clock = FakeClock()

    def test_runner_uses_fixed_argv_minimal_environment_and_shared_deadline(self):
        runner = RecordingRunner()
        result = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", executable=self.fake_binary),
            ("--version",), self.repo, PROVIDERS.Deadline(self.clock, 30),
            runner=runner,
        )

        self.assertEqual(result.argv, (str(self.fake_binary), "--version"))
        self.assertEqual(result.environment, {
            "PATH": str(self.fake_binary.parent),
            "CODEGRAPH_TELEMETRY": "0",
            "NO_COLOR": "1",
        })
        argv, kwargs = runner.calls[0]
        self.assertEqual(argv, result.argv)
        self.assertFalse(kwargs["shell"])
        self.assertTrue(kwargs["start_new_session"])
        self.assertEqual(kwargs["cwd"], str(self.repo.resolve()))
        self.assertEqual(kwargs["timeout"], 30.0)
        self.assertEqual(kwargs["stdout_limit"], 4 * 1024 * 1024)
        self.assertEqual(kwargs["stderr_limit"], 256 * 1024)
        self.assertNotIn("HOME", kwargs["env"])
        self.assertFalse(any(
            name.lower().endswith(("token", "proxy", "password", "secret"))
            for name in kwargs["env"]
        ))

    def test_deadline_is_shared_and_expired_work_is_not_started(self):
        deadline = PROVIDERS.Deadline(self.clock, 30)
        self.clock.advance(12.5)
        runner = RecordingRunner()
        result = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", self.fake_binary),
            ("--help",), self.repo, deadline, runner=runner,
        )
        self.assertEqual(runner.calls[0][1]["timeout"], 17.5)

        self.clock.advance(17.5)
        expired = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", self.fake_binary),
            ("--help",), self.repo, deadline, runner=runner,
        )
        self.assertEqual(expired.status, "timed_out")
        self.assertEqual(len(runner.calls), 1)

    def test_configured_executable_must_be_absolute_regular_and_not_symlinked(self):
        with self.assertRaisesRegex(ValueError, "absolute"):
            PROVIDERS.ProviderSpec("ast-grep", Path("bin/sg"))

        directory = self.bin / "directory"
        directory.mkdir()
        linked = self.bin / "linked-sg"
        os.symlink(self.fake_binary, linked)
        runner = RecordingRunner()
        for path in (directory, linked):
            with self.subTest(path=path):
                result = PROVIDERS.run_provider(
                    PROVIDERS.ProviderSpec("ast-grep", path), ("--version",),
                    self.repo, PROVIDERS.Deadline(self.clock, 30), runner=runner,
                )
                self.assertEqual(result.status, "unsafe")
        self.assertEqual(runner.calls, [])

    def test_open_executable_identity_detects_change_race_and_records_digest(self):
        original_digest = __import__("hashlib").sha256(self.fake_binary.read_bytes()).hexdigest()

        def changing_runner(argv, **kwargs):
            self.fake_binary.write_bytes(b"#!/bin/sh\nexit 1\n")
            self.fake_binary.chmod(0o700)
            return Completed(stdout=b"ast-grep 0.45.0\n")

        changed = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", self.fake_binary), ("--version",),
            self.repo, PROVIDERS.Deadline(self.clock, 30), runner=changing_runner,
        )
        self.assertEqual(changed.status, "unsafe")
        self.assertEqual(changed.executable_sha256, original_digest)

    def test_executable_descriptor_remains_open_through_post_spawn_identity_check(self):
        captured = {}
        runner = RecordingRunner((Completed(stdout=b"ast-grep 0.45.0\n"),))

        def recording_runner(argv, **kwargs):
            captured["descriptor"] = kwargs["executable_fd"]
            return runner(argv, **kwargs)

        real_same = PROVIDERS._same_executable

        def checked_while_open(path, opened, digest):
            os.fstat(captured["descriptor"])
            return real_same(path, opened, digest)

        with mock.patch.object(
            PROVIDERS, "_same_executable", side_effect=checked_while_open,
        ):
            result = PROVIDERS.run_provider(
                PROVIDERS.ProviderSpec("ast-grep", self.fake_binary),
                ("--version",), self.repo, PROVIDERS.Deadline(self.clock, 30),
                runner=recording_runner,
            )
        self.assertEqual(result.status, "ready")
        with self.assertRaises(OSError):
            os.fstat(captured["descriptor"])

    def test_output_caps_non_utf8_malformed_json_and_nonzero_are_fail_closed(self):
        cases = (
            (Completed(stdout=b"x" * (4 * 1024 * 1024 + 1)), False, "failed"),
            (Completed(stderr=b"x" * (256 * 1024 + 1)), False, "failed"),
            (Completed(stdout=b"\xff"), False, "failed"),
            (Completed(stdout=b"not json"), True, "failed"),
            (Completed(returncode=7, stderr=b"no"), False, "failed"),
        )
        for response, expect_json, expected in cases:
            with self.subTest(response=response, expect_json=expect_json):
                result = PROVIDERS.run_provider(
                    PROVIDERS.ProviderSpec("ast-grep", self.fake_binary),
                    ("--version",), self.repo, PROVIDERS.Deadline(self.clock, 30),
                    runner=RecordingRunner((response,)), expect_json=expect_json,
                )
                self.assertEqual(result.status, expected)
                self.assertLessEqual(len(result.stdout.encode("utf-8")), 4 * 1024 * 1024)
                self.assertLessEqual(len(result.stderr.encode("utf-8")), 256 * 1024)

    def test_timeout_status_is_preserved(self):
        runner = RecordingRunner((subprocess.TimeoutExpired(("sg",), 2),))
        result = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", self.fake_binary), ("--help",),
            self.repo, PROVIDERS.Deadline(self.clock, 2), runner=runner,
        )
        self.assertEqual(result.status, "timed_out")

    def test_default_runner_terminates_the_provider_process_group(self):
        sleeper = self.bin / "sleeper"
        sleeper.write_bytes(b"#!/bin/sh\nexec /bin/sleep 10\n")
        sleeper.chmod(0o700)
        started = time.monotonic()
        with mock.patch.object(
            PROVIDERS, "_descriptor_executable_path", return_value=str(sleeper),
        ), mock.patch.object(
            PROVIDERS, "_terminate_process_group",
            wraps=PROVIDERS._terminate_process_group,
        ) as terminate:
            result = PROVIDERS.run_provider(
                PROVIDERS.ProviderSpec("ast-grep", sleeper), ("--help",),
                self.repo, PROVIDERS.Deadline(time, 0.05),
            )
        self.assertEqual(result.status, "timed_out")
        self.assertTrue(terminate.called)
        self.assertLess(time.monotonic() - started, 2)

    def test_leader_exit_with_child_held_pipes_times_out_and_kills_saved_group(self):
        child_pid_path = self.repo / "child.pid"
        sleeper = self.bin / "forking-provider"
        sleeper.write_text(
            "#!/usr/bin/python3\n"
            "import os\n"
            "import time\n"
            "child = os.fork()\n"
            "if child == 0:\n"
            "    time.sleep(6)\n"
            "    os._exit(0)\n"
            f"open({str(child_pid_path)!r}, 'w').write(str(child))\n"
            "os._exit(0)\n",
            encoding="utf-8",
        )
        sleeper.chmod(0o700)
        started = time.monotonic()
        child_pid = None
        try:
            with mock.patch.object(
                PROVIDERS, "_descriptor_executable_path", return_value=str(sleeper),
            ):
                result = PROVIDERS.run_provider(
                    PROVIDERS.ProviderSpec("ast-grep", sleeper), ("--help",),
                    self.repo, PROVIDERS.Deadline(FakeClock(), 2.0),
                )
            self.assertEqual(result.status, "timed_out")
            self.assertLess(time.monotonic() - started, 3.5)
            child_pid = int(child_pid_path.read_text(encoding="ascii").strip())
            for _ in range(100):
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.01)
            else:
                self.fail("timed-out provider child remained alive")
        finally:
            if child_pid is not None:
                try:
                    os.kill(child_pid, 9)
                except (PermissionError, ProcessLookupError):
                    pass

    def test_descriptor_path_selection_prefers_proc_then_dev_and_can_fail_closed(self):
        def selection(exists, executable):
            metadata = self.fake_binary.stat()
            with mock.patch.object(PROVIDERS.os.path, "exists", side_effect=exists), \
                 mock.patch.object(PROVIDERS.os, "access", side_effect=executable), \
                 mock.patch.object(PROVIDERS.os, "fstat", return_value=metadata), \
                 mock.patch.object(PROVIDERS.os, "stat", return_value=metadata):
                return PROVIDERS._descriptor_executable_path(17)

        self.assertEqual(
            selection(lambda path: True, lambda path, mode: True),
            "/proc/self/fd/17",
        )
        self.assertEqual(
            selection(
                lambda path: path.startswith("/dev/"),
                lambda path, mode: path.startswith("/dev/"),
            ),
            "/dev/fd/17",
        )
        self.assertIsNone(selection(lambda path: False, lambda path, mode: False))

    def test_platform_descriptor_launch_executes_bound_file_or_fails_closed(self):
        descriptor = os.open(str(self.fake_binary), os.O_RDONLY)
        try:
            supported = PROVIDERS._descriptor_executable_path(descriptor) is not None
        finally:
            os.close(descriptor)

        result = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", self.fake_binary),
            ("--version",), self.repo, PROVIDERS.Deadline(time, 1),
        )
        self.assertEqual(result.status, "ready" if supported else "unsafe")

    def test_path_replacement_before_spawn_never_executes_replacement(self):
        replacement_marker = self.repo / "replacement-ran"
        original_marker = self.repo / "original-ran"
        binary = self.bin / "race-provider"
        binary.write_text(
            f"#!/bin/sh\n/bin/echo original > \"{original_marker}\"\n",
            encoding="utf-8",
        )
        binary.chmod(0o700)

        def replacing_runner(argv, **kwargs):
            binary.write_text(
                f"#!/bin/sh\n/bin/echo replacement > \"{replacement_marker}\"\n",
                encoding="utf-8",
            )
            binary.chmod(0o700)
            return PROVIDERS._bounded_subprocess(argv, **kwargs)

        result = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", binary), ("--help",), self.repo,
            PROVIDERS.Deadline(time, 1), runner=replacing_runner,
        )
        self.assertEqual(result.status, "unsafe")
        self.assertFalse(replacement_marker.exists())

    def test_forbidden_discovery_and_mutating_commands_never_run(self):
        runner = RecordingRunner()
        for argument in ("server", "login", "auth", "upload", "install", "watch", "index", "parse"):
            with self.subTest(argument=argument):
                result = PROVIDERS.run_provider(
                    PROVIDERS.ProviderSpec("codegraph", self.fake_binary),
                    (argument,), self.repo, PROVIDERS.Deadline(self.clock, 30), runner=runner,
                )
                self.assertEqual(result.status, "unsafe")
        self.assertEqual(runner.calls, [])


class ProviderDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        self.bin = Path(self.temporary.name) / "bin"
        self.bin.mkdir()
        for name in ("codegraph", "scip", "sg", "ast-grep", "joern"):
            path = self.bin / name
            path.write_bytes(b"#!/bin/sh\nexit 0\n")
            path.chmod(0o700)
        self.clock = FakeClock()

    def test_auto_discovery_has_fixed_names_priority_and_exact_probe_argv(self):
        responses = []
        for name in ("codegraph", "scip", "joern", "ast-grep"):
            responses.extend((
                Completed(stdout=(name + " 1.2.3\n").encode()),
                Completed(stdout=b"read-only json help\n"),
            ))
        runner = RecordingRunner(responses)
        probes = PROVIDERS.discover_providers(
            self.repo, ("auto",), PROVIDERS.Deadline(self.clock, 30),
            runner=runner, search_path=str(self.bin), deep=True,
        )

        self.assertEqual([probe.name for probe in probes], [
            "codegraph", "scip", "joern", "ast-grep",
        ])
        self.assertTrue(all(probe.status == "ready" for probe in probes))
        self.assertEqual([call[0][1:] for call in runner.calls], [
            ("--version",), ("--help",),
            ("--version",), ("--help",),
            ("--version",), ("--help",),
            ("--version",), ("--help",),
        ])
        self.assertTrue(all(probe.version for probe in probes))
        self.assertTrue(all(len(probe.executable_sha256 or "") == 64 for probe in probes))

    def test_auto_discovery_exact_order_excludes_joern_unless_deep(self):
        def discover(deep):
            names = (
                ("codegraph", "scip", "joern", "ast-grep")
                if deep else ("codegraph", "scip", "ast-grep")
            )
            responses = []
            for name in names:
                responses.extend((
                    Completed(stdout=(name + " 1.0\n").encode()),
                    Completed(stdout=b"help\n"),
                ))
            return PROVIDERS.discover_providers(
                self.repo, ("auto",), PROVIDERS.Deadline(self.clock, 30),
                runner=RecordingRunner(responses), search_path=str(self.bin), deep=deep,
            )

        self.assertEqual(
            [probe.name for probe in discover(False)],
            ["codegraph", "scip", "ast-grep"],
        )
        self.assertEqual(
            [probe.name for probe in discover(True)],
            ["codegraph", "scip", "joern", "ast-grep"],
        )

    def test_explicit_absolute_path_and_sg_alias_are_normalized(self):
        runner = RecordingRunner((
            Completed(stdout=b"ast-grep 0.45.0\n"), Completed(stdout=b"json stream\n"),
        ))
        probes = PROVIDERS.discover_providers(
            self.repo, (str(self.bin / "sg"),), PROVIDERS.Deadline(self.clock, 30),
            runner=runner,
        )
        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].name, "ast-grep")
        self.assertEqual(probes[0].executable, self.bin / "sg")

    def test_unknown_or_relative_config_is_unsafe_without_execution(self):
        runner = RecordingRunner()
        for configured in ("other", "tools/sg"):
            with self.subTest(configured=configured):
                probes = PROVIDERS.discover_providers(
                    self.repo, (configured,), PROVIDERS.Deadline(self.clock, 30),
                    runner=runner, search_path=str(self.bin),
                )
                self.assertEqual(probes[0].status, "unsafe")
        self.assertEqual(runner.calls, [])

    def test_missing_timeout_failure_and_unsupported_help_preserve_status(self):
        missing = PROVIDERS.discover_providers(
            self.repo, ("codegraph",), PROVIDERS.Deadline(self.clock, 30),
            runner=RecordingRunner(), search_path="",
        )
        self.assertEqual(missing[0].status, "missing")

        cases = (
            (subprocess.TimeoutExpired(("scip",), 1), "timed_out"),
            (Completed(returncode=3), "failed"),
            ((Completed(stdout=b"scip 1.0\n"), Completed(returncode=2)), "unsupported"),
        )
        for responses, expected in cases:
            with self.subTest(expected=expected):
                values = responses if isinstance(responses, tuple) else (responses,)
                probe = PROVIDERS.discover_providers(
                    self.repo, (str(self.bin / "scip"),),
                    PROVIDERS.Deadline(self.clock, 30), runner=RecordingRunner(values),
                )[0]
                self.assertEqual(probe.status, expected)

    def test_discovery_rejects_executable_change_between_version_and_help(self):
        binary = self.bin / "scip"

        class ChangeAfterIdentityCheck:
            returncode = 0
            stderr = b""
            timed_out = False
            stdout_truncated = False
            stderr_truncated = False

            @property
            def stdout(self):
                binary.write_bytes(b"#!/bin/sh\n# changed\nexit 0\n")
                binary.chmod(0o700)
                return b"scip 1.0\n"

        def changing_runner(argv, **kwargs):
            if argv[-1] == "--version":
                return ChangeAfterIdentityCheck()
            return Completed(stdout=b"help\n")

        probe = PROVIDERS.discover_providers(
            self.repo, (str(binary),), PROVIDERS.Deadline(self.clock, 30),
            runner=changing_runner,
        )[0]
        self.assertEqual(probe.status, "unsafe")

    def test_version_metadata_redacts_credential_shaped_provider_output(self):
        runner = RecordingRunner((
            Completed(stdout=b"API_TOKEN=supersecret\n"),
            Completed(stdout=b"help\n"),
        ))
        probe = PROVIDERS.discover_providers(
            self.repo, (str(self.bin / "codegraph"),),
            PROVIDERS.Deadline(self.clock, 30), runner=runner,
        )[0]
        self.assertNotIn("supersecret", probe.version or "")

    def test_discovery_result_does_not_capture_inherited_credentials(self):
        runner = RecordingRunner((Completed(stdout=b"v1\n"), Completed(stdout=b"help\n")))
        with mock.patch.dict(os.environ, {
            "HOME": "/sensitive", "HTTP_PROXY": "http://proxy", "API_TOKEN": "secret",
        }):
            PROVIDERS.discover_providers(
                self.repo, (str(self.bin / "codegraph"),),
                PROVIDERS.Deadline(self.clock, 30), runner=runner,
            )
        for _, kwargs in runner.calls:
            self.assertEqual(set(kwargs["env"]), {
                "PATH", "CODEGRAPH_TELEMETRY", "NO_COLOR",
            })


if __name__ == "__main__":
    unittest.main()
