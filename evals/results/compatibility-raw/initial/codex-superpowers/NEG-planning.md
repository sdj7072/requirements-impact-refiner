# Task 7: Cross-Client Release Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add CI and complete evidence-backed cross-client release verification for the already-approved Requirements Impact Refiner specification.

**Architecture:** The existing canonical skill, manifests, tests, adapter cases, and recorded results remain the source of truth. This task adds one GitHub Actions workflow, executes deterministic and compatibility checks, then synchronizes all three README compatibility tables with observed results before a release-ready local commit.

**Tech Stack:** GitHub Actions, Python 3.11 standard-library `unittest`, `py_compile`, repository validators, Markdown, and Git.

**Spec:** `.superpowers/sdd/2026-08-20-requirements-impact-refiner/task-7-brief.md` (approved Task 7 specification)

## Global Constraints

- The impact report and requirement are already approved; do not repeat impact refinement, recalculate impacts, or create impact artifacts.
- Run equivalent cases in each available client/environment; unavailable environments must be recorded as `blocked` with the concrete missing executable, plugin, account, or harness.
- Do not claim compatibility from manifest validation alone; compatibility claims require the documented scenario set to have run in that exact environment.
- Preserve the existing canonical skill, adapter boundaries, and neighboring workflow ownership.
- Keep English, Korean, and Japanese compatibility rows identical in product/version/status; translate only explanatory prose.
- Stop after the clean local release-ready commit; do not create a remote, push, tag, or submit to a marketplace.

---

### Task 1: Add the repository CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: The existing `tests/` suite and `skills/requirements-impact-refiner/scripts/validate-impact-report.py`.
- Produces: A GitHub Actions `ci` workflow that runs on pushes and pull requests with read-only contents permission.

- [ ] **Step 1: Create the workflow with the required checks**

Create `.github/workflows/ci.yml` with:

```yaml
name: ci

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Run standard-library tests
        run: python3 -m unittest discover -s tests -v
      - name: Compile validator
        run: python3 -m py_compile skills/requirements-impact-refiner/scripts/validate-impact-report.py
      - name: Check unfinished markers
        run: |
          if grep -RInE '\\[([T]ODO|[T]BD):|<place''holder>' skills .codex-plugin .claude-plugin README*.md; then
            exit 1
          fi
```

- [ ] **Step 2: Check the workflow diff for whitespace errors**

Run:

```bash
git diff --check -- .github/workflows/ci.yml
```

Expected: no output and exit status 0.

- [ ] **Step 3: Commit the CI workflow**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add release verification workflow"
```

### Task 2: Run deterministic release checks

**Files:**
- Read: `tests/`
- Read: `skills/requirements-impact-refiner/scripts/validate-impact-report.py`
- Read: `evals/runbook.md`

**Interfaces:**
- Consumes: Task 1’s workflow plus all existing tests, manifests, and canonical skill files.
- Produces: Verified local test output and a list of deterministic failures, if any, for correction before compatibility testing.

- [ ] **Step 1: Run the complete standard-library test suite**

```bash
python3 -m unittest discover -s tests -v
```

Expected: every discovered test passes.

- [ ] **Step 2: Compile and validate the skill and plugin packages**

```bash
python3 -m py_compile skills/requirements-impact-refiner/scripts/validate-impact-report.py
python3 /Users/p042890/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/requirements-impact-refiner
python3 /Users/p042890/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
```

Expected: all commands exit 0 with no warnings or tracebacks.

- [ ] **Step 3: Confirm no unfinished markers remain**

```bash
grep -RInE '\\[([T]ODO|[T]BD):|<place''holder>' skills .codex-plugin .claude-plugin README*.md
```

Expected: no matches; the “no matches” status is acceptable.

### Task 3: Execute the compatibility matrix and record evidence

**Files:**
- Read: `evals/cases.json`
- Read: `evals/runbook.md`
- Modify: `evals/results/with-skill.md`

**Interfaces:**
- Consumes: The 17 evaluation cases, all available clients, and the canonical skill plus adapters.
- Produces: `evals/results/with-skill.md` containing client/version/scenario results, explicit blocked environments, and no unsupported compatibility claims.

- [ ] **Step 1: Enumerate required environments**

Check these independently: Codex standalone; Codex with Superpowers; Claude Code standalone; Claude Code with Superpowers; Claude Code with feature-dev; Claude Code with Spec Kit; and a generic Agent Skills-compatible harness. Record exact client/version and whether executable, plugin, account, and harness are available.

- [ ] **Step 2: Run all 17 cases in every available environment**

Follow `evals/runbook.md`. For any client whose instructions or adapter wording changed during this task, run five repetitions of affected cases. Record observed outputs, versions, repetitions, and limitations in `evals/results/with-skill.md`. Mark unavailable environments `blocked` with the missing dependency named.

Expected: eight positive cases produce evidence-linked impacts, five negative cases remain in neighboring workflows, and four integration cases select exactly one orchestrator.

- [ ] **Step 3: Verify refinement-loop invariants**

Verify that applicable outputs show resolved, mitigated, unchanged, accepted, deferred, blocked, and new categories where applicable; accepted risk remains visible and decision-linked; and unknown evidence is never presented as verified. Record failures and rerun after correcting execution/instructions. Do not rewrite the approved impact analysis.

- [ ] **Step 4: Commit compatibility evidence**

```bash
git add evals/results/with-skill.md
git commit -m "test: record cross-client compatibility evidence"
```

### Task 4: Synchronize multilingual compatibility documentation

**Files:**
- Modify: `README.md`
- Modify: `README.ko.md`
- Modify: `README.ja.md`

**Interfaces:**
- Consumes: The observed matrix in `evals/results/with-skill.md`.
- Produces: Three documentation files with identical product/version/status rows and translated explanatory notes.

- [ ] **Step 1: Extract observed compatibility rows**

Build the row set directly from `evals/results/with-skill.md`. Each row includes exact environment, tested version, status, scenario scope, and known limitation. Add `supported` only when that exact environment completed the documented scenario set.

- [ ] **Step 2: Update all three README files**

Update the English matrix and notes, then translate the same rows into Korean and Japanese in the same order. Preserve product names, case IDs, commands, compatibility semantics, non-goals, and the warning that multiple orchestrators cannot own one run.

- [ ] **Step 3: Verify parity and links**

```bash
python3 -m unittest tests.test_documentation -v
git diff --check -- README.md README.ko.md README.ja.md
```

Expected: documentation tests pass and `git diff --check` prints nothing.

- [ ] **Step 4: Commit synchronized documentation**

```bash
git add README.md README.ko.md README.ja.md
git commit -m "docs: document verified client compatibility"
```

### Task 5: Perform final clean-tree verification and stop at the local release boundary

**Files:**
- Read: all Task 7 files and Git history

**Interfaces:**
- Consumes: CI, compatibility evidence, and multilingual documentation commits from Tasks 1–4.
- Produces: A clean local branch with release-ready history and no remote publication.

- [ ] **Step 1: Run final required checks**

```bash
python3 -m unittest discover -s tests -v
git diff --check
git status --short
```

Expected: tests pass, `git diff --check` prints nothing, and `git status --short` is empty (or contains only explicitly pre-existing unrelated changes, which must be reported rather than staged).

- [ ] **Step 2: Verify final history and branch state**

```bash
git status --short --branch
git log --oneline --decorate -8
```

Expected: clean local branch with CI, compatibility-evidence, and documentation commits alongside earlier design, evaluation, skill, validator, integration, and packaging commits.

- [ ] **Step 3: Stop before external publication**

Do not run `git remote add`, `git push`, `git tag`, GitHub repository creation, or marketplace submission. Request explicit repository-owner/organization and publication authorization before any external action.

## Self-review checklist

- [ ] Every Task 7 brief step is represented: CI, deterministic checks, compatibility matrix, behavior/negative verification, documentation synchronization, clean-tree verification, commit, and publication stop.
- [ ] No step repeats impact refinement, recalculation, or impact-report generation.
- [ ] Every compatibility claim is tied to observed scenario evidence or explicitly marked `blocked`.
- [ ] The three README matrices use identical product/version/status rows.
- [ ] No placeholder instructions or unresolved TODO/TBD markers appear in the plan.

