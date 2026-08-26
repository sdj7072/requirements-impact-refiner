# v0.6 Instant Report Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return a same-lineage completed report immediately, skip exact-repeat work, and revalidate changed repositories within a three-second default while preserving indirect-impact frontiers and bounded token input.

**Architecture:** Immutable report context sidecars bind repository, requirement, source, payload, and revision identities. A new previous-report lookup runs before Fast Scan; exact clean matches stop, while stale matches seed a bounded delta scan from changed files, prior paths, and preserved invariants. Runtime metrics are semantic data consumed later by the localized UX plan.

**Tech Stack:** Python 3.9 standard library; existing controller/storage/graph modules; JSON Schema; MCP JSON-RPC; unittest; existing root/installed-skill mirrors.

**Spec:** `docs/superpowers/specs/2026-08-25-v0.6-instant-report-performance-design.md`

## Global Constraints

- Complete the quality-foundation and controller/graph architecture plans first.
- Default runtime is standard-library-only, network-free, and installs no provider automatically.
- Previous content is reusable only when repository, requirement lineage, report revision, payload, and schema identities validate.
- A result is `fresh` only when the implementation proves it; timeout, missing Git, dirty ambiguity, or incomplete source proof is `stale`. Missing v2 context is `none` with no body.
- Previous lookup p95 is at most 300ms; stale delta scan p95 is at most 3 seconds on pinned fixtures.
- An exact fresh match performs zero provider, graph, and LLM calls.
- Delta scanning preserves changed files, previous selected paths, preserved invariants, and every unknown frontier.
- Root and installed-skill copies of shipped skill scripts remain byte-identical; `rir_mcp_server.py` remains plugin-root-only.
- Python 3.9, 3.11, and 3.13 behavior remains supported.

---

### Task 1: Persist immutable report context

**Files:**
- Create: `scripts/rir_report_context.py`
- Create: `skills/requirements-impact-refiner/scripts/rir_report_context.py`
- Modify: `scripts/rir_finalize.py`
- Modify: installed-skill mirror
- Modify: `scripts/rir_storage.py`
- Modify: installed-skill mirror
- Test: `tests/test_rir_report_context.py`

**Interfaces:**
- Produces: v2 `ReportContext`, requirement/evidence/state/source identities, `publish_report_context(root: Path, context: ReportContext) -> Path`, `load_report_context(root: Path, report_id: str, revision: int) -> Optional[ReportContext]`
- Consumes: validated report ID/revision, immutable Markdown digest, payload digest, graph source-inventory digest, optional Git baseline

- [ ] **Step 1: Write failing canonicalization and sidecar tests**

```python
def test_requirement_digest_is_unicode_and_whitespace_stable(self):
    self.assertEqual(
        canonical_requirement_sha256("  프로필   변경\n"),
        canonical_requirement_sha256("프로필 변경"),
    )

def test_context_is_bound_to_one_published_revision(self):
    context = sample_context(report_id="RPT-001", revision=2)
    path = publish_report_context(self.root, context)
    self.assertEqual(path.name, "revision-0002.context.json")
    self.assertEqual(load_report_context(self.root, "RPT-001", 2), context)
```

- [ ] **Step 2: Run tests and confirm the module is missing**

Run: `python3 -m unittest -q tests.test_rir_report_context`

Expected: FAIL importing `rir_report_context`.

- [ ] **Step 3: Implement the exact context contract**

```python
@dataclass(frozen=True)
class ReportContext:
    schema_version: int
    report_id: str
    revision: int
    markdown_sha256: str
    repo_root_sha256: str
    requirement_sha256: str
    source_inventory_sha256: str
    payload_sha256: str
    created_at: str
    baseline_commit: Optional[str]
    baseline_clean: bool
```

Normalize requests with Unicode NFC and `" ".join(request.split())`; do not lowercase. Serialize canonical UTF-8 JSON, mode `0600`, and bind the sidecar filename and fields to the already-published immutable revision. Legacy missing sidecars return `None`; malformed, symlinked, digest-mismatched, or non-private sidecars fail closed.

- [ ] **Step 4: Publish context only after report publication succeeds**

`rir_finalize` obtains the verified graph inventory digest and payload identity, probes the bounded Git baseline, publishes the immutable report, then atomically writes the context sidecar before updating controller completion metadata. An interrupted context write leaves the report readable but stale.

- [ ] **Step 5: Verify and commit**

Run: `python3 -m unittest -q tests.test_rir_report_context tests.test_report_store tests.test_rir_controller`

Run: `.quality-venv/bin/mypy scripts evals/harness`

```bash
git add scripts/rir_report_context.py scripts/rir_finalize.py scripts/rir_storage.py skills/requirements-impact-refiner/scripts tests/test_rir_report_context.py
git commit -m "feat: persist immutable report context"
```

### Task 2: Add bounded previous-report lookup

**Files:**
- Create: `scripts/rir_previous.py`
- Create: `skills/requirements-impact-refiner/scripts/rir_previous.py`
- Create: `scripts/rir_previous_renderer.py`
- Create: `skills/requirements-impact-refiner/scripts/rir_previous_renderer.py`
- Modify: `scripts/rir_controller.py`
- Modify: installed-skill mirror
- Test: `tests/test_rir_previous.py`
- Create: `tests/fixtures/previous-report-repository/`

**Interfaces:**
- Consumes: `ReportContext`, current report pointer, normalized requirement digest, bounded Git probe
- Produces: `PreviousLookupRequest`, `PreviousReportResult`, `lookup_previous(request: PreviousLookupRequest) -> PreviousReportResult`, `render_previous(result, compact_state) -> str`

- [ ] **Step 1: Write failing status and isolation tests**

```python
def test_exact_clean_match_is_fresh(self):
    result = lookup_previous(self.request("rename profile"))
    self.assertEqual(result.status, "fresh")
    self.assertEqual(result.changed_paths, ())

def test_other_requirement_never_returns_previous_body(self):
    result = lookup_previous(self.request("delete account"))
    self.assertEqual(result.status, "none")
    self.assertIsNone(result.display_text)
```

Add cases for `stale`, `ambiguous`, missing v2 context, missing Git, Git timeout, dirty tracked files, relevant ignored/untracked files, index visibility flags, unsafe pointer, and another repository root.

- [ ] **Step 2: Run and observe the missing lookup API**

Run: `python3 -m unittest -q tests.test_rir_previous`

- [ ] **Step 3: Implement bounded lookup results**

```python
@dataclass(frozen=True)
class PreviousReportResult:
    status: Literal["none", "fresh", "stale", "ambiguous"]
    report_id: Optional[str]
    revision: Optional[int]
    markdown_sha256: Optional[str]
    created_at: Optional[str]
    baseline_commit: Optional[str]
    changed_paths: Tuple[str, ...]
    changed_count: Optional[int]
    requirement_sha256: str
    source_inventory_sha256: Optional[str]
    display_text: Optional[str]
    reason: str
    elapsed_ms: int
```

Use a 250ms operation deadline and bounded output for explicitly scoped Git probes. Only a matching v2 state/evidence/payload context, stable HEAD, clean tracked/untracked worktree and submodules, tracked-only inventory, and absence of assume-unchanged/skip-worktree flags is `fresh`. Missing/slow Git or incomplete proof is `stale`; missing context is `none`. Multiple matching lineages are `ambiguous` without body disclosure.

`render_previous` reads the already-published compact state, prefixes status,
creation time, baseline commit, changed-file count, and freshness, then appends
the existing compact impact summary. It preserves complete Markdown blocks and
never returns the full immutable Markdown report by default. Task 2 uses the
current English labels; the UX/evidence plan replaces labels through the shared
locale catalog without changing fields or identity.

- [ ] **Step 4: Prove the lookup budget**

Use a pinned fixture with 1,000 irrelevant generated files. Assert 20 warm lookups have p95 `<= 300ms`, and unsafe or ambiguous cases return no Markdown body.

- [ ] **Step 5: Verify and commit**

Run: `python3 -m unittest -q tests.test_rir_previous tests.test_report_store tests.test_report_lineage`

```bash
git add scripts/rir_previous.py scripts/rir_previous_renderer.py scripts/rir_controller.py skills/requirements-impact-refiner/scripts tests/test_rir_previous.py tests/fixtures/previous-report-repository
git commit -m "feat: look up previous impact reports"
```

### Task 3: Expose previous lookup through CLI and MCP

**Files:**
- Modify: `scripts/rir-controller.py`
- Modify: installed-skill mirror
- Modify: `scripts/rir_mcp_server.py`
- Modify: `.mcp.json`
- Modify: `.codex-plugin/plugin.json`
- Test: `tests/test_rir_controller_cli.py`
- Test: `tests/test_rir_mcp_server.py`
- Test: `tests/test_packaging.py`

**Interfaces:**
- Produces: CLI `previous`; MCP tool `rir_previous`; JSON-safe `PreviousReportResult`
- Consumes: Task 2 `lookup_previous`

- [ ] **Step 1: Write failing CLI and JSON-RPC contract tests**

```python
def test_previous_cli_returns_renderer_neutral_json(self):
    result = run_cli("previous", self.request_path)
    self.assertEqual(result.returncode, 0)
    self.assertEqual(json.loads(result.stdout)["status"], "fresh")

def test_previous_tool_is_declared(self):
    tools = self.initialize_and_list_tools()
    self.assertIn("rir_previous", {row["name"] for row in tools})
```

- [ ] **Step 2: Run and confirm command/tool absence**

Run: `python3 -m unittest -q tests.test_rir_controller_cli tests.test_rir_mcp_server`

- [ ] **Step 3: Add exact request schema and handlers**

`rir_previous` accepts only `repo_root`, `request`, and `repository_evidence`. Unknown keys are `-32602`. Unsafe storage or internal result-contract failures are `-32603`. The response returns bounded semantic fields and Markdown bytes only for a safe `fresh` or `stale` same-lineage result. Do not add an installed-skill MCP server mirror.

- [ ] **Step 4: Verify notification, malformed, and payload identity behavior**

Run: `python3 -m unittest -q tests.test_rir_mcp_server tests.test_rir_controller_cli tests.test_packaging tests.test_distribution`

- [ ] **Step 5: Commit**

```bash
git add scripts/rir-controller.py scripts/rir_mcp_server.py skills/requirements-impact-refiner/scripts/rir-controller.py .mcp.json .codex-plugin/plugin.json tests/test_rir_controller_cli.py tests/test_rir_mcp_server.py tests/test_packaging.py
git commit -m "feat: expose previous report lookup"
```

### Task 4: Make automatic bootstrap previous-first

**Files:**
- Modify: `skills/using-requirements-impact-refiner/SKILL.md`
- Modify: `skills/requirements-impact-refiner/SKILL.md`
- Create: `references/previous-report.md`
- Create: `skills/requirements-impact-refiner/references/previous-report.md`
- Modify: `tests/test_integration_adapters.py`
- Modify: `tests/test_installed_plugin_evidence.py`

**Interfaces:**
- Consumes: `rir_previous`, existing `rir_scan`, explicit detailed-refinement confirmation
- Produces: deterministic `previous → stop|scan → optional begin/trace/finalize` tool order

- [ ] **Step 1: Write failing instruction and tool-order tests**

```python
def test_bootstrap_requires_previous_before_scan(self):
    text = bootstrap_skill.read_text(encoding="utf-8")
    self.assertLess(text.index("rir_previous"), text.index("rir_scan"))

def test_fresh_previous_stops_without_scan(self):
    calls = run_bootstrap_fixture(previous_status="fresh")
    self.assertEqual(calls, ["rir_previous"])
```

Add stale `["rir_previous", "rir_scan"]`, none `["rir_previous", "rir_scan"]`, ambiguous `["rir_previous"]`, and explicit confirmation detailed-flow cases.

- [ ] **Step 2: Run and observe old scan-first instructions**

Run: `python3 -m unittest -q tests.test_integration_adapters tests.test_installed_plugin_evidence`

- [ ] **Step 3: Write the exact previous-first workflow**

The bootstrap returns previous renderer text immediately. `fresh` stops. `stale` continues with the immutable report ID/revision and changed paths. `none` runs ordinary Fast Scan. `ambiguous` asks for the missing report discriminator. Only an explicit yes starts detailed refinement. Do not infer confirmation from the original change request.

- [ ] **Step 4: Verify Codex, Claude, generic, and Superpowers adapters**

Run: `python3 -m unittest -q tests.test_integration_adapters tests.test_integration_evidence tests.test_with_skill_evidence`

- [ ] **Step 5: Commit**

```bash
git add skills tests/test_integration_adapters.py tests/test_installed_plugin_evidence.py
git commit -m "feat: bootstrap from previous impact reports"
```

### Task 5: Add safe three-second delta scanning

**Files:**
- Create: `scripts/rir_delta.py`
- Create: installed-skill mirror
- Modify: `scripts/fast_scan.py`
- Modify: installed-skill mirror
- Modify: `scripts/graph_builtin.py`
- Modify: installed-skill mirror
- Modify: `scripts/resolve-settings.py`
- Modify: installed-skill mirror
- Modify: `schemas/fast-impact-scan.schema.json`
- Modify: installed-skill schema mirror
- Test: `tests/test_rir_delta.py`
- Create: `tests/fixtures/delta-cdz-project/`

**Interfaces:**
- Consumes: stale `PreviousReportResult`, previous compact state, changed paths, prior graph receipt
- Produces: `DeltaScanContext`, `derive_delta_seeds(...)`, optional `previous_report_id`, `previous_revision`, `delta_max_seconds=3`

- [ ] **Step 1: Write failing indirect-impact and exclusion tests**

```python
def test_a_change_preserves_indirect_c_d_z_seeds(self):
    seeds = derive_delta_seeds(self.previous, changed_paths=("a.py",))
    self.assertEqual(
        tuple(seed.location for seed in seeds),
        ("a.py", "c.py", "d.py", "z.py"),
    )

def test_generated_directories_do_not_consume_inventory(self):
    inventory = collect_sources(self.root, explicit_seeds=())
    self.assertNotIn(".mypy_cache/3.9/a.meta.json", inventory.digests)
```

- [ ] **Step 2: Run and confirm delta API and exclusions are absent**

Run: `python3 -m unittest -q tests.test_rir_delta`

- [ ] **Step 3: Implement deterministic seed priority**

Order unique seeds as changed paths, prior selected path nodes, preserved invariant evidence locations, then uncovered request terms. Explicit request seeds override generated-directory exclusions. Default exclusions are `.git`, `.mypy_cache`, `.quality-venv`, `.requirements-impact-refiner`, `evals/results`, `__pycache__`, and common build outputs already ignored by the repository collector.

- [ ] **Step 4: Enforce the hard delta deadline and partial fallback**

A stale delta request uses `min(configured_delta_max_seconds, 3)` by default. At deadline it returns the prior revision identity, changed paths, every surviving frontier, `status=partial`, and `can_promote=false`. It never discards the prior valid report or fabricates a path.

- [ ] **Step 5: Verify C/D/Z and timeout behavior**

Run: `python3 -m unittest -q tests.test_rir_delta tests.test_fast_scan tests.test_graph_builtin tests.test_graph_coordinator`

- [ ] **Step 6: Commit**

```bash
git add scripts/rir_delta.py scripts/fast_scan.py scripts/graph_builtin.py scripts/resolve-settings.py skills/requirements-impact-refiner schemas/fast-impact-scan.schema.json tests/test_rir_delta.py tests/fixtures/delta-cdz-project
git commit -m "feat: bound indirect delta impact scans"
```

### Task 6: Record end-to-end performance and token estimates

**Files:**
- Create: `scripts/rir_performance.py`
- Create: installed-skill mirror
- Modify: `scripts/rir_previous.py`
- Modify: installed-skill mirror
- Modify: `scripts/fast_scan.py`
- Modify: installed-skill mirror
- Modify: `schemas/fast-impact-scan.schema.json`
- Modify: installed-skill mirror
- Modify: `evals/harness/performance.py`
- Test: `tests/test_rir_performance.py`
- Modify: `tests/test_performance_budget.py`

**Interfaces:**
- Produces: `PhaseMetric`, `PerformanceMetrics`, `estimate_tokens(payload: bytes) -> int`
- Consumes: lookup, inventory, compact graph, previous-state reuse, client-reported token usage when available

- [ ] **Step 1: Write failing deterministic metric tests**

```python
def test_estimated_and_actual_tokens_are_separate(self):
    metrics = PerformanceMetrics.from_payloads(previous=b"1234", delta=b"12345678")
    self.assertEqual(metrics.estimated_input_tokens, 3)
    self.assertIsNone(metrics.actual_input_tokens)

def test_reused_bytes_are_not_counted_twice(self):
    metrics = measure(previous=PAYLOAD, delta=PAYLOAD, reused_sha256=sha256(PAYLOAD))
    self.assertEqual(metrics.new_evidence_bytes, 0)
```

- [ ] **Step 2: Run and confirm missing metric types**

Run: `python3 -m unittest -q tests.test_rir_performance`

- [ ] **Step 3: Implement deterministic byte-based estimates**

Use `ceil(utf8_bytes / 4)` and name fields `estimated_*`. Client-reported usage is stored only in `actual_*`. Record lookup, inventory/delta, compact serialization, reused bytes, new evidence bytes, cache status, and total elapsed time. Metrics do not enter scan identity or evidence confidence.

- [ ] **Step 4: Add literal performance gates**

Pinned fixtures assert lookup p95 `<=300ms`, stale delta p95 `<=3000ms`, exact-match provider/graph/model call counts equal zero, repeated-request estimated input tokens below the v0.5 baseline, and no lost frontier.

- [ ] **Step 5: Verify and commit**

Run: `python3 -m unittest -q tests.test_rir_performance tests.test_performance_budget tests.test_fast_scan`

```bash
git add scripts/rir_performance.py scripts/rir_previous.py scripts/fast_scan.py skills/requirements-impact-refiner schemas/fast-impact-scan.schema.json evals/harness/performance.py tests/test_rir_performance.py tests/test_performance_budget.py
git commit -m "perf: measure bounded impact refinement"
```

### Task 7: Runtime integration and deterministic review gate

**Files:**
- Verify: Tasks 1-6 changes

**Interfaces:**
- Consumes: immutable context, lookup, CLI/MCP, bootstrap, delta scan, metrics
- Produces: runtime payload ready for the UX/evidence plan

- [ ] **Step 1: Run complete deterministic gates**

Run: `.quality-venv/bin/python scripts/run-quality-gates.py`

Run: `python3 -m unittest discover -s tests -q`

- [ ] **Step 2: Run performance and compatibility canaries**

Run: `python3 -m unittest -q tests.test_rir_previous tests.test_rir_delta tests.test_rir_performance tests.test_distribution tests.test_packaging`

- [ ] **Step 3: Request independent security, concurrency, and compatibility review**

Security review attacks repository/lineage confusion, symlinked sidecars, state/evidence confusion, Markdown disclosure, index visibility flags, worktree redirection, and Git output injection. Concurrency review attacks simultaneous lookup/finalize, HEAD races, and interrupted sidecar publication. Compatibility review verifies legacy reports remain artifact-readable but previous lookup returns no body, while existing four controller tools remain byte-compatible.

- [ ] **Step 4: Record review verdicts and route findings through the task review loop**

Any Critical or Important finding fails this task and enters the
subagent-driven-development fix loop with its exact affected files and covering
tests. A clean review creates no empty commit.

- [ ] **Step 5: Hand off semantic fields to UX plan**

Document the exact `PreviousReportResult` and `PerformanceMetrics` fields in the task report. The next plan renders them but must not change identity, freshness, timeout, or token calculations.
