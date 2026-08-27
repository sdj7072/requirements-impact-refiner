from __future__ import annotations

import copy
import hashlib
import importlib.util
import inspect
import json
import os
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
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
        source_inventory_git_tracked_only: bool = False,
        required_source_digests: dict[str, str] | None = None,
        source_recheck_complete: bool = False,
        baseline_commit: str | None = None,
        baseline_clean: bool = False,
        state_sha256: str | None = None,
    ):
        state_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / f"revision-{revision:04d}.json"
        )
        if state_sha256 is None:
            state_payload = (
                state_path.read_bytes()
                if state_path.is_file()
                else canonical_bytes(self.base_state)
            )
            state_sha256 = hashlib.sha256(state_payload).hexdigest()
        return CONTEXT.ReportContext(
            schema_version=2,
            report_id="RPT-001",
            revision=revision,
            markdown_sha256=markdown_sha256,
            state_sha256=state_sha256,
            repo_root_sha256=hashlib.sha256(str(self.root).encode("utf-8")).hexdigest(),
            requirement_sha256=CONTEXT.canonical_requirement_sha256("프로필 변경"),
            repository_evidence_sha256=CONTEXT.canonical_repository_evidence_sha256(()),
            source_inventory_sha256=source_inventory_sha256,
            payload_sha256="5" * 64,
            created_at="2026-08-25T12:34:56.123456Z",
            baseline_commit=baseline_commit,
            baseline_clean=baseline_clean,
            source_inventory_available=source_inventory_available,
            source_inventory_complete=source_inventory_complete,
            source_inventory_git_tracked_only=source_inventory_git_tracked_only,
            required_source_digests=required_source_digests,
            source_recheck_complete=source_recheck_complete,
        )

    def context_path(self, revision: int = 1) -> Path:
        return (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / f"revision-{revision:04d}.context-v2.json"
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

    def test_v2_context_binds_state_evidence_and_tracked_source_proof(self):
        published = self.publish_report()
        state_sha256 = hashlib.sha256(published.state_path.read_bytes()).hexdigest()
        evidence_sha256 = hashlib.sha256(b'["row one","row one","row two"]').hexdigest()
        context = CONTEXT.ReportContext(
            schema_version=2,
            report_id="RPT-001",
            revision=1,
            markdown_sha256=published.markdown_sha256,
            state_sha256=state_sha256,
            repo_root_sha256=hashlib.sha256(str(self.root).encode("utf-8")).hexdigest(),
            requirement_sha256=CONTEXT.canonical_requirement_sha256("프로필 변경"),
            repository_evidence_sha256=evidence_sha256,
            source_inventory_sha256="4" * 64,
            payload_sha256="5" * 64,
            created_at="2026-08-25T12:34:56Z",
            baseline_commit=None,
            baseline_clean=False,
            source_inventory_available=True,
            source_inventory_complete=True,
            source_inventory_git_tracked_only=False,
            required_source_digests={"z.py": "7" * 64, "a.py": "6" * 64},
            source_recheck_complete=True,
        )

        path = CONTEXT.publish_report_context(self.root, context)

        self.assertEqual(path.name, "revision-0001.context-v2.json")
        self.assertEqual(CONTEXT.load_report_context(self.root, "RPT-001", 1), context)
        self.assertEqual(list(context.required_source_digests), ["a.py", "z.py"])

    def test_pre_recheck_v2_context_migrates_to_incomplete_source_recheck(self):
        published = self.publish_report()
        context = self.sample_context(
            markdown_sha256=published.markdown_sha256,
            required_source_digests={"app.py": "6" * 64},
            source_recheck_complete=True,
        )
        path = CONTEXT.publish_report_context(self.root, context)
        payload = json.loads(path.read_text(encoding="utf-8"))
        del payload["required_source_digests"]
        del payload["source_recheck_complete"]
        path.write_bytes(canonical_bytes(payload))

        migrated = CONTEXT.load_report_context(self.root, "RPT-001", 1)

        self.assertIsNotNone(migrated)
        self.assertIsNone(migrated.required_source_digests)
        self.assertFalse(migrated.source_recheck_complete)

    def test_required_source_digest_map_is_canonical_and_bounded(self):
        published = self.publish_report()
        context = self.sample_context(
            markdown_sha256=published.markdown_sha256,
            required_source_digests={"z.py": "7" * 64, "a.py": "6" * 64},
            source_recheck_complete=True,
        )

        self.assertEqual(list(context.required_source_digests), ["a.py", "z.py"])
        with self.assertRaisesRegex(ValueError, "required source digest map"):
            replace(context, required_source_digests=None, source_recheck_complete=True)
        with mock.patch.object(CONTEXT, "MAX_REQUIRED_SOURCE_DIGESTS", 1):
            with self.assertRaisesRegex(ValueError, "count limit"):
                replace(
                    context,
                    required_source_digests={"a.py": "6" * 64, "z.py": "7" * 64},
                )
        with mock.patch.object(CONTEXT, "MAX_REQUIRED_SOURCE_PATH_BYTES", 4):
            with self.assertRaisesRegex(ValueError, "path byte limit"):
                replace(context, required_source_digests={"long.py": "6" * 64})
        with mock.patch.object(CONTEXT, "MAX_REQUIRED_SOURCE_MAP_BYTES", 2):
            with self.assertRaisesRegex(ValueError, "serialized byte limit"):
                replace(context, required_source_digests={"a.py": "6" * 64})
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            replace(context, required_source_digests={"bad\ud800.py": "6" * 64})

    def test_repository_evidence_digest_preserves_order_and_duplicates(self):
        first = CONTEXT.canonical_repository_evidence_sha256(("alpha", "alpha", "beta"))
        reordered = CONTEXT.canonical_repository_evidence_sha256(("beta", "alpha", "alpha"))
        deduplicated = CONTEXT.canonical_repository_evidence_sha256(("alpha", "beta"))

        self.assertNotEqual(first, reordered)
        self.assertNotEqual(first, deduplicated)
        self.assertEqual(
            first,
            hashlib.sha256(b'["alpha","alpha","beta"]').hexdigest(),
        )
        for invalid in ("text", b"bytes", [""], [1]):
            with self.subTest(invalid=invalid):
                with self.assertRaises((TypeError, ValueError)):
                    CONTEXT.canonical_repository_evidence_sha256(invalid)
        with mock.patch.object(CONTEXT, "MAX_EVIDENCE_ROW_BYTES", 2):
            with self.assertRaisesRegex(ValueError, "64 KiB"):
                CONTEXT.canonical_repository_evidence_sha256(("long",))
        with mock.patch.object(CONTEXT, "MAX_EVIDENCE_BYTES", 2):
            with self.assertRaisesRegex(ValueError, "256 KiB"):
                CONTEXT.canonical_repository_evidence_sha256(("row",))

    def test_v1_context_artifact_does_not_block_v2_publication(self):
        published = self.publish_report()
        report_dir = published.state_path.parent
        old = report_dir / "revision-0001.context.json"
        old.write_text('{"schema_version":1}\n', encoding="utf-8")
        os.chmod(old, 0o600)
        self.assertIsNone(CONTEXT.load_report_context(self.root, "RPT-001", 1))
        state_sha256 = hashlib.sha256(published.state_path.read_bytes()).hexdigest()
        context = CONTEXT.ReportContext(
            schema_version=2,
            report_id="RPT-001",
            revision=1,
            markdown_sha256=published.markdown_sha256,
            state_sha256=state_sha256,
            repo_root_sha256=hashlib.sha256(str(self.root).encode("utf-8")).hexdigest(),
            requirement_sha256=CONTEXT.canonical_requirement_sha256("프로필 변경"),
            repository_evidence_sha256=CONTEXT.canonical_repository_evidence_sha256(()),
            source_inventory_sha256=None,
            payload_sha256="5" * 64,
            created_at="2026-08-25T12:34:56Z",
            baseline_commit=None,
            baseline_clean=False,
            source_inventory_available=False,
            source_inventory_complete=False,
            source_inventory_git_tracked_only=False,
        )

        path = CONTEXT.publish_report_context(self.root, context)

        self.assertTrue(old.is_file())
        self.assertEqual(path.name, "revision-0001.context-v2.json")

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

    def promoted_finalize_case(self):
        self.configure_graph(True)
        (self.root / "api").mkdir()
        source = self.root / "api" / "profile.py"
        source.write_text('FIELD = "profile.displayName"\n', encoding="utf-8")
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
        return source, scan, draft, request

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

    def test_requirement_bounds_apply_after_normalization_and_match_begin_admission(self):
        self.configure_graph(False)
        whitespace_heavy = " " * (64 * 1024 + 1) + "프로필   변경"
        self.assertEqual(
            CONTEXT.canonical_requirement_sha256(whitespace_heavy),
            CONTEXT.canonical_requirement_sha256("프로필 변경"),
        )
        draft = self.begin(whitespace_heavy)
        self.assertEqual(
            CONTROLLER.load_draft(self.root, draft.draft_id)["request"], whitespace_heavy
        )

        exact_normalized = "x" * (64 * 1024)
        CONTEXT.canonical_requirement_sha256(exact_normalized)
        self.begin(exact_normalized)
        semantic_overflow = exact_normalized + "x"
        with self.assertRaisesRegex(ValueError, "64 KiB"):
            CONTEXT.canonical_requirement_sha256(semantic_overflow)
        with self.assertRaisesRegex(ValueError, "64 KiB"):
            self.begin(semantic_overflow)

        raw_overflow = " " * (256 * 1024 + 1) + "small"
        with self.assertRaisesRegex(ValueError, "256 KiB"):
            CONTEXT.canonical_requirement_sha256(raw_overflow)
        with self.assertRaisesRegex(ValueError, "256 KiB"):
            self.begin(raw_overflow)

    def test_context_is_bound_to_one_published_revision_with_canonical_private_bytes(self):
        published = self.publish_report(revision=2)
        context = self.sample_context(
            revision=2,
            markdown_sha256=published.markdown_sha256,
        )

        path = CONTEXT.publish_report_context(self.root, context)

        self.assertEqual(path.name, "revision-0002.context-v2.json")
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
                    "state_sha256": hashlib.sha256(published.state_path.read_bytes()).hexdigest(),
                    "payload_sha256": "5" * 64,
                    "repo_root_sha256": hashlib.sha256(str(self.root).encode("utf-8")).hexdigest(),
                    "report_id": "RPT-001",
                    "required_source_digests": None,
                    "requirement_sha256": CONTEXT.canonical_requirement_sha256("프로필 변경"),
                    "repository_evidence_sha256": CONTEXT.canonical_repository_evidence_sha256(()),
                    "revision": 2,
                    "schema_version": 2,
                    "source_inventory_available": True,
                    "source_inventory_complete": True,
                    "source_inventory_git_tracked_only": False,
                    "source_inventory_sha256": "4" * 64,
                    "source_recheck_complete": False,
                }
            ),
        )
        self.assertEqual(CONTEXT.publish_report_context(self.root, context), path)

    def test_context_link_cleanup_precedes_the_durable_directory_fsync(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        events: list[str] = []
        linked = False
        real_link = CONTEXT.os.link
        real_unlink = CONTEXT.os.unlink
        real_fsync = CONTEXT.os.fsync

        def recording_link(*args, **kwargs):
            nonlocal linked
            result = real_link(*args, **kwargs)
            linked = True
            events.append("link")
            return result

        def recording_unlink(*args, **kwargs):
            if linked:
                events.append("unlink")
            return real_unlink(*args, **kwargs)

        def recording_fsync(descriptor):
            if linked:
                events.append("fsync")
            return real_fsync(descriptor)

        with (
            mock.patch.object(CONTEXT.os, "link", side_effect=recording_link),
            mock.patch.object(CONTEXT.os, "unlink", side_effect=recording_unlink),
            mock.patch.object(CONTEXT.os, "fsync", side_effect=recording_fsync),
        ):
            path = CONTEXT.publish_report_context(self.root, context)

        self.assertEqual(events, ["link", "unlink", "fsync"])
        self.assertEqual(path.stat().st_nlink, 1)

    def test_context_unlink_failure_is_retryable_and_never_returns_nlink_two(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = self.context_path()
        real_unlink = CONTEXT.os.unlink

        def failing_context_unlink(name, *args, **kwargs):
            if str(name).endswith(".pending"):
                raise OSError("injected context cleanup failure")
            return real_unlink(name, *args, **kwargs)

        with mock.patch.object(CONTEXT.os, "unlink", side_effect=failing_context_unlink):
            with self.assertRaisesRegex(ValueError, "cleanup"):
                CONTEXT.publish_report_context(self.root, context)

        self.assertEqual(path.stat().st_nlink, 2)
        pending = path.parent / f".{path.name}.pending"
        self.assertTrue(pending.is_file())

        self.assertEqual(CONTEXT.publish_report_context(self.root, context), path)
        self.assertEqual(path.stat().st_nlink, 1)
        self.assertFalse(pending.exists())

    def test_partial_context_stage_is_reader_invisible_and_does_not_block_retry(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = self.context_path()
        pending = path.parent / f".{path.name}.pending"
        real_write = CONTEXT.os.write
        interrupted = False

        class SimulatedCrash(BaseException):
            pass

        def crashing_write(descriptor, payload):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                real_write(descriptor, payload[:7])
                raise SimulatedCrash("context stage write interrupted")
            return real_write(descriptor, payload)

        with mock.patch.object(CONTEXT.os, "write", side_effect=crashing_write):
            with self.assertRaises(SimulatedCrash):
                CONTEXT.publish_report_context(self.root, context)

        stages = tuple(path.parent.glob(f".{path.name}.stage-*"))
        self.assertEqual(len(stages), 1)
        self.assertEqual(stages[0].read_bytes(), b'{"basel')
        self.assertFalse(path.exists())
        self.assertFalse(pending.exists())
        self.assertIsNone(CONTEXT.load_report_context(self.root, "RPT-001", 1))

        with mock.patch.object(
            CONTEXT.os,
            "scandir",
            side_effect=AssertionError("stage retry must not scan the report lineage"),
        ):
            self.assertEqual(CONTEXT.publish_report_context(self.root, context), path)

        self.assertEqual(CONTEXT.load_report_context(self.root, "RPT-001", 1), context)
        self.assertTrue(stages[0].exists())

    def test_context_stage_collision_preserves_foreign_file_and_uses_another_candidate(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = self.context_path()
        real_open = CONTEXT.os.open
        foreign_names = []

        def collide_once(name, flags, *args, **kwargs):
            if str(name).startswith(f".{path.name}.stage-") and not foreign_names:
                descriptor = real_open(name, flags, *args, **kwargs)
                real_write = os.write
                real_write(descriptor, b"foreign-stage")
                os.close(descriptor)
                foreign_names.append(str(name))
                raise FileExistsError(str(name))
            return real_open(name, flags, *args, **kwargs)

        with (
            mock.patch.object(CONTEXT.os, "open", side_effect=collide_once),
            mock.patch.object(
                CONTEXT.os,
                "scandir",
                side_effect=AssertionError("stage creation must not scan the report lineage"),
            ),
        ):
            self.assertEqual(CONTEXT.publish_report_context(self.root, context), path)

        self.assertEqual(len(foreign_names), 1)
        foreign = path.parent / foreign_names[0]
        self.assertEqual(foreign.read_bytes(), b"foreign-stage")
        self.assertEqual(CONTEXT.load_report_context(self.root, "RPT-001", 1), context)

    def test_context_stage_candidate_collisions_are_bounded(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = self.context_path()
        real_open = CONTEXT.os.open
        attempts = 0

        def colliding_open(name, flags, *args, **kwargs):
            nonlocal attempts
            if str(name).startswith(f".{path.name}.stage-"):
                attempts += 1
                if attempts > 16:
                    raise AssertionError("context stage candidate loop is unbounded")
                raise FileExistsError(str(name))
            return real_open(name, flags, *args, **kwargs)

        with mock.patch.object(CONTEXT.os, "open", side_effect=colliding_open):
            with self.assertRaisesRegex(ValueError, "candidate limit"):
                CONTEXT.publish_report_context(self.root, context)

        self.assertGreater(attempts, 0)
        self.assertLessEqual(attempts, 16)
        self.assertFalse(path.exists())
        self.assertFalse((path.parent / f".{path.name}.pending").exists())

    def test_context_stage_cleanup_never_deletes_a_foreign_replacement(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = self.context_path()
        real_open = CONTEXT.os.open
        real_write = CONTEXT.os.write
        stage_name = None
        stage_directory_fd = None

        def recording_open(name, flags, *args, **kwargs):
            nonlocal stage_name, stage_directory_fd
            descriptor = real_open(name, flags, *args, **kwargs)
            if str(name).startswith(f".{path.name}.stage-"):
                stage_name = str(name)
                stage_directory_fd = kwargs["dir_fd"]
            return descriptor

        def replace_stage_then_fail(descriptor, payload):
            self.assertIsNotNone(stage_name)
            self.assertIsNotNone(stage_directory_fd)
            real_write(descriptor, payload[:5])
            os.unlink(stage_name, dir_fd=stage_directory_fd)
            foreign_fd = real_open(
                stage_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=stage_directory_fd,
            )
            try:
                real_write(foreign_fd, b"foreign-replacement")
            finally:
                os.close(foreign_fd)
            raise OSError("injected context stage failure after foreign replacement")

        with (
            mock.patch.object(CONTEXT.os, "open", side_effect=recording_open),
            mock.patch.object(CONTEXT.os, "write", side_effect=replace_stage_then_fail),
        ):
            with self.assertRaisesRegex(ValueError, "stage"):
                CONTEXT.publish_report_context(self.root, context)

        foreign = path.parent / str(stage_name)
        self.assertEqual(foreign.read_bytes(), b"foreign-replacement")
        self.assertFalse(path.exists())
        self.assertFalse((path.parent / f".{path.name}.pending").exists())
        self.assertEqual(CONTEXT.publish_report_context(self.root, context), path)

    def test_context_stage_cleanup_failure_leaves_no_authority_and_retry_succeeds(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = self.context_path()
        pending = path.parent / f".{path.name}.pending"
        real_write = CONTEXT.os.write
        real_unlink = CONTEXT.os.unlink
        failed_write = False

        def failing_write(descriptor, payload):
            nonlocal failed_write
            if not failed_write:
                failed_write = True
                real_write(descriptor, payload[:9])
                raise OSError("injected context stage write failure")
            return real_write(descriptor, payload)

        def failing_stage_unlink(name, *args, **kwargs):
            if str(name).startswith(f".{path.name}.stage-"):
                raise OSError("injected context stage cleanup failure")
            return real_unlink(name, *args, **kwargs)

        with (
            mock.patch.object(CONTEXT.os, "write", side_effect=failing_write),
            mock.patch.object(CONTEXT.os, "unlink", side_effect=failing_stage_unlink),
        ):
            with self.assertRaisesRegex(ValueError, "stage"):
                CONTEXT.publish_report_context(self.root, context)

        stages = tuple(path.parent.glob(f".{path.name}.stage-*"))
        self.assertEqual(len(stages), 1)
        self.assertFalse(path.exists())
        self.assertFalse(pending.exists())
        self.assertEqual(CONTEXT.publish_report_context(self.root, context), path)
        self.assertEqual(CONTEXT.load_report_context(self.root, "RPT-001", 1), context)

    def test_context_crash_before_and_after_stage_rename_is_retryable(self):
        for phase in ("before", "after"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                published = STORE.publish_revision(
                    root,
                    canonical_bytes(copy.deepcopy(self.base_state)),
                )
                context = replace(
                    self.sample_context(markdown_sha256=published.markdown_sha256),
                    repo_root_sha256=hashlib.sha256(str(root).encode("utf-8")).hexdigest(),
                )
                path = (
                    root
                    / ".requirements-impact-refiner"
                    / "reports"
                    / "RPT-001"
                    / "revision-0001.context-v2.json"
                )
                pending = path.parent / f".{path.name}.pending"
                real_replace = CONTEXT.os.replace

                class SimulatedCrash(BaseException):
                    pass

                def crashing_replace(
                    source,
                    destination,
                    *args,
                    pending_name=pending.name,
                    current_phase=phase,
                    current_replace=real_replace,
                    **kwargs,
                ):
                    if str(destination) == pending_name:
                        if current_phase == "after":
                            current_replace(source, destination, *args, **kwargs)
                        raise SimulatedCrash(f"{current_phase} context stage rename")
                    return current_replace(source, destination, *args, **kwargs)

                with mock.patch.object(CONTEXT.os, "replace", side_effect=crashing_replace):
                    with self.assertRaises(SimulatedCrash):
                        CONTEXT.publish_report_context(root, context)

                self.assertFalse(path.exists())
                self.assertEqual(pending.exists(), phase == "after")
                self.assertEqual(
                    CONTEXT.load_report_context(root, "RPT-001", 1),
                    context if phase == "after" else None,
                )
                if phase == "before":
                    self.assertEqual(CONTEXT.publish_report_context(root, context), path)
                self.assertEqual(CONTEXT.load_report_context(root, "RPT-001", 1), context)

    def test_context_crash_after_stage_rename_fsync_recovers_complete_pending(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = self.context_path()
        pending = path.parent / f".{path.name}.pending"
        real_fsync = CONTEXT.os.fsync
        interrupted = False

        class SimulatedCrash(BaseException):
            pass

        def crash_after_pending_fsync(descriptor):
            nonlocal interrupted
            result = real_fsync(descriptor)
            if (
                not interrupted
                and stat.S_ISDIR(os.fstat(descriptor).st_mode)
                and pending.exists()
                and not path.exists()
            ):
                interrupted = True
                raise SimulatedCrash("context pending directory entry is durable")
            return result

        with mock.patch.object(CONTEXT.os, "fsync", side_effect=crash_after_pending_fsync):
            with self.assertRaises(SimulatedCrash):
                CONTEXT.publish_report_context(self.root, context)

        self.assertTrue(interrupted)
        self.assertFalse(path.exists())
        self.assertTrue(pending.is_file())
        self.assertEqual(CONTEXT.load_report_context(self.root, "RPT-001", 1), context)

    def test_context_pre_link_pending_recovers_without_directory_scan(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = self.context_path()

        class SimulatedCrash(BaseException):
            pass

        def crashing_before_link(*_args, **_kwargs):
            raise SimulatedCrash("pending durable before link")

        with mock.patch.object(CONTEXT.os, "link", side_effect=crashing_before_link):
            with self.assertRaises(SimulatedCrash):
                CONTEXT.publish_report_context(self.root, context)

        pending = path.parent / f".{path.name}.pending"
        self.assertFalse(path.exists())
        self.assertTrue(pending.is_file())
        self.assertEqual(pending.stat().st_nlink, 1)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index in range(40_000):
                descriptor = os.open(
                    f"unrelated-{index:05d}",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=directory_fd,
                )
                os.close(descriptor)
        finally:
            os.close(directory_fd)

        with mock.patch.object(
            CONTEXT.os,
            "scandir",
            side_effect=AssertionError("recovery must not scan"),
        ):
            self.assertEqual(CONTEXT.load_report_context(self.root, "RPT-001", 1), context)

        self.assertFalse(pending.exists())
        self.assertEqual(path.stat().st_nlink, 1)

    def test_context_post_link_pending_recovers_without_directory_scan(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = self.context_path()
        real_unlink = CONTEXT.os.unlink

        class SimulatedCrash(BaseException):
            pass

        def crashing_context_unlink(name, *args, **kwargs):
            if str(name).endswith(".pending"):
                raise SimulatedCrash("link completed before process crash")
            return real_unlink(name, *args, **kwargs)

        with mock.patch.object(CONTEXT.os, "unlink", side_effect=crashing_context_unlink):
            with self.assertRaises(SimulatedCrash):
                CONTEXT.publish_report_context(self.root, context)

        pending = path.parent / f".{path.name}.pending"
        self.assertEqual(path.stat().st_nlink, 2)
        self.assertEqual(pending.stat().st_ino, path.stat().st_ino)

        with mock.patch.object(
            CONTEXT.os,
            "scandir",
            side_effect=AssertionError("recovery must not scan"),
        ):
            self.assertEqual(CONTEXT.load_report_context(self.root, "RPT-001", 1), context)

        self.assertFalse(pending.exists())
        self.assertEqual(path.stat().st_nlink, 1)

    def test_context_exact_target_removes_separate_exact_pending_leftover(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = CONTEXT.publish_report_context(self.root, context)
        pending = path.parent / f".{path.name}.pending"
        pending.write_bytes(path.read_bytes())
        pending.chmod(0o600)
        target_inode = path.stat().st_ino
        self.assertNotEqual(pending.stat().st_ino, target_inode)

        with mock.patch.object(
            CONTEXT.os,
            "scandir",
            side_effect=AssertionError("recovery must not scan"),
        ):
            self.assertEqual(CONTEXT.load_report_context(self.root, "RPT-001", 1), context)

        self.assertFalse(pending.exists())
        self.assertEqual(path.stat().st_ino, target_inode)
        self.assertEqual(path.stat().st_nlink, 1)

    def test_context_wrong_pending_leftover_fails_closed(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = CONTEXT.publish_report_context(self.root, context)
        pending = path.parent / f".{path.name}.pending"
        pending.write_bytes(b"wrong")
        pending.chmod(0o600)

        with self.assertRaises(ValueError):
            CONTEXT.load_report_context(self.root, "RPT-001", 1)

        self.assertTrue(pending.exists())
        self.assertEqual(path.stat().st_nlink, 1)

    def test_context_directory_fsync_failure_leaves_a_single_link_for_retry(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = self.context_path()
        real_unlink = CONTEXT.os.unlink
        real_fsync = CONTEXT.os.fsync
        cleaned = False
        failed = False

        def recording_unlink(*args, **kwargs):
            nonlocal cleaned
            result = real_unlink(*args, **kwargs)
            cleaned = True
            return result

        def failing_directory_fsync(descriptor):
            nonlocal failed
            if cleaned and not failed:
                failed = True
                raise OSError("injected directory fsync failure")
            return real_fsync(descriptor)

        with (
            mock.patch.object(CONTEXT.os, "unlink", side_effect=recording_unlink),
            mock.patch.object(CONTEXT.os, "fsync", side_effect=failing_directory_fsync),
        ):
            with self.assertRaisesRegex(ValueError, "fsync"):
                CONTEXT.publish_report_context(self.root, context)

        self.assertEqual(path.stat().st_nlink, 1)
        self.assertEqual(CONTEXT.publish_report_context(self.root, context), path)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO support")
    def test_special_context_artifacts_are_opened_nonblocking_and_rejected(self):
        published = self.publish_report()
        context = self.sample_context(markdown_sha256=published.markdown_sha256)
        path = CONTEXT.publish_report_context(self.root, context)
        path.unlink()
        os.mkfifo(path, 0o600)
        real_open = CONTEXT.os.open

        def guarded_open(name, flags, *args, **kwargs):
            if name == path.name:
                self.assertTrue(flags & os.O_NONBLOCK)
            return real_open(name, flags, *args, **kwargs)

        with mock.patch.object(CONTEXT.os, "open", side_effect=guarded_open):
            with self.assertRaises(ValueError):
                CONTEXT.load_report_context(self.root, "RPT-001", 1)

        path.unlink()

    @unittest.skipUnless(hasattr(socket, "AF_UNIX"), "requires Unix-domain sockets")
    def test_unix_socket_context_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory(dir="/tmp", prefix="r") as short_temporary:
            short_root = Path(short_temporary).resolve()
            short_state = copy.deepcopy(self.base_state)
            short_report = STORE.publish_revision(short_root, canonical_bytes(short_state))
            context = CONTEXT.ReportContext(
                schema_version=2,
                report_id="RPT-001",
                revision=1,
                markdown_sha256=short_report.markdown_sha256,
                state_sha256=hashlib.sha256(short_report.state_path.read_bytes()).hexdigest(),
                repo_root_sha256=hashlib.sha256(str(short_root).encode("utf-8")).hexdigest(),
                requirement_sha256=CONTEXT.canonical_requirement_sha256("프로필 변경"),
                repository_evidence_sha256=CONTEXT.canonical_repository_evidence_sha256(()),
                source_inventory_sha256="4" * 64,
                payload_sha256="5" * 64,
                created_at="2026-08-25T12:34:56.123456Z",
                baseline_commit=None,
                baseline_clean=False,
                source_inventory_git_tracked_only=False,
            )
            socket_path = CONTEXT.publish_report_context(short_root, context)
            socket_path.unlink()
            endpoint = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                try:
                    endpoint.bind(str(socket_path))
                except PermissionError:
                    self.skipTest("sandbox does not permit Unix-domain socket binding")
                os.chmod(socket_path, 0o600)
                with self.assertRaises(ValueError):
                    CONTEXT.load_report_context(short_root, "RPT-001", 1)
            finally:
                endpoint.close()

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
            {"revision": 0},
            {"markdown_sha256": "A" * 64},
            {"source_inventory_available": 1},
            {"source_inventory_complete": 1},
            {"source_inventory_git_tracked_only": 1},
            {
                "source_inventory_git_tracked_only": True,
                "source_inventory_complete": False,
            },
            {"created_at": "2026-08-25"},
            {"baseline_commit": "not-a-commit"},
            {"baseline_clean": 1},
            {"baseline_clean": True, "baseline_commit": None},
            {
                "source_inventory_git_tracked_only": True,
                "baseline_clean": False,
            },
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises((TypeError, ValueError)):
                    replace(valid, **changes)

    def test_git_source_proof_parsers_reject_malformed_bounded_values(self):
        for payload in (b"H path", b"bad\0", b"H \xff\0", b"H ../escape\0"):
            with self.subTest(flags=payload):
                with self.assertRaises(CONTEXT.UnsafeGitOutput):
                    CONTEXT._tracked_paths_from_flags(payload)
        self.assertEqual(CONTEXT._tracked_paths_from_flags(b"h path.py\0"), ({"path.py"}, False))

        for payload in (b"bad\0", b"\xff", b"", b"a\nb"):
            with self.subTest(path=payload):
                with self.assertRaises(CONTEXT.UnsafeGitOutput):
                    CONTEXT._git_single_path(payload, "test")

        for payload in (
            b"bad\0",
            b"100644 " + b"a" * 40 + b" 0\t\xff\0",
            b"100644 " + b"a" * 40 + b" 0\t../escape\0",
        ):
            with self.subTest(index=payload):
                with self.assertRaises(CONTEXT.UnsafeGitOutput):
                    CONTEXT._index_paths_without_unsupported_entries(payload)
        with self.assertRaises(ValueError):
            CONTEXT.probe_source_inventory_git(self.root, {"path.py": "bad"})

    def test_context_accepts_every_positive_nonboolean_report_revision(self):
        report_dir = self.root / ".requirements-impact-refiner" / "reports" / "RPT-001"
        report_dir.mkdir(parents=True)
        markdown = report_dir / "revision-10000.md"
        markdown.write_bytes(b"immutable revision 10000\n")
        state = report_dir / "revision-10000.json"
        state.write_bytes(b"{}\n")
        context = self.sample_context(
            revision=10_000,
            markdown_sha256=hashlib.sha256(markdown.read_bytes()).hexdigest(),
        )

        path = CONTEXT.publish_report_context(self.root, context)

        self.assertEqual(path.name, "revision-10000.context-v2.json")
        self.assertEqual(CONTEXT.load_report_context(self.root, "RPT-001", 10_000), context)
        for invalid in (0, -1, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    CONTEXT.load_report_context(self.root, "RPT-001", invalid)

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

    def test_source_inventory_git_proof_rejects_index_flags_ignored_sources_and_redirects(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "rir@example.invalid"], cwd=self.root, check=True
        )
        subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=self.root, check=True)
        tracked = self.root / "tracked.py"
        tracked.write_text("stable = True\n", encoding="utf-8")
        ignore = self.root / ".gitignore"
        ignore.write_text("ignored.py\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.py", ".gitignore"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=self.root, check=True)
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        inventory = {"tracked.py": hashlib.sha256(tracked.read_bytes()).hexdigest()}

        self.assertEqual(
            CONTEXT.probe_source_inventory_git(self.root, inventory),
            (commit, True, True),
        )
        subprocess.run(
            ["git", "update-index", "--assume-unchanged", "tracked.py"],
            cwd=self.root,
            check=True,
        )
        self.assertEqual(
            CONTEXT.probe_source_inventory_git(self.root, inventory),
            (commit, False, False),
        )
        subprocess.run(
            ["git", "update-index", "--no-assume-unchanged", "tracked.py"],
            cwd=self.root,
            check=True,
        )

        ignored = self.root / "ignored.py"
        ignored.write_text("ignored = True\n", encoding="utf-8")
        ignored_inventory = {
            **inventory,
            "ignored.py": hashlib.sha256(ignored.read_bytes()).hexdigest(),
        }
        self.assertEqual(
            CONTEXT.probe_source_inventory_git(self.root, ignored_inventory),
            (commit, True, False),
        )

        redirect = self.root / "redirect"
        redirect.mkdir()
        subprocess.run(["git", "config", "core.worktree", str(redirect)], cwd=self.root, check=True)
        redirected = CONTEXT.probe_source_inventory_git(self.root, inventory)
        self.assertFalse(redirected[2])

    def test_source_inventory_git_proof_binds_required_digest_to_commit_blob(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "rir@example.invalid"], cwd=self.root, check=True
        )
        subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=self.root, check=True)
        source = self.root / "api.py"
        source.write_text("value = 'commit'\n", encoding="utf-8")
        subprocess.run(["git", "add", "api.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=self.root, check=True)
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        wrong = {"api.py": hashlib.sha256(b"different bytes\n").hexdigest()}

        self.assertEqual(
            CONTEXT.probe_source_inventory_git(self.root, wrong),
            (commit, True, False),
        )

    def test_source_inventory_git_proof_rejects_replacement_refs(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "rir@example.invalid"], cwd=self.root, check=True
        )
        subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=self.root, check=True)
        source = self.root / "api.py"
        source.write_text("value = 'A'\n", encoding="utf-8")
        subprocess.run(["git", "add", "api.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "A"], cwd=self.root, check=True)
        commit_a = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True
        ).stdout.strip()
        required = {"api.py": hashlib.sha256(source.read_bytes()).hexdigest()}
        source.write_text("value = 'B'\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-qam", "B"], cwd=self.root, check=True)
        commit_b = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True
        ).stdout.strip()
        subprocess.run(["git", "checkout", "-q", commit_a], cwd=self.root, check=True)
        subprocess.run(["git", "replace", commit_a, commit_b], cwd=self.root, check=True)

        result = CONTEXT.probe_source_inventory_git(self.root, required)

        self.assertEqual(result, (commit_a, False, False))

    def test_source_inventory_git_proof_rejects_all_checkout_transform_state(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "rir@example.invalid"], cwd=self.root, check=True
        )
        subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=self.root, check=True)
        source = self.root / "api.py"
        source.write_text("value = 'stable'\n", encoding="utf-8")
        subprocess.run(["git", "add", "api.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=self.root, check=True)
        required = {"api.py": hashlib.sha256(source.read_bytes()).hexdigest()}

        for key, value in (
            ("core.autocrlf", "false"),
            ("core.eol", "lf"),
            ("core.attributesfile", ".git/custom-attributes"),
            ("filter.demo.required", "false"),
        ):
            subprocess.run(["git", "config", key, value], cwd=self.root, check=True)
            self.assertFalse(CONTEXT.probe_source_inventory_git(self.root, required)[2])
            subprocess.run(["git", "config", "--unset-all", key], cwd=self.root, check=True)

        info_attributes = self.root / ".git" / "info" / "attributes"
        info_attributes.write_text("*.py text\n", encoding="utf-8")
        self.assertFalse(CONTEXT.probe_source_inventory_git(self.root, required)[2])
        info_attributes.unlink()

        nested = self.root / "nested"
        nested.mkdir()
        attributes = nested / ".gitattributes"
        attributes.write_text("*.py text\n", encoding="utf-8")
        subprocess.run(["git", "add", "nested/.gitattributes"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "attributes"], cwd=self.root, check=True)
        self.assertFalse(CONTEXT.probe_source_inventory_git(self.root, required)[2])

    def test_git_baseline_rejects_transform_state_and_transform_races(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "rir@example.invalid"], cwd=self.root, check=True
        )
        subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=self.root, check=True)
        source = self.root / "api.py"
        source.write_text("value = 'stable'\n", encoding="utf-8")
        subprocess.run(["git", "add", "api.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=self.root, check=True)
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(CONTEXT.probe_git_baseline(self.root), (commit, True))

        subprocess.run(
            ["git", "config", "filter.demo.arbitrary", "configured"],
            cwd=self.root,
            check=True,
        )
        self.assertEqual(CONTEXT.probe_git_baseline(self.root), (commit, False))
        subprocess.run(
            ["git", "config", "--unset-all", "filter.demo.arbitrary"],
            cwd=self.root,
            check=True,
        )

        global_temporary = tempfile.TemporaryDirectory()
        self.addCleanup(global_temporary.cleanup)
        global_home = Path(global_temporary.name)
        (global_home / ".gitconfig").write_text("[core]\n\teol = lf\n", encoding="utf-8")
        with mock.patch.dict(CONTEXT.os.environ, {"HOME": str(global_home)}):
            self.assertEqual(CONTEXT.probe_git_baseline(self.root), (commit, False))

        real_run_git = CONTEXT._run_git
        sampled = False

        def transform_race(root, arguments, **kwargs):
            nonlocal sampled
            result = real_run_git(root, arguments, **kwargs)
            if not sampled and "config" in arguments and "--get-regexp" in arguments:
                sampled = True
                subprocess.run(
                    ["git", "config", "filter.race.clean", "cat"],
                    cwd=self.root,
                    check=True,
                )
            return result

        with mock.patch.object(CONTEXT, "_run_git", side_effect=transform_race):
            self.assertEqual(CONTEXT.probe_git_baseline(self.root), (commit, False))

    def test_source_inventory_git_proof_rejects_checkout_and_index_flag_races(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "rir@example.invalid"], cwd=self.root, check=True
        )
        subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=self.root, check=True)
        source = self.root / "api.py"
        source.write_text("value = 'A'\n", encoding="utf-8")
        subprocess.run(["git", "add", "api.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "A"], cwd=self.root, check=True)
        commit_a = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True
        ).stdout.strip()
        digest_a = hashlib.sha256(source.read_bytes()).hexdigest()
        source.write_text("value = 'B'\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-qam", "B"], cwd=self.root, check=True)
        commit_b = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True
        ).stdout.strip()
        subprocess.run(["git", "checkout", "-q", commit_a], cwd=self.root, check=True)
        real_run_git = CONTEXT._run_git
        switched = False

        def checkout_race(root, arguments, **kwargs):
            nonlocal switched
            result = real_run_git(root, arguments, **kwargs)
            if not switched and "HEAD^{commit}" in arguments:
                switched = True
                subprocess.run(["git", "checkout", "-q", commit_b], cwd=self.root, check=True)
            return result

        with mock.patch.object(CONTEXT, "_run_git", side_effect=checkout_race):
            checkout_result = CONTEXT.probe_source_inventory_git(self.root, {"api.py": digest_a})
        self.assertFalse(checkout_result[2])

        subprocess.run(["git", "checkout", "-q", commit_a], cwd=self.root, check=True)
        raced = False

        def index_race(root, arguments, **kwargs):
            nonlocal raced
            result = real_run_git(root, arguments, **kwargs)
            if not raced and "ls-files" in arguments:
                raced = True
                subprocess.run(
                    ["git", "update-index", "--assume-unchanged", "api.py"],
                    cwd=self.root,
                    check=True,
                )
                source.write_text("hidden edit\n", encoding="utf-8")
            return result

        with mock.patch.object(CONTEXT, "_run_git", side_effect=index_race):
            index_result = CONTEXT.probe_source_inventory_git(self.root, {"api.py": digest_a})
        self.assertFalse(index_result[2])

    def test_source_inventory_git_proof_rejects_any_clean_source_bearing_submodule(self):
        child_temporary = tempfile.TemporaryDirectory()
        self.addCleanup(child_temporary.cleanup)
        child = Path(child_temporary.name).resolve()
        for repository in (child, self.root):
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "user.email", "rir@example.invalid"],
                cwd=repository,
                check=True,
            )
            subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=repository, check=True)
        child_source = child / "api.py"
        child_source.write_text("value = 'submodule'\n", encoding="utf-8")
        subprocess.run(["git", "add", "api.py"], cwd=child, check=True)
        subprocess.run(["git", "commit", "-qm", "child"], cwd=child, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                "-q",
                str(child),
                "deps/child",
            ],
            cwd=self.root,
            check=True,
        )
        (self.root / ".gitignore").write_text(".requirements-impact-refiner/\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qam", "add child"], cwd=self.root, check=True)
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        checkout_source = self.root / "deps" / "child" / "api.py"
        required = {"deps/child/api.py": hashlib.sha256(checkout_source.read_bytes()).hexdigest()}

        self.assertEqual(
            CONTEXT.probe_source_inventory_git(self.root, required),
            (commit, False, False),
        )

    def test_git_baseline_rejects_any_gitlink_even_when_checkout_is_clean(self):
        def initialize(repository: Path) -> None:
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "user.email", "rir@example.invalid"],
                cwd=repository,
                check=True,
            )
            subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=repository, check=True)

        with tempfile.TemporaryDirectory() as child_temporary:
            child = Path(child_temporary).resolve()
            initialize(child)
            child_file = child / "child.txt"
            child_file.write_text("one\n", encoding="utf-8")
            subprocess.run(["git", "add", "child.txt"], cwd=child, check=True)
            subprocess.run(["git", "commit", "-qm", "child baseline"], cwd=child, check=True)

            initialize(self.root)
            parent_file = self.root / "parent.txt"
            parent_file.write_text("parent\n", encoding="utf-8")
            subprocess.run(["git", "add", "parent.txt"], cwd=self.root, check=True)
            subprocess.run(["git", "commit", "-qm", "parent baseline"], cwd=self.root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "protocol.file.allow=always",
                    "submodule",
                    "add",
                    "-q",
                    str(child),
                    "deps/child",
                ],
                cwd=self.root,
                check=True,
            )
            subprocess.run(["git", "commit", "-qam", "add submodule"], cwd=self.root, check=True)
            parent_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(CONTEXT.probe_git_baseline(self.root), (parent_commit, False))

    def test_non_git_and_git_execution_failure_are_unproven_not_errors(self):
        self.assertEqual(CONTEXT.probe_git_baseline(self.root), (None, False))
        with mock.patch.object(CONTEXT, "_run_git", return_value=None):
            self.assertEqual(CONTEXT.probe_git_baseline(self.root), (None, False))

    @unittest.skipUnless(hasattr(os, "killpg"), "requires POSIX process groups")
    def test_git_timeout_kills_the_entire_descendant_process_group(self):
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        marker = self.root / "descendant-survived"
        child_pid_path = self.root / "child.pid"
        child_code = (
            "import pathlib,sys,time\n"
            "time.sleep(1.5)\n"
            "pathlib.Path(sys.argv[1]).write_text('survived', encoding='utf-8')\n"
        )
        fake_git = fake_bin / "git"
        fake_git.write_text(
            f"#!{sys.executable}\n"
            "import pathlib,subprocess,time\n"
            f"child = subprocess.Popen([{sys.executable!r}, '-c', {child_code!r}, "
            f"{str(marker)!r}])\n"
            f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid), encoding='utf-8')\n"
            "time.sleep(10.0)\n",
            encoding="utf-8",
        )
        fake_git.chmod(0o700)
        child_pid: int | None = None
        real_popen = subprocess.Popen

        def launch_fake_git(_command, **kwargs):
            return real_popen([sys.executable, str(fake_git)], **kwargs)

        def process_exists(process_id: int) -> bool:
            try:
                os.kill(process_id, 0)
            except ProcessLookupError:
                return False
            except PermissionError:
                return True
            return True

        try:
            with (
                mock.patch.object(
                    CONTEXT.subprocess,
                    "Popen",
                    side_effect=launch_fake_git,
                ),
                mock.patch.object(CONTEXT, "GIT_TIMEOUT_SECONDS", 0.3),
            ):
                self.assertIsNone(CONTEXT._run_git(self.root, ("rev-parse", "HEAD")))
            self.assertTrue(child_pid_path.is_file())
            child_pid = int(child_pid_path.read_text(encoding="utf-8"))
            deadline = time.monotonic() + 0.5
            while process_exists(child_pid) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(process_exists(child_pid), "Git descendant survived timeout cleanup")
            time.sleep(1.0)
            self.assertFalse(marker.exists(), "Git descendant executed after timeout")
        finally:
            if child_pid is not None and process_exists(child_pid):
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
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
        self.assertEqual(
            context.repository_evidence_sha256,
            CONTEXT.canonical_repository_evidence_sha256(
                (
                    "authorizeProjectEdit permits owner and admin",
                    "workspace invitations default to member",
                )
            ),
        )
        self.assertEqual(
            context.state_sha256,
            hashlib.sha256(result.state_path.read_bytes()).hexdigest(),
        )
        self.assertFalse(context.source_inventory_available)
        self.assertFalse(context.source_inventory_complete)
        self.assertFalse(context.source_inventory_git_tracked_only)
        self.assertIsNone(context.source_inventory_sha256)
        self.assertIsNone(context.required_source_digests)
        self.assertFalse(context.source_recheck_complete)
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
        (self.root / ".gitignore").write_text(".requirements-impact-refiner/\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "rir@example.invalid"], cwd=self.root, check=True
        )
        subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=self.root, check=True)
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
        self.assertTrue(context.source_inventory_git_tracked_only)
        self.assertEqual(dict(context.required_source_digests), inventory["digests"])
        self.assertTrue(context.source_recheck_complete)
        self.assertEqual(
            context.state_sha256,
            hashlib.sha256(result.state_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            context.repository_evidence_sha256,
            CONTEXT.canonical_repository_evidence_sha256(()),
        )

    def test_explicit_ignored_generated_seed_is_required_and_never_tracked_only(self):
        self.configure_graph(True)
        generated = self.root / "generated"
        generated.mkdir()
        source = generated / "api.py"
        source.write_text("def generated_api():\n    return True\n", encoding="utf-8")
        (self.root / ".gitignore").write_text(
            ".requirements-impact-refiner/\ngenerated/\n", encoding="utf-8"
        )
        (self.root / "tracked.py").write_text("stable = True\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "rir@example.invalid"], cwd=self.root, check=True
        )
        subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=self.root, check=True)
        change = "Change generated/api.py generated_api and generated/later.py"
        scan = CONTROLLER.scan_impact(CONTROLLER.ScanRequest(self.root, change, (), "balanced"))
        draft = CONTROLLER.begin_refinement(
            CONTROLLER.BeginRequest(self.root, change, (), "generic", scan_id=scan.scan_id)
        )
        request = self.finalize_request(draft, scan.receipt_id)
        request.analysis["impacts"][0]["graph_path_keys"] = [row["id"] for row in scan.paths]
        if not request.analysis["impacts"][0]["graph_path_keys"]:
            request.analysis["impacts"][0]["coverage_rationale"] = (
                "Fast Scan found no closed repository path."
            )
        request.analysis["impacts"][0]["evidence_level"] = "unknown"

        draft_value = CONTROLLER.load_draft(self.root, draft.draft_id)
        graph_context = FINALIZE.load_promoted_scan_context(self.root, draft_value, scan.receipt_id)
        result = FINALIZE.finalize_refinement(request)
        context = CONTEXT.load_report_context(self.root, result.report_id, result.revision)
        wrapper = json.loads(
            (
                self.root / ".requirements-impact-refiner" / "scans" / f"{scan.scan_id}.json"
            ).read_text(encoding="utf-8")
        )
        generated_seed = next(
            row for row in wrapper["seeds"] if row["location"] == "generated/api.py"
        )

        self.assertIsNotNone(context)
        self.assertEqual(
            generated_seed["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest()
        )
        self.assertNotIn("generated/api.py", wrapper["source_inventory"]["digests"])
        required_digests = graph_context["source_inventory"]["required_digests"]
        self.assertEqual(required_digests["generated/api.py"], generated_seed["source_sha256"])
        self.assertNotIn("generated/later.py", required_digests)
        self.assertIsNone(context.required_source_digests)
        self.assertFalse(context.source_recheck_complete)
        self.assertTrue(context.source_inventory_complete)
        self.assertFalse(context.source_inventory_git_tracked_only)
        (generated / "later.py").write_text("appeared = True\n", encoding="utf-8")
        previous = CONTROLLER.lookup_previous(
            CONTROLLER.PreviousLookupRequest(self.root, change, ())
        )
        self.assertEqual(previous.status, "stale")

    def test_absent_source_stays_stale_and_full_delta_call_p95_is_bounded(self):
        self.configure_graph(True)
        source = self.root / "src" / "tracked.py"
        source.parent.mkdir()
        source.write_text("def create_file():\n    return True\n", encoding="utf-8")
        (self.root / ".gitignore").write_text(
            ".requirements-impact-refiner/\nignored.py\n", encoding="utf-8"
        )
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "rir@example.invalid"], cwd=self.root, check=True
        )
        subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=self.root, check=True)
        change = "create ignored.py"
        evidence = ("src/tracked.py is the creation hook",)
        scan = CONTROLLER.scan_impact(
            CONTROLLER.ScanRequest(self.root, change, evidence, "balanced")
        )
        self.assertTrue(scan.can_promote)
        draft = CONTROLLER.begin_refinement(
            CONTROLLER.BeginRequest(
                self.root,
                change,
                evidence,
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
        context = CONTEXT.load_report_context(self.root, result.report_id, result.revision)
        (self.root / "ignored.py").write_text("appeared = True\n", encoding="utf-8")
        sample_count = 20
        observations_ms = []
        scan_ids = set()
        cache_statuses = []
        delta = None
        previous = None
        for index in range(sample_count):
            (self.root / "ignored.py").write_text(f"appeared = {index}\n", encoding="utf-8")
            previous = CONTROLLER.lookup_previous(
                CONTROLLER.PreviousLookupRequest(self.root, change, evidence)
            )
            delta_request = CONTROLLER.ScanRequest(
                self.root,
                change,
                evidence,
                "balanced",
                previous_report_id=previous.report_id,
                previous_revision=previous.revision,
                changed_paths=previous.changed_paths,
            )
            started = time.monotonic()
            delta = CONTROLLER.scan_impact(delta_request)
            observations_ms.append((time.monotonic() - started) * 1000)
            scan_ids.add(delta.scan_id)
            cache_statuses.append(delta.cache_status)
        observations_ms.sort()
        nearest_rank = ((95 * sample_count + 99) // 100) - 1
        p95_ms = observations_ms[nearest_rank]
        self.delta_benchmark_sample_count = sample_count
        self.delta_benchmark_p95_ms = p95_ms

        self.assertIsNotNone(context)
        self.assertIsNotNone(delta)
        self.assertIsNotNone(previous)
        assert delta is not None
        assert previous is not None
        self.assertIsNone(context.required_source_digests)
        self.assertFalse(context.source_recheck_complete)
        self.assertEqual(previous.status, "stale")
        self.assertIn(delta.status, {"complete", "partial"})
        self.assertEqual(delta.previous_report_id, previous.report_id)
        self.assertEqual(delta.previous_revision, previous.revision)
        self.assertEqual(delta.changed_paths, previous.changed_paths)
        self.assertTrue(delta.display_text.startswith(previous.display_text))
        self.assertLessEqual(delta.elapsed_ms, 3_000)
        self.assertEqual(len(observations_ms), sample_count)
        self.assertEqual(len(scan_ids), sample_count)
        self.assertNotIn("hit", cache_statuses)
        self.assertLessEqual(p95_ms, 3_000)
        delta_receipt = json.loads(
            (
                self.root / ".requirements-impact-refiner" / "scans" / f"{delta.scan_id}.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(delta_receipt["settings"]["max_seconds"], 3)
        self.assertEqual(delta_receipt["delta_context"]["previous_revision"], previous.revision)

    def test_complete_recheck_map_unions_inventory_with_readable_explicit_seed(self):
        self.configure_graph(True)
        tracked = self.root / "tracked.py"
        tracked.write_text("stable = True\n", encoding="utf-8")
        generated = self.root / "generated"
        generated.mkdir()
        explicit = generated / "api.py"
        explicit.write_text("generated = True\n", encoding="utf-8")
        tracked_digest = hashlib.sha256(tracked.read_bytes()).hexdigest()
        explicit_digest = hashlib.sha256(explicit.read_bytes()).hexdigest()
        required = {"tracked.py": tracked_digest, "generated/api.py": explicit_digest}
        draft = self.begin("Change generated/api.py")
        request = self.finalize_request(draft, "9" * 32)
        runtime = dict(FINALIZE.default_runtime())
        runtime["load_graph_context"] = lambda *args: {
            "receipt": {"receipt_id": "9" * 32},
            "sha256": "8" * 64,
            "source_inventory": {
                "sha256": "7" * 64,
                "complete": True,
                "digests": {"tracked.py": tracked_digest},
                "required_digests": required,
                "required_complete": True,
            },
        }
        runtime["validate_analysis"] = lambda *args: None
        runtime["validate_graph_coverage"] = lambda *args: None
        runtime["build_state"] = lambda selected_draft, analysis, graph: (
            FINALIZE.LINEAGE.build_state(selected_draft, analysis, None)
        )

        result = FINALIZE.finalize_refinement(request, _runtime=runtime)

        context = CONTEXT.load_report_context(self.root, result.report_id, result.revision)
        self.assertEqual(dict(context.required_source_digests), required)
        self.assertTrue(context.source_recheck_complete)
        self.assertFalse(context.source_inventory_git_tracked_only)

    def test_required_source_count_overflow_persists_stale_recheck_contract(self):
        self.configure_graph(True)
        required = {}
        for index in range(CONTEXT.MAX_REQUIRED_SOURCE_DIGESTS + 1):
            relative = f"src/source-{index:03d}.py"
            source = self.root / relative
            source.parent.mkdir(exist_ok=True)
            source.write_text(f"VALUE = {index}\n", encoding="utf-8")
            required[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
        change = "Change bounded source inventory"
        draft = self.begin(change)
        request = self.finalize_request(draft, "9" * 32)
        runtime = dict(FINALIZE.default_runtime())
        runtime["load_graph_context"] = lambda *args: {
            "receipt": {"receipt_id": "9" * 32},
            "sha256": "8" * 64,
            "source_inventory": {
                "sha256": "7" * 64,
                "complete": True,
                "digests": required,
                "required_digests": required,
                "required_complete": True,
            },
        }
        runtime["validate_analysis"] = lambda *args: None
        runtime["validate_graph_coverage"] = lambda *args: None
        runtime["build_state"] = lambda selected_draft, analysis, graph: (
            FINALIZE.LINEAGE.build_state(selected_draft, analysis, None)
        )

        result = FINALIZE.finalize_refinement(request, _runtime=runtime)
        context = CONTEXT.load_report_context(self.root, result.report_id, result.revision)
        previous = CONTROLLER.lookup_previous(
            CONTROLLER.PreviousLookupRequest(
                self.root,
                change,
                (
                    "authorizeProjectEdit permits owner and admin",
                    "workspace invitations default to member",
                ),
            )
        )

        self.assertIsNone(context.required_source_digests)
        self.assertFalse(context.source_recheck_complete)
        self.assertEqual(previous.status, "stale")

    def test_explicit_path_candidate_overflow_finalizes_with_incomplete_proof(self):
        self.configure_graph(False)
        change = "Change " + " ".join(f"src/path-{index}.py" for index in range(17))
        draft = self.begin(change)

        result = FINALIZE.finalize_refinement(self.finalize_request(draft))

        context = CONTEXT.load_report_context(self.root, result.report_id, result.revision)
        self.assertIsNotNone(context)
        self.assertFalse(context.source_inventory_git_tracked_only)
        self.assertIsNone(context.required_source_digests)
        self.assertFalse(context.source_recheck_complete)
        previous = CONTROLLER.lookup_previous(
            CONTROLLER.PreviousLookupRequest(
                self.root,
                change,
                (
                    "authorizeProjectEdit permits owner and admin",
                    "workspace invitations default to member",
                ),
            )
        )
        self.assertEqual(previous.status, "stale")

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
        self.assertTrue((published.state_path.parent / "revision-0001.context-v2.json").is_file())
        self.assertTrue(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

    def test_intermediate_v1_metadata_and_context_fail_closed_without_rebinding(self):
        self.configure_graph(False)
        source = self.root / "source.py"
        source.write_text("value = 'old'\n", encoding="utf-8")
        legacy_inventory_sha256 = FINALIZE.GRAPH_DELIVERY.source_inventory_sha256(
            {"source.py": hashlib.sha256(source.read_bytes()).hexdigest()}
        )
        (self.root / ".gitignore").write_text(".requirements-impact-refiner/\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "rir@example.invalid"], cwd=self.root, check=True
        )
        subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "legacy baseline"], cwd=self.root, check=True)
        legacy_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        draft_result = self.begin("Migrate literal v1 context safely.")
        request = self.finalize_request(draft_result)
        draft = CONTROLLER.load_draft(self.root, draft_result.draft_id)
        state, key_map = FINALIZE.LINEAGE.build_state(draft, request.analysis, None)
        state_bytes = FINALIZE.CONTRACTS.canonical_bytes(state)
        published = FINALIZE.REPORT_STORE.publish_revision(
            self.root, state_bytes, resume_partial=True
        )
        analysis_sha256 = hashlib.sha256(
            FINALIZE.CONTRACTS.canonical_bytes(request.analysis)
        ).hexdigest()
        requirement_sha256 = CONTEXT.canonical_requirement_sha256(draft["request"])
        old_context_identity = {
            "repo_root_sha256": CONTEXT.repo_root_sha256(self.root),
            "requirement_sha256": requirement_sha256,
            "source_inventory_sha256": legacy_inventory_sha256,
            "source_inventory_available": True,
            "source_inventory_complete": True,
            "payload_sha256": "5" * 64,
        }
        old_metadata = {
            "schema_version": 1,
            "draft_id": draft["draft_id"],
            "report_id": draft["report_id"],
            "revision": draft["revision"],
            "state_sha256": hashlib.sha256(state_bytes).hexdigest(),
            "key_map": key_map,
            "analysis_sha256": analysis_sha256,
            "context_identity": old_context_identity,
        }
        metadata_path = published.state_path.with_name("revision-0001.controller.json")
        metadata_path.write_bytes(canonical_bytes(old_metadata))
        os.chmod(metadata_path, 0o600)
        old_context = {
            "schema_version": 1,
            "report_id": "RPT-001",
            "revision": 1,
            "markdown_sha256": published.markdown_sha256,
            **old_context_identity,
            "created_at": "2026-08-25T12:34:56Z",
            "baseline_commit": legacy_commit,
            "baseline_clean": True,
        }
        old_context_path = published.state_path.with_name("revision-0001.context.json")
        old_context_path.write_bytes(canonical_bytes(old_context))
        os.chmod(old_context_path, 0o600)
        source.write_text("value = 'changed after v1 publication'\n", encoding="utf-8")

        metadata_before = metadata_path.read_bytes()
        context_before = old_context_path.read_bytes()

        with self.assertRaisesRegex(
            ValueError,
            "completed report schema or payload identity is incompatible with this runtime",
        ):
            FINALIZE.finalize_refinement(request)

        self.assertEqual(metadata_path.read_bytes(), metadata_before)
        self.assertEqual(old_context_path.read_bytes(), context_before)
        self.assertIsNone(CONTEXT.load_report_context(self.root, "RPT-001", 1))
        self.assertTrue(old_context_path.is_file())
        self.assertFalse(
            FINALIZE.STORAGE.load_private_draft(self.root, draft_result.draft_id)["consumed"]
        )
        previous = CONTROLLER.lookup_previous(
            CONTROLLER.PreviousLookupRequest(
                self.root, draft["request"], tuple(draft["repository_evidence"])
            )
        )
        self.assertEqual(previous.status, "none")
        self.assertIsNone(previous.display_text)
        self.assertEqual(
            previous.reason,
            "previous report schema or payload identity is incompatible with this runtime",
        )

    def test_current_schema_payload_mismatch_fails_with_stable_diagnostic(self):
        self.configure_graph(False)
        draft_result = self.begin("Reject mismatched current payload.")
        request = self.finalize_request(draft_result)
        runtime = dict(FINALIZE.default_runtime())

        class SimulatedInterruption(BaseException):
            pass

        runtime["consume_draft"] = mock.Mock(side_effect=SimulatedInterruption("before consume"))
        with self.assertRaises(SimulatedInterruption):
            FINALIZE.finalize_refinement(request, _runtime=runtime)

        published = FINALIZE.REPORT_STORE.load_current(self.root, "RPT-001")
        metadata_path = published.state_path.with_name("revision-0001.controller.json")
        context_path = published.state_path.with_name("revision-0001.context-v2.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        context = json.loads(context_path.read_text(encoding="utf-8"))
        metadata["context_identity"]["payload_sha256"] = "f" * 64
        context["payload_sha256"] = "f" * 64
        metadata_path.write_bytes(canonical_bytes(metadata))
        context_path.write_bytes(canonical_bytes(context))

        with self.assertRaisesRegex(
            ValueError,
            "completed report schema or payload identity is incompatible with this runtime",
        ):
            FINALIZE.finalize_refinement(request)

        self.assertFalse(
            FINALIZE.STORAGE.load_private_draft(self.root, draft_result.draft_id)["consumed"]
        )

    def test_context_cleanup_failure_leaves_draft_unconsumed_and_retry_recovers(self):
        self.configure_graph(False)
        draft = self.begin("Context cleanup failure remains retryable.")
        request = self.finalize_request(draft)
        real_unlink = FINALIZE.REPORT_CONTEXT.os.unlink

        def failing_context_unlink(name, *args, **kwargs):
            if str(name).endswith(".context-v2.json.pending"):
                raise OSError("injected context cleanup failure")
            return real_unlink(name, *args, **kwargs)

        with mock.patch.object(
            FINALIZE.REPORT_CONTEXT.os,
            "unlink",
            side_effect=failing_context_unlink,
        ):
            with self.assertRaisesRegex(ValueError, "cleanup"):
                FINALIZE.finalize_refinement(request)

        path = self.context_path()
        self.assertEqual(path.stat().st_nlink, 2)
        self.assertFalse(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

        result = FINALIZE.finalize_refinement(request)

        self.assertEqual(result.revision, 1)
        self.assertEqual(path.stat().st_nlink, 1)
        self.assertTrue(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

    def test_oversized_completion_metadata_fails_before_report_or_consumption(self):
        self.configure_graph(False)
        draft = self.begin("Oversized completion metadata cannot publish.")
        request = self.finalize_request(draft)
        runtime = dict(FINALIZE.default_runtime())
        real_build_state = runtime["build_state"]

        def oversized_key_map(selected_draft, analysis, graph_context):
            state, _key_map = real_build_state(selected_draft, analysis, graph_context)
            return state, {"padding": "x" * FINALIZE.STORAGE.MAX_CONTROLLER_METADATA_BYTES}

        runtime["build_state"] = oversized_key_map
        with self.assertRaisesRegex(ValueError, "256 KiB"):
            FINALIZE.finalize_refinement(request, _runtime=runtime)

        self.assertIsNone(FINALIZE.REPORT_STORE.load_current(self.root, "RPT-001"))
        self.assertFalse(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

    def test_finalize_retries_metadata_cleanup_failure_before_consumption(self):
        self.configure_graph(False)
        draft = self.begin("Metadata cleanup failure remains retryable.")
        request = self.finalize_request(draft)
        real_unlink = FINALIZE.STORAGE.os.unlink

        def failing_metadata_unlink(name, *args, **kwargs):
            if "revision-0001.controller.json" in str(name):
                raise OSError("injected metadata cleanup failure")
            return real_unlink(name, *args, **kwargs)

        with mock.patch.object(
            FINALIZE.STORAGE.os,
            "unlink",
            side_effect=failing_metadata_unlink,
        ):
            with self.assertRaisesRegex(ValueError, "cleanup"):
                FINALIZE.finalize_refinement(request)

        self.assertIsNone(FINALIZE.REPORT_STORE.load_current(self.root, "RPT-001"))
        self.assertFalse(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

        result = FINALIZE.finalize_refinement(request)

        self.assertEqual(result.revision, 1)
        self.assertTrue(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

    def test_finalize_cannot_resume_with_arbitrarily_linked_metadata(self):
        self.configure_graph(False)
        draft = self.begin("Unreadable metadata cannot consume the draft.")
        request = self.finalize_request(draft)
        runtime = dict(FINALIZE.default_runtime())

        class SimulatedCrash(BaseException):
            pass

        runtime["consume_draft"] = mock.Mock(side_effect=SimulatedCrash("before consumption"))
        with self.assertRaises(SimulatedCrash):
            FINALIZE.finalize_refinement(request, _runtime=runtime)
        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        arbitrary = metadata_path.with_name("arbitrary-metadata-hardlink")
        os.link(metadata_path, arbitrary)

        with self.assertRaisesRegex(ValueError, "pending state"):
            FINALIZE.finalize_refinement(request)

        self.assertFalse(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

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

    def test_completed_graph_context_retries_before_source_or_git_revalidation(self):
        source, _scan, draft, request = self.promoted_finalize_case()
        runtime = dict(FINALIZE.default_runtime())

        class SimulatedCrash(BaseException):
            pass

        runtime["consume_draft"] = mock.Mock(
            side_effect=SimulatedCrash("context durable before draft consumption")
        )
        with self.assertRaises(SimulatedCrash):
            FINALIZE.finalize_refinement(request, _runtime=runtime)

        current = FINALIZE.REPORT_STORE.load_current(self.root, "RPT-001")
        context = CONTEXT.load_report_context(self.root, "RPT-001", 1)
        self.assertIsNotNone(current)
        self.assertIsNotNone(context)
        self.assertFalse(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])
        source.write_text('FIELD = "profile.renamed"\n', encoding="utf-8")

        retry_runtime = dict(FINALIZE.default_runtime())
        forbidden = (
            "load_graph_context",
            "load_promoted_scan_context",
            "validate_analysis",
            "validate_graph_coverage",
            "build_state",
            "probe_git_baseline",
            "write_controller_metadata",
            "publish_revision",
        )
        for name in forbidden:
            retry_runtime[name] = mock.Mock(side_effect=AssertionError(f"unexpected {name}"))

        result = FINALIZE.finalize_refinement(request, _runtime=retry_runtime)

        self.assertEqual((result.report_id, result.revision), ("RPT-001", 1))
        self.assertEqual(result.markdown_sha256, current.markdown_sha256)
        self.assertEqual(CONTEXT.load_report_context(self.root, "RPT-001", 1), context)
        self.assertTrue(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])
        for name in forbidden:
            retry_runtime[name].assert_not_called()

    def test_missing_context_cannot_skip_safe_graph_reconstruction(self):
        source, _scan, draft, request = self.promoted_finalize_case()
        runtime = dict(FINALIZE.default_runtime())
        runtime["publish_report_context"] = mock.Mock(
            side_effect=ValueError("injected missing context")
        )
        with self.assertRaisesRegex(ValueError, "injected missing context"):
            FINALIZE.finalize_refinement(request, _runtime=runtime)
        self.assertIsNone(CONTEXT.load_report_context(self.root, "RPT-001", 1))
        source.write_text('FIELD = "profile.renamed"\n', encoding="utf-8")

        retry_runtime = dict(FINALIZE.default_runtime())
        graph_revalidation = mock.Mock(side_effect=ValueError("stale graph reconstruction"))
        retry_runtime["load_promoted_scan_context"] = graph_revalidation
        with self.assertRaisesRegex(ValueError, "stale graph reconstruction"):
            FINALIZE.finalize_refinement(request, _runtime=retry_runtime)

        graph_revalidation.assert_called_once()
        self.assertFalse(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

    def test_foreign_context_or_changed_analysis_cannot_skip_graph_revalidation(self):
        _source, _scan, draft, request = self.promoted_finalize_case()
        runtime = dict(FINALIZE.default_runtime())

        class SimulatedCrash(BaseException):
            pass

        runtime["consume_draft"] = mock.Mock(side_effect=SimulatedCrash("before consume"))
        with self.assertRaises(SimulatedCrash):
            FINALIZE.finalize_refinement(request, _runtime=runtime)
        exact_context = CONTEXT.load_report_context(self.root, "RPT-001", 1)
        self.assertIsNotNone(exact_context)

        foreign_runtime = dict(FINALIZE.default_runtime())
        foreign_runtime["load_report_context"] = mock.Mock(
            return_value=replace(exact_context, payload_sha256="6" * 64)
        )
        foreign_graph = mock.Mock(side_effect=ValueError("foreign context revalidation"))
        foreign_runtime["load_promoted_scan_context"] = foreign_graph
        with self.assertRaisesRegex(
            ValueError,
            "completed report schema or payload identity is incompatible with this runtime",
        ):
            FINALIZE.finalize_refinement(request, _runtime=foreign_runtime)
        foreign_graph.assert_not_called()

        changed_analysis = copy.deepcopy(request.analysis)
        changed_analysis["scope"][0]["evidence"] += " Changed after publication."
        changed_request = CONTROLLER.FinalizeRequest(
            self.root,
            draft.draft_id,
            changed_analysis,
            request.graph_receipt_id,
        )
        changed_runtime = dict(FINALIZE.default_runtime())
        changed_graph = mock.Mock(side_effect=ValueError("changed analysis revalidation"))
        changed_runtime["load_promoted_scan_context"] = changed_graph
        with self.assertRaisesRegex(ValueError, "changed analysis revalidation"):
            FINALIZE.finalize_refinement(changed_request, _runtime=changed_runtime)
        changed_graph.assert_called_once()
        self.assertFalse(FINALIZE.STORAGE.load_private_draft(self.root, draft.draft_id)["consumed"])

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
