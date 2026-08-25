# v0.6 Controller and Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose the controller behind a byte-compatible facade and prove a pinned ast-grep provider against licensed real corpora.

**Architecture:** Extract one controller responsibility at a time after capturing its observable contract. The default runtime remains standard-library-only; ast-grep 0.45.0 is a development/release canary and an optional detected provider.

**Tech Stack:** Python 3.9+ standard library; ast-grep-cli 0.45.0; existing MCP/CLI contracts; BSD-3-Clause `pallets/click` corpus; MIT `sindresorhus/slugify` corpus.

**Spec:** `docs/superpowers/specs/2026-08-25-v0.6-production-readiness-design.md`

**Pinned external sources:** [ast-grep-cli 0.45.0](https://pypi.org/project/ast-grep-cli/0.45.0/), [ast-grep JSON stream contract](https://ast-grep.github.io/reference/cli/scan), [pallets/click](https://github.com/pallets/click/tree/68e7ea7228ca144c52e4d1d282cc09da59f7771f), [sindresorhus/slugify](https://github.com/sindresorhus/slugify/tree/7c318bd1aa4b4affab29761f15a9604323fe2a3b).

## Global Constraints

- Complete `docs/superpowers/plans/2026-08-25-v06-quality-foundation.md` first.
- `scripts/rir_controller.py` remains the stable public import facade.
- CLI stdout/stderr, MCP results, canonical JSON/Markdown, file modes, and exceptions remain compatible.
- Every new root module has an identical installed-skill mirror.
- ast-grep is never auto-installed by plugin runtime code.
- External corpus files are fetched only by an explicit evaluation command and never enter the plugin payload.

---

### Task 1: Seal the controller facade contract

**Files:**
- Create: `tests/test_rir_controller_facade.py`
- Create: `tests/fixtures/rir-controller-facade-v05.json`
- Modify: `scripts/payload_identity.py`

**Interfaces:**
- Consumes: current `rir_controller` public dataclasses and entry points
- Produces: literal facade inventory and representative byte-level outputs

- [ ] **Step 1: Write the characterization test**

```python
PUBLIC_NAMES = (
    "BeginRequest", "DraftResult", "ScanRequest", "TraceRequest",
    "TraceResult", "FinalizeRequest", "FinalizeResult",
    "scan_impact", "begin_refinement", "load_draft", "trace_impact",
    "finalize_refinement",
)

def test_public_facade_inventory_matches_v05_fixture(self):
    fixture = json.loads(FIXTURE.read_text())
    self.assertEqual(sorted(PUBLIC_NAMES), fixture["public_names"])
    for name in PUBLIC_NAMES:
        self.assertTrue(hasattr(CONTROLLER, name), name)
```

Capture one successful and one rejected begin/trace/finalize flow with literal canonical digests, result fields, exception type, and error text. Do not derive expected values through the controller under test.

- [ ] **Step 2: Run and confirm the fixture is absent**

Run: `python3 -m unittest -q tests.test_rir_controller_facade`

Expected: FAIL because the facade fixture does not exist.

- [ ] **Step 3: Create the hand-checked fixture and payload inventory entry**

Generate candidate bytes once, inspect them, and write their literal values to `rir-controller-facade-v05.json`. Add each future internal module path to `payload_identity.ROOT_FILES` before extraction so cache identity changes with implementation.

- [ ] **Step 4: Verify and commit**

Run: `python3 -m unittest -q tests.test_rir_controller_facade tests.test_rir_controller tests.test_rir_controller_cli tests.test_rir_mcp_server`

```bash
git add tests/test_rir_controller_facade.py tests/fixtures/rir-controller-facade-v05.json scripts/payload_identity.py
git commit -m "test: seal controller facade contract"
```

### Task 2: Extract request contracts and bounded validation

**Files:**
- Create: `scripts/rir_contracts.py`
- Create: `skills/requirements-impact-refiner/scripts/rir_contracts.py`
- Modify: `scripts/rir_controller.py:114-187,256-277,3170-3245`
- Test: `tests/test_rir_contracts.py`

**Interfaces:**
- Produces: `BeginRequest`, `DraftResult`, `ScanRequest`, `TraceRequest`, `TraceResult`, `FinalizeRequest`, `FinalizeResult`, `canonical_bytes`, `bounded_bytes`, `validate_analysis`
- Consumes: no controller storage or graph modules

- [ ] **Step 1: Write import and validation parity tests**

```python
def test_facade_reexports_contract_types(self):
    self.assertIs(CONTROLLER.BeginRequest, CONTRACTS.BeginRequest)
    self.assertIs(CONTROLLER.FinalizeRequest, CONTRACTS.FinalizeRequest)

def test_analysis_errors_match_facade_fixture(self):
    with self.assertRaisesRegex(ValueError, "post-decision analysis requires decisions only"):
        CONTRACTS.validate_analysis(INVALID_POST_DECISION)
```

- [ ] **Step 2: Run and confirm the module is missing**

Run: `python3 -m unittest -q tests.test_rir_contracts`

- [ ] **Step 3: Move only contract code and re-export it**

`rir_controller.py` imports and re-exports the exact names. Keep dataclass field order and frozen semantics unchanged. Do not move storage or state-building code in this task.

- [ ] **Step 4: Verify parity and commit**

Run: `python3 -m unittest -q tests.test_rir_contracts tests.test_rir_controller_facade tests.test_rir_controller`

```bash
git add scripts/rir_contracts.py skills/requirements-impact-refiner/scripts/rir_contracts.py scripts/rir_controller.py skills/requirements-impact-refiner/scripts/rir_controller.py tests/test_rir_contracts.py
git commit -m "refactor: extract controller contracts"
```

### Task 3: Extract private storage, lock, CAS, and recovery

**Files:**
- Create: `scripts/rir_storage.py`
- Create: `skills/requirements-impact-refiner/scripts/rir_storage.py`
- Modify: `scripts/rir_controller.py:194-255,520-1829,3515-3647`
- Test: `tests/test_rir_storage.py`

**Interfaces:**
- Produces: `root_path`, `write_private_draft`, `load_private_draft`, `cas_replace_private_draft`, `recover_private_draft_transaction`, `report_lock`, `write_controller_metadata`, `consume_draft`
- Consumes: request identifiers and byte bounds from `rir_contracts`

- [ ] **Step 1: Write filesystem parity tests**

```python
def test_private_draft_modes_and_cas_failure_are_stable(self):
    path = STORAGE.write_private_draft(root, DRAFT_ID, b"{}")
    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
    with self.assertRaisesRegex(ValueError, "draft changed during refinement"):
        STORAGE.cas_replace_private_draft(root, DRAFT_ID, b"wrong", b"new")
```

Add controlled crash-phase fixtures for quarantine, rename, replacement, cleanup, and lock contention; assert exact surviving files and modes.

- [ ] **Step 2: Run the storage tests before extraction**

Run: `python3 -m unittest -q tests.test_rir_storage`

Expected: FAIL because `rir_storage` is absent.

- [ ] **Step 3: Move storage code without rewriting algorithms**

Copy the existing functions, keep private constants and transaction schemas with them, import through the facade, and delete the original definitions only after parity tests pass. Correct the tracked lock-file problem by creating lock files at runtime and refusing version-controlled lock artifacts in packaging tests.

- [ ] **Step 4: Verify crash recovery and commit**

Run: `python3 -m unittest -q tests.test_rir_storage tests.test_rir_controller tests.test_rir_controller_cli tests.test_report_store`

```bash
git add scripts/rir_storage.py skills/requirements-impact-refiner/scripts/rir_storage.py scripts/rir_controller.py skills/requirements-impact-refiner/scripts/rir_controller.py tests/test_rir_storage.py tests/test_packaging.py
git commit -m "refactor: extract controller storage transactions"
```

### Task 4: Extract graph binding and compact delivery

**Files:**
- Create: `scripts/rir_graph_delivery.py`
- Create: `skills/requirements-impact-refiner/scripts/rir_graph_delivery.py`
- Modify: `scripts/rir_controller.py:1831-3169`
- Test: `tests/test_rir_graph_delivery.py`

**Interfaces:**
- Produces: `compact_graph`, `source_inventory_sha256`, `new_trace_intent`, `validate_trace_intent`, `load_graph_context`, `validate_graph_coverage`, `trace_impact`
- Consumes: storage primitives and graph coordinator/contract modules

- [ ] **Step 1: Write graph parity and mutation tests**

```python
def test_compact_graph_matches_facade_bytes(self):
    expected = json.dumps(EXPECTED_COMPACT, sort_keys=True, separators=(",", ":"))
    actual = json.dumps(DELIVERY.compact_graph(RECEIPT), sort_keys=True, separators=(",", ":"))
    self.assertEqual(actual, expected)

def test_uncovered_high_risk_node_is_rejected(self):
    with self.assertRaisesRegex(ValueError, "uncovered high-risk graph node NODE-009"):
        DELIVERY.validate_graph_coverage(ANALYSIS, CONTEXT)
```

- [ ] **Step 2: Run the red tests**

Run: `python3 -m unittest -q tests.test_rir_graph_delivery`

- [ ] **Step 3: Extract graph code and retain facade wrappers**

Keep `COMPACT_MAX_NODES = 48`, `COMPACT_MAX_PATHS = 16`, `COMPACT_MAX_FRONTIER = 16`, and `COMPACT_MAX_BYTES = 24000`. Preserve receipt-binding transaction order and exact error strings.

- [ ] **Step 4: Verify and commit**

Run: `python3 -m unittest -q tests.test_rir_graph_delivery tests.test_compact_graph_bounds tests.test_graph_cache tests.test_graph_coordinator tests.test_rir_controller`

```bash
git add scripts/rir_graph_delivery.py skills/requirements-impact-refiner/scripts/rir_graph_delivery.py scripts/rir_controller.py skills/requirements-impact-refiner/scripts/rir_controller.py tests/test_rir_graph_delivery.py
git commit -m "refactor: extract graph delivery controller"
```

### Task 5: Extract lineage and finalize orchestration

**Files:**
- Create: `scripts/rir_lineage.py`
- Create: `scripts/rir_finalize.py`
- Create: `skills/requirements-impact-refiner/scripts/rir_lineage.py`
- Create: `skills/requirements-impact-refiner/scripts/rir_finalize.py`
- Modify: `scripts/rir_controller.py:278-519,3170-3710`
- Test: `tests/test_rir_lineage.py`
- Test: `tests/test_rir_finalize.py`

**Interfaces:**
- `rir_lineage` produces `current_lineage`, `legacy_key_map`, `allocate_ids`, `map_keys`, `build_state`
- `rir_finalize` produces `finalize_refinement`
- Facade re-exports `finalize_refinement` and all result types

- [ ] **Step 1: Write revision and final-byte parity tests**

```python
def test_revision_two_preserves_ids_and_delta(self):
    state = LINEAGE.build_state(DRAFT, ANALYSIS, GRAPH_CONTEXT)
    self.assertEqual(state["report"]["revision"], 2)
    self.assertEqual(state["impacts"][0]["id"], "IMP-001")
    self.assertEqual(state["delta"]["unchanged"], ["IMP-001"])

def test_facade_finalize_matches_canonical_markdown_digest(self):
    result = FINALIZE.finalize_refinement(REQUEST)
    self.assertEqual(result.markdown_sha256, EXPECTED_SHA256)
```

- [ ] **Step 2: Run the red tests**

Run: `python3 -m unittest -q tests.test_rir_lineage tests.test_rir_finalize`

- [ ] **Step 3: Extract lineage first, then finalize**

Move key allocation and pure state transitions before moving publish orchestration. Finalize imports contracts, storage, graph delivery, and lineage; it does not reach into their private functions.

- [ ] **Step 4: Run facade and full controller tests**

Run: `python3 -m unittest -q tests.test_rir_lineage tests.test_rir_finalize tests.test_rir_controller_facade tests.test_rir_controller tests.test_rir_controller_cli tests.test_rir_mcp_server`

- [ ] **Step 5: Commit**

```bash
git add scripts/rir_lineage.py scripts/rir_finalize.py skills/requirements-impact-refiner/scripts/rir_lineage.py skills/requirements-impact-refiner/scripts/rir_finalize.py scripts/rir_controller.py skills/requirements-impact-refiner/scripts/rir_controller.py tests/test_rir_lineage.py tests/test_rir_finalize.py
git commit -m "refactor: extract lineage and finalize orchestration"
```

### Task 6: Add the pinned ast-grep 0.45.0 canary

**Files:**
- Create: `requirements-provider-canary.txt`
- Create: `evals/ast-grep-canary/sgconfig.yml`
- Create: `evals/ast-grep-canary/rules/imports.yml`
- Create: `evals/ast-grep-canary/expected.json`
- Create: `scripts/run-ast-grep-canary.py`
- Test: `tests/test_ast_grep_canary.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `ast-grep-cli==0.45.0`; adapter `ProviderResult`
- Produces: deterministic `--json=stream` observations and adapter receipt comparison

- [ ] **Step 1: Write the failing canary test**

```python
def test_canary_requires_exact_version_and_json_stream(self):
    result = subprocess.run(
        [sys.executable, "scripts/run-ast-grep-canary.py", "--print-command"],
        text=True, capture_output=True, check=True,
    )
    self.assertEqual(result.stdout.strip(), "ast-grep scan --json=stream --config evals/ast-grep-canary/sgconfig.yml evals/ast-grep-canary/fixture")
```

- [ ] **Step 2: Run and confirm the canary is absent**

Run: `python3 -m unittest -q tests.test_ast_grep_canary`

- [ ] **Step 3: Add pinned provider and read-only runner**

`requirements-provider-canary.txt` contains `ast-grep-cli==0.45.0`. The runner verifies `ast-grep --version`, refuses rewrite/update flags, parses JSONL, compares literal expected matches, and invokes `graph_adapter_ast_grep` against the same fixture.

- [ ] **Step 4: Execute locally and in CI**

Run: `.quality-venv/bin/pip install -r requirements-provider-canary.txt`

Run: `.quality-venv/bin/python scripts/run-ast-grep-canary.py`

Expected: exact match set, provenance digest parity, and no repository mutation.

- [ ] **Step 5: Commit**

```bash
git add requirements-provider-canary.txt evals/ast-grep-canary scripts/run-ast-grep-canary.py tests/test_ast_grep_canary.py .github/workflows/ci.yml
git commit -m "test: add pinned ast-grep provider canary"
```

### Task 7: Add licensed public-corpus precision and recall

**Files:**
- Create: `evals/corpora/catalog.json`
- Create: `evals/corpora/expected-relationships.json`
- Create: `evals/corpora/LICENSES/pallets-click.txt`
- Create: `evals/corpora/LICENSES/sindresorhus-slugify.txt`
- Create: `scripts/fetch-graph-corpora.py`
- Create: `scripts/score-graph-corpora.py`
- Test: `tests/test_graph_corpus.py`

**Interfaces:**
- Consumes: `pallets/click@68e7ea7228ca144c52e4d1d282cc09da59f7771f` and `sindresorhus/slugify@7c318bd1aa4b4affab29761f15a9604323fe2a3b`
- Produces: path/digest-pinned corpus checkout outside the plugin payload and literal precision/recall report

- [ ] **Step 1: Write catalog and traversal tests**

```python
def test_corpus_catalog_is_pinned_and_licensed(self):
    self.assertEqual(CATALOG[0]["commit"], "68e7ea7228ca144c52e4d1d282cc09da59f7771f")
    self.assertEqual(CATALOG[0]["license"], "BSD-3-Clause")
    self.assertEqual(CATALOG[1]["commit"], "7c318bd1aa4b4affab29761f15a9604323fe2a3b")
    self.assertEqual(CATALOG[1]["license"], "MIT")
```

- [ ] **Step 2: Run and confirm corpus files are missing**

Run: `python3 -m unittest -q tests.test_graph_corpus`

- [ ] **Step 3: Implement explicit fetch and scoring**

The fetch script accepts `--destination`, clones only the pinned commit, verifies the remote URL and license digest, and refuses a destination inside the repository. The scoring script runs built-in and ast-grep paths, compares hand-curated relationships, and writes precision, recall, unknown-frontier count, duration, and compact bytes.

- [ ] **Step 4: Establish literal gates**

Require precision at least 0.90, recall at least 0.80, no undisclosed high-risk miss, median runtime at most 10 seconds, hard runtime at most 30 seconds, and compact output at most 24,000 bytes.

- [ ] **Step 5: Verify and commit**

Run: `.quality-venv/bin/python scripts/fetch-graph-corpora.py --destination /tmp/rir-v06-corpora`

Run: `.quality-venv/bin/python scripts/score-graph-corpora.py --corpora /tmp/rir-v06-corpora`

```bash
git add evals/corpora scripts/fetch-graph-corpora.py scripts/score-graph-corpora.py tests/test_graph_corpus.py
git commit -m "eval: gate graph precision on pinned corpora"
```

### Task 8: Controller/graph review gate

**Files:**
- Verify only: all Task 1-7 changes

**Interfaces:**
- Consumes: decomposed controller and real graph evidence
- Produces: green reviewed commit eligible for UX/evidence work

- [ ] **Step 1: Run quality, facade, provider, corpus, and full tests**

Run: `.quality-venv/bin/python scripts/run-quality-gates.py`

Run: `.quality-venv/bin/python scripts/run-ast-grep-canary.py`

Run: `.quality-venv/bin/python scripts/score-graph-corpora.py --corpora /tmp/rir-v06-corpora`

- [ ] **Step 2: Request independent architecture and security reviews**

Architecture review checks module ownership, cycles, facade parity, and byte identity. Security review checks locks, descriptor-relative traversal, CAS recovery, subprocess snapshots, corpus paths, and provider output bounds.

- [ ] **Step 3: Commit review fixes**

```bash
git add -u
git commit -m "fix: close controller and graph review findings"
```
