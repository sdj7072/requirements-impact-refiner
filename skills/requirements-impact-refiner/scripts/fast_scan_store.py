"""Private atomic persistence for Fast Scan receipts."""
import json, os, re, secrets, stat
from pathlib import Path
_ID = re.compile(r"^[0-9a-f]{32}$")
_MAX = 4 * 1024 * 1024

def _id(value):
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError("scan_id must be 32 lowercase hex characters")
    return value

def _open_dir(parent_fd, name, mode):
    created = True
    try: os.mkdir(name, mode=mode, dir_fd=parent_fd)
    except FileExistsError: created = False
    try:
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
    except OSError as error:
        raise ValueError("scan directory is unsafe") from error
    # Only stamp the mode on directories this store created; an existing
    # directory keeps whatever permissions the user chose.
    if created:
        os.fchmod(fd, mode)
    return fd


def _ensure_self_ignore(base_fd):
    """Keep receipt payloads (which may embed repository text) out of version
    control: the workspace must always ignore itself. A symlinked ignore file
    is refused, and an existing file without an ignore-all line gains one."""
    try:
        fd = os.open(
            ".gitignore",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode=0o644, dir_fd=base_fd,
        )
    except FileExistsError:
        try:
            fd = os.open(
                ".gitignore",
                os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=base_fd,
            )
        except OSError as error:
            raise ValueError("scan directory is unsafe") from error
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("scan directory is unsafe")
            with os.fdopen(fd, "r+", closefd=False, encoding="utf-8") as handle:
                content = handle.read()
                if "*" not in content.splitlines():
                    handle.seek(0, os.SEEK_END)
                    if content and not content.endswith("\n"):
                        handle.write("\n")
                    handle.write("*\n")
                    handle.flush()
                    os.fsync(fd)
        finally:
            os.close(fd)
        return
    try:
        os.write(fd, b"*\n")
        os.fsync(fd)
    finally:
        os.close(fd)

def _scan_dir(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("repository root is unsafe")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
    base_fd = None
    try:
        base_fd = _open_dir(root_fd, ".requirements-impact-refiner", 0o755)
        _ensure_self_ignore(base_fd)
        return _open_dir(base_fd, "scans", 0o700)
    finally:
        if base_fd is not None: os.close(base_fd)
        os.close(root_fd)

def publish_scan_receipt(root, scan_id, payload):
    scan_id = _id(scan_id)
    if not isinstance(payload, bytes) or not payload or len(payload) > _MAX:
        raise ValueError("scan receipt payload is invalid")
    directory_fd = _scan_dir(root)
    temporary = "." + scan_id + "." + secrets.token_hex(8) + ".tmp"
    fd = None
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd)
        offset = 0
        while offset < len(payload): offset += os.write(fd, payload[offset:])
        os.fsync(fd); os.close(fd); fd = None
        try:
            os.link(temporary, scan_id + ".json", src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
        except FileExistsError as error:
            raise ValueError("scan receipt already exists") from error
        os.fsync(directory_fd)
        os.unlink(temporary, dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        if fd is not None: os.close(fd)
        try: os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError: pass
        os.close(directory_fd)
    return Path(root).resolve() / ".requirements-impact-refiner" / "scans" / (scan_id + ".json")

def load_scan_receipt_bytes(root, scan_id):
    scan_id = _id(scan_id)
    directory_fd = _scan_dir(root)
    fd = None
    try:
        fd = os.open(scan_id + ".json", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX:
            raise ValueError("scan receipt is invalid")
        payload = b""
        while len(payload) < before.st_size:
            chunk = os.read(fd, before.st_size - len(payload))
            if not chunk: raise ValueError("scan receipt changed while reading")
            payload += chunk
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("scan receipt changed while reading")
        try: value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
            raise ValueError("scan receipt is invalid") from error
        if not isinstance(value, dict) or value.get("scan_id") != scan_id:
            raise ValueError("scan receipt is invalid")
        canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        if canonical != payload: raise ValueError("scan receipt is not canonical")
        return payload
    finally:
        if fd is not None: os.close(fd)
        os.close(directory_fd)
