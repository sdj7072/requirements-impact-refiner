import json
import os
import tempfile
import unittest
from pathlib import Path

from evals.harness.adapters.codex import CodexAdapter
from evals.harness.models import CaseSpec, CaseTurn, RunRequest, RunStatus


UUID = "123e4567-e89b-12d3-a456-426614174000"


def make_request(root, turns, model=None, reasoning=None):
    return RunRequest(
        case=CaseSpec(
            id="POS-example",
            kind="lineage" if len(turns) > 1 else "positive",
            turns=tuple(CaseTurn(prompt, ("src/example.py",)) for prompt in turns),
            must_detect=("relevant impact",),
            must_not_do=("write implementation",),
            modes=("codex",),
            expected_transition="unchanged" if len(turns) > 1 else None,
        ),
        repetition=1,
        client="codex",
        model=model,
        reasoning=reasoning,
        output_root=Path(root) / "raw",
    )


def write_fake_codex(directory, plugins=None, exec_mode="success"):
    plugins = plugins or [
        {
            "id": "requirements-impact-refiner",
            "name": "Requirements Impact Refiner",
            "version": "0.3.0",
            "enabled": True,
        },
        {"id": "superpowers", "name": "Superpowers", "version": "6.3.0", "enabled": True},
        {"id": "other-enabled", "name": "Other", "version": "1.0.0", "enabled": True},
        {"id": "disabled", "name": "Disabled", "version": "1.0.0", "enabled": False},
    ]
    script = Path(directory) / "fake-codex.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "log = os.environ.get('FAKE_CODEX_LOG')\n"
        "if log:\n"
        "    with open(log, 'a', encoding='utf-8') as handle:\n"
        "        handle.write(json.dumps(args) + '\\n')\n"
        "if args == ['--version']:\n"
        "    print('codex-cli 0.148.0-test')\n"
        "elif args == ['plugin', 'list', '--json']:\n"
        f"    print({json.dumps(json.dumps(plugins))})\n"
        "elif args and args[0] == 'exec':\n"
        f"    mode = {exec_mode!r}\n"
        "    if mode == 'nonzero':\n"
        "        print('{\\\"type\\\":\\\"thread.started\\\",\\\"thread_id\\\":\\\"" + UUID + "\\\"}')\n"
        "        print('client error', file=sys.stderr)\n"
        "        sys.exit(7)\n"
        "    if mode == 'malformed-jsonl':\n"
        "        print('not json')\n"
        "    elif mode == 'missing-thread':\n"
        "        print('{\\\"type\\\":\\\"item.completed\\\"}')\n"
        "    else:\n"
        "        print('{\\\"type\\\":\\\"thread.started\\\",\\\"thread_id\\\":\\\"" + UUID + "\\\"}')\n"
        "    if mode != 'missing-final':\n"
        "        output = args[args.index('-o') + 1]\n"
        "        with open(output, 'w', encoding='utf-8') as handle:\n"
        "            handle.write('final response')\n"
        "else:\n"
        "    print('unexpected arguments', file=sys.stderr)\n"
        "    sys.exit(2)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


class CodexAdapterTest(unittest.TestCase):
    def test_one_turn_is_ephemeral_and_omitted_model_stays_omitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            request = make_request(temporary, ("first turn",))
            adapter = CodexAdapter(cwd=Path(temporary))

            argv = adapter.build_first_turn_command(request, Path(temporary) / "FINAL")

        self.assertEqual(
            argv[:10],
            ("codex", "exec", "--ephemeral", "--json", "-s", "read-only", "--approve-for-me", "-o", str(Path(temporary) / "FINAL"), "first turn\n\nRepository evidence:\n- src/example.py"),
        )
        self.assertNotIn("-m", argv)
        self.assertNotIn("model_reasoning_effort", " ".join(argv))

    def test_selected_model_and_reasoning_are_run_local(self):
        with tempfile.TemporaryDirectory() as temporary:
            request = make_request(temporary, ("first turn",), "gpt-5.6-sol", "high")
            argv = CodexAdapter(cwd=Path(temporary)).build_first_turn_command(
                request, Path(temporary) / "FINAL"
            )

        self.assertIn("gpt-5.6-sol", argv)
        self.assertIn('model_reasoning_effort="high"', argv)
        self.assertEqual(argv.count("-m"), 1)
        self.assertEqual(argv.count("-c"), 1)

    def test_resume_uses_only_a_parsed_uuid(self):
        with tempfile.TemporaryDirectory() as temporary:
            request = make_request(temporary, ("first turn", "second turn"), "gpt-5.6-sol", "high")
            adapter = CodexAdapter(cwd=Path(temporary))
            thread_id = adapter.parse_thread_id(
                '{"type":"thread.started","thread_id":"' + UUID + '"}\n'
            )
            argv = adapter.build_resume_command(
                request, thread_id, "second turn", Path(temporary) / "FINAL"
            )

        self.assertEqual(thread_id, UUID)
        self.assertEqual(
            argv,
            ("codex", "exec", "resume", "--json", "-o", str(Path(temporary) / "FINAL"), UUID, "second turn\n\nRepository evidence:\n- src/example.py"),
        )
        self.assertNotIn("--last", argv)
        self.assertNotIn("-m", argv)
        self.assertNotIn("model_reasoning_effort", " ".join(argv))

    def test_parse_thread_id_rejects_non_thread_or_non_uuid_events(self):
        adapter = CodexAdapter()

        self.assertIsNone(adapter.parse_thread_id('{"type":"item.completed","thread_id":"' + UUID + '"}\n'))
        self.assertIsNone(adapter.parse_thread_id('{"type":"thread.started","thread_id":"not-a-uuid"}\n'))
        self.assertIsNone(adapter.parse_thread_id("not json\n"))

    def test_probe_requires_exact_enabled_composition_and_records_all_enabled_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary)
            probe = CodexAdapter(executable=str(executable), cwd=Path(temporary)).probe()

        self.assertTrue(probe.available)
        self.assertEqual(probe.version, "codex-cli 0.148.0-test")
        self.assertEqual(probe.plugin_version, "0.3.0")
        self.assertEqual(
            probe.enabled_plugins,
            ("requirements-impact-refiner", "superpowers", "other-enabled"),
        )
        self.assertIn("Codex with Superpowers", probe.capabilities)
        self.assertIsNone(probe.authenticated)

    def test_prepare_rejects_disabled_required_plugin(self):
        plugins = [
            {"id": "requirements-impact-refiner", "name": "Requirements Impact Refiner", "version": "0.3.0", "enabled": True},
            {"id": "superpowers", "name": "Superpowers", "version": "6.3.0", "enabled": False},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary, plugins)
            probe = CodexAdapter(executable=str(executable), cwd=Path(temporary)).prepare()

        self.assertFalse(probe.available)
        self.assertIn("enabled Superpowers", probe.reason)

    def test_execute_persists_single_turn_jsonl_final_and_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary)
            request = make_request(temporary, ("first turn",))
            adapter = CodexAdapter(
                executable=str(executable),
                cwd=Path(temporary),
                quarantine_root=Path(temporary) / "quarantine",
            )

            result = adapter.execute(request)
            evidence = request.output_root / "codex" / request.case.id / "01"

            self.assertEqual(result.status, RunStatus.PASS)
            self.assertEqual(result.final_output, "final response")
            self.assertIsNone(result.session_id)
            self.assertEqual(
                set(path.name for path in evidence.iterdir()),
                {"first.prompt.txt", "first.jsonl", "first.stderr.txt", "first.final.txt", "metadata.json"},
            )
            metadata = json.loads((evidence / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["environment"], "Codex with Superpowers")

    def test_execute_resumes_only_the_first_turn_uuid(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary)
            log = Path(temporary) / "argv.jsonl"
            request = make_request(temporary, ("first turn", "second turn"), "gpt-5.6-sol", "high")
            adapter = CodexAdapter(
                executable=str(executable),
                cwd=Path(temporary),
                quarantine_root=Path(temporary) / "quarantine",
            )
            original_log = os.environ.get("FAKE_CODEX_LOG")
            os.environ["FAKE_CODEX_LOG"] = str(log)
            try:
                result = adapter.execute(request)
            finally:
                if original_log is None:
                    del os.environ["FAKE_CODEX_LOG"]
                else:
                    os.environ["FAKE_CODEX_LOG"] = original_log

            commands = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

        execution_commands = [command for command in commands if command[0] == "exec"]
        self.assertEqual(result.status, RunStatus.PASS)
        self.assertEqual(result.session_id, UUID)
        self.assertNotIn("--ephemeral", execution_commands[0])
        self.assertEqual(execution_commands[1][0:2], ["exec", "resume"])
        self.assertIn(UUID, execution_commands[1])
        self.assertNotIn("--last", execution_commands[1])

    def test_execute_classifies_bad_client_output_as_preserved_infra_error(self):
        for mode, reason in (
            ("nonzero", "nonzero exit"),
            ("malformed-jsonl", "malformed JSONL"),
            ("missing-final", "missing final output"),
        ):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                executable = write_fake_codex(temporary, exec_mode=mode)
                request = make_request(temporary, ("first turn",))
                result = CodexAdapter(
                    executable=str(executable),
                    cwd=Path(temporary),
                    quarantine_root=Path(temporary) / "quarantine",
                ).execute(request)
                evidence = request.output_root / "codex" / request.case.id / "01"

                self.assertEqual(result.status, RunStatus.INFRA_ERROR)
                self.assertIn(reason, result.reason)
                self.assertTrue(evidence.is_dir())
                self.assertTrue((evidence / "first.jsonl").is_file())

    def test_execute_requires_thread_started_for_a_multi_turn_case(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary, exec_mode="missing-thread")
            request = make_request(temporary, ("first turn", "second turn"))
            result = CodexAdapter(
                executable=str(executable),
                cwd=Path(temporary),
                quarantine_root=Path(temporary) / "quarantine",
            ).execute(request)

        self.assertEqual(result.status, RunStatus.INFRA_ERROR)
        self.assertEqual(result.reason, "missing thread.started UUID")


if __name__ == "__main__":
    unittest.main()
