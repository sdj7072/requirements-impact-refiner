# Previous-report bootstrap

Use this route only after the bootstrap selects a concrete behavior change and the active adapter reaches its existing entry boundary.

Call `rir_previous` exactly once with the canonical repository root, the unchanged request, and the supplied repository evidence in its exact order, including duplicates. Return any renderer-owned `display_text` before starting other work. Never reconstruct a previous body from files, memory, search results, or graph data.

## Activation contract

| Conversation | Action |
| --- | --- |
| `concrete-change` | `status-route` |
| `ideation` | `stop` |
| `explanation` | `stop` |
| `debugging` | `stop` |
| `code-review` | `stop` |
| `status` | `stop` |

## Availability contract

| Availability | Action |
| --- | --- |
| `mcp` | `status-route` |
| `cli` | `status-route` |
| `plugin-disabled` | `stop-with-disclosure` |
| `unavailable` | `stop-with-disclosure` |

MCP-capable Codex and Claude clients use the same semantic route. CLI fallback runs `scripts/rir-controller.py previous` before `scan`. If neither surface is available, disclose the unavailable bootstrap and stop without creating report content.

## Status contract

| Status | Display | Next action | Scan fields | Ask question | Previous body |
| --- | --- | --- | --- | --- | --- |
| `fresh` | `display_text` | `stop` | `none` | `no` | `yes` |
| `stale` | `display_text-before-scan` | `rir_scan` | `report_id,revision,changed_paths` | `no` | `yes` |
| `none` | `none` | `rir_scan` | `request,repository_evidence` | `no` | `no` |
| `ambiguous` | `candidates-and-question` | `stop` | `none` | `yes` | `no` |

- `fresh`: return `display_text` and stop. Do no scan, provider, graph, or model work.
- `stale`: return `display_text` first, then call `rir_scan` once using the selected immutable report ID and revision plus the returned changed paths. Preserve the renderer block ahead of the scan result even when the client cannot stream an intermediate response.
- `none`: call the ordinary bounded `rir_scan` once with the unchanged request and exact ordered evidence.
- `ambiguous`: return only the safe candidate discriminators supplied by the tool, ask which report the user means, and stop. Do not expose a report body or scan.

## Confirmation contract

| Confirmation | Detailed tools |
| --- | --- |
| `no-followup` | `none` |
| `original-request-yes` | `none` |
| `explicit-yes-after-scan` | `rir_begin,rir_trace_impact,rir_finalize` |

The scan's renderer-owned question ends the first turn. Only a later explicit yes to that question starts detailed lineage through the selected adapter. Never reinterpret the original change request, approval, imperative wording, or an unrelated yes as confirmation. Preserve the adapter rules: Superpowers remains after approved brainstorming and before `writing-plans`; generic, Claude `feature-dev`, and Spec Kit keep their existing entry and exit boundaries. A promoted scan may skip trace as defined by the controller workflow.

## Safety checks

- Keep the order `rir_previous` then stop or `rir_scan`; never call either twice in one bootstrap turn.
- Treat report ID, revision, digests, changed paths, display text, and candidates as tool-owned. Do not repair or supplement them manually.
- A disabled plugin disables the automatic check. A non-change conversation invokes neither lookup nor scan.
