from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
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

    def test_controller_clean_path_reuses_the_canonical_storage_module(self):
        self.assertIs(CONTROLLER.STORAGE, STORAGE)
        self.assertIs(CONTROLLER.fcntl, STORAGE.fcntl)
        for facade_name, storage_name in (
            ("_root", "root_path"),
            ("_write_private_draft", "write_private_draft"),
            ("_draft_path", "draft_path"),
            ("_load_controller_metadata", "load_controller_metadata"),
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
