from __future__ import annotations

import copy
import hashlib
import importlib.util
import inspect
import json
import os
import stat
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SKILL_SCRIPTS = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "compact-state-post-decision.json"


def load_module(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


CONTEXT = load_module("rir_report_context_test", SCRIPTS / "rir_report_context.py")
STORE = load_module("rir_report_context_store_test", SCRIPTS / "report_store.py")
CONTROLLER = load_module("rir_report_context_controller_test", SCRIPTS / "rir_controller.py")
FINALIZE = CONTROLLER.FINALIZE


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


class RirReportContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.base_state = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def publish_report(self, revision: int = 1):
        first_state = copy.deepcopy(self.base_state)
        first = STORE.publish_revision(self.root, canonical_bytes(first_state))
        if revision == 1:
            return first
        self.assertEqual(revision, 2)
        second_state = copy.deepcopy(self.base_state)
        second_state["report"]["revision"] = 2
        second_state["report"]["previous_sha256"] = first.markdown_sha256
        second_state["delta"]["new"] = []
        second_state["delta"]["unchanged"] = ["IMP-001"]
        return STORE.publish_revision(self.root, canonical_bytes(second_state))

    def sample_context(
        self,
        *,
        revision: int = 1,
        markdown_sha256: str,
        source_inventory_sha256: str | None = "4" * 64,
        source_inventory_available: bool = True,
        source_inventory_complete: bool = True,
        baseline_commit: str | None = None,
        baseline_clean: bool = False,
    ):
        return CONTEXT.ReportContext(
            schema_version=1,
            report_id="RPT-001",
            revision=revision,
            markdown_sha256=markdown_sha256,
            repo_root_sha256=hashlib.sha256(str(self.root).encode("utf-8")).hexdigest(),
            requirement_sha256=CONTEXT.canonical_requirement_sha256("프로필 변경"),
            source_inventory_sha256=source_inventory_sha256,
            payload_sha256="5" * 64,
            created_at="2026-08-25T12:34:56.123456Z",
            baseline_commit=baseline_commit,
            baseline_clean=baseline_clean,
            source_inventory_available=source_inventory_available,
            source_inventory_complete=source_inventory_complete,
        )

    def context_path(self, revision: int = 1) -> Path:
        return (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / f"revision-{revision:04d}.context.json"
        )

    def configure_graph(self, enabled: bool) -> None:
        (self.root / ".requirements-impact-refiner.json").write_text(
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

    def begin(self, request: str = "Let workspace members edit every project."):
        return CONTROLLER.begin_refinement(
            CONTROLLER.BeginRequest(
                repo_root=self.root,
                request=request,
                repository_evidence=(
                    "authorizeProjectEdit permits owner and admin",
                    "workspace invitations default to member",
                ),
                adapter="generic",
            )
        )

    def finalize_request(self, draft, graph_receipt_id: str | None = None):
        analysis = json.loads(
            (ROOT / "tests" / "fixtures" / "controller-analysis-pre-decision.json").read_text(
                encoding="utf-8"
            )
        )
        return CONTROLLER.FinalizeRequest(
            self.root,
            draft.draft_id,
            analysis,
            graph_receipt_id,
        )

    def test_requirement_digest_is_nfc_and_whitespace_stable_without_collapsing_semantics(self):
        composed = "  프로필   Caf\u00e9\n변경  "
        decomposed = "프로필 Cafe\u0301 변경"
        self.assertEqual(
            CONTEXT.canonical_requirement_sha256(composed),
            CONTEXT.canonical_requirement_sha256(decomposed),
        )
        self.assertNotEqual(
            CONTEXT.canonical_requirement_sha256("Rename UserID"),
            CONTEXT.canonical_requirement_sha256("rename UserID"),
        )
        self.assertNotEqual(
            CONTEXT.canonical_requirement_sha256("allow foo_bar()"),
            CONTEXT.canonical_requirement_sha256("allow fooBar()"),
        )
        expected = hashlib.sha256(
            unicodedata.normalize("NFC", "프로필 Caf\u00e9 변경").encode("utf-8")
        ).hexdigest()
        self.assertEqual(CONTEXT.canonical_requirement_sha256(composed), expected)

    def test_requirement_digest_rejects_blank_nontext_and_oversized_requests(self):
        for request in ("", " \n\t ", None, b"request", "x" * (64 * 1024 + 1)):
            with self.subTest(request_type=type(request).__name__):
                with self.assertRaises((TypeError, ValueError)):
                    CONTEXT.canonical_requirement_sha256(request)

    def test_context_is_bound_to_one_published_revision_with_canonical_private_bytes(self):
        published = self.publish_report(revision=2)
        context = self.sample_context(
            revision=2,
            markdown_sha256=published.markdown_sha256,
        )

        path = CONTEXT.publish_report_context(self.root, context)

        self.assertEqual(path.name, "revision-0002.context.json")
        self.assertEqual(CONTEXT.load_report_context(self.root, "RPT-001", 2), context)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(path.stat().st_nlink, 1)
        self.assertEqual(
            path.read_bytes(),
            canonical_bytes(
                {
                    "baseline_clean": False,
                    "baseline_commit": None,
                    "created_at": "2026-08-25T12:34:56.123456Z",
                    "markdown_sha256": published.markdown_sha256,
                    "payload_sha256": "5" * 64,
                    "repo_root_sha256": hashlib.sha256(str(self.root).encode("utf-8")).hexdigest(),
                    "report_id": "RPT-001",
                    "requirement_sha256": CONTEXT.canonical_requirement_sha256("프로필 변경"),
                    "revision": 2,
                    "schema_version": 1,
                    "source_inventory_available": True,
                    "source_inventory_complete": True,
                    "source_inventory_sha256": "4" * 64,
                }
            ),
        )
        self.assertEqual(CONTEXT.publish_report_context(self.root, context), path)

    def test_inventory_unavailable_and_incomplete_are_explicit_and_never_complete(self):
        published = self.publish_report()
        unavailable = self.sample_context(
            markdown_sha256=published.markdown_sha256,
            source_inventory_sha256=None,
            source_inventory_available=False,
            source_inventory_complete=False,
        )
        self.assertEqual(
            CONTEXT.load_report_context(
                self.root,
                "RPT-001",
                1,
            ),
            None,
        )
        path = CONTEXT.publish_report_context(self.root, unavailable)
        self.assertEqual(CONTEXT.load_report_context(self.root, "RPT-001", 1), unavailable)
        path.unlink()

        incomplete = self.sample_context(
            markdown_sha256=published.markdown_sha256,
            source_inventory_available=True,
            source_inventory_complete=False,
        )
        CONTEXT.publish_report_context(self.root, incomplete)
        self.assertEqual(CONTEXT.load_report_context(self.root, "RPT-001", 1), incomplete)

        invalid_combinations = (
            {"source_inventory_available": False, "source_inventory_complete": True},
            {
                "source_inventory_sha256": "4" * 64,
                "source_inventory_available": False,
                "source_inventory_complete": False,
            },
            {
                "source_inventory_sha256": None,
                "source_inventory_available": True,
                "source_inventory_complete": False,
            },
        )
        for changes in invalid_combinations:
            values = {
                "markdown_sha256": published.markdown_sha256,
                "source_inventory_sha256": None,
                "source_inventory_available": False,
                "source_inventory_complete": False,
            }
            values.update(changes)
            with self.subTest(changes=changes):
                with self.assertRaises((TypeError, ValueError)):
                    self.sample_context(**values)

    def test_context_value_contract_rejects_wrong_types_bounds_and_git_claims(self):
        valid = self.sample_context(markdown_sha256="0" * 64)
        cases = (
            {"schema_version": True},
            {"report_id": "RPT-01"},
            {"revision": 10_000},
            {"markdown_sha256": "A" * 64},
            {"source_inventory_available": 1},
            {"source_inventory_complete": 1},
            {"created_at": "2026-08-25"},
            {"baseline_commit": "not-a-commit"},
            {"baseline_clean": 1},
            {"baseline_clean": True, "baseline_commit": None},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises((TypeError, ValueError)):
                    replace(valid, **changes)

    def test_missing_report_and_unsafe_repository_roots_fail_conservatively(self):
        self.assertIsNone(CONTEXT.load_report_context(self.root, "RPT-001", 1))
        alias = self.root.parent / f"{self.root.name}-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        try:
            with self.assertRaises(ValueError):
                CONTEXT.repo_root_sha256(alias)
        finally:
            alias.unlink()
        unavailable = self.root / "missing"
        with self.assertRaises(ValueError):
            CONTEXT.repo_root_sha256(unavailable)

    def test_legacy_missing_context_returns_none_but_invalid_identity_fails_closed(self):
        published = self.publish_report()
        self.assertIsNone(CONTEXT.load_report_context(self.root, "RPT-001", 1))
        for report_id, revision in (("../escape", 1), ("RPT-001", 0), ("RPT-001", True)):
            with self.subTest(report_id=report_id, revision=revision):
                with self.assertRaises((TypeError, ValueError)):
                    CONTEXT.load_report_context(self.root, report_id, revision)
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        with self.assertRaises((TypeError, ValueError)):
            CONTEXT.publish_report_context(self.root, replace(context, report_id="bad"))

    def test_load_fails_closed_for_noncanonical_tampered_nonprivate_and_linked_sidecars(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = CONTEXT.publish_report_context(self.root, context)
        baseline = json.loads(path.read_text(encoding="utf-8"))
        mutations = {
            "invalid-utf8": b"\xff",
            "noncanonical": json.dumps(baseline, ensure_ascii=False, indent=2).encode("utf-8"),
            "unknown-field": canonical_bytes(dict(baseline, extra=True)),
            "wrong-revision": canonical_bytes(dict(baseline, revision=2)),
            "wrong-markdown-digest": canonical_bytes(dict(baseline, markdown_sha256="0" * 64)),
        }
        for name, payload in mutations.items():
            with self.subTest(name=name):
                path.write_bytes(payload)
                os.chmod(path, 0o600)
                with self.assertRaises(ValueError):
                    CONTEXT.load_report_context(self.root, "RPT-001", 1)
                path.write_bytes(canonical_bytes(baseline))
                os.chmod(path, 0o600)

        os.chmod(path, 0o644)
        with self.assertRaises(ValueError):
            CONTEXT.load_report_context(self.root, "RPT-001", 1)
        os.chmod(path, 0o600)

        hardlink = path.with_name("context-hardlink")
        os.link(path, hardlink)
        try:
            with self.assertRaises(ValueError):
                CONTEXT.load_report_context(self.root, "RPT-001", 1)
        finally:
            hardlink.unlink()

        payload = path.read_bytes()
        path.unlink()
        outside = self.root / "outside-context.json"
        outside.write_bytes(payload)
        outside.chmod(0o600)
        path.symlink_to(outside)
        with self.assertRaises(ValueError):
            CONTEXT.load_report_context(self.root, "RPT-001", 1)

    def test_markdown_tamper_and_existing_context_mismatch_fail_closed(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = CONTEXT.publish_report_context(self.root, context)
        published.markdown_path.write_bytes(published.markdown_path.read_bytes() + b"tamper")
        with self.assertRaises(ValueError):
            CONTEXT.load_report_context(self.root, "RPT-001", 1)
        with self.assertRaises(ValueError):
            CONTEXT.publish_report_context(self.root, context)

        published.markdown_path.write_bytes(
            published.markdown_path.read_bytes().removesuffix(b"tamper")
        )
        replacement = json.loads(path.read_text(encoding="utf-8"))
        replacement["payload_sha256"] = "6" * 64
        path.write_bytes(canonical_bytes(replacement))
        os.chmod(path, 0o600)
        with self.assertRaises(FileExistsError):
            CONTEXT.publish_report_context(self.root, context)

    def test_git_baseline_proves_only_a_clean_local_commit_and_ignores_host_git_env(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "rir@example.invalid"], cwd=self.root, check=True
        )
        subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=self.root, check=True)
        tracked = self.root / "tracked.txt"
        tracked.write_text("stable\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=self.root, check=True)
        expected = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        with mock.patch.dict(
            os.environ,
            {"GIT_DIR": "/untrusted/git-dir", "GIT_WORK_TREE": "/untrusted/work-tree"},
        ):
            self.assertEqual(CONTEXT.probe_git_baseline(self.root), (expected, True))

        tracked.write_text("dirty\n", encoding="utf-8")
        self.assertEqual(CONTEXT.probe_git_baseline(self.root), (expected, False))

    def test_non_git_and_git_execution_failure_are_unproven_not_errors(self):
        self.assertEqual(CONTEXT.probe_git_baseline(self.root), (None, False))
        with mock.patch.object(CONTEXT, "_run_git", return_value=None):
            self.assertEqual(CONTEXT.probe_git_baseline(self.root), (None, False))
        with mock.patch.object(CONTEXT.subprocess, "Popen", side_effect=OSError("blocked")):
            self.assertEqual(CONTEXT.probe_git_baseline(self.root), (None, False))
        with mock.patch.object(
            CONTEXT.selectors,
            "DefaultSelector",
            side_effect=OSError("selector unavailable"),
        ):
            self.assertEqual(CONTEXT.probe_git_baseline(self.root), (None, False))
        with mock.patch.object(
            CONTEXT.selectors.DefaultSelector,
            "select",
            side_effect=OSError("selector failed"),
        ):
            self.assertEqual(CONTEXT.probe_git_baseline(self.root), (None, False))

    def test_unsafe_git_output_fails_instead_of_becoming_a_false_clean_proof(self):
        with mock.patch.object(
            CONTEXT,
            "_run_git",
            return_value=(0, b"a" * 40 + b"\0"),
        ):
            with self.assertRaises(CONTEXT.UnsafeGitOutput):
                CONTEXT.probe_git_baseline(self.root)

        self.configure_graph(False)
        draft = self.begin("Unsafe Git output cannot publish context.")
        request = self.finalize_request(draft)
        runtime = dict(FINALIZE.default_runtime())
        runtime["probe_git_baseline"] = mock.Mock(
            side_effect=CONTEXT.UnsafeGitOutput("oversized output")
        )
        with self.assertRaisesRegex(CONTEXT.UnsafeGitOutput, "oversized output"):
            FINALIZE.finalize_refinement(request, _runtime=runtime)
        self.assertIsNone(FINALIZE.REPORT_STORE.load_current(self.root, "RPT-001"))
        self.assertFalse(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

    def test_finalize_publishes_unavailable_context_after_report_readback_before_consumption(self):
        self.configure_graph(False)
        draft = self.begin("  Allow   Profile\nEditing ")
        request = self.finalize_request(draft)
        runtime = dict(FINALIZE.default_runtime())
        events: list[str] = []

        def record(name: str, operation):
            def wrapped(*args, **kwargs):
                events.append(name)
                return operation(*args, **kwargs)

            return wrapped

        for name, event in (
            ("write_controller_metadata", "metadata"),
            ("publish_revision", "report"),
            ("load_state_bytes", "readback"),
            ("publish_report_context", "context"),
            ("consume_draft", "consume"),
        ):
            runtime[name] = record(event, runtime[name])

        result = FINALIZE.finalize_refinement(request, _runtime=runtime)

        self.assertEqual(events, ["metadata", "report", "readback", "context", "consume"])
        context = CONTEXT.load_report_context(self.root, result.report_id, result.revision)
        self.assertIsNotNone(context)
        self.assertEqual(context.markdown_sha256, result.markdown_sha256)
        self.assertEqual(
            context.requirement_sha256,
            CONTEXT.canonical_requirement_sha256("Allow Profile Editing"),
        )
        self.assertEqual(context.payload_sha256, FINALIZE._payload_sha256())
        self.assertFalse(context.source_inventory_available)
        self.assertFalse(context.source_inventory_complete)
        self.assertIsNone(context.source_inventory_sha256)
        self.assertIsNone(context.baseline_commit)
        self.assertFalse(context.baseline_clean)
        self.assertTrue(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])
        self.assertEqual(
            tuple(inspect.signature(CONTROLLER.finalize_refinement).parameters),
            ("request",),
        )
        self.assertIs(type(result), runtime["result_type"])

    def test_incomplete_graph_inventory_is_persisted_as_available_but_not_complete(self):
        self.configure_graph(True)
        draft = self.begin("Profile graph inventory is incomplete.")
        request = self.finalize_request(draft)
        runtime = dict(FINALIZE.default_runtime())
        digest = "7" * 64
        runtime["load_graph_context"] = lambda *args: {
            "receipt": {"receipt_id": "9" * 32},
            "sha256": "8" * 64,
            "binding": {
                "source_inventory_sha256": digest,
                "source_inventory_complete": False,
                "source_inventory_reason": "deadline",
            },
        }
        runtime["validate_analysis"] = lambda *args: None
        runtime["validate_graph_coverage"] = lambda *args: None
        runtime["build_state"] = lambda selected_draft, analysis, graph: (
            FINALIZE.LINEAGE.build_state(selected_draft, analysis, None)
        )

        result = FINALIZE.finalize_refinement(request, _runtime=runtime)

        context = CONTEXT.load_report_context(self.root, result.report_id, result.revision)
        self.assertEqual(context.source_inventory_sha256, digest)
        self.assertTrue(context.source_inventory_available)
        self.assertFalse(context.source_inventory_complete)

    def test_promoted_scan_context_uses_the_verified_complete_source_inventory(self):
        self.configure_graph(True)
        (self.root / "api").mkdir()
        (self.root / "api" / "profile.py").write_text(
            'FIELD = "profile.displayName"\n', encoding="utf-8"
        )
        scan = CONTROLLER.scan_impact(
            CONTROLLER.ScanRequest(self.root, "Rename profile.displayName", (), "balanced")
        )
        draft = CONTROLLER.begin_refinement(
            CONTROLLER.BeginRequest(
                self.root,
                "Rename profile.displayName",
                (),
                "generic",
                scan_id=scan.scan_id,
            )
        )
        request = self.finalize_request(draft, scan.receipt_id)
        request.analysis["impacts"][0]["graph_path_keys"] = [row["id"] for row in scan.paths]
        if not request.analysis["impacts"][0]["graph_path_keys"]:
            request.analysis["impacts"][0]["coverage_rationale"] = (
                "Fast Scan found no closed repository path."
            )
        request.analysis["impacts"][0]["evidence_level"] = "unknown"

        result = FINALIZE.finalize_refinement(request)

        receipt = json.loads(
            (
                self.root / ".requirements-impact-refiner" / "scans" / f"{scan.scan_id}.json"
            ).read_text(encoding="utf-8")
        )
        inventory = receipt["source_inventory"]
        context = CONTEXT.load_report_context(self.root, result.report_id, result.revision)
        self.assertEqual(
            context.source_inventory_sha256,
            FINALIZE.GRAPH_DELIVERY.source_inventory_sha256(inventory["digests"]),
        )
        self.assertTrue(context.source_inventory_available)
        self.assertIs(context.source_inventory_complete, inventory["complete"])

    def test_context_failure_leaves_published_report_and_unconsumed_draft_for_retry(self):
        self.configure_graph(False)
        draft = self.begin("Context failure remains retryable.")
        request = self.finalize_request(draft)
        runtime = dict(FINALIZE.default_runtime())
        runtime["publish_report_context"] = mock.Mock(
            side_effect=ValueError("injected context failure")
        )

        with self.assertRaisesRegex(ValueError, "^injected context failure$"):
            FINALIZE.finalize_refinement(request, _runtime=runtime)

        published = FINALIZE.REPORT_STORE.load_current(self.root, "RPT-001")
        self.assertIsNotNone(published)
        self.assertIsNone(CONTEXT.load_report_context(self.root, "RPT-001", 1))
        self.assertFalse(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

        result = FINALIZE.finalize_refinement(request)
        self.assertEqual(result.markdown_sha256, published.markdown_sha256)
        self.assertIsNotNone(CONTEXT.load_report_context(self.root, "RPT-001", 1))
        self.assertTrue(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

    def test_retry_reuses_an_exact_context_written_before_process_interruption(self):
        self.configure_graph(False)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "rir@example.invalid"], cwd=self.root, check=True
        )
        subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_text(
            ".requirements-impact-refiner/\n.requirements-impact-refiner.json\n",
            encoding="utf-8",
        )
        tracked = self.root / "tracked.txt"
        tracked.write_text("stable\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore", "tracked.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=self.root, check=True)
        draft = self.begin("Persist context before interruption.")
        request = self.finalize_request(draft)
        runtime = dict(FINALIZE.default_runtime())
        real_publish = runtime["publish_report_context"]

        class SimulatedInterruption(BaseException):
            pass

        def publish_then_interrupt(root, context):
            real_publish(root, context)
            raise SimulatedInterruption("after context link")

        runtime["publish_report_context"] = publish_then_interrupt
        with self.assertRaises(SimulatedInterruption):
            FINALIZE.finalize_refinement(request, _runtime=runtime)

        first = CONTEXT.load_report_context(self.root, "RPT-001", 1)
        self.assertTrue(first.baseline_clean)
        self.assertFalse(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])
        tracked.write_text("dirty after context\n", encoding="utf-8")

        FINALIZE.finalize_refinement(request)

        self.assertEqual(CONTEXT.load_report_context(self.root, "RPT-001", 1), first)
        self.assertTrue(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

    def test_finalize_resolves_its_local_context_dependency_under_foreign_aliases(self):
        script = r"""
import importlib.util
import sys
import types
from pathlib import Path

root_scripts = Path(sys.argv[1]).resolve()
skill_scripts = Path(sys.argv[2]).resolve()

def load(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module

foreign = types.ModuleType("rir_report_context")
foreign.__file__ = "/foreign/rir_report_context.py"
foreign.publish_report_context = lambda *args: (_ for _ in ()).throw(
    AssertionError("foreign context used")
)
sys.modules["rir_report_context"] = foreign

root = load("context_conflict_root_finalize", root_scripts / "rir_finalize.py")
skill = load("context_conflict_skill_finalize", skill_scripts / "rir_finalize.py")
assert sys.modules["rir_report_context"] is foreign
assert Path(root.REPORT_CONTEXT.__file__).resolve() == (root_scripts / "rir_report_context.py")
assert Path(skill.REPORT_CONTEXT.__file__).resolve() == (skill_scripts / "rir_report_context.py")
assert root.REPORT_CONTEXT is not skill.REPORT_CONTEXT
assert root.default_runtime()["publish_report_context"] is root.REPORT_CONTEXT.publish_report_context
assert skill.default_runtime()["load_report_context"] is skill.REPORT_CONTEXT.load_report_context
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(SCRIPTS), str(SKILL_SCRIPTS)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_root_and_skill_context_payloads_are_byte_identical(self):
        self.assertEqual(
            (SCRIPTS / "rir_report_context.py").read_bytes(),
            (SKILL_SCRIPTS / "rir_report_context.py").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
