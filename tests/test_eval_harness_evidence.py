import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from evals.harness import evidence
from evals.harness.evidence import (
    PotentialSecretError,
    build_manifest,
    find_potential_secrets,
    record_run,
    verify_manifest,
)
from evals.harness.process import run_command


ROOT = Path(__file__).resolve().parents[1]


class EvalHarnessEvidenceTest(unittest.TestCase):
    def test_timeout_is_preserved(self):
        """Removing the timeout handler would lose the timed-out result."""
        result = run_command(
            [sys.executable, "-c", "import time; time.sleep(2)"], ROOT, 0.01
        )

        self.assertTrue(result.timed_out)
        self.assertIsNone(result.returncode)

    def test_secret_detector_requires_concrete_value(self):
        """A detector that flags generic prose would block safe evidence."""
        self.assertEqual(find_potential_secrets("API key is required"), ())
        self.assertIn(
            "github-token",
            find_potential_secrets("token=gho_abcdefghijklmnopqrstuvwxyz123456"),
        )

    def test_one_byte_change_breaks_manifest(self):
        """Ignoring file contents would permit tampered raw evidence."""
        with tempfile.TemporaryDirectory() as temporary:
            raw_root = Path(temporary) / "raw"
            target = raw_root / "codex" / "POS-authorization" / "01" / "final.md"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"original evidence")

            manifest = build_manifest(raw_root)
            target.write_bytes(target.read_bytes() + b"x")

            self.assertEqual(
                verify_manifest(raw_root, manifest),
                ["checksum mismatch: codex/POS-authorization/01/final.md"],
            )

    def test_record_run_creates_an_immutable_atomic_artifact_directory(self):
        """Replacing an existing run would destroy preserved evidence."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw_root = root / "raw"
            quarantine_root = root / "quarantine"
            artifacts = {
                "prompt.txt": "Inspect the authorization rule.",
                "final.md": b"The rule is present.\n",
            }

            recorded = record_run(
                raw_root, "codex", "POS-authorization", 1, artifacts, quarantine_root
            )

            self.assertEqual(recorded, raw_root / "codex" / "POS-authorization" / "01")
            self.assertEqual(
                (recorded / "prompt.txt").read_text(encoding="utf-8"),
                "Inspect the authorization rule.",
            )
            with self.assertRaises(FileExistsError):
                record_run(
                    raw_root, "codex", "POS-authorization", 1, artifacts, quarantine_root
                )
            self.assertEqual((recorded / "final.md").read_bytes(), b"The rule is present.\n")

    def test_suspicious_artifacts_are_quarantined_without_repository_write(self):
        """Redacting or recording detected credentials would corrupt raw evidence."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw_root = root / "raw"
            quarantine_root = root / "quarantine"
            artifacts = {"stdout.txt": "Authorization: Bearer sk-proj-abcdefghijklmnopqrstuv"}

            with self.assertRaises(PotentialSecretError) as raised:
                record_run(
                    raw_root, "codex", "POS-authorization", 1, artifacts, quarantine_root
                )

            self.assertEqual(raised.exception.findings, ("openai-token",))
            self.assertFalse(raw_root.exists())
            self.assertEqual(
                (raised.exception.quarantine_path / "stdout.txt").read_text(encoding="utf-8"),
                "Authorization: Bearer sk-proj-abcdefghijklmnopqrstuv",
            )

    def test_quarantine_must_be_outside_a_detected_repository(self):
        """A quarantine directory within the repository could commit a credential."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()

            with self.assertRaisesRegex(ValueError, "outside repository"):
                record_run(
                    root / "evals" / "results" / "raw",
                    "codex",
                    "POS-authorization",
                    1,
                    {"stdout.txt": "token=gho_abcdefghijklmnopqrstuvwxyz123456"},
                    root / "quarantine",
                )

    def test_manifest_excludes_its_own_file_and_has_deterministic_order(self):
        """Including its own digest makes a manifest impossible to seal."""
        with tempfile.TemporaryDirectory() as temporary:
            raw_root = Path(temporary) / "raw"
            (raw_root / "z.txt").parent.mkdir(parents=True)
            (raw_root / "z.txt").write_bytes(b"z")
            (raw_root / "a.txt").write_bytes(b"a")
            (raw_root / "manifest.sha256").write_text("stale\n", encoding="utf-8")

            manifest = build_manifest(raw_root)

            self.assertEqual([row.split(" ", 1)[0] for row in manifest.splitlines()], ["a.txt", "z.txt"])
            self.assertTrue(manifest.endswith("\n"))
            self.assertEqual(verify_manifest(raw_root, manifest), [])

    def test_manifest_excludes_only_the_root_manifest_file(self):
        """Skipping a nested artifact named manifest would lose raw evidence."""
        with tempfile.TemporaryDirectory() as temporary:
            raw_root = Path(temporary) / "raw"
            (raw_root / "manifest.sha256").parent.mkdir(parents=True)
            (raw_root / "manifest.sha256").write_text("stale\n", encoding="utf-8")
            nested_manifest = raw_root / "codex" / "manifest.sha256"
            nested_manifest.parent.mkdir()
            nested_manifest.write_bytes(b"raw artifact")

            manifest = build_manifest(raw_root)

            self.assertEqual(
                [row.split(" ", 1)[0] for row in manifest.splitlines()],
                ["codex/manifest.sha256"],
            )

    def test_manifest_verification_requires_the_exact_canonical_serialization(self):
        """Equivalent rows with reordered or anomalous newlines are not the seal bytes."""
        with tempfile.TemporaryDirectory() as temporary:
            raw_root = Path(temporary) / "raw"
            raw_root.mkdir()
            (raw_root / "a.txt").write_bytes(b"a")
            (raw_root / "z.txt").write_bytes(b"z")
            canonical = build_manifest(raw_root)
            rows = canonical.splitlines()
            mutations = (
                "\n".join(reversed(rows)) + "\n",
                canonical[:-1],
                canonical + "\n",
                canonical.replace("\n", "\r\n"),
            )

            for manifest in mutations:
                with self.subTest(manifest=repr(manifest)):
                    self.assertIn(
                        "manifest is not the canonical sorted POSIX representation",
                        verify_manifest(raw_root, manifest),
                    )

    def test_noncanonical_manifest_still_reports_checksum_and_inventory_errors(self):
        """Formatting rejection must not hide which evidence rows are also wrong."""
        with tempfile.TemporaryDirectory() as temporary:
            raw_root = Path(temporary) / "raw"
            raw_root.mkdir()
            (raw_root / "a.txt").write_bytes(b"a")
            wrong = "missing.txt %s" % ("0" * 64)

            self.assertEqual(
                verify_manifest(raw_root, wrong),
                [
                    "manifest is not the canonical sorted POSIX representation",
                    "missing: missing.txt",
                    "unexpected: a.txt",
                ],
            )

    def test_concurrent_recorders_claim_one_run_before_publication(self):
        """Two recorders reaching publication together must not overwrite a run."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw_root = root / "raw"
            quarantine_root = root / "quarantine"
            start = threading.Barrier(2)
            replace_barrier = threading.Barrier(2)
            outcomes = []
            outcomes_lock = threading.Lock()
            original_replace = evidence.os.replace

            def synchronized_replace(source, destination):
                try:
                    replace_barrier.wait(timeout=0.2)
                except threading.BrokenBarrierError:
                    pass
                return original_replace(source, destination)

            def recorder(payload):
                start.wait(timeout=1)
                try:
                    result = record_run(
                        raw_root,
                        "codex",
                        "POS-authorization",
                        1,
                        {"final.md": payload},
                        quarantine_root,
                    )
                except Exception as error:
                    result = error
                with outcomes_lock:
                    outcomes.append(result)

            with patch("evals.harness.evidence.os.replace", synchronized_replace):
                first = threading.Thread(target=recorder, args=(b"first",))
                second = threading.Thread(target=recorder, args=(b"second",))
                first.start()
                second.start()
                first.join(timeout=2)
                second.join(timeout=2)

            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(sum(isinstance(item, Path) for item in outcomes), 1)
            self.assertEqual(sum(isinstance(item, FileExistsError) for item in outcomes), 1)
            self.assertIn(
                (raw_root / "codex" / "POS-authorization" / "01" / "final.md").read_bytes(),
                (b"first", b"second"),
            )
            self.assertEqual(
                list((raw_root / "codex" / "POS-authorization").glob(".01.*")), []
            )

    def test_record_run_rejects_whitespace_in_any_artifact_path_component(self):
        """Whitespace in a path would make the space-delimited manifest invalid."""
        unsafe_names = (
            "final evidence.md",
            "final\tevidence.md",
            "final\nevidence.md",
            "nested/final evidence.md",
            "nested/final\tevidence.md",
            "nested/final\nevidence.md",
        )

        for name in unsafe_names:
            with self.subTest(name=repr(name)), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                raw_root = root / "raw"
                with self.assertRaisesRegex(ValueError, "artifact names"):
                    record_run(
                        raw_root,
                        "codex",
                        "POS-authorization",
                        1,
                        {name: b"safe contents"},
                        root / "quarantine",
                    )
                self.assertFalse(raw_root.exists())

    def test_record_run_allows_nested_posix_artifact_paths(self):
        """Rejecting all nested paths would prevent the documented raw layout."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recorded = record_run(
                root / "raw",
                "codex",
                "POS-authorization",
                1,
                {"events/turn-01.jsonl": b"{}\n"},
                root / "quarantine",
            )

            self.assertEqual((recorded / "events" / "turn-01.jsonl").read_bytes(), b"{}\n")


if __name__ == "__main__":
    unittest.main()
