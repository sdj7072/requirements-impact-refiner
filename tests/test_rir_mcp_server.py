import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts" / "rir_mcp_server.py"
FIXTURES = ROOT / "tests" / "fixtures"


def request(identifier, method, params):
    return {"jsonrpc": "2.0", "id": identifier, "method": method, "params": params}


class RirMcpServerTest(unittest.TestCase):
    def write_graph_config(self, root, enabled):
        (root / ".requirements-impact-refiner.json").write_text(
            json.dumps(
                {
                    "impact_graph": {
                        "enabled": enabled,
                        "max_seconds": 30,
                        "target_seconds": 10,
                        "providers": ["builtin"],
                        "install_policy": "never",
                        "deep": False,
                    }
                }
            ),
            encoding="utf-8",
        )

    def exchange(self, messages):
        payload = "".join(json.dumps(message) + "\n" for message in messages)
        result = subprocess.run(
            [sys.executable, str(SERVER)],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines() if line]

    def test_tools_list_exposes_only_controller_tools(self):
        replies = self.exchange(
            [
                request(
                    1,
                    "initialize",
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                ),
                request(2, "tools/list", {}),
            ]
        )

        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(
            [tool["name"] for tool in replies[1]["result"]["tools"]],
            ["rir_scan", "rir_begin", "rir_trace_impact", "rir_finalize"],
        )
        for tool in replies[1]["result"]["tools"]:
            self.assertEqual(tool["inputSchema"]["additionalProperties"], False)
            self.assertIn("local", tool["description"].lower())
            self.assertIn("network", tool["description"].lower())
        scan_schema = replies[1]["result"]["tools"][0]["inputSchema"]
        self.assertEqual(scan_schema["required"], ["repo_root", "change_request"])
        trace_schema = replies[1]["result"]["tools"][2]["inputSchema"]
        self.assertEqual(
            trace_schema["properties"]["seeds"]["items"]["additionalProperties"], False
        )
        self.assertEqual(
            trace_schema["properties"]["seeds"]["items"]["required"],
            ["term", "location"],
        )
        finalize_schema = replies[1]["result"]["tools"][3]["inputSchema"]
        analysis = finalize_schema["properties"]["analysis"]
        self.assertEqual(analysis["additionalProperties"], False)
        self.assertIn("impacts", analysis["required"])
        self.assertEqual(analysis["properties"]["impacts"]["items"]["additionalProperties"], False)
        impact_properties = analysis["properties"]["impacts"]["items"]["properties"]
        self.assertIn("graph_path_keys", impact_properties)
        self.assertIn("coverage_rationale", impact_properties)

    def test_scan_returns_renderer_text_and_structured_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_graph_config(root, True)
            (root / "api").mkdir()
            (root / "api/profile.py").write_text(
                'FIELD = "profile.displayName"\n', encoding="utf-8"
            )
            replies = self.exchange(
                [
                    request(
                        1,
                        "tools/call",
                        {
                            "name": "rir_scan",
                            "arguments": {
                                "repo_root": str(root),
                                "change_request": "Rename profile.displayName",
                                "evidence": [],
                                "presentation": "balanced",
                            },
                        },
                    )
                ]
            )
            result = replies[0]["result"]
            self.assertEqual(
                result["content"][0]["text"],
                result["structuredContent"]["display_text"],
            )
            self.assertRegex(result["structuredContent"]["scan_id"], r"^[0-9a-f]{32}$")
            promoted = self.exchange(
                [
                    request(
                        2,
                        "tools/call",
                        {
                            "name": "rir_begin",
                            "arguments": {
                                "repo_root": str(root),
                                "request": "Rename profile.displayName",
                                "repository_evidence": [],
                                "adapter": "generic",
                                "scan_id": result["structuredContent"]["scan_id"],
                            },
                        },
                    )
                ]
            )[0]["result"]["structuredContent"]
            self.assertEqual(
                promoted["graph_receipt_id"],
                result["structuredContent"]["receipt_id"],
            )
            rules = " ".join(promoted["semantic_rules"])
            self.assertIn("do not call rir_trace_impact", rules)

    def test_begin_and_finalize_tools_share_controller_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_graph_config(root, False)
            process = subprocess.Popen(
                [sys.executable, str(SERVER)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            try:
                begin = request(
                    1,
                    "tools/call",
                    {
                        "name": "rir_begin",
                        "arguments": {
                            "repo_root": str(root),
                            "request": "Add nickname.",
                            "repository_evidence": ["displayName exists"],
                            "adapter": "generic",
                        },
                    },
                )
                process.stdin.write(json.dumps(begin) + "\n")
                process.stdin.flush()
                begin_reply = json.loads(process.stdout.readline())
                begin_content = begin_reply["result"]["structuredContent"]
                draft_id = begin_content["draft_id"]
                self.assertEqual(begin_content["repository_evidence"], ["displayName exists"])
                self.assertIn("impacts", begin_content["analysis_contract"]["required"])
                self.assertIn("prior_key_map", begin_content)
                self.assertRegex(begin_content["installed_payload_sha256"], r"^[0-9a-f]{64}$")
                self.assertIn("post-decision requires", " ".join(begin_content["semantic_rules"]))
                rules = " ".join(begin_content["semantic_rules"])
                self.assertIn("blocked impacts require workflow Not ready", rules)
                self.assertIn("deferred impacts may proceed", rules)
                self.assertIn("remaining risk with an owner", rules)
                self.assertIn("Superpowers handoff marker", rules)
                self.assertIn("controller-owned", rules)
                analysis = json.loads(
                    (FIXTURES / "controller-analysis-pre-decision.json").read_text()
                )
                finalize = request(
                    2,
                    "tools/call",
                    {
                        "name": "rir_finalize",
                        "arguments": {
                            "repo_root": str(root),
                            "draft_id": draft_id,
                            "analysis": analysis,
                        },
                    },
                )
                process.stdin.write(json.dumps(finalize) + "\n")
                process.stdin.flush()
                final_reply = json.loads(process.stdout.readline())
            finally:
                process.stdin.close()
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()

        result = final_reply["result"]
        self.assertEqual(result["structuredContent"]["status"], "published")
        self.assertTrue(result["content"][0]["text"].startswith("## Change Impact Summary"))
        self.assertEqual(result["content"][0]["text"], result["structuredContent"]["display_text"])
        self.assertFalse(result["structuredContent"]["display_text"].endswith("\n"))

    def test_unknown_tool_and_malformed_params_return_bounded_errors_then_continue(self):
        replies = self.exchange(
            [
                request(1, "tools/call", {"name": "other", "arguments": {}}),
                request(2, "tools/call", {"name": "rir_begin", "arguments": []}),
                request(
                    3,
                    "tools/call",
                    {
                        "name": "rir_begin",
                        "arguments": {
                            "repo_root": "/tmp",
                            "request": "x",
                            "repository_evidence": {"bad": "shape"},
                            "adapter": "generic",
                        },
                    },
                ),
                request(4, "tools/list", {}),
            ]
        )

        self.assertEqual(replies[0]["error"]["code"], -32602)
        self.assertEqual(replies[1]["error"]["code"], -32602)
        self.assertEqual(replies[2]["error"]["code"], -32602)
        self.assertIn("tools", replies[3]["result"])
        self.assertLess(len(json.dumps(replies[0])), 2048)

    def test_notification_has_no_response_and_clean_eof_exits_zero(self):
        replies = self.exchange(
            [
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                request(2, "tools/list", {}),
            ]
        )
        self.assertEqual([reply["id"] for reply in replies], [2])

    def test_stale_finalize_returns_bounded_error_and_server_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_graph_config(root, False)
            process = subprocess.Popen(
                [sys.executable, str(SERVER)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            try:
                drafts = []
                for identifier in (1, 2):
                    message = request(
                        identifier,
                        "tools/call",
                        {
                            "name": "rir_begin",
                            "arguments": {
                                "repo_root": str(root),
                                "request": "Add nickname.",
                                "repository_evidence": ["displayName exists"],
                                "adapter": "generic",
                            },
                        },
                    )
                    process.stdin.write(json.dumps(message) + "\n")
                    process.stdin.flush()
                    drafts.append(
                        json.loads(process.stdout.readline())["result"]["structuredContent"][
                            "draft_id"
                        ]
                    )
                analysis = json.loads(
                    (FIXTURES / "controller-analysis-pre-decision.json").read_text()
                )
                replies = []
                for identifier, draft_id in ((3, drafts[0]), (4, drafts[1])):
                    message = request(
                        identifier,
                        "tools/call",
                        {
                            "name": "rir_finalize",
                            "arguments": {
                                "repo_root": str(root),
                                "draft_id": draft_id,
                                "analysis": analysis,
                            },
                        },
                    )
                    process.stdin.write(json.dumps(message) + "\n")
                    process.stdin.flush()
                    replies.append(json.loads(process.stdout.readline()))
                process.stdin.write(json.dumps(request(5, "tools/list", {})) + "\n")
                process.stdin.flush()
                after = json.loads(process.stdout.readline())
            finally:
                process.stdin.close()
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()

        self.assertIn("result", replies[0])
        self.assertEqual(replies[1]["error"]["code"], -32602)
        self.assertIn("tools", after["result"])

    def test_revision_begin_returns_normalized_prior_decision_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_graph_config(root, False)
            process = subprocess.Popen(
                [sys.executable, str(SERVER)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            try:

                def call(identifier, name, arguments):
                    process.stdin.write(
                        json.dumps(
                            request(
                                identifier, "tools/call", {"name": name, "arguments": arguments}
                            )
                        )
                        + "\n"
                    )
                    process.stdin.flush()
                    return json.loads(process.stdout.readline())["result"]["structuredContent"]

                first = call(
                    1,
                    "rir_begin",
                    {
                        "repo_root": str(root),
                        "request": "Remove displayName.",
                        "repository_evidence": ["mobile reads displayName"],
                        "adapter": "generic",
                    },
                )
                post = json.loads((FIXTURES / "controller-analysis-post-decision.json").read_text())
                call(
                    2,
                    "rir_finalize",
                    {"repo_root": str(root), "draft_id": first["draft_id"], "analysis": post},
                )
                second = call(
                    3,
                    "rir_begin",
                    {
                        "repo_root": str(root),
                        "request": "Desktop cache evidence arrived.",
                        "repository_evidence": ["desktop cache persists displayName"],
                        "adapter": "generic",
                    },
                )
            finally:
                process.stdin.close()
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()

        guidance = second["analysis_guidance"]
        self.assertEqual(guidance["recommended_phase"], "post-decision")
        self.assertEqual(guidance["carry_forward_decisions"][0]["key"], "own-workspace")
        self.assertEqual(
            guidance["carry_forward_decisions"][0]["accepted_impact_keys"], ["member-scope"]
        )
        prior_impact = guidance["carry_forward_impacts"][0]
        self.assertEqual(prior_impact["key"], "member-scope")
        self.assertEqual(prior_impact["state"], "accepted")
        self.assertIn("summary", prior_impact)
        self.assertIn("reopened", " ".join(second["semantic_rules"]))
        self.assertIn("reuse its key", " ".join(second["semantic_rules"]))

    def test_line_larger_than_limit_is_rejected_even_when_newline_is_buffered(self):
        payload = b" " * (2 * 1024 * 1024) + b"\n"
        result = subprocess.run(
            [sys.executable, str(SERVER)],
            input=payload,
            capture_output=True,
            check=False,
        )
        replies = [json.loads(line) for line in result.stdout.splitlines()]

        self.assertEqual(result.returncode, 0)
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertIn("exceeds", replies[0]["error"]["message"])

    def test_initialize_negotiates_the_supported_protocol_version(self):
        replies = self.exchange(
            [
                request(
                    1,
                    "initialize",
                    {
                        "protocolVersion": "2099-01-01",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                ),
            ]
        )
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")

    def test_deeply_nested_json_is_bounded_and_following_request_survives(self):
        nested = "[" * 1500 + "0" + "]" * 1500
        safe = json.dumps(request(2, "tools/list", {}))
        result = subprocess.run(
            [sys.executable, str(SERVER)],
            input=nested + "\n" + safe + "\n",
            text=True,
            capture_output=True,
            check=False,
        )
        replies = [json.loads(line) for line in result.stdout.splitlines()]

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertIn("tools", replies[1]["result"])

    def test_begin_trace_finalize_share_controller_and_compact_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_graph_config(root, True)
            (root / "api").mkdir()
            (root / "desktop").mkdir()
            (root / "api/profile.py").write_text(
                'FIELD = "profile.displayName"\n', encoding="utf-8"
            )
            (root / "desktop/profile_cache.ts").write_text(
                'const key = "profile.displayName";\n', encoding="utf-8"
            )
            process = subprocess.Popen(
                [sys.executable, str(SERVER)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            try:

                def call(identifier, name, arguments):
                    process.stdin.write(
                        json.dumps(
                            request(
                                identifier, "tools/call", {"name": name, "arguments": arguments}
                            )
                        )
                        + "\n"
                    )
                    process.stdin.flush()
                    return json.loads(process.stdout.readline())

                begun = call(
                    1,
                    "rir_begin",
                    {
                        "repo_root": str(root),
                        "request": "Change profile display name.",
                        "repository_evidence": ["profile.displayName exists"],
                        "adapter": "generic",
                    },
                )["result"]["structuredContent"]
                trace_reply = call(
                    2,
                    "rir_trace_impact",
                    {
                        "repo_root": str(root),
                        "draft_id": begun["draft_id"],
                        "seeds": [{"term": "profile.displayName", "location": "api/profile.py"}],
                    },
                )
                traced = trace_reply["result"]["structuredContent"]
                self.assertEqual(json.loads(trace_reply["result"]["content"][0]["text"]), traced)
                self.assertTrue(traced["compact_graph"]["paths"])
                self.assertEqual(
                    traced["seeds"], [{"term": "profile.displayName", "location": "api/profile.py"}]
                )
                self.assertRegex(traced["request_sha256"], r"^[0-9a-f]{64}$")
                analysis = json.loads(
                    (FIXTURES / "controller-analysis-pre-decision.json").read_text()
                )
                analysis["impacts"][0]["graph_path_keys"] = [
                    row["key"] for row in traced["compact_graph"]["paths"]
                ]
                analysis["impacts"][0]["evidence_level"] = "unknown"
                finalized = call(
                    3,
                    "rir_finalize",
                    {
                        "repo_root": str(root),
                        "draft_id": begun["draft_id"],
                        "graph_receipt_id": traced["receipt_id"],
                        "analysis": analysis,
                    },
                )
            finally:
                process.stdin.close()
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()

        self.assertEqual(
            finalized["result"]["content"][0]["text"],
            finalized["result"]["structuredContent"]["display_text"],
        )

    def test_malformed_trace_error_is_bounded_and_following_request_survives(self):
        replies = self.exchange(
            [
                request(
                    1,
                    "tools/call",
                    {
                        "name": "rir_trace_impact",
                        "arguments": {
                            "repo_root": "/tmp",
                            "draft_id": "0" * 32,
                            "seeds": [{"term": "x", "location": "../escape"}],
                        },
                    },
                ),
                request(2, "tools/list", {}),
            ]
        )

        self.assertEqual(replies[0]["error"]["code"], -32602)
        self.assertLess(len(json.dumps(replies[0])), 2048)
        self.assertEqual(
            [tool["name"] for tool in replies[1]["result"]["tools"]],
            ["rir_scan", "rir_begin", "rir_trace_impact", "rir_finalize"],
        )

    @unittest.skipIf(fcntl is None, "requires POSIX flock")
    def test_trace_held_lock_error_is_bounded_and_server_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_graph_config(root, True)
            config_path = root / ".requirements-impact-refiner.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["impact_graph"]["max_seconds"] = 1
            config["impact_graph"]["target_seconds"] = 1
            config_path.write_text(json.dumps(config), encoding="utf-8")
            (root / "api").mkdir()
            (root / "desktop").mkdir()
            (root / "api/profile.py").write_text(
                'FIELD = "profile.displayName"\n', encoding="utf-8"
            )
            (root / "desktop/profile_cache.ts").write_text(
                'const key = "profile.displayName";\n', encoding="utf-8"
            )
            process = subprocess.Popen(
                [sys.executable, str(SERVER)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            descriptor = None
            try:

                def call(identifier, name, arguments):
                    process.stdin.write(
                        json.dumps(
                            request(
                                identifier, "tools/call", {"name": name, "arguments": arguments}
                            )
                        )
                        + "\n"
                    )
                    process.stdin.flush()
                    return json.loads(process.stdout.readline())

                begun = call(
                    1,
                    "rir_begin",
                    {
                        "repo_root": str(root),
                        "request": "Bound MCP lock.",
                        "repository_evidence": ["profile.displayName exists"],
                        "adapter": "generic",
                    },
                )["result"]["structuredContent"]
                report_dir = root / ".requirements-impact-refiner/reports" / begun["report_id"]
                report_dir.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(report_dir / ".controller.lock", os.O_RDWR | os.O_CREAT, 0o600)
                fcntl.flock(descriptor, fcntl.LOCK_EX)

                def release():
                    time.sleep(1.25)
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                    os.close(descriptor)

                releaser = threading.Thread(target=release)
                releaser.start()
                started = time.monotonic()
                reply = call(
                    2,
                    "rir_trace_impact",
                    {
                        "repo_root": str(root),
                        "draft_id": begun["draft_id"],
                        "seeds": [{"term": "profile.displayName", "location": "api/profile.py"}],
                    },
                )
                elapsed = time.monotonic() - started
                releaser.join(timeout=2)
                descriptor = None
                process.stdin.write(json.dumps(request(3, "tools/list", {})) + "\n")
                process.stdin.flush()
                after = json.loads(process.stdout.readline())
            finally:
                if descriptor is not None:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                    os.close(descriptor)
                process.stdin.close()
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()

        self.assertEqual(reply["error"]["code"], -32602)
        self.assertIn("deadline exhausted waiting for controller lock", reply["error"]["message"])
        self.assertLess(len(json.dumps(reply)), 2048)
        self.assertLess(elapsed, 1.2)
        self.assertIn("tools", after["result"])


if __name__ == "__main__":
    unittest.main()


class SchemaPatternAnchoringTest(unittest.TestCase):
    """Pattern validation must consume the whole value: a trailing newline
    slipped past re.search because $ matches before it."""

    def test_newline_smuggled_id_is_rejected_at_the_schema_layer(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("_srv_schema", SERVER)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        schema = {"type": "string", "pattern": "^[0-9a-f]{32}$"}
        module._validate_schema("0" * 32, schema, "scan_id")
        with self.assertRaises(ValueError):
            module._validate_schema("0" * 32 + "\n", schema, "scan_id")
