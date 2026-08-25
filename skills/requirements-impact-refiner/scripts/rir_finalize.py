#!/usr/bin/env python3
"""Final refinement validation, publication, verification, and consumption."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable, Protocol, cast

if TYPE_CHECKING:
    from rir_contracts import FinalizeRequest, FinalizeResult
    from typing_extensions import TypeGuard


class _ContractsContract(Protocol):
    MAX_FINALIZE_BYTES: int
    BeginRequest: type
    FinalizeRequest: type
    FinalizeResult: type

    def bounded_bytes(self, value: object, maximum: int, label: str) -> bytes: ...

    def canonical_bytes(self, value: object) -> bytes: ...

    def validate_analysis(self, analysis: Mapping[str, object]) -> None: ...


class _StorageContract(Protocol):
    DRAFT_ID_PATTERN: re.Pattern[str]
    report_store: object

    def root_path(self, path: Path) -> Path: ...

    def load_private_draft(self, repo_root: Path, draft_id: str) -> dict[str, object]: ...

    def draft_path(self, root: Path, draft_id: str) -> Path: ...

    def report_lock(self, root: Path, report_id: str, deadline: object = None): ...

    def write_controller_metadata(
        self,
        root: Path,
        draft: Mapping[str, object],
        state_bytes: bytes,
        key_map: Mapping[str, object],
        graph_receipt: Mapping[str, object] | None = None,
    ) -> None: ...

    def consume_draft(self, path: Path, draft: dict[str, object], published, key_map) -> None: ...


class _LineageContract(Protocol):
    CONTRACTS: _ContractsContract
    STORAGE: _StorageContract
    COMPACT_STATE: object
    IMPACT_RENDERER: object
    REPORT_STORE: object

    def build_state(self, draft, analysis, graph_context=None): ...


class _GraphContract(Protocol):
    def validate_receipt(self, value: object) -> tuple[str, ...]: ...

    def canonical_receipt_bytes(self, value: object) -> bytes: ...


class _GraphDeliveryContract(Protocol):
    CONTRACTS: _ContractsContract
    STORAGE: _StorageContract
    GRAPH: _GraphContract
    GRAPH_COORDINATOR: object

    def load_graph_context(
        self,
        root: Path,
        draft: Mapping[str, object],
        selected_receipt_id: str | None,
        *,
        deadline=None,
        _runtime=None,
    ): ...

    def validate_graph_coverage(self, analysis: Mapping[str, object], context) -> None: ...

    def verify_receipt_sources(self, root: Path, receipt: Mapping[str, object]) -> None: ...


class _FastScanContract(Protocol):
    FastScanRequest: type

    def prepare_fast_scan_identity(self, request, graph_settings, payload_sha256): ...

    def validate_fast_scan_receipt(self, value: object) -> tuple[str, ...]: ...

    def canonical_fast_scan_bytes(self, value: Mapping[str, object]) -> bytes: ...


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


def _module_uses_sibling(value: object, expected: Path) -> bool:
    module_file = getattr(value, "__file__", None)
    return isinstance(module_file, str) and _regular_module_path(Path(module_file)) == expected


def _callables(value: object, names: Sequence[str]) -> bool:
    return all(callable(getattr(value, name, None)) for name in names)


def _is_lineage_contract(value: object) -> TypeGuard[_LineageContract]:
    contracts = getattr(value, "CONTRACTS", None)
    storage = getattr(value, "STORAGE", None)
    compact_state = getattr(value, "COMPACT_STATE", None)
    renderer = getattr(value, "IMPACT_RENDERER", None)
    report_store = getattr(value, "REPORT_STORE", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "rir_lineage.py")
        and _module_uses_sibling(contracts, SCRIPT_DIR / "rir_contracts.py")
        and type(getattr(contracts, "MAX_FINALIZE_BYTES", None)) is int
        and isinstance(getattr(contracts, "FinalizeResult", None), type)
        and _callables(contracts, ("bounded_bytes", "canonical_bytes", "validate_analysis"))
        and _module_uses_sibling(storage, SCRIPT_DIR / "rir_storage.py")
        and isinstance(getattr(storage, "DRAFT_ID_PATTERN", None), re.Pattern)
        and _callables(
            storage,
            (
                "root_path",
                "load_private_draft",
                "draft_path",
                "report_lock",
                "write_controller_metadata",
                "consume_draft",
            ),
        )
        and _module_uses_sibling(compact_state, SCRIPT_DIR / "compact_state.py")
        and _module_uses_sibling(renderer, SCRIPT_DIR / "impact_renderer.py")
        and _module_uses_sibling(report_store, SCRIPT_DIR / "report_store.py")
        and getattr(storage, "report_store", None) is report_store
        and getattr(report_store, "compact_state", None) is compact_state
        and getattr(report_store, "impact_renderer", None) is renderer
        and callable(getattr(value, "build_state", None))
    )


def _execute_registered(
    module_name: str,
    expected: Path,
    validator: Callable[[object], bool],
    label: str,
    aliases: Mapping[str, ModuleType] | None = None,
) -> object:
    specification = importlib.util.spec_from_file_location(module_name, expected)
    if specification is None or specification.loader is None:
        raise ImportError(f"cannot load fixed finalize {label} sibling")
    module = importlib.util.module_from_spec(specification)
    previous = {name: (name in sys.modules, sys.modules.get(name)) for name in (aliases or {})}
    sys.modules[module_name] = module
    try:
        if aliases:
            sys.modules.update(aliases)
        specification.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ImportError(f"cannot load fixed finalize {label} sibling") from error
    finally:
        for name, (present, value) in previous.items():
            if name == module_name:
                continue
            if present:
                sys.modules[name] = cast(ModuleType, value)
            else:
                sys.modules.pop(name, None)
    if not validator(module):
        sys.modules.pop(module_name, None)
        raise ImportError(f"finalize {label} sibling contract is incomplete")
    return module


def _load_fixed_sibling(
    filename: str,
    canonical_name: str,
    prefix: str,
    validator: Callable[[object], bool],
    label: str,
    aliases: Mapping[str, ModuleType] | None = None,
) -> object:
    sibling = SCRIPT_DIR / filename
    expected = _regular_module_path(sibling)
    if expected is None or expected != sibling:
        raise ImportError(f"finalize {label} sibling is unsafe")
    hashed_name = prefix + hashlib.sha256(str(expected).encode("utf-8")).hexdigest()[:16]
    hashed_present = hashed_name in sys.modules
    hashed = sys.modules.get(hashed_name)
    if canonical_name not in sys.modules:
        if hashed_present:
            if not _module_uses_sibling(hashed, expected):
                raise ImportError(f"finalize {label} sibling is unsafe")
            if not validator(hashed):
                raise ImportError(f"finalize {label} sibling contract is incomplete")
            sys.modules[canonical_name] = cast(ModuleType, hashed)
            return hashed
        return _execute_registered(canonical_name, expected, validator, label, aliases=aliases)
    canonical = sys.modules.get(canonical_name)
    if _module_uses_sibling(canonical, expected):
        if validator(canonical) and not hashed_present:
            return canonical
        if hashed_present:
            if not _module_uses_sibling(hashed, expected):
                raise ImportError(f"finalize {label} sibling is unsafe")
            if not validator(hashed):
                raise ImportError(f"finalize {label} sibling contract is incomplete")
            return hashed
        if aliases is not None:
            return _execute_registered(hashed_name, expected, validator, label, aliases=aliases)
        raise ImportError(f"finalize {label} sibling contract is incomplete")
    if hashed_present:
        if not _module_uses_sibling(hashed, expected):
            raise ImportError(f"finalize {label} sibling is unsafe")
        if not validator(hashed):
            raise ImportError(f"finalize {label} sibling contract is incomplete")
        return hashed
    return _execute_registered(hashed_name, expected, validator, label, aliases=aliases)


LINEAGE = cast(
    _LineageContract,
    _load_fixed_sibling(
        "rir_lineage.py",
        "rir_lineage",
        "_rir_finalize_lineage_",
        _is_lineage_contract,
        "lineage",
    ),
)
CONTRACTS = LINEAGE.CONTRACTS
STORAGE = LINEAGE.STORAGE
COMPACT_STATE = cast(Any, LINEAGE.COMPACT_STATE)
IMPACT_RENDERER = cast(Any, LINEAGE.IMPACT_RENDERER)
REPORT_STORE = cast(Any, LINEAGE.REPORT_STORE)


def _is_graph_delivery_contract(value: object) -> TypeGuard[_GraphDeliveryContract]:
    coordinator = getattr(value, "GRAPH_COORDINATOR", None)
    graph = getattr(value, "GRAPH", None)
    return (
        _module_uses_sibling(value, SCRIPT_DIR / "rir_graph_delivery.py")
        and getattr(value, "CONTRACTS", None) is CONTRACTS
        and getattr(value, "STORAGE", None) is STORAGE
        and _module_uses_sibling(graph, SCRIPT_DIR / "impact_graph.py")
        and _module_uses_sibling(coordinator, SCRIPT_DIR / "graph_coordinator.py")
        and getattr(coordinator, "GRAPH", None) is graph
        and _callables(
            value,
            ("load_graph_context", "validate_graph_coverage", "verify_receipt_sources"),
        )
    )


GRAPH_DELIVERY = cast(
    _GraphDeliveryContract,
    _load_fixed_sibling(
        "rir_graph_delivery.py",
        "rir_graph_delivery",
        "_rir_finalize_graph_delivery_",
        _is_graph_delivery_contract,
        "graph delivery",
        aliases={
            "rir_contracts": cast(ModuleType, CONTRACTS),
            "rir_storage": cast(ModuleType, STORAGE),
        },
    ),
)

if not TYPE_CHECKING:
    FinalizeRequest = CONTRACTS.FinalizeRequest
    FinalizeResult = CONTRACTS.FinalizeResult


def _payload_sha256() -> str:
    payload_identity = _load_fixed_sibling(
        "payload_identity.py",
        "payload_identity",
        "_rir_finalize_payload_identity_",
        lambda value: callable(getattr(value, "payload_sha256", None)),
        "payload identity",
    )
    candidate = SCRIPT_DIR.parent
    if not (candidate / ".codex-plugin" / "plugin.json").is_file():
        candidate = SCRIPT_DIR.parents[2]
    return cast(Any, payload_identity).payload_sha256(candidate)


def _fast_scan_modules():
    renderer = _load_fixed_sibling(
        "fast_scan_renderer.py",
        "fast_scan_renderer",
        "_rir_finalize_fast_scan_renderer_",
        lambda value: callable(getattr(value, "render_fast_scan", None)),
        "Fast Scan renderer",
    )
    store = _load_fixed_sibling(
        "fast_scan_store.py",
        "fast_scan_store",
        "_rir_finalize_fast_scan_store_",
        lambda value: callable(getattr(value, "load_scan_receipt_bytes", None)),
        "Fast Scan store",
    )
    coordinator = cast(Any, GRAPH_DELIVERY.GRAPH_COORDINATOR)

    def valid(value: object) -> bool:
        return (
            getattr(value, "fast_scan_renderer", None) is renderer
            and getattr(value, "fast_scan_store", None) is store
            and getattr(value, "graph_builtin", None) is coordinator.BUILTIN
            and getattr(value, "graph_coordinator", None) is coordinator
            and isinstance(getattr(value, "FastScanRequest", None), type)
            and _callables(
                value,
                (
                    "prepare_fast_scan_identity",
                    "validate_fast_scan_receipt",
                    "canonical_fast_scan_bytes",
                ),
            )
        )

    fast_scan = _load_fixed_sibling(
        "fast_scan.py",
        "fast_scan",
        "_rir_finalize_fast_scan_",
        valid,
        "Fast Scan",
        aliases={
            "fast_scan_renderer": cast(ModuleType, renderer),
            "fast_scan_store": cast(ModuleType, store),
            "graph_builtin": cast(ModuleType, coordinator.BUILTIN),
            "graph_coordinator": cast(ModuleType, coordinator),
        },
    )
    return cast(_FastScanContract, fast_scan), cast(Any, store)


def _promoted_scan(root: Path, request, settings: Mapping[str, object]):
    if request.scan_id is None:
        return None
    if STORAGE.DRAFT_ID_PATTERN.fullmatch(request.scan_id) is None:
        raise ValueError("invalid Fast Scan ID")
    fast_scan, fast_scan_store = _fast_scan_modules()
    prepared = fast_scan.prepare_fast_scan_identity(
        fast_scan.FastScanRequest(
            root,
            request.request,
            request.repository_evidence,
            settings["audience"],
        ),
        settings["impact_graph"],
        _payload_sha256(),
    )
    if prepared.scan_id != request.scan_id:
        raise ValueError(
            "Fast Scan request identity does not match: the change request "
            "text, repository evidence rows, audience, graph settings, and "
            "repository contents must all equal the original rir_scan call"
        )
    payload = fast_scan_store.load_scan_receipt_bytes(root, request.scan_id)
    value = json.loads(payload)
    errors = fast_scan.validate_fast_scan_receipt(value)
    if errors or fast_scan.canonical_fast_scan_bytes(value) != payload:
        raise ValueError("Fast Scan receipt is invalid")
    if value["status"] != "complete" or value["can_promote"] is not True:
        raise ValueError("Fast Scan receipt is not promotable")
    if (
        value["request_sha256"] != prepared.request_sha256
        or value["repo_root_sha256"] != prepared.repo_root_sha256
        or value["payload_sha256"] != _payload_sha256()
        or value["settings"] != prepared.settings.to_mapping()
        or value["source_inventory"] != dict(prepared.inventory_mapping)
        or value["seeds"] != [row.to_mapping() for row in prepared.seeds]
    ):
        raise ValueError("Fast Scan source or identity is stale")
    graph = value["graph_receipt"]
    graph_errors = GRAPH_DELIVERY.GRAPH.validate_receipt(graph)
    if graph_errors:
        raise ValueError("Fast Scan graph receipt is invalid")
    graph_payload = GRAPH_DELIVERY.GRAPH.canonical_receipt_bytes(graph)
    return {
        "scan_id": request.scan_id,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "receipt_id": graph["receipt_id"],
        "receipt_sha256": hashlib.sha256(graph_payload).hexdigest(),
    }


def load_promoted_scan_context(
    root: Path, draft: Mapping[str, object], selected_receipt_id: str | None
):
    binding = draft.get("promoted_scan")
    if not isinstance(binding, dict) or set(binding) != {
        "scan_id",
        "sha256",
        "receipt_id",
        "receipt_sha256",
    }:
        raise ValueError("promoted Fast Scan binding is invalid")
    if selected_receipt_id != binding["receipt_id"]:
        raise ValueError("Fast Scan graph receipt does not match draft")
    request_value = draft.get("request")
    evidence_value = draft.get("repository_evidence")
    adapter_value = draft.get("adapter")
    settings_value = draft.get("settings")
    if (
        not isinstance(request_value, str)
        or not isinstance(evidence_value, list)
        or not all(isinstance(item, str) for item in evidence_value)
        or not isinstance(adapter_value, str)
        or not isinstance(settings_value, dict)
        or not isinstance(settings_value.get("audience"), str)
        or not isinstance(settings_value.get("delivery"), str)
    ):
        raise ValueError("promoted Fast Scan binding is invalid")
    audience = settings_value["audience"]
    delivery = settings_value["delivery"]
    request = CONTRACTS.BeginRequest(
        root,
        request_value,
        tuple(evidence_value),
        adapter_value,
        audience,
        delivery,
        binding["scan_id"],
    )
    promotion = _promoted_scan(root, request, settings_value)
    if promotion != binding:
        raise ValueError("promoted Fast Scan binding is stale")
    _fast_scan, fast_scan_store = _fast_scan_modules()
    payload = fast_scan_store.load_scan_receipt_bytes(root, binding["scan_id"])
    if hashlib.sha256(payload).hexdigest() != binding["sha256"]:
        raise ValueError("promoted Fast Scan digest is stale")
    wrapper = json.loads(payload)
    if not isinstance(wrapper, dict):
        raise ValueError("promoted Fast Scan binding is invalid")
    receipt = wrapper["graph_receipt"]
    if not isinstance(receipt, dict) or GRAPH_DELIVERY.GRAPH.validate_receipt(receipt):
        raise ValueError("promoted Fast Scan binding is invalid")
    graph_payload = GRAPH_DELIVERY.GRAPH.canonical_receipt_bytes(receipt)
    if hashlib.sha256(graph_payload).hexdigest() != binding["receipt_sha256"]:
        raise ValueError("promoted graph receipt digest is stale")
    GRAPH_DELIVERY.verify_receipt_sources(root, receipt)
    return {"receipt": receipt, "sha256": binding["receipt_sha256"], "binding": binding}


def _default_runtime() -> dict[str, object]:
    return {
        "root_path": STORAGE.root_path,
        "bounded_bytes": CONTRACTS.bounded_bytes,
        "max_finalize_bytes": CONTRACTS.MAX_FINALIZE_BYTES,
        "load_draft": STORAGE.load_private_draft,
        "report_lock": STORAGE.report_lock,
        "load_graph_context": GRAPH_DELIVERY.load_graph_context,
        "load_promoted_scan_context": load_promoted_scan_context,
        "validate_analysis": CONTRACTS.validate_analysis,
        "validate_graph_coverage": GRAPH_DELIVERY.validate_graph_coverage,
        "build_state": LINEAGE.build_state,
        "canonical_bytes": CONTRACTS.canonical_bytes,
        "write_controller_metadata": STORAGE.write_controller_metadata,
        "publish_revision": REPORT_STORE.publish_revision,
        "report_store_error": REPORT_STORE.ReportStoreError,
        "load_state_bytes": COMPACT_STATE.load_state_bytes,
        "render_compact": IMPACT_RENDERER.render_compact,
        "render_markdown": IMPACT_RENDERER.render_markdown,
        "draft_path": STORAGE.draft_path,
        "consume_draft": STORAGE.consume_draft,
        "result_type": CONTRACTS.FinalizeResult,
    }


def _operation(runtime: Mapping[str, object], name: str):
    value = runtime.get(name)
    if not callable(value):
        raise TypeError(f"finalize runtime operation is invalid: {name}")
    return value


def _finalize(request, runtime: Mapping[str, object]):
    root = _operation(runtime, "root_path")(request.repo_root)
    maximum = runtime.get("max_finalize_bytes")
    if type(maximum) is not int or maximum <= 0:
        raise TypeError("finalize runtime maximum is invalid")
    _operation(runtime, "bounded_bytes")(request.analysis, maximum, "finalize input")
    load_draft = _operation(runtime, "load_draft")
    draft = load_draft(root, request.draft_id)
    if draft.get("consumed") is True:
        raise ValueError("draft is already consumed")
    with _operation(runtime, "report_lock")(root, str(draft["report_id"])):
        draft = load_draft(root, request.draft_id)
        if draft.get("consumed") is True:
            raise ValueError("draft is already consumed")
        settings_value = draft.get("settings")
        graph_settings = (
            settings_value.get("impact_graph") if isinstance(settings_value, dict) else None
        )
        if not isinstance(graph_settings, dict):
            raise ValueError("draft graph settings are invalid")
        graph_context = None
        if graph_settings.get("enabled") is True:
            graph_context = (
                _operation(runtime, "load_promoted_scan_context")(
                    root, draft, request.graph_receipt_id
                )
                if draft.get("promoted_scan") is not None
                else _operation(runtime, "load_graph_context")(
                    root, draft, request.graph_receipt_id
                )
            )
            _operation(runtime, "validate_analysis")(request.analysis)
            _operation(runtime, "validate_graph_coverage")(request.analysis, graph_context)
        elif request.graph_receipt_id is not None:
            raise ValueError("graph_receipt_id is not allowed when impact graph is disabled")
        state, key_map = _operation(runtime, "build_state")(draft, request.analysis, graph_context)
        state_bytes = _operation(runtime, "canonical_bytes")(state)
        _operation(runtime, "write_controller_metadata")(
            root,
            draft,
            state_bytes,
            key_map,
            None
            if graph_context is None
            else {
                "receipt_id": graph_context["receipt"]["receipt_id"],
                "sha256": graph_context["sha256"],
            },
        )
        report_store_error = runtime.get("report_store_error")
        if not isinstance(report_store_error, type) or not issubclass(
            report_store_error, Exception
        ):
            raise TypeError("finalize runtime report error is invalid")
        try:
            published = _operation(runtime, "publish_revision")(
                root, state_bytes, resume_partial=True
            )
        except (FileExistsError, report_store_error) as error:
            raise ValueError(f"controller publication failed: {error}") from error
        stored_state, errors = _operation(runtime, "load_state_bytes")(
            published.state_path.read_bytes()
        )
        if errors or stored_state is None:
            raise ValueError("published state could not be verified")
        stored_settings = stored_state.get("settings")
        delivery = stored_settings.get("delivery") if isinstance(stored_settings, dict) else None
        if not isinstance(delivery, str):
            raise ValueError("published state could not be verified")
        display = (
            _operation(runtime, "render_compact")(stored_state)
            if delivery == "compact"
            else _operation(runtime, "render_markdown")(stored_state)
        )
        if display.endswith("\n"):
            display = display[:-1]
        _operation(runtime, "consume_draft")(
            _operation(runtime, "draft_path")(root, request.draft_id),
            draft,
            published,
            key_map,
        )
    return _operation(runtime, "result_type")(
        status="published",
        report_id=published.report_id,
        revision=published.revision,
        delivery=delivery,
        display_text=display,
        state_path=published.state_path,
        markdown_path=published.markdown_path,
        markdown_sha256=published.markdown_sha256,
    )


def finalize_refinement(
    request: FinalizeRequest, *, _runtime: Mapping[str, object] | None = None
) -> FinalizeResult:
    return _finalize(request, _default_runtime() if _runtime is None else _runtime)
