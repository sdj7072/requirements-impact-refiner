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
                draft_id = begin_reply["result"]["structuredContent"]["draft_id"]
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
                request(3, "tools/list", {}),
            ]
        )

        self.assertEqual(replies[0]["error"]["code"], -32602)
        self.assertEqual(replies[1]["error"]["code"], -32602)
        self.assertIn("tools", replies[2]["result"])
        self.assertLess(len(json.dumps(replies[0])), 2048)

    def test_notification_has_no_response_and_clean_eof_exits_zero(self):
        replies = self.exchange(
            [
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                request(2, "tools/list", {}),
            ]
        )
        self.assertEqual([reply["id"] for reply in replies], [2])


if __name__ == "__main__":
    unittest.main()
