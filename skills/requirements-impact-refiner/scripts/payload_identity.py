"""Deterministic identity for the executable controller plugin payload."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT_FILES = (
    ".codex-plugin/plugin.json",
    ".mcp.json",
    "schemas/controller-analysis.schema.json",
    "schemas/compact-state.schema.json",
    "schemas/impact-graph-receipt.schema.json",
    "schemas/fast-impact-scan.schema.json",
    "scripts/compact_state.py",
    "scripts/fast_scan.py",
    "scripts/fast_scan_renderer.py",
    "scripts/fast_scan_store.py",
    "scripts/graph_adapter_ast_grep.py",
    "scripts/graph_adapter_codegraph.py",
    "scripts/graph_adapter_joern.py",
    "scripts/graph_adapter_scip.py",
    "scripts/graph_builtin.py",
    "scripts/graph_cache.py",
    "scripts/graph_coordinator.py",
    "scripts/graph_providers.py",
    "scripts/impact_graph.py",
    "scripts/impact_renderer.py",
    "scripts/impact_report.py",
    "scripts/launch-rir-mcp",
    "scripts/payload_identity.py",
    "scripts/report_store.py",
    "scripts/resolve-settings.py",
    "scripts/rir-controller.py",
    "scripts/rir_contracts.py",
    "scripts/rir_finalize.py",
    "scripts/rir_graph_delivery.py",
    "scripts/rir_lineage.py",
    "scripts/rir_report_context.py",
    "scripts/rir_storage.py",
    "scripts/rir_controller.py",
    "scripts/rir_mcp_server.py",
    "scripts/validate-impact-report.py",
)


def functional_paths(plugin_root: Path) -> tuple[Path, ...]:
    root = Path(plugin_root)
    paths = [root / relative for relative in ROOT_FILES]
    skill_root = root / "skills" / "requirements-impact-refiner"
    paths.extend(
        path
        for path in skill_root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    )
    result = tuple(sorted(set(paths), key=lambda path: path.relative_to(root).as_posix()))
    if any(not path.is_file() or path.is_symlink() for path in result):
        raise ValueError("controller payload contains a missing or unsafe file")
    return result


def payload_sha256(plugin_root: Path) -> str:
    root = Path(plugin_root)
    digest = hashlib.sha256()
    for path in functional_paths(root):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()
