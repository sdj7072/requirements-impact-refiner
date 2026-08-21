"""Immutable raw-evidence recording, screening, and checksum verification."""

import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Mapping, Union


Artifact = Union[str, bytes]

_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_SECRET_PATTERNS = (
    (
        "github-token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    ),
    (
        "openai-token",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "anthropic-token",
        re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "private-key",
        re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
    ),
    (
        "credential-assignment",
        re.compile(
            r"\b(?:api[_-]?key|token|secret|password|credential)\b\s*[:=]\s*"
            r"(?:[\"'][^\"'\r\n]{16,}[\"']|[A-Za-z0-9_./+=-]{16,})",
            re.IGNORECASE,
        ),
    ),
)


class PotentialSecretError(RuntimeError):
    """Raised after suspicious raw evidence has been preserved in quarantine."""

    def __init__(self, findings: tuple[str, ...], quarantine_path: Path) -> None:
        self.findings = findings
        self.quarantine_path = quarantine_path
        super().__init__("potential secret exposure quarantined")


def find_potential_secrets(text: str) -> tuple[str, ...]:
    """Return stable labels for concrete credential-shaped values in *text*."""
    return tuple(label for label, pattern in _SECRET_PATTERNS if pattern.search(text))


def _component(value: object, field: str) -> str:
    component = str(value)
    if not _COMPONENT.fullmatch(component):
        raise ValueError(f"{field} must be a single safe path component")
    return component


def _repetition_component(repetition: object) -> str:
    if isinstance(repetition, bool):
        raise ValueError("repetition must be a positive integer or safe component")
    if isinstance(repetition, int):
        if repetition < 1:
            raise ValueError("repetition must be positive")
        return f"{repetition:02d}"
    return _component(repetition, "repetition")


def _artifact_bytes(artifacts: Mapping[str, Artifact]) -> tuple[tuple[str, bytes], ...]:
    if not artifacts:
        raise ValueError("artifacts must not be empty")

    prepared = []
    for name, content in artifacts.items():
        relative = Path(name)
        if (
            not name
            or relative.is_absolute()
            or any(part in ("", ".", "..") for part in relative.parts)
            or any(any(character.isspace() for character in part) for part in relative.parts)
            or "\\" in name
        ):
            raise ValueError("artifact names must be safe relative paths")
        if isinstance(content, str):
            payload = content.encode("utf-8")
        elif isinstance(content, bytes):
            payload = content
        else:
            raise TypeError("artifact content must be str or bytes")
        prepared.append((relative.as_posix(), payload))
    return tuple(prepared)


def _attempt_component(attempt: object) -> str:
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError("attempt must be a positive integer")
    return "attempt-%02d" % attempt


def _run_directory(
    root: Path, client: object, case_id: object, repetition: object, attempt: object = 1
) -> Path:
    directory = (
        root
        / _component(client, "client")
        / _component(case_id, "case_id")
        / _repetition_component(repetition)
    )
    return directory if attempt == 1 else directory / _attempt_component(attempt)


def _repository_root(path: Path):
    for candidate in (path,) + tuple(path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _write_atomically(target: Path, artifacts: tuple[tuple[str, bytes], ...]) -> Path:
    """Publish staging bytes under a recorder-to-recorder exclusive claim.

    The portable ``O_EXCL`` claim coordinates callers of this recorder. It
    cannot prevent unrelated filesystem writers that ignore the claim.
    """
    if target.exists():
        raise FileExistsError(f"evidence already exists: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    claim = target.parent / f".{target.name}.lock"
    try:
        claim_descriptor = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise FileExistsError(f"evidence recording already in progress: {target}") from error

    temporary = None
    try:
        if target.exists():
            raise FileExistsError(f"evidence already exists: {target}")
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=target.parent)
        )
        for name, payload in artifacts:
            destination = temporary / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        if target.exists():
            raise FileExistsError(f"evidence already exists: {target}")
        os.replace(temporary, target)
    except BaseException:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
        raise
    finally:
        os.close(claim_descriptor)
        try:
            claim.unlink()
        except FileNotFoundError:
            pass
    return target


def record_run(
    raw_root: Path,
    client: str,
    case_id: str,
    repetition: object,
    artifacts: Mapping[str, Artifact],
    quarantine_root: Path,
    attempt: int = 1,
) -> Path:
    """Atomically persist one run, or quarantine its original bytes on suspicion.

    ``quarantine_root`` must be supplied by the caller outside the repository.
    It is rejected if it is nested in ``raw_root`` so suspicious content cannot
    accidentally become raw evaluation evidence.
    """
    prepared = _artifact_bytes(artifacts)
    raw_root = Path(raw_root)
    quarantine_root = Path(quarantine_root)
    raw_resolved = raw_root.resolve()
    quarantine_resolved = quarantine_root.resolve()
    if quarantine_resolved == raw_resolved or raw_resolved in quarantine_resolved.parents:
        raise ValueError("quarantine_root must be outside raw_root")
    repository_root = _repository_root(raw_resolved)
    if repository_root is not None and _is_within(quarantine_resolved, repository_root):
        raise ValueError("quarantine_root must be outside repository")

    findings = tuple(
        sorted(
            {
                finding
                for _, payload in prepared
                for finding in find_potential_secrets(
                    payload.decode("utf-8", errors="replace")
                )
            }
        )
    )
    if findings:
        quarantine_path = _write_atomically(
            _run_directory(quarantine_root, client, case_id, repetition, attempt), prepared
        )
        raise PotentialSecretError(findings, quarantine_path)

    return _write_atomically(
        _run_directory(raw_root, client, case_id, repetition, attempt), prepared
    )


def record_probe(
    raw_root: Path,
    client: str,
    probe_id: str,
    artifacts: Mapping[str, Artifact],
    quarantine_root: Path,
) -> Path:
    """Atomically record one named structural probe without a run/repetition path."""
    prepared = _artifact_bytes(artifacts)
    raw_root = Path(raw_root)
    quarantine_root = Path(quarantine_root)
    raw_resolved = raw_root.resolve()
    quarantine_resolved = quarantine_root.resolve()
    if quarantine_resolved == raw_resolved or raw_resolved in quarantine_resolved.parents:
        raise ValueError("quarantine_root must be outside raw_root")
    repository_root = _repository_root(raw_resolved)
    if repository_root is not None and _is_within(quarantine_resolved, repository_root):
        raise ValueError("quarantine_root must be outside repository")

    target = raw_root / _component(client, "client") / _component(probe_id, "probe_id")
    findings = tuple(
        sorted(
            {
                finding
                for _, payload in prepared
                for finding in find_potential_secrets(
                    payload.decode("utf-8", errors="replace")
                )
            }
        )
    )
    if findings:
        quarantine_path = _write_atomically(
            quarantine_root / _component(client, "client") / _component(probe_id, "probe_id"),
            prepared,
        )
        raise PotentialSecretError(findings, quarantine_path)
    return _write_atomically(target, prepared)


def _evidence_files(raw_root: Path):
    if not raw_root.exists():
        return ()
    files = []
    for path in raw_root.rglob("*"):
        if path == raw_root / "manifest.sha256":
            continue
        if path.is_symlink():
            raise ValueError(f"symlinked evidence is not allowed: {path}")
        if path.is_file():
            files.append(path)
    return tuple(sorted(files, key=lambda path: path.relative_to(raw_root).as_posix()))


def build_manifest(raw_root: Path) -> str:
    """Build a sorted lower-case SHA-256 inventory for all raw evidence files."""
    root = Path(raw_root)
    rows = []
    for path in _evidence_files(root):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{path.relative_to(root).as_posix()} {digest}")
    return "\n".join(rows) + "\n"


def _parse_manifest(manifest: str) -> tuple[dict[str, str], list[str]]:
    rows: dict[str, str] = {}
    problems = []
    for line in manifest.splitlines():
        try:
            relative, digest = line.split(" ")
        except ValueError:
            problems.append(f"invalid manifest row: {line}")
            continue
        if (
            not relative
            or Path(relative).is_absolute()
            or "\\" in relative
            or any(part in ("", ".", "..") for part in Path(relative).parts)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            problems.append(f"invalid manifest row: {line}")
        elif relative in rows:
            problems.append(f"duplicate manifest path: {relative}")
        else:
            rows[relative] = digest
    return rows, problems


def verify_manifest(raw_root: Path, manifest: str) -> list[str]:
    """Return deterministic integrity failures for a manifest and raw tree."""
    expected, problems = _parse_manifest(manifest)
    actual = {}
    root = Path(raw_root)
    for path in _evidence_files(root):
        relative = path.relative_to(root).as_posix()
        actual[relative] = hashlib.sha256(path.read_bytes()).hexdigest()

    for relative in sorted(expected):
        if relative not in actual:
            problems.append(f"missing: {relative}")
        elif actual[relative] != expected[relative]:
            problems.append(f"checksum mismatch: {relative}")
    for relative in sorted(set(actual) - set(expected)):
        problems.append(f"unexpected: {relative}")
    return problems
