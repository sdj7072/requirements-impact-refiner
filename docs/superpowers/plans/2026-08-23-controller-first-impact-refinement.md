# Controller-First Impact Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local MCP+CLI controller that creates a draft before analysis and permits final output only after validated compact-state publication and renderer completion.

**Architecture:** A standard-library controller library owns draft lifecycle, canonical ID allocation, state construction, validation, publication, and rendering. A thin CLI provides hard enforcement; a minimal stdio MCP server exposes the same begin/finalize operations to Codex and Claude. The Agent Skill becomes a two-tool positive recipe.

**Tech Stack:** Python 3 standard library, JSON-RPC 2.0 over stdio, MCP tools, JSON, `unittest`, existing compact-state/renderer/report-store modules.

**Spec:** `docs/superpowers/specs/2026-08-23-controller-first-impact-refinement-design.md`

## Global Constraints

- No runtime dependency, network client, shell execution, dynamic import from user paths, or Python object deserialization.
- Repository root is resolved and pinned at begin; finalize must use the same root.
- Begin input is at most 256 KiB; finalize input is at most 2 MiB; each string is at most 64 KiB.
- Draft IDs are `secrets.token_hex(16)` and caller-selected IDs are rejected.
- Draft files are exclusive, mode 0600 where supported, repository-local, and single-use only after successful publication.
- The controller allocates canonical IDs and calculates Delta; the model supplies semantic rows with local keys.
- A clarification is a complete pre-decision state rendered by the controller, never a standalone question.
- CLI finalize prints renderer output only on success; validation failures produce no display text.
- MCP skips remain mechanically invalid, because hosts cannot be forced to call tools.
- Existing compact/full, Markdown lineage, 0.3.x compatibility, and append-only report contracts remain intact.
- Fresh smoke starts only after deterministic tests and independent review; 85-run starts only after smoke PASS.

---

### Task C1: Controller Draft and Finalize Engine

**Files:**
- Create: `skills/requirements-impact-refiner/scripts/rir_controller.py`
- Create: `scripts/rir_controller.py`
- Create: `skills/requirements-impact-refiner/schemas/controller-analysis.schema.json`
- Create: `schemas/controller-analysis.schema.json`
- Create: `tests/fixtures/controller-analysis-pre-decision.json`
- Create: `tests/fixtures/controller-analysis-post-decision.json`
- Create: `tests/test_rir_controller.py`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Produces `BeginRequest`, `DraftResult`, `FinalizeRequest`, `FinalizeResult`, `begin_refinement()`, `finalize_refinement()`, and `load_draft()`.
- Reuses `resolve-settings.py`, `compact_state.py`, `impact_renderer.py`, and `report_store.py` through stable library functions.

- [ ] **Step 1: Write failing begin/draft tests**

```python
def test_begin_creates_repository_bound_private_draft(self):
    result = CONTROLLER.begin_refinement(CONTROLLER.BeginRequest(
        repo_root=self.root,
        request="Let workspace members edit every project.",
        repository_evidence=("authorizeProjectEdit permits owner and admin",),
        adapter="generic",
    ))
    self.assertRegex(result.draft_id, r"^[0-9a-f]{32}$")
    self.assertEqual(result.report_id, "RPT-001")
    self.assertEqual(result.revision, 1)
    self.assertEqual(result.previous_sha256, "none")
    self.assertEqual(result.settings["delivery"], "compact")
    self.assertEqual(result.draft_path.stat().st_mode & 0o777, 0o600)

def test_begin_rejects_oversized_request_and_non_directory_root(self):
    with self.assertRaisesRegex(ValueError, "256 KiB"):
        CONTROLLER.begin_refinement(self.request(request="x" * (256 * 1024 + 1)))
    file_root = self.root / "file"
    file_root.write_text("x")
    with self.assertRaisesRegex(ValueError, "repository root"):
        CONTROLLER.begin_refinement(self.request(repo_root=file_root))
```

- [ ] **Step 2: Run RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-c1-red python3 -m unittest tests.test_rir_controller -v
```

Expected: module/schema/fixtures are missing.

- [ ] **Step 3: Implement begin and safe draft storage**

Use frozen dataclasses with these required fields:

```python
@dataclass(frozen=True)
class BeginRequest:
    repo_root: Path
    request: str
    repository_evidence: tuple[str, ...]
    adapter: str
    audience_override: str | None = None
    delivery_override: str | None = None

@dataclass(frozen=True)
class DraftResult:
    draft_id: str
    draft_path: Path
    report_id: str
    revision: int
    previous_sha256: str
    settings: Mapping[str, str]
    prior_state: Mapping[str, object] | None
```

For Python 3.9 source compatibility use `Optional[...]` in the implementation. Create `.requirements-impact-refiner/drafts`, reject symlinks, use exclusive `xb`, chmod 0600, and store canonical JSON with root identity, request hash, evidence, adapter, report metadata, settings, prior pointer, `consumed: false`, and creation timestamp.

- [ ] **Step 4: Write failing finalize/ID/Delta tests**

```python
def test_predecision_finalize_allocates_ids_and_embeds_question(self):
    draft = CONTROLLER.begin_refinement(self.request())
    result = CONTROLLER.finalize_refinement(CONTROLLER.FinalizeRequest(
        repo_root=self.root,
        draft_id=draft.draft_id,
        analysis=self.fixture("controller-analysis-pre-decision.json"),
    ))
    self.assertEqual(result.status, "published")
    self.assertIn("IMP-001", result.display_text)
    self.assertIn("Decision needed", result.display_text)
    self.assertEqual(result.revision, 1)
    self.assertTrue(result.state_path.is_file())

def test_finalize_calculates_delta_and_never_accepts_model_ids(self):
    analysis = self.fixture("controller-analysis-post-decision.json")
    analysis["impacts"][0]["id"] = "IMP-999"
    with self.assertRaisesRegex(ValueError, "unknown analysis key id"):
        CONTROLLER.finalize_refinement(self.finalize(analysis))
```

Also test local-key relationship resolution, stable prior key-to-ID mapping, silent deletion rejection, accepted/decision coupling, blocked owner, future criteria not evidence, wrong root, unknown/stale/consumed draft, finalize size, publication failure preserving reusable draft, and successful consumption.

- [ ] **Step 5: Implement normalized analysis to compact state**

The analysis schema uses `additionalProperties: false`. Local keys match `^[a-z][a-z0-9_-]{0,63}$`. Allocate IDs by sorted stable input order for revision 1; preserve prior `source_key` mappings on revisions. Calculate Delta from prior state with the existing domain functions. Build phase-specific decision structures, validate compact state, publish, render, then atomically mark draft consumed.

- [ ] **Step 6: Verify GREEN and mirrors**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-c1-green python3 -m unittest tests.test_rir_controller tests.test_compact_state tests.test_report_store tests.test_impact_renderer tests.test_packaging -v
cmp skills/requirements-impact-refiner/scripts/rir_controller.py scripts/rir_controller.py
cmp skills/requirements-impact-refiner/schemas/controller-analysis.schema.json schemas/controller-analysis.schema.json
```

- [ ] **Step 7: Commit**

```sh
git add skills/requirements-impact-refiner/scripts/rir_controller.py scripts/rir_controller.py skills/requirements-impact-refiner/schemas/controller-analysis.schema.json schemas/controller-analysis.schema.json tests/fixtures/controller-analysis-pre-decision.json tests/fixtures/controller-analysis-post-decision.json tests/test_rir_controller.py tests/test_packaging.py
git commit -m "feat: add controller-first impact engine"
```

---

### Task C2: Hard-Enforcement CLI

**Files:**
- Create: `skills/requirements-impact-refiner/scripts/rir-controller.py`
- Create: `scripts/rir-controller.py`
- Create: `tests/test_rir_controller_cli.py`

**Interfaces:**
- `begin --repo-root REPO --input REQUEST.json` emits structured JSON.
- `finalize --repo-root REPO --draft-id ID --input ANALYSIS.json` emits only renderer-owned display text on success.

- [ ] **Step 1: Write failing CLI exit/output tests**

```python
def test_finalize_stdout_is_exact_renderer_output(self):
    begin = self.run_cli("begin", "--repo-root", self.root, "--input", self.begin_json)
    draft_id = json.loads(begin.stdout)["draft_id"]
    result = self.run_cli("finalize", "--repo-root", self.root,
                          "--draft-id", draft_id, "--input", self.analysis_json)
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(result.stdout, expected_compact_text)

def test_invalid_finalize_has_no_display_stdout(self):
    result = self.run_cli("finalize", "--repo-root", self.root,
                          "--draft-id", self.draft_id, "--input", self.invalid_json)
    self.assertEqual(result.returncode, 1)
    self.assertEqual(result.stdout, "")
```

Cover malformed UTF-8/JSON, oversized input, missing files, invalid root, unknown command, consumed draft, and full delivery.

- [ ] **Step 2: Run RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-c2-red python3 -m unittest tests.test_rir_controller_cli -v
```

- [ ] **Step 3: Implement thin CLI**

Parse files strictly, construct controller requests, print sorted JSON for begin, print `FinalizeResult.display_text` verbatim for finalize, and map controller validation to exit 1 and invocation/I/O to exit 2. Do not duplicate business logic.

- [ ] **Step 4: Mirror, verify, commit**

```sh
cp skills/requirements-impact-refiner/scripts/rir-controller.py scripts/rir-controller.py
PYTHONPYCACHEPREFIX=/tmp/rir-c2-green python3 -m unittest tests.test_rir_controller_cli tests.test_rir_controller -v
git add skills/requirements-impact-refiner/scripts/rir-controller.py scripts/rir-controller.py tests/test_rir_controller_cli.py
git commit -m "feat: add enforced impact controller CLI"
```

---

### Task C3: MCP Server and Plugin Packaging

**Files:**
- Create: `scripts/rir_mcp_server.py`
- Create: `scripts/launch-rir-mcp`
- Create: `.mcp.json`
- Modify: `.codex-plugin/plugin.json`
- Modify: `tests/test_rir_mcp_server.py`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- JSON-RPC methods: `initialize`, `tools/list`, `tools/call`.
- MCP tools: `rir_begin`, `rir_finalize`.

- [ ] **Step 1: Write failing protocol and package tests**

Feed newline-delimited JSON-RPC requests through a subprocess and assert exact IDs, protocol version, tool schemas, structured content, bounded errors, continued processing after safe errors, and clean EOF shutdown.

```python
def test_tools_list_exposes_only_controller_tools(self):
    replies = self.exchange([
        request(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}),
        request(2, "tools/list", {}),
    ])
    self.assertEqual([tool["name"] for tool in replies[1]["result"]["tools"]], ["rir_begin", "rir_finalize"])
```

Packaging tests require `.mcp.json` command `./scripts/launch-rir-mcp`, `cwd: "."`, no URL, no inherited credential env vars, executable launcher, and matching manifest MCP declaration only when supported by the checked-in validator contract.

- [ ] **Step 2: Run RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-c3-red python3 -m unittest tests.test_rir_mcp_server tests.test_packaging -v
```

- [ ] **Step 3: Implement minimal stdio server**

Read one JSON object per line with a 2 MiB line cap. Return JSON-RPC 2.0 responses on stdout only; diagnostics go to stderr. `rir_begin` and `rir_finalize` validate argument schemas before calling `rir_controller`. MCP finalize returns `display_text` in text content plus structured metadata. Unknown methods/tools and malformed params return standard bounded errors without shell or network access.

Launcher:

```sh
#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${PYTHON:-python3}" "$SCRIPT_DIR/rir_mcp_server.py"
```

- [ ] **Step 4: Verify protocol, package, and security behavior**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-c3-green python3 -m unittest tests.test_rir_mcp_server tests.test_packaging tests.test_distribution -v
python3 -m json.tool .mcp.json >/dev/null
```

- [ ] **Step 5: Commit**

```sh
git add scripts/rir_mcp_server.py scripts/launch-rir-mcp .mcp.json .codex-plugin/plugin.json tests/test_rir_mcp_server.py tests/test_packaging.py
git commit -m "feat: expose impact controller over MCP"
```

---

### Task C4: Skill Recipe, Harness Evidence, and Fresh Smoke

**Files:**
- Modify: `skills/requirements-impact-refiner/SKILL.md`
- Create: `skills/requirements-impact-refiner/references/controller-workflow.md`
- Create: `references/controller-workflow.md`
- Modify: `evals/harness/adapters/codex.py`
- Modify: `evals/harness/performance.py`
- Modify: `evals/harness/schemas/result.schema.json`
- Modify: `tests/test_resource_routing.py`
- Modify: `tests/test_eval_harness_codex.py`
- Modify: `tests/test_performance_budget.py`
- Modify: `tests/test_documentation.py`

**Interfaces:**
- Skill recipe: `rir_begin` → evidence analysis → `rir_finalize` → return `display_text` verbatim.
- Harness captures tool-call evidence and byte-equality between MCP `display_text` and final output.

- [ ] **Step 1: Write RED skill/harness tests**

Tests require the normal path to name only the two MCP tools, prohibit manual JSON authoring in the core recipe, and keep CLI/full-inline fallbacks explicit. Fake Codex JSONL includes begin/finalize tool events; adapter evidence must preserve them. Performance observations require one begin, one successful finalize, and final-output equality for every non-negative smoke case.

- [ ] **Step 2: Run RED**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-c4-red python3 -m unittest tests.test_resource_routing tests.test_eval_harness_codex tests.test_performance_budget tests.test_documentation -v
```

- [ ] **Step 3: Rewrite the skill as a positive tool recipe**

Keep core under 320 words. Normal MCP mode contains exactly five actions: select adapter, call `rir_begin`, inspect evidence using returned predicates, call `rir_finalize`, return `display_text`. Pre-decision questions are finalize input. CLI fallback uses the same begin/finalize engine. Full-inline is used only when neither MCP nor CLI is available.

- [ ] **Step 4: Capture and gate controller evidence**

Parse raw JSONL tool-call/result events without trusting prose. Record draft ID, tool order, finalize status, display-text digest, final-output digest, and state/Markdown parity. Gate skips, duplicate calls, finalize-before-begin, mismatched draft IDs, tool errors, and output mismatch.

- [ ] **Step 5: Full deterministic verification and independent review**

```sh
PYTHONPYCACHEPREFIX=/tmp/rir-c4-full python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=/tmp/rir-c4-compile python3 -m compileall -q skills/requirements-impact-refiner scripts evals/harness tests
git diff --check
```

Require independent code/security review with no Critical or Important findings before installation.

- [ ] **Step 6: Install isolated plugin and run one fresh smoke**

Preserve prior diagnostic directories under their existing names and use a new empty `evals/results/installed-v0.4-controller-smoke` directory. Run exactly six cases once with user-selected `gpt-5.6-sol/high`. Stop before 85 runs unless runtime, mechanical, controller, semantic, and performance gates all pass.

- [ ] **Step 7: Commit reviewed deterministic work and sealed smoke separately**

```sh
git add skills/requirements-impact-refiner/SKILL.md skills/requirements-impact-refiner/references/controller-workflow.md references/controller-workflow.md evals/harness tests
git commit -m "feat: require controller-first impact delivery"
```

After independent evidence review, commit only the approved sealed smoke tree and its pinning tests.

---

## Continuation

On controller smoke PASS, resume Task 8 of `2026-08-23-compact-impact-delivery.md`: full 85-run evaluation, community files, metadata, tag, and Public Preview release. On smoke failure, stop and report the exact controller or host boundary; do not add another prose-only skill fix.

## Plan Self-Review Record

- Coverage: controller engine, CLI, MCP, packaging, security limits, tool recipe, evidence capture, smoke, and prior-plan continuation are mapped to C1–C4.
- Interfaces: `rir_controller` is the single business layer used by CLI and MCP; finalize returns the renderer-owned text consumed by both.
- Placeholders: no deferred code or unspecified error behavior remains; fresh smoke values are execution evidence, not plan constants.
- Scope: the amendment replaces the unreliable model-owned orchestration while preserving completed compact state/render/store work.
