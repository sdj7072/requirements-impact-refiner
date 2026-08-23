#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import rir_controller


MAX_LINE_BYTES = 2 * 1024 * 1024
PROTOCOL_VERSION = "2025-06-18"


BEGIN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["repo_root", "request", "repository_evidence", "adapter"],
    "properties": {
        "repo_root": {"type": "string", "minLength": 1},
        "request": {"type": "string", "minLength": 1, "maxLength": 262144},
        "repository_evidence": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "adapter": {"enum": ["generic", "superpowers", "claude-feature-dev", "spec-kit"]},
        "audience_override": {"type": ["string", "null"], "enum": ["simple", "balanced", "technical", None]},
        "delivery_override": {"type": ["string", "null"], "enum": ["compact", "full", None]},
    },
}
FINALIZE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["repo_root", "draft_id", "analysis"],
    "properties": {
        "repo_root": {"type": "string", "minLength": 1},
        "draft_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
        "analysis": {"type": "object"},
    },
}
TOOLS = [
    {
        "name": "rir_begin",
        "description": "Create a repository-bound impact-refinement draft before analysis.",
        "inputSchema": BEGIN_SCHEMA,
    },
    {
        "name": "rir_finalize",
        "description": "Validate, publish, and render one controller draft.",
        "inputSchema": FINALIZE_SCHEMA,
    },
]


def _error(identifier, code, message):
    return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": str(message)[:1024]}}


def _result(identifier, result):
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def _validate_arguments(arguments, schema, label):
    if not isinstance(arguments, dict):
        raise ValueError(f"{label} arguments must be an object")
    expected = set(schema["properties"])
    unknown = sorted(set(arguments) - expected)
    missing = sorted(set(schema["required"]) - set(arguments))
    if unknown:
        raise ValueError(f"unknown {label} argument {unknown[0]}")
    if missing:
        raise ValueError(f"missing {label} argument {missing[0]}")


def _begin(arguments):
    _validate_arguments(arguments, BEGIN_SCHEMA, "rir_begin")
    result = rir_controller.begin_refinement(
        rir_controller.BeginRequest(
            repo_root=Path(arguments["repo_root"]),
            request=arguments["request"],
            repository_evidence=tuple(arguments["repository_evidence"]),
            adapter=arguments["adapter"],
            audience_override=arguments.get("audience_override"),
            delivery_override=arguments.get("delivery_override"),
        )
    )
    root = Path(arguments["repo_root"]).resolve()
    structured = {
        "draft_id": result.draft_id,
        "draft_path": result.draft_path.relative_to(root).as_posix(),
        "report_id": result.report_id,
        "revision": result.revision,
        "previous_sha256": result.previous_sha256,
        "settings": dict(result.settings),
        "prior_state": result.prior_state,
    }
    return {
        "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False, sort_keys=True)}],
        "structuredContent": structured,
        "isError": False,
    }


def _finalize(arguments):
    _validate_arguments(arguments, FINALIZE_SCHEMA, "rir_finalize")
    result = rir_controller.finalize_refinement(
        rir_controller.FinalizeRequest(
            repo_root=Path(arguments["repo_root"]),
            draft_id=arguments["draft_id"],
            analysis=arguments["analysis"],
        )
    )
    root = Path(arguments["repo_root"]).resolve()
    structured = {
        "status": result.status,
        "report_id": result.report_id,
        "revision": result.revision,
        "delivery": result.delivery,
        "display_text": result.display_text,
        "state_path": result.state_path.relative_to(root).as_posix(),
        "markdown_path": result.markdown_path.relative_to(root).as_posix(),
        "markdown_sha256": result.markdown_sha256,
    }
    return {
        "content": [{"type": "text", "text": result.display_text}],
        "structuredContent": structured,
        "isError": False,
    }


def handle(message):
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, -32600, "invalid JSON-RPC request")
    identifier = message.get("id")
    method = message.get("method")
    params = message.get("params", {})
    if identifier is None:
        return None
    if method == "initialize":
        version = params.get("protocolVersion") if isinstance(params, dict) else None
        return _result(identifier, {
            "protocolVersion": version or PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "requirements-impact-refiner", "version": "0.4.0"},
        })
    if method == "tools/list":
        return _result(identifier, {"tools": TOOLS})
    if method != "tools/call" or not isinstance(params, dict):
        return _error(identifier, -32601, "method not found")
    name = params.get("name")
    arguments = params.get("arguments")
    try:
        if name == "rir_begin":
            result = _begin(arguments)
        elif name == "rir_finalize":
            result = _finalize(arguments)
        else:
            return _error(identifier, -32602, "unknown tool")
    except (TypeError, ValueError) as error:
        return _error(identifier, -32602, error)
    return _result(identifier, result)


def main():
    source = sys.stdin.buffer
    destination = sys.stdout
    while True:
        raw = source.readline(MAX_LINE_BYTES + 1)
        if not raw:
            return 0
        if len(raw) > MAX_LINE_BYTES and not raw.endswith(b"\n"):
            while raw and not raw.endswith(b"\n"):
                raw = source.readline(MAX_LINE_BYTES + 1)
            response = _error(None, -32700, "request exceeds 2 MiB")
        else:
            try:
                message = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                response = _error(None, -32700, "parse error")
            else:
                response = handle(message)
        if response is not None:
            destination.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
            destination.flush()


if __name__ == "__main__":
    raise SystemExit(main())
