from __future__ import annotations

import importlib.util
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PROCESS_PATH = ROOT / "scripts" / "rir_delta_process.py"


def load_module(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ImportError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


PROCESS = load_module("_test_rir_delta_process", PROCESS_PATH)


class DeltaProcessTest(unittest.TestCase):
    def test_terminate_worker_signals_process_group_and_reaps_process(self):
        process = mock.Mock(spec=subprocess.Popen)
        process.pid = 123
        process.poll.return_value = 0

        with mock.patch.object(PROCESS.os, "killpg") as killpg:
            self.assertTrue(PROCESS.terminate_worker(process))

        self.assertEqual(
            killpg.call_args_list,
            [mock.call(123, signal.SIGTERM), mock.call(123, signal.SIGKILL)],
        )
        self.assertEqual(process.wait.call_count, 2)

    def test_terminate_worker_fallback_normalizes_signal_and_wait_errors(self):
        process = mock.Mock(spec=subprocess.Popen)
        process.poll.side_effect = (None, None, 0)
        process.terminate.side_effect = OSError("terminate blocked")
        process.kill.side_effect = OSError("kill blocked")
        process.wait.side_effect = subprocess.TimeoutExpired("worker", 0.01)

        with mock.patch.object(PROCESS, "os", SimpleNamespace()):
            self.assertTrue(PROCESS.terminate_worker(process))

        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()
        self.assertEqual(process.wait.call_count, 2)

    def test_terminate_worker_normalizes_process_group_signal_errors(self):
        process = mock.Mock(spec=subprocess.Popen)
        process.pid = 456
        process.poll.return_value = 0

        with mock.patch.object(PROCESS.os, "killpg", side_effect=OSError("signal blocked")):
            self.assertTrue(PROCESS.terminate_worker(process))

        self.assertEqual(process.wait.call_count, 2)

    def test_cleanup_shared_temps_removes_only_matching_regular_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = "a" * 32
            scans = root / ".requirements-impact-refiner" / "scans"
            scans.mkdir(parents=True)
            matching = scans / f".{token}.receipt.tmp"
            foreign = scans / f".{'b' * 32}.receipt.tmp"
            matching.write_bytes(b"matching")
            foreign.write_bytes(b"foreign")

            complete = PROCESS.cleanup_shared_temps(
                root,
                token,
                deadline=time.monotonic() + 1,
            )

            self.assertTrue(complete)
            self.assertFalse(matching.exists())
            self.assertTrue(foreign.is_file())

    def test_cleanup_shared_temps_normalizes_directory_open_and_close_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def open_path(path, *_args, **_kwargs):
                if isinstance(path, Path):
                    return 10
                raise PermissionError("nested directory blocked")

            with (
                mock.patch.object(PROCESS.os, "open", side_effect=open_path),
                mock.patch.object(PROCESS.os, "close", side_effect=OSError("close blocked")),
            ):
                self.assertFalse(PROCESS.cleanup_shared_temps(root, "a" * 32))

    def test_cleanup_shared_temps_honors_entry_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scans = root / ".requirements-impact-refiner" / "scans"
            scans.mkdir(parents=True)
            (scans / "foreign.tmp").write_bytes(b"foreign")

            with mock.patch.object(PROCESS, "MAX_CLEANUP_ENTRIES", 0):
                self.assertFalse(PROCESS.cleanup_shared_temps(root, "a" * 32))

    def test_cleanup_private_directory_rejects_unrelated_input_path(self):
        with tempfile.TemporaryDirectory() as directory:
            worker_temp = Path(directory) / "worker"
            worker_temp.mkdir()

            self.assertFalse(
                PROCESS.cleanup_private_directory(
                    worker_temp,
                    worker_temp / "foreign.json",
                    time.monotonic() + 1,
                )
            )


if __name__ == "__main__":
    unittest.main()
