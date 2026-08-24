# Fast Impact Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Add a one-call, receipt-backed Fast Scan that exposes distant regression paths within a 10-second target and 30-second hard scan ceiling, while running full requirements refinement only after explicit user promotion.

**Architecture:** rir_scan deterministically derives bounded repository-backed seeds, invokes the existing graph coordinator once, stores an immutable private scan receipt, and returns renderer-owned output of at most 180 words. rir_begin(scan_id) validates and reuses that receipt so detailed refinement skips graph execution; the existing advanced flow remains available.

**Tech Stack:** Python 3 standard library, local MCP JSON-RPC, JSON Schema, existing graph coordinator/cache/providers, unittest, Git.

**Spec:** docs/superpowers/specs/2026-08-24-fast-impact-scan-design.md

## Global Constraints

- Scan target is exactly 10,000 ms; controller ceiling is exactly 30,000 ms.
- User output is renderer-owned and at most 180 whitespace-delimited words.
- Normal mode performs one rir_scan call and never promotes or retries automatically.
- High or critical risk is shown before detailed refinement.
- Deadline-limited work returns partial with explicit unknown frontier.
- Provider install/update/auth/network/upload/server/index operations remain forbidden.
- Raw provider output, complete receipts, schemas, templates, and detailed references stay out of normal model context.
- Promotion reuses the exact immutable receipt and never reruns the graph.
- Existing rir_begin → rir_trace_impact → rir_finalize clients remain compatible.
- The plugin uses the user's selected model and never substitutes one.
- No live model call occurs before deterministic tasks and independent reviews pass.
- Canonical skill files and root fallback mirrors remain byte-identical.

---

### Task 1: Fast Scan Contract and Deterministic Seed Derivation

**Files:**
- Create: scripts/fast_scan.py
- Create: skills/requirements-impact-refiner/scripts/fast_scan.py
- Create: schemas/fast-impact-scan.schema.json
- Create: skills/requirements-impact-refiner/schemas/fast-impact-scan.schema.json
- Modify: scripts/payload_identity.py
- Modify: skills/requirements-impact-refiner/scripts/payload_identity.py
- Create: tests/test_fast_scan.py
- Modify: tests/test_packaging.py

**Interfaces:**
- Produces DerivedSeed, FastScanRequest, validate_fast_scan_receipt, canonical_fast_scan_bytes, and derive_seeds.
- derive_seeds(repo_root, change_request, evidence, deadline, maximum=16) returns an ordered tuple of repository-backed seeds.
- Later tasks consume schema version 1 and the exact fields defined here.

- [ ] **Step 1: Write failing seed and schema tests**

~~~python
def test_derives_file_symbol_and_evidence_seeds(self):
    self.write("api/profile.py", 'FIELD = "profile.displayName"\n')
    self.write(
        "mobile/profile_decoder.swift",
        'let field = "profile.displayName"\n',
    )
    seeds = FAST_SCAN.derive_seeds(
        self.root,
        "Rename profile.displayName in api/profile.py",
        ("mobile/profile_decoder.swift reads profile.displayName",),
        self.deadline(),
    )
    self.assertEqual(
        [(row.term, row.location) for row in seeds],
        [
            ("profile.displayName", "api/profile.py"),
            ("profile.displayName", "mobile/profile_decoder.swift"),
        ],
    )

def test_unmatched_natural_language_needs_input(self):
    self.assertEqual(
        FAST_SCAN.derive_seeds(
            self.root, "make the experience nicer", (), self.deadline()
        ),
        (),
    )
~~~

Also test request >4 KiB, >32 evidence rows, duplicates, traversal, symlinks, binary/oversized files, Unicode, deadline expiry, maximum 16 seeds, stable rank, source digest, and credential-shaped evidence redaction.

- [ ] **Step 2: Run RED**

~~~bash
PYTHONPYCACHEPREFIX=/tmp/rir-fast-task1-red \
python3 -m unittest tests.test_fast_scan tests.test_packaging -v
~~~

Expected: missing module/schema failures.

- [ ] **Step 3: Implement exact types and bounded derivation**

~~~python
@dataclass(frozen=True)
class DerivedSeed:
    term: str
    location: Optional[str]
    derivation: str
    source_sha256: Optional[str]

@dataclass(frozen=True)
class FastScanRequest:
    repo_root: Path
    change_request: str
    evidence: Tuple[str, ...]
    audience: str

@dataclass(frozen=True)
class FastScanReceipt:
    schema_version: int
    status: str
    scan_id: str
    receipt_id: str
    repo_root_sha256: str
    request_sha256: str
    payload_sha256: str
    settings: Mapping[str, object]
    source_inventory: Mapping[str, object]
    seeds: Tuple[DerivedSeed, ...]
    graph_receipt: Mapping[str, object]
    risk_level: str
    frontier: Tuple[Mapping[str, object], ...]
    elapsed_ms: int
    cache_status: str
    can_promote: bool
    created_at: str

def derive_seeds(
    repo_root: Path,
    change_request: str,
    evidence: Tuple[str, ...],
    deadline: object,
    maximum: int = 16,
) -> Tuple[DerivedSeed, ...]: ...
~~~

Derivation order is exact path+symbol, qualified symbol, bounded distinctive-term repository match, then supplied-evidence location. Unmatched generic prose cannot become a guessed seed.

The schema requires the exact top-level keys: schema_version, status, scan_id, receipt_id, repo_root_sha256, request_sha256, payload_sha256, settings, source_inventory, seeds, graph_receipt, risk_level, frontier, elapsed_ms, cache_status, can_promote, created_at.

- [ ] **Step 4: Add mirror and payload coverage**

Add the root schema/script to ROOT_FILES. Tests prove byte-identical mirrors, JSON parsing, inventory inclusion, and payload hash change after either dependency mutates.

- [ ] **Step 5: Run GREEN and commit**

~~~bash
PYTHONPYCACHEPREFIX=/tmp/rir-fast-task1-green \
python3 -m unittest tests.test_fast_scan tests.test_packaging -v
cmp scripts/fast_scan.py skills/requirements-impact-refiner/scripts/fast_scan.py
cmp schemas/fast-impact-scan.schema.json skills/requirements-impact-refiner/schemas/fast-impact-scan.schema.json
cmp scripts/payload_identity.py skills/requirements-impact-refiner/scripts/payload_identity.py
git diff --check
git add scripts/fast_scan.py skills/requirements-impact-refiner/scripts/fast_scan.py schemas/fast-impact-scan.schema.json skills/requirements-impact-refiner/schemas/fast-impact-scan.schema.json scripts/payload_identity.py skills/requirements-impact-refiner/scripts/payload_identity.py tests/test_fast_scan.py tests/test_packaging.py
git commit -m "feat: define fast impact scan contract"
~~~

---

### Task 2: Scan Execution, Private Storage, Cache, and Rendering

**Files:**
- Create: scripts/fast_scan_store.py
- Create: skills/requirements-impact-refiner/scripts/fast_scan_store.py
- Create: scripts/fast_scan_renderer.py
- Create: skills/requirements-impact-refiner/scripts/fast_scan_renderer.py
- Modify: scripts/fast_scan.py
- Modify: skills/requirements-impact-refiner/scripts/fast_scan.py
- Modify: scripts/payload_identity.py
- Modify: skills/requirements-impact-refiner/scripts/payload_identity.py
- Create: tests/test_fast_scan_store.py
- Create: tests/test_fast_scan_renderer.py
- Modify: tests/test_fast_scan.py
- Modify: tests/test_packaging.py

**Interfaces:**
- Consumes Task 1 and graph_coordinator.coordinate.
- Produces execute_fast_scan(...) -> FastScanResult.
- Produces load_scan_receipt(repo_root, scan_id) for promotion.

- [ ] **Step 1: Write execution/storage/render RED tests**

~~~python
def test_executes_graph_once_and_renders_under_limit(self):
    result = FAST_SCAN.execute_fast_scan(
        self.request("Rename profile.displayName"),
        self.settings(),
        payload_sha256="a" * 64,
        coordinator=self.coordinator,
    )
    self.assertEqual(self.coordinator.calls, 1)
    self.assertLessEqual(len(result.display_text.split()), 180)
    self.assertIn("api/profile.py → mobile/profile_decoder.swift", result.display_text)
    self.assertEqual(result.display_text.count("Coverage:"), 1)
~~~

Cover 0600 immutable files, descriptor-bound directories, atomic publication, destination collision, rename/symlink races, source mutation, deadline partial result, provider failure, exact cache hit/miss/bypass, maximum eight displayed paths, escaping, and all presentation modes.

- [ ] **Step 2: Run RED**

~~~bash
PYTHONPYCACHEPREFIX=/tmp/rir-fast-task2-red \
python3 -m unittest tests.test_fast_scan tests.test_fast_scan_store tests.test_fast_scan_renderer -v
~~~

- [ ] **Step 3: Implement storage and renderer**

~~~python
def publish_scan_receipt(repo_root: Path, scan_id: str, payload: bytes) -> Path: ...
def load_scan_receipt(repo_root: Path, scan_id: str) -> Mapping[str, object]: ...
def render_fast_scan(receipt: Mapping[str, object], audience: str) -> str: ...
~~~

Store under .requirements-impact-refiner/scans using 0600 temporary files, fsync, atomic no-replace rename, directory fsync, and exact inode/size/digest verification. Renderer orders critical/high paths, unknown frontiers, then lower risks; it truncates labels independently and preserves provenance.

- [ ] **Step 4: Implement one-deadline execution**

~~~python
@dataclass(frozen=True)
class FastScanResult:
    status: str
    scan_id: str
    receipt_id: str
    receipt_sha256: str
    display_text: str
    risk_level: str
    paths: Tuple[Mapping[str, object], ...]
    frontier: Tuple[Mapping[str, object], ...]
    elapsed_ms: int
    cache_status: str
    can_promote: bool

def execute_fast_scan(
    request: FastScanRequest,
    graph_settings: Mapping[str, object],
    payload_sha256: str,
    *,
    coordinator=GRAPH_COORDINATOR.coordinate,
) -> FastScanResult: ...
~~~

The deadline starts before inventory/lock/cache work. Empty trustworthy seeds produce needs_input without calling the coordinator. Deadline exhaustion produces partial. Publication uncertainty returns no promotable ID.

- [ ] **Step 5: Verify and commit**

~~~bash
PYTHONPYCACHEPREFIX=/tmp/rir-fast-task2-green \
python3 -m unittest tests.test_fast_scan tests.test_fast_scan_store tests.test_fast_scan_renderer tests.test_graph_coordinator tests.test_graph_cache tests.test_packaging -v
cmp scripts/fast_scan.py skills/requirements-impact-refiner/scripts/fast_scan.py
cmp scripts/fast_scan_store.py skills/requirements-impact-refiner/scripts/fast_scan_store.py
cmp scripts/fast_scan_renderer.py skills/requirements-impact-refiner/scripts/fast_scan_renderer.py
git diff --check
git add scripts/fast_scan.py skills/requirements-impact-refiner/scripts/fast_scan.py scripts/fast_scan_store.py skills/requirements-impact-refiner/scripts/fast_scan_store.py scripts/fast_scan_renderer.py skills/requirements-impact-refiner/scripts/fast_scan_renderer.py scripts/payload_identity.py skills/requirements-impact-refiner/scripts/payload_identity.py tests/test_fast_scan.py tests/test_fast_scan_store.py tests/test_fast_scan_renderer.py tests/test_packaging.py
git commit -m "feat: execute and render fast impact scans"
~~~

---

### Task 3: Controller Promotion Without a Second Graph Run

**Files:**
- Modify: scripts/rir_controller.py
- Modify: skills/requirements-impact-refiner/scripts/rir_controller.py
- Modify: schemas/controller-analysis.schema.json
- Modify: skills/requirements-impact-refiner/schemas/controller-analysis.schema.json
- Modify: scripts/payload_identity.py
- Modify: skills/requirements-impact-refiner/scripts/payload_identity.py
- Modify: tests/test_rir_controller.py
- Modify: tests/test_packaging.py

**Interfaces:**
- Adds ScanRequest, ScanResult, and scan_impact(request).
- Extends BeginRequest with scan_id: Optional[str] = None.
- Extends DraftResult with scan_id: Optional[str] and graph_receipt_id: Optional[str].
- Promoted drafts bind the exact scan and graph receipt.

- [ ] **Step 1: Write controller RED tests**

~~~python
def test_promoted_begin_reuses_receipt_without_graph_rerun(self):
    scan = CONTROLLER.scan_impact(
        CONTROLLER.ScanRequest(
            self.root, "Rename profile.displayName", (), "balanced"
        )
    )
    draft = CONTROLLER.begin_refinement(
        CONTROLLER.BeginRequest(
            self.root, "Rename profile.displayName", (), "generic",
            scan_id=scan.scan_id,
        )
    )
    self.assertEqual(draft.graph_receipt_id, scan.receipt_id)
    self.assertEqual(self.coordinator.calls, 1)
~~~

Cover wrong root/request/evidence/settings/payload, stale/mutated/partial scans, consumed/cross-draft scan, concurrent promotion, source mutation, crash retry, legacy begin, advanced trace, and finalize.

- [ ] **Step 2: Run RED**

~~~bash
PYTHONPYCACHEPREFIX=/tmp/rir-fast-task3-red \
python3 -m unittest tests.test_rir_controller tests.test_packaging -v
~~~

- [ ] **Step 3: Add controller scan types**

~~~python
@dataclass(frozen=True)
class ScanRequest:
    repo_root: Path
    change_request: str
    evidence: Tuple[str, ...]
    audience_override: Optional[str] = None

def scan_impact(request: ScanRequest) -> ScanResult: ...
~~~

scan_impact resolves existing presentation/graph settings and calls Task 2 exactly once.

- [ ] **Step 4: Implement promotion binding**

Add scan_id to BeginRequest. Before creating a draft, validate root, normalized request/evidence, settings, source inventory, payload, scan digest, and embedded graph receipt. Persist scan identity in the private draft. Promotion is compare-and-swap safe and one-way; failed draft publication leaves the scan reusable.

- [ ] **Step 5: Verify and commit**

~~~bash
PYTHONPYCACHEPREFIX=/tmp/rir-fast-task3-green \
python3 -m unittest tests.test_rir_controller tests.test_fast_scan tests.test_fast_scan_store tests.test_packaging -v
cmp scripts/rir_controller.py skills/requirements-impact-refiner/scripts/rir_controller.py
cmp schemas/controller-analysis.schema.json skills/requirements-impact-refiner/schemas/controller-analysis.schema.json
git diff --check
git add scripts/rir_controller.py skills/requirements-impact-refiner/scripts/rir_controller.py schemas/controller-analysis.schema.json skills/requirements-impact-refiner/schemas/controller-analysis.schema.json scripts/payload_identity.py skills/requirements-impact-refiner/scripts/payload_identity.py tests/test_rir_controller.py tests/test_packaging.py
git commit -m "feat: promote fast scans into refinement"
~~~

---

### Task 4: MCP and CLI One-Call Surfaces

**Files:**
- Modify: scripts/rir_mcp_server.py
- Modify: scripts/rir-controller.py
- Modify: skills/requirements-impact-refiner/scripts/rir-controller.py
- Modify: scripts/payload_identity.py
- Modify: skills/requirements-impact-refiner/scripts/payload_identity.py
- Modify: tests/test_rir_mcp_server.py
- Modify: tests/test_rir_controller_cli.py
- Modify: tests/test_packaging.py

**Interfaces:**
- MCP order becomes rir_scan, rir_begin, rir_trace_impact, rir_finalize.
- CLI adds scan --repo-root REPO --input REQUEST.json.
- CLI scan defaults to renderer text; explicit --json returns the complete ScanResult projection for machine-driven promotion.
- rir_begin gains optional scan_id.

- [ ] **Step 1: Write MCP/CLI RED tests**

~~~python
def test_tools_list_places_scan_first(self):
    reply = self.call("tools/list", {})
    self.assertEqual(
        [row["name"] for row in reply["result"]["tools"]],
        ["rir_scan", "rir_begin", "rir_trace_impact", "rir_finalize"],
    )

def test_scan_text_equals_structured_display(self):
    reply = self.scan("Rename profile.displayName")
    result = reply["result"]
    self.assertEqual(
        result["content"][0]["text"],
        result["structuredContent"]["display_text"],
    )
~~~

Cover deep/oversized JSON, wrong types, traversal, bounded errors, server continuation, lock deadline, partial, needs_input, failed CLI stdout, exit 1/2 contracts, and begin --scan-id.

- [ ] **Step 2: Run RED**

~~~bash
PYTHONPYCACHEPREFIX=/tmp/rir-fast-task4-red \
python3 -m unittest tests.test_rir_mcp_server tests.test_rir_controller_cli -v
~~~

- [ ] **Step 3: Add exact MCP schema and handler**

SCAN_SCHEMA accepts only repo_root, change_request, optional evidence, and optional presentation. MCP content text equals display_text. The description says local, network-free, one-call, and no automatic promotion. BEGIN_SCHEMA accepts optional 32-hex scan_id.

- [ ] **Step 4: Add CLI scan**

Input shape:

~~~json
{
  "change_request": "Rename profile.displayName",
  "evidence": [],
  "presentation": "balanced"
}
~~~

Successful default stdout is display_text only. With --json, stdout is the canonical ScanResult projection containing scan_id and display_text; no other diagnostics appear on stdout. Add --scan-id to begin.

- [ ] **Step 5: Verify and commit**

~~~bash
PYTHONPYCACHEPREFIX=/tmp/rir-fast-task4-green \
python3 -m unittest tests.test_rir_mcp_server tests.test_rir_controller_cli tests.test_rir_controller tests.test_packaging -v
cmp scripts/rir-controller.py skills/requirements-impact-refiner/scripts/rir-controller.py
git diff --check
git add scripts/rir_mcp_server.py scripts/rir-controller.py skills/requirements-impact-refiner/scripts/rir-controller.py scripts/payload_identity.py skills/requirements-impact-refiner/scripts/payload_identity.py tests/test_rir_mcp_server.py tests/test_rir_controller_cli.py tests/test_packaging.py
git commit -m "feat: expose one-call fast impact scan"
~~~

---

### Task 5: Short Skill Route and Multilingual Docs

**Files:**
- Modify: skills/using-requirements-impact-refiner/SKILL.md
- Modify: skills/requirements-impact-refiner/SKILL.md
- Create: skills/requirements-impact-refiner/references/fast-scan.md
- Create: references/fast-scan.md
- Modify: skills/requirements-impact-refiner/references/controller-workflow.md
- Modify: references/controller-workflow.md
- Modify: README.md
- Modify: README.ko.md
- Modify: README.ja.md
- Modify: docs/compact-delivery-demo.md
- Modify: assets/compact-delivery-demo.svg
- Modify: tests/test_documentation.py
- Modify: tests/test_integration_adapters.py
- Modify: tests/test_packaging.py

**Interfaces:**
- Default recipe: call rir_scan once, return display_text verbatim, ask whether to refine, stop.
- Detailed references load only after explicit promotion.
- Advanced flow stays documented but is not on the default route.

- [ ] **Step 1: Write skill/docs RED tests**

~~~python
def test_default_route_is_one_call_and_under_budget(self):
    text = CORE_SKILL.read_text(encoding="utf-8")
    self.assertLess(len(text.split()), 180)
    route = default_route_section(text)
    self.assertEqual(route.count("rir_scan"), 1)
    self.assertNotIn("rir_trace_impact", route)
    self.assertNotIn("controller-workflow.md", route)
~~~

Add EN/KO/JA parity for names, 180 words, 10/30 seconds, statuses, promotion, advanced compatibility, provider policy, and not-verified status. Assert high risk asks the user and does not promote.

- [ ] **Step 2: Run RED**

~~~bash
PYTHONPYCACHEPREFIX=/tmp/rir-fast-task5-red \
python3 -m unittest tests.test_documentation tests.test_integration_adapters tests.test_packaging -v
~~~

- [ ] **Step 3: Rewrite default route**

The core says exactly:

~~~text
1. Call rir_scan once with the user's change and supplied evidence.
2. Return display_text verbatim.
3. Ask whether the user wants detailed refinement.
4. Stop; never promote, plan, or implement without the answer.
~~~

Move technical detail to fast-scan.md. Put existing controller/adapter references behind explicit detailed refinement.

- [ ] **Step 4: Synchronize docs**

Separate graph-engine time from full model latency. Record the observed 17 ms graph and 297.159-second model turn, distant path success, strict automation failure, and unverified v0.4 status. Do not promise a 30-second LLM response.

- [ ] **Step 5: Verify and commit**

~~~bash
PYTHONPYCACHEPREFIX=/tmp/rir-fast-task5-green \
python3 -m unittest tests.test_documentation tests.test_integration_adapters tests.test_packaging -v
cmp skills/requirements-impact-refiner/references/fast-scan.md references/fast-scan.md
cmp skills/requirements-impact-refiner/references/controller-workflow.md references/controller-workflow.md
git diff --check
git add skills/using-requirements-impact-refiner/SKILL.md skills/requirements-impact-refiner/SKILL.md skills/requirements-impact-refiner/references/fast-scan.md references/fast-scan.md skills/requirements-impact-refiner/references/controller-workflow.md references/controller-workflow.md README.md README.ko.md README.ja.md docs/compact-delivery-demo.md assets/compact-delivery-demo.svg tests/test_documentation.py tests/test_integration_adapters.py tests/test_packaging.py
git commit -m "docs: make fast scan the default route"
~~~

---

### Task 6: Deterministic Evaluation and Safety Gates

**Files:**
- Create: evals/fast-scan-cases.json
- Create: evals/harness/fast_scan_scoring.py
- Modify: evals/harness/performance.py
- Modify: evals/harness/run.py
- Modify: evals/harness/adapters/codex.py
- Modify: evals/harness/controller_evidence.py
- Modify: evals/harness/schemas/result.schema.json
- Create: tests/test_fast_scan_eval_cases.py
- Create: tests/test_fast_scan_scoring.py
- Modify: tests/test_performance_budget.py
- Modify: tests/test_eval_harness_codex.py
- Modify: tests/test_eval_harness_cli.py

**Interfaces:**
- Adds five positive cases and one negative no-tool case.
- Produces FastScanPerformanceObservation and a deterministic gate.
- Seals request/seed/source/settings/payload/receipt/display provenance.

- [ ] **Step 1: Write catalog/scoring RED tests**

~~~python
def test_distant_path_requires_expected_seed_and_distance(self):
    score = score_fast_scan(case, receipt, display_text)
    self.assertTrue(score.passed, score.findings)
    self.assertGreaterEqual(score.maximum_required_distance, 3)
~~~

Required catalog seeds must be a subset of actual derived seeds; every actual seed stays request-hash bound. This permits extra repository-backed seeds but rejects alternate-only provenance.

- [ ] **Step 2: Add exact gate RED tests**

Require six attempt-1/no-retry rows, five positive rir_scan calls, zero controller calls for the negative row, runtime/mechanical pass, exact receipt/display/payload/provider parity, no uncovered high risk, median ≤10,000 ms, every scan ≤30,000 ms, median output ≤180 words, and no automatic begin/trace/finalize. Token fields are informational.

- [ ] **Step 3: Add deterministic hostile-input coverage**

Cover symlinks, source mutation, stale receipt, malicious paths, deep JSON, output flood, credential-shaped evidence, provider command/environment restrictions, timeout cleanup, post-score mutation, manifest binding, promotion replay, and unsupported no-replace primitives.

- [ ] **Step 4: Run full deterministic verification**

~~~bash
PYTHONPYCACHEPREFIX=/tmp/rir-fast-task6-full \
python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=/tmp/rir-fast-task6-compile \
python3 -m compileall -q skills/requirements-impact-refiner scripts evals/harness tests
git diff --check
~~~

Require one independent task review. Run only a bounded diff security review if execution/filesystem/evidence boundaries changed; never repeat a whole-branch scan.

- [ ] **Step 5: Commit**

~~~bash
git add evals/fast-scan-cases.json evals/harness/fast_scan_scoring.py evals/harness/performance.py evals/harness/run.py evals/harness/adapters/codex.py evals/harness/controller_evidence.py evals/harness/schemas/result.schema.json tests/test_fast_scan_eval_cases.py tests/test_fast_scan_scoring.py tests/test_performance_budget.py tests/test_eval_harness_codex.py tests/test_eval_harness_cli.py
git commit -m "test: gate fast impact scan behavior"
~~~

---

### Task 7: Approved Single Canary and Release Decision

**Files:**
- Create only after explicit approval and PASS: evals/results/installed-v0.4-fast-scan-canary/**
- Create only after PASS: tests/test_installed_fast_scan_canary.py
- Modify only after PASS: .gitattributes
- Modify only after release qualification: README.md
- Modify only after release qualification: README.ko.md
- Modify only after release qualification: README.ja.md

**Interfaces:**
- Consumes reviewed deterministic HEAD and an isolated installed payload with exact SHA equality.
- Produces one representative observation, not six-case or 85-run qualification.

- [ ] **Step 1: Obtain explicit approval**

Show model/reasoning, one-call count, installation changes, timeout, and restoration plan. A generic continue instruction is insufficient.

- [ ] **Step 2: Install isolated exact-payload alias**

Archive reviewed HEAD into a fresh marketplace, verify source/snapshot/cache hashes, disable the official plugin, install only the alias, and read back inventory. Record the prior official version.

- [ ] **Step 3: Run exactly one representative case**

Use GRAPH-api-mobile-cache-migration through Fast Scan. Require one rir_scan, no begin/trace/finalize, distance three, no hidden high-risk node, scan ≤30,000 ms, output ≤180 words. Never retry a failed model call.

- [ ] **Step 4: Restore unconditionally**

Remove alias and marketplace, reinstall the prior official plugin, and prove exactly one enabled RIR installation whether the canary passes, fails, or times out.

- [ ] **Step 5: Record honest status**

Failure keeps temporary evidence and not verified status. PASS may seal the single canary after independent review, but six-case and 85-run release qualification still need separate approval.

No tag, release, merge, or push is authorized here.

---

## Plan Self-Review Record

- Spec coverage: UX, derivation, private receipt, promotion, renderer, deadline, cache, compatibility, token routing, tests, and rollout map to Tasks 1–7.
- File boundaries: contract, store/renderer, controller, transports, docs, evaluation, and live evidence are independently reviewable.
- Type consistency: scan_id, receipt_id, receipt_sha256, display_text, risk_level, paths, frontier, elapsed_ms, cache_status, and can_promote are introduced once and reused.
- Safety: no provider install/network behavior, automatic promotion, live retry, full security rescan, tag, release, push, or merge.
- Placeholder scan: clean; tasks name exact files, signatures, commands, failures, and commit boundaries.
