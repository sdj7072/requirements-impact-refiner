import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts" / "rir_mcp_server.py"
FIXTURES = ROOT / "tests" / "fixtures"


def request(identifier, method, params):
    return {"jsonrpc": "2.0", "id": identifier, "method": method, "params": params}


class RirMcpServerTest(unittest.TestCase):
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
                request(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}),
                request(2, "tools/list", {}),
            ]
        )

        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(
            [tool["name"] for tool in replies[1]["result"]["tools"]],
            ["rir_begin", "rir_finalize"],
        )
        for tool in replies[1]["result"]["tools"]:
            self.assertEqual(tool["inputSchema"]["additionalProperties"], False)
        finalize_schema = replies[1]["result"]["tools"][1]["inputSchema"]
        analysis = finalize_schema["properties"]["analysis"]
        self.assertEqual(analysis["additionalProperties"], False)
        self.assertIn("impacts", analysis["required"])
        self.assertEqual(analysis["properties"]["impacts"]["items"]["additionalProperties"], False)

    def test_begin_and_finalize_tools_share_controller_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = subprocess.Popen(
                [sys.executable, str(SERVER)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            try:
                begin = request(1, "tools/call", {"name": "rir_begin", "arguments": {"repo_root": str(root), "request": "Add nickname.", "repository_evidence": ["displayName exists"], "adapter": "generic"}})
                process.stdin.write(json.dumps(begin) + "\n")
                process.stdin.flush()
                begin_reply = json.loads(process.stdout.readline())
                begin_content = begin_reply["result"]["structuredContent"]
                draft_id = begin_content["draft_id"]
                self.assertEqual(begin_content["repository_evidence"], ["displayName exists"])
                self.assertIn("impacts", begin_content["analysis_contract"]["required"])
                self.assertIn("prior_key_map", begin_content)
                analysis = json.loads((FIXTURES / "controller-analysis-pre-decision.json").read_text())
                finalize = request(2, "tools/call", {"name": "rir_finalize", "arguments": {"repo_root": str(root), "draft_id": draft_id, "analysis": analysis}})
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

    def test_unknown_tool_and_malformed_params_return_bounded_errors_then_continue(self):
        replies = self.exchange(
            [
                request(1, "tools/call", {"name": "other", "arguments": {}}),
                request(2, "tools/call", {"name": "rir_begin", "arguments": []}),
                request(3, "tools/call", {"name": "rir_begin", "arguments": {"repo_root": "/tmp", "request": "x", "repository_evidence": {"bad": "shape"}, "adapter": "generic"}}),
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
            process = subprocess.Popen(
                [sys.executable, str(SERVER)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
            )
            try:
                drafts = []
                for identifier in (1, 2):
                    message = request(identifier, "tools/call", {"name": "rir_begin", "arguments": {"repo_root": str(root), "request": "Add nickname.", "repository_evidence": ["displayName exists"], "adapter": "generic"}})
                    process.stdin.write(json.dumps(message) + "\n")
                    process.stdin.flush()
                    drafts.append(json.loads(process.stdout.readline())["result"]["structuredContent"]["draft_id"])
                analysis = json.loads((FIXTURES / "controller-analysis-pre-decision.json").read_text())
                replies = []
                for identifier, draft_id in ((3, drafts[0]), (4, drafts[1])):
                    message = request(identifier, "tools/call", {"name": "rir_finalize", "arguments": {"repo_root": str(root), "draft_id": draft_id, "analysis": analysis}})
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

    def test_line_larger_than_limit_is_rejected_even_when_newline_is_buffered(self):
        payload = b" " * (2 * 1024 * 1024) + b"\n"
        result = subprocess.run(
            [sys.executable, str(SERVER)], input=payload,
            capture_output=True, check=False,
        )
        replies = [json.loads(line) for line in result.stdout.splitlines()]

        self.assertEqual(result.returncode, 0)
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertIn("exceeds", replies[0]["error"]["message"])

    def test_initialize_negotiates_the_supported_protocol_version(self):
        replies = self.exchange([
            request(1, "initialize", {"protocolVersion": "2099-01-01", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}),
        ])
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")


if __name__ == "__main__":
    unittest.main()
