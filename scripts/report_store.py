#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import compact_state
import impact_renderer

REPORT_ID_PATTERN = re.compile(r"RPT-\d{3}")
REPORT_ROOT = Path(".requirements-impact-refiner/reports")
POINTER_KEYS = {
    "schema_version",
    "report_id",
    "revision",
    "state",
    "markdown",
    "markdown_sha256",
}


class ReportStoreError(RuntimeError):
    pass


class ReportStoreUnavailable(ReportStoreError):
    pass


class UnsafeReportPath(ReportStoreError):
    pass


class LineageError(ReportStoreError):
    pass


@dataclass(frozen=True)
class CurrentRevision:
    report_id: str
    revision: int
    state_path: Path
    markdown_path: Path
    pointer_path: Path
    markdown_sha256: str


PublishedRevision = CurrentRevision


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _resolved_root(repo_root: Path) -> Path:
    try:
        root = Path(repo_root).resolve(strict=True)
    except OSError as error:
        raise ReportStoreUnavailable(f"repository root is unavailable: {error}") from error
    if not root.is_dir():
        raise ReportStoreUnavailable(f"repository root is not a directory: {root}")
    return root


def _ensure_directory(root: Path, path: Path, *, create: bool) -> Path:
    try:
        path.relative_to(root)
    except ValueError as error:
        raise UnsafeReportPath(f"report path escapes repository: {path}") from error
    current = root
    for component in path.relative_to(root).parts:
        current = current / component
        if current.is_symlink():
            raise UnsafeReportPath(f"report path uses a symlink: {current}")
        if current.exists():
            if not current.is_dir():
                raise ReportStoreUnavailable(f"report path component is not a directory: {current}")
        elif create:
            try:
                current.mkdir()
            except OSError as error:
                raise ReportStoreUnavailable(f"cannot create report directory: {error}") from error
        else:
            return current
    return current


def report_directory(repo_root: Path, report_id: str, *, create: bool = False) -> Path:
    if not isinstance(report_id, str) or REPORT_ID_PATTERN.fullmatch(report_id) is None:
        raise UnsafeReportPath(f"invalid report id: {report_id}")
    root = _resolved_root(repo_root)
    return _ensure_directory(root, root / REPORT_ROOT / report_id, create=create)


def _safe_artifact(report_dir: Path, relative: object, label: str) -> Path:
    if not isinstance(relative, str):
        raise UnsafeReportPath(f"pointer {label} path must be a string")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or len(candidate.parts) != 1:
        raise UnsafeReportPath(f"pointer {label} path is unsafe: {relative}")
    path = report_dir / candidate
    if path.is_symlink():
        raise UnsafeReportPath(f"pointer {label} path uses a symlink: {relative}")
    try:
        path.resolve(strict=True).relative_to(report_dir.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise UnsafeReportPath(f"pointer {label} path is unavailable: {relative}") from error
    if not path.is_file():
        raise ReportStoreUnavailable(f"pointer {label} is not a file: {relative}")
    return path


def load_current(repo_root: Path, report_id: str) -> CurrentRevision | None:
    report_dir = report_directory(repo_root, report_id, create=False)
    pointer_path = report_dir / "current.json"
    if not pointer_path.exists():
        return None
    if pointer_path.is_symlink():
        raise UnsafeReportPath("current pointer must not be a symlink")
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReportStoreUnavailable(f"cannot read current pointer: {error}") from error
    if not isinstance(pointer, dict) or set(pointer) != POINTER_KEYS:
        raise ReportStoreUnavailable("current pointer has an invalid schema")
    if pointer.get("schema_version") != 1 or pointer.get("report_id") != report_id:
        raise ReportStoreUnavailable("current pointer identity is invalid")
    revision = pointer.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ReportStoreUnavailable("current pointer revision is invalid")
    state_path = _safe_artifact(report_dir, pointer.get("state"), "state")
    markdown_path = _safe_artifact(report_dir, pointer.get("markdown"), "markdown")
    try:
        markdown_bytes = markdown_path.read_bytes()
    except OSError as error:
        raise ReportStoreUnavailable(f"cannot read selected Markdown: {error}") from error
    digest = _digest(markdown_bytes)
    if pointer.get("markdown_sha256") != digest:
        raise LineageError("current pointer Markdown SHA-256 does not match selected bytes")
    return CurrentRevision(
        report_id=report_id,
        revision=revision,
        state_path=state_path,
        markdown_path=markdown_path,
        pointer_path=pointer_path,
        markdown_sha256=digest,
    )


def _write_exclusive(path: Path, payload: bytes) -> None:
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=f".{path.name}-", delete=False
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_path, path)
    except FileExistsError:
        raise
    except OSError as error:
        raise ReportStoreUnavailable(f"cannot write artifact {path.name}: {error}") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _write_or_verify(path: Path, payload: bytes, *, resume_partial: bool) -> None:
    try:
        _write_exclusive(path, payload)
    except FileExistsError:
        if not resume_partial or path.is_symlink():
            raise
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise ReportStoreUnavailable(
                f"cannot verify existing artifact {path.name}: {error}"
            ) from error
        if existing != payload:
            raise FileExistsError(path) from None


def _replace_pointer(pointer_path: Path, payload: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=pointer_path.parent, prefix=".current-", delete=False
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, pointer_path)
    except OSError as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise ReportStoreUnavailable(f"cannot publish current pointer: {error}") from error


def publish_revision(
    repo_root: Path, state_bytes: bytes, *, resume_partial: bool = False
) -> PublishedRevision:
    state, state_errors = compact_state.load_state_bytes(state_bytes)
    if state_errors or state is None:
        raise ValueError("; ".join(state_errors))
    typed_state = cast(
        compact_state.State, state
    )  # compact_state.load_state_bytes validates the complete State shape.
    report = typed_state["report"]
    report_id = report["id"]
    revision = report["revision"]
    report_dir = report_directory(repo_root, report_id, create=True)
    pointer_path = report_dir / "current.json"
    state_path = report_dir / f"revision-{revision:04d}.json"
    markdown_path = report_dir / f"revision-{revision:04d}.md"
    current = load_current(repo_root, report_id)
    canonical_state = _canonical_json(state)
    markdown = impact_renderer.render_markdown(state)
    markdown_bytes = markdown.encode("utf-8")
    if current is not None and current.revision == revision:
        if not resume_partial:
            raise FileExistsError(state_path)
        try:
            if current.state_path.read_bytes() != canonical_state:
                raise FileExistsError(state_path)
            if current.markdown_path.read_bytes() != markdown_bytes:
                raise FileExistsError(markdown_path)
        except OSError as error:
            raise ReportStoreUnavailable(f"cannot verify published revision: {error}") from error
        return current
    if revision == 1:
        if current is not None:
            raise LineageError("revision 1 cannot replace an existing lineage")
    else:
        if current is None:
            raise LineageError("later revision requires a current predecessor")
        if revision != current.revision + 1:
            raise LineageError("revision must follow the current revision exactly")
        if report["previous_sha256"] != current.markdown_sha256:
            raise LineageError("previous_sha256 does not match selected predecessor bytes")
    previous_bytes = current.markdown_path.read_bytes() if current is not None else None
    markdown_errors = impact_renderer.validate_rendered_markdown(
        markdown, previous_bytes=previous_bytes
    )
    if markdown_errors:
        raise ValueError("; ".join(markdown_errors))
    _write_or_verify(state_path, canonical_state, resume_partial=resume_partial)
    _write_or_verify(markdown_path, markdown_bytes, resume_partial=resume_partial)
    digest = _digest(markdown_bytes)
    pointer = {
        "schema_version": 1,
        "report_id": report_id,
        "revision": revision,
        "state": state_path.name,
        "markdown": markdown_path.name,
        "markdown_sha256": digest,
    }
    _replace_pointer(pointer_path, _canonical_json(pointer))
    selected = load_current(repo_root, report_id)
    if selected is None or selected.revision != revision:
        raise ReportStoreUnavailable("published pointer could not be verified")
    return selected
