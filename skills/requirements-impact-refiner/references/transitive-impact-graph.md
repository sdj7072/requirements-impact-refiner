# Transitive Impact Graph

Read this after the compact graph receipt arrives. It is evidence, not a plan or a request to operate providers.

## Use the receipt

Choose only paths returned for the current draft. Map each impact to one or more returned path IDs; describe the shortest user-facing path. Reuse a path for same-risk impacts only when the same path actually supports both claims. A different consequence, owner, or mitigation needs its own impact even when the path overlaps.

Do not create graph JSON, rerun provider commands, infer omitted edges, or hide a frontier. A path with no selected receipt evidence is supplied-only: give a bounded rationale, mark the impact `unknown`, and do not resolve it. Keep `unknown` when providers disagree, evidence conflicts, coverage ends, or a required source is unavailable; name the gap rather than selecting a winner.

## Confidence and coverage

`verified-provider` and `verified-source` support direct evidence; `structural-inferred` supports an inference; `lexical` is weaker textual evidence. These receipt confidences can limit, never upgrade, the report's `verified`/`inferred`/`unknown` level. A frontier is an explicit coverage limit, not a negative finding.

The compact footer reports elapsed scan time, node/edge counts, frontier count, budget status, and cache state without raw provider output. Cache hits reuse a matching receipt; partial or invalidated cache data stays partial. Deep broadens bounded discovery only; it cannot prove completeness. Optional providers are detect-only, never auto-installed, and may be unavailable, unsafe, unsupported, stale, failed, or timed out.

## Presentation and fallbacks

Compact output has one short path line per impact and one coverage footer. Simple uses plain component names; balanced adds the path ID; technical adds receipt-derived provider, confidence, and location. Escape Markdown table cells and never leak raw provider payloads.

CLI uses the controller's begin, trace, and finalize flow with the same receipt rules. Use full-inline only when both MCP and CLI are unavailable; disclose unavailable persistence and fast revisions, preserve unknown frontiers, and stop before planning.
