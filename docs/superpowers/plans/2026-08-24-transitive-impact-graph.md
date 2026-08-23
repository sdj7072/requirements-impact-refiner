# Transitive Impact Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local, provider-neutral, 30-second impact graph phase that finds and proves direct and transitive `A → C → D → Z` risks before impact finalization.

**Architecture:** `rir_trace_impact` coordinates a standard-library built-in scanner with detect-only external providers, normalizes their evidence into a private graph receipt, and binds that receipt to `rir_finalize`. The LLM receives only ranked compact paths and an explicit unknown frontier; the controller owns deadlines, provider provenance, cache identity, coverage enforcement, and receipt publication.

**Tech Stack:** Python 3 standard library, JSON/JSON-RPC 2.0, existing MCP/CLI controller, optional existing CodeGraph/SCIP/ast-grep/Joern executables, `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-24-transitive-impact-graph-design.md`

## Global Constraints

- Automatic graph target is median/normal target 10 seconds and hard ceiling 30 seconds.
- No provider installation, update, authentication, remote endpoint, upload, watcher, telemetry, rewrite, or cold indexing.
- External provider execution uses fixed validated argv without a shell, a minimal credential-free environment, bounded output, and the shared monotonic deadline.
- A missing, stale, unsafe, unsupported, or failed provider degrades to built-in scanning and remains visible.
- Every indirect impact needs a valid receipt path or an explicit supplied-only/unknown rationale.
- Every uncovered high/critical frontier remains visible and prevents a false closed-coverage claim.
- Existing reports remain readable; graph enforcement applies only to drafts whose resolved settings enable it.
- Canonical skill files and plugin-root fallback mirrors remain byte-identical.
- No 85-run evaluation or release action begins before deterministic review and a fresh graph smoke pass.

---

### Task 1: Graph Settings, Domain Model, and Receipt Schema

**Files:**
- Create: `skills/requirements-impact-refiner/scripts/impact_graph.py`
- Create: `scripts/impact_graph.py`
- Create: `skills/requirements-impact-refiner/schemas/impact-graph-receipt.schema.json`
- Create: `schemas/impact-graph-receipt.schema.json`
- Modify: `skills/requirements-impact-refiner/scripts/resolve-settings.py`
- Modify: `scripts/resolve-settings.py`
- Create: `tests/fixtures/impact-graph-receipt.json`
- Create: `tests/test_impact_graph.py`
- Modify: `tests/test_presentation_settings.py`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Produces `GraphSettings`, `ProviderStatus`, `GraphNode`, `GraphEdge`, `GraphPath`, `FrontierEntry`, `GraphReceipt`, `load_receipt_bytes()`, `validate_receipt()`, and `canonical_receipt_bytes()`.
- Extends resolved settings with `impact_graph.enabled`, `max_seconds`, `target_seconds`, `providers`, `install_policy`, and `deep`.

- [ ] **Step 1: Write failing settings and receipt tests**

```python
def test_graph_defaults_are_fast_detect_only(self):
    resolved = SETTINGS.resolve(self.root, None, None)
    self.assertEqual(resolved["impact_graph"], {
        "enabled": True,
        "max_seconds": 30,
        "target_seconds": 10,
        "providers": ["auto"],
        "install_policy": "never",
        "deep": False,
    })

def test_receipt_requires_path_evidence_and_unknown_frontier(self):
    value = fixture("impact-graph-receipt.json")
    self.assertEqual(GRAPH.validate_receipt(value), ())
    value["paths"][0]["edges"] = ["EDGE-999"]
    self.assertIn("unknown graph edge EDGE-999", GRAPH.validate_receipt(value))
```

Also cover unknown keys, invalid enums, `target_seconds > max_seconds`, automatic `max_seconds > 30`, duplicate IDs, unsafe/absolute paths, unknown node/edge/path references, provider confidence upgrades, missing receipt SHA input fields, and collection/string/byte limits.

- [ ] **Step 2: Run RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-graph-task1-red python3 -m unittest tests.test_impact_graph tests.test_presentation_settings tests.test_packaging -v
```

Expected: missing `impact_graph` module/schema and missing settings fields.

- [ ] **Step 3: Implement immutable graph domain and strict schema**

Use frozen dataclasses with tuple collections. Required receipt shape:

```json
{
  "schema_version": 1,
  "receipt_id": "32 lowercase hex",
  "draft_id": "32 lowercase hex",
  "repo_root_sha256": "64 lowercase hex",
  "request_sha256": "64 lowercase hex",
  "settings": {},
  "providers": [],
  "nodes": [],
  "edges": [],
  "paths": [],
  "frontier": [],
  "timings_ms": {},
  "budget_status": "closed|budget_exhausted|provider_limited|no_workspace",
  "cache": {"status":"miss|hit|partial", "key":"64 lowercase hex", "invalidated_nodes":[]}
}
```

Node IDs use `NODE-001`, edges `EDGE-001`, paths `PATH-001`. Source paths are repository-relative POSIX paths. Confidence is `verified-provider`, `verified-source`, `structural-inferred`, or `lexical`. Provider status is `ready`, `missing`, `stale`, `unsafe`, `unsupported`, `failed`, or `timed_out`.

- [ ] **Step 4: Implement graph settings resolution**

Accept only the exact fields in the spec. Repository values are type-checked before normalization. Invalid graph configuration returns the six defaults above plus a warning; request overrides remain limited to the existing audience/delivery interface in this release.

- [ ] **Step 5: Verify GREEN and mirrors**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-graph-task1-green python3 -m unittest tests.test_impact_graph tests.test_presentation_settings tests.test_packaging -v
cmp skills/requirements-impact-refiner/scripts/impact_graph.py scripts/impact_graph.py
cmp skills/requirements-impact-refiner/schemas/impact-graph-receipt.schema.json schemas/impact-graph-receipt.schema.json
cmp skills/requirements-impact-refiner/scripts/resolve-settings.py scripts/resolve-settings.py
```

- [ ] **Step 6: Commit**

```sh
git add skills/requirements-impact-refiner/scripts/impact_graph.py scripts/impact_graph.py skills/requirements-impact-refiner/schemas/impact-graph-receipt.schema.json schemas/impact-graph-receipt.schema.json skills/requirements-impact-refiner/scripts/resolve-settings.py scripts/resolve-settings.py tests/fixtures/impact-graph-receipt.json tests/test_impact_graph.py tests/test_presentation_settings.py tests/test_packaging.py
git commit -m "feat: add transitive impact graph contract"
```

---

### Task 2: Built-In Scanner, Deadline, and Incremental Cache

**Files:**
- Create: `skills/requirements-impact-refiner/scripts/graph_builtin.py`
- Create: `scripts/graph_builtin.py`
- Create: `skills/requirements-impact-refiner/scripts/graph_cache.py`
- Create: `scripts/graph_cache.py`
- Create: `tests/fixtures/graph-project/api/profile.py`
- Create: `tests/fixtures/graph-project/mobile/user_dto.swift`
- Create: `tests/fixtures/graph-project/desktop/profile_cache.ts`
- Create: `tests/fixtures/graph-project/events/profile_changed.py`
- Create: `tests/fixtures/graph-project/tests/test_profile_migration.py`
- Create: `tests/test_graph_builtin.py`
- Create: `tests/test_graph_cache.py`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Produces `ScanSeed`, `ScanLimits`, `BuiltInScanResult`, `scan_repository(repo_root, seeds, limits, clock)`, `GraphCache.load()`, `GraphCache.publish()`, and `GraphCache.invalidate()`.
- Consumes Task 1 graph dataclasses and canonical JSON helpers.

- [ ] **Step 1: Write failing distant-impact scanner tests**

```python
def test_shared_field_discovers_mobile_desktop_event_and_migration_test(self):
    result = BUILTIN.scan_repository(
        FIXTURE_ROOT,
        (BUILTIN.ScanSeed("profile.displayName", "api/profile.py"),),
        BUILTIN.ScanLimits(max_seconds=30, max_files=500, max_bytes=8_000_000),
        FakeClock(),
    )
    locations = {node.location for node in result.nodes}
    self.assertTrue({
        "api/profile.py", "mobile/user_dto.swift",
        "desktop/profile_cache.ts", "events/profile_changed.py",
        "tests/test_profile_migration.py",
    } <= locations)
    self.assertTrue(any(path.distance >= 3 for path in result.paths))
```

Cover ignored `.git`, vendor/build/generated paths, binaries, oversized files, traversal/symlink rejection, invalid UTF-8, file/byte/node/edge/path limits, stable deterministic IDs, empty repositories, supplied-only seeds, duplicate terms, risk-domain ranking, and immediate stop when `clock.monotonic() >= deadline`.

- [ ] **Step 2: Run scanner RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-graph-task2-red python3 -m unittest tests.test_graph_builtin -v
```

- [ ] **Step 3: Implement bounded scanner**

Enumerate regular files deterministically. Extract identifier-like tokens, dotted keys, slash paths, quoted data/config/event strings, imports, and test/fixture naming relationships. Create only evidence-labelled lexical/structural-inferred edges. Read at most 1 MiB per file, 8 MiB total by default, and check the monotonic deadline before every directory, file, and frontier expansion.

- [ ] **Step 4: Write cache RED tests**

```python
def test_cache_reuses_unchanged_nodes_and_invalidates_dependents(self):
    first = CACHE.publish(self.root, receipt, source_digests)
    loaded = CACHE.load(self.root, first.key, source_digests)
    self.assertEqual(loaded.status, "hit")
    changed = {**source_digests, "desktop/profile_cache.ts": "f" * 64}
    partial = CACHE.load(self.root, first.key, changed)
    self.assertEqual(partial.status, "partial")
    self.assertIn("NODE-003", partial.invalidated_nodes)
```

Cover provider/version/config/schema key changes, root mismatch, missing source, corrupt digest, malformed JSON, symlink, partial temporary file, atomic pointer update, mode `0600`, and no credential/environment persistence.

- [ ] **Step 5: Implement private incremental cache**

Store under `.requirements-impact-refiner/cache/graph/v1/<key>.json`, using exclusive private files and atomic pointer replacement. Cache identity hashes graph settings, root identity, provider identities, and source digests. Invalidation walks dependent receipt paths from changed nodes without rescanning unrelated files.

- [ ] **Step 6: Verify and commit**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-graph-task2-green python3 -m unittest tests.test_graph_builtin tests.test_graph_cache tests.test_impact_graph tests.test_packaging -v
cmp skills/requirements-impact-refiner/scripts/graph_builtin.py scripts/graph_builtin.py
cmp skills/requirements-impact-refiner/scripts/graph_cache.py scripts/graph_cache.py
git add skills/requirements-impact-refiner/scripts/graph_builtin.py scripts/graph_builtin.py skills/requirements-impact-refiner/scripts/graph_cache.py scripts/graph_cache.py tests/fixtures/graph-project tests/test_graph_builtin.py tests/test_graph_cache.py tests/test_packaging.py
git commit -m "feat: scan and cache indirect impact paths"
```

---

### Task 3: Provider Runner, Detection, and Coordination

**Files:**
- Create: `skills/requirements-impact-refiner/scripts/graph_providers.py`
- Create: `scripts/graph_providers.py`
- Create: `skills/requirements-impact-refiner/scripts/graph_coordinator.py`
- Create: `scripts/graph_coordinator.py`
- Create: `tests/test_graph_providers.py`
- Create: `tests/test_graph_coordinator.py`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Produces `ProviderSpec`, `ProviderProbe`, `ProviderQuery`, `ProviderResult`, `Deadline`, `run_provider()`, `discover_providers()`, and `trace_impact()`.
- `trace_impact(repo_root, draft, seeds, settings, clock, runner) -> GraphReceipt` consumes Task 1/2 contracts.

- [ ] **Step 1: Write provider security RED tests**

```python
def test_runner_uses_fixed_argv_minimal_environment_and_shared_deadline(self):
    result = PROVIDERS.run_provider(
        ProviderSpec("ast-grep", executable=self.fake_binary),
        ("--version",), self.repo, Deadline(self.clock, 30),
        runner=self.runner,
    )
    self.assertEqual(result.argv, (str(self.fake_binary), "--version"))
    self.assertEqual(result.environment, {
        "PATH": str(self.fake_binary.parent),
        "CODEGRAPH_TELEMETRY": "0",
        "NO_COLOR": "1",
    })
```

Cover no shell, no inherited tokens/proxies/home, executable regular-file identity, user-configured absolute paths, PATH discovery, symlink/change race, executable digest/version, timeout/process-group termination, 4 MiB stdout and 256 KiB stderr caps, non-UTF-8, malformed JSON, nonzero exit, unsupported help, and provider status preservation.

- [ ] **Step 2: Run provider RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-graph-task3-red python3 -m unittest tests.test_graph_providers -v
```

- [ ] **Step 3: Implement runner and detect-only discovery**

Only fixed names `codegraph`, `scip`, `sg`/`ast-grep`, and `joern` are auto-discovered. Configured paths must be absolute. Probe commands are exact `--version` and bounded `--help`; no provider server, login, watcher, upload, install, parse, or index command is allowed during discovery.

- [ ] **Step 4: Write coordinator RED tests**

```python
def test_coordinator_stops_closed_frontier_without_spending_30_seconds(self):
    receipt = COORDINATOR.trace_impact(
        self.root, self.draft, self.seeds, self.settings,
        clock=self.clock, runner=self.runner,
    )
    self.assertEqual(receipt.budget_status, "closed")
    self.assertLess(receipt.timings_ms["total"], 10_000)

def test_budget_exhaustion_preserves_high_risk_frontier(self):
    self.clock.advance_to(30.0)
    receipt = COORDINATOR.trace_impact(
        self.root,
        self.draft,
        (COORDINATOR.ScanSeed("profile.displayName", "api/profile.py"),),
        self.settings,
        clock=self.clock,
        runner=self.runner,
    )
    self.assertEqual(receipt.budget_status, "budget_exhausted")
    self.assertTrue(any(item.severity in {"critical", "high"} for item in receipt.frontier))
```

Cover deterministic provider priority, provider disagreement, cache hit/partial/miss, no workspace, supplied-only evidence, high-risk-first scheduling, no work after deadline, provider failure fallback, compact output limits, receipt atomic persistence, and receipt mode `0600`.

- [ ] **Step 5: Implement coordinator and verify**

Schedule cached precise providers before built-in/structural expansion, but return immediately when the frontier closes. Rank high/critical boundary crossings first. Persist the receipt at `.requirements-impact-refiner/graph/<draft-id>.json` and verify its digest after reopening.

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-graph-task3-green python3 -m unittest tests.test_graph_providers tests.test_graph_coordinator tests.test_graph_builtin tests.test_graph_cache -v
cmp skills/requirements-impact-refiner/scripts/graph_providers.py scripts/graph_providers.py
cmp skills/requirements-impact-refiner/scripts/graph_coordinator.py scripts/graph_coordinator.py
```

- [ ] **Step 6: Commit**

```sh
git add skills/requirements-impact-refiner/scripts/graph_providers.py scripts/graph_providers.py skills/requirements-impact-refiner/scripts/graph_coordinator.py scripts/graph_coordinator.py tests/test_graph_providers.py tests/test_graph_coordinator.py tests/test_packaging.py
git commit -m "feat: coordinate bounded graph providers"
```

---

### Task 4: ast-grep, CodeGraph, SCIP, and Joern Adapters

**Files:**
- Create: `skills/requirements-impact-refiner/scripts/graph_adapter_ast_grep.py`
- Create: `scripts/graph_adapter_ast_grep.py`
- Create: `skills/requirements-impact-refiner/scripts/graph_adapter_codegraph.py`
- Create: `scripts/graph_adapter_codegraph.py`
- Create: `skills/requirements-impact-refiner/scripts/graph_adapter_scip.py`
- Create: `scripts/graph_adapter_scip.py`
- Create: `skills/requirements-impact-refiner/scripts/graph_adapter_joern.py`
- Create: `scripts/graph_adapter_joern.py`
- Create: `tests/fixtures/providers/ast-grep-query.json`
- Create: `tests/fixtures/providers/codegraph-explore.json`
- Create: `tests/fixtures/providers/scip-print.json`
- Create: `tests/fixtures/providers/joern-query.json`
- Create: `tests/test_graph_adapters.py`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Each module produces `probe(spec, root, deadline, runner) -> ProviderProbe` and `query(probe, seeds, deadline, runner) -> ProviderResult`.
- Provider results contain only normalized candidate nodes/edges and raw receipt digests; Task 3 coordinator assigns canonical graph IDs.

- [ ] **Step 1: Write adapter RED fixtures/tests**

```python
def test_scip_print_json_maps_definitions_and_references(self):
    result = SCIP.query(self.scip_probe, self.seeds, self.deadline, self.runner)
    self.assertIn(("api/profile.py", "desktop/profile_cache.ts", "references"), edge_tuples(result))

def test_joern_never_cold_parses_in_automatic_mode(self):
    probe = JOERN.probe(self.joern_spec, self.root, self.deadline, self.runner)
    self.assertEqual(probe.status, "stale")
    self.assertNotIn("joern-parse", flatten_argv(self.runner.calls))
```

Tests use complete version/help/query fixtures and cover malicious paths, root mismatch, stale index/graph fingerprints, unsupported versions/options, JSON shape drift, source ranges, duplicate relationships, provider confidence, output truncation, and no write/upload/index command.

- [ ] **Step 2: Run adapter RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-graph-task4-red python3 -m unittest tests.test_graph_adapters -v
```

- [ ] **Step 3: Implement exact read-only adapter contracts**

- ast-grep 0.45.x: require help-confirmed JSON output and run bounded `sg --json=stream --lang <language> --pattern <pattern> <relative-path>` queries only.
- CodeGraph: require installed-help-confirmed `status`/`explore` JSON capabilities, exact-root project identity, freshness, and `CODEGRAPH_TELEMETRY=0`; otherwise mark unsupported.
- SCIP: require repository-local regular `index.scip`, matching project root/freshness, and installed `scip print --json <index>` support. Parse only bounded JSON documents/occurrences/symbol roles and never invoke an indexer or upload.
- Joern: require an existing repository-local graph with matching source fingerprint and installed JSON/export query support. Never invoke `joern-parse`, server, install, or interactive mode.

- [ ] **Step 4: Reconcile semantic and structural disagreement**

Precise provider edges retain `verified-provider`; ast-grep disagreement creates a frontier entry instead of deleting either observation. Targeted built-in source evidence may upgrade a matching structural edge only to `verified-source`, never to compiler-resolved precision.

- [ ] **Step 5: Verify mirrors and commit**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-graph-task4-green python3 -m unittest tests.test_graph_adapters tests.test_graph_providers tests.test_graph_coordinator -v
for name in ast_grep codegraph scip joern; do cmp "skills/requirements-impact-refiner/scripts/graph_adapter_${name}.py" "scripts/graph_adapter_${name}.py"; done
git add skills/requirements-impact-refiner/scripts/graph_adapter_*.py scripts/graph_adapter_*.py tests/fixtures/providers tests/test_graph_adapters.py tests/test_packaging.py
git commit -m "feat: add detect-only graph provider adapters"
```

---

### Task 5: Controller, MCP, and CLI Graph Enforcement

**Files:**
- Modify: `skills/requirements-impact-refiner/scripts/rir_controller.py`
- Modify: `scripts/rir_controller.py`
- Modify: `skills/requirements-impact-refiner/scripts/rir-controller.py`
- Modify: `scripts/rir-controller.py`
- Modify: `scripts/rir_mcp_server.py`
- Modify: `skills/requirements-impact-refiner/schemas/controller-analysis.schema.json`
- Modify: `schemas/controller-analysis.schema.json`
- Modify: `scripts/payload_identity.py`
- Modify: `skills/requirements-impact-refiner/scripts/payload_identity.py`
- Modify: `tests/test_rir_controller.py`
- Modify: `tests/test_rir_controller_cli.py`
- Modify: `tests/test_rir_mcp_server.py`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Adds `TraceRequest(repo_root, draft_id, seeds)` and `TraceResult(receipt_id, receipt_path, receipt_sha256, compact_graph, budget_status)`.
- Adds `trace_impact()` to `rir_controller`.
- Adds MCP tool `rir_trace_impact` and CLI command `rir-controller trace --repo-root REPO --draft-id ID --input SEEDS.json`.
- Extends finalize arguments with required `graph_receipt_id` when graph settings are enabled.
- Extends each analysis impact with `graph_path_keys` and optional `coverage_rationale`.

- [ ] **Step 1: Write controller trace RED tests**

```python
def test_trace_persists_private_receipt_bound_to_draft(self):
    draft = CONTROLLER.begin_refinement(self.request())
    traced = CONTROLLER.trace_impact(CONTROLLER.TraceRequest(
        self.root, draft.draft_id,
        (CONTROLLER.TraceSeed("profile.displayName", "api/profile.py"),),
    ))
    self.assertRegex(traced.receipt_id, r"^[0-9a-f]{32}$")
    self.assertEqual(traced.receipt_path.stat().st_mode & 0o777, 0o600)
    self.assertEqual(traced.budget_status, "closed")
```

Cover wrong/cross-root/consumed draft, duplicate trace, receipt replacement, disabled graph, unsafe repo, oversized seeds, publication failure, deadline, provider failure, receipt tampering, and exact draft/request/settings identities.

- [ ] **Step 2: Write finalize coverage RED tests**

```python
def test_finalize_rejects_uncovered_high_risk_graph_node(self):
    draft, receipt = self.traced_draft("high-risk-receipt.json")
    analysis = self.analysis()
    analysis["impacts"][0]["graph_path_keys"] = []
    with self.assertRaisesRegex(ValueError, "uncovered high-risk graph node"):
        CONTROLLER.finalize_refinement(self.finalize(draft, receipt, analysis))
```

Cover valid direct/indirect paths, supplied-only evidence with rationale, unknown frontier preservation, invalid path keys, confidence upgrades, lexical-only resolution, stale/tampered receipt, receipt/draft mismatch, graph-disabled compatibility, and scope injection with provider/time/frontier summary.

- [ ] **Step 3: Implement controller trace and finalize binding**

Import Task 1–4 modules from the fixed script directory only. Persist one immutable receipt per draft. Finalize verifies the selected receipt bytes/digest and injects graph coverage into the existing compact-state scope; compact state schema remains backward-compatible.

- [ ] **Step 4: Write MCP/CLI RED tests**

MCP lists exactly `rir_begin`, `rir_trace_impact`, `rir_finalize` in that order. Trace result content is compact JSON; finalize output remains renderer-owned. CLI trace prints canonical receipt metadata only. Cover malformed/deep/oversized input, bounded errors, continued MCP processing, exit 1 validation, exit 2 invocation/I/O, and no stdout on failed finalize.

- [ ] **Step 5: Implement MCP/CLI surface and payload binding**

Add strict recursive schemas, fixed local/network-free descriptions, and the same controller business layer. Extend payload identity to every new canonical/root graph script and schema so installed smoke cannot use stale graph code.

- [ ] **Step 6: Verify and commit**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-graph-task5-green python3 -m unittest tests.test_rir_controller tests.test_rir_controller_cli tests.test_rir_mcp_server tests.test_impact_graph tests.test_graph_builtin tests.test_graph_cache tests.test_graph_providers tests.test_graph_coordinator tests.test_graph_adapters tests.test_packaging -v
cmp skills/requirements-impact-refiner/scripts/rir_controller.py scripts/rir_controller.py
cmp skills/requirements-impact-refiner/scripts/rir-controller.py scripts/rir-controller.py
cmp skills/requirements-impact-refiner/schemas/controller-analysis.schema.json schemas/controller-analysis.schema.json
git add skills/requirements-impact-refiner/scripts/rir_controller.py scripts/rir_controller.py skills/requirements-impact-refiner/scripts/rir-controller.py scripts/rir-controller.py scripts/rir_mcp_server.py skills/requirements-impact-refiner/schemas/controller-analysis.schema.json schemas/controller-analysis.schema.json scripts/payload_identity.py skills/requirements-impact-refiner/scripts/payload_identity.py tests/test_rir_controller.py tests/test_rir_controller_cli.py tests/test_rir_mcp_server.py tests/test_packaging.py
git commit -m "feat: enforce graph receipts in controller"
```

---

### Task 6: Skill Recipe, Friendly Output, and Documentation

**Files:**
- Modify: `skills/requirements-impact-refiner/SKILL.md`
- Modify: `skills/requirements-impact-refiner/references/controller-workflow.md`
- Modify: `references/controller-workflow.md`
- Create: `skills/requirements-impact-refiner/references/transitive-impact-graph.md`
- Create: `references/transitive-impact-graph.md`
- Modify: `skills/using-requirements-impact-refiner/SKILL.md`
- Modify: `skills/requirements-impact-refiner/scripts/impact_renderer.py`
- Modify: `scripts/impact_renderer.py`
- Modify: `README.md`
- Modify: `README.ko.md`
- Modify: `README.ja.md`
- Modify: `docs/compact-delivery-demo.md`
- Modify: `assets/compact-delivery-demo.svg`
- Modify: `tests/test_documentation.py`
- Modify: `tests/test_integration_adapters.py`
- Modify: `tests/test_impact_renderer.py`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Normal recipe becomes `rir_begin → rir_trace_impact → inspect compact receipt → rir_finalize → return display_text`.
- Compact rendering adds per-impact evidence path and one coverage footer without exposing raw provider output.

- [ ] **Step 1: Run skill pressure RED scenario and write deterministic output tests**

The no-guidance baseline uses a fixture where `profile.displayName` appears in API, mobile DTO, desktop cache, event consumer, and migration test. Record whether a fresh agent finds all five surfaces, which files it reads, elapsed time, and output words. Deterministic tests require core `SKILL.md` under 340 words, exactly one occurrence of each tool name in the five-action recipe, and no manual graph JSON authoring.

```python
def test_compact_output_explains_indirect_path_and_unknown_frontier(self):
    text = RENDERER.render_compact(state_with_graph_scope())
    self.assertIn("A → profile event → desktop cache → migration test", text)
    self.assertIn("Impact scan: 8.4 s", text)
    self.assertIn("2 unknown frontiers", text)
```

- [ ] **Step 2: Run RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-graph-task6-red python3 -m unittest tests.test_documentation tests.test_integration_adapters tests.test_impact_renderer tests.test_packaging -v
```

- [ ] **Step 3: Rewrite positive recipe and references**

The model interprets only the compact receipt. It must not re-run provider searches, invent edges, suppress frontiers, or begin planning. The reference explains confidence levels, same-risk key reuse, provider disagreement, supplied-only evidence, and `unknown` handling. CLI/full-inline fallbacks remain explicit.

- [ ] **Step 4: Render friendly graph evidence**

Add one short path line per impact and a single footer. Simple mode uses plain-language component names; balanced includes component/path; technical includes provider/confidence/location. Enforce existing output budgets and HTML/Markdown escaping.

- [ ] **Step 5: Synchronize EN/KO/JA docs and demo**

Document 10-second target/30-second ceiling, detect-only policy, no auto install/network, optional providers and licenses, fallback precision, cache behavior, Deep limitations, graph receipt paths, and honest compatibility status. Keep all commands, versions, provider names, statuses, and settings identical across languages.

- [ ] **Step 6: Verify and commit**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-graph-task6-green python3 -m unittest tests.test_documentation tests.test_integration_adapters tests.test_impact_renderer tests.test_packaging -v
cmp skills/requirements-impact-refiner/references/controller-workflow.md references/controller-workflow.md
cmp skills/requirements-impact-refiner/references/transitive-impact-graph.md references/transitive-impact-graph.md
cmp skills/requirements-impact-refiner/scripts/impact_renderer.py scripts/impact_renderer.py
git add skills/requirements-impact-refiner/SKILL.md skills/requirements-impact-refiner/references/controller-workflow.md references/controller-workflow.md skills/requirements-impact-refiner/references/transitive-impact-graph.md references/transitive-impact-graph.md skills/using-requirements-impact-refiner/SKILL.md skills/requirements-impact-refiner/scripts/impact_renderer.py scripts/impact_renderer.py README.md README.ko.md README.ja.md docs/compact-delivery-demo.md assets/compact-delivery-demo.svg tests/test_documentation.py tests/test_integration_adapters.py tests/test_impact_renderer.py tests/test_packaging.py
git commit -m "docs: explain transitive impact graph workflow"
```

---

### Task 7: Graph Evaluation, Security, and Performance Gates

**Files:**
- Create: `evals/graph-cases.json`
- Create: `evals/harness/graph_scoring.py`
- Modify: `evals/harness/performance.py`
- Modify: `evals/harness/run.py`
- Modify: `evals/harness/adapters/codex.py`
- Modify: `evals/harness/controller_evidence.py`
- Modify: `evals/harness/schemas/result.schema.json`
- Create: `tests/test_graph_eval_cases.py`
- Create: `tests/test_graph_scoring.py`
- Modify: `tests/test_performance_budget.py`
- Modify: `tests/test_eval_harness_codex.py`
- Modify: `tests/test_eval_harness_cli.py`

**Interfaces:**
- Adds graph smoke suite with the five distant-breakage fixtures from the spec plus one negative non-change case.
- Produces graph coverage scores, exact receipt provenance, cache/timing observations, and a graph smoke gate.

- [ ] **Step 1: Write graph case and scoring RED tests**

Each positive case names exact required nodes, edge types, minimum path distance, forbidden fabricated precision, allowed providers, unknown-frontier expectation, and compact-output phrases. The negative case must not invoke graph/controller tools.

```python
def test_api_to_cache_case_requires_distant_path(self):
    score = score_graph(case, receipt, final_output)
    self.assertTrue(score.passed, score.findings)
    self.assertGreaterEqual(score.maximum_required_distance, 3)
```

- [ ] **Step 2: Capture raw trace/receipt provenance**

Harness evidence requires one begin, one trace, one finalize per positive/integration turn; exact draft/receipt IDs; installed payload digest; trace tool success; receipt file/digest; state/Markdown parity; exact/presentation display fields; no duplicate/error calls; and zero controller calls for the negative case.

- [ ] **Step 3: Add performance RED tests and gate**

```python
def test_graph_smoke_requires_target_and_ceiling(self):
    result = evaluate_graph_smoke(self.six_rows())
    self.assertTrue(result.passed)
    slow = replace(self.six_rows()[0], graph_duration_ms=30_001)
    self.assertIn("graph duration exceeds 30 seconds", evaluate_graph_smoke((slow,) + self.six_rows()[1:]).errors)
```

Gate exact six cases, attempt 1/no retry, runtime and mechanical pass, receipt/state/provider parity, no uncovered high-risk node, median graph duration ≤10,000 ms, every graph duration ≤30,000 ms, median output ≤450 words, and routed guidance at least 50 percent below historical baseline. Token fields remain client-reported only.

- [ ] **Step 4: Add adversarial security tests**

Cover provider executable swap, malicious output path, secret-shaped output, symlinked index/cache/receipt, deep JSON/protobuf JSON, timeout and child cleanup, output flood, stale graph, root mismatch, environment credential leak, attempted installation/network/upload/server command, receipt mutation after scoring, and manifest binding.

- [ ] **Step 5: Verify full deterministic suite and independent reviews**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-graph-task7-full python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=/tmp/rir-graph-task7-compile python3 -m compileall -q skills/requirements-impact-refiner scripts evals/harness tests
git diff --check
```

Require independent code review and bounded security diff review with no Critical or Important findings.

- [ ] **Step 6: Commit deterministic evaluation code**

```sh
git add evals/graph-cases.json evals/harness/graph_scoring.py evals/harness/performance.py evals/harness/run.py evals/harness/adapters/codex.py evals/harness/controller_evidence.py evals/harness/schemas/result.schema.json tests/test_graph_eval_cases.py tests/test_graph_scoring.py tests/test_performance_budget.py tests/test_eval_harness_codex.py tests/test_eval_harness_cli.py
git commit -m "test: gate transitive graph coverage and latency"
```

---

### Task 8: Installed Graph Smoke and Release Continuation

**Files:**
- Create after approved execution: `evals/results/installed-v0.4-graph-smoke/**`
- Create: `tests/test_installed_graph_smoke_evidence.py`
- Modify after approved evidence: `.gitattributes`
- Modify only after graph smoke and full evaluation: `README.md`, `README.ko.md`, `README.ja.md`

**Interfaces:**
- Consumes reviewed deterministic HEAD and an isolated installed plugin whose functional payload matches it.
- Produces sealed graph smoke evidence; only on PASS does it unblock the existing 85-run evaluation and Public Preview release workflow.

- [ ] **Step 1: Create a fresh isolated marketplace snapshot**

Archive the reviewed commit into a new local evaluation marketplace and use a unique marketplace/plugin ID. Verify the source, snapshot, and installed-cache functional payload SHA-256 are identical. Remove or disable the official plugin during evaluation so only one RIR skill is active. Do not reuse any diagnostic directory or cache.

- [ ] **Step 2: Run exactly one graph smoke**

```sh
python3 -m evals.harness.run \
  --client codex \
  --suite graph-smoke \
  --repetitions 1 \
  --model gpt-5.6-sol \
  --reasoning high \
  --expected-plugin-version 0.4.0 \
  --expected-rir-plugin-id requirements-impact-refiner@requirements-impact-refiner-v040-graph-eval \
  --output evals/results/installed-v0.4-graph-smoke \
  --timeout 300
```

The local evaluation marketplace name is exactly `requirements-impact-refiner-v040-graph-eval`; it must match probe evidence before any model call. Stop before the 85-run matrix unless every runtime, mechanical, graph, controller, semantic, security, and performance gate passes.

- [ ] **Step 3: Independently review and pin smoke evidence**

Require exact file inventory/digest, raw `-text -whitespace`, secret scan, provider commands/environment, installed payload identity, six attempt-1/no-retry results, graph receipt IDs/digests, source evidence, provider freshness, cache/timings, all scores, exact report re-rendering, and explicit exact/presentation display semantics.

- [ ] **Step 4: Commit approved smoke separately**

```sh
git add .gitattributes evals/results/installed-v0.4-graph-smoke tests/test_installed_graph_smoke_evidence.py
git commit -m "test: seal transitive graph smoke evidence"
```

- [ ] **Step 5: Continue existing Task 8 only on PASS**

Run the approved 85-result installed-superpowers evaluation against the same reviewed payload, complete human adjudication, add community files/metadata, update EN/KO/JA claims with exact evidence and latency numbers, run CI, merge to main, push, create `v0.4.0`, and publish a GitHub prerelease. Any failed graph or release gate keeps status `not verified` and blocks tag/release.

- [ ] **Step 6: Restore normal installation state**

Remove the evaluation alias/marketplace and reinstall the official plugin version that was active before evaluation. Read back plugin inventory; leave no duplicate RIR installation enabled.

---

## Plan Self-Review Record

- Spec coverage: graph model, built-in fallback, four provider layers, detect-only policy, deadline, cache, receipt, controller enforcement, friendly output, compatibility, security, evaluation, and rollout map to Tasks 1–8.
- Type consistency: receipt/node/edge/path/provider/settings names originate in Task 1; later tasks consume those exact names. Controller trace and evaluation fields are introduced once and reused consistently.
- Dependency order: domain → scanner/cache → coordinator → provider adapters → controller → skill/docs → evaluation → live evidence.
- Scope: provider installation and cold indexing remain excluded; release work is conditional on graph smoke PASS.
- Placeholder scan: clean; every interface, command, fixture, and evaluation marketplace identity is concrete.
