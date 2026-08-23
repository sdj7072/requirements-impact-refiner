# Transitive Impact Graph Design

## Status

Proposed on 2026-08-24. This design extends the approved controller-first impact refinement architecture. Implementation is blocked until user review approves this written specification.

## Problem

A change requested at surface `A` can preserve its direct tests while breaking apparently unrelated consumers `C`, data paths `D`, or operational behavior `Z`. Requirements Impact Refiner currently forces impacts, invariants, relationships, and regression criteria into a validated report, but discovery of those remote surfaces depends primarily on model-led repository exploration. That is too variable, token-heavy, and slow for the project's central promise.

The system needs a bounded, evidence-producing graph phase that discovers direct and transitive relationships before semantic impact analysis. It must normally finish near 10 seconds, never intentionally exceed a 30-second graph budget, reuse existing code-intelligence installations without silently installing anything, and disclose unexplored frontiers instead of claiming safety.

## Goals

- Trace `A → A-1/A-2 → C → D → Z` through inspectable repository evidence.
- Cover calls, references, implementations, imports, data keys, serialization, persistence, caches, events, authorization, configuration, operations, and tests.
- Prefer precise existing graphs, then structural evidence, then bounded lexical fallback.
- Make every reported indirect impact cite at least one normalized path and source location.
- Require an explicit `unknown` frontier when time, tools, freshness, or repository scope prevents closure.
- Keep median graph discovery at or below 10 seconds and enforce a hard 30-second graph deadline.
- Cache graph receipts and incrementally revisit only changed nodes on later revisions.
- Keep the LLM focused on interpreting a compact graph receipt instead of repeatedly reading whole files.
- Preserve local-only execution, no implicit installation, and honest compatibility claims.

## Non-Goals

- Building a new compiler, universal language server, or full code-property-graph engine.
- Guaranteeing that static analysis proves runtime behavior.
- Cold-indexing Joern or a language SCIP indexer inside the normal 30-second path.
- Automatically downloading, installing, authenticating, or updating external providers.
- Uploading source, indexes, telemetry, or repository metadata.
- Treating a missing provider as proof that no indirect impact exists.
- Replacing repository-native tests or human review for critical changes.

## Chosen Architecture

The controller gains a third operation, `rir_trace_impact`, backed by a provider-neutral graph coordinator. The operation runs after `rir_begin` and before `rir_finalize`:

```text
rir_begin
  -> rir_trace_impact
       -> provider discovery
       -> existing semantic graph
       -> structural and lexical reconciliation
       -> persisted graph receipt
  -> model interprets compact receipt
  -> rir_finalize(graph_receipt_id, analysis)
```

The coordinator owns the monotonic deadline, provider selection, output limits, cache identity, graph normalization, path ranking, and receipt persistence. The model never selects an executable path, constructs provider commands, or claims provider coverage from prose.

## Provider Layers

### Built-in bounded scanner

Always available and standard-library-only. It extracts seed symbols, paths, API fields, data keys, configuration keys, event names, and relevant test names from the request and supplied evidence. It scans bounded regular files while ignoring common generated, vendor, VCS, binary, and oversized paths. It produces conservative edges for:

- file/import and module relationships;
- literal symbol and reference occurrences;
- shared API, JSON, database, cache, event, permission, and configuration keys;
- source-to-test naming and fixture relationships;
- repository metadata that names build, deployment, schema, or migration consumers.

These edges are labelled `lexical` or `structural-inferred`; they are never presented as compiler-resolved calls.

### CodeGraph provider

Preferred when an existing, healthy, fresh CodeGraph installation exposes a supported read-only CLI or MCP-backed receipt that can be independently verified. The adapter uses semantic ownership, call, reference, and project-scope paths. CodeGraph telemetry is disabled for approved checks unless the user separately opted in. The existing Apache-2.0 `codegraph-ast-grep` Agent Skill may be recommended for explicit setup, update, or diagnosis, but is not bundled or automatically invoked as an installer.

The CodeGraph product/distribution license is verified for the exact selected installation channel before public installation guidance. An unknown or incompatible license disables the adapter without disabling the built-in scanner.

### SCIP provider

Consumes an existing fresh `index.scip` and an installed compatible reader. It is used for exact definition, reference, implementation, and cross-file symbol relationships. Provider metadata records the indexer, version, project root, source revision/fingerprint, and index age. The normal path never starts a cold language indexer. SCIP protocol and major Java/TypeScript indexers are Apache-2.0; the Python indexer is Pyright-derived MIT. Exact installed artifacts remain subject to license/provenance checks.

### ast-grep provider

Uses an existing MIT-licensed ast-grep CLI for bounded structural searches after seed syntax is known. It supplements semantic providers and the built-in scanner; it does not claim type, call, taint, or runtime proof. Commands are read-only, language-explicit where needed, path-bounded, output-capped, and executed without a shell.

### Joern provider

Optional `deep` provider for existing fresh Joern Code Property Graphs. Joern is Apache-2.0 and can expose AST, call, control-flow, and data-flow relationships across supported languages, but its JDK 21/runtime and indexing cost make it unsuitable for cold default analysis. Normal mode uses it only when a compatible graph is already ready and the query fits the remaining deadline. Cold parsing requires an explicit user-selected Deep workflow outside the normal automatic path.

## Provider Discovery and Installation Policy

Default policy is `detect-only`:

- Never install or update a provider automatically.
- Never run pipe-to-shell installers.
- Detect only fixed provider names or user-configured absolute executable paths.
- Resolve an executable to a regular trusted file, record its digest/version, and reject unsafe or changing paths.
- Use a minimal environment without credentials, tokens, proxy variables, or inherited telemetry configuration.
- Do not connect to a remote Sourcegraph, CodeGraph, Joern, or other service in automatic mode.
- When no compatible external provider exists, continue with built-in scanning and disclose reduced precision.
- Installation guidance appears only after explicit user approval and is owned by the provider's setup skill or official installer documentation.

## Time and Token Budget

The graph coordinator uses a monotonic deadline and stops scheduling work when remaining time cannot cover its bounded timeout.

| Phase | Target window | Work |
| --- | ---: | --- |
| Seed | 0–3 s | request/evidence terms, changed paths, cached receipt lookup |
| Precise graph | 3–8 s | fresh CodeGraph/SCIP/Joern queries already ready |
| Structural expansion | 8–15 s | ast-grep and built-in high-risk neighbor discovery |
| Critical frontier | 15–30 s | only unresolved high/critical paths |

The 30-second value is a ceiling, not a target. A closed frontier returns immediately. Default limits are also enforced for files, bytes, nodes, edges, paths, provider output, and subprocess count. The receipt contains timings per phase and provider.

The LLM receives only ranked paths, compact node summaries, bounded source excerpts, and the remaining unknown frontier. Raw provider output stays out of the prompt and is persisted only when safe and needed for audit. Later revisions reuse the cache and invalidate only nodes whose source digest or provider identity changed.

## Settings

`.requirements-impact-refiner.json` gains an optional object:

```json
{
  "impact_graph": {
    "enabled": true,
    "max_seconds": 30,
    "target_seconds": 10,
    "providers": ["auto"],
    "install_policy": "never",
    "deep": false
  }
}
```

Rules:

- `max_seconds` defaults to 30 and cannot exceed 30 in automatic mode.
- `target_seconds` defaults to 10 and cannot exceed `max_seconds`.
- `providers: ["auto"]` selects healthy existing providers in deterministic priority order.
- Explicit provider lists constrain discovery; they do not install missing tools.
- `install_policy` is initially only `never`; future installation flows require a separate approved design.
- `deep: true` allows queries against an existing deep graph but does not authorize cold indexing.
- Invalid settings fall back to the disclosed defaults and add a configuration warning.

## Normalized Graph Model

Each node has:

- stable receipt-local key;
- kind: symbol, file, API field, data key, schema, database, cache, event, permission, configuration, operation, or test;
- repository-relative source location when available;
- provider and provider confidence;
- source digest/freshness identity;
- risk domains.

Each edge has:

- source and target keys;
- type: calls, references, implements, imports, reads, writes, serializes, persists, caches, publishes, subscribes, authorizes, configures, deploys, or tests;
- evidence location and compact excerpt/digest;
- evidence level: verified-provider, verified-source, structural-inferred, or lexical;
- provider identity and freshness.

Paths are ranked by severity domain, edge confidence, distance, source freshness, and whether they cross a boundary such as API-to-client, service-to-cache, event-to-consumer, or permission-to-data.

## Graph Receipt

Receipts live under:

```text
.requirements-impact-refiner/graph/
  <draft-id>.json
```

They are private draft artifacts, mode `0600`, repository-bound, size-limited, and immutable after finalize. A receipt records:

- draft and repository identity;
- request/evidence hashes;
- provider inventory, versions, executable/index digests, freshness, and status;
- normalized nodes, edges, ranked paths, and source evidence;
- explored and unexpanded frontier;
- elapsed timings and budget exhaustion reason;
- cache hits and invalidations;
- receipt SHA-256.

`rir_trace_impact` returns a compact view plus the receipt ID and digest. It never returns entire indexes or unbounded source output.

## Controller Enforcement

`rir_finalize` requires the graph receipt ID produced for the same draft. Analysis impacts gain receipt-local `graph_path_keys`. The controller enforces:

- every direct or indirect impact links to at least one valid graph path, or is explicitly marked as supplied-only/unknown with rationale;
- every high/critical graph node is covered by an impact, an existing invariant, or an unknown frontier entry;
- graph paths resolve to known receipt nodes and edges;
- provider confidence is not upgraded by the model;
- unexplored high-risk frontier cannot disappear;
- `resolved` cannot rely solely on lexical or unknown evidence;
- the compact scope contains provider coverage, elapsed time, and unknown-frontier disclosure;
- receipt identity and digest are bound to the published report revision and evaluation evidence.

Clarification remains a complete pre-decision report. Missing tools or budget exhaustion do not produce a standalone question; they produce an impact report with visible unknowns.

## User-Facing Output

Compact output remains friendly and short. Each impact explains:

- changed feature;
- what might break;
- affected component/user;
- evidence path such as `A → event → consumer C → cache D → test Z`;
- trigger;
- prevention or regression test;
- evidence confidence.

The footer reports graph coverage in one concise line, for example:

```text
Impact scan: 8.4 s · CodeGraph + ast-grep · 14 nodes / 17 edges · 2 unknown frontiers
```

Full reports and graph receipts retain complete paths. The interface never claims “no impact” without a closed frontier and inspectable evidence.

## Cache and Revision Behavior

Cache identity includes repository root, source digests, provider/version/digest, provider configuration, and graph schema version. Cache files never include credentials or provider telemetry identifiers. On a later revision:

1. load the predecessor receipt;
2. invalidate changed or missing source nodes and their dependent paths;
3. query only the invalidated frontier;
4. preserve stable graph keys where evidence identity is unchanged;
5. calculate impact Delta through the existing controller lineage.

Stale, mismatched-root, provider-changed, symlinked, malformed, or digest-invalid cache entries are rejected and rebuilt within the remaining budget.

## Security and Failure Handling

- No shell interpolation; provider commands use fixed executable plus validated argv.
- No network provider is called in automatic mode.
- Provider processes have per-call and shared deadlines, bounded stdout/stderr, a minimal environment, repository cwd, and process-group termination on timeout.
- Provider output is untrusted: strict UTF-8/JSON or provider-specific parsing, schema validation, path confinement, and secret scanning apply.
- Provider failure degrades to another provider or built-in scanning and remains visible in the receipt.
- A timeout returns `budget_exhausted`, persists the frontier, and never converts unknown nodes to safe.
- Unsafe executable/index paths fail closed for that provider.
- The coordinator does not run provider rewrites, fixes, uploads, watchers, servers, authentication, or installation.
- Source excerpts and public evidence are bounded and secret-scanned.

## Compatibility

- Codex and Claude plugin modes expose `rir_trace_impact` through the existing local MCP server.
- Generic Agent Skills clients use an equivalent `rir-controller trace` CLI.
- Clients without executable access retain the existing full-inline fallback, disclose that deterministic graph enforcement is unavailable, and cannot claim graph-verified coverage.
- Existing 0.3.x/0.4 reports remain readable. Graph receipts are required only for reports created after the graph feature is activated.
- Provider support claims are per exact provider/version/platform evidence, not inferred from protocol compatibility.
- The release remains Public Preview until deterministic tests, a bounded installed-plugin smoke, and independent evidence review pass.

## Evaluation

Deterministic fixtures include distant breakages that text adjacency misses:

- API field → mobile decoder → persisted cache → migration fixture;
- authorization helper → default role → audit event → downstream consumer;
- event publisher → retry queue → idempotency store → billing/notification side effect;
- schema key → serializer → database/backfill → export/report;
- configuration flag → deployment manifest → worker startup → health check.

Tests require:

- exact A-to-C/D/Z paths with evidence and stable keys;
- no fabricated provider precision;
- provider disagreement reconciliation;
- missing/stale provider fallback;
- cold-index prohibition;
- no installation/network/telemetry side effects;
- cache hit, invalidation, root isolation, symlink rejection, and digest binding;
- deadline behavior under a fake monotonic clock;
- bounded output and provider process termination;
- high-risk frontier preservation;
- finalize rejection for uncovered high/critical nodes;
- friendly compact output and complete full receipt;
- median live graph time at or below 10 seconds and every automatic graph phase at or below 30 seconds on the approved smoke corpus.

The existing six-case controller smoke remains historical evidence for the pre-graph controller. A new graph-specific smoke must pass before the 85-run Public Preview evaluation continues.

## Rollout

1. Implement normalized receipt/domain validation and built-in scanner.
2. Add provider protocol, detection, deadline, and cache coordinator.
3. Add ast-grep, CodeGraph, SCIP, and existing-Joern adapters behind detect-only policy.
4. Add MCP/CLI trace operation and finalize receipt binding.
5. Add compact coverage/path rendering and multilingual documentation.
6. Run deterministic security/code review.
7. Install an isolated plugin snapshot and run graph-specific smoke.
8. Continue the 85-run evaluation only after every controller, semantic, graph, security, and performance gate passes.

## Design Decisions

- Existing providers are collaborators, not bundled dependencies.
- Automatic installation is forbidden.
- A fresh exact graph is preferred, but structural/lexical fallback keeps the plugin usable.
- The 30-second limit is a hard graph ceiling; target latency is 10 seconds.
- Unknown frontiers are first-class output, not silent omissions.
- Provider evidence and model interpretation remain separate and independently auditable.
