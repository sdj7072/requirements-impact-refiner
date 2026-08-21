import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evals.harness.adapters.claude import ClaudeAdapter
from evals.harness.models import CaseSpec, CaseTurn, RunRequest, RunStatus


ROOT = Path(__file__).resolve().parents[1]

CLAUDE_PLUGIN_LIST_FIXTURE = """[
  {
    "id": "requirements-impact-refiner@requirements-impact-refiner",
    "version": "0.3.0",
    "scope": "user",
    "enabled": true,
    "installPath": "/Users/example/.claude/plugins/cache/requirements-impact-refiner/requirements-impact-refiner/0.3.0",
    "installedAt": "2026-08-21T14:12:55.810Z",
    "lastUpdated": "2026-08-21T14:12:55.810Z"
  }
]"""


def make_request(root):
    return RunRequest(
        case=CaseSpec(
            id="POS-example",
            kind="positive",
            turns=(CaseTurn("Inspect this change.", ("src/example.py",)),),
            must_detect=("relevant impact",),
            must_not_do=("write implementation",),
            modes=("claude-code",),
        ),
        repetition=1,
        client="claude",
        model=None,
        reasoning=None,
        output_root=Path(root) / "raw",
    )


def write_fake_claude(
    directory,
    doctor_mode="success",
    version_text="claude 1.2.3-test",
    plugin_list_payload=None,
):
    if plugin_list_payload is None:
        plugin_list_payload = json.dumps(
            {"plugins": [{"id": "example-plugin", "enabled": True}]}
        )
    script = Path(directory) / "fake-claude.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys, time\n"
        "args = sys.argv[1:]\n"
        "log = os.environ.get('FAKE_CLAUDE_LOG')\n"
        "if log:\n"
        "    with open(log, 'a', encoding='utf-8') as handle:\n"
        "        handle.write(json.dumps(args) + '\\n')\n"
        "if args == ['--version']:\n"
        f"    print({version_text!r})\n"
        "elif args == ['doctor']:\n"
        f"    mode = {doctor_mode!r}\n"
        "    if mode == 'hang':\n"
        "        print('Sign in to continue', flush=True)\n"
        "        time.sleep(2)\n"
        "    else:\n"
        "        print('doctor ok')\n"
        "elif args == ['plugin', 'validate', '.']:\n"
        "    print('plugin valid')\n"
        "elif args == ['plugin', 'marketplace', 'list']:\n"
        "    print('marketplace empty')\n"
        "elif args == ['plugin', 'list', '--json']:\n"
        f"    print({plugin_list_payload!r})\n"
        "else:\n"
        "    print('unexpected arguments', file=sys.stderr)\n"
        "    sys.exit(2)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def write_hostile_claude(directory):
    script = Path(directory) / "claude"
    script.write_text(
        "#!/bin/sh\n"
        "printf escaped > \"$HOSTILE_CLAUDE_SENTINEL\"\n"
        "exit 99\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


class ClaudeAdapterTest(unittest.TestCase):
    def test_construction_requires_an_explicit_executable(self):
        """A default executable could silently resolve a host Claude installation."""
        with self.assertRaises(TypeError):
            ClaudeAdapter()

    def test_commands_never_authenticate_or_prompt_model(self):
        """Adding an interactive or auth argv would violate the paid-auth boundary."""
        with tempfile.TemporaryDirectory() as temporary:
            adapter = ClaudeAdapter(executable=str(write_fake_claude(temporary)))

            flattened = " ".join(
                argument for command in adapter.structural_commands(ROOT) for argument in command
            )

        self.assertNotIn("login", flattened)
        self.assertNotIn("auth", flattened)
        self.assertNotIn(" -p", " " + flattened)
        self.assertIn("plugin validate", flattened)

    def test_behavior_is_blocked(self):
        """Replacing the explicit boundary with a model call would spend paid credentials."""
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_claude(temporary)
            hostile_directory = Path(temporary) / "hostile"
            hostile_directory.mkdir()
            write_hostile_claude(hostile_directory)
            sentinel = Path(temporary) / "escaped.txt"
            previous_path = os.environ.get("PATH")
            previous_sentinel = os.environ.get("HOSTILE_CLAUDE_SENTINEL")
            os.environ["PATH"] = str(hostile_directory) + os.pathsep + (previous_path or "")
            os.environ["HOSTILE_CLAUDE_SENTINEL"] = str(sentinel)
            try:
                result = ClaudeAdapter(
                    executable=str(executable), cwd=Path(temporary)
                ).execute(make_request(temporary))
            finally:
                if previous_path is None:
                    del os.environ["PATH"]
                else:
                    os.environ["PATH"] = previous_path
                if previous_sentinel is None:
                    del os.environ["HOSTILE_CLAUDE_SENTINEL"]
                else:
                    os.environ["HOSTILE_CLAUDE_SENTINEL"] = previous_sentinel

        self.assertEqual(result.status, RunStatus.BLOCKED)
        self.assertEqual(result.reason, "paid authentication unavailable")
        self.assertIsNone(result.command)
        self.assertFalse(sentinel.exists())

    def test_probe_runs_each_structural_command_and_records_plugin_inventory(self):
        """Dropping a structural probe would hide an independently observable check."""
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_claude(temporary)
            log = Path(temporary) / "argv.jsonl"
            previous = os.environ.get("FAKE_CLAUDE_LOG")
            os.environ["FAKE_CLAUDE_LOG"] = str(log)
            try:
                adapter = ClaudeAdapter(executable=str(executable), cwd=Path(temporary))
                probe = adapter.probe()
            finally:
                if previous is None:
                    del os.environ["FAKE_CLAUDE_LOG"]
                else:
                    os.environ["FAKE_CLAUDE_LOG"] = previous

            commands = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

        self.assertTrue(probe.available)
        self.assertEqual(probe.version, "claude 1.2.3-test")
        self.assertEqual(probe.enabled_plugins, ("example-plugin",))
        self.assertEqual(
            commands,
            [
                ["--version"],
                ["doctor"],
                ["plugin", "validate", "."],
                ["plugin", "marketplace", "list"],
                ["plugin", "list", "--json"],
            ],
        )
        self.assertEqual(len(adapter.structural_results), 5)

    def test_probe_records_enabled_requirements_impact_refiner_version(self):
        """Leaving the installed plugin version unset hides the evaluated configuration."""
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_claude(
                temporary, plugin_list_payload=CLAUDE_PLUGIN_LIST_FIXTURE
            )
            probe = ClaudeAdapter(executable=str(executable), cwd=Path(temporary)).probe()

        self.assertEqual(probe.plugin_version, "0.3.0")
        self.assertEqual(
            probe.enabled_plugins,
            ("requirements-impact-refiner@requirements-impact-refiner",),
        )

    def test_doctor_timeout_blocks_only_doctor_probe(self):
        """Treating a timed-out doctor as a global failure would erase usable structure."""
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_claude(temporary, doctor_mode="hang")
            adapter = ClaudeAdapter(
                executable=str(executable), cwd=Path(temporary), doctor_timeout_seconds=0.01
            )
            probe = adapter.probe()

        self.assertTrue(probe.available)
        self.assertEqual(probe.enabled_plugins, ("example-plugin",))
        self.assertTrue(adapter.structural_results[1].timed_out)
        self.assertFalse(adapter.structural_results[0].timed_out)
        self.assertFalse(adapter.structural_results[4].timed_out)

    def test_blocked_execution_preserves_each_structural_result_separately(self):
        """Collapsing probe output into one artifact would lose command-level evidence."""
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_claude(temporary)
            request = make_request(temporary)
            result = ClaudeAdapter(
                executable=str(executable),
                cwd=Path(temporary),
                quarantine_root=Path(temporary) / "quarantine",
            ).execute(request)
            evidence = request.output_root / "claude" / request.case.id / "01"

            metadata = json.loads((evidence / "metadata.json").read_text(encoding="utf-8"))
            artifacts = {path.name for path in evidence.iterdir()}

        self.assertEqual(result.status, RunStatus.BLOCKED)
        self.assertEqual(len(metadata["probe_commands"]), 5)
        self.assertEqual(
            artifacts,
            {
                "version.stdout.txt", "version.stderr.txt",
                "doctor.stdout.txt", "doctor.stderr.txt",
                "plugin-validate.stdout.txt", "plugin-validate.stderr.txt",
                "marketplace-list.stdout.txt", "marketplace-list.stderr.txt",
                "plugin-list.stdout.txt", "plugin-list.stderr.txt",
                "metadata.json",
            },
        )

    def test_secret_structural_evidence_is_quarantined_and_blocks_the_result(self):
        """Ignoring a secret detector would publish credential-shaped probe output."""
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_claude(
                temporary, version_text="claude sk-ant-abcdefghijklmnopqrstuvwxyz"
            )
            request = make_request(temporary)
            quarantine_root = Path(temporary) / "quarantine"
            adapter = ClaudeAdapter(
                executable=str(executable),
                cwd=Path(temporary),
                quarantine_root=quarantine_root,
            )

            result = adapter.execute(request)

            self.assertEqual(result.status, RunStatus.BLOCKED)
            self.assertEqual(result.reason, "potential secret exposure")
            self.assertFalse(request.output_root.exists())
            self.assertEqual(len(adapter.structural_results), 5)
            quarantined = list(quarantine_root.rglob("version.stdout.txt"))

        self.assertEqual(len(quarantined), 1)

    def test_recording_failure_is_invalid_evidence_without_losing_probe_results(self):
        """Discarding recorder errors would falsely present incomplete evidence as usable."""
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_claude(temporary)
            request = make_request(temporary)
            adapter = ClaudeAdapter(
                executable=str(executable),
                cwd=Path(temporary),
                quarantine_root=Path(temporary) / "quarantine",
            )

            with patch(
                "evals.harness.adapters.claude.record_run", side_effect=OSError("disk full")
            ):
                result = adapter.execute(request)

            self.assertEqual(result.status, RunStatus.INVALID_EVIDENCE)
            self.assertEqual(result.reason, "evidence recording failed: disk full")
            self.assertEqual(len(adapter.structural_results), 5)


if __name__ == "__main__":
    unittest.main()
