import dataclasses
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
FIXTURE = FIXTURES / "rir-controller-facade-v05.json"
BASELINE_COMMIT = "e8599b3ff4b9870b67ed1ea8e08658e938a209ea"
PUBLIC_NAMES = (
    "BeginRequest",
    "DraftResult",
    "ScanRequest",
    "TraceRequest",
    "TraceResult",
    "FinalizeRequest",
    "FinalizeResult",
    "scan_impact",
    "begin_refinement",
    "load_draft",
    "trace_impact",
    "finalize_refinement",
)
RESULT_TYPES = ("DraftResult", "TraceResult", "FinalizeResult")
FIXED_DRAFT_ID = "1" * 32


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CONTROLLER = load_module("rir_controller_facade", SCRIPTS / "rir_controller.py")


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2025, 1, 2, 3, 4, 5, tzinfo=tz)


def canonical_object_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def canonical_bytes(value):
    return canonical_object_bytes(value) + b"\n"


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def relative_path(root, path):
    return Path(path).relative_to(Path(root).resolve()).as_posix()


def captured_error(call):
    try:
        call()
    except Exception as error:
        return {"exception_type": type(error).__name__, "message": str(error)}
    raise AssertionError("representative rejected flow did not raise")


def normalized_draft_bytes(payload):
    value = json.loads(payload)
    value["repo_root"] = "<repo-root>"
    return canonical_bytes(value)


def normalized_trace_result(root, result):
    compact_graph = json.loads(json.dumps(result.compact_graph))
    compact_graph["summary"]["timings_ms"] = {
        key: 0 for key in compact_graph["summary"]["timings_ms"]
    }
    return {
        "receipt_id": "<hex32>",
        "receipt_path": relative_path(root, result.receipt_path),
        "receipt_sha256": "<sha256>",
        "compact_graph": compact_graph,
        "budget_status": result.budget_status,
        "request_sha256": "<sha256>",
        "seeds": [{"term": seed.term, "location": seed.location} for seed in result.seeds],
    }


def normalized_receipt_bytes(payload):
    value = json.loads(payload)
    value["receipt_id"] = "<hex32>"
    value["repo_root_sha256"] = "<sha256>"
    value["request_sha256"] = "<sha256>"
    value["timings_ms"] = {key: 0 for key in value["timings_ms"]}
    value["cache"]["key"] = "<sha256>"
    return canonical_object_bytes(value)


class RirControllerFacadeContractTest(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def configure(self, graph_enabled):
        (self.root / ".requirements-impact-refiner.json").write_text(
            json.dumps(
                {
                    "impact_graph": {
                        "enabled": graph_enabled,
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

    def begin(self, **changes):
        values = {
            "repo_root": self.root,
            "request": "Let workspace members edit every project.",
            "repository_evidence": (
                "authorizeProjectEdit permits owner and admin",
                "workspace invitations default to member",
            ),
            "adapter": "generic",
        }
        values.update(changes)
        with (
            mock.patch.object(CONTROLLER, "datetime", FixedDateTime),
            mock.patch.object(CONTROLLER.secrets, "token_hex", return_value=FIXED_DRAFT_ID),
        ):
            return CONTROLLER.begin_refinement(CONTROLLER.BeginRequest(**values))

    def test_public_facade_inventory_matches_v05_fixture(self):
        self.assertEqual(
            {
                "baseline_commit": BASELINE_COMMIT,
                "fixture_filename": "rir-controller-facade-v05.json",
                "provenance": (
                    "Characterized at baseline commit e8599b3; the retained v05 filename "
                    "does not assert that these bytes came from a historical v0.5 release."
                ),
            },
            self.fixture["metadata"],
        )
        self.assertEqual(sorted(PUBLIC_NAMES), self.fixture["public_names"])
        for name in PUBLIC_NAMES:
            self.assertTrue(hasattr(CONTROLLER, name), name)

    def test_result_fields_match_v05_fixture(self):
        actual = {
            name: [field.name for field in dataclasses.fields(getattr(CONTROLLER, name))]
            for name in RESULT_TYPES
        }
        self.assertEqual(self.fixture["result_fields"], actual)

    def test_begin_success_and_rejection_match_v05_fixture(self):
        self.configure(graph_enabled=False)
        result = self.begin()
        draft_payload = result.draft_path.read_bytes()
        self.assertEqual(canonical_bytes(json.loads(draft_payload)), draft_payload)
        actual = {
            "result": {
                "draft_id": result.draft_id,
                "draft_path": relative_path(self.root, result.draft_path),
                "report_id": result.report_id,
                "revision": result.revision,
                "previous_sha256": result.previous_sha256,
                "settings": dict(result.settings),
                "prior_state": result.prior_state,
                "prior_key_map": result.prior_key_map,
                "scan_id": result.scan_id,
                "graph_receipt_id": result.graph_receipt_id,
            },
            "result_canonical_sha256": sha256(
                canonical_bytes(
                    {
                        "draft_id": result.draft_id,
                        "draft_path": relative_path(self.root, result.draft_path),
                        "report_id": result.report_id,
                        "revision": result.revision,
                        "previous_sha256": result.previous_sha256,
                        "settings": dict(result.settings),
                        "prior_state": result.prior_state,
                        "prior_key_map": result.prior_key_map,
                        "scan_id": result.scan_id,
                        "graph_receipt_id": result.graph_receipt_id,
                    }
                )
            ),
            "draft_canonical_sha256": sha256(normalized_draft_bytes(draft_payload)),
        }
        self.assertEqual(self.fixture["flows"]["begin"]["success"], actual)
        self.assertEqual(
            self.fixture["flows"]["begin"]["rejected"],
            captured_error(lambda: self.begin(adapter="unsupported")),
        )

    def test_trace_success_and_rejection_match_v05_fixture(self):
        self.configure(graph_enabled=True)
        (self.root / "api").mkdir()
        (self.root / "api" / "profile.py").write_text(
            'FIELD = "profile.displayName"\n', encoding="utf-8"
        )
        draft = self.begin()
        result = CONTROLLER.trace_impact(
            CONTROLLER.TraceRequest(
                self.root,
                draft.draft_id,
                (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
            )
        )
        self.assertRegex(result.receipt_id, r"^[0-9a-f]{32}$")
        self.assertRegex(result.receipt_sha256, r"^[0-9a-f]{64}$")
        self.assertRegex(result.request_sha256, r"^[0-9a-f]{64}$")
        receipt_payload = result.receipt_path.read_bytes()
        receipt_value = json.loads(receipt_payload)
        self.assertEqual(canonical_object_bytes(receipt_value), receipt_payload)
        self.assertRegex(receipt_value["cache"]["key"], r"^[0-9a-f]{64}$")
        normalized = normalized_trace_result(self.root, result)
        actual = {
            "result": normalized,
            "result_canonical_sha256": sha256(canonical_bytes(normalized)),
            "receipt_canonical_sha256": sha256(normalized_receipt_bytes(receipt_payload)),
        }
        self.assertEqual(self.fixture["flows"]["trace"]["success"], actual)

        rejected_root = self.root / "disabled"
        rejected_root.mkdir()
        self.root = rejected_root
        self.configure(graph_enabled=False)
        rejected_draft = self.begin()
        self.assertEqual(
            self.fixture["flows"]["trace"]["rejected"],
            captured_error(
                lambda: CONTROLLER.trace_impact(
                    CONTROLLER.TraceRequest(
                        self.root,
                        rejected_draft.draft_id,
                        (CONTROLLER.TraceSeed("profile.displayName", None),),
                    )
                )
            ),
        )

    def test_finalize_success_and_rejection_match_v05_fixture(self):
        self.configure(graph_enabled=False)
        draft = self.begin()
        analysis_path = FIXTURES / "controller-analysis-pre-decision.json"
        analysis_payload = analysis_path.read_bytes()
        analysis = json.loads(analysis_payload)
        result = CONTROLLER.finalize_refinement(
            CONTROLLER.FinalizeRequest(self.root, draft.draft_id, analysis)
        )
        result_value = {
            "status": result.status,
            "report_id": result.report_id,
            "revision": result.revision,
            "delivery": result.delivery,
            "display_text_sha256": sha256(result.display_text.encode("utf-8")),
            "state_path": relative_path(self.root, result.state_path),
            "markdown_path": relative_path(self.root, result.markdown_path),
            "markdown_sha256": result.markdown_sha256,
        }
        actual = {
            "analysis_fixture_sha256": sha256(analysis_payload),
            "result": result_value,
            "result_canonical_sha256": sha256(canonical_bytes(result_value)),
            "state_canonical_sha256": sha256(result.state_path.read_bytes()),
            "markdown_canonical_sha256": sha256(result.markdown_path.read_bytes()),
        }
        self.assertEqual(self.fixture["flows"]["finalize"]["success"], actual)

        rejected_root = self.root / "rejected"
        rejected_root.mkdir()
        self.root = rejected_root
        self.configure(graph_enabled=False)
        rejected_draft = self.begin()
        rejected_analysis = dict(analysis)
        rejected_analysis["phase"] = "unsupported"
        self.assertEqual(
            self.fixture["flows"]["finalize"]["rejected"],
            captured_error(
                lambda: CONTROLLER.finalize_refinement(
                    CONTROLLER.FinalizeRequest(
                        self.root, rejected_draft.draft_id, rejected_analysis
                    )
                )
            ),
        )


if __name__ == "__main__":
    unittest.main()
