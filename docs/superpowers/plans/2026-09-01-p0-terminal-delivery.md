# P0 Terminal Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent same-turn implementation after impact refinement, reject generic PRD over-activation, bind evaluation to the actual delivered final, and detect product-workspace mutation.

**Architecture:** Add a machine-readable terminal bit to the finalize delivery contract and reinforce the skill's current-turn stop rule. Keep historical v0.4 controller evidence intact; add a focused v0.6 terminal-delivery verifier that binds successful finalize output to the selected final and rejects post-finalize tool activity. Snapshot each isolated evaluation workspace before a turn and reject changes outside the current `-o` output and `.requirements-impact-refiner/**`.

**Tech Stack:** Python 3 standard library, Agent Skills Markdown, MCP JSON-RPC, `unittest`.

**Spec:** `.requirements-impact-refiner/reports/RPT-007/revision-0001.md`

## Global Constraints

- Implement only P0; do not change lineage continuation identity or Delta state semantics.
- Preserve v0.3/v0.4 historical evaluation compatibility.
- Keep `.requirements-impact-refiner/**` report and graph persistence writable.
- Preserve append-only raw evidence and retained retry behavior.
- Use strict RED-GREEN TDD for every production change.

---

### Task 1: Fail-closed generic PRD admission

**Files:**
- Modify: `skills/using-requirements-impact-refiner/SKILL.md`
- Modify: `skills/requirements-impact-refiner/SKILL.md`
- Modify: `skills/requirements-impact-refiner/references/integration-generic.md`
- Modify: `evals/harness/scoring.py`
- Test: `tests/test_integration_adapters.py`
- Test: `tests/test_eval_harness_scoring.py`

**Interfaces:**
- Consumes: request text plus supplied repository evidence/scope.
- Produces: zero RIR calls for a generic PRD; anchored Fast Scan output is a negative-case mechanical failure.

- [ ] Add failing pressure tests for the exact empty generic-PRD request and for a concrete zero-evidence file/symbol request.
- [ ] Verify RED: the generic PRD currently reaches `rir_previous`/`rir_scan` or lacks an explicit pre-tool gate.
- [ ] Add the minimal pre-tool rule: substantive behavior and an inspectable evidence/scope target are both required; otherwise call neither lookup nor scan.
- [ ] Add an anchored `## Fast impact scan` negative-output backstop without matching casual uses of “scan”.
- [ ] Run `python3 -m unittest tests.test_integration_adapters tests.test_eval_harness_scoring -v`.

### Task 2: Publish and teach the terminal delivery contract

**Files:**
- Modify: `scripts/rir_mcp_server.py`
- Modify: `skills/using-requirements-impact-refiner/SKILL.md`
- Modify: `skills/requirements-impact-refiner/SKILL.md`
- Modify: `skills/requirements-impact-refiner/references/controller-workflow.md`
- Modify: `skills/requirements-impact-refiner/references/integration-generic.md`
- Modify: `skills/requirements-impact-refiner/references/integration-superpowers.md`
- Test: `tests/test_rir_mcp_server.py`
- Test: `tests/test_integration_adapters.py`
- Test: `tests/test_documentation.py`

**Interfaces:**
- Produces: `delivery_contract = {canonical: true, must_return_content_verbatim: true, terminal: true}`.
- Terminal semantics: return `display_text` byte-for-byte as the only final response and end the current turn; execution requires a later user turn.

- [ ] Change the exact MCP contract assertion first and verify RED.
- [ ] Add `terminal: True` to `_finalize` without changing persisted report schema.
- [ ] Add pressure assertions that finalize is the last workflow action and the renderer text is the only emitted output.
- [ ] Add the concise current-turn stop rule at bootstrap, main skill, controller, and both adapters.
- [ ] Run MCP, documentation, and integration-adapter tests.

### Task 3: Bind v0.6 selected finals to terminal delivery

**Files:**
- Modify: `evals/harness/controller_evidence.py`
- Modify: `evals/harness/adapters/codex.py`
- Modify: `evals/harness/run.py`
- Test: `tests/test_controller_evidence.py`
- Test: `tests/test_eval_harness_codex.py`
- Test: `tests/test_eval_harness_cli.py`

**Interfaces:**
- Add: `analyze_terminal_delivery(jsonl_streams, final_outputs) -> TerminalDeliveryEvidence`.
- Evidence requires exact successful-finalize `display_text` bytes and no post-finalize tool item; absent finalize remains a semantic-scoring concern outside this P0 verifier.
- v0.4 continues using `analyze_controller_trace`; v0.6+ records `terminal-delivery-evidence.json`.

- [ ] Add failing tests for rewritten final bytes and a command/MCP call after successful finalize.
- [ ] Implement terminal event parsing without rejecting permitted failed-finalize correction attempts before the single successful finalize.
- [ ] Enforce and persist terminal evidence in `CodexAdapter._record_result` for semantic version 0.6+.
- [ ] Before canonical-Markdown substitution, require valid terminal evidence for v0.6+ selected scoring attempts.
- [ ] Preserve the existing valid compact-delivery test with matching terminal evidence.
- [ ] Run controller, Codex adapter, and CLI harness tests.

### Task 4: Detect isolated product-workspace mutation

**Files:**
- Modify: `evals/harness/adapters/codex.py`
- Test: `tests/test_eval_harness_codex.py`

**Interfaces:**
- Add: `_snapshot_guarded_workspace(workspace_root) -> fingerprint`.
- Add: `_workspace_mutation(expected, workspace_root, allowed_output) -> integrity payload`.
- Exclude only a real `.requirements-impact-refiner/**` subtree and the current direct-child output file.

- [ ] Add failing tests for overwrite, delete, chmod, atomic same-byte replacement, symlink replacement, extra file, `.requirements-impact-refiner.json` mutation, and turn-2 predecessor mutation.
- [ ] Add passing tests for report/graph-only writes and normal final-output creation.
- [ ] Implement lstat-based, no-follow fingerprints for directories, regular files, and symlinks.
- [ ] Record a content-free `workspace-integrity.json`; classify mutation as `INVALID_EVIDENCE` and inspection failure as `INFRA_ERROR`.
- [ ] Run the complete Codex adapter test module.

### Task 5: Verify, package, and reinstall

**Files:**
- Verify all modified files and generated plugin metadata.

- [ ] Run focused P0 test modules and `git diff --check`.
- [ ] Temporarily isolate large untracked evaluation outputs and run `python3 -m unittest discover -s tests -q`; restore outputs immediately.
- [ ] Run the repository quality command and skill quick validation.
- [ ] Review the diff to confirm no P1 lineage/Delta files changed.
- [ ] Reinstall the local plugin using the plugin-creator cachebuster flow and verify the enabled installed version/payload.
