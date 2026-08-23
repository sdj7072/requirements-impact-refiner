import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "compact-state-post-decision.json"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


STORE = load_module("report_store", SCRIPTS / "report_store.py")
CLI = SCRIPTS / "publish-impact-report.py"


def canonical_json(value):
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReportStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.base_state = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def tearDown(self):
        self.temporary.cleanup()

    def state(self, revision=1):
        value = copy.deepcopy(self.base_state)
        value["report"]["revision"] = revision
        if revision > 1:
            value["delta"]["new"] = []
            value["delta"]["unchanged"] = ["IMP-001"]
        return value

    def state_bytes(self, revision=1):
        return canonical_json(self.state(revision))

    def test_publication_is_append_only_and_pointer_is_atomic(self):
        published = STORE.publish_revision(self.root, self.state_bytes())

        self.assertEqual(published.state_path.name, "revision-0001.json")
        self.assertEqual(published.markdown_path.name, "revision-0001.md")
        pointer = json.loads(published.pointer_path.read_text(encoding="utf-8"))
        self.assertEqual(pointer["revision"], 1)
        self.assertEqual(pointer["markdown_sha256"], sha256(published.markdown_path))
        with self.assertRaises(FileExistsError):
            STORE.publish_revision(self.root, self.state_bytes())

    def test_revision_two_hashes_exact_selected_markdown_bytes(self):
        first = STORE.publish_revision(self.root, self.state_bytes())
        second_state = self.state(revision=2)
        second_state["report"]["previous_sha256"] = sha256(first.markdown_path)

        second = STORE.publish_revision(self.root, canonical_json(second_state))

        current = STORE.load_current(self.root, "RPT-001")
        self.assertEqual(current.revision, 2)
        self.assertEqual(current.markdown_path, second.markdown_path)
        self.assertTrue(first.markdown_path.exists())

    def test_wrong_predecessor_digest_cannot_publish_revision(self):
        first = STORE.publish_revision(self.root, self.state_bytes())
        second_state = self.state(revision=2)
        second_state["report"]["previous_sha256"] = "0" * 64

        with self.assertRaises(STORE.LineageError):
            STORE.publish_revision(self.root, canonical_json(second_state))

        self.assertEqual(STORE.load_current(self.root, "RPT-001").revision, 1)
        self.assertTrue(first.markdown_path.exists())

    def test_pointer_replace_failure_leaves_prior_revision_current(self):
        STORE.publish_revision(self.root, self.state_bytes())
        first_current = STORE.load_current(self.root, "RPT-001")
        second_state = self.state(revision=2)
        second_state["report"]["previous_sha256"] = first_current.markdown_sha256

        with mock.patch.object(STORE.os, "replace", side_effect=OSError("fault")):
            with self.assertRaises(STORE.ReportStoreUnavailable):
                STORE.publish_revision(self.root, canonical_json(second_state))

        self.assertEqual(STORE.load_current(self.root, "RPT-001").revision, 1)

    def test_store_rejects_traversal_and_external_symlink(self):
        for report_id in ("../escape", "/tmp/escape", "RPT-001/../../escape"):
            with self.subTest(report_id=report_id):
                with self.assertRaises(STORE.UnsafeReportPath):
                    STORE.report_directory(self.root, report_id)

        outside = self.root / "outside"
        outside.mkdir()
        (self.root / ".requirements-impact-refiner").symlink_to(
            outside, target_is_directory=True
        )
        with self.assertRaises(STORE.UnsafeReportPath):
            STORE.publish_revision(self.root, self.state_bytes())

    def test_cli_publishes_or_returns_explicit_full_inline_fallback(self):
        state_path = self.root / "state.json"
        state_path.write_bytes(self.state_bytes())
        success = subprocess.run(
            [sys.executable, str(CLI), "--repo-root", str(self.root), str(state_path)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual(json.loads(success.stdout)["status"], "published")

        blocked_root = self.root / "blocked"
        blocked_root.write_text("not a directory", encoding="utf-8")
        blocked = subprocess.run(
            [sys.executable, str(CLI), "--repo-root", str(blocked_root), str(state_path)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(blocked.returncode, 2)
        self.assertEqual(json.loads(blocked.stdout)["fallback"], "full-inline")


if __name__ == "__main__":
    unittest.main()
