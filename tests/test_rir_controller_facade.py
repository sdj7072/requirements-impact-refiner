import copy
import dataclasses
import hashlib
import importlib.util
import inspect
import json
import re
import stat
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
DATACLASS_NAMES = (
    "BeginRequest",
    "DraftResult",
    "ScanRequest",
    "TraceRequest",
    "TraceResult",
    "FinalizeRequest",
    "FinalizeResult",
)
ENTRY_POINTS = (
    "scan_impact",
    "begin_refinement",
    "load_draft",
    "trace_impact",
    "finalize_refinement",
)
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


def default_contract(value):
    if value is dataclasses.MISSING or value is inspect.Signature.empty:
        return "<missing>"
    if callable(value):
        return f"<factory:{value.__qualname__}>"
    return value


def dataclass_contract(value):
    return {
        "fields": [
            [
                field.name,
                default_contract(field.default),
                default_contract(field.default_factory),
            ]
            for field in dataclasses.fields(value)
        ],
        "frozen": value.__dataclass_params__.frozen,
    }


def annotation_contract(value):
    if value is inspect.Signature.empty:
        return "<missing>"
    return value if isinstance(value, str) else value.__name__


def signature_contract(value):
    signature = inspect.signature(value)
    return {
        "parameters": [
            [
                parameter.name,
                parameter.kind.name,
                default_contract(parameter.default),
                annotation_contract(parameter.annotation),
            ]
            for parameter in signature.parameters.values()
        ],
        "return": annotation_contract(signature.return_annotation),
    }


def different_hex(value):
    replacement = "0" if value[0] != "0" else "1"
    return replacement + value[1:]


def assert_trace_relationships(test, result, receipt_payload, draft):
    receipt = json.loads(receipt_payload)
    binding = draft["graph_receipt"]
    summary = result.compact_graph["summary"]
    test.assertEqual(result.receipt_id, receipt["receipt_id"])
    test.assertEqual(result.receipt_sha256, sha256(receipt_payload))
    test.assertEqual(result.request_sha256, receipt["request_sha256"])
    test.assertEqual(result.budget_status, receipt["budget_status"])
    test.assertEqual(result.budget_status, summary["budget_status"])
    test.assertEqual(receipt["draft_id"], draft["draft_id"])
    test.assertEqual(result.receipt_path.name, f"{draft['draft_id']}.json")
    test.assertEqual(receipt["repo_root_sha256"], sha256(draft["repo_root"].encode("utf-8")))
    test.assertEqual(receipt["settings"], draft["settings"]["impact_graph"])
    test.assertEqual(summary["nodes"], len(receipt["nodes"]))
    test.assertEqual(summary["edges"], len(receipt["edges"]))
    test.assertEqual(summary["paths"], len(receipt["paths"]))
    test.assertEqual(summary["unknown_frontiers"], len(receipt["frontier"]))
    test.assertEqual(binding["receipt_id"], result.receipt_id)
    test.assertEqual(binding["sha256"], result.receipt_sha256)
    test.assertEqual(binding["request_sha256"], result.request_sha256)
    test.assertEqual(binding["settings"], receipt["settings"])
    test.assertEqual(binding["cache_key"], receipt["cache"]["key"])
    test.assertEqual(
        binding["seeds"],
        [{"term": seed.term, "location": seed.location} for seed in result.seeds],
    )


def artifact_snapshot(root):
    base = Path(root) / ".requirements-impact-refiner"
    if not base.exists():
        return {}
    snapshot = {}
    for path in sorted((base, *base.rglob("*")), key=lambda item: item.as_posix()):
        metadata = path.lstat()
        row = {
            "kind": "directory" if stat.S_ISDIR(metadata.st_mode) else "file",
            "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        }
        if stat.S_ISREG(metadata.st_mode):
            row["sha256"] = sha256(path.read_bytes())
        snapshot[path.relative_to(root).as_posix()] = row
    return snapshot


def portable_artifact_paths(root):
    result = []
    for path in artifact_snapshot(root):
        parts = []
        for part in path.split("/"):
            match = re.fullmatch(r"([0-9a-f]{64})(.*)", part)
            parts.append("<sha256>" + match.group(2) if match else part)
        result.append("/".join(parts))
    return sorted(result)


def mode_contract(root, relatives):
    return {
        relative: f"{stat.S_IMODE((Path(root) / relative).stat().st_mode):04o}"
        for relative in relatives
    }


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
        self.assertEqual(
            [
                ".requirements-impact-refiner",
                ".requirements-impact-refiner/cache and descendants",
                ".requirements-impact-refiner/reports and report-ID directories",
            ],
            self.fixture["filesystem_mode_exclusions"],
        )
        self.assertEqual(sorted(PUBLIC_NAMES), self.fixture["public_names"])
        for name in PUBLIC_NAMES:
            self.assertTrue(hasattr(CONTROLLER, name), name)

    def test_public_dataclass_contracts_match_v05_fixture(self):
        actual = {name: dataclass_contract(getattr(CONTROLLER, name)) for name in DATACLASS_NAMES}
        self.assertEqual(self.fixture["public_dataclasses"], actual)
        for name in DATACLASS_NAMES:
            with self.subTest(name=name):
                value = object.__new__(getattr(CONTROLLER, name))
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    value.contract_mutation = True

    def test_public_entry_point_contracts_match_v05_fixture(self):
        actual = {name: signature_contract(getattr(CONTROLLER, name)) for name in ENTRY_POINTS}
        self.assertEqual(self.fixture["entry_points"], actual)
        for name in ENTRY_POINTS:
            with self.subTest(name=name):
                value = getattr(CONTROLLER, name)
                self.assertTrue(callable(value))
                self.assertTrue(inspect.isfunction(value))
                self.assertEqual(value.__name__, name)
                self.assertEqual(value.__qualname__, name)

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
            "filesystem": {
                "surviving_paths": portable_artifact_paths(self.root),
                "modes": mode_contract(
                    self.root,
                    (
                        ".requirements-impact-refiner/drafts",
                        f".requirements-impact-refiner/drafts/{FIXED_DRAFT_ID}.json",
                    ),
                ),
            },
        }
        self.assertEqual(self.fixture["flows"]["begin"]["success"], actual)

        rejected_root = self.root / "rejected-begin"
        rejected_root.mkdir()
        self.root = rejected_root
        self.configure(graph_enabled=False)
        before = artifact_snapshot(self.root)
        error = captured_error(lambda: self.begin(adapter="unsupported"))
        after = artifact_snapshot(self.root)
        self.assertEqual(before, after)
        self.assertEqual(
            self.fixture["flows"]["begin"]["rejected"],
            {
                **error,
                "filesystem": {
                    "before_paths": list(before),
                    "after_paths": list(after),
                    "unchanged": before == after,
                },
            },
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
        stored_draft = CONTROLLER.load_draft(self.root, draft.draft_id)
        assert_trace_relationships(self, result, receipt_payload, stored_draft)
        for field in ("receipt_id", "receipt_sha256", "request_sha256"):
            with self.subTest(mutated_result_field=field):
                mutated = dataclasses.replace(
                    result, **{field: different_hex(getattr(result, field))}
                )
                with self.assertRaises(AssertionError):
                    assert_trace_relationships(self, mutated, receipt_payload, stored_draft)
        for field in ("receipt_id", "sha256", "request_sha256", "cache_key"):
            with self.subTest(mutated_binding_field=field):
                mutated_draft = copy.deepcopy(stored_draft)
                binding = mutated_draft["graph_receipt"]
                binding[field] = different_hex(binding[field])
                with self.assertRaises(AssertionError):
                    assert_trace_relationships(self, result, receipt_payload, mutated_draft)
        normalized = normalized_trace_result(self.root, result)
        actual = {
            "result": normalized,
            "result_canonical_sha256": sha256(canonical_bytes(normalized)),
            "receipt_canonical_sha256": sha256(normalized_receipt_bytes(receipt_payload)),
            "filesystem": {
                "surviving_paths": portable_artifact_paths(self.root),
                "modes": mode_contract(
                    self.root,
                    (
                        ".requirements-impact-refiner/drafts",
                        f".requirements-impact-refiner/drafts/{FIXED_DRAFT_ID}.json",
                        ".requirements-impact-refiner/graph",
                        f".requirements-impact-refiner/graph/{FIXED_DRAFT_ID}.json",
                        ".requirements-impact-refiner/reports/RPT-001/.controller.lock",
                    ),
                ),
            },
        }
        self.assertEqual(self.fixture["flows"]["trace"]["success"], actual)

        rejected_root = self.root / "disabled"
        rejected_root.mkdir()
        self.root = rejected_root
        self.configure(graph_enabled=False)
        rejected_draft = self.begin()
        before = artifact_snapshot(self.root)
        error = captured_error(
            lambda: CONTROLLER.trace_impact(
                CONTROLLER.TraceRequest(
                    self.root,
                    rejected_draft.draft_id,
                    (CONTROLLER.TraceSeed("profile.displayName", None),),
                )
            )
        )
        after = artifact_snapshot(self.root)
        for path, metadata in before.items():
            self.assertEqual(metadata, after[path], path)
        stored_rejected = CONTROLLER.load_draft(self.root, rejected_draft.draft_id)
        self.assertIs(stored_rejected["consumed"], False)
        published_paths = [
            path
            for path in after
            if path.startswith(
                (
                    ".requirements-impact-refiner/cache/",
                    ".requirements-impact-refiner/graph/",
                    ".requirements-impact-refiner/reports/",
                )
            )
        ]
        self.assertEqual(published_paths, [])
        self.assertEqual(
            self.fixture["flows"]["trace"]["rejected"],
            {
                **error,
                "filesystem": {
                    "before_paths": list(before),
                    "after_paths": list(after),
                    "preexisting_unchanged": all(
                        after.get(path) == metadata for path, metadata in before.items()
                    ),
                    "draft_consumed": stored_rejected["consumed"],
                    "published_paths": published_paths,
                    "modes": mode_contract(
                        self.root,
                        (
                            ".requirements-impact-refiner/drafts",
                            f".requirements-impact-refiner/drafts/{FIXED_DRAFT_ID}.json",
                            ".requirements-impact-refiner/drafts/.draft-transaction.lock",
                        ),
                    ),
                },
            },
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
        context_relative = (
            ".requirements-impact-refiner/reports/RPT-001/revision-0001.context-v2.json"
        )
        surviving_paths = portable_artifact_paths(self.root)
        self.assertIn(context_relative, surviving_paths)
        self.assertEqual(
            stat.S_IMODE((self.root / context_relative).stat().st_mode),
            0o600,
        )
        actual = {
            "analysis_fixture_sha256": sha256(analysis_payload),
            "result": result_value,
            "result_canonical_sha256": sha256(canonical_bytes(result_value)),
            "state_canonical_sha256": sha256(result.state_path.read_bytes()),
            "markdown_canonical_sha256": sha256(result.markdown_path.read_bytes()),
            "filesystem": {
                # The immutable context sidecar is an additive v0.6 artifact;
                # the sealed v0.5 facade snapshot remains byte-for-byte stable.
                "surviving_paths": [path for path in surviving_paths if path != context_relative],
                "modes": mode_contract(
                    self.root,
                    (
                        ".requirements-impact-refiner/drafts",
                        f".requirements-impact-refiner/drafts/{FIXED_DRAFT_ID}.json",
                        ".requirements-impact-refiner/reports/RPT-001/.controller.lock",
                        ".requirements-impact-refiner/reports/RPT-001/"
                        "revision-0001.controller.json",
                        ".requirements-impact-refiner/reports/RPT-001/revision-0001.json",
                        ".requirements-impact-refiner/reports/RPT-001/revision-0001.md",
                        ".requirements-impact-refiner/reports/RPT-001/current.json",
                    ),
                ),
            },
        }
        self.assertEqual(self.fixture["flows"]["finalize"]["success"], actual)

        rejected_root = self.root / "rejected"
        rejected_root.mkdir()
        self.root = rejected_root
        self.configure(graph_enabled=False)
        rejected_draft = self.begin()
        rejected_analysis = dict(analysis)
        rejected_analysis["phase"] = "unsupported"
        before = artifact_snapshot(self.root)
        error = captured_error(
            lambda: CONTROLLER.finalize_refinement(
                CONTROLLER.FinalizeRequest(self.root, rejected_draft.draft_id, rejected_analysis)
            )
        )
        after = artifact_snapshot(self.root)
        for path, metadata in before.items():
            self.assertEqual(metadata, after[path], path)
        stored_rejected = CONTROLLER.load_draft(self.root, rejected_draft.draft_id)
        self.assertIs(stored_rejected["consumed"], False)
        published_paths = [
            path
            for path in after
            if path.endswith(("current.json", ".controller.json", "revision-0001.json", ".md"))
        ]
        self.assertEqual(published_paths, [])
        self.assertEqual(
            self.fixture["flows"]["finalize"]["rejected"],
            {
                **error,
                "filesystem": {
                    "before_paths": list(before),
                    "after_paths": list(after),
                    "preexisting_unchanged": all(
                        after.get(path) == metadata for path, metadata in before.items()
                    ),
                    "draft_consumed": stored_rejected["consumed"],
                    "published_paths": published_paths,
                    "modes": mode_contract(
                        self.root,
                        (
                            ".requirements-impact-refiner/drafts",
                            f".requirements-impact-refiner/drafts/{FIXED_DRAFT_ID}.json",
                            ".requirements-impact-refiner/reports/RPT-001/.controller.lock",
                        ),
                    ),
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
