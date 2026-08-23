#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import re
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import rir_controller
import payload_identity


MAX_LINE_BYTES = 2 * 1024 * 1024
PROTOCOL_VERSION = "2025-06-18"
ANALYSIS_SCHEMA = json.loads(
    (SCRIPT_DIR.parent / "schemas" / "controller-analysis.schema.json").read_text(
        encoding="utf-8"
    )
)
INSTALLED_PAYLOAD_SHA256 = payload_identity.payload_sha256(SCRIPT_DIR.parent)


def _expand_schema(schema, root):
    if isinstance(schema, list):
        return [_expand_schema(item, root) for item in schema]
    if not isinstance(schema, dict):
        return schema
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/"):
        target = root
        for part in reference[2:].split("/"):
            target = target[part]
        return _expand_schema(target, root)
    return {
        key: _expand_schema(value, root)
        for key, value in schema.items()
        if key not in {"$schema", "$defs"}
    }


EXPANDED_ANALYSIS_SCHEMA = _expand_schema(ANALYSIS_SCHEMA, ANALYSIS_SCHEMA)


BEGIN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["repo_root", "request", "repository_evidence", "adapter"],
    "properties": {
        "repo_root": {"type": "string", "minLength": 1},
        "request": {"type": "string", "minLength": 1, "maxLength": 262144},
        "repository_evidence": {"type": "array", "maxItems": 128, "items": {"type": "string", "minLength": 1, "maxLength": 65536}},
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
        "analysis": EXPANDED_ANALYSIS_SCHEMA,
    },
}
TOOLS = [
    {
        "name": "rir_begin",
        "description": "Create a local, network-free, repository-bound impact-refinement draft before analysis; data stays in the isolated workspace.",
        "inputSchema": BEGIN_SCHEMA,
    },
    {
        "name": "rir_finalize",
        "description": "Validate, publish, and render one local, network-free controller draft inside the isolated workspace.",
        "inputSchema": FINALIZE_SCHEMA,
    },
]


def _error(identifier, code, message):
    return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": str(message)[:1024]}}


def _result(identifier, result):
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def _validate_arguments(arguments, schema, label):
    _validate_schema(arguments, schema, f"{label} arguments")


def _matches_type(value, expected):
    types = expected if isinstance(expected, list) else [expected]
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "null": lambda item: item is None,
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
    }
    return any(name in checks and checks[name](value) for name in types)


def _validate_schema(value, schema, label):
    if "oneOf" in schema:
        matches = 0
        for option in schema["oneOf"]:
            try:
                _validate_schema(value, option, label)
            except ValueError:
                continue
            matches += 1
        if matches != 1:
            raise ValueError(f"{label} does not match exactly one allowed shape")
        return
    if "type" in schema and not _matches_type(value, schema["type"]):
        raise ValueError(f"{label} has the wrong type")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{label} has an unsupported value")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = sorted(set(schema.get("required", [])) - set(value))
        unknown = sorted(set(value) - set(properties)) if schema.get("additionalProperties") is False else []
        if missing:
            raise ValueError(f"{label} is missing {missing[0]}")
        if unknown:
            raise ValueError(f"{label} has unknown key {unknown[0]}")
        for key, item in value.items():
            if key in properties:
                _validate_schema(item, properties[key], f"{label}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"{label} has too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValueError(f"{label} has too many items")
        if schema.get("uniqueItems"):
            serialized = [json.dumps(item, sort_keys=True) for item in value]
            if len(serialized) != len(set(serialized)):
                raise ValueError(f"{label} contains duplicate items")
        for item in value:
            _validate_schema(item, schema.get("items", {}), f"{label} item")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValueError(f"{label} is too short")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValueError(f"{label} is too long")
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, value) is None:
            raise ValueError(f"{label} has an invalid format")


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
        "prior_key_map": result.prior_key_map,
        "repository_evidence": list(arguments["repository_evidence"]),
        "allowed_enums": {
            "phase": ["pre-decision", "post-decision"],
            "adapter": sorted(rir_controller.ADAPTERS),
            "audience": ["simple", "balanced", "technical"],
            "delivery": ["compact", "full"],
        },
        "analysis_contract": EXPANDED_ANALYSIS_SCHEMA,
        "semantic_rules": [
            "pre-decision requires decision_needed with two or three options and decisions must be empty",
            "post-decision requires decision_needed null and at least one explicit decision",
            "blocked impacts require workflow Not ready",
            "deferred impacts may proceed only when listed as a remaining risk with an owner",
            "accepted impacts require a linked decision and resolved impacts require current evidence",
            "the Superpowers handoff marker is controller-owned and must not be authored or decorated",
        ],
        "installed_payload_sha256": INSTALLED_PAYLOAD_SHA256,
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
        return _result(identifier, {
            "protocolVersion": PROTOCOL_VERSION,
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
    except Exception:
        return _error(identifier, -32603, "controller operation failed")
    return _result(identifier, result)


def main():
    source = sys.stdin.buffer
    destination = sys.stdout
    while True:
        raw = source.readline(MAX_LINE_BYTES + 1)
        if not raw:
            return 0
        if len(raw) > MAX_LINE_BYTES:
            while raw and not raw.endswith(b"\n"):
                raw = source.readline(MAX_LINE_BYTES + 1)
            response = _error(None, -32700, "request exceeds 2 MiB")
        else:
            try:
                message = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
                response = _error(None, -32700, "parse error")
            else:
                response = handle(message)
        if response is not None:
            destination.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
            destination.flush()


if __name__ == "__main__":
    raise SystemExit(main())
