import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evals.harness.adapters.codex import CodexAdapter
from evals.harness.graph_scoring import load_graph_cases
from evals.harness.models import (
    CaseSpec, CaseTurn, ClientProbe, RunRequest, RunStatus,
)


UUID = "123e4567-e89b-12d3-a456-426614174000"
COMPACT_PREDECESSOR_HANDOFF = (
    "Harness continuity evidence:\n"
    "- In compact delivery, read `.requirements-impact-refiner/reports/RPT-###/current.json` and hash the exact canonical Markdown file it selects.\n"
    "- `first.final.txt` is the chat response, not canonical lineage bytes, unless no persisted report exists and it is itself a complete canonical report.\n"
    "- Do not reconstruct predecessor bytes from conversation text or add, remove, or normalize bytes."
)
INSTALLED_PLUGIN_LIST = {
    "installed": [
        {
            "pluginId": "requirements-impact-refiner@requirements-impact-refiner",
            "name": "Requirements Impact Refiner",
            "marketplaceName": "personal-marketplace",
            "version": "0.3.0",
            "installed": True,
            "enabled": True,
            "source": "marketplace",
            "installPolicy": "user",
            "authPolicy": "none",
        },
        {
            "pluginId": "superpowers@openai-curated",
            "name": "Superpowers",
            "marketplaceName": "openai-curated-remote",
            "version": "6.3.0",
            "installed": True,
            "enabled": True,
            "source": "marketplace",
            "installPolicy": "user",
            "authPolicy": "none",
        },
        {
            "pluginId": "other-enabled",
            "name": "Other",
            "marketplaceName": "openai-curated-remote",
            "version": "1.0.0",
            "installed": True,
            "enabled": True,
            "source": "marketplace",
            "installPolicy": "user",
            "authPolicy": "none",
        },
        {
            "pluginId": "disabled",
            "name": "Disabled",
            "marketplaceName": "personal-marketplace",
            "version": "1.0.0",
            "installed": True,
            "enabled": False,
            "source": "marketplace",
            "installPolicy": "user",
            "authPolicy": "none",
        },
    ],
    "available": [],
}


def make_request(root, turns, model=None, reasoning=None, evidence=None):
    evidence = evidence or tuple(("src/example.py",) for _ in turns)
    return RunRequest(
        case=CaseSpec(
            id="POS-example",
            kind="lineage" if len(turns) > 1 else "positive",
            turns=tuple(
                CaseTurn(prompt, turn_evidence)
                for prompt, turn_evidence in zip(turns, evidence)
            ),
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
            "id": "requirements-impact-refiner@requirements-impact-refiner",
            "name": "Requirements Impact Refiner",
            "version": "0.3.0",
            "enabled": True,
        },
        {"id": "superpowers@openai-curated", "name": "Superpowers", "version": "6.3.0", "enabled": True},
        {"id": "other-enabled", "name": "Other", "version": "1.0.0", "enabled": True},
        {"id": "disabled", "name": "Disabled", "version": "1.0.0", "enabled": False},
    ]
    script = Path(directory) / "fake-codex.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import hashlib, json, os, sys\n"
        "args = sys.argv[1:]\n"
        "log = os.environ.get('FAKE_CODEX_LOG')\n"
        "cwd_log = os.environ.get('FAKE_CODEX_CWD_LOG')\n"
        "if log:\n"
        "    with open(log, 'a', encoding='utf-8') as handle:\n"
        "        handle.write(json.dumps(args) + '\\n')\n"
        "if args == ['--version']:\n"
        "    print('codex-cli 0.148.0-test')\n"
        "elif args == ['plugin', 'list', '--json']:\n"
        f"    print({json.dumps(json.dumps(plugins))})\n"
        "elif args and args[0] == 'exec':\n"
        f"    mode = {exec_mode!r}\n"
        "    if cwd_log:\n"
        "        with open(cwd_log, 'a', encoding='utf-8') as handle:\n"
        "            handle.write(json.dumps({'args': args, 'cwd': os.getcwd()}) + '\\n')\n"
        "    if mode == 'require-isolated-cwd':\n"
        "        if os.path.exists('HARNESS_REPOSITORY_MARKER') or os.path.exists('synthetic-secret-fixture'):\n"
        "            print('repository fixture visible to model execution', file=sys.stderr)\n"
        "            sys.exit(23)\n"
        "        if '--skip-git-repo-check' not in args:\n"
        "            print('missing isolated-workspace execution flag', file=sys.stderr)\n"
        "            sys.exit(24)\n"
        "    if mode == 'require-predecessor-file' and args[0:2] == ['exec', 'resume']:\n"
        "        if not os.path.isfile('first.final.txt'):\n"
        "            print('missing exact predecessor artifact', file=sys.stderr)\n"
        "            sys.exit(25)\n"
        "    if mode == 'write-compact-report':\n"
        "        report_dir = os.path.join('.requirements-impact-refiner', 'reports', 'RPT-001')\n"
        "        os.makedirs(report_dir, exist_ok=True)\n"
        "        with open(os.path.join(report_dir, 'revision-0001.json'), 'w', encoding='utf-8') as handle:\n"
        "            handle.write('{\"schema_version\":1}\\n')\n"
        "        with open(os.path.join(report_dir, 'revision-0001.md'), 'w', encoding='utf-8') as handle:\n"
        "            handle.write('# Requirements Impact Report\\n')\n"
        "        with open(os.path.join(report_dir, 'current.json'), 'w', encoding='utf-8') as handle:\n"
        "            handle.write('{\"revision\":1}\\n')\n"
        "    if mode == 'symlink-compact-report':\n"
        "        os.makedirs('.requirements-impact-refiner', exist_ok=True)\n"
        "        os.symlink('/tmp', os.path.join('.requirements-impact-refiner', 'reports'))\n"
        "    if mode == 'reject-readonly-approval' and '-s' in args and 'read-only' in args and '--approve-for-me' in args:\n"
        "        print('error: --sandbox and --approve-for-me cannot be used together', file=sys.stderr)\n"
        "        sys.exit(2)\n"
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
        "        if mode == 'controller-success':\n"
        "            draft = '0123456789abcdef0123456789abcdef'\n"
        "            receipt = 'fedcba9876543210fedcba9876543210'\n"
        "            graph_dir = os.path.join('.requirements-impact-refiner', 'graph')\n"
        "            os.makedirs(graph_dir, exist_ok=True)\n"
        "            receipt_payload = b'{}\\n'\n"
        "            with open(os.path.join(graph_dir, draft + '.json'), 'wb') as handle:\n"
        "                handle.write(receipt_payload)\n"
        "            begin = {'type': 'item.completed', 'item': {'id': 'begin', 'type': 'mcp_tool_call', 'server': 'requirements-impact-refiner', 'tool': 'rir_begin', 'arguments': {'repo_root': os.getcwd()}, 'result': {'content': [], 'structured_content': {'draft_id': draft, 'installed_payload_sha256': 'a' * 64}}, 'error': None, 'status': 'completed'}}\n"
        "            trace = {'type': 'item.completed', 'item': {'id': 'trace', 'type': 'mcp_tool_call', 'server': 'requirements-impact-refiner', 'tool': 'rir_trace_impact', 'arguments': {'repo_root': os.getcwd(), 'draft_id': draft, 'seeds': []}, 'result': {'content': [], 'structured_content': {'receipt_id': receipt, 'receipt_path': '.requirements-impact-refiner/graph/' + draft + '.json', 'receipt_sha256': hashlib.sha256(receipt_payload).hexdigest(), 'compact_graph': {'providers': [], 'nodes': [], 'edges': [], 'paths': [], 'frontier': [], 'timings_ms': {'total': 1}, 'budget_status': 'closed'}, 'budget_status': 'closed', 'request_sha256': 'c' * 64, 'seeds': []}}, 'error': None, 'status': 'completed'}}\n"
        "            finalize = {'type': 'item.completed', 'item': {'id': 'finalize', 'type': 'mcp_tool_call', 'server': 'requirements-impact-refiner', 'tool': 'rir_finalize', 'arguments': {'repo_root': os.getcwd(), 'draft_id': draft, 'graph_receipt_id': receipt, 'analysis': {}}, 'result': {'content': [{'type': 'text', 'text': 'final response'}], 'structured_content': {'status': 'published', 'display_text': 'final response'}}, 'error': None, 'status': 'completed'}}\n"
        "            print(json.dumps(begin))\n"
        "            print(json.dumps(trace))\n"
        "            print(json.dumps(finalize))\n"
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
    def test_graph_case_fixture_is_staged_inside_isolated_workspace(self):
        case = load_graph_cases()[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            CodexAdapter._stage_graph_fixture(case.id, root)

            self.assertEqual(
                (root / "api/profile.py").read_text(encoding="utf-8"),
                dict(case.fixture_files)["api/profile.py"],
            )
            settings = json.loads(
                (root / ".requirements-impact-refiner.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(settings["impact_graph"]["providers"], ["builtin"])
            self.assertEqual(settings["impact_graph"]["max_seconds"], 30)
            self.assertEqual(settings["impact_graph"]["target_seconds"], 10)
            self.assertEqual(settings["impact_graph"]["install_policy"], "never")

    def test_graph_case_policy_is_sealed_in_raw_run_metadata(self):
        case = load_graph_cases()[0]
        request = RunRequest(
            case.to_case_spec(), 1, "codex", None, None, Path("raw")
        )
        probe = ClientProbe(
            client="codex", available=True, version="fake",
            authenticated=None, plugin_version="0.4.0",
            enabled_plugins=(
                "requirements-impact-refiner@requirements-impact-refiner",
                "superpowers@openai-curated",
            ),
            capabilities=("fake",), reason=None,
        )

        metadata = json.loads(
            CodexAdapter._metadata_json(probe, (), (), request)
        )

        self.assertEqual(metadata["graph_policy"], {
            "schema_version": 1,
            "settings": {
                "enabled": True, "max_seconds": 30, "target_seconds": 10,
                "providers": ["builtin"], "install_policy": "never",
                "deep": False,
            },
            "provider_inventory": ["builtin"],
            "seeds": [
                {"term": term, "location": location}
                for term, location in case.seeds
            ],
        })

    def test_graph_fixture_staging_never_follows_settings_or_parent_symlinks(self):
        case = load_graph_cases()[0]
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside_settings = base / "outside-settings.json"
            outside_settings.write_text("outside-safe", encoding="utf-8")
            settings_root = base / "settings-root"
            settings_root.mkdir()
            os.symlink(
                outside_settings,
                settings_root / ".requirements-impact-refiner.json",
            )
            with self.assertRaisesRegex(ValueError, "overwrite|symlink|unsafe"):
                CodexAdapter._stage_graph_fixture(case.id, settings_root)
            self.assertEqual(
                outside_settings.read_text(encoding="utf-8"), "outside-safe"
            )

            outside_directory = base / "outside-directory"
            outside_directory.mkdir()
            parent_root = base / "parent-root"
            parent_root.mkdir()
            os.symlink(outside_directory, parent_root / "api")
            with self.assertRaisesRegex(ValueError, "overwrite|symlink|unsafe"):
                CodexAdapter._stage_graph_fixture(case.id, parent_root)
            self.assertFalse((outside_directory / "profile.py").exists())

    def test_graph_receipts_are_captured_as_raw_regular_files_and_symlinks_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph = root / ".requirements-impact-refiner/graph"
            graph.mkdir(parents=True)
            receipt = graph / ("a" * 32 + ".json")
            receipt.write_bytes(b"exact-receipt\n")
            artifacts = {}

            self.assertIsNone(CodexAdapter._capture_workspace_graph(artifacts, root))
            self.assertEqual(
                artifacts[f"workspace-graph/{'a' * 32}.json"],
                b"exact-receipt\n",
            )

            receipt.unlink()
            os.symlink(root / "outside", receipt)
            self.assertIn(
                "must not use symlinks",
                CodexAdapter._capture_workspace_graph({}, root),
            )

    def test_graph_receipt_capture_rejects_output_flood_and_malicious_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph = root / ".requirements-impact-refiner/graph"
            graph.mkdir(parents=True)
            oversized = graph / ("a" * 32 + ".json")
            oversized.write_bytes(b"x" * (1_048_576 + 1))

            self.assertIn(
                "maximum byte size",
                CodexAdapter._capture_workspace_graph({}, root),
            )

            oversized.unlink()
            (graph / "..malicious.json").write_text("{}", encoding="utf-8")
            self.assertIn(
                "name is invalid",
                CodexAdapter._capture_workspace_graph({}, root),
            )

    def test_graph_receipt_capture_is_descriptor_bound_across_parent_replacements(self):
        for boundary in ("workspace-base", "base-graph"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "workspace"
                graph = root / ".requirements-impact-refiner/graph"
                graph.mkdir(parents=True)
                receipt_name = "a" * 32 + ".json"
                (graph / receipt_name).write_bytes(b"inside-receipt")
                outside_base = Path(temporary) / "outside-base"
                outside_graph = Path(temporary) / "outside-graph"
                (outside_base / "graph").mkdir(parents=True)
                outside_graph.mkdir()
                (outside_base / "graph" / receipt_name).write_bytes(
                    b"outside-base-receipt"
                )
                (outside_graph / receipt_name).write_bytes(
                    b"outside-graph-receipt"
                )
                saved = Path(temporary) / f"saved-{boundary}"
                real_open = os.open
                raced = False

                def racing_open(path, flags, *args, **kwargs):
                    nonlocal raced
                    selected = os.fspath(path)
                    if not raced and boundary == "workspace-base" and (
                        selected == os.fspath(graph)
                        or selected == ".requirements-impact-refiner"
                    ):
                        raced = True
                        os.rename(root / ".requirements-impact-refiner", saved)
                        os.symlink(outside_base, root / ".requirements-impact-refiner")
                    elif not raced and boundary == "base-graph" and (
                        selected == os.fspath(graph) or selected == "graph"
                    ):
                        raced = True
                        os.rename(graph, saved)
                        os.symlink(outside_graph, graph)
                    return real_open(path, flags, *args, **kwargs)

                artifacts = {}
                with patch(
                    "evals.harness.adapters.codex.os.open",
                    side_effect=racing_open,
                ):
                    problem = CodexAdapter._capture_workspace_graph(artifacts, root)

                self.assertTrue(raced)
                self.assertIn("capture failed", problem)
                self.assertEqual(artifacts, {})
                if boundary == "workspace-base":
                    self.assertEqual(
                        (saved / "graph" / receipt_name).read_bytes(),
                        b"inside-receipt",
                    )
                else:
                    self.assertEqual(
                        (saved / receipt_name).read_bytes(), b"inside-receipt"
                    )

    def test_v04_run_records_and_enforces_controller_trace(self):
        plugins = [
            {"id": "requirements-impact-refiner@requirements-impact-refiner", "name": "Requirements Impact Refiner", "version": "0.4.0", "enabled": True},
            {"id": "superpowers@openai-curated", "name": "Superpowers", "version": "6.3.0", "enabled": True},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary, plugins=plugins, exec_mode="controller-success")
            request = make_request(temporary, ("first turn",))
            adapter = CodexAdapter(executable=str(executable), cwd=Path(temporary), expected_plugin_version="0.4.0")

            result = adapter.execute(request)
            evidence_path = request.output_root / "codex" / "POS-example" / "01" / "controller-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

        self.assertEqual(result.status, RunStatus.PASS)
        self.assertTrue(evidence["valid"])
        self.assertEqual(
            evidence["tool_order"],
            ["rir_begin", "rir_trace_impact", "rir_finalize"],
        )
        self.assertEqual(evidence["trace_calls"], 1)
        self.assertTrue(evidence["trace_succeeded"])
        self.assertTrue(evidence["finalize_receipt_ids_match"])
        self.assertTrue(evidence["display_text_exact_match"])
        self.assertTrue(evidence["display_text_presentation_equivalent"])
        self.assertEqual(evidence["display_comparison"], "codex-markdown-v1")

    def test_v04_run_without_controller_is_invalid_evidence(self):
        plugins = [
            {"id": "requirements-impact-refiner@requirements-impact-refiner", "name": "Requirements Impact Refiner", "version": "0.4.0", "enabled": True},
            {"id": "superpowers@openai-curated", "name": "Superpowers", "version": "6.3.0", "enabled": True},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary, plugins=plugins)
            request = make_request(temporary, ("first turn",))
            adapter = CodexAdapter(executable=str(executable), cwd=Path(temporary), expected_plugin_version="0.4.0")

            result = adapter.execute(request)

        self.assertEqual(result.status, RunStatus.INVALID_EVIDENCE)
        self.assertEqual(result.reason, "controller evidence invalid")
        self.assertIsNone(result.final_output)

    def test_one_turn_is_ephemeral_and_omitted_model_stays_omitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            request = make_request(temporary, ("first turn",))
            adapter = CodexAdapter(cwd=Path(temporary))

            argv = adapter.build_first_turn_command(request, Path(temporary) / "FINAL")

        self.assertEqual(
            argv[:9],
            ("codex", "exec", "--ephemeral", "--json", "--skip-git-repo-check", "--approve-for-me", "-o", str(Path(temporary) / "FINAL"), "first turn\n\nRepository evidence:\n- src/example.py"),
        )
        self.assertNotIn("-s", argv)
        self.assertIn("--approve-for-me", argv)
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
                request, thread_id, request.case.turns[1], Path(temporary) / "FINAL"
            )

        self.assertEqual(thread_id, UUID)
        self.assertEqual(
            argv,
            (
                "codex",
                "exec",
                "resume",
                "--json",
                "--skip-git-repo-check",
                "-o",
                str(Path(temporary) / "FINAL"),
                UUID,
                "second turn\n\nRepository evidence:\n- src/example.py\n\n"
                + COMPACT_PREDECESSOR_HANDOFF,
            ),
        )
        self.assertNotIn("--last", argv)
        self.assertNotIn("-m", argv)
        self.assertNotIn("model_reasoning_effort", " ".join(argv))

    def test_resume_rejects_raw_prompt_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            request = make_request(temporary, ("first turn", "second turn"))
            adapter = CodexAdapter(cwd=Path(temporary))

            with self.assertRaisesRegex(TypeError, "CaseTurn"):
                adapter.build_resume_command(
                    request, UUID, "second turn", Path(temporary) / "FINAL"
                )

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
            (
                "requirements-impact-refiner@requirements-impact-refiner",
                "superpowers@openai-curated",
                "other-enabled",
            ),
        )
        self.assertIn("Codex with Superpowers", probe.capabilities)
        self.assertIsNone(probe.authenticated)

    def test_probe_parses_real_installed_inventory_and_plugin_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary, INSTALLED_PLUGIN_LIST)
            probe = CodexAdapter(executable=str(executable), cwd=Path(temporary)).probe()

        self.assertTrue(probe.available)
        self.assertEqual(probe.plugin_version, "0.3.0")
        self.assertEqual(
            probe.enabled_plugins,
            (
                "requirements-impact-refiner@requirements-impact-refiner",
                "superpowers@openai-curated",
                "other-enabled",
            ),
        )

    def test_probe_accepts_an_explicit_expected_v031_plugin_version(self):
        """A 0.3.1 smoke must not be rejected by the historical 0.3.0 gate."""
        plugins = [dict(entry) for entry in INSTALLED_PLUGIN_LIST["installed"]]
        plugins[0]["version"] = "0.3.1"
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary, {"installed": plugins, "available": []})
            probe = CodexAdapter(
                executable=str(executable), cwd=Path(temporary), expected_plugin_version="0.3.1"
            ).probe()

        self.assertTrue(probe.available)
        self.assertEqual(probe.plugin_version, "0.3.1")

    def test_probe_fails_closed_when_observed_version_differs_from_expected_version(self):
        """Treating a different installed release as eligible would invalidate smoke provenance."""
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary)
            probe = CodexAdapter(
                executable=str(executable), cwd=Path(temporary), expected_plugin_version="0.3.1"
            ).probe()

        self.assertFalse(probe.available)
        self.assertEqual(probe.plugin_version, "0.3.0")
        self.assertIn("0.3.1", probe.reason)

    def test_probe_rejects_required_display_names_with_wrong_plugin_ids(self):
        """A display name must not impersonate either required plugin identity."""
        mutations = (
            (
                {"id": "wrong-rir@market", "name": "Requirements Impact Refiner", "version": "0.3.0", "enabled": True},
                {"id": "superpowers@openai-curated", "name": "Superpowers", "version": "6.3.0", "enabled": True},
            ),
            (
                {"id": "requirements-impact-refiner@requirements-impact-refiner", "name": "Requirements Impact Refiner", "version": "0.3.0", "enabled": True},
                {"id": "wrong-superpowers@market", "name": "Superpowers", "version": "6.3.0", "enabled": True},
            ),
        )
        for plugins in mutations:
            with self.subTest(ids=[entry["id"] for entry in plugins]), tempfile.TemporaryDirectory() as temporary:
                executable = write_fake_codex(temporary, list(plugins))
                probe = CodexAdapter(
                    executable=str(executable), cwd=Path(temporary)
                ).probe()
                self.assertFalse(probe.available)

    def test_probe_accepts_an_alias_only_when_its_exact_id_is_explicitly_expected(self):
        """An evaluation alias must be opt-in and remain visible in inventory."""
        alias_id = "requirements-impact-refiner@requirements-impact-refiner-v031-eval"
        plugins = [dict(entry) for entry in INSTALLED_PLUGIN_LIST["installed"]]
        plugins[0]["pluginId"] = alias_id
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(
                temporary, {"installed": plugins, "available": []}
            )
            default_probe = CodexAdapter(
                executable=str(executable), cwd=Path(temporary)
            ).probe()
            explicit_probe = CodexAdapter(
                executable=str(executable),
                cwd=Path(temporary),
                expected_rir_plugin_id=alias_id,
            ).probe()

        self.assertFalse(default_probe.available)
        self.assertTrue(explicit_probe.available)
        self.assertIn(alias_id, explicit_probe.enabled_plugins)

    def test_prepare_rejects_disabled_required_plugin(self):
        plugins = [
            {"id": "requirements-impact-refiner@requirements-impact-refiner", "name": "Requirements Impact Refiner", "version": "0.3.0", "enabled": True},
            {"id": "superpowers@openai-curated", "name": "Superpowers", "version": "6.3.0", "enabled": False},
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

    def test_execute_captures_compact_report_artifacts_before_workspace_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary, exec_mode="write-compact-report")
            request = make_request(temporary, ("first turn",))
            adapter = CodexAdapter(
                executable=str(executable),
                cwd=Path(temporary),
                quarantine_root=Path(temporary) / "quarantine",
            )

            result = adapter.execute(request)
            evidence = request.output_root / "codex" / request.case.id / "01"

            self.assertEqual(result.status, RunStatus.PASS)
            self.assertEqual(
                (evidence / "workspace-reports/RPT-001/revision-0001.json").read_text(),
                '{"schema_version":1}\n',
            )
            self.assertEqual(
                (evidence / "workspace-reports/RPT-001/revision-0001.md").read_text(),
                "# Requirements Impact Report\n",
            )
            self.assertEqual(
                (evidence / "workspace-reports/RPT-001/current.json").read_text(),
                '{"revision":1}\n',
            )

    def test_execute_classifies_unsafe_workspace_report_as_infrastructure_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary, exec_mode="symlink-compact-report")
            request = make_request(temporary, ("first turn",))
            adapter = CodexAdapter(
                executable=str(executable),
                cwd=Path(temporary),
                quarantine_root=Path(temporary) / "quarantine",
            )

            result = adapter.execute(request)

        self.assertEqual(result.status, RunStatus.INFRA_ERROR)
        self.assertIn("workspace report capture failed", result.reason)

    def test_execute_returns_exact_structured_provenance_from_probe_and_argv(self):
        """A future sealed final must carry all provenance used for promotion."""
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary)
            request = make_request(
                temporary, ("first turn",), "gpt-5.6-sol", "high"
            )
            result = CodexAdapter(
                executable=str(executable),
                cwd=Path(temporary),
                quarantine_root=Path(temporary) / "quarantine",
            ).execute(request)

        self.assertEqual(
            dict(result.metadata),
            {
                "environment": "Codex with Superpowers",
                "client_version": "codex-cli 0.148.0-test",
                "plugin_version": "0.3.0",
                "enabled_composition": (
                    "codex codex-cli 0.148.0-test plugins="
                    "other-enabled,requirements-impact-refiner@requirements-impact-refiner,"
                    "superpowers@openai-curated"
                ),
                "enabled_plugins": (
                    "other-enabled,requirements-impact-refiner@requirements-impact-refiner,"
                    "superpowers@openai-curated"
                ),
                "model": "gpt-5.6-sol",
                "reasoning": "high",
            },
        )

    def test_execute_rejects_model_or_reasoning_not_present_in_actual_argv(self):
        """Request fields alone cannot prove which model options the client executed."""
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary)
            request = make_request(
                temporary, ("first turn",), "gpt-5.6-sol", "high"
            )
            adapter = CodexAdapter(
                executable=str(executable),
                cwd=Path(temporary),
                quarantine_root=Path(temporary) / "quarantine",
            )
            original = adapter.build_first_turn_command

            def omit_run_options(run_request, final_path):
                argv = list(original(run_request, final_path))
                model_index = argv.index("-m")
                del argv[model_index : model_index + 2]
                reasoning_index = argv.index("-c")
                del argv[reasoning_index : reasoning_index + 2]
                return tuple(argv)

            adapter.build_first_turn_command = omit_run_options
            result = adapter.execute(request)

        self.assertEqual(result.status, RunStatus.INVALID_EVIDENCE)
        self.assertIn("run options disagree with execution argv", result.reason)

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
            persisted_second_prompt = (
                request.output_root / "codex" / request.case.id / "01" / "second.prompt.txt"
            ).read_text(encoding="utf-8")

        execution_commands = [command for command in commands if command[0] == "exec"]
        self.assertEqual(result.status, RunStatus.PASS)
        self.assertEqual(result.session_id, UUID)
        self.assertNotIn("--ephemeral", execution_commands[0])
        self.assertNotIn("-s", execution_commands[0])
        self.assertIn("--approve-for-me", execution_commands[0])
        self.assertEqual(execution_commands[1][0:2], ["exec", "resume"])
        self.assertIn(UUID, execution_commands[1])
        self.assertNotIn("--last", execution_commands[1])

    def test_execute_isolates_each_case_workspace_and_cleans_it_after_capture(self):
        """Model execution cannot inspect harness fixtures through its working directory."""
        with tempfile.TemporaryDirectory() as temporary:
            harness = Path(temporary) / "harness"
            harness.mkdir()
            (harness / "HARNESS_REPOSITORY_MARKER").write_text("marker", encoding="utf-8")
            (harness / "synthetic-secret-fixture").write_text(
                "test-only-secret-shaped-fixture", encoding="utf-8"
            )
            executable = write_fake_codex(harness, exec_mode="require-isolated-cwd")
            cwd_log = Path(temporary) / "execution-cwds.jsonl"
            multi_turn = make_request(Path(temporary) / "case-one", ("first turn", "second turn"))
            one_turn = make_request(Path(temporary) / "case-two", ("other case",))
            adapter = CodexAdapter(
                executable=str(executable),
                cwd=harness,
                quarantine_root=Path(temporary) / "quarantine",
            )
            original_cwd_log = os.environ.get("FAKE_CODEX_CWD_LOG")
            os.environ["FAKE_CODEX_CWD_LOG"] = str(cwd_log)
            try:
                multi_turn_result = adapter.execute(multi_turn)
                one_turn_result = adapter.execute(one_turn)
            finally:
                if original_cwd_log is None:
                    del os.environ["FAKE_CODEX_CWD_LOG"]
                else:
                    os.environ["FAKE_CODEX_CWD_LOG"] = original_cwd_log

            executions = [
                json.loads(line)
                for line in cwd_log.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(multi_turn_result.status, RunStatus.PASS)
        self.assertEqual(one_turn_result.status, RunStatus.PASS)
        self.assertEqual(len(executions), 3)
        first_workspace = Path(executions[0]["cwd"])
        self.assertEqual(first_workspace, Path(executions[1]["cwd"]))
        self.assertNotEqual(first_workspace, Path(executions[2]["cwd"]))
        self.assertNotEqual(first_workspace, harness)
        self.assertNotEqual(Path(executions[2]["cwd"]), harness)
        self.assertTrue(all("--skip-git-repo-check" in execution["args"] for execution in executions))
        self.assertFalse(first_workspace.exists())
        self.assertFalse(Path(executions[2]["cwd"]).exists())

    def test_execute_uses_automatic_review_without_conflicting_sandbox_flag(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary, exec_mode="reject-readonly-approval")
            log = Path(temporary) / "argv.jsonl"
            request = make_request(temporary, ("first turn",))
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

        execution_command = next(command for command in commands if command[0] == "exec")
        self.assertEqual(result.status, RunStatus.PASS)
        self.assertNotIn("-s", execution_command)
        self.assertNotIn("workspace-write", execution_command)
        self.assertIn("--approve-for-me", execution_command)

    def test_resume_appends_handoff_after_exact_second_turn_request_and_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            request = make_request(
                temporary,
                ("same prompt", "same prompt"),
                evidence=(("first.py",), ("second.py",)),
            )
            supplied_turn = CaseTurn("same prompt", ("supplied.py",))
            argv = CodexAdapter(cwd=Path(temporary)).build_resume_command(
                request,
                UUID,
                supplied_turn,
                Path(temporary) / "FINAL",
            )

        self.assertEqual(
            argv[-1],
            "same prompt\n\nRepository evidence:\n- supplied.py\n\n"
            + COMPACT_PREDECESSOR_HANDOFF,
        )
        self.assertNotIn("must_detect", argv[-1])
        self.assertNotIn("must_not_do", argv[-1])
        self.assertNotIn("expected_transition", argv[-1])
        self.assertNotIn("relevant impact", argv[-1])
        self.assertNotIn("write implementation", argv[-1])

    def test_execute_uses_the_second_turn_evidence_when_prompts_are_identical(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary)
            log = Path(temporary) / "argv.jsonl"
            request = make_request(
                temporary,
                ("same prompt", "same prompt"),
                evidence=(("first.py",), ("second.py",)),
            )
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
            persisted_second_prompt = (
                request.output_root / "codex" / request.case.id / "01" / "second.prompt.txt"
            ).read_text(encoding="utf-8")

        execution_commands = [command for command in commands if command[0] == "exec"]
        self.assertEqual(result.status, RunStatus.PASS)
        self.assertEqual(
            execution_commands[1][-1],
            "same prompt\n\nRepository evidence:\n- second.py\n\n"
            + COMPACT_PREDECESSOR_HANDOFF,
        )
        self.assertEqual(persisted_second_prompt, execution_commands[1][-1])
        self.assertEqual(persisted_second_prompt.count("Harness continuity evidence:"), 1)

    def test_execute_leaves_exact_first_final_artifact_for_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = write_fake_codex(temporary, exec_mode="require-predecessor-file")
            request = make_request(temporary, ("first turn", "second turn"))
            result = CodexAdapter(
                executable=str(executable),
                cwd=Path(temporary),
                quarantine_root=Path(temporary) / "quarantine",
            ).execute(request)

        self.assertEqual(result.status, RunStatus.PASS)

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
