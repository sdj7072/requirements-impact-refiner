# Controller-First Impact Refinement Design

## Status

Approved in conversation on 2026-08-23 after four bounded smoke attempts exposed a structural limit in the skill-only compact workflow. This design amends `2026-08-23-compact-impact-delivery-design.md`; unchanged compact state, rendering, storage, lineage, and performance requirements remain authoritative.

## Evidence for the Change

The compact implementation produced short validated outputs and reduced routed reference words, but fresh installed-plugin smoke runs showed that a model can stop after a clarification question without creating state. Prose changes fixed canonical-lineage selection, captured-report scoring, and workflow entry boundaries. A later run still read the core skill, resolved settings, and then returned a standalone scope question rather than invoking the route, publisher, and renderer.

A pure Agent Skill cannot technically intercept or reject a model's final message. More imperative wording therefore cannot provide the promised invariant that every entered refinement yields a validated impact artifact. Enforcement requires an executable controller boundary.

## Goals

- Create a draft before the model performs impact reasoning.
- Represent a clarification as a validated pre-decision impact state, never a standalone question.
- Allocate canonical IDs and lineage metadata deterministically.
- Permit final user output only after controller validation and rendering on controller-driven paths.
- Support Codex and Claude through MCP and other Agent Skills clients through the same CLI engine.
- Keep the controller local, network-free, standard-library-only, and repository-scoped.
- Preserve the existing full-inline fallback when the controller is unavailable.

## Enforcement Boundary

The MCP path strongly structures ordinary plugin use but cannot force a host model to call a tool. Skipping the controller remains an evaluation failure and a disclosed host limitation.

The CLI path is the hard-enforcement boundary: `rir-controller finalize` exits without user output when validation fails, and only renderer output is printed on success. Public documentation must distinguish MCP structured enforcement from CLI hard enforcement.

## Components

### Controller library

`scripts/rir_controller.py` owns draft creation, normalized analysis ingestion, ID allocation, compact-state construction, publication, and response rendering. Canonical and plugin-root copies remain byte-identical.

Public interfaces:

```python
begin_refinement(request: BeginRequest) -> DraftResult
finalize_refinement(request: FinalizeRequest) -> FinalizeResult
load_draft(repo_root: Path, draft_id: str) -> Draft
```

### MCP server

`scripts/rir_mcp_server.py` implements the minimal MCP stdio JSON-RPC surface required for `initialize`, `tools/list`, and `tools/call`. It exposes exactly two tools:

- `rir_begin`
- `rir_finalize`

The server has no network client, shell execution, prompt endpoint, or arbitrary filesystem tool.

`.mcp.json` launches `./scripts/launch-rir-mcp` with `cwd: "."`. The launcher resolves its own plugin root and executes the bundled Python server. This follows the relative launcher pattern used by installed Codex plugins and avoids host-specific absolute paths.

### CLI

`scripts/rir-controller.py` exposes the same library:

```sh
python3 scripts/rir-controller.py begin --repo-root REPO --input REQUEST.json
python3 scripts/rir-controller.py finalize --repo-root REPO --draft-id DRAFT --input ANALYSIS.json
```

CLI stdout is machine-readable JSON for `begin`. Successful `finalize` stdout is renderer output only. Diagnostics use stderr. Invocation errors return 2; validation or lineage errors return 1; success returns 0.

## Begin Contract

`BeginRequest` contains:

```json
{
  "request": "concrete requested behavior",
  "repository_evidence": ["supplied evidence statement"],
  "adapter": "generic",
  "audience_override": null,
  "delivery_override": null
}
```

The controller:

1. validates the repository root and input size;
2. resolves settings;
3. loads a verified current pointer when one exists;
4. assigns or preserves `RPT-###`, revision, predecessor SHA, and `REQ-###`;
5. creates an append-only draft envelope;
6. returns a random draft ID, resolved settings, prior normalized state when present, supplied evidence, allowed enums, and the exact analysis fields required by finalize.

Begin never invents impacts or decisions. It ensures a draft exists before the model chooses whether clarification is needed.

## Draft Storage

Drafts live at:

```text
.requirements-impact-refiner/
`-- drafts/
    `-- <128-bit-lowercase-hex-id>.json
```

Draft creation uses exclusive creation and mode `0600` where supported. A draft records schema version, nonce, repository identity, request hash, creation timestamp, resolved settings, adapter, assigned report metadata, supplied evidence, and prior pointer identity. Drafts are not current reports and never affect lineage until finalize succeeds.

Drafts are single-use. Successful finalize records their consumed state. A failed finalize leaves the draft reusable only with corrected analysis. A request cannot finalize a draft from another resolved repository root.

## Finalize Contract

The model supplies normalized semantic content without canonical numeric IDs:

- refined requirement text;
- invariant rows with local keys;
- impact rows with local keys, classification, state, evidence, and summary text;
- criterion rows linked by local keys;
- either one pre-decision question with two or three options, or explicit supplied/selected decisions;
- scope, unresolved ownership, and planning workflow.

The controller deterministically assigns `INV`, `IMP`, `AC`, and `DEC` IDs in stable input order. On a revision it maps preserved local keys to prior canonical IDs and rejects silent deletion. It calculates Delta rather than accepting a model-authored Delta.

If clarification is required, finalize builds a complete `pre-decision` state whose compact renderer contains the impact summary and the question. A standalone question is not a valid `FinalizeResult`.

Finalize then runs:

1. normalized-analysis validation;
2. compact-state semantic validation;
3. deterministic Markdown rendering;
4. canonical Markdown validation against exact predecessor bytes;
5. append-only publication and pointer verification;
6. compact or full rendering from the published state.

No earlier intermediate text is suitable for the user.

## MCP Tool Results

`rir_begin` returns structured JSON content only. `rir_finalize` returns:

```json
{
  "status": "published",
  "report_id": "RPT-001",
  "revision": 1,
  "delivery": "compact",
  "display_text": "renderer-owned final response",
  "state_path": "repository-relative path",
  "markdown_path": "repository-relative path",
  "markdown_sha256": "lowercase digest"
}
```

The skill's positive recipe is: call `rir_begin`, inspect evidence, call `rir_finalize`, return `display_text` verbatim. It does not describe manual state authoring in the normal MCP path.

## Security

- Resolve and pin the repository root at begin; require the same root at finalize.
- Reject roots that are not existing directories.
- Reject traversal, external symlinks, absolute artifact paths, and non-regular files.
- Limit begin input to 256 KiB, finalize input to 2 MiB, each string to 64 KiB, and collection counts to schema-specific bounds.
- Generate draft IDs with `secrets.token_hex(16)`; never accept caller-selected IDs.
- Never deserialize Python objects, execute shell commands, access the network, or interpolate input into commands.
- Use strict UTF-8 and deterministic JSON.
- Do not store environment variables, credentials, full command output, or files outside the report/draft roots.
- Preserve existing secret scanning for evaluation evidence.

## Failure Handling

- MCP protocol errors use JSON-RPC errors without process termination when safe.
- Unknown tools, malformed params, oversized requests, invalid roots, stale drafts, cross-root drafts, and consumed drafts fail closed.
- Controller validation errors return exact bounded messages and no `display_text`.
- Publication failure cannot consume the draft or move the current pointer.
- MCP startup failure routes the skill to the existing CLI when executable access exists, otherwise to disclosed full-inline fallback.
- A model that returns text without controller finalization fails installed-plugin mechanical evaluation.

## Packaging and Compatibility

- Add `.mcp.json` and declare the companion MCP server in the Codex plugin manifest only in the supported schema shape.
- Claude discovers the root `.mcp.json` through its plugin distribution; its structural probe must confirm the server declaration before any behavioral claim.
- Generic installation copies the full canonical skill, controller library, CLI, launcher, schemas, and references. It does not assume MCP discovery.
- Existing 0.3.x Markdown and current 0.4 draft-free compact artifacts remain readable.
- The initial controller release stays `0.4.0` Public Preview until fresh evidence is sealed.

## Evaluation

Deterministic tests cover begin/finalize contracts, ID allocation, pre-decision question embedding, prior-ID preservation, automatic Delta, draft lifecycle, atomic publication, path security, size limits, MCP framing, CLI exits, and packaging.

The smoke gate is amended to require for every positive, integration, and lineage case:

- one recorded `rir_begin` tool call;
- one successful `rir_finalize` tool call;
- no user-facing agent message before finalize except a short progress update;
- raw SHA-256 for both compact `display_text` and the final response, plus an explicit exact-match boolean;
- `codex-markdown-v1` presentation equivalence for the smoke gate: normalize CRLF to LF, remove at most one terminal newline, and ignore only trailing horizontal whitespace on each line; every other byte difference fails;
- captured state/Markdown parity;
- exact six-case coverage, attempt 1, no retries;
- median compact output at most 450 words;
- median routed guidance at least 50 percent below baseline.

Only one fresh smoke batch is run after deterministic and independent review. The 85-run evaluation remains blocked until that smoke passes. Diagnostic smoke attempts already preserved are explicitly excluded from release evidence.

## Rollout

1. Implement and verify controller library and CLI.
2. Implement MCP server, launcher, manifest, and protocol tests.
3. Rewrite the skill to the begin/finalize positive recipe.
4. Amend the harness to record tool evidence and controller-owned output.
5. Run deterministic tests and independent security/code review.
6. Run one fresh six-case smoke.
7. Continue to full evaluation and public release only on smoke PASS.
