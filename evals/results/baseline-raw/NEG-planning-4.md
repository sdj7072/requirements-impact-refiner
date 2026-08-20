# Requirements Impact Refiner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the approved specification into implementation-ready coding tasks without duplicating impact-report approval work.

**Architecture:** The supplied request contains no specification contents, repository paths, acceptance criteria, interfaces, or technology details. Therefore this artifact records the minimum safe intake and decomposition work required before implementation tasks can be authored; it does not invent code changes.

**Tech Stack:** Not specified in the supplied request; determine from the target repository after the approved specification is supplied.

**Spec:** Approved specification contents were not included in the supplied request.

**Repository fact:** The impact report is already approved; no task should re-run or seek approval for that report.

**Status:** Blocked for concrete coding-task generation until the approved specification (or a path/reference to it) is provided. Any concrete file, API, schema, dependency, or test task would otherwise be fabricated.

**Next required input:** Provide the approved specification text or its exact repository path, including its acceptance criteria and any explicitly approved constraints.

---

### Task 1: Ingest the approved specification

**Files:**
- Read: `[approved specification path]`
- Modify: `.superpowers/sdd/2026-08-20-requirements-impact-refiner/baseline-raw/NEG-planning-4.md`

**Interfaces:**
- Consumes: The approved specification, including requirements, acceptance criteria, constraints, and named system boundaries.
- Produces: A requirements-to-files matrix with exact repository paths and test surfaces.

- [ ] **Step 1: Record each requirement verbatim with a stable identifier.**
- [ ] **Step 2: Record the acceptance test or observable behavior for every identifier.**
- [ ] **Step 3: Record constraints that apply globally, including version floors, dependency limits, naming/copy rules, and platform requirements.**
- [ ] **Step 4: Map each identifier to existing or new files after inspecting the repository.**
- [ ] **Step 5: Confirm that no task repeats impact-report approval, which is already complete.**

### Task 2: Decompose the requirements into independently testable coding tasks

**Files:**
- Modify: `.superpowers/sdd/2026-08-20-requirements-impact-refiner/baseline-raw/NEG-planning-4.md`
- Test: Exact test files identified by Task 1 after repository inspection.

**Interfaces:**
- Consumes: The requirements-to-files matrix produced by Task 1.
- Produces: Ordered tasks with exact create/modify/test paths, interfaces, failing tests, implementation steps, verification commands, and commit boundaries.

- [ ] **Step 1: Group requirements by independently reviewable subsystem and keep each task small enough to have its own test cycle.**
- [ ] **Step 2: For each task, name exact files and define every consumed and produced symbol or data shape.**
- [ ] **Step 3: Write a concrete failing test for each acceptance criterion before implementation steps.**
- [ ] **Step 4: Specify the exact command and expected failure for each failing test.**
- [ ] **Step 5: Specify minimal implementation changes, then the exact command and expected passing result.**
- [ ] **Step 6: Add a commit step containing only the files for that task.**

### Task 3: Validate plan completeness against the approved specification

**Files:**
- Read: Approved specification and every file named by the generated tasks.
- Modify: `.superpowers/sdd/2026-08-20-requirements-impact-refiner/baseline-raw/NEG-planning-4.md`

**Interfaces:**
- Consumes: The complete task decomposition from Task 2.
- Produces: A checked plan with no uncovered requirements, unresolved symbol names, or placeholder instructions.

- [ ] **Step 1: Check every specification requirement against at least one task and its test.**
- [ ] **Step 2: Search the plan for `TBD`, `TODO`, “implement later”, “appropriate error handling”, and other non-actionable placeholders.**
- [ ] **Step 3: Check that all referenced functions, types, paths, commands, and test names are defined consistently.**
- [ ] **Step 4: Run the listed verification commands in the repository and record their expected outcomes.**
- [ ] **Step 5: Leave the approved impact report marked as complete and outside the implementation task sequence.**
