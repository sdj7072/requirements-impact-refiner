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
            "schema_version": 1,
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
            "source_inventory_available": True,
            "source_inventory_complete": False,
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

    def test_completion_metadata_size_contract_is_symmetric_at_the_boundary(self):
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
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
                    "schema_version": 1,
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
            "source_inventory_available": False,
            "source_inventory_complete": False,
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
            "source_inventory_available": False,
            "source_inventory_complete": False,
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
        self.assertEqual(tuple(metadata_path.parent.glob(f".{metadata_path.name}.*.tmp")), ())

    def test_completion_metadata_crash_recovers_across_long_lineage(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        key_map = {"impacts": {"member-edit": "IMP-001"}}
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
            "source_inventory_sha256": None,
        }
        real_unlink = STORAGE.os.unlink

        class SimulatedCrash(BaseException):
            pass

        def crashing_metadata_unlink(name, *args, **kwargs):
            if "revision-0001.controller.json" in str(name):
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
        for revision in range(2, 132):
            for suffix in ("json", "md", "controller.json", "context.json"):
                (metadata_path.parent / f"revision-{revision:04d}.{suffix}").write_bytes(b"x")
        self.assertGreater(len(tuple(metadata_path.parent.iterdir())), 500)

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

    def test_completion_metadata_fsync_failure_retries_single_link(self):
        draft, _path = self.write_draft()
        draft.update({"report_id": "RPT-001", "revision": 1})
        state_bytes = b'{"schema_version":1}\n'
        context_identity = {
            "payload_sha256": "5" * 64,
            "repo_root_sha256": "6" * 64,
            "requirement_sha256": "7" * 64,
            "source_inventory_available": False,
            "source_inventory_complete": False,
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
            "source_inventory_available": False,
            "source_inventory_complete": False,
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

        with self.assertRaisesRegex(ValueError, "recovery alias"):
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
