import importlib.util
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "fast_scan_store.py"


def load_store():
    if not MODULE.is_file():
        raise AssertionError("scripts/fast_scan_store.py must exist")
    name = "_fast_scan_store_test"
    spec = importlib.util.spec_from_file_location(name, MODULE)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


class FastScanStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.payload = json.dumps(
            {"schema_version": 1, "scan_id": "a" * 32}, sort_keys=True, separators=(",", ":")
        ).encode()

    def tearDown(self):
        self.temporary.cleanup()

    def test_publish_and_load_are_private_atomic_and_exact(self):
        store = load_store()
        path = store.publish_scan_receipt(self.root, "a" * 32, self.payload)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(store.load_scan_receipt_bytes(self.root, "a" * 32), self.payload)

    def test_publish_is_no_replace_and_mutation_is_detected(self):
        store = load_store()
        path = store.publish_scan_receipt(self.root, "a" * 32, self.payload)
        with self.assertRaisesRegex(ValueError, "already exists"):
            store.publish_scan_receipt(self.root, "a" * 32, self.payload)
        path.write_bytes(self.payload + b"x")
        with self.assertRaisesRegex(ValueError, "changed|invalid"):
            store.load_scan_receipt_bytes(self.root, "a" * 32)

    def test_symlinked_scan_directory_and_unsafe_id_are_rejected(self):
        store = load_store()
        outside_context = tempfile.TemporaryDirectory()
        self.addCleanup(outside_context.cleanup)
        base = self.root / ".requirements-impact-refiner"
        base.mkdir()
        (base / "scans").symlink_to(Path(outside_context.name), target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            store.publish_scan_receipt(self.root, "a" * 32, self.payload)
        with self.assertRaisesRegex(ValueError, "scan_id"):
            store.load_scan_receipt_bytes(self.root, "../outside")


if __name__ == "__main__":
    unittest.main()


class WorkspaceDirectoryHygieneTest(unittest.TestCase):
    def setUp(self):
        self.store = load_store()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.payload = b'{"probe": true}'

    def test_does_not_widen_existing_directory_permissions(self):
        base = self.root / ".requirements-impact-refiner"
        base.mkdir(mode=0o700)
        (base / "scans").mkdir(mode=0o700)
        self.store.publish_scan_receipt(self.root, "a" * 32, self.payload)
        self.assertEqual(stat.S_IMODE(base.stat().st_mode), 0o700)

    def test_workspace_ignores_itself_from_version_control(self):
        self.store.publish_scan_receipt(self.root, "a" * 32, self.payload)
        ignore = self.root / ".requirements-impact-refiner" / ".gitignore"
        self.assertEqual(ignore.read_text(), "*\n")

    def test_existing_gitignore_keeps_custom_lines_and_gains_ignore_all(self):
        base = self.root / ".requirements-impact-refiner"
        base.mkdir(mode=0o755)
        (base / ".gitignore").write_text("custom\n")
        self.store.publish_scan_receipt(self.root, "a" * 32, self.payload)
        lines = (base / ".gitignore").read_text().splitlines()
        self.assertIn("custom", lines)
        self.assertIn("*", lines)

    def test_existing_ignore_all_gitignore_is_untouched(self):
        base = self.root / ".requirements-impact-refiner"
        base.mkdir(mode=0o755)
        (base / ".gitignore").write_text("*\n")
        self.store.publish_scan_receipt(self.root, "a" * 32, self.payload)
        self.assertEqual((base / ".gitignore").read_text(), "*\n")

    def test_symlinked_gitignore_is_refused(self):
        base = self.root / ".requirements-impact-refiner"
        base.mkdir(mode=0o755)
        outside = Path(self.tmp.name) / "outside-ignore"
        outside.write_text("decoy\n")
        (base / ".gitignore").symlink_to(outside)
        with self.assertRaises(ValueError):
            self.store.publish_scan_receipt(self.root, "a" * 32, self.payload)
