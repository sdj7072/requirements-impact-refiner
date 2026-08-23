#!/usr/bin/env python3
"""Detect-only ast-grep 0.45 adapter with bounded structural output."""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys


def _load_providers():
    name = "_rir_graph_providers"
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    path = Path(__file__).with_name("graph_providers.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load graph provider contracts")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PROVIDERS = _load_providers()
ProviderProbe = PROVIDERS.ProviderProbe
ProviderResult = PROVIDERS.ProviderResult
ProviderSpec = PROVIDERS.ProviderSpec

_VERSION = re.compile(r"(?im)^ast-grep\s+0\.45\.\d+(?:[-+][^\s]+)?\s*$")
_LANGUAGES = {
    ".py": "python", ".pyi": "python", ".js": "javascript",
    ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".go": "go",
    ".rs": "rust", ".swift": "swift", ".c": "c", ".h": "c",
    ".cc": "cpp", ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp",
}
_IGNORED = frozenset({
    ".git", ".hg", ".svn", ".requirements-impact-refiner", ".joern",
    "node_modules", "vendor", "build", "dist", "generated", "target",
    ".venv", "venv", "coverage", ".next",
})
_MAX_FILES = 500
_MAX_BYTES = 8_000_000
_MAX_FILE_BYTES = 1_048_576
_MAX_MATCHES = 512
_MAX_SEEDS = 16


def _safe_relative(value):
    if not isinstance(value, str) or not value or len(value) > 4096:
        return None
    if "\\" in value or "\x00" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or value in {".", ".."} or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.as_posix()


def _regular_bytes(root: Path, relative: str):
    safe = _safe_relative(relative)
    if safe is None:
        return None
    root_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(root), root_flags)
    except OSError:
        return None
    current = descriptor
    try:
        parts = PurePosixPath(safe).parts
        for part in parts[:-1]:
            next_descriptor = os.open(
                part, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current,
            )
            if current != descriptor:
                os.close(current)
            current = next_descriptor
        metadata = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_FILE_BYTES:
            return None
        file_descriptor = os.open(
            parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=current,
        )
        opened = os.fstat(file_descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
            metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns,
        ):
            os.close(file_descriptor)
            return None
        payload = bytearray()
        try:
            while len(payload) <= _MAX_FILE_BYTES:
                chunk = os.read(file_descriptor, min(64 * 1024, _MAX_FILE_BYTES + 1 - len(payload)))
                if not chunk:
                    break
                payload.extend(chunk)
        finally:
            os.close(file_descriptor)
        if len(payload) > _MAX_FILE_BYTES:
            return None
        return bytes(payload)
    except OSError:
        return None
    finally:
        if current != descriptor:
            os.close(current)
        os.close(descriptor)


def source_fingerprint(root) -> str | None:
    """Hash a bounded, symlink-free view of repository source files."""
    base = Path(root)
    if base.is_symlink() or not base.is_dir():
        return None
    base = base.resolve()
    rows = []
    count = 0
    total = 0
    try:
        for current, directories, files in os.walk(base, topdown=True, followlinks=False):
            directories[:] = sorted(
                name for name in directories
                if name not in _IGNORED and not (Path(current) / name).is_symlink()
            )
            for name in sorted(files):
                path = Path(current) / name
                relative = path.relative_to(base).as_posix()
                if relative == "index.scip" or path.is_symlink():
                    continue
                payload = _regular_bytes(base, relative)
                if payload is None:
                    return None
                count += 1
                total += len(payload)
                if count > _MAX_FILES or total > _MAX_BYTES:
                    return None
                rows.append((relative, hashlib.sha256(payload).hexdigest()))
    except OSError:
        return None
    canonical = "".join("%s\0%s\n" % row for row in rows).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _range(value):
    if not isinstance(value, dict) or set(value) != {"byteOffset", "start", "end"}:
        raise ValueError("ast-grep range shape is unsupported")
    byte_offset = value["byteOffset"]
    start, end = value["start"], value["end"]
    if not isinstance(byte_offset, dict) or set(byte_offset) != {"start", "end"}:
        raise ValueError("ast-grep byte range shape is unsupported")
    if not isinstance(start, dict) or set(start) != {"line", "column"}:
        raise ValueError("ast-grep start range shape is unsupported")
    if not isinstance(end, dict) or set(end) != {"line", "column"}:
        raise ValueError("ast-grep end range shape is unsupported")
    values = (byte_offset["start"], byte_offset["end"], start["line"], start["column"], end["line"], end["column"])
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in values):
        raise ValueError("ast-grep range values are invalid")
    if byte_offset["end"] < byte_offset["start"] or (end["line"], end["column"]) < (start["line"], start["column"]):
        raise ValueError("ast-grep range is reversed")
    return start["line"] + 1, start["column"] + 1, end["line"] + 1, end["column"] + 1


def _risk_domains(path, label=""):
    text = (path + " " + label).lower()
    domains = set()
    if any(word in text for word in ("auth", "permission", "privacy", "token", "role")):
        domains.add("authorization/privacy")
    if any(word in text for word in ("api", "schema", "dto", "interface")):
        domains.add("interfaces")
    if any(word in text for word in ("data", "database", "migration", "serialize")):
        domains.add("data")
    if any(word in text for word in ("cache", "state", "lock", "concurr")):
        domains.add("state/concurrency")
    if any(word in text for word in ("mobile", "desktop", "compat", "migration")):
        domains.add("compatibility")
    if any(word in text for word in ("event", "deploy", "config", "queue")):
        domains.add("operations")
    if any(word in text for word in ("test", "fixture", "migration")):
        domains.add("regression")
    return tuple(sorted(domains or {"functionality"}))


def _kind(path, label):
    text = (path + " " + label).lower()
    if "test" in text or "fixture" in text:
        return "test"
    if "cache" in text:
        return "cache"
    if "event" in text:
        return "event"
    if "api" in text or "dto" in text:
        return "api_field"
    return "symbol"


def _failure(name, status, confidence, detail, digests=()):
    return ProviderResult(name, status, confidence, raw_receipt_sha256=digests, detail=str(detail)[:512])


def probe(spec, root, deadline, runner) -> ProviderProbe:
    if not isinstance(spec, ProviderSpec) or spec.name != "ast-grep":
        raise TypeError("ast-grep probe requires its ProviderSpec")
    base = Path(root)
    resolved = base.resolve() if not base.is_symlink() and base.is_dir() else base.absolute()
    version = PROVIDERS.run_provider(spec, ("--version",), base, deadline, runner=runner)
    if version.status != "ready":
        return ProviderProbe("ast-grep", version.status, "structural-inferred", spec.executable, executable_sha256=version.executable_sha256, detail=version.detail, repo_root=resolved)
    line = next((item.strip() for item in version.stdout.splitlines() if item.strip()), "")
    if _VERSION.fullmatch(line) is None:
        return ProviderProbe("ast-grep", "unsupported", "structural-inferred", spec.executable, line[:256] or None, version.executable_sha256, detail="ast-grep 0.45.x is required", repo_root=resolved)
    help_result = PROVIDERS.run_provider(spec, ("--help",), base, deadline, runner=runner)
    if help_result.status != "ready":
        status = help_result.status if help_result.status in {"unsafe", "timed_out"} else "unsupported"
        return ProviderProbe("ast-grep", status, "structural-inferred", spec.executable, line, version.executable_sha256, detail=help_result.detail or "ast-grep help unavailable", repo_root=resolved)
    if help_result.executable_sha256 != version.executable_sha256:
        return ProviderProbe("ast-grep", "unsafe", "structural-inferred", spec.executable, line, version.executable_sha256, detail="provider executable changed between probes", repo_root=resolved)
    help_text = help_result.stdout
    stream_help = re.search(r"--json[^\n]{0,96}\bstream\b", help_text, re.IGNORECASE)
    if stream_help is None or not all(token in help_text for token in ("--lang", "--pattern")):
        return ProviderProbe("ast-grep", "unsupported", "structural-inferred", spec.executable, line, version.executable_sha256, detail="help does not confirm JSON stream, language, and pattern options", repo_root=resolved)
    fingerprint = source_fingerprint(resolved)
    if fingerprint is None:
        return ProviderProbe("ast-grep", "unsafe", "structural-inferred", spec.executable, line, version.executable_sha256, detail="repository source identity is unsafe or exceeds bounds", repo_root=resolved)
    return ProviderProbe(
        "ast-grep", "ready", "structural-inferred", spec.executable, line,
        version.executable_sha256, ("json-stream", "language", "pattern"),
        repo_root=resolved, metadata={"source_fingerprint": fingerprint},
    )


def query(probe, seeds, deadline, runner) -> ProviderResult:
    if not isinstance(probe, ProviderProbe) or probe.name != "ast-grep":
        raise TypeError("ast-grep query requires its ProviderProbe")
    if probe.status != "ready" or probe.executable is None or probe.repo_root is None:
        return _failure("ast-grep", probe.status, "structural-inferred", probe.detail or "provider is not ready")
    root = probe.repo_root.resolve()
    if source_fingerprint(root) != probe.metadata.get("source_fingerprint"):
        return _failure("ast-grep", "stale", "structural-inferred", "repository changed after ast-grep probe")
    spec = ProviderSpec("ast-grep", probe.executable)
    nodes = {}
    edges = {}
    digests = []
    for index, seed in enumerate(tuple(seeds)[:_MAX_SEEDS]):
        term = getattr(seed, "term", None)
        location = _safe_relative(getattr(seed, "location", None))
        if not isinstance(term, str) or not term or len(term) > 256 or location is None:
            continue
        language = _LANGUAGES.get(PurePosixPath(location).suffix.lower())
        source_bytes = _regular_bytes(root, location)
        if language is None or source_bytes is None:
            continue
        result = PROVIDERS.run_provider(
            spec, ("--json=stream", "--lang", language, "--pattern", term, "."),
            root, deadline, runner=runner,
        )
        if result.status != "ready":
            return _failure("ast-grep", result.status, "structural-inferred", result.detail or "ast-grep query failed", tuple(digests))
        digest = hashlib.sha256(result.stdout.encode("utf-8")).hexdigest()
        digests.append(digest)
        source_key = "seed:%d" % index
        nodes[source_key] = {
            "key": source_key, "kind": _kind(location, term), "label": term,
            "location": location, "confidence": "structural-inferred",
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "risk_domains": _risk_domains(location, term),
        }
        lines = result.stdout.splitlines()
        if len(lines) > _MAX_MATCHES:
            return _failure("ast-grep", "failed", "structural-inferred", "ast-grep match count exceeds bound", tuple(digests))
        for row_index, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                import json
                row = json.loads(line)
                required = {"text", "range", "file", "lines", "charCount", "language", "metaVariables"}
                if not isinstance(row, dict) or set(row) != required:
                    raise ValueError("ast-grep match shape is unsupported")
                path = _safe_relative(row["file"])
                if path is None or not isinstance(row["text"], str) or not row["text"] or len(row["text"]) > 4096:
                    raise ValueError("ast-grep match path or text is invalid")
                if not isinstance(row["lines"], str) or len(row["lines"]) > 4096:
                    raise ValueError("ast-grep source excerpt is invalid")
                if not isinstance(row["charCount"], dict) or set(row["charCount"]) != {"leading", "trailing"}:
                    raise ValueError("ast-grep character count shape is unsupported")
                if (
                    not isinstance(row["language"], str)
                    or row["language"].lower() != language
                    or not isinstance(row["metaVariables"], dict)
                ):
                    raise ValueError("ast-grep language or metavariables are invalid")
                start_line, start_col, end_line, end_col = _range(row["range"])
                target_bytes = _regular_bytes(root, path)
                if target_bytes is None or row["text"].encode("utf-8") not in target_bytes:
                    raise ValueError("ast-grep match is outside regular repository source")
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                return _failure("ast-grep", "failed", "structural-inferred", error, tuple(digests))
            target_key = "match:%d:%d" % (index, row_index)
            nodes[target_key] = {
                "key": target_key, "kind": _kind(path, row["text"]), "label": row["text"][:256],
                "location": path, "confidence": "structural-inferred",
                "source_sha256": hashlib.sha256(target_bytes).hexdigest(),
                "risk_domains": _risk_domains(path, row["text"]),
            }
            signature = (source_key, target_key, "references", path, start_line, start_col, end_line, end_col)
            edges[signature] = {
                "source": source_key, "target": target_key, "kind": "references",
                "location": path,
                "evidence": "ast-grep structural match at %d:%d-%d:%d" % (start_line, start_col, end_line, end_col),
                "confidence": "structural-inferred",
                "source_sha256": hashlib.sha256(target_bytes).hexdigest(),
            }
    if source_fingerprint(root) != probe.metadata.get("source_fingerprint"):
        return _failure("ast-grep", "stale", "structural-inferred", "repository changed during ast-grep query", tuple(digests))
    return ProviderResult(
        "ast-grep", "ready", "structural-inferred", tuple(nodes.values()),
        tuple(edges.values()), raw_receipt_sha256=tuple(digests),
        metadata={"queries": len(digests)},
    )


__all__ = ["probe", "query", "source_fingerprint"]
