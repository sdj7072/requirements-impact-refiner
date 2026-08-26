# Previous-report bootstrap

Use this route only after the bootstrap selects a concrete behavior change and the active adapter reaches its existing entry boundary.

Call `rir_previous` with the canonical repository root, unchanged request, and supplied repository evidence in exact order, including duplicates. Lookup keeps its detailed limits: raw request at most 256 KiB and evidence under the existing ordered-evidence contract. Return renderer-owned `display_text` before other work. Never reconstruct a previous body from files, memory, search results, or graph data.

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

MCP-capable Codex and Claude clients use the same semantic route. CLI fallback runs `scripts/rir-controller.py previous` before `scan`; ambiguity selection uses input `report_id` or `--report-id`. If neither surface is available, disclose the unavailable bootstrap and stop without creating report content.

## Status contract

| Status | Display | Next action | Scan fields | Ask question | Previous body |
| --- | --- | --- | --- | --- | --- |
| `fresh` | `display_text` | `stop` | `none` | `no` | `yes` |
| `stale` | `display_text-before-scan` | `rir_scan-if-forwardable` | `repo_root,change_request,evidence,presentation` | `no` | `yes` |
| `none` | `none` | `rir_scan-if-forwardable` | `repo_root,change_request,evidence,presentation` | `no` | `no` |
| `ambiguous` | `candidate-question` | `rir_previous(report_id)` | `none` | `yes` | `no` |

- `fresh`: return `display_text` and stop. Do no scan, provider, graph, or model work.
- `stale`: return `display_text` first. If scan-forwardable, run one ordinary scan; otherwise stop after the shortening instruction.
- `none`: if scan-forwardable, run one ordinary scan; otherwise stop after the shortening instruction.
- `ambiguous`: show only the returned candidates—at most 16 rows of `report_id`, `revision`, and `created_at`—and ask which report ID to use. Stop. A reply restarts lookup with the exact same root, request, ordered evidence, payload, and selected `report_id`. Never display a body from the initial ambiguous response. A missing, malformed, foreign, or non-candidate ID returns no body and does not scan.

Before `rir_scan`, separately require request UTF-8 at most 4 KiB, at most 32 evidence rows, and at most 4 KiB UTF-8 per row. A wider fresh lookup still returns and stops. A wider stale/none result never calls an invalid scan: keep any stale display, emit one bounded sentence in the request language asking for shorter input and naming those limits, then stop. English: “Shorten the request to 4 KiB and evidence to 32 rows of 4 KiB, then retry.” Korean: “요청은 4 KiB 이하, 근거는 행당 4 KiB 이하로 32개까지 줄인 뒤 다시 시도해 주세요.” Japanese: “リクエストを4 KiB以下、根拠を1行4 KiB以下で32件までに短縮して再試行してください。”

For every ordinary scan, map `repo_root` unchanged, `request` to `change_request`, and `repository_evidence` to `evidence` without sorting or deduplicating; optional `presentation` is the selected audience. The current `rir_scan` schema has no report ID, revision, or changed-path input.

## Scan result contract

- `needs_input`: return the renderer's boundary question and stop. The user's corrected request/evidence starts a new `rir_previous → rir_scan` turn. Do not call begin, trace, or finalize.
- `complete` with `can_promote` and `scan_id`: the later explicit refinement yes uses the promoted branch below.
- `partial` or otherwise non-promotable, excluding `needs_input`: the later explicit refinement yes uses the traced branch below.

## Confirmation contract

| Confirmation | Scan state | Detailed tools |
| --- | --- | --- |
| `no-followup` | any | `none` |
| `original-request-yes` | any | `none` |
| boundary reply | `needs_input` | `restart rir_previous,rir_scan` |
| `explicit-yes-after-scan` | promotable completed scan with `scan_id` | `rir_begin(scan_id),rir_finalize(begin.graph_receipt_id)` |
| `explicit-yes-after-scan` | partial/non-promotable, not `needs_input` | `rir_begin(no scan_id),rir_trace_impact,rir_finalize(trace.receipt_id)` |

Only a later explicit yes to a non-`needs_input` scan's refinement question starts detailed lineage. A promotable completed scan passes `scan_id` to `rir_begin`, does not trace, and finalizes with begin's graph receipt. A partial/non-promotable scan begins without `scan_id`, traces exactly once, and finalizes with that receipt. Never reinterpret the original request, approval, imperative wording, ambiguity selection, boundary correction, or unrelated yes as detailed confirmation. Preserve adapter rules: Superpowers remains after approved brainstorming and before `writing-plans`; generic, Claude `feature-dev`, and Spec Kit keep their existing boundaries.

## Safety checks

- Keep the order `rir_previous` then stop or `rir_scan`; ambiguity and boundary replies start new turns.
- Treat report identity, digests, changed paths, display text, and reason as tool-owned. Do not repair or supplement them manually.
- A disabled plugin disables the automatic check. A non-change conversation invokes neither lookup nor scan.
