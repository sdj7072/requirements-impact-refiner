# Previous-report bootstrap

Use this route only after the bootstrap selects a concrete behavior change and the active adapter reaches its existing entry boundary.

Call `rir_previous` exactly once with the canonical repository root, the unchanged request, and the supplied repository evidence in its exact order, including duplicates. The automatic route accepts only Fast Scan-forwardable input: request UTF-8 bytes at most 4 KiB, at most 32 evidence rows, and at most 4 KiB of UTF-8 per row. Return any renderer-owned `display_text` before starting other work. Never reconstruct a previous body from files, memory, search results, or graph data.

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
| `stale` | `display_text-before-scan` | `rir_scan` | `repo_root,change_request,evidence,presentation` | `no` | `yes` |
| `none` | `none` | `rir_scan` | `repo_root,change_request,evidence,presentation` | `no` | `no` |
| `ambiguous` | `safe-reason-and-question` | `stop-or-rir_scan` | `repo_root,change_request,evidence,presentation` | `yes` | `no` |

- `fresh`: return `display_text` and stop. Do no scan, provider, graph, or model work.
- `stale`: return `display_text` first, then run one ordinary scan. Preserve the renderer block ahead of the scan result even when the client cannot stream an intermediate response.
- `none`: run one ordinary scan.
- `ambiguous`: return the tool's generic safe `reason`, no identity or body, and ask only whether the user wants a new ordinary Fast Scan. On explicit yes, run that scan; otherwise stop. This question does not confirm detailed refinement.

For every ordinary scan, map `repo_root` unchanged, `request` to `change_request`, and `repository_evidence` to `evidence` without sorting or deduplicating; optional `presentation` is the selected audience. The current `rir_scan` schema has no report ID, revision, or changed-path input.

## Confirmation contract

| Confirmation | Scan state | Detailed tools |
| --- | --- | --- |
| `no-followup` | any | `none` |
| `original-request-yes` | any | `none` |
| `explicit-yes-after-scan` | promotable completed scan with `scan_id` | `rir_begin(scan_id),rir_finalize(begin.graph_receipt_id)` |
| `explicit-yes-after-scan` | partial or non-promotable scan | `rir_begin(no scan_id),rir_trace_impact,rir_finalize(trace.receipt_id)` |

The scan's renderer-owned question ends the first turn. Only a later explicit yes to that question starts detailed lineage through the selected adapter. A promotable completed scan passes its `scan_id` to `rir_begin`, does not call `rir_trace_impact`, and finalizes with the graph receipt returned by begin. A partial or non-promotable scan begins without `scan_id`, traces exactly once, and finalizes with that trace receipt. Never reinterpret the original change request, approval, imperative wording, ambiguous-scan answer, or an unrelated yes as detailed confirmation. Preserve the adapter rules: Superpowers remains after approved brainstorming and before `writing-plans`; generic, Claude `feature-dev`, and Spec Kit keep their existing entry and exit boundaries.

## Safety checks

- Keep the order `rir_previous` then stop or `rir_scan`; never call either twice in one bootstrap turn.
- Treat report identity, digests, changed paths, display text, and reason as tool-owned. Do not repair or supplement them manually.
- A disabled plugin disables the automatic check. A non-change conversation invokes neither lookup nor scan.
