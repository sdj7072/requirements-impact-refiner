from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SKILL_SCRIPTS = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
DRAFT_ID = "1" * 32
TRANSACTION_ID = "2" * 32


def load_module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def canonical_bytes(value):
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


STORAGE = load_module("rir_storage", SCRIPTS / "rir_storage.py")
CONTROLLER = load_module("rir_storage_controller_test", SCRIPTS / "rir_controller.py")


class SimulatedProcessInterruption(BaseException):
    pass


class RirStorageTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()

    def tearDown(self):
        self.temporary.cleanup()

    def draft(self, *, consumed=False):
        return {
            "consumed": consumed,
            "draft_id": DRAFT_ID,
            "repo_root": str(self.root),
        }

    def write_draft(self):
        value = self.draft()
        path = STORAGE.write_private_draft(self.root, DRAFT_ID, canonical_bytes(value))
        return value, path

    def test_private_draft_modes_cas_bytes_and_exact_failure_are_stable(self):
        expected, path = self.write_draft()
        replacement = self.draft(consumed=True)

        self.assertEqual(STORAGE.root_path(self.root), self.root)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        with self.assertRaisesRegex(ValueError, "trace transaction changed before receipt binding"):
            STORAGE.cas_replace_private_draft(
                self.root,
                DRAFT_ID,
                b"wrong",
                canonical_bytes(replacement),
            )

        STORAGE.cas_replace_private_draft(
            self.root,
            DRAFT_ID,
            canonical_bytes(expected),
            canonical_bytes(replacement),
        )

        self.assertEqual(STORAGE.load_private_draft(self.root, DRAFT_ID), replacement)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(path.stat().st_nlink, 1)
        self.assertEqual(
            sorted(item.name for item in path.parent.iterdir()),
            [".draft-transaction.lock", f"{DRAFT_ID}.json"],
        )
        self.assertEqual(
            stat.S_IMODE((path.parent / ".draft-transaction.lock").stat().st_mode),
            0o600,
        )

    def test_cas_recovers_exact_quarantine_replacement_and_cleanup_crash_snapshots(self):
        stem = f".{DRAFT_ID}.{TRANSACTION_ID}"
        expected_names = {
            "after-quarantine-rename": (
                f"{stem}.anchor",
                f"{stem}.new",
                f"{stem}.quarantine",
                f"{stem}.swap",
                f".{DRAFT_ID}.transaction",
                ".draft-transaction.lock",
            ),
            "after-replacement-publication": (
                f"{stem}.anchor",
                f"{stem}.new",
                f"{stem}.quarantine",
                f"{stem}.swap",
                f".{DRAFT_ID}.transaction",
                ".draft-transaction.lock",
                f"{DRAFT_ID}.json",
            ),
            "before-quarantine-cleanup": (
                f"{stem}.anchor",
                f"{stem}.commit",
                f"{stem}.quarantine.removing",
                f"{stem}.swap",
                f".{DRAFT_ID}.transaction",
                ".draft-transaction.lock",
                f"{DRAFT_ID}.json",
            ),
            "after-quarantine-cleanup": (
                f"{stem}.anchor",
                f"{stem}.commit",
                f"{stem}.swap",
                f".{DRAFT_ID}.transaction",
                ".draft-transaction.lock",
                f"{DRAFT_ID}.json",
            ),
        }
        for phase, surviving_names in expected_names.items():
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                expected = {
                    "consumed": False,
                    "draft_id": DRAFT_ID,
                    "repo_root": str(root),
                }
                replacement = dict(expected, consumed=True)
                path = STORAGE.write_private_draft(root, DRAFT_ID, canonical_bytes(expected))
                real_rename = STORAGE._rename_noreplace
                real_link = STORAGE.os.link
                real_unlink = STORAGE.os.unlink
                interrupted = False

                def interrupting_rename(
                    directory_fd,
                    source,
                    destination,
                    real_rename=real_rename,
                    phase=phase,
                ):
                    nonlocal interrupted
                    result = real_rename(directory_fd, source, destination)
                    if (
                        not interrupted
                        and phase == "after-quarantine-rename"
                        and source == f"{DRAFT_ID}.json"
                        and str(destination).endswith(".quarantine")
                    ):
                        interrupted = True
                        raise SimulatedProcessInterruption(phase)
                    return result

                def interrupting_link(
                    source,
                    destination,
                    real_link=real_link,
                    phase=phase,
                    **kwargs,
                ):
                    nonlocal interrupted
                    result = real_link(source, destination, **kwargs)
                    if (
                        not interrupted
                        and phase == "after-replacement-publication"
                        and str(source).endswith(".new")
                        and destination == f"{DRAFT_ID}.json"
                    ):
                        interrupted = True
                        raise SimulatedProcessInterruption(phase)
                    return result

                def interrupting_unlink(
                    selected,
                    real_unlink=real_unlink,
                    phase=phase,
                    **kwargs,
                ):
                    nonlocal interrupted
                    is_quarantine = str(selected).endswith(".quarantine") or str(selected).endswith(
                        ".quarantine.removing"
                    )
                    if not interrupted and phase == "before-quarantine-cleanup" and is_quarantine:
                        interrupted = True
                        raise SimulatedProcessInterruption(phase)
                    result = real_unlink(selected, **kwargs)
                    if not interrupted and phase == "after-quarantine-cleanup" and is_quarantine:
                        interrupted = True
                        raise SimulatedProcessInterruption(phase)
                    return result

                with (
                    mock.patch.object(STORAGE.secrets, "token_hex", return_value=TRANSACTION_ID),
                    mock.patch.object(
                        STORAGE, "_rename_noreplace", side_effect=interrupting_rename
                    ),
                    mock.patch.object(STORAGE.os, "link", side_effect=interrupting_link),
                    mock.patch.object(STORAGE.os, "unlink", side_effect=interrupting_unlink),
                ):
                    with self.assertRaises(SimulatedProcessInterruption):
                        STORAGE.cas_replace_private_draft(
                            root,
                            DRAFT_ID,
                            canonical_bytes(expected),
                            canonical_bytes(replacement),
                        )

                self.assertTrue(interrupted)
                self.assertEqual(
                    tuple(item.name for item in sorted(path.parent.iterdir())),
                    surviving_names,
                )
                self.assertEqual(
                    {stat.S_IMODE(item.stat().st_mode) for item in path.parent.iterdir()},
                    {0o600},
                )

                STORAGE.recover_private_draft_transaction(root, DRAFT_ID)

                self.assertEqual(STORAGE.load_private_draft(root, DRAFT_ID), replacement)
                self.assertEqual(
                    sorted(item.name for item in path.parent.iterdir()),
                    [".draft-transaction.lock", f"{DRAFT_ID}.json"],
                )
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(path.stat().st_nlink, 1)

    @unittest.skipIf(STORAGE.fcntl is None, "requires POSIX flock")
    def test_draft_and_report_lock_contention_errors_and_modes_are_stable(self):
        _expected, path = self.write_draft()
        draft_lock = path.parent / ".draft-transaction.lock"
        descriptor = os.open(draft_lock, os.O_RDWR | os.O_CREAT, 0o600)
        STORAGE.fcntl.flock(descriptor, STORAGE.fcntl.LOCK_EX)
        try:
            with self.assertRaisesRegex(ValueError, "draft transaction recovery is busy; retry"):
                STORAGE.recover_private_draft_transaction(self.root, DRAFT_ID)
        finally:
            STORAGE.fcntl.flock(descriptor, STORAGE.fcntl.LOCK_UN)
            os.close(descriptor)
        self.assertEqual(stat.S_IMODE(draft_lock.stat().st_mode), 0o600)

        with STORAGE.report_lock(self.root, "RPT-001"):
            pass
        report_lock = (
            self.root / ".requirements-impact-refiner" / "reports" / "RPT-001" / ".controller.lock"
        )
        self.assertEqual(stat.S_IMODE(report_lock.stat().st_mode), 0o600)
        report_descriptor = os.open(report_lock, os.O_RDWR)
        STORAGE.fcntl.flock(report_descriptor, STORAGE.fcntl.LOCK_EX)

        class Deadline:
            checks = 0

            def expired(self):
                self.checks += 1
                return self.checks > 1

            def remaining(self):
                return 0.0

        try:
            with self.assertRaisesRegex(
                ValueError, "graph trace deadline exhausted waiting for controller lock"
            ):
                with STORAGE.report_lock(self.root, "RPT-001", deadline=Deadline()):
                    self.fail("contended report lock was acquired")
        finally:
            STORAGE.fcntl.flock(report_descriptor, STORAGE.fcntl.LOCK_UN)
            os.close(report_descriptor)

    def test_controller_metadata_and_consumed_draft_remain_canonical_and_private(self):
        draft, path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        key_map = {"impacts": {"member-edit": "IMP-001"}}
        state_bytes = b'{"schema_version":1}\n'

        STORAGE.write_controller_metadata(
            self.root,
            draft,
            state_bytes,
            key_map,
            {"receipt_id": "3" * 32, "sha256": "4" * 64},
        )

        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        metadata = {
            "draft_id": DRAFT_ID,
            "graph_receipt": {"receipt_id": "3" * 32, "sha256": "4" * 64},
            "key_map": key_map,
            "report_id": "RPT-001",
            "revision": 1,
            "schema_version": 2,
            "state_sha256": hashlib.sha256(state_bytes).hexdigest(),
        }
        self.assertEqual(metadata_path.read_bytes(), canonical_bytes(metadata))
        self.assertEqual(stat.S_IMODE(metadata_path.stat().st_mode), 0o600)

        published = SimpleNamespace(
            report_id="RPT-001",
            revision=1,
            markdown_sha256="5" * 64,
        )
        STORAGE.consume_draft(path, draft, published, key_map)

        consumed = dict(draft)
        consumed["consumed"] = True
        consumed["key_map"] = key_map
        consumed["published"] = {
            "markdown_sha256": "5" * 64,
            "report_id": "RPT-001",
            "revision": 1,
        }
        self.assertEqual(path.read_bytes(), canonical_bytes(consumed))
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_completion_metadata_binds_analysis_and_report_context_identity(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        key_map = {"impacts": {"member-edit": "IMP-001"}}
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": True,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": "8" * 64,
        }

        STORAGE.write_controller_metadata(
            self.root,
            draft,
            state_bytes,
            key_map,
            {"receipt_id": "3" * 32, "sha256": "4" * 64},
            "9" * 64,
            context_identity,
        )
        current = SimpleNamespace(
            report_id="RPT-001",
            revision=1,
            state_path=(
                self.root
                / ".requirements-impact-refiner"
                / "reports"
                / "RPT-001"
                / "revision-0001.json"
            ),
        )
        current.state_path.write_bytes(state_bytes)

        metadata = STORAGE.load_controller_completion_metadata(current)

        self.assertEqual(metadata["analysis_sha256"], "9" * 64)
        self.assertEqual(metadata["context_identity"], context_identity)
        self.assertEqual(metadata["key_map"], key_map)
        self.assertEqual(STORAGE.load_controller_metadata(current), key_map)

    def test_legacy_completion_metadata_validator_accepts_only_exact_v1_identity(self):
        state_sha256 = "1" * 64
        legacy = {
            "schema_version": 1,
            "draft_id": DRAFT_ID,
            "report_id": "RPT-001",
            "revision": 1,
            "state_sha256": state_sha256,
            "key_map": {"impacts": {}},
            "analysis_sha256": "2" * 64,
            "context_identity": {
                "repo_root_sha256": "3" * 64,
                "requirement_sha256": "4" * 64,
                "source_inventory_sha256": None,
                "source_inventory_available": False,
                "source_inventory_complete": False,
                "payload_sha256": "5" * 64,
            },
        }
        raw = canonical_bytes(legacy)
        self.assertEqual(
            STORAGE._validate_legacy_controller_metadata_bytes(
                raw,
                report_id="RPT-001",
                revision=1,
                state_sha256=state_sha256,
            ),
            legacy,
        )
        variants = (
            {**legacy, "schema_version": 2},
            {**legacy, "draft_id": "bad"},
            {**legacy, "state_sha256": "6" * 64},
            {**legacy, "analysis_sha256": "bad"},
            {**legacy, "context_identity": {}},
            {**legacy, "unknown": True},
            {
                **legacy,
                "graph_receipt": {"receipt_id": "bad", "sha256": "7" * 64},
            },
        )
        for value in variants:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    STORAGE._validate_legacy_controller_metadata_bytes(
                        canonical_bytes(value),
                        report_id="RPT-001",
                        revision=1,
                        state_sha256=state_sha256,
                    )
        with self.assertRaises(ValueError):
            STORAGE._validate_legacy_controller_metadata_bytes(
                b"{}",
                report_id="RPT-001",
                revision=1,
                state_sha256=state_sha256,
            )

    def test_partial_metadata_stage_is_reader_invisible_and_does_not_block_replacement(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        old_key_map = {"version": "old"}
        new_key_map = {"version": "new"}
        STORAGE.write_controller_metadata(
            self.root,
            draft,
            state_bytes,
            old_key_map,
            None,
            "8" * 64,
            context_identity,
        )
        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        pending = metadata_path.parent / f".{metadata_path.name}.pending"
        old_payload = metadata_path.read_bytes()
        real_write = STORAGE.os.write
        interrupted = False

        class SimulatedCrash(BaseException):
            pass

        def crashing_write(descriptor, payload):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                real_write(descriptor, payload[:11])
                raise SimulatedCrash("metadata stage write interrupted")
            return real_write(descriptor, payload)

        with mock.patch.object(STORAGE.os, "write", side_effect=crashing_write):
            with self.assertRaises(SimulatedCrash):
                STORAGE.write_controller_metadata(
                    self.root,
                    draft,
                    state_bytes,
                    new_key_map,
                    None,
                    "9" * 64,
                    context_identity,
                )

        stages = tuple(metadata_path.parent.glob(f".{metadata_path.name}.stage-*"))
        self.assertEqual(len(stages), 1)
        self.assertFalse(pending.exists())
        self.assertEqual(metadata_path.read_bytes(), old_payload)
        state_path = metadata_path.with_name(".reader-state")
        state_path.write_bytes(state_bytes)
        current = SimpleNamespace(report_id="RPT-001", revision=1, state_path=state_path)
        self.assertEqual(
            STORAGE.load_controller_completion_metadata(current)["key_map"], old_key_map
        )

        with mock.patch.object(
            STORAGE.os,
            "scandir",
            side_effect=AssertionError("metadata stage retry must not scan the report lineage"),
        ):
            STORAGE.write_controller_metadata(
                self.root,
                draft,
                state_bytes,
                new_key_map,
                None,
                "9" * 64,
                context_identity,
            )

        loaded = STORAGE.load_controller_completion_metadata(current)
        self.assertEqual(loaded["analysis_sha256"], "9" * 64)
        self.assertEqual(loaded["key_map"], new_key_map)
        self.assertTrue(stages[0].exists())

    def test_metadata_stage_collision_preserves_foreign_file_and_retries_candidate(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        real_open = STORAGE.os.open
        foreign_names = []

        def collide_once(name, flags, *args, **kwargs):
            if str(name).startswith(f".{metadata_path.name}.stage-") and not foreign_names:
                descriptor = real_open(name, flags, *args, **kwargs)
                os.write(descriptor, b"foreign-metadata-stage")
                os.close(descriptor)
                foreign_names.append(str(name))
                raise FileExistsError(str(name))
            return real_open(name, flags, *args, **kwargs)

        with (
            mock.patch.object(STORAGE.os, "open", side_effect=collide_once),
            mock.patch.object(
                STORAGE.os,
                "scandir",
                side_effect=AssertionError("metadata stage creation must not scan"),
            ),
        ):
            STORAGE.write_controller_metadata(
                self.root,
                draft,
                state_bytes,
                {},
                None,
                "9" * 64,
                context_identity,
            )

        self.assertEqual(len(foreign_names), 1)
        foreign = metadata_path.parent / foreign_names[0]
        self.assertEqual(foreign.read_bytes(), b"foreign-metadata-stage")
        self.assertTrue(metadata_path.is_file())

    def test_metadata_stage_candidate_collisions_are_bounded(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        real_open = STORAGE.os.open
        attempts = 0

        def colliding_open(name, flags, *args, **kwargs):
            nonlocal attempts
            if str(name).startswith(f".{metadata_path.name}.stage-"):
                attempts += 1
                if attempts > 16:
                    raise AssertionError("metadata stage candidate loop is unbounded")
                raise FileExistsError(str(name))
            return real_open(name, flags, *args, **kwargs)

        with mock.patch.object(STORAGE.os, "open", side_effect=colliding_open):
            with self.assertRaisesRegex(ValueError, "candidate limit"):
                STORAGE.write_controller_metadata(
                    self.root,
                    draft,
                    state_bytes,
                    {},
                    None,
                    "9" * 64,
                    context_identity,
                )

        self.assertGreater(attempts, 0)
        self.assertLessEqual(attempts, 16)
        self.assertFalse(metadata_path.exists())
        self.assertFalse((metadata_path.parent / f".{metadata_path.name}.pending").exists())

    def test_metadata_stage_cleanup_never_deletes_a_foreign_replacement(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        real_open = STORAGE.os.open
        real_write = STORAGE.os.write
        stage_name = None
        stage_directory_fd = None

        def recording_open(name, flags, *args, **kwargs):
            nonlocal stage_name, stage_directory_fd
            descriptor = real_open(name, flags, *args, **kwargs)
            if str(name).startswith(f".{metadata_path.name}.stage-"):
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
            raise OSError("injected metadata stage failure after foreign replacement")

        with (
            mock.patch.object(STORAGE.os, "open", side_effect=recording_open),
            mock.patch.object(STORAGE.os, "write", side_effect=replace_stage_then_fail),
        ):
            with self.assertRaisesRegex(ValueError, "stage"):
                STORAGE.write_controller_metadata(
                    self.root,
                    draft,
                    state_bytes,
                    {},
                    None,
                    "9" * 64,
                    context_identity,
                )

        foreign = metadata_path.parent / str(stage_name)
        self.assertEqual(foreign.read_bytes(), b"foreign-replacement")
        self.assertFalse(metadata_path.exists())
        self.assertFalse((metadata_path.parent / f".{metadata_path.name}.pending").exists())
        STORAGE.write_controller_metadata(
            self.root,
            draft,
            state_bytes,
            {},
            None,
            "9" * 64,
            context_identity,
        )

    def test_metadata_stage_cleanup_failure_leaves_no_authority_and_retry_succeeds(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        pending = metadata_path.parent / f".{metadata_path.name}.pending"
        real_write = STORAGE.os.write
        real_unlink = STORAGE.os.unlink
        failed_write = False

        def failing_write(descriptor, payload):
            nonlocal failed_write
            if not failed_write:
                failed_write = True
                real_write(descriptor, payload[:13])
                raise OSError("injected metadata stage write failure")
            return real_write(descriptor, payload)

        def failing_stage_unlink(name, *args, **kwargs):
            if str(name).startswith(f".{metadata_path.name}.stage-"):
                raise OSError("injected metadata stage cleanup failure")
            return real_unlink(name, *args, **kwargs)

        with (
            mock.patch.object(STORAGE.os, "write", side_effect=failing_write),
            mock.patch.object(STORAGE.os, "unlink", side_effect=failing_stage_unlink),
        ):
            with self.assertRaisesRegex(ValueError, "stage"):
                STORAGE.write_controller_metadata(
                    self.root,
                    draft,
                    state_bytes,
                    {},
                    None,
                    "9" * 64,
                    context_identity,
                )

        stages = tuple(metadata_path.parent.glob(f".{metadata_path.name}.stage-*"))
        self.assertEqual(len(stages), 1)
        self.assertFalse(metadata_path.exists())
        self.assertFalse(pending.exists())
        STORAGE.write_controller_metadata(
            self.root,
            draft,
            state_bytes,
            {},
            None,
            "9" * 64,
            context_identity,
        )
        self.assertTrue(metadata_path.is_file())

    def test_metadata_crash_before_and_after_stage_rename_is_retryable(self):
        for phase in ("before", "after"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                draft = {
                    "consumed": False,
                    "draft_id": DRAFT_ID,
                    "repo_root": str(root),
                    "report_id": "RPT-001",
                    "revision": 1,
                }
                state_bytes = b'{"schema_version":1}\n'
                context_identity = {
                    "payload_sha256": "5" * 64,
                    "repo_root_sha256": "6" * 64,
                    "requirement_sha256": "7" * 64,
                    "state_sha256": "a" * 64,
                    "repository_evidence_sha256": "b" * 64,
                    "source_inventory_available": False,
                    "source_inventory_complete": False,
                    "source_inventory_git_tracked_only": False,
                    "source_inventory_sha256": None,
                }
                metadata_path = (
                    root
                    / ".requirements-impact-refiner"
                    / "reports"
                    / "RPT-001"
                    / "revision-0001.controller.json"
                )
                pending = metadata_path.parent / f".{metadata_path.name}.pending"
                real_replace = STORAGE.os.replace

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
                        raise SimulatedCrash(f"{current_phase} metadata stage rename")
                    return current_replace(source, destination, *args, **kwargs)

                with mock.patch.object(STORAGE.os, "replace", side_effect=crashing_replace):
                    with self.assertRaises(SimulatedCrash):
                        STORAGE.write_controller_metadata(
                            root,
                            draft,
                            state_bytes,
                            {},
                            None,
                            "9" * 64,
                            context_identity,
                        )

                self.assertFalse(metadata_path.exists())
                self.assertEqual(pending.exists(), phase == "after")
                STORAGE.write_controller_metadata(
                    root,
                    draft,
                    state_bytes,
                    {},
                    None,
                    "9" * 64,
                    context_identity,
                )
                self.assertTrue(metadata_path.is_file())
                self.assertFalse(pending.exists())

    def test_metadata_crash_after_stage_rename_fsync_recovers_complete_pending(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        pending = metadata_path.parent / f".{metadata_path.name}.pending"
        real_fsync = STORAGE.os.fsync
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
                and not metadata_path.exists()
            ):
                interrupted = True
                raise SimulatedCrash("metadata pending directory entry is durable")
            return result

        with mock.patch.object(STORAGE.os, "fsync", side_effect=crash_after_pending_fsync):
            with self.assertRaises(SimulatedCrash):
                STORAGE.write_controller_metadata(
                    self.root,
                    draft,
                    state_bytes,
                    {},
                    None,
                    "9" * 64,
                    context_identity,
                )

        self.assertTrue(interrupted)
        self.assertFalse(metadata_path.exists())
        self.assertTrue(pending.is_file())
        STORAGE.write_controller_metadata(
            self.root,
            draft,
            state_bytes,
            {},
            None,
            "9" * 64,
            context_identity,
        )
        self.assertTrue(metadata_path.is_file())
        self.assertFalse(pending.exists())

    def test_new_complete_pending_replaces_valid_old_same_draft_metadata_after_crash(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        old_key_map = {"version": "old"}
        new_key_map = {"version": "new"}
        STORAGE.write_controller_metadata(
            self.root,
            draft,
            state_bytes,
            old_key_map,
            None,
            "8" * 64,
            context_identity,
        )
        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        pending = metadata_path.parent / f".{metadata_path.name}.pending"
        old_payload = metadata_path.read_bytes()
        real_replace = STORAGE.os.replace

        class SimulatedCrash(BaseException):
            pass

        def crash_before_target_replace(source, destination, *args, **kwargs):
            if str(source) == pending.name and str(destination) == metadata_path.name:
                raise SimulatedCrash("new pending durable before target replacement")
            return real_replace(source, destination, *args, **kwargs)

        with mock.patch.object(STORAGE.os, "replace", side_effect=crash_before_target_replace):
            with self.assertRaises(SimulatedCrash):
                STORAGE.write_controller_metadata(
                    self.root,
                    draft,
                    state_bytes,
                    new_key_map,
                    None,
                    "9" * 64,
                    context_identity,
                )

        self.assertEqual(metadata_path.read_bytes(), old_payload)
        pending_payload = pending.read_bytes()
        self.assertNotEqual(pending_payload, old_payload)
        state_path = metadata_path.with_name(".reader-state")
        state_path.write_bytes(state_bytes)
        current = SimpleNamespace(report_id="RPT-001", revision=1, state_path=state_path)
        with self.assertRaisesRegex(ValueError, "pending state"):
            STORAGE.load_controller_completion_metadata(current)

        with mock.patch.object(
            STORAGE.os,
            "scandir",
            side_effect=AssertionError("metadata replacement recovery must not scan"),
        ):
            STORAGE.write_controller_metadata(
                self.root,
                draft,
                state_bytes,
                new_key_map,
                None,
                "9" * 64,
                context_identity,
            )

        self.assertFalse(pending.exists())
        loaded = STORAGE.load_controller_completion_metadata(current)
        self.assertEqual(loaded["analysis_sha256"], "9" * 64)
        self.assertEqual(loaded["key_map"], new_key_map)

    def test_metadata_retry_after_target_replace_and_directory_fsync_crashes(self):
        state_bytes = b'{"schema_version":1}\n'
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        for phase in ("after-replace", "after-fsync"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                draft = {
                    "consumed": False,
                    "draft_id": DRAFT_ID,
                    "repo_root": str(root),
                    "report_id": "RPT-001",
                    "revision": 1,
                }
                STORAGE.write_controller_metadata(
                    root,
                    draft,
                    state_bytes,
                    {"version": "old"},
                    None,
                    "8" * 64,
                    context_identity,
                )
                metadata_path = (
                    root
                    / ".requirements-impact-refiner"
                    / "reports"
                    / "RPT-001"
                    / "revision-0001.controller.json"
                )
                pending = metadata_path.parent / f".{metadata_path.name}.pending"
                real_replace = STORAGE.os.replace
                real_fsync = STORAGE.os.fsync
                fault_state = {"replacement_completed": False, "interrupted": False}

                class SimulatedCrash(BaseException):
                    pass

                def crashing_replace(
                    source,
                    destination,
                    *args,
                    pending_name=pending.name,
                    target_name=metadata_path.name,
                    current_phase=phase,
                    current_replace=real_replace,
                    state=fault_state,
                    **kwargs,
                ):
                    result = current_replace(source, destination, *args, **kwargs)
                    if str(source) == pending_name and str(destination) == target_name:
                        state["replacement_completed"] = True
                        if current_phase == "after-replace":
                            state["interrupted"] = True
                            raise SimulatedCrash("metadata target replaced before fsync")
                    return result

                def crashing_fsync(
                    descriptor,
                    current_phase=phase,
                    current_fsync=real_fsync,
                    state=fault_state,
                ):
                    result = current_fsync(descriptor)
                    if (
                        current_phase == "after-fsync"
                        and state["replacement_completed"]
                        and not state["interrupted"]
                        and stat.S_ISDIR(os.fstat(descriptor).st_mode)
                    ):
                        state["interrupted"] = True
                        raise SimulatedCrash("metadata replacement directory entry is durable")
                    return result

                with (
                    mock.patch.object(STORAGE.os, "replace", side_effect=crashing_replace),
                    mock.patch.object(STORAGE.os, "fsync", side_effect=crashing_fsync),
                ):
                    with self.assertRaises(SimulatedCrash):
                        STORAGE.write_controller_metadata(
                            root,
                            draft,
                            state_bytes,
                            {"version": "new"},
                            None,
                            "9" * 64,
                            context_identity,
                        )

                self.assertTrue(fault_state["interrupted"])
                self.assertFalse(pending.exists())
                STORAGE.write_controller_metadata(
                    root,
                    draft,
                    state_bytes,
                    {"version": "new"},
                    None,
                    "9" * 64,
                    context_identity,
                )
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                self.assertEqual(metadata["analysis_sha256"], "9" * 64)
                self.assertEqual(metadata["key_map"], {"version": "new"})

    def test_pending_metadata_replacement_rechecks_draft_analysis_artifacts_and_bytes(self):
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        state_bytes = b'{"schema_version":1}\n'
        for rejection in ("draft", "analysis", "artifacts", "tamper"):
            with self.subTest(rejection=rejection), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                draft = {
                    "consumed": False,
                    "draft_id": DRAFT_ID,
                    "repo_root": str(root),
                    "report_id": "RPT-001",
                    "revision": 1,
                }
                STORAGE.write_controller_metadata(
                    root,
                    draft,
                    state_bytes,
                    {"version": "old"},
                    None,
                    "8" * 64,
                    context_identity,
                )
                metadata_path = (
                    root
                    / ".requirements-impact-refiner"
                    / "reports"
                    / "RPT-001"
                    / "revision-0001.controller.json"
                )
                pending = metadata_path.parent / f".{metadata_path.name}.pending"
                real_replace = STORAGE.os.replace

                class SimulatedCrash(BaseException):
                    pass

                def crash_before_target_replace(
                    source,
                    destination,
                    *args,
                    pending_name=pending.name,
                    target_name=metadata_path.name,
                    current_replace=real_replace,
                    **kwargs,
                ):
                    if str(source) == pending_name and str(destination) == target_name:
                        raise SimulatedCrash("pending preserved")
                    return current_replace(source, destination, *args, **kwargs)

                with mock.patch.object(
                    STORAGE.os,
                    "replace",
                    side_effect=crash_before_target_replace,
                ):
                    with self.assertRaises(SimulatedCrash):
                        STORAGE.write_controller_metadata(
                            root,
                            draft,
                            state_bytes,
                            {"version": "new"},
                            None,
                            "9" * 64,
                            context_identity,
                        )

                retry_draft = draft
                retry_analysis = "9" * 64
                if rejection == "draft":
                    retry_draft = dict(draft, draft_id="2" * 32)
                elif rejection == "analysis":
                    retry_analysis = "a" * 64
                elif rejection == "artifacts":
                    metadata_path.with_name("revision-0001.md").write_text(
                        "published",
                        encoding="utf-8",
                    )
                else:
                    pending.write_bytes(b"tampered")

                with self.assertRaises(ValueError):
                    STORAGE.write_controller_metadata(
                        root,
                        retry_draft,
                        state_bytes,
                        {"version": "new"},
                        None,
                        retry_analysis,
                        context_identity,
                    )

                self.assertTrue(metadata_path.is_file())
                self.assertTrue(pending.is_file())

    def test_completion_metadata_size_contract_is_symmetric_at_the_boundary(self):
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        state_bytes = b'{"schema_version":1}\n'
        for delta in (-1, 0, 1):
            with self.subTest(delta=delta), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                draft = {
                    "consumed": False,
                    "draft_id": DRAFT_ID,
                    "repo_root": str(root),
                    "report_id": "RPT-001",
                    "revision": 1,
                }
                metadata = {
                    "analysis_sha256": "9" * 64,
                    "context_identity": context_identity,
                    "draft_id": DRAFT_ID,
                    "key_map": {"padding": ""},
                    "report_id": "RPT-001",
                    "revision": 1,
                    "schema_version": 2,
                    "state_sha256": hashlib.sha256(state_bytes).hexdigest(),
                }
                base_size = len(canonical_bytes(metadata))
                padding = STORAGE.MAX_CONTROLLER_METADATA_BYTES - base_size + delta
                self.assertGreater(padding, 0)
                key_map = {"padding": "x" * padding}
                metadata["key_map"] = key_map
                self.assertEqual(
                    len(canonical_bytes(metadata)),
                    STORAGE.MAX_CONTROLLER_METADATA_BYTES + delta,
                )
                metadata_path = (
                    root
                    / ".requirements-impact-refiner"
                    / "reports"
                    / "RPT-001"
                    / "revision-0001.controller.json"
                )
                if delta > 0:
                    with self.assertRaisesRegex(ValueError, "256 KiB"):
                        STORAGE.write_controller_metadata(
                            root,
                            draft,
                            state_bytes,
                            key_map,
                            None,
                            "9" * 64,
                            context_identity,
                        )
                    self.assertFalse(metadata_path.exists())
                    continue
                STORAGE.write_controller_metadata(
                    root,
                    draft,
                    state_bytes,
                    key_map,
                    None,
                    "9" * 64,
                    context_identity,
                )
                state_path = metadata_path.with_name("revision-0001.json")
                state_path.write_bytes(state_bytes)
                current = SimpleNamespace(
                    report_id="RPT-001",
                    revision=1,
                    state_path=state_path,
                )
                loaded = STORAGE.load_controller_completion_metadata(current)
                self.assertEqual(loaded["key_map"], key_map)

    def test_completion_metadata_depth_is_rejected_before_publication(self):
        nested = {}
        for _index in range(STORAGE.MAX_CONTROLLER_METADATA_DEPTH + 1):
            nested = {"nested": nested}
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }

        with self.assertRaisesRegex(ValueError, "depth"):
            STORAGE.write_controller_metadata(
                self.root,
                draft,
                b'{"schema_version":1}\n',
                nested,
                None,
                "9" * 64,
                context_identity,
            )

        self.assertFalse(
            (
                self.root
                / ".requirements-impact-refiner"
                / "reports"
                / "RPT-001"
                / "revision-0001.controller.json"
            ).exists()
        )

    def test_completion_metadata_cleanup_failure_is_mandatory_and_retryable(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        key_map = {"impacts": {"member-edit": "IMP-001"}}
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        real_unlink = STORAGE.os.unlink

        def failing_metadata_unlink(name, *args, **kwargs):
            if "revision-0001.controller.json" in str(name):
                raise OSError("injected metadata cleanup failure")
            return real_unlink(name, *args, **kwargs)

        with mock.patch.object(STORAGE.os, "unlink", side_effect=failing_metadata_unlink):
            with self.assertRaisesRegex(ValueError, "cleanup"):
                STORAGE.write_controller_metadata(
                    self.root,
                    draft,
                    state_bytes,
                    key_map,
                    None,
                    "9" * 64,
                    context_identity,
                )

        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        self.assertEqual(metadata_path.stat().st_nlink, 2)
        pending = metadata_path.parent / f".{metadata_path.name}.pending"
        self.assertTrue(pending.is_file())
        STORAGE.write_controller_metadata(
            self.root,
            draft,
            state_bytes,
            key_map,
            None,
            "9" * 64,
            context_identity,
        )
        self.assertEqual(metadata_path.stat().st_nlink, 1)
        self.assertFalse(pending.exists())

    def test_completion_metadata_pre_link_pending_recovers_without_scan(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }

        class SimulatedCrash(BaseException):
            pass

        with mock.patch.object(
            STORAGE.os,
            "link",
            side_effect=SimulatedCrash("pending durable before metadata link"),
        ):
            with self.assertRaises(SimulatedCrash):
                STORAGE.write_controller_metadata(
                    self.root,
                    draft,
                    state_bytes,
                    {},
                    None,
                    "9" * 64,
                    context_identity,
                )
        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        pending = metadata_path.parent / f".{metadata_path.name}.pending"
        self.assertFalse(metadata_path.exists())
        self.assertTrue(pending.is_file())
        self.assertEqual(pending.stat().st_nlink, 1)

        with mock.patch.object(
            STORAGE.os,
            "scandir",
            side_effect=AssertionError("metadata recovery must not scan"),
        ):
            STORAGE.write_controller_metadata(
                self.root,
                draft,
                state_bytes,
                {},
                None,
                "9" * 64,
                context_identity,
            )

        self.assertTrue(metadata_path.is_file())
        self.assertFalse(pending.exists())
        self.assertEqual(metadata_path.stat().st_nlink, 1)

    def test_completion_metadata_crash_recovers_across_long_lineage(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        key_map = {"impacts": {"member-edit": "IMP-001"}}
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        real_unlink = STORAGE.os.unlink

        class SimulatedCrash(BaseException):
            pass

        def crashing_metadata_unlink(name, *args, **kwargs):
            if str(name).endswith(".controller.json.pending"):
                raise SimulatedCrash("metadata linked before cleanup")
            return real_unlink(name, *args, **kwargs)

        with mock.patch.object(STORAGE.os, "unlink", side_effect=crashing_metadata_unlink):
            with self.assertRaises(SimulatedCrash):
                STORAGE.write_controller_metadata(
                    self.root,
                    draft,
                    state_bytes,
                    key_map,
                    None,
                    "9" * 64,
                    context_identity,
                )
        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        pending = metadata_path.parent / f".{metadata_path.name}.pending"
        self.assertEqual(metadata_path.stat().st_nlink, 2)
        self.assertEqual(pending.stat().st_ino, metadata_path.stat().st_ino)
        for revision in range(2, 132):
            for suffix in ("json", "md", "controller.json", "context.json"):
                (metadata_path.parent / f"revision-{revision:04d}.{suffix}").write_bytes(b"x")
        self.assertGreater(len(tuple(metadata_path.parent.iterdir())), 500)

        with mock.patch.object(
            STORAGE.os,
            "scandir",
            side_effect=AssertionError("metadata recovery must not scan"),
        ):
            STORAGE.write_controller_metadata(
                self.root,
                draft,
                state_bytes,
                key_map,
                None,
                "9" * 64,
                context_identity,
            )

        self.assertEqual(metadata_path.stat().st_nlink, 1)
        self.assertFalse(pending.exists())

    def test_completion_metadata_exact_target_removes_separate_pending(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        STORAGE.write_controller_metadata(
            self.root,
            draft,
            state_bytes,
            {},
            None,
            "9" * 64,
            context_identity,
        )
        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        pending = metadata_path.parent / f".{metadata_path.name}.pending"
        pending.write_bytes(metadata_path.read_bytes())
        pending.chmod(0o600)
        self.assertNotEqual(pending.stat().st_ino, metadata_path.stat().st_ino)

        with mock.patch.object(
            STORAGE.os,
            "scandir",
            side_effect=AssertionError("metadata recovery must not scan"),
        ):
            STORAGE.write_controller_metadata(
                self.root,
                draft,
                state_bytes,
                {},
                None,
                "9" * 64,
                context_identity,
            )

        self.assertFalse(pending.exists())
        self.assertEqual(metadata_path.stat().st_nlink, 1)

    def test_completion_metadata_fsync_failure_retries_single_link(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        real_unlink = STORAGE.os.unlink
        real_fsync = STORAGE.os.fsync
        cleaned = False
        failed = False

        def recording_unlink(*args, **kwargs):
            nonlocal cleaned
            result = real_unlink(*args, **kwargs)
            if "revision-0001.controller.json" in str(args[0]):
                cleaned = True
            return result

        def failing_directory_fsync(descriptor):
            nonlocal failed
            if cleaned and not failed:
                failed = True
                raise OSError("injected metadata directory fsync failure")
            return real_fsync(descriptor)

        with (
            mock.patch.object(STORAGE.os, "unlink", side_effect=recording_unlink),
            mock.patch.object(STORAGE.os, "fsync", side_effect=failing_directory_fsync),
        ):
            with self.assertRaisesRegex(ValueError, "fsync"):
                STORAGE.write_controller_metadata(
                    self.root,
                    draft,
                    state_bytes,
                    {},
                    None,
                    "9" * 64,
                    context_identity,
                )

        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        self.assertEqual(metadata_path.stat().st_nlink, 1)
        STORAGE.write_controller_metadata(
            self.root,
            draft,
            state_bytes,
            {},
            None,
            "9" * 64,
            context_identity,
        )

    def test_completion_metadata_arbitrary_hardlink_is_not_recovered(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "state_sha256": "a" * 64,
            "repository_evidence_sha256": "b" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_git_tracked_only": False,
            "source_inventory_sha256": None,
        }
        STORAGE.write_controller_metadata(
            self.root,
            draft,
            state_bytes,
            {},
            None,
            "9" * 64,
            context_identity,
        )
        metadata_path = (
            self.root
            / ".requirements-impact-refiner"
            / "reports"
            / "RPT-001"
            / "revision-0001.controller.json"
        )
        state_path = metadata_path.with_name("revision-0001.json")
        state_path.write_bytes(state_bytes)
        arbitrary = metadata_path.with_name("arbitrary-metadata-hardlink")
        os.link(metadata_path, arbitrary)
        current = SimpleNamespace(
            report_id="RPT-001",
            revision=1,
            state_path=state_path,
        )

        with self.assertRaisesRegex(ValueError, "pending state"):
            STORAGE.load_controller_completion_metadata(current)

        self.assertTrue(arbitrary.exists())
        self.assertEqual(metadata_path.stat().st_nlink, 2)

    def test_controller_clean_path_reuses_the_canonical_storage_module(self):
        self.assertIs(CONTROLLER.STORAGE, STORAGE)
        self.assertIs(CONTROLLER.fcntl, STORAGE.fcntl)
        for facade_name, storage_name in (
            ("_root", "root_path"),
            ("_write_private_draft", "write_private_draft"),
            ("_draft_path", "draft_path"),
            ("_load_controller_metadata", "load_controller_metadata"),
            (
                "_load_controller_completion_metadata",
                "load_controller_completion_metadata",
            ),
            ("_report_lock", "report_lock"),
            ("_write_controller_metadata", "write_controller_metadata"),
            ("_consume", "consume_draft"),
        ):
            with self.subTest(name=facade_name):
                self.assertIs(
                    getattr(CONTROLLER, facade_name),
                    getattr(STORAGE, storage_name),
                )

    def test_storage_does_not_import_or_capture_a_conflicting_contract_alias(self):
        preserved = sys.modules.get("rir_contracts")
        conflict = types.ModuleType("rir_contracts")
        conflict.__file__ = str(self.root / "rir_contracts.py")
        sys.modules["rir_contracts"] = conflict
        try:
            isolated = load_module(
                "rir_storage_without_contract_capture", SCRIPTS / "rir_storage.py"
            )
            self.assertIs(sys.modules["rir_contracts"], conflict)
            self.assertNotIn("CONTRACTS", vars(isolated))
        finally:
            sys.modules.pop("rir_storage_without_contract_capture", None)
            if preserved is None:
                sys.modules.pop("rir_contracts", None)
            else:
                sys.modules["rir_contracts"] = preserved

    def test_pristine_facades_isolate_a_coherent_local_report_graph_from_foreign_aliases(self):
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

calls = []
foreign_compact = types.ModuleType("compact_state")
foreign_compact.__file__ = "/tmp/foreign-compact-state.py"
foreign_compact.DELTA_CATEGORIES = ("added",)
foreign_compact.load_state_bytes = lambda *args, **kwargs: calls.append("compact.load")
foreign_compact.validate_state = lambda *args, **kwargs: calls.append("compact.validate")

foreign_renderer = types.ModuleType("impact_renderer")
foreign_renderer.__file__ = "/tmp/foreign-impact-renderer.py"
foreign_renderer.compact_state = foreign_compact
foreign_renderer.render_markdown = lambda *args, **kwargs: calls.append("renderer.markdown")
foreign_renderer.render_compact = lambda *args, **kwargs: calls.append("renderer.compact")
foreign_renderer.validate_rendered_markdown = (
    lambda *args, **kwargs: calls.append("renderer.validate")
)

class ForeignReportStoreError(RuntimeError):
    pass

foreign_store = types.ModuleType("report_store")
foreign_store.__file__ = "/tmp/foreign-report-store.py"
foreign_store.compact_state = foreign_compact
foreign_store.impact_renderer = foreign_renderer
foreign_store.ReportStoreError = ForeignReportStoreError
foreign_store.CurrentRevision = type("ForeignCurrentRevision", (), {})
foreign_store.load_current = lambda *args, **kwargs: calls.append("store.load")
foreign_store.publish_revision = lambda *args, **kwargs: calls.append("store.publish")
foreign_store.report_directory = lambda *args, **kwargs: calls.append("store.directory")

foreign = {
    "compact_state": foreign_compact,
    "impact_renderer": foreign_renderer,
    "report_store": foreign_store,
}
sys.modules.update(foreign)

for index, directory in enumerate((root_scripts, skill_scripts), start=1):
    controller = load(f"pristine_storage_controller_{index}", directory / "rir_controller.py")
    storage = controller.STORAGE
    report_store = storage.report_store
    compact_state = report_store.compact_state
    renderer = report_store.impact_renderer
    assert Path(storage.__file__).resolve() == (directory / "rir_storage.py").resolve()
    assert Path(report_store.__file__).resolve() == (directory / "report_store.py").resolve()
    assert Path(compact_state.__file__).resolve() == (directory / "compact_state.py").resolve()
    assert Path(renderer.__file__).resolve() == (directory / "impact_renderer.py").resolve()
    assert renderer.compact_state is compact_state
    assert controller.LINEAGE.REPORT_STORE is report_store
    assert controller.FINALIZE.REPORT_STORE is report_store
    assert controller.GRAPH_DELIVERY.STORAGE.report_store is report_store
    for name, sentinel in foreign.items():
        assert sys.modules[name] is sentinel, name

assert calls == [], calls
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(SCRIPTS), str(SKILL_SCRIPTS)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_direct_storage_conflict_load_preserves_foreign_report_graph_aliases(self):
        exact_names = {"compact_state", "impact_renderer", "report_store"}
        prefixes = (
            "_rir_lineage_compact_state_",
            "_rir_lineage_impact_renderer_",
            "_rir_lineage_report_store_",
        )
        preserved = {
            name: module
            for name, module in sys.modules.items()
            if name in exact_names or name.startswith(prefixes)
        }
        module_name = "rir_storage_direct_report_conflict"
        repeat_name = "rir_storage_vacated_report_aliases"
        foreign = {}
        try:
            for name in tuple(sys.modules):
                if name in exact_names or name.startswith(prefixes):
                    sys.modules.pop(name, None)
            for name in exact_names:
                sentinel = types.ModuleType(name)
                sentinel.__file__ = str(self.root / f"foreign-{name}.py")
                foreign[name] = sentinel
                sys.modules[name] = sentinel

            isolated = load_module(module_name, SCRIPTS / "rir_storage.py")

            self.assertEqual(
                Path(isolated.report_store.__file__).resolve(),
                (SCRIPTS / "report_store.py").resolve(),
            )
            self.assertEqual(
                Path(isolated.COMPACT_STATE.__file__).resolve(),
                (SCRIPTS / "compact_state.py").resolve(),
            )
            self.assertEqual(
                Path(isolated.IMPACT_RENDERER.__file__).resolve(),
                (SCRIPTS / "impact_renderer.py").resolve(),
            )
            self.assertIs(isolated.report_store.compact_state, isolated.COMPACT_STATE)
            self.assertIs(isolated.report_store.impact_renderer, isolated.IMPACT_RENDERER)
            self.assertIs(isolated.IMPACT_RENDERER.compact_state, isolated.COMPACT_STATE)
            for name, sentinel in foreign.items():
                self.assertIs(sys.modules[name], sentinel)

            for name in exact_names:
                sys.modules.pop(name)
            repeated = load_module(repeat_name, SCRIPTS / "rir_storage.py")
            self.assertIs(repeated.COMPACT_STATE, isolated.COMPACT_STATE)
            self.assertIs(repeated.IMPACT_RENDERER, isolated.IMPACT_RENDERER)
            self.assertIs(repeated.report_store, isolated.report_store)
            self.assertIs(sys.modules["compact_state"], isolated.COMPACT_STATE)
            self.assertIs(sys.modules["impact_renderer"], isolated.IMPACT_RENDERER)
            self.assertIs(sys.modules["report_store"], isolated.report_store)
        finally:
            for name in tuple(sys.modules):
                if (
                    name in exact_names
                    or name.startswith(prefixes)
                    or name
                    in {
                        module_name,
                        repeat_name,
                    }
                ):
                    sys.modules.pop(name, None)
            sys.modules.update(preserved)

    def test_storage_report_graph_rejects_unsafe_local_and_expected_hash_modules(self):
        script = r"""
import hashlib
import importlib.util
import shutil
import sys
import tempfile
import types
from pathlib import Path

source = Path(sys.argv[1]).resolve()

def load(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module

def clear():
    for name in tuple(sys.modules):
        if name in {"compact_state", "impact_report", "impact_renderer", "report_store"} or name.startswith("_rir_lineage_"):
            sys.modules.pop(name, None)

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    shutil.copyfile(source / "rir_storage.py", root / "rir_storage.py")
    (root / "compact_state.py").write_text("DELTA_CATEGORIES = ()\n", encoding="utf-8")
    try:
        load("incomplete_local_storage", root / "rir_storage.py")
    except ImportError as error:
        assert str(error) == "storage compact state sibling contract is incomplete", error
    else:
        raise AssertionError("incomplete local compact state was accepted")

clear()
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    shutil.copyfile(source / "rir_storage.py", root / "rir_storage.py")
    (root / "compact_state.py").symlink_to(source / "compact_state.py")
    try:
        load("symlink_local_storage", root / "rir_storage.py")
    except ImportError as error:
        assert str(error) == "storage compact state sibling is unsafe", error
    else:
        raise AssertionError("symlinked local compact state was accepted")

clear()
foreign = types.ModuleType("compact_state")
foreign.__file__ = "/tmp/foreign-compact-state.py"
sys.modules["compact_state"] = foreign
expected = (source / "compact_state.py").resolve()
hashed_name = "_rir_lineage_compact_state_" + hashlib.sha256(
    str(expected).encode("utf-8")
).hexdigest()[:16]
invalid = types.ModuleType(hashed_name)
invalid.__file__ = str(expected)
sys.modules[hashed_name] = invalid
try:
    load("invalid_hashed_storage", source / "rir_storage.py")
except ImportError as error:
    assert str(error) == "storage compact state sibling contract is incomplete", error
else:
    raise AssertionError("invalid expected compact-state hash was accepted")
assert sys.modules["compact_state"] is foreign
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(SCRIPTS)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_facades_resolve_fixed_storage_siblings_despite_a_conflicting_alias(self):
        prefix = "_rir_controller_storage_"
        preserved = {
            name: module
            for name, module in sys.modules.items()
            if name == "rir_storage" or name.startswith(prefix)
        }
        controller_names = (
            "storage_collision_root_one",
            "storage_collision_root_two",
            "storage_collision_root_three",
            "storage_collision_skill_one",
        )
        try:
            for name in preserved:
                sys.modules.pop(name, None)
            conflict_path = self.root / "rir_storage.py"
            callable_names = (
                "root_path",
                "write_private_draft",
                "load_private_draft",
                "replace_private_draft",
                "draft_path",
                "load_controller_metadata",
                "cas_replace_private_draft",
                "recover_private_draft_transaction",
                "report_lock",
                "write_controller_metadata",
                "consume_draft",
                "_read_bounded_descriptor",
                "_rename_noreplace",
                "_unlink_transaction_component",
                "_write_private_transaction_component",
            )
            conflict_path.write_text(
                "import re\n"
                "MAX_DRAFT_BYTES = 1\n"
                "DRAFT_ID_PATTERN = re.compile(r'[0-9a-f]{32}')\n"
                + "\n".join(
                    f"def {name}(*args, **kwargs): return 'conflict'" for name in callable_names
                )
                + "\n",
                encoding="utf-8",
            )
            conflict = load_module("rir_storage", conflict_path)
            first_root = load_module(controller_names[0], SCRIPTS / "rir_controller.py")
            second_root = load_module(controller_names[1], SCRIPTS / "rir_controller.py")
            first_skill = load_module(controller_names[3], SKILL_SCRIPTS / "rir_controller.py")

            self.assertIs(sys.modules["rir_storage"], conflict)
            self.assertIs(first_root.STORAGE, second_root.STORAGE)
            self.assertIsNot(first_root.STORAGE, conflict)
            self.assertIsNot(first_skill.STORAGE, conflict)
            self.assertIsNot(first_root.STORAGE, first_skill.STORAGE)
            self.assertEqual(
                Path(first_root.STORAGE.__file__).resolve(),
                (SCRIPTS / "rir_storage.py").resolve(),
            )
            self.assertEqual(
                Path(first_skill.STORAGE.__file__).resolve(),
                (SKILL_SCRIPTS / "rir_storage.py").resolve(),
            )

            later_canonical = load_module("rir_storage", SCRIPTS / "rir_storage.py")
            third_root = load_module(controller_names[2], SCRIPTS / "rir_controller.py")
            self.assertIs(sys.modules["rir_storage"], later_canonical)
            self.assertIs(third_root.STORAGE, first_root.STORAGE)
            self.assertIsNot(third_root.STORAGE, later_canonical)

            sys.modules.pop("rir_storage")
            fourth_root = load_module("storage_collision_root_four", SCRIPTS / "rir_controller.py")
            self.assertIs(fourth_root.STORAGE, first_root.STORAGE)
            self.assertIs(sys.modules["rir_storage"], first_root.STORAGE)
        finally:
            for name in tuple(sys.modules):
                if (
                    name == "rir_storage"
                    or name.startswith(prefix)
                    or name.startswith("storage_collision_")
                ):
                    sys.modules.pop(name, None)
            sys.modules.update(preserved)

    def test_vacant_alias_fails_closed_for_an_invalid_expected_storage_hash(self):
        prefix = "_rir_controller_storage_"
        expected_hash = (
            prefix
            + hashlib.sha256(
                str((SCRIPTS / "rir_storage.py").resolve()).encode("utf-8")
            ).hexdigest()[:16]
        )
        preserved = {
            name: module
            for name, module in sys.modules.items()
            if name == "rir_storage" or name.startswith(prefix)
        }
        try:
            for name in preserved:
                sys.modules.pop(name, None)
            sys.modules[expected_hash] = types.ModuleType(expected_hash)
            with self.assertRaisesRegex(ImportError, "controller storage sibling is unsafe"):
                load_module("invalid_storage_hash_controller", SCRIPTS / "rir_controller.py")
            self.assertNotIn("rir_storage", sys.modules)
        finally:
            for name in tuple(sys.modules):
                if name == "rir_storage" or name.startswith(prefix):
                    sys.modules.pop(name, None)
            sys.modules.update(preserved)
            sys.modules.pop("invalid_storage_hash_controller", None)


if __name__ == "__main__":
    unittest.main()
