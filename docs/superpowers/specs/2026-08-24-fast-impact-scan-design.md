# Fast Impact Scan Design

## Context

Requirements Impact Refiner 0.4 can discover distant repository effects such as API → decoder → cache → migration test. Its graph engine is already fast: the representative `GRAPH-api-mobile-cache-migration` canary completed the built-in graph scan in 17 ms and found distance-three paths. The full model turn nevertheless took 297.159 seconds because the normal workflow loaded several references, authored a large analysis object, supplied four trace seeds, and attempted finalize three times.

The bottleneck is therefore orchestration, not graph traversal. The default automatic experience must expose regression risk quickly without forcing every change through a full formal impact report.

## Goals

- Return a useful first impact result with a 10-second target and 30-second hard scan ceiling.
- Preserve the core promise: a change to A must surface plausible breakage in seemingly unrelated C, D, or Z.
- Use one normal MCP call and no model-authored graph JSON.
- Keep the first response at or below 180 words.
- Make incomplete evidence and unknown frontiers visible; never imply safety from a partial scan.
- Reuse the exact scan receipt if the user later requests full refinement.
- Preserve the existing `rir_begin → rir_trace_impact → rir_finalize` flow for compatibility and advanced use.

## Non-goals

- Automatically generate a complete impact report, decision record, and acceptance criteria for every change.
- Automatically escalate a high-risk scan into the expensive refinement flow.
- Install, update, authenticate, index, upload, or start external providers.
- Guarantee that the surrounding LLM returns within 30 seconds; the controller can enforce only its own scan deadline. The default path minimizes model work so the product-level response can approach that target.
- Qualify v0.4 for release from a single canary. The six-case smoke and release matrix remain separate gates.

## User Experience

For a concrete software behavior change, the bootstrap invokes Fast Scan automatically. The user receives:

1. the interpreted change boundary;
2. up to eight ranked affected components or paths;
3. the most important possible failures in plain language;
4. unknown or unscanned frontiers;
5. elapsed time and cache status; and
6. one explicit choice: stop here or request detailed refinement.

High or critical risk never starts detailed refinement automatically. The user sees the result first and chooses whether the additional latency and token cost are justified.

## MCP Interface

### `rir_scan`

Input:

```json
{
  "repo_root": "/absolute/repository/path",
  "change_request": "Rename profile.displayName to profile.name",
  "evidence": ["optional concise supplied evidence"],
  "presentation": "simple | balanced | technical"
}
```

Rules:

- `repo_root` must resolve to a real bounded repository directory.
- `change_request` is required, UTF-8, nonblank, and at most 4 KiB.
- `evidence` is optional, contains at most 32 nonblank strings, and is size-bounded before parsing.
- `presentation` defaults to the existing resolved repository/user setting.
- The tool does not accept provider commands, graph edges, report IDs, decisions, or acceptance criteria.

Output:

```json
{
  "status": "complete | partial | needs_input",
  "scan_id": "32 lowercase hex characters",
  "receipt_id": "32 lowercase hex characters",
  "receipt_sha256": "64 lowercase hex characters",
  "display_text": "renderer-owned text at or below 180 words",
  "risk_level": "low | medium | high | critical | unknown",
  "paths": [],
  "frontier": [],
  "elapsed_ms": 17,
  "cache_status": "hit | miss | bypassed",
  "can_promote": true
}
```

`display_text` is the only text returned to the user. Structured fields exist for audit, promotion, and client UI; the model must not rewrite them.

## Seed Derivation

Fast Scan derives seeds deterministically from the bounded request and supplied evidence:

1. exact file paths and qualified symbols;
2. code-form identifiers such as `profile.displayName`;
3. repository matches for remaining distinctive terms; and
4. explicit supplied-evidence locations.

The controller ranks and deduplicates candidates, preserves their derivation evidence, and passes a bounded set to the existing graph coordinator. It never asks the model to invent edges or manually construct seeds.

If no trustworthy seed can be derived, the tool returns `needs_input` with at most three repository-backed candidates. It does not silently broaden to a repository-wide guess and does not automatically issue a second scan.

## Persistence and Promotion

Fast Scan writes a private, immutable receipt under:

```text
.requirements-impact-refiner/scans/<scan_id>.json
```

The receipt is mode `0600`, atomically published, and bound to:

- repository-root identity;
- normalized change request and evidence digest;
- resolved graph settings and provider policy;
- source inventory and freshness state;
- normalized derived seeds;
- graph receipt ID and canonical digest; and
- payload identity.

The existing `rir_begin` gains an optional `scan_id`. When present, it validates freshness and identity, creates a normal draft bound to the existing receipt, and skips graph execution. Detailed refinement then requires only analysis plus `rir_finalize`.

Promotion is explicit and one-way. A promoted scan cannot be rebound to another repository, request, draft, or payload. A stale or partial receipt remains visible and cannot support a false resolved impact.

## Rendering

The Fast Scan renderer is separate from the full report renderer but uses the same escaping and presentation vocabulary.

- Simple: component names and plain-language failures.
- Balanced: component names plus short A → C → D → Z paths.
- Technical: provider, confidence, and locations when receipt-backed.

All modes include one coverage footer. The renderer prioritizes critical/high paths, then unknown frontiers, then lower-risk paths. It truncates labels independently and never drops provenance or frontier disclosure to meet the 180-word cap.

## Deadline, Cache, and Failure Semantics

One monotonic deadline covers lock acquisition, inventory collection, cache lookup, built-in scanning, optional detect-only providers, normalization, and receipt publication.

- Target: 10,000 ms.
- Hard ceiling: 30,000 ms.
- At the ceiling, return `partial` with the exact completed paths and explicit unknown frontier.
- Provider unavailable, unsafe, stale, or timed out: continue with built-in evidence and disclose the limitation.
- Cache hit: reuse only an exact request/settings/source/payload identity.
- Source mutation or stale cache: invalidate and rescan within the same remaining deadline.
- Publication uncertainty: fail closed without returning a promotable scan ID.

No error path triggers full refinement or a second scan automatically.

## Compatibility

- Existing clients may continue to use `rir_begin`, `rir_trace_impact`, and `rir_finalize` unchanged.
- MCP lists `rir_scan` first as the default automatic path, followed by the existing advanced tools.
- CLI gains a matching `scan` command with the same controller implementation and renderer-owned stdout.
- Generic Agent Skills clients without MCP may use the CLI scan fallback.
- Full-inline mode cannot claim persisted Fast Scan receipts and must disclose that limitation.
- Codex, Claude Code, and other supported clients use the user's selected model; the plugin does not select or substitute a model.

## Skill Routing and Token Budget

The automatic bootstrap loads only the short Fast Scan recipe. It must not require the controller workflow, graph reference, integration adapter, report schema, or report template before `rir_scan`.

Detailed references are loaded only after the user selects full refinement. The default skill instruction target is below 180 words, and normal Fast Scan guidance returned by the MCP is below 250 words. Provider raw output and full receipts never enter model context.

## Testing

Implementation is test-driven and uses no live model calls until deterministic approval.

Required deterministic coverage:

- one-call MCP and CLI scan contracts;
- exact 10-second target and 30-second partial-result ceiling;
- A → C → D → Z path discovery across the five graph fixtures;
- no-change and no-trustworthy-seed cases;
- source inventory, cache identity, and mutation invalidation;
- receipt privacy, atomic publication, lineage, and promotion freshness;
- one coverage footer and 180-word limits in all presentation modes;
- HTML/Markdown escaping and provenance preservation;
- no provider install/network/auth/server commands;
- backward compatibility for the three-tool advanced flow; and
- promotion that reuses the exact receipt without a second graph run.

After deterministic tests and independent review pass, run exactly one representative installed-plugin canary. A failed canary does not trigger an automatic retry. The six-case and 85-run release evaluations require separate approval.

## Rollout

1. Add the deterministic `rir_scan` controller/MCP/CLI contract.
2. Add private scan receipts and explicit `rir_begin(scan_id)` promotion.
3. Add the bounded renderer and short bootstrap route.
4. Run the deterministic suite and independent scoped review.
5. Run one approved representative canary.
6. Only after a passing canary, consider the six-case release smoke and later release matrix.

The feature remains unreleased and unverified until the required release gates pass.
