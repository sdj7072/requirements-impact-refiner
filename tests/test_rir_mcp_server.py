import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

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
    def load_server_module(self, name="_rir_mcp_test"):
        import importlib.util

        spec = importlib.util.spec_from_file_location(name, SERVER)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_stdlib_only_import_smoke_has_no_site_packages(self):
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        for script in (
            ROOT / "scripts/rir_controller.py",
            ROOT / "skills/requirements-impact-refiner/scripts/rir_controller.py",
            SERVER,
        ):
            with self.subTest(script=script.name):
                result = subprocess.run(
                    [sys.executable, "-S", str(script)],
                    text=True,
                    input="",
                    capture_output=True,
                    check=False,
                    env=environment,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_trace_seed_guard_requires_exact_location_key(self):
        module = self.load_server_module("_rir_mcp_trace_seed_guard")
        self.assertFalse(module._is_trace_seed({"term": "profile.displayName"}))
        self.assertTrue(module._is_trace_seed({"term": "profile.displayName", "location": None}))

    def test_malformed_controller_results_are_internal_handle_failures(self):
        module = self.load_server_module("_rir_mcp_result_guard")
        analysis = json.loads(
            (FIXTURES / "controller-analysis-pre-decision.json").read_text(encoding="utf-8")
        )
        cases = (
            (
                "rir_previous",
                "lookup_previous",
                {
                    "repo_root": str(ROOT),
                    "request": "Change the profile contract",
                    "repository_evidence": [],
                },
            ),
            (
                "rir_scan",
                "scan_impact",
                {"repo_root": str(ROOT), "change_request": "Change the profile contract"},
            ),
            (
                "rir_begin",
                "begin_refinement",
                {
                    "repo_root": str(ROOT),
                    "request": "Change the profile contract",
                    "repository_evidence": [],
                    "adapter": "generic",
                },
            ),
            (
                "rir_trace_impact",
                "trace_impact",
                {
                    "repo_root": str(ROOT),
                    "draft_id": "0" * 32,
                    "seeds": [{"term": "profile.displayName", "location": None}],
                },
            ),
            (
                "rir_finalize",
                "finalize_refinement",
                {
                    "repo_root": str(ROOT),
                    "draft_id": "0" * 32,
                    "analysis": analysis,
                },
            ),
        )
        for identifier, (name, operation, arguments) in enumerate(cases, start=1):
            with self.subTest(name=name):
                with mock.patch.object(module.rir_controller, operation, return_value=object()):
                    reply = module.handle(
                        request(
                            identifier,
                            "tools/call",
                            {"name": name, "arguments": arguments},
                        )
                    )
                self.assertEqual(
                    reply["error"],
                    {"code": -32603, "message": "controller operation failed"},
                )

        malformed = module.handle(
            request(
                9,
                "tools/call",
                {"name": "rir_scan", "arguments": {"repo_root": str(ROOT)}},
            )
        )
        self.assertEqual(malformed["error"]["code"], -32602)

    def test_previous_result_bounds_and_cross_root_paths_fail_as_internal_errors(self):
        module = self.load_server_module("_rir_mcp_previous_result_guard")
        arguments = {
            "repo_root": str(ROOT),
            "request": "Change the profile contract",
            "repository_evidence": [],
        }
        baseline = {
            "status": "stale",
            "report_id": "RPT-001",
            "revision": 1,
            "markdown_sha256": "1" * 64,
            "created_at": "2026-08-25T12:34:56Z",
            "baseline_commit": "2" * 40,
            "changed_paths": (),
            "changed_count": 0,
            "requirement_sha256": "3" * 64,
            "source_inventory_sha256": "4" * 64,
            "display_text": "## Previous Impact Report\n",
            "reason": "source changed",
            "elapsed_ms": 1,
        }
        invalid = (
            {"changed_paths": ("../foreign.py",), "changed_count": 1},
            {"changed_paths": ("/tmp/foreign.py",), "changed_count": 1},
            {"changed_paths": ("foreign\\path.py",), "changed_count": 1},
            {"changed_paths": ("changed.py",), "changed_count": None},
            {"display_text": "x" * (256 * 1024 + 1)},
            {"reason": "x" * 4097},
            {"created_at": "not-a-timestamp"},
            {"elapsed_ms": 60_001},
            {"status": "none", "display_text": None},
        )
        for identifier, changes in enumerate(invalid, start=1):
            with self.subTest(changes=changes):
                result = types.SimpleNamespace(**{**baseline, **changes})
                with mock.patch.object(
                    module.rir_controller, "lookup_previous", return_value=result
                ):
                    reply = module.handle(
                        request(
                            identifier,
                            "tools/call",
                            {"name": "rir_previous", "arguments": arguments},
                        )
                    )
                self.assertEqual(
                    reply["error"],
                    {"code": -32603, "message": "controller operation failed"},
                )
                self.assertNotIn("foreign", json.dumps(reply, sort_keys=True))

    def test_previous_storage_failure_is_sanitized_as_an_internal_error(self):
        module = self.load_server_module("_rir_mcp_previous_storage_guard")
        arguments = {
            "repo_root": str(ROOT),
            "request": "Change the profile contract",
            "repository_evidence": [],
        }

        with mock.patch.object(
            module.rir_controller,
            "lookup_previous",
            side_effect=OSError("/private/secret/report.json"),
        ):
            reply = module.handle(
                request(
                    1,
                    "tools/call",
                    {"name": "rir_previous", "arguments": arguments},
                )
            )

        self.assertEqual(
            reply["error"],
            {"code": -32603, "message": "controller operation failed"},
        )
        self.assertNotIn("secret", json.dumps(reply, sort_keys=True))

    def test_previous_keeps_wide_lookup_bounds_and_forwards_optional_report_id(self):
        module = self.load_server_module("_rir_mcp_previous_wide_lookup")
        captured = []

        def lookup(value):
            captured.append(value)
            return types.SimpleNamespace(
                status="none",
                report_id=None,
                revision=None,
                markdown_sha256=None,
                created_at=None,
                baseline_commit=None,
                changed_paths=(),
                changed_count=None,
                requirement_sha256="1" * 64,
                source_inventory_sha256=None,
                display_text=None,
                reason="no match",
                elapsed_ms=1,
                candidates=(),
            )

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(module.rir_controller, "lookup_previous", side_effect=lookup):
                reply = module.handle(
                    request(
                        1,
                        "tools/call",
                        {
                            "name": "rir_previous",
                            "arguments": {
                                "repo_root": directory,
                                "request": "x" * 5000,
                                "repository_evidence": ["e" * 5000],
                                "report_id": "RPT-002",
                            },
                        },
                    )
                )

        self.assertEqual(reply["result"]["structuredContent"]["status"], "none")
        self.assertEqual(captured[0].report_id, "RPT-002")
        self.assertEqual(module.PREVIOUS_SCHEMA["properties"]["request"]["maxLength"], 262144)
        self.assertEqual(
            module.PREVIOUS_SCHEMA["properties"]["repository_evidence"]["maxItems"], 128
        )

    def test_previous_ambiguous_serializes_only_bounded_safe_candidates(self):
        module = self.load_server_module("_rir_mcp_previous_candidates")
        candidates = tuple(
            types.SimpleNamespace(
                report_id=f"RPT-{number:03d}",
                revision=number,
                created_at="2026-08-25T12:34:56Z",
            )
            for number in range(1, 3)
        )
        result = types.SimpleNamespace(
            status="ambiguous",
            report_id=None,
            revision=None,
            markdown_sha256=None,
            created_at=None,
            baseline_commit=None,
            changed_paths=(),
            changed_count=None,
            requirement_sha256="1" * 64,
            source_inventory_sha256=None,
            display_text=None,
            reason="multiple matches",
            elapsed_ms=1,
            candidates=candidates,
        )
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(module.rir_controller, "lookup_previous", return_value=result):
                reply = module.handle(
                    request(
                        1,
                        "tools/call",
                        {
                            "name": "rir_previous",
                            "arguments": {
                                "repo_root": directory,
                                "request": "rename profile",
                                "repository_evidence": [],
                            },
                        },
                    )
                )

        structured = reply["result"]["structuredContent"]
        self.assertEqual(structured["status"], "ambiguous")
        self.assertIsNone(structured["display_text"])
        self.assertEqual(
            structured["candidates"],
            [
                {
                    "report_id": "RPT-001",
                    "revision": 1,
                    "created_at": "2026-08-25T12:34:56Z",
                },
                {
                    "report_id": "RPT-002",
                    "revision": 2,
                    "created_at": "2026-08-25T12:34:56Z",
                },
            ],
        )

    def test_nested_begin_result_shapes_fail_closed_as_internal_errors(self):
        module = self.load_server_module("_rir_mcp_nested_begin_result_guard")
        valid_key_map = {
            "invariants": {},
            "impacts": {},
            "decisions": {},
            "criteria": {},
        }
        malformed_values = (
            (
                None,
                {
                    **valid_key_map,
                    "decisions": object(),
                },
            ),
            ({"impacts": [], "decisions": [], "summary": "not-a-list"}, valid_key_map),
            (
                {"impacts": [], "decisions": [], "summary": [{"impact_id": 7}]},
                valid_key_map,
            ),
        )
        arguments = {
            "repo_root": str(ROOT),
            "request": "Change the profile contract",
            "repository_evidence": [],
            "adapter": "generic",
        }
        for index, (prior_state, prior_key_map) in enumerate(malformed_values, start=1):
            with self.subTest(index=index):
                result = types.SimpleNamespace(
                    draft_id="0" * 32,
                    draft_path=ROOT / "draft.json",
                    report_id="RPT-001",
                    revision=1,
                    previous_sha256="none",
                    settings={"audience": "balanced", "delivery": "compact"},
                    prior_state=prior_state,
                    prior_key_map=prior_key_map,
                    scan_id=None,
                    graph_receipt_id=None,
                )
                with mock.patch.object(
                    module.rir_controller, "begin_refinement", return_value=result
                ):
                    reply = module.handle(
                        request(
                            index,
                            "tools/call",
                            {"name": "rir_begin", "arguments": arguments},
                        )
                    )
                self.assertEqual(
                    reply["error"],
                    {"code": -32603, "message": "controller operation failed"},
                )

        malformed_trace = types.SimpleNamespace(
            receipt_id="0" * 32,
            receipt_path=ROOT,
            receipt_sha256="0" * 64,
            compact_graph={},
            budget_status="closed",
            request_sha256="0" * 64,
            seeds=(types.SimpleNamespace(term="profile.displayName"),),
        )
        self.assertFalse(module._is_trace_result(malformed_trace))

    def test_controller_result_paths_are_strictly_repository_contained(self):
        module = self.load_server_module("_rir_mcp_result_path_guard")
        analysis = json.loads(
            (FIXTURES / "controller-analysis-pre-decision.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "repo"
            artifacts = repo / "artifacts"
            nested = repo / "nested"
            artifacts.mkdir(parents=True)
            nested.mkdir()
            contained = {}
            for name in ("draft", "state", "markdown", "receipt"):
                path = artifacts / f"{name}.json"
                path.write_text(name, encoding="utf-8")
                contained[name] = path
            outside = base / "outside.json"
            outside.write_text("outside", encoding="utf-8")
            symlink_escape = repo / "symlink-escape.json"
            symlink_escape.symlink_to(outside)
            invalid_paths = (
                ("traversal", nested / ".." / ".." / outside.name),
                ("absolute-outside", outside.resolve()),
                ("missing", repo / "missing.json"),
                ("symlink-escape", symlink_escape),
            )
            begin_arguments = {
                "repo_root": str(repo),
                "request": "Change the profile contract",
                "repository_evidence": [],
                "adapter": "generic",
            }
            finalize_arguments = {
                "repo_root": str(repo),
                "draft_id": "0" * 32,
                "analysis": analysis,
            }
            trace_arguments = {
                "repo_root": str(repo),
                "draft_id": "0" * 32,
                "seeds": [{"term": "profile.displayName", "location": None}],
            }
            begin_result = {
                "draft_id": "0" * 32,
                "draft_path": contained["draft"],
                "report_id": "RPT-001",
                "revision": 1,
                "previous_sha256": "none",
                "settings": {"audience": "balanced", "delivery": "compact"},
                "prior_state": None,
                "prior_key_map": None,
                "scan_id": None,
                "graph_receipt_id": None,
            }
            finalize_result = {
                "status": "published",
                "report_id": "RPT-001",
                "revision": 1,
                "delivery": "compact",
                "display_text": "published",
                "state_path": contained["state"],
                "markdown_path": contained["markdown"],
                "markdown_sha256": "1" * 64,
            }
            trace_result = {
                "receipt_id": "2" * 32,
                "receipt_path": contained["receipt"],
                "receipt_sha256": "3" * 64,
                "compact_graph": {},
                "budget_status": "closed",
                "request_sha256": "4" * 64,
                "seeds": (types.SimpleNamespace(term="profile.displayName", location=None),),
            }
            cases = (
                (
                    "rir_begin",
                    "begin_refinement",
                    "draft_path",
                    begin_arguments,
                    begin_result,
                    contained["draft"],
                ),
                (
                    "rir_finalize",
                    "finalize_refinement",
                    "state_path",
                    finalize_arguments,
                    finalize_result,
                    contained["state"],
                ),
                (
                    "rir_finalize",
                    "finalize_refinement",
                    "markdown_path",
                    finalize_arguments,
                    finalize_result,
                    contained["markdown"],
                ),
                (
                    "rir_trace_impact",
                    "trace_impact",
                    "receipt_path",
                    trace_arguments,
                    trace_result,
                    contained["receipt"],
                ),
            )
            identifier = 0
            for tool_name, operation, field, arguments, baseline, valid_path in cases:
                for path_kind, invalid_path in invalid_paths:
                    identifier += 1
                    with self.subTest(tool=tool_name, field=field, path_kind=path_kind):
                        result_values = dict(baseline)
                        result_values[field] = invalid_path
                        with mock.patch.object(
                            module.rir_controller,
                            operation,
                            return_value=types.SimpleNamespace(**result_values),
                        ):
                            reply = module.handle(
                                request(
                                    identifier,
                                    "tools/call",
                                    {"name": tool_name, "arguments": arguments},
                                )
                            )

                        self.assertEqual(
                            reply["error"],
                            {"code": -32603, "message": "controller operation failed"},
                        )
                        self.assertNotIn(str(base), json.dumps(reply, sort_keys=True))

                identifier += 1
                with self.subTest(tool=tool_name, field=field, path_kind="contained"):
                    result_values = dict(baseline)
                    result_values[field] = valid_path
                    with mock.patch.object(
                        module.rir_controller,
                        operation,
                        return_value=types.SimpleNamespace(**result_values),
                    ):
                        reply = module.handle(
                            request(
                                identifier,
                                "tools/call",
                                {"name": tool_name, "arguments": arguments},
                            )
                        )

                    expected = valid_path.resolve().relative_to(repo.resolve()).as_posix()
                    self.assertEqual(reply["result"]["structuredContent"][field], expected)

    def test_malformed_payload_identity_return_fails_closed(self):
        script = r"""
import importlib.util
import sys
import types
from pathlib import Path

path = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(path.parent))
fake = types.ModuleType("payload_identity")
fake.__file__ = str(path.parent / "payload_identity.py")
fake.payload_sha256 = lambda plugin_root: object()
sys.modules["payload_identity"] = fake
spec = importlib.util.spec_from_file_location("_mcp_payload_guard", path)
module = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(module)
except ImportError as error:
    if str(error) != "payload identity sibling result contract is incomplete":
        raise AssertionError(str(error))
else:
    raise AssertionError("malformed payload identity result was accepted")
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(SERVER)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def write_graph_config(self, root, enabled):
        (root / ".requirements-impact-refiner.json").write_text(
            json.dumps(
                {
                    "delivery": "compact",
                    "impact_graph": {
                        "enabled": enabled,
                        "max_seconds": 30,
                        "target_seconds": 10,
                        "providers": ["builtin"],
                        "install_policy": "never",
                        "deep": False,
                    },
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
        self.assertEqual(replies[0]["result"]["serverInfo"]["version"], "0.6.2-dev")
        self.assertEqual(
            [tool["name"] for tool in replies[1]["result"]["tools"]],
            [
                "rir_previous",
                "rir_scan",
                "rir_begin",
                "rir_trace_impact",
                "rir_finalize",
            ],
        )
        for tool in replies[1]["result"]["tools"]:
            self.assertEqual(tool["inputSchema"]["additionalProperties"], False)
            self.assertIn("local", tool["description"].lower())
            self.assertIn("network", tool["description"].lower())
        previous_schema = replies[1]["result"]["tools"][0]["inputSchema"]
        self.assertEqual(
            previous_schema["required"],
            ["repo_root", "request", "repository_evidence"],
        )
        self.assertEqual(
            set(previous_schema["properties"]),
            {"repo_root", "request", "repository_evidence", "report_id"},
        )
        scan_schema = replies[1]["result"]["tools"][1]["inputSchema"]
        self.assertEqual(scan_schema["required"], ["repo_root", "change_request"])
        trace_schema = replies[1]["result"]["tools"][3]["inputSchema"]
        self.assertEqual(
            trace_schema["properties"]["seeds"]["items"]["additionalProperties"], False
        )
        self.assertEqual(
            trace_schema["properties"]["seeds"]["items"]["required"],
            ["term", "location"],
        )
        finalize_schema = replies[1]["result"]["tools"][4]["inputSchema"]
        analysis = finalize_schema["properties"]["analysis"]
        self.assertEqual(analysis["additionalProperties"], False)
        self.assertIn("impacts", analysis["required"])
        self.assertEqual(analysis["properties"]["impacts"]["items"]["additionalProperties"], False)
        impact_properties = analysis["properties"]["impacts"]["items"]["properties"]
        self.assertIn("graph_path_keys", impact_properties)
        self.assertIn("coverage_rationale", impact_properties)
        self.assertIn(
            "graph_path_keys",
            analysis["properties"]["impacts"]["items"]["required"],
        )

    def test_incomplete_controller_sibling_fails_closed(self):
        script = r"""
import importlib.util
import sys
import types
from pathlib import Path

path = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(path.parent))
fake = types.ModuleType("rir_controller")
fake.__file__ = str(path.parent / "rir_controller.py")
fake.BeginRequest = type("BeginRequest", (), {})
sys.modules["rir_controller"] = fake
spec = importlib.util.spec_from_file_location("_mcp_guard", path)
module = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(module)
except ImportError as error:
    if str(error) != "controller sibling contract is incomplete":
        raise AssertionError(str(error))
else:
    raise AssertionError("incomplete controller sibling was accepted")
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(SERVER)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_server_ignores_foreign_controller_and_payload_identity_aliases(self):
        script = r"""
import importlib
import importlib.util
import sys
import types
from pathlib import Path

server = Path(sys.argv[1]).resolve()
scripts = server.parent
sys.path.insert(0, str(scripts))
local_controller = importlib.import_module("rir_controller")
local_payload = importlib.import_module("payload_identity")

foreign_controller = types.ModuleType("rir_controller")
foreign_controller.__file__ = str(scripts.parent / "foreign" / "rir_controller.py")
for name in (
    "ADAPTERS",
    "BeginRequest",
    "FinalizeRequest",
    "PreviousLookupRequest",
    "PreviousReportCandidate",
    "PreviousReportResult",
    "ScanRequest",
    "TraceRequest",
    "TraceSeed",
    "begin_refinement",
    "finalize_refinement",
    "lookup_previous",
    "scan_impact",
    "trace_impact",
):
    setattr(foreign_controller, name, getattr(local_controller, name))
foreign_payload = types.ModuleType("payload_identity")
foreign_payload.__file__ = str(scripts.parent / "foreign" / "payload_identity.py")
foreign_payload.payload_sha256 = local_payload.payload_sha256
sys.modules["rir_controller"] = foreign_controller
sys.modules["payload_identity"] = foreign_payload

spec = importlib.util.spec_from_file_location("_mcp_local_alias_guard", server)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if Path(module.rir_controller.__file__).resolve() != scripts / "rir_controller.py":
    raise AssertionError("foreign controller alias was trusted")
if Path(module.payload_identity.__file__).resolve() != scripts / "payload_identity.py":
    raise AssertionError("foreign payload identity alias was trusted")
if sys.modules["rir_controller"] is not foreign_controller:
    raise AssertionError("foreign controller alias was not preserved")
if sys.modules["payload_identity"] is not foreign_payload:
    raise AssertionError("foreign payload alias was not preserved")
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(SERVER)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

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
            structured_bytes = len(
                json.dumps(
                    result["structuredContent"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            self.assertLess(structured_bytes, 900)
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
            self.assertEqual(
                promoted["next_action"],
                {
                    "tool": "rir_finalize",
                    "required": True,
                    "fixed_arguments": {
                        "repo_root": str(root),
                        "draft_id": promoted["draft_id"],
                        "graph_receipt_id": promoted["graph_receipt_id"],
                    },
                    "required_agent_arguments": ["analysis"],
                },
            )
            rules = " ".join(promoted["semantic_rules"])
            self.assertIn("do not call rir_trace_impact", rules)

    def test_graph_enabled_begin_declares_required_trace_seeds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            begin = self.exchange(
                [
                    request(
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
                ]
            )[0]["result"]["structuredContent"]

        self.assertEqual(begin["next_action"]["tool"], "rir_trace_impact")
        self.assertEqual(
            begin["next_action"]["fixed_arguments"],
            {"repo_root": str(root), "draft_id": begin["draft_id"]},
        )
        self.assertEqual(begin["next_action"]["required_agent_arguments"], ["seeds"])

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
                self.assertNotIn("repository_evidence", begin_content)
                self.assertNotIn("analysis_contract", begin_content)
                self.assertNotIn("allowed_enums", begin_content)
                self.assertEqual(begin_content["contract_version"], 2)
                self.assertEqual(
                    begin_content["next_action"],
                    {
                        "tool": "rir_finalize",
                        "required": True,
                        "fixed_arguments": {
                            "repo_root": str(root),
                            "draft_id": draft_id,
                        },
                        "required_agent_arguments": ["analysis"],
                    },
                )
                begin_bytes = len(json.dumps(begin_content, ensure_ascii=False).encode("utf-8"))
                self.assertLess(begin_bytes, 7613 // 2)
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
                previous = request(
                    3,
                    "tools/call",
                    {
                        "name": "rir_previous",
                        "arguments": {
                            "repo_root": str(root),
                            "request": "Add nickname.",
                            "repository_evidence": ["displayName exists"],
                        },
                    },
                )
                process.stdin.write(json.dumps(previous) + "\n")
                process.stdin.flush()
                previous_reply = json.loads(process.stdout.readline())
            finally:
                process.stdin.close()
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()

        result = final_reply["result"]
        self.assertEqual(result["structuredContent"]["status"], "published")
        self.assertTrue(result["content"][0]["text"].startswith("# Requirements Impact Report"))
        self.assertTrue(
            any(line.startswith("|") for line in result["content"][0]["text"].splitlines())
        )
        self.assertEqual(result["content"][0]["text"], result["structuredContent"]["display_text"])
        self.assertFalse(result["structuredContent"]["display_text"].endswith("\n"))
        previous_result = previous_reply["result"]
        self.assertEqual(previous_result["structuredContent"]["status"], "stale")
        self.assertEqual(
            previous_result["content"][0]["text"],
            previous_result["structuredContent"]["display_text"],
        )
        self.assertTrue(
            previous_result["structuredContent"]["display_text"].startswith(
                "## Previous Impact Report\n"
            )
        )
        self.assertIn(
            "# Requirements Impact Report\n",
            previous_result["structuredContent"]["display_text"],
        )
        self.assertTrue(
            any(
                line.startswith("|")
                for line in previous_result["structuredContent"]["display_text"].splitlines()
            )
        )

    def test_previous_none_returns_structured_status_without_identity_or_body(self):
        with tempfile.TemporaryDirectory() as directory:
            replies = self.exchange(
                [
                    request(
                        1,
                        "tools/call",
                        {
                            "name": "rir_previous",
                            "arguments": {
                                "repo_root": directory,
                                "request": "Add nickname.",
                                "repository_evidence": [],
                            },
                        },
                    )
                ]
            )

        result = replies[0]["result"]
        self.assertEqual(result["content"], [])
        structured = result["structuredContent"]
        self.assertEqual(structured["status"], "none")
        for field in (
            "report_id",
            "revision",
            "markdown_sha256",
            "created_at",
            "baseline_commit",
            "source_inventory_sha256",
            "display_text",
        ):
            self.assertIsNone(structured[field], field)
        self.assertEqual(structured["changed_paths"], [])
        self.assertIsNone(structured["changed_count"])
        structured_bytes = len(
            json.dumps(
                structured,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        self.assertLess(structured_bytes, 700)

    def test_previous_lookup_key_is_stable_and_binds_exact_lookup_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            base = {
                "repo_root": directory,
                "request": "Rename profile.displayName",
                "repository_evidence": ["path:b.py", "symbol:B", "symbol:B"],
            }
            variants = (
                base,
                dict(base),
                {**base, "request": "Rename profile.nickname"},
                {**base, "repository_evidence": ["symbol:B", "path:b.py", "symbol:B"]},
                {**base, "report_id": "RPT-002"},
            )
            replies = self.exchange(
                [
                    request(
                        identifier,
                        "tools/call",
                        {"name": "rir_previous", "arguments": arguments},
                    )
                    for identifier, arguments in enumerate(variants, start=1)
                ]
            )

        keys = [reply["result"]["structuredContent"]["lookup_key"] for reply in replies]
        self.assertRegex(keys[0], r"^[0-9a-f]{32}$")
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(len(set(keys)), 4)

    def test_previous_root_parameter_and_operation_failures_have_distinct_error_codes(self):
        module = self.load_server_module("_rir_mcp_previous_root_failure_guard")

        def call(identifier, repo_root):
            return module.handle(
                request(
                    identifier,
                    "tools/call",
                    {
                        "name": "rir_previous",
                        "arguments": {
                            "repo_root": repo_root,
                            "request": "Add nickname.",
                            "repository_evidence": [],
                        },
                    },
                )
            )

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            valid_root = base / "valid"
            valid_root.mkdir()
            regular_file = base / "regular-file"
            regular_file.write_text("not a repository root\n", encoding="utf-8")
            symlink_root = base / "symlink-root"
            symlink_root.symlink_to(valid_root, target_is_directory=True)
            missing_root = base / "missing-root"

            valid = call(1, str(valid_root))
            malformed_type = call(2, [str(valid_root)])
            malformed_nul = call(7, "bad\x00root")
            failures = (
                call(3, str(missing_root)),
                call(4, str(symlink_root)),
                call(5, str(regular_file)),
            )
            with mock.patch.object(
                module.Path,
                "lstat",
                side_effect=PermissionError("/private/secret/repository"),
            ):
                failures = (*failures, call(6, str(valid_root)))

        self.assertEqual(valid["result"]["structuredContent"]["status"], "none")
        self.assertEqual(malformed_type["error"]["code"], -32602)
        self.assertEqual(malformed_nul["error"]["code"], -32602)
        for reply in failures:
            self.assertEqual(
                reply["error"],
                {"code": -32603, "message": "controller operation failed"},
            )
            self.assertNotIn("repository", json.dumps(reply, sort_keys=True))

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
                request(
                    5,
                    "tools/call",
                    {
                        "name": "rir_previous",
                        "arguments": {
                            "repo_root": "/tmp",
                            "request": "x",
                            "repository_evidence": [],
                            "surprise": True,
                        },
                    },
                ),
                request(
                    6,
                    "tools/call",
                    {
                        "name": "rir_previous",
                        "arguments": {
                            "repo_root": "/tmp",
                            "request": "x",
                            "repository_evidence": {},
                        },
                    },
                ),
            ]
        )

        self.assertEqual(replies[0]["error"]["code"], -32602)
        self.assertEqual(replies[1]["error"]["code"], -32602)
        self.assertEqual(replies[2]["error"]["code"], -32602)
        self.assertIn("tools", replies[3]["result"])
        self.assertEqual(replies[4]["error"]["code"], -32602)
        self.assertEqual(replies[5]["error"]["code"], -32602)
        self.assertLess(len(json.dumps(replies[0])), 2048)

    def test_notification_has_no_response_and_clean_eof_exits_zero(self):
        replies = self.exchange(
            [
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "rir_previous",
                        "arguments": {
                            "repo_root": str(ROOT),
                            "request": "notification",
                            "repository_evidence": [],
                        },
                    },
                },
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
                message = request(
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
                process.stdin.write(json.dumps(message) + "\n")
                process.stdin.flush()
                first_draft = json.loads(process.stdout.readline())["result"]["structuredContent"][
                    "draft_id"
                ]
                second_draft = "f" * 32
                first_path = (
                    root / ".requirements-impact-refiner" / "drafts" / f"{first_draft}.json"
                )
                clone = json.loads(first_path.read_text(encoding="utf-8"))
                clone["draft_id"] = second_draft
                second_path = first_path.with_name(f"{second_draft}.json")
                second_path.write_text(
                    json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    + "\n",
                    encoding="utf-8",
                )
                second_path.chmod(0o600)
                drafts = [first_draft, second_draft]
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
                        "request": "Remove displayName.",
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
                self.assertEqual(
                    traced["next_action"],
                    {
                        "tool": "rir_finalize",
                        "required": True,
                        "arguments": {
                            "repo_root": str(root),
                            "draft_id": begun["draft_id"],
                            "graph_receipt_id": traced["receipt_id"],
                        },
                    },
                )
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
        self.assertEqual(
            finalized["result"]["structuredContent"]["delivery_contract"],
            {
                "canonical": True,
                "must_return_content_verbatim": True,
                "terminal": True,
            },
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
            [
                "rir_previous",
                "rir_scan",
                "rir_begin",
                "rir_trace_impact",
                "rir_finalize",
            ],
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
