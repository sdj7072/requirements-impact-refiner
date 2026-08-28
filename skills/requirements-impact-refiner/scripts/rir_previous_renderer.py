#!/usr/bin/env python3
"""Compact, renderer-owned presentation for a selected previous report."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Callable, Protocol, cast

KOREAN_TEXT = re.compile(r"[\u3131-\u318e\uac00-\ud7a3]")


class _CompactStateContract(Protocol):
    DELTA_CATEGORIES: Sequence[str]

    def validate_state(self, value: object) -> list[str]: ...

    def load_state_bytes(self, raw: bytes) -> tuple[dict[str, object] | None, list[str]]: ...


class _ImpactReportContract(Protocol):
    def parse_report(self, text: str): ...

    def validate_semantics(self, report): ...


class _ImpactRendererContract(Protocol):
    compact_state: _CompactStateContract
    impact_report: _ImpactReportContract
    VALIDATOR: object

    def render_compact(self, state: Mapping[str, object]) -> str: ...

    def render_markdown(self, state: Mapping[str, object]) -> str: ...

    def render_reader_view(self, state: Mapping[str, object], locale: str | None = None) -> str: ...

    def validate_rendered_markdown(
        self, text: str, previous_bytes: bytes | None = None
    ) -> list[str]: ...


class _PreviousResult(Protocol):
    status: str
    report_id: str | None
    revision: int | None
    created_at: str | None
    baseline_commit: str | None
    changed_count: int | None
    reason: str


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def _regular_module_path(path: Path) -> Path | None:
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        return None
    return resolved


def module_uses_sibling(value: object, filename: str) -> bool:
    module_file = getattr(value, "__file__", None)
    expected = SCRIPT_DIR / filename
    return (
        isinstance(module_file, str)
        and _regular_module_path(expected) == expected
        and _regular_module_path(Path(module_file)) == expected
    )


def _dependency_suffix(aliases: Mapping[str, ModuleType] | None) -> str:
    identity = tuple(
        (
            name,
            getattr(module, "__name__", ""),
            getattr(module, "__file__", ""),
            id(module),
        )
        for name, module in sorted((aliases or {}).items())
    )
    return hashlib.sha256(repr(identity).encode("utf-8")).hexdigest()[:16]


def load_local_module(
    filename: str,
    canonical_name: str,
    prefix: str,
    validator: Callable[[object], bool],
    label: str,
    aliases: Mapping[str, ModuleType] | None = None,
) -> object:
    """Load one regular sibling without trusting process-wide import aliases."""

    expected = _regular_module_path(SCRIPT_DIR / filename)
    if expected is None or expected != SCRIPT_DIR / filename:
        raise ImportError(f"previous renderer {label} sibling is unsafe")
    canonical = sys.modules.get(canonical_name)
    if module_uses_sibling(canonical, filename) and validator(canonical):
        return canonical
    base_name = prefix + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    module_name = base_name
    existing = sys.modules.get(module_name)
    if existing is not None:
        if not module_uses_sibling(existing, filename):
            raise ImportError(f"previous renderer {label} sibling is unsafe")
        if validator(existing):
            return existing
        if aliases is None:
            raise ImportError(f"previous renderer {label} sibling contract is incomplete")
        module_name = f"{base_name}_{_dependency_suffix(aliases)}"
        existing = sys.modules.get(module_name)
        if existing is not None:
            if not module_uses_sibling(existing, filename) or not validator(existing):
                raise ImportError(f"previous renderer {label} sibling contract is incomplete")
            return existing
    elif canonical is None:
        module_name = canonical_name
    specification = importlib.util.spec_from_file_location(module_name, expected)
    if specification is None or specification.loader is None:
        raise ImportError(f"cannot load fixed previous renderer {label} sibling")
    module = importlib.util.module_from_spec(specification)
    previous = {name: (name in sys.modules, sys.modules.get(name)) for name in (aliases or {})}
    sys.modules[module_name] = module
    try:
        if aliases:
            sys.modules.update(aliases)
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError(f"cannot load fixed previous renderer {label} sibling") from error
    finally:
        for name, (present, value) in previous.items():
            if present:
                sys.modules[name] = cast(ModuleType, value)
            else:
                sys.modules.pop(name, None)
    if not validator(module):
        sys.modules.pop(module_name, None)
        raise ImportError(f"previous renderer {label} sibling contract is incomplete")
    return module


def _compact_state_contract(value: object) -> bool:
    categories = getattr(value, "DELTA_CATEGORIES", None)
    return (
        module_uses_sibling(value, "compact_state.py")
        and isinstance(categories, Sequence)
        and not isinstance(categories, (str, bytes))
        and all(isinstance(item, str) for item in categories)
        and callable(getattr(value, "validate_state", None))
        and callable(getattr(value, "load_state_bytes", None))
    )


def _impact_report_contract(value: object) -> bool:
    return (
        module_uses_sibling(value, "impact_report.py")
        and callable(getattr(value, "parse_report", None))
        and callable(getattr(value, "validate_semantics", None))
    )


COMPACT_STATE = cast(
    _CompactStateContract,
    load_local_module(
        "compact_state.py",
        "compact_state",
        "_rir_previous_renderer_compact_state_",
        _compact_state_contract,
        "compact state",
    ),
)
IMPACT_REPORT = cast(
    _ImpactReportContract,
    load_local_module(
        "impact_report.py",
        "impact_report",
        "_rir_previous_renderer_impact_report_",
        _impact_report_contract,
        "impact report",
    ),
)


def _impact_renderer_contract(value: object) -> bool:
    return (
        module_uses_sibling(value, "impact_renderer.py")
        and getattr(value, "compact_state", None) is COMPACT_STATE
        and getattr(value, "impact_report", None) is IMPACT_REPORT
        and module_uses_sibling(getattr(value, "VALIDATOR", None), "validate-impact-report.py")
        and callable(getattr(value, "render_compact", None))
        and callable(getattr(value, "render_markdown", None))
        and callable(getattr(value, "render_reader_view", None))
        and callable(getattr(value, "validate_rendered_markdown", None))
    )


IMPACT_RENDERER = cast(
    _ImpactRendererContract,
    load_local_module(
        "impact_renderer.py",
        "impact_renderer",
        "_rir_previous_renderer_impact_renderer_",
        _impact_renderer_contract,
        "impact renderer",
        aliases={
            "compact_state": cast(ModuleType, COMPACT_STATE),
            "impact_report": cast(ModuleType, IMPACT_REPORT),
        },
    ),
)


def _header_text(value: str) -> str:
    return " ".join(value.replace("`", "").split())


def _request_locale(compact_state: Mapping[str, object]) -> str:
    original = compact_state.get("original_requirement")
    request = original.get("request") if isinstance(original, Mapping) else None
    return "ko" if isinstance(request, str) and KOREAN_TEXT.search(request) else "en"


def render_previous(result: _PreviousResult, compact_state: Mapping[str, object]) -> str:
    """Render a complete fresh report or stale report with freshness metadata."""

    if result.status in {"none", "ambiguous"}:
        return ""
    if result.status not in {"fresh", "stale"}:
        raise ValueError("previous result status is invalid")
    errors = COMPACT_STATE.validate_state(compact_state)
    if errors:
        raise ValueError("; ".join(errors))
    report = compact_state.get("report")
    if not isinstance(report, Mapping):
        raise ValueError("previous compact state report is unavailable")
    if report.get("id") != result.report_id or report.get("revision") != result.revision:
        raise ValueError("previous compact state identity does not match the result")
    if result.report_id is None or result.revision is None:
        raise ValueError("selected previous result identity is unavailable")
    if result.status == "fresh":
        return IMPACT_RENDERER.render_reader_view(compact_state)
    created = result.created_at or "unavailable"
    commit = f"`{result.baseline_commit}`" if result.baseline_commit else "unavailable"
    changed = str(result.changed_count) if result.changed_count is not None else "unavailable"
    reason = _header_text(result.reason)
    if _request_locale(compact_state) == "ko":
        header = (
            "## 이전 영향 보고서\n\n"
            f"- 최신 상태: {result.status}\n"
            f"- 보고서: `{result.report_id}` 개정 {result.revision}\n"
            f"- 생성 시각: {created}\n"
            f"- 커밋: {commit}\n"
            f"- 변경 파일 수: {changed}\n"
            f"- 사유: {reason}\n"
        )
    else:
        header = (
            "## Previous Impact Report\n\n"
            f"- **Freshness:** {result.status}\n"
            f"- **Report:** `{result.report_id}` revision {result.revision}\n"
            f"- **Created:** {created}\n"
            f"- **Commit:** {commit}\n"
            f"- **Changed files:** {changed}\n"
            f"- **Reason:** {reason}\n"
        )
    return header + "\n" + IMPACT_RENDERER.render_reader_view(compact_state)
