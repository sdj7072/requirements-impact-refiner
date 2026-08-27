"""Process termination and bounded cleanup for the private delta worker."""

from __future__ import annotations

import os
import signal
import stat
import subprocess
import time
from pathlib import Path

CLEANUP_GRACE_SECONDS = 0.1
CLEANUP_SCAN_SECONDS = 0.025
MAX_CLEANUP_ENTRIES = 4096
MAX_PRIVATE_TEMP_ENTRIES = 128


def terminate_worker(process: subprocess.Popen[bytes]) -> bool:
    if hasattr(os, "killpg"):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            pass
    elif process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.wait(timeout=CLEANUP_GRACE_SECONDS / 4)
    except (OSError, subprocess.TimeoutExpired):
        pass
    if hasattr(os, "killpg"):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
    elif process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=CLEANUP_GRACE_SECONDS / 2)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return process.poll() is not None


def cleanup_shared_temps(root: Path, token: str, deadline: float | None = None) -> bool:
    directories = (
        (".requirements-impact-refiner", "scans"),
        (".requirements-impact-refiner", "graph"),
        (".requirements-impact-refiner", "cache", "graph", "v1"),
    )
    marker = f".{token}."
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    complete = True
    for parts in directories:
        if deadline is not None and time.monotonic() >= deadline:
            return False
        opened = []
        try:
            parent = os.open(root, directory_flags)
            opened.append(parent)
            for part in parts:
                parent = os.open(part, directory_flags, dir_fd=parent)
                opened.append(parent)
        except (FileNotFoundError, NotADirectoryError):
            for descriptor in reversed(opened):
                os.close(descriptor)
            continue
        except OSError:
            complete = False
            for descriptor in reversed(opened):
                try:
                    os.close(descriptor)
                except OSError:
                    complete = False
            continue
        try:
            with os.scandir(parent) as entries:
                for index, entry in enumerate(entries, start=1):
                    if index > MAX_CLEANUP_ENTRIES:
                        complete = False
                        break
                    if deadline is not None and time.monotonic() >= deadline:
                        complete = False
                        break
                    if marker not in entry.name or not entry.name.endswith(".tmp"):
                        continue
                    try:
                        removable = not entry.is_symlink() and entry.is_file(follow_symlinks=False)
                    except OSError:
                        complete = False
                        continue
                    if not removable:
                        complete = False
                        continue
                    try:
                        os.unlink(entry.name, dir_fd=parent)
                    except OSError:
                        complete = False
        except OSError:
            complete = False
        finally:
            for descriptor in reversed(opened):
                try:
                    os.close(descriptor)
                except OSError:
                    complete = False
    return complete


def cleanup_private_directory(worker_temp: Path, input_path: Path, deadline: float) -> bool:
    if input_path.parent != worker_temp or input_path.name != "input.json":
        return False
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    parent_descriptor = -1
    directory_descriptor = -1
    complete = True
    removed = False
    try:
        parent_descriptor = os.open(worker_temp.parent, directory_flags)
        directory_descriptor = os.open(
            worker_temp.name,
            directory_flags,
            dir_fd=parent_descriptor,
        )
    except FileNotFoundError:
        for descriptor in (directory_descriptor, parent_descriptor):
            if descriptor >= 0:
                os.close(descriptor)
        return False
    except OSError:
        for descriptor in (directory_descriptor, parent_descriptor):
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        return False
    try:
        try:
            os.unlink(input_path.name, dir_fd=directory_descriptor)
        except FileNotFoundError:
            pass
        except OSError:
            complete = False
        if time.monotonic() >= deadline:
            complete = False
        else:
            try:
                with os.scandir(directory_descriptor) as entries:
                    for index, entry in enumerate(entries, start=1):
                        if index > MAX_PRIVATE_TEMP_ENTRIES:
                            complete = False
                            break
                        if time.monotonic() >= deadline:
                            complete = False
                            break
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                os.rmdir(entry.name, dir_fd=directory_descriptor)
                            else:
                                os.unlink(entry.name, dir_fd=directory_descriptor)
                        except OSError:
                            complete = False
            except OSError:
                complete = False
        try:
            opened = os.fstat(directory_descriptor)
            current = os.stat(
                worker_temp.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISDIR(current.st_mode)
                or opened.st_dev != current.st_dev
                or opened.st_ino != current.st_ino
            ):
                complete = False
            else:
                os.rmdir(worker_temp.name, dir_fd=parent_descriptor)
                removed = True
        except OSError:
            complete = False
    finally:
        for descriptor in (directory_descriptor, parent_descriptor):
            try:
                os.close(descriptor)
            except OSError:
                complete = False
    return complete and removed
