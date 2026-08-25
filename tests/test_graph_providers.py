import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "graph_providers.py"
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
        self,
        returncode=0,
        stdout=b"ok\n",
        stderr=b"",
        *,
        timed_out=False,
        stdout_truncated=False,
        stderr_truncated=False,
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
            ("--version",),
            self.repo,
            PROVIDERS.Deadline(self.clock, 30),
            runner=runner,
        )

        self.assertEqual(result.argv, (str(self.fake_binary), "--version"))
        self.assertEqual(
            result.environment,
            {
                "PATH": str(self.fake_binary.parent),
                "CODEGRAPH_TELEMETRY": "0",
                "NO_COLOR": "1",
            },
        )
        argv, kwargs = runner.calls[0]
        self.assertEqual(argv, result.argv)
        self.assertFalse(kwargs["shell"])
        self.assertTrue(kwargs["start_new_session"])
        self.assertEqual(kwargs["cwd"], str(self.repo.resolve()))
        self.assertEqual(kwargs["timeout"], 30.0)
        self.assertEqual(kwargs["stdout_limit"], 4 * 1024 * 1024)
        self.assertEqual(kwargs["stderr_limit"], 256 * 1024)
        self.assertNotIn("HOME", kwargs["env"])
        self.assertFalse(
            any(
                name.lower().endswith(("token", "proxy", "password", "secret"))
                for name in kwargs["env"]
            )
        )

    def test_deadline_is_shared_and_expired_work_is_not_started(self):
        deadline = PROVIDERS.Deadline(self.clock, 30)
        self.clock.advance(12.5)
        runner = RecordingRunner()
        PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", self.fake_binary),
            ("--help",),
            self.repo,
            deadline,
            runner=runner,
        )
        self.assertEqual(runner.calls[0][1]["timeout"], 17.5)

        self.clock.advance(17.5)
        expired = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", self.fake_binary),
            ("--help",),
            self.repo,
            deadline,
            runner=runner,
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
                    PROVIDERS.ProviderSpec("ast-grep", path),
                    ("--version",),
                    self.repo,
                    PROVIDERS.Deadline(self.clock, 30),
                    runner=runner,
                )
                self.assertEqual(result.status, "unsafe")
        self.assertEqual(runner.calls, [])

    def test_snapshot_is_private_fsynced_identity_and_removed_after_runner_returns(self):
        captured = {}

        def inspecting_runner(argv, **kwargs):
            snapshot = Path(kwargs["executable_snapshot"])
            captured["snapshot"] = snapshot
            captured["directory"] = snapshot.parent
            self.assertEqual(stat.S_IMODE(snapshot.stat().st_mode), 0o500)
            self.assertEqual(stat.S_IMODE(snapshot.parent.stat().st_mode), 0o700)
            self.assertEqual(
                __import__("hashlib").sha256(snapshot.read_bytes()).hexdigest(),
                kwargs["snapshot_sha256"],
            )
            return Completed(stdout=b"ast-grep 0.45.0\n")

        result = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", self.fake_binary),
            ("--version",),
            self.repo,
            PROVIDERS.Deadline(self.clock, 30),
            runner=inspecting_runner,
        )
        self.assertEqual(result.status, "ready")
        self.assertFalse(captured["snapshot"].exists())
        self.assertFalse(captured["directory"].exists())

    def test_executable_size_cap_rejects_before_snapshot_or_runner(self):
        oversized = self.bin / "oversized-provider"
        with oversized.open("wb") as handle:
            handle.truncate(PROVIDERS.MAX_EXECUTABLE_BYTES + 1)
        oversized.chmod(0o700)
        runner = RecordingRunner()
        result = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", oversized),
            ("--version",),
            self.repo,
            PROVIDERS.Deadline(self.clock, 30),
            runner=runner,
        )
        self.assertEqual(result.status, "unsafe")
        self.assertEqual(runner.calls, [])

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
                    ("--version",),
                    self.repo,
                    PROVIDERS.Deadline(self.clock, 30),
                    runner=RecordingRunner((response,)),
                    expect_json=expect_json,
                )
                self.assertEqual(result.status, expected)
                self.assertLessEqual(len(result.stdout.encode("utf-8")), 4 * 1024 * 1024)
                self.assertLessEqual(len(result.stderr.encode("utf-8")), 256 * 1024)

    def test_deep_provider_and_protobuf_json_fail_closed_without_recursion_escape(self):
        for label, payload in (
            ("generic-json", b"[" * 1200 + b"0" + b"]" * 1200),
            (
                "protobuf-json",
                b'{"documents":' + b"[" * 1200 + b"{}" + b"]" * 1200 + b"}",
            ),
        ):
            with self.subTest(label=label):
                result = PROVIDERS.run_provider(
                    PROVIDERS.ProviderSpec("ast-grep", self.fake_binary),
                    ("--version",),
                    self.repo,
                    PROVIDERS.Deadline(self.clock, 30),
                    runner=RecordingRunner((Completed(stdout=payload),)),
                    expect_json=True,
                )
                self.assertEqual(result.status, "failed")
                self.assertIsNone(result.parsed_json)

    def test_timeout_status_is_preserved(self):
        runner = RecordingRunner((subprocess.TimeoutExpired(("sg",), 2),))
        result = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", self.fake_binary),
            ("--help",),
            self.repo,
            PROVIDERS.Deadline(self.clock, 2),
            runner=runner,
        )
        self.assertEqual(result.status, "timed_out")

    def test_default_runner_terminates_the_provider_process_group(self):
        sleeper = self.bin / "sleeper"
        sleeper.write_bytes(b"#!/bin/sh\nexec /bin/sleep 10\n")
        sleeper.chmod(0o700)
        started = time.monotonic()
        captured = {}

        def capture_snapshot(argv, **kwargs):
            captured["snapshot"] = Path(kwargs["executable_snapshot"])
            captured["directory"] = captured["snapshot"].parent
            return PROVIDERS._bounded_subprocess(argv, **kwargs)

        with mock.patch.object(
            PROVIDERS,
            "_terminate_process_group",
            wraps=PROVIDERS._terminate_process_group,
        ) as terminate:
            result = PROVIDERS.run_provider(
                PROVIDERS.ProviderSpec("ast-grep", sleeper),
                ("--help",),
                self.repo,
                PROVIDERS.Deadline(time, 0.05),
                runner=capture_snapshot,
            )
        self.assertEqual(result.status, "timed_out")
        self.assertTrue(terminate.called)
        self.assertLess(time.monotonic() - started, 2)
        self.assertFalse(captured["snapshot"].exists())
        self.assertFalse(captured["directory"].exists())

    def test_runner_error_path_removes_snapshot(self):
        captured = {}

        def failing_runner(argv, **kwargs):
            captured["snapshot"] = Path(kwargs["executable_snapshot"])
            captured["directory"] = captured["snapshot"].parent
            raise OSError("controlled runner failure")

        result = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", self.fake_binary),
            ("--help",),
            self.repo,
            PROVIDERS.Deadline(self.clock, 2),
            runner=failing_runner,
        )
        self.assertEqual(result.status, "failed")
        self.assertFalse(captured["snapshot"].exists())
        self.assertFalse(captured["directory"].exists())

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
            result = PROVIDERS.run_provider(
                PROVIDERS.ProviderSpec("ast-grep", sleeper),
                ("--help",),
                self.repo,
                PROVIDERS.Deadline(FakeClock(), 2.0),
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

    def test_current_platform_executes_compiled_and_script_providers_from_snapshot(self):
        compiled = self.bin / "codegraph"
        source = self.bin / "provider.c"
        source.write_text(
            '#include <stdio.h>\nint main(void) { puts("snapshot-compiled"); return 0; }\n',
            encoding="utf-8",
        )
        subprocess.run(
            ("/usr/bin/clang", str(source), "-o", str(compiled)),
            check=True,
            capture_output=True,
        )
        script = self.bin / "sg-self-contained"
        script.write_text("#!/bin/sh\nprintf 'snapshot-script\\n'\n", encoding="utf-8")
        script.chmod(0o700)

        compiled_result = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("codegraph", compiled),
            ("--version",),
            self.repo,
            PROVIDERS.Deadline(time, 2),
        )
        script_result = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", script),
            ("--version",),
            self.repo,
            PROVIDERS.Deadline(time, 2),
        )
        self.assertEqual(compiled_result.status, "ready")
        self.assertEqual(compiled_result.stdout.strip(), "snapshot-compiled")
        self.assertEqual(script_result.status, "ready")
        self.assertEqual(script_result.stdout.strip(), "snapshot-script")

    def test_original_path_replacement_and_same_inode_overwrite_cannot_affect_snapshot(self):
        for mutation in ("replace", "overwrite"):
            with self.subTest(mutation=mutation):
                attacker_marker = self.repo / (mutation + "-attacker-ran")
                binary = self.bin / (mutation + "-provider")
                binary.write_text("#!/bin/sh\nprintf 'snapshot-safe\\n'\n", encoding="utf-8")
                binary.chmod(0o700)

                def mutating_runner(
                    argv,
                    attacker_marker=attacker_marker,
                    mutation=mutation,
                    binary=binary,
                    **kwargs,
                ):
                    attacker = (
                        "#!/bin/sh\n"
                        f'/bin/echo attacker > "{attacker_marker}"\n'
                        "printf 'attacker\\n'\n"
                    ).encode()
                    if mutation == "replace":
                        replacement = binary.with_suffix(".replacement")
                        replacement.write_bytes(attacker)
                        replacement.chmod(0o700)
                        os.replace(replacement, binary)
                    else:
                        descriptor = os.open(str(binary), os.O_WRONLY | os.O_TRUNC)
                        try:
                            os.write(descriptor, attacker)
                            os.fsync(descriptor)
                        finally:
                            os.close(descriptor)
                    return PROVIDERS._bounded_subprocess(argv, **kwargs)

                result = PROVIDERS.run_provider(
                    PROVIDERS.ProviderSpec("ast-grep", binary),
                    ("--version",),
                    self.repo,
                    PROVIDERS.Deadline(time, 2),
                    runner=mutating_runner,
                )
                self.assertEqual(result.status, "ready")
                self.assertEqual(result.stdout.strip(), "snapshot-safe")
                self.assertFalse(attacker_marker.exists())

    def test_snapshot_mutation_hook_fails_closed_before_execution(self):
        attacker_marker = self.repo / "snapshot-attacker-ran"
        binary = self.bin / "snapshot-mutation-provider"
        binary.write_text("#!/bin/sh\nprintf 'safe\\n'\n", encoding="utf-8")
        binary.chmod(0o700)

        def mutate_snapshot(argv, **kwargs):
            snapshot = Path(kwargs["executable_snapshot"])
            snapshot.chmod(0o700)
            snapshot.write_text(
                f'#!/bin/sh\n/bin/echo attacker > "{attacker_marker}"\n',
                encoding="utf-8",
            )
            snapshot.chmod(0o700)
            return PROVIDERS._bounded_subprocess(argv, **kwargs)

        result = PROVIDERS.run_provider(
            PROVIDERS.ProviderSpec("ast-grep", binary),
            ("--version",),
            self.repo,
            PROVIDERS.Deadline(time, 2),
            runner=mutate_snapshot,
        )
        self.assertEqual(result.status, "unsafe")
        self.assertFalse(attacker_marker.exists())

    def test_provider_chmod_and_extra_artifacts_are_cleaned_without_following_symlink(self):
        captured = {}
        binary = self.bin / "cleanup-hostile-provider"
        binary.write_text(
            "#!/bin/sh\n"
            'snapshot="$0"\n'
            'directory=$(/usr/bin/dirname "$snapshot")\n'
            "printf 'extra' > \"$directory/extra-file\"\n"
            '/bin/ln -s /etc/passwd "$directory/extra-link"\n'
            '/bin/chmod 000 "$snapshot"\n'
            '/bin/chmod 000 "$directory"\n',
            encoding="utf-8",
        )
        binary.chmod(0o700)

        def capture_snapshot(argv, **kwargs):
            captured["snapshot"] = Path(kwargs["executable_snapshot"])
            captured["directory"] = captured["snapshot"].parent
            captured["extra"] = captured["directory"] / "extra-file"
            captured["link"] = captured["directory"] / "extra-link"
            return PROVIDERS._bounded_subprocess(argv, **kwargs)

        try:
            result = PROVIDERS.run_provider(
                PROVIDERS.ProviderSpec("ast-grep", binary),
                ("--version",),
                self.repo,
                PROVIDERS.Deadline(time, 2),
                runner=capture_snapshot,
            )
            remnants = {name: os.path.lexists(path) for name, path in captured.items()}
        finally:
            directory = captured.get("directory")
            if directory is not None and os.path.lexists(directory):
                try:
                    os.chmod(directory, 0o700)
                except OSError:
                    pass
                shutil.rmtree(directory)
        self.assertEqual(result.status, "unsafe")
        self.assertEqual(
            remnants,
            {
                "snapshot": False,
                "directory": False,
                "extra": False,
                "link": False,
            },
        )

    def test_cleanup_child_directory_swap_never_touches_outside_target(self):
        captured = {}
        outside = self.repo / "outside-cleanup-target"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_text("outside-must-survive", encoding="utf-8")
        quarantined = self.repo / "quarantined-private-child"
        real_open = os.open
        real_scandir = os.scandir
        swapped = False

        def swap_child_to_outside_symlink():
            nonlocal swapped
            if swapped:
                return
            swapped = True
            os.rename(captured["child"], quarantined)
            os.symlink(outside, captured["child"], target_is_directory=True)

        def racing_open(path, flags, mode=0o777, *, dir_fd=None):
            if not swapped and dir_fd is not None and path == captured.get("child", Path()).name:
                swap_child_to_outside_symlink()
            return real_open(path, flags, mode, dir_fd=dir_fd)

        def racing_scandir(path):
            if not swapped and not isinstance(path, int) and Path(path) == captured.get("child"):
                swap_child_to_outside_symlink()
            return real_scandir(path)

        def create_private_child(argv, **kwargs):
            captured["snapshot"] = Path(kwargs["executable_snapshot"])
            captured["directory"] = captured["snapshot"].parent
            captured["child"] = captured["directory"] / "race-child"
            captured["child"].mkdir()
            (captured["child"] / "private-file").write_text(
                "private",
                encoding="utf-8",
            )
            return Completed(stdout=b"ready\n")

        try:
            with (
                mock.patch.object(PROVIDERS.os, "open", side_effect=racing_open),
                mock.patch.object(
                    PROVIDERS.os,
                    "scandir",
                    side_effect=racing_scandir,
                ),
            ):
                result = PROVIDERS.run_provider(
                    PROVIDERS.ProviderSpec("ast-grep", self.fake_binary),
                    ("--version",),
                    self.repo,
                    PROVIDERS.Deadline(self.clock, 2),
                    runner=create_private_child,
                )
            self.assertTrue(swapped)
            self.assertEqual(result.status, "unsafe")
            self.assertEqual(
                sentinel.read_text(encoding="utf-8") if sentinel.exists() else None,
                "outside-must-survive",
            )
        finally:
            child = captured.get("child")
            if child is not None and os.path.lexists(child):
                os.unlink(child)
            if quarantined.exists():
                shutil.rmtree(quarantined)
            directory = captured.get("directory")
            if directory is not None and os.path.lexists(directory):
                os.chmod(directory, 0o700)
                shutil.rmtree(directory)

    def test_private_root_cleanup_removes_retained_renamed_inode_not_replacement(self):
        directory, descriptor = PROVIDERS.create_private_root("rir-test-root-")
        original = directory
        raw = os.open(
            "raw-index",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o400,
            dir_fd=descriptor,
        )
        os.write(raw, b"raw-index-bytes")
        os.close(raw)
        renamed = directory.with_name(directory.name + "-renamed")
        os.rename(directory, renamed)
        directory.mkdir(mode=0o700)
        replacement = directory / "replacement.txt"
        replacement.write_text("keep", encoding="utf-8")

        cleaned, changed, detail = PROVIDERS.cleanup_private_root(
            original,
            descriptor,
        )

        self.assertTrue(cleaned)
        self.assertTrue(changed)
        self.assertIn("changed", detail)
        self.assertFalse(renamed.exists())
        self.assertEqual(replacement.read_text(encoding="utf-8"), "keep")
        shutil.rmtree(directory)

    def test_cleanup_failure_upgrades_ready_result_to_unsafe(self):
        captured = {}
        real_cleanup = PROVIDERS._cleanup_snapshot

        def controlled_cleanup_failure(snapshot):
            captured["snapshot"] = snapshot.path
            captured["directory"] = snapshot.directory
            real_cleanup(snapshot)
            return False, "controlled cleanup verification failure"

        with mock.patch.object(
            PROVIDERS,
            "_cleanup_snapshot",
            side_effect=controlled_cleanup_failure,
        ):
            result = PROVIDERS.run_provider(
                PROVIDERS.ProviderSpec("ast-grep", self.fake_binary),
                ("--version",),
                self.repo,
                PROVIDERS.Deadline(self.clock, 2),
                runner=RecordingRunner((Completed(stdout=b"ready\n"),)),
            )
        self.assertEqual(result.status, "unsafe")
        self.assertIn("cleanup", result.detail)
        self.assertFalse(os.path.lexists(captured["snapshot"]))
        self.assertFalse(os.path.lexists(captured["directory"]))

    def test_forbidden_discovery_and_mutating_commands_never_run(self):
        runner = RecordingRunner()
        for argument in ("server", "login", "auth", "upload", "install", "watch", "index", "parse"):
            with self.subTest(argument=argument):
                result = PROVIDERS.run_provider(
                    PROVIDERS.ProviderSpec("codegraph", self.fake_binary),
                    (argument,),
                    self.repo,
                    PROVIDERS.Deadline(self.clock, 30),
                    runner=runner,
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
            responses.extend(
                (
                    Completed(stdout=(name + " 1.2.3\n").encode()),
                    Completed(stdout=b"read-only json help\n"),
                )
            )
        runner = RecordingRunner(responses)
        probes = PROVIDERS.discover_providers(
            self.repo,
            ("auto",),
            PROVIDERS.Deadline(self.clock, 30),
            runner=runner,
            search_path=str(self.bin),
            deep=True,
        )

        self.assertEqual(
            [probe.name for probe in probes],
            [
                "codegraph",
                "scip",
                "joern",
                "ast-grep",
            ],
        )
        self.assertTrue(all(probe.status == "ready" for probe in probes))
        self.assertEqual(
            [call[0][1:] for call in runner.calls],
            [
                ("--version",),
                ("--help",),
                ("--version",),
                ("--help",),
                ("--version",),
                ("--help",),
                ("--version",),
                ("--help",),
            ],
        )
        self.assertTrue(all(probe.version for probe in probes))
        self.assertTrue(all(len(probe.executable_sha256 or "") == 64 for probe in probes))

    def test_auto_discovery_exact_order_excludes_joern_unless_deep(self):
        def discover(deep):
            names = (
                ("codegraph", "scip", "joern", "ast-grep")
                if deep
                else ("codegraph", "scip", "ast-grep")
            )
            responses = []
            for name in names:
                responses.extend(
                    (
                        Completed(stdout=(name + " 1.0\n").encode()),
                        Completed(stdout=b"help\n"),
                    )
                )
            return PROVIDERS.discover_providers(
                self.repo,
                ("auto",),
                PROVIDERS.Deadline(self.clock, 30),
                runner=RecordingRunner(responses),
                search_path=str(self.bin),
                deep=deep,
            )

        self.assertEqual(
            [probe.name for probe in discover(False)],
            ["codegraph", "scip", "ast-grep"],
        )
        self.assertEqual(
            [probe.name for probe in discover(True)],
            ["codegraph", "scip", "joern", "ast-grep"],
        )

    def test_explicit_joern_is_never_detected_without_deep_mode(self):
        for requested in ("joern", str(self.bin / "joern")):
            with self.subTest(requested=requested):
                runner = RecordingRunner()
                probes = PROVIDERS.discover_providers(
                    self.repo,
                    (requested,),
                    PROVIDERS.Deadline(self.clock, 30),
                    runner=runner,
                    search_path=str(self.bin),
                    deep=False,
                )
                self.assertEqual(len(probes), 1)
                self.assertEqual(probes[0].name, "joern")
                self.assertEqual(probes[0].status, "unsupported")
                self.assertEqual(runner.calls, [])

        runner = RecordingRunner(
            (
                Completed(stdout=b"joern 4.0.12\n"),
                Completed(stdout=b"Usage: joern query --json --graph <GRAPH> --seed <TEXT>\n"),
            )
        )
        probes = PROVIDERS.discover_providers(
            self.repo,
            ("joern",),
            PROVIDERS.Deadline(self.clock, 30),
            runner=runner,
            search_path=str(self.bin),
            deep=True,
        )
        self.assertEqual(probes[0].status, "ready")
        self.assertEqual([call[0][1:] for call in runner.calls], [("--version",), ("--help",)])

    def test_explicit_absolute_path_and_sg_alias_are_normalized(self):
        runner = RecordingRunner(
            (
                Completed(stdout=b"ast-grep 0.45.0\n"),
                Completed(stdout=b"json stream\n"),
            )
        )
        probes = PROVIDERS.discover_providers(
            self.repo,
            (str(self.bin / "sg"),),
            PROVIDERS.Deadline(self.clock, 30),
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
                    self.repo,
                    (configured,),
                    PROVIDERS.Deadline(self.clock, 30),
                    runner=runner,
                    search_path=str(self.bin),
                )
                self.assertEqual(probes[0].status, "unsafe")
        self.assertEqual(runner.calls, [])

    def test_missing_timeout_failure_and_unsupported_help_preserve_status(self):
        missing = PROVIDERS.discover_providers(
            self.repo,
            ("codegraph",),
            PROVIDERS.Deadline(self.clock, 30),
            runner=RecordingRunner(),
            search_path="",
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
                    self.repo,
                    (str(self.bin / "scip"),),
                    PROVIDERS.Deadline(self.clock, 30),
                    runner=RecordingRunner(values),
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
            self.repo,
            (str(binary),),
            PROVIDERS.Deadline(self.clock, 30),
            runner=changing_runner,
        )[0]
        self.assertEqual(probe.status, "unsafe")

    def test_version_metadata_redacts_credential_shaped_provider_output(self):
        runner = RecordingRunner(
            (
                Completed(stdout=b"API_TOKEN=supersecret\n"),
                Completed(stdout=b"help\n"),
            )
        )
        probe = PROVIDERS.discover_providers(
            self.repo,
            (str(self.bin / "codegraph"),),
            PROVIDERS.Deadline(self.clock, 30),
            runner=runner,
        )[0]
        self.assertNotIn("supersecret", probe.version or "")

    def test_discovery_result_does_not_capture_inherited_credentials(self):
        runner = RecordingRunner((Completed(stdout=b"v1\n"), Completed(stdout=b"help\n")))
        with mock.patch.dict(
            os.environ,
            {
                "HOME": "/sensitive",
                "HTTP_PROXY": "http://proxy",
                "API_TOKEN": "secret",
            },
        ):
            PROVIDERS.discover_providers(
                self.repo,
                (str(self.bin / "codegraph"),),
                PROVIDERS.Deadline(self.clock, 30),
                runner=runner,
            )
        for _, kwargs in runner.calls:
            self.assertEqual(
                set(kwargs["env"]),
                {
                    "PATH",
                    "CODEGRAPH_TELEMETRY",
                    "NO_COLOR",
                },
            )


if __name__ == "__main__":
    unittest.main()
