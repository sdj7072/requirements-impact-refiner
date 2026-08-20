# Requirements Impact Refiner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a public, cross-client Agent Skill that discovers repository-backed change impacts and iteratively refines requirements without duplicating brainstorming or implementation planning workflows.

**Architecture:** One canonical skill under `skills/requirements-impact-refiner/` owns the evidence model, impact lifecycle, refinement loop, and report contract. Conditional reference files provide progressive disclosure for integrations, while a Python standard-library validator checks report integrity; Codex and Claude manifests package the same skill without forking its behavior.

**Tech Stack:** Markdown, YAML frontmatter, JSON manifests and evaluation cases, Python 3.11+ standard library, `unittest`, GitHub Actions, Agent Skills specification.

**Spec:** `docs/superpowers/specs/2026-08-20-requirements-impact-refiner-design.md`

## Global Constraints

- The repository contains one canonical skill: `skills/requirements-impact-refiner/SKILL.md`.
- The skill analyzes and refines requirements; it does not perform broad ideation, write implementation plans, implement code, debug, review code, or claim runtime verification.
- Evidence levels are exactly `verified`, `inferred`, and `unknown`.
- Impact states are exactly `detected`, `refining`, `mitigated`, `resolved`, `accepted`, `deferred`, `blocked`, and `superseded`.
- An `accepted` impact requires a `DEC-###` reference; a `resolved` impact requires supporting evidence.
- Every material requirement revision triggers whole-set impact recalculation.
- Only one workflow orchestrator owns a run; multiple evidence providers may be combined.
- The v1 implementation adds no MCP server and no custom code-graph engine.
- Runtime code uses only the Python standard library.
- English is canonical; Korean and Japanese README files contain equivalent full documentation.
- The core skill uses capability language and must not depend on Codex-, Claude-, or Superpowers-specific tool names.
- The initial license is MIT, using “Requirements Impact Refiner contributors” as the copyright holder.
- Remote publication, marketplace submission, and GitHub repository creation remain separate authorized actions after the local release-ready commit.

## File Map

| Path | Responsibility |
|---|---|
| `skills/requirements-impact-refiner/SKILL.md` | Concise trigger, core workflow, stop conditions, and reference routing |
| `skills/requirements-impact-refiner/references/evidence-model.md` | IDs, relationships, evidence levels, impact states, and proof rules |
| `skills/requirements-impact-refiner/references/impact-taxonomy.md` | Cross-cutting inspection checklist and evidence prompts |
| `skills/requirements-impact-refiner/references/refinement-loop.md` | User decision loop, recalculation rules, and delta presentation |
| `skills/requirements-impact-refiner/references/integration-*.md` | Standalone, Superpowers, Claude feature-dev, and Spec Kit handoffs |
| `skills/requirements-impact-refiner/assets/impact-report-template.md` | Canonical generated report shape |
| `skills/requirements-impact-refiner/scripts/validate-impact-report.py` | Deterministic report-integrity validator |
| `evals/cases.json` | Positive, negative, and compatibility behavior scenarios |
| `evals/runbook.md` | Repeatable no-guidance and with-skill evaluation procedure |
| `evals/results/baseline.md` | Observed behavior before the skill is available |
| `evals/results/with-skill.md` | Observed behavior after loading the skill |
| `tests/test_eval_cases.py` | Evaluation-case schema and coverage checks |
| `tests/test_validate_impact_report.py` | Validator behavior tests |
| `tests/test_packaging.py` | Skill and plugin manifest structure checks |
| `tests/test_documentation.py` | README language parity and link checks |
| `.codex-plugin/plugin.json` | Codex package metadata pointing to the canonical skill |
| `.claude-plugin/plugin.json` | Claude Code package metadata pointing to the canonical skill |
| `README.md`, `README.ko.md`, `README.ja.md` | English, Korean, and Japanese user documentation |
| `CONTRIBUTING.md` | Contribution, testing, and translation synchronization policy |
| `LICENSE` | MIT license text |
| `.github/workflows/ci.yml` | Standard-library tests and validators on pushes and pull requests |

---

### Task 1: Create the Behavioral Evaluation Contract and Capture RED Baselines

**Files:**
- Create: `evals/cases.json`
- Create: `evals/runbook.md`
- Create: `evals/results/baseline.md`
- Create: `tests/test_eval_cases.py`

**Interfaces:**
- Consumes: The impact states, evidence levels, boundaries, and integration sequences from the design specification.
- Produces: `evals/cases.json` with stable case IDs and `tests.test_eval_cases.load_cases() -> list[dict[str, object]]`; later tasks use the same cases unchanged for GREEN and compatibility runs.

- [ ] **Step 1: Write the evaluation schema test before creating any skill file**

Create `tests/test_eval_cases.py`:

```python
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "cases.json"
REQUIRED_KEYS = {
    "id",
    "kind",
    "request",
    "repository_evidence",
    "must_detect",
    "must_not_do",
    "modes",
}
ALLOWED_KINDS = {"positive", "negative", "integration"}
REQUIRED_POSITIVE_TOPICS = {
    "authorization",
    "deletion",
    "api-contract",
    "cache",
    "payments",
    "sharing",
    "offline-sync",
    "background-retry",
}


def load_cases():
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


class EvalCaseContractTest(unittest.TestCase):
    def test_cases_have_unique_ids_and_required_fields(self):
        cases = load_cases()
        self.assertEqual(len(cases), len({case["id"] for case in cases}))
        for case in cases:
            self.assertEqual(set(case), REQUIRED_KEYS)
            self.assertIn(case["kind"], ALLOWED_KINDS)
            self.assertTrue(case["request"].strip())
            self.assertIsInstance(case["repository_evidence"], list)
            self.assertIsInstance(case["must_detect"], list)
            self.assertIsInstance(case["must_not_do"], list)
            self.assertIsInstance(case["modes"], list)

    def test_positive_cases_cover_the_release_taxonomy(self):
        topics = {
            case["id"].removeprefix("POS-")
            for case in load_cases()
            if case["kind"] == "positive"
        }
        self.assertEqual(topics, REQUIRED_POSITIVE_TOPICS)

    def test_negative_cases_protect_neighboring_workflows(self):
        negative_ids = {
            case["id"] for case in load_cases() if case["kind"] == "negative"
        }
        self.assertEqual(
            negative_ids,
            {
                "NEG-brainstorming",
                "NEG-planning",
                "NEG-debugging",
                "NEG-code-review",
                "NEG-generic-prd",
            },
        )

    def test_integration_cases_cover_formal_adapters(self):
        modes = {
            mode
            for case in load_cases()
            if case["kind"] == "integration"
            for mode in case["modes"]
        }
        self.assertEqual(
            modes,
            {"generic", "superpowers", "claude-feature-dev", "spec-kit"},
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the schema test and verify RED**

Run:

```bash
python3 -m unittest tests.test_eval_cases -v
```

Expected: error because `evals/cases.json` does not exist. This confirms the test is exercising the missing evaluation contract.

- [ ] **Step 3: Create the complete evaluation case set**

Create `evals/cases.json` with this complete case set:

```json
{
  "cases": [
    {
      "id": "POS-authorization",
      "kind": "positive",
      "request": "Let workspace members edit every project.",
      "repository_evidence": ["authorizeProjectEdit currently permits owner and admin roles", "workspace invitations default to member", "project edits emit an actor-role audit event"],
      "must_detect": ["owner/admin distinction", "invitation scope", "audit behavior"],
      "must_not_do": ["write implementation plan", "modify repository"],
      "modes": ["generic", "codex", "claude-code"]
    },
    {
      "id": "POS-deletion",
      "kind": "positive",
      "request": "Delete an account immediately.",
      "repository_evidence": ["invoice.account_id uses RESTRICT", "privacy.md requires a 30-day finance retention period", "account cleanup is consumed by a background worker"],
      "must_detect": ["foreign records", "retention policy", "asynchronous jobs"],
      "must_not_do": ["write implementation plan", "modify repository"],
      "modes": ["generic", "codex", "claude-code"]
    },
    {
      "id": "POS-api-contract",
      "kind": "positive",
      "request": "Rename displayName to name.",
      "repository_evidence": ["ios/UserDTO.swift decodes displayName", "cached profile JSON persists displayName", "the public API changelog promises one-version deprecation"],
      "must_detect": ["mobile consumer", "stored payload", "backward compatibility"],
      "must_not_do": ["write implementation plan", "modify repository"],
      "modes": ["generic", "codex", "claude-code"]
    },
    {
      "id": "POS-cache",
      "kind": "positive",
      "request": "Cache the dashboard response for one hour.",
      "repository_evidence": ["dashboard results depend on tenant_id", "role changes invalidate permission_cache only", "dashboard writes publish dashboard.updated"],
      "must_detect": ["tenant key", "invalidation path", "stale authorization"],
      "must_not_do": ["write implementation plan", "modify repository"],
      "modes": ["generic", "codex", "claude-code"]
    },
    {
      "id": "POS-payments",
      "kind": "positive",
      "request": "Retry every failed charge automatically.",
      "repository_evidence": ["charge requests accept an idempotency_key", "payment status is rendered before webhook settlement", "the provider may time out after capture"],
      "must_detect": ["idempotency key", "user-visible status", "duplicate capture"],
      "must_not_do": ["write implementation plan", "modify repository"],
      "modes": ["generic", "codex", "claude-code"]
    },
    {
      "id": "POS-sharing",
      "kind": "positive",
      "request": "Make shared links permanent.",
      "repository_evidence": ["share tokens currently expire after seven days", "permission changes revoke active tokens", "token signing keys rotate every 90 days"],
      "must_detect": ["revocation", "permission changes", "secret rotation"],
      "must_not_do": ["write implementation plan", "modify repository"],
      "modes": ["generic", "codex", "claude-code"]
    },
    {
      "id": "POS-offline-sync",
      "kind": "positive",
      "request": "Sync offline edits when the app reconnects.",
      "repository_evidence": ["records carry an updated_at timestamp", "server deletions create tombstones for 24 hours", "the client queue preserves local creation order only"],
      "must_detect": ["conflict resolution", "deleted records", "ordering"],
      "must_not_do": ["write implementation plan", "modify repository"],
      "modes": ["generic", "codex", "claude-code"]
    },
    {
      "id": "POS-background-retry",
      "kind": "positive",
      "request": "Retry failed export jobs forever.",
      "repository_evidence": ["exports write to a deterministic object key", "worker retries currently stop after five attempts", "alerts consume dead_letter events"],
      "must_detect": ["duplicate output", "retry ceiling", "dead-letter observability"],
      "must_not_do": ["write implementation plan", "modify repository"],
      "modes": ["generic", "codex", "claude-code"]
    },
    {
      "id": "NEG-brainstorming",
      "kind": "negative",
      "request": "Help me brainstorm ideas for a new fitness app.",
      "repository_evidence": [],
      "must_detect": [],
      "must_not_do": ["activate impact refinement", "invent repository evidence"],
      "modes": ["generic", "codex", "claude-code"]
    },
    {
      "id": "NEG-planning",
      "kind": "negative",
      "request": "Turn this approved specification into coding tasks.",
      "repository_evidence": ["the impact report is already approved"],
      "must_detect": [],
      "must_not_do": ["repeat impact refinement", "replace the planning workflow"],
      "modes": ["generic", "codex", "claude-code"]
    },
    {
      "id": "NEG-debugging",
      "kind": "negative",
      "request": "Find why this test intermittently fails.",
      "repository_evidence": ["the failure occurs only in CI"],
      "must_detect": [],
      "must_not_do": ["activate impact refinement", "rewrite the requirement"],
      "modes": ["generic", "codex", "claude-code"]
    },
    {
      "id": "NEG-code-review",
      "kind": "negative",
      "request": "Review this pull request for correctness.",
      "repository_evidence": ["a complete diff is supplied"],
      "must_detect": [],
      "must_not_do": ["activate impact refinement", "replace code review"],
      "modes": ["generic", "codex", "claude-code"]
    },
    {
      "id": "NEG-generic-prd",
      "kind": "negative",
      "request": "Write a complete PRD from this product idea.",
      "repository_evidence": [],
      "must_detect": [],
      "must_not_do": ["activate impact refinement", "claim repository-backed findings"],
      "modes": ["generic", "codex", "claude-code"]
    },
    {
      "id": "INT-generic",
      "kind": "integration",
      "request": "Refine this approved requirement before I plan it with my own workflow.",
      "repository_evidence": ["the requirement is approved", "no named orchestration framework is active"],
      "must_detect": ["generic entry after clarification", "handoff to user-selected planning method"],
      "must_not_do": ["invoke an external framework", "write implementation tasks"],
      "modes": ["generic"]
    },
    {
      "id": "INT-superpowers",
      "kind": "integration",
      "request": "Brainstorming approved the design; refine repository impacts next.",
      "repository_evidence": ["Superpowers brainstorming is complete", "writing-plans has not started"],
      "must_detect": ["entry after brainstorming", "exit before writing-plans"],
      "must_not_do": ["repeat brainstorming", "invoke writing-plans automatically"],
      "modes": ["superpowers"]
    },
    {
      "id": "INT-claude-feature-dev",
      "kind": "integration",
      "request": "Feature-dev clarification is complete; analyze change impact.",
      "repository_evidence": ["feature-dev Phase 3 is complete", "Phase 4 architecture has not started"],
      "must_detect": ["entry after Phase 3", "exit before Phase 4"],
      "must_not_do": ["repeat general clarification", "invoke architecture design automatically"],
      "modes": ["claude-feature-dev"]
    },
    {
      "id": "INT-spec-kit",
      "kind": "integration",
      "request": "Speckit clarify is complete; refine impacts before planning.",
      "repository_evidence": ["speckit.clarify is complete", "speckit.plan has not started"],
      "must_detect": ["entry after speckit.clarify", "exit before speckit.plan"],
      "must_not_do": ["repeat specification", "invoke speckit.plan automatically"],
      "modes": ["spec-kit"]
    }
  ]
}
```

- [ ] **Step 4: Create the repeatable evaluation runbook**

Create `evals/runbook.md` with these rules:

1. Use a fresh agent context for every repetition.
2. Run each selected case five times with no skill guidance and five times with the candidate skill.
3. Supply only the case request and `repository_evidence`; do not supply the rubric.
4. Score each `must_detect` item as present only when the output connects it to evidence or explicitly marks it inferred/unknown.
5. Score a `must_not_do` violation when the output performs the forbidden neighboring workflow.
6. Record exact model/client/version, enabled orchestrator, tool access, repetition count, detections, violations, and representative quotations.
7. Treat unavailable repository access or unavailable fresh-context execution as a disclosed blocked evaluation, never as a pass.
8. Require all negative cases to avoid activation and all integration cases to preserve one-orchestrator ownership.

- [ ] **Step 5: Run the schema test and verify GREEN**

Run:

```bash
python3 -m unittest tests.test_eval_cases -v
```

Expected: four tests pass.

- [ ] **Step 6: Capture the no-guidance behavioral baseline**

Run five fresh-context repetitions for `POS-authorization`, `POS-api-contract`, `POS-payments`, `NEG-brainstorming`, and `NEG-planning` without loading the new skill. Create `evals/results/baseline.md` with:

- environment and model metadata;
- a row per case with `detections / possible detections`, forbidden-workflow violations, and variance notes;
- representative verbatim failure excerpts;
- a final list of demonstrated failures that the skill must correct.

Expected: at least one positive case misses a cross-cutting impact, fails to label evidence confidence, or fails to distinguish accepted from resolved risk. If the no-guidance control shows no failure, stop and redesign the pressure cases before creating `SKILL.md`.

- [ ] **Step 7: Commit the RED evaluation contract**

```bash
git add evals/cases.json evals/runbook.md evals/results/baseline.md tests/test_eval_cases.py
git commit -m "test: add requirements impact baseline evaluations"
```

---

### Task 2: Implement the Minimal Canonical Skill and Report Contract

**Files:**
- Create: `skills/requirements-impact-refiner/SKILL.md`
- Create: `skills/requirements-impact-refiner/references/evidence-model.md`
- Create: `skills/requirements-impact-refiner/references/impact-taxonomy.md`
- Create: `skills/requirements-impact-refiner/references/refinement-loop.md`
- Create: `skills/requirements-impact-refiner/assets/impact-report-template.md`
- Create: `evals/results/with-skill.md`

**Interfaces:**
- Consumes: Demonstrated baseline failures in `evals/results/baseline.md` and stable case IDs from `evals/cases.json`.
- Produces: Agent Skill frontmatter `name: requirements-impact-refiner`, report IDs `REQ|INV|IMP|DEC|AC-###`, and the canonical report sections consumed by the validator in Task 3.

- [ ] **Step 1: Confirm RED evidence exists before authoring the skill**

Run:

```bash
test -s evals/results/baseline.md
rg -n "demonstrated failures|variance|miss|violation|unknown" evals/results/baseline.md
```

Expected: the baseline file exists and contains concrete observed failures. Do not create the skill if the control did not fail.

- [ ] **Step 2: Create the minimal `SKILL.md`**

Use this frontmatter exactly:

```yaml
---
name: requirements-impact-refiner
description: Use when a proposed software change may affect existing behavior, contracts, data, permissions, compatibility, or regression risk and repository evidence can refine the requirement before implementation planning.
license: MIT
compatibility: Works with Agent Skills clients that can inspect supplied files; repository access, search, and tests improve evidence quality but are not required.
metadata:
  version: "0.1.0"
---
```

The body must stay below 500 words and contain these exact behavioral contracts:

1. Preserve current behavior as `INV-###` entries before refining the change.
2. Inspect repository evidence and classify every impact as `verified`, `inferred`, or `unknown`.
3. Create stable `REQ-###`, `INV-###`, `IMP-###`, `DEC-###`, and `AC-###` identifiers.
4. Show the impact ledger before asking a focused question.
5. Offer two or three concrete refinement options only when a decision is needed.
6. After a decision, update the requirement and recalculate the complete impact set.
7. Show the delta, including new impacts.
8. Keep `accepted` separate from `resolved`.
9. Stop at a planning handoff; do not write the implementation plan.
10. Route conditionally to the three core references and the selected integration reference; never load every integration reference by default.

Include a quick-reference table for states and evidence levels plus a “Common mistakes” section derived only from observed baseline failures.

- [ ] **Step 3: Create the evidence and taxonomy references**

Create `references/evidence-model.md` with:

- the five identifier types and relationship vocabulary;
- the eight allowed impact states;
- the three evidence levels;
- rules requiring `DEC-###` for accepted impacts, evidence for resolved impacts, and `AC-###` for every critical impact;
- evidence citations using repository-relative paths plus symbols, test names, schema objects, or specification IDs when available;
- one complete API-field-rename example showing a verified consumer path, an inferred external consumer, and an unknown unavailable dependency.

Add this failure and uncertainty matrix to the same reference:

| Condition | Required handling |
|---|---|
| repository unavailable | inspect supplied artifacts only and mark code impacts unknown |
| tests unavailable | record a validation gap and propose criteria without claiming coverage |
| documentation conflicts with code | use observed code behavior as the baseline and record the conflict |
| dynamic dispatch or reflection | disclose static-inspection limits and downgrade unsupported claims |
| external dependency unavailable | inspect local contracts/call sites and mark external behavior unknown |
| repository too large for complete inspection | prioritize likely core paths and record the inspected scope |
| requirement changes substantially | mark obsolete impacts superseded and recalculate the whole set |
| evidence contradicts itself | mark the impact blocked or unknown until resolved |
| user accepts a risk | retain accepted state and its decision link |

Create `references/impact-taxonomy.md` with one section each for functionality, data, interfaces, authorization/privacy, state/concurrency, operations, compatibility, legal/policy, and regression. Each section must contain inspection targets and evidence examples, not generic risk prose.

- [ ] **Step 4: Create the refinement-loop reference**

Create `references/refinement-loop.md` with this output sequence:

```text
Requirement revision
Current behavior and preserved invariants
Impact ledger ordered by severity and evidence confidence
One focused decision with 2–3 options
Recorded decision
Whole-set recalculation
Delta: resolved / mitigated / unchanged / accepted / deferred / blocked / new
Stop check and planning handoff
```

Define stopping conditions: every material impact is `resolved`, `accepted`, `deferred` with rationale, or `blocked` with a named information gap. Silence is never acceptance.

- [ ] **Step 5: Create the canonical report template**

Create `assets/impact-report-template.md` with these headings exactly:

```markdown
# Requirements Impact Report

## Original Requirement
## Current Refined Requirement
## Current Behavior
## Preserved Invariants
## Impact Ledger
## Decisions and Accepted Risks
## Requirement Revision History
## Acceptance and Regression Criteria
## Unresolved, Deferred, and Blocked Items
## Analysis Scope and Limitations
## Planning Handoff
```

Under `Impact Ledger`, define columns `ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria`. Under the other identifier-bearing sections, include columns that make all relationships explicit.

- [ ] **Step 6: Validate skill structure before behavioral evaluation**

Run:

```bash
python3 /Users/p042890/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/requirements-impact-refiner
wc -w skills/requirements-impact-refiner/SKILL.md
```

Expected: validator succeeds and word count is below 500.

- [ ] **Step 7: Run GREEN behavioral repetitions**

Repeat the same cases, inputs, model/client versions, and five-repetition count used for the baseline, now with `SKILL.md` loaded. Create `evals/results/with-skill.md` using the baseline table shape.

Expected:

- every baseline-missed critical impact is detected or explicitly marked unknown;
- all material claims carry an evidence level;
- a user decision produces a whole-set delta;
- accepted and resolved impacts remain distinct;
- negative cases do not enter the impact workflow.

If a failure remains, change only the smallest instruction supported by the observed failure and rerun all five repetitions for that case.

- [ ] **Step 8: Commit the verified core skill**

```bash
git add skills/requirements-impact-refiner evals/results/with-skill.md
git commit -m "feat: add requirements impact refinement skill"
```

---

### Task 3: Build the Deterministic Impact Report Validator with TDD

**Files:**
- Create: `tests/test_validate_impact_report.py`
- Create: `skills/requirements-impact-refiner/scripts/validate-impact-report.py`

**Interfaces:**
- Consumes: Headings, columns, identifiers, states, and evidence levels defined by the report template.
- Produces: `validate_report(text: str) -> list[str]`, `validate_path(path: Path) -> list[str]`, and CLI exit code `0` for valid reports or `1` for invalid reports.

- [ ] **Step 1: Write validator tests first**

Create `tests/test_validate_impact_report.py`. Load the script with `importlib.util.spec_from_file_location`. Define one complete valid report string and mutated cases that assert these error fragments:

```python
EXPECTED_ERRORS = {
    "duplicate": "duplicate identifier IMP-001",
    "dangling": "unknown reference DEC-999",
    "malformed_id": "invalid identifier IMP-1",
    "state": "invalid impact state ignored",
    "evidence_level": "invalid evidence level certain",
    "missing_requirement": "impact IMP-001 requires REQ reference",
    "resolved_without_evidence": "resolved impact IMP-001 requires evidence",
    "accepted_without_decision": "accepted impact IMP-001 requires DEC reference",
    "critical_without_ac": "critical impact IMP-001 requires AC reference",
    "missing_limitations": "missing section: Analysis Scope and Limitations",
}
```

The valid report must include `REQ-001`, `INV-001`, `IMP-001`, `DEC-001`, and `AC-001`, with an accepted critical impact linked to both `DEC-001` and `AC-001`.

- [ ] **Step 2: Run validator tests and verify RED**

Run:

```bash
python3 -m unittest tests.test_validate_impact_report -v
```

Expected: import error because `validate-impact-report.py` does not exist.

- [ ] **Step 3: Implement the minimal validator**

Implement these constants and functions in `validate-impact-report.py`:

```python
import re
import sys
from pathlib import Path


ID_PATTERN = re.compile(r"\b(?:REQ|INV|IMP|DEC|AC)-\d{3}\b")
ID_LIKE_PATTERN = re.compile(r"^(?:REQ|INV|IMP|DEC|AC)-")
IMPACT_STATES = {
    "detected", "refining", "mitigated", "resolved",
    "accepted", "deferred", "blocked", "superseded",
}
EVIDENCE_LEVELS = {"verified", "inferred", "unknown"}
REQUIRED_SECTIONS = {
    "Original Requirement",
    "Current Refined Requirement",
    "Current Behavior",
    "Preserved Invariants",
    "Impact Ledger",
    "Decisions and Accepted Risks",
    "Requirement Revision History",
    "Acceptance and Regression Criteria",
    "Unresolved, Deferred, and Blocked Items",
    "Analysis Scope and Limitations",
    "Planning Handoff",
}


def markdown_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines) for name, lines in sections.items()}


def table_rows(section: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in section.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return []
    headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def references(value: str) -> set[str]:
    return set(ID_PATTERN.findall(value))


def validate_report(text: str) -> list[str]:
    errors: list[str] = []
    sections = markdown_sections(text)
    for name in sorted(REQUIRED_SECTIONS - sections.keys()):
        errors.append(f"missing section: {name}")

    definitions: list[str] = []
    for section in sections.values():
        for row in table_rows(section):
            identifier = row.get("ID", "")
            if ID_PATTERN.fullmatch(identifier):
                definitions.append(identifier)
            elif ID_LIKE_PATTERN.match(identifier):
                errors.append(f"invalid identifier {identifier}")
    known = set(definitions)
    for identifier in sorted(known):
        if definitions.count(identifier) > 1:
            errors.append(f"duplicate identifier {identifier}")

    for name, section in sections.items():
        for row in table_rows(section):
            for value in row.values():
                for reference in references(value):
                    if reference not in known and reference != row.get("ID"):
                        errors.append(f"unknown reference {reference}")

    for row in table_rows(sections.get("Impact Ledger", "")):
        impact_id = row.get("ID", "unknown impact")
        state = row.get("State", "")
        level = row.get("Evidence Level", "")
        evidence = row.get("Evidence", "").strip()
        requirement_refs = {ref for ref in references(row.get("Requirement", "")) if ref.startswith("REQ-")}
        decision_refs = {ref for ref in references(row.get("Decision", "")) if ref.startswith("DEC-")}
        ac_refs = {ref for ref in references(row.get("Acceptance Criteria", "")) if ref.startswith("AC-")}
        if state not in IMPACT_STATES:
            errors.append(f"invalid impact state {state}")
        if level not in EVIDENCE_LEVELS:
            errors.append(f"invalid evidence level {level}")
        if not requirement_refs:
            errors.append(f"impact {impact_id} requires REQ reference")
        if state == "resolved" and not evidence:
            errors.append(f"resolved impact {impact_id} requires evidence")
        if state == "accepted" and not decision_refs:
            errors.append(f"accepted impact {impact_id} requires DEC reference")
        if row.get("Severity", "").lower() == "critical" and not ac_refs:
            errors.append(f"critical impact {impact_id} requires AC reference")
    return sorted(set(errors))


def validate_path(path: Path) -> list[str]:
    return validate_report(path.read_text(encoding="utf-8"))
```

Add a `main(argv: list[str]) -> int` that accepts one report path, prints each error to stderr, prints `valid impact report` on success, and returns the required exit code.

```python
def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate-impact-report.py REPORT.md", file=sys.stderr)
        return 2
    errors = validate_path(Path(argv[1]))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("valid impact report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run validator tests and verify GREEN**

Run:

```bash
python3 -m unittest tests.test_validate_impact_report -v
```

Expected: all validator tests pass.

- [ ] **Step 5: Validate a real report generated from the template**

Copy the template to a temporary directory, populate one coherent requirement/invariant/impact/decision/criterion set, and run:

```bash
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py /tmp/requirements-impact-valid.md
```

Expected: `valid impact report` and exit code `0`.

- [ ] **Step 6: Commit the validator**

```bash
git add tests/test_validate_impact_report.py skills/requirements-impact-refiner/scripts/validate-impact-report.py
git commit -m "feat: validate requirements impact reports"
```

---

### Task 4: Add Optional Workflow Integration References Without Orchestrator Overlap

**Files:**
- Create: `skills/requirements-impact-refiner/references/integration-generic.md`
- Create: `skills/requirements-impact-refiner/references/integration-superpowers.md`
- Create: `skills/requirements-impact-refiner/references/integration-claude-feature-dev.md`
- Create: `skills/requirements-impact-refiner/references/integration-spec-kit.md`
- Modify: `skills/requirements-impact-refiner/SKILL.md`
- Modify: `evals/cases.json`
- Modify: `evals/results/with-skill.md`

**Interfaces:**
- Consumes: The selected orchestrator name and the core report’s `Planning Handoff` section.
- Produces: Four mutually exclusive adapter contracts; each consumes an already-clarified requirement and returns the same canonical impact report.

- [ ] **Step 1: Run the four integration cases without adapter references**

Run `INT-generic`, `INT-superpowers`, `INT-claude-feature-dev`, and `INT-spec-kit` using the core skill but no adapter reference. Record whether the agent repeats brainstorming, writes an implementation plan, invokes an external framework, or fails to identify the correct handoff point.

Expected: at least one observed routing ambiguity. If all four are correct and stable across five repetitions, keep the adapter references minimal and document that the baseline already passed.

- [ ] **Step 2: Write the four adapter contracts**

Each reference must contain exactly four sections: `Entry`, `Ownership`, `Output`, and `Exit`.

Use these sequences:

| Reference | Entry | Exit |
|---|---|---|
| `integration-generic.md` | after the request is concrete enough for repository inspection | hand the report to the user’s chosen planning method |
| `integration-superpowers.md` | after `brainstorming` design approval | before `writing-plans` |
| `integration-claude-feature-dev.md` | after Phase 3 clarification | before Phase 4 architecture design |
| `integration-spec-kit.md` | after `speckit.specify` or `speckit.clarify` | before `speckit.plan` |

Every `Ownership` section must state:

- the adapter does not repeat general clarification already completed;
- the impact refiner asks only evidence-gap or impact-resolution questions;
- the external workflow is not automatically invoked;
- if more than one orchestrator is active, ask the user to choose one before continuing.

- [ ] **Step 3: Add conditional routing to `SKILL.md`**

Add a compact routing table that instructs the agent to read exactly one integration reference after the orchestrator is known. Keep the total `SKILL.md` word count below 500 by moving any expanded integration wording out of the entrypoint.

- [ ] **Step 4: Re-run integration and negative-trigger evaluations**

Run five repetitions for all four integration cases plus `NEG-brainstorming` and `NEG-planning`.

Expected:

- each formal adapter uses its exact entry and exit boundary;
- no run activates two orchestrators;
- no run repeats broad ideation;
- no run writes implementation tasks;
- generic mode does not mention a framework the user did not select.

Append the results and client/version metadata to `evals/results/with-skill.md`.

- [ ] **Step 5: Revalidate the skill and commit**

```bash
python3 /Users/p042890/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/requirements-impact-refiner
python3 -m unittest tests.test_eval_cases -v
git add skills/requirements-impact-refiner evals/cases.json evals/results/with-skill.md
git commit -m "docs: add workflow integration contracts"
```

---

### Task 5: Package the Canonical Skill for Codex and Claude Code

**Files:**
- Create: `tests/test_packaging.py`
- Create: `.codex-plugin/plugin.json`
- Create: `.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: `skills/requirements-impact-refiner/SKILL.md` and version `0.1.0`.
- Produces: Two valid manifests named `requirements-impact-refiner`, each discovering `./skills/` and declaring no MCP, hooks, apps, agents, or external plugin dependencies.

- [ ] **Step 1: Write packaging tests first**

Create `tests/test_packaging.py`:

```python
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackagingTest(unittest.TestCase):
    def load(self, relative_path):
        return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))

    def test_canonical_skill_exists(self):
        self.assertTrue(
            (ROOT / "skills/requirements-impact-refiner/SKILL.md").is_file()
        )

    def test_codex_manifest_points_to_canonical_skills(self):
        manifest = self.load(".codex-plugin/plugin.json")
        self.assertEqual(manifest["name"], "requirements-impact-refiner")
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("apps", manifest)
        self.assertNotIn("hooks", manifest)

    def test_claude_manifest_uses_default_skill_location(self):
        manifest = self.load(".claude-plugin/plugin.json")
        self.assertEqual(manifest["name"], "requirements-impact-refiner")
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertNotIn("dependencies", manifest)
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("hooks", manifest)

    def test_manifest_identity_is_consistent(self):
        codex = self.load(".codex-plugin/plugin.json")
        claude = self.load(".claude-plugin/plugin.json")
        for key in ("name", "version", "description", "license"):
            self.assertEqual(codex[key], claude[key])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run packaging tests and verify RED**

Run:

```bash
python3 -m unittest tests.test_packaging -v
```

Expected: file-not-found errors for both manifests.

- [ ] **Step 3: Create the Codex manifest**

Create `.codex-plugin/plugin.json`:

```json
{
  "name": "requirements-impact-refiner",
  "version": "0.1.0",
  "description": "Refines software requirements by exposing repository-backed change impacts and regression risks before planning.",
  "author": {
    "name": "Requirements Impact Refiner Contributors"
  },
  "license": "MIT",
  "keywords": [
    "requirements",
    "impact-analysis",
    "regression-risk",
    "agent-skills"
  ],
  "skills": "./skills/",
  "interface": {
    "displayName": "Requirements Impact Refiner",
    "shortDescription": "Refine changes against repository impact",
    "longDescription": "Discover affected behavior, preserve invariants, and reduce or explicitly accept regression risks before implementation planning.",
    "developerName": "Requirements Impact Refiner Contributors",
    "category": "Developer Tools",
    "capabilities": ["Read", "Interactive"],
    "defaultPrompt": [
      "Analyze this change's impact before planning it.",
      "Refine this requirement without breaking existing behavior."
    ],
    "brandColor": "#6D5EF5"
  }
}
```

- [ ] **Step 4: Create the Claude Code manifest**

Create `.claude-plugin/plugin.json`:

```json
{
  "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
  "name": "requirements-impact-refiner",
  "displayName": "Requirements Impact Refiner",
  "version": "0.1.0",
  "description": "Refines software requirements by exposing repository-backed change impacts and regression risks before planning.",
  "author": {
    "name": "Requirements Impact Refiner Contributors"
  },
  "license": "MIT",
  "keywords": [
    "requirements",
    "impact-analysis",
    "regression-risk",
    "agent-skills"
  ]
}
```

- [ ] **Step 5: Run packaging tests and platform validators**

Run:

```bash
python3 -m unittest tests.test_packaging -v
python3 /Users/p042890/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
claude plugin validate .
```

Expected: unit tests pass; Codex validator succeeds; Claude validator succeeds. If the Claude CLI is unavailable, record that command as blocked in the compatibility matrix rather than reporting a pass.

- [ ] **Step 6: Commit packaging**

```bash
git add tests/test_packaging.py .codex-plugin/plugin.json .claude-plugin/plugin.json
git commit -m "feat: package skill for Codex and Claude Code"
```

---

### Task 6: Write and Synchronize English, Korean, and Japanese Documentation

**Files:**
- Create: `tests/test_documentation.py`
- Create: `README.md`
- Create: `README.ko.md`
- Create: `README.ja.md`
- Create: `CONTRIBUTING.md`
- Create: `LICENSE`

**Interfaces:**
- Consumes: Formal adapter names, report schema, installation paths, version `0.1.0`, and observed evaluation limitations.
- Produces: Three structurally equivalent READMEs with reciprocal language links and one contribution policy that keeps them synchronized.

- [ ] **Step 1: Write documentation synchronization tests first**

Create `tests/test_documentation.py`:

```python
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
READMES = ["README.md", "README.ko.md", "README.ja.md"]
LANGUAGE_TARGETS = {"README.md", "README.ko.md", "README.ja.md"}


def headings(path):
    text = path.read_text(encoding="utf-8")
    return [
        re.sub(r"^#+\s+", "", line).strip()
        for line in text.splitlines()
        if line.startswith("## ")
    ]


class DocumentationTest(unittest.TestCase):
    def test_all_languages_exist_and_link_to_each_other(self):
        for name in READMES:
            path = ROOT / name
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            linked = set(re.findall(r"README(?:\.ko|\.ja)?\.md", text))
            self.assertEqual(linked, LANGUAGE_TARGETS)

    def test_all_languages_have_ten_numbered_sections(self):
        for name in READMES:
            numbered = [h for h in headings(ROOT / name) if re.match(r"\d+\.", h)]
            self.assertEqual(len(numbered), 10, name)

    def test_compatibility_terms_exist_in_every_language(self):
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            for term in ("Codex", "Claude Code", "Superpowers", "Spec Kit"):
                self.assertIn(term, text, f"{term} missing from {name}")

    def test_license_and_contributing_exist(self):
        self.assertIn("MIT License", (ROOT / "LICENSE").read_text(encoding="utf-8"))
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("README.ko.md", contributing)
        self.assertIn("README.ja.md", contributing)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run documentation tests and verify RED**

Run:

```bash
python3 -m unittest tests.test_documentation -v
```

Expected: failures because the README, contribution, and license files do not exist.

- [ ] **Step 3: Write the canonical English README**

Start `README.md` with reciprocal links:

```markdown
English | [한국어](README.ko.md) | [日本語](README.ja.md)
```

Use these ten numbered sections:

1. `Problem`
2. `Core Concepts`
3. `Quick Start`
4. `Worked Example`
5. `Integrations`
6. `Compatibility`
7. `Comparison and Non-Goals`
8. `Safety and Limitations`
9. `Report Schema and Validation`
10. `Development and Contributing`

The quick start must include the cross-client `.agents/skills/` convention without claiming the Agent Skills specification mandates an installation path, Codex plugin loading, and Claude Code `--plugin-dir` development loading. The integration table must show the four formal sequences and must label BMAD/GSD as manual guidance. The compatibility table must list only actually tested client/version combinations and mark unavailable runs `not tested` or `blocked`.

The comparison section must include Superpowers, Claude Code `feature-dev`, and GitHub Spec Kit. Explain that they remain orchestrators or upstream/downstream workflows, while this project contributes the repository-backed impact ledger and iterative impact reduction between clarification and planning.

The worked example must show an API field rename producing an invariant, a verified mobile-client impact, an inferred external-client impact, a user decision, a refined compatibility period, and the recalculated delta.

- [ ] **Step 4: Write complete Korean and Japanese translations**

Start the Korean README with:

```markdown
[English](README.md) | 한국어 | [日本語](README.ja.md)
```

Start the Japanese README with:

```markdown
[English](README.md) | [한국어](README.ko.md) | 日本語
```

Translate all ten sections, the worked example, installation instructions, compatibility table, and limitations. Preserve commands, paths, identifiers, state names, and evidence-level values in English so reports remain interoperable. Keep the English README as the semantic authority while using natural Korean and Japanese developer terminology.

- [ ] **Step 5: Add contribution and license policies**

Create `CONTRIBUTING.md` with:

- setup and standard-library test commands;
- the mandatory RED baseline before skill instruction changes;
- the five-repetition no-guidance control for wording changes;
- report-validator and platform-validator commands;
- a pull-request checklist requiring all maintained README languages to change together or explicitly record a pending translation;
- a prohibition on unsupported compatibility claims;
- instructions to add related-work attribution without claiming dependency or code reuse.

Create `LICENSE` with the complete MIT License text and:

```text
Copyright (c) 2026 Requirements Impact Refiner contributors
```

- [ ] **Step 6: Run documentation tests and verify GREEN**

Run:

```bash
python3 -m unittest tests.test_documentation -v
```

Expected: all documentation tests pass.

- [ ] **Step 7: Commit synchronized documentation**

```bash
git add README.md README.ko.md README.ja.md CONTRIBUTING.md LICENSE tests/test_documentation.py
git commit -m "docs: add multilingual project documentation"
```

---

### Task 7: Add CI and Complete Cross-Client Release Verification

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `evals/results/with-skill.md`
- Modify: `README.md`
- Modify: `README.ko.md`
- Modify: `README.ja.md`

**Interfaces:**
- Consumes: All tests, both manifests, the canonical skill, adapter cases, and recorded client/version results.
- Produces: A release-ready local commit whose documented compatibility claims match executed evidence.

- [ ] **Step 1: Create the CI workflow**

Create `.github/workflows/ci.yml`:

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
          if grep -RInE '\[([T]ODO|[T]BD):|<place''holder>' skills .codex-plugin .claude-plugin README*.md; then
            exit 1
          fi
```

- [ ] **Step 2: Run all deterministic checks locally**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile skills/requirements-impact-refiner/scripts/validate-impact-report.py
python3 /Users/p042890/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/requirements-impact-refiner
python3 /Users/p042890/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
```

Expected: every command succeeds with no warnings or tracebacks.

- [ ] **Step 3: Run the documented compatibility matrix**

Use `evals/runbook.md` to run equivalent cases in every available environment:

- Codex standalone
- Codex with Superpowers
- Claude Code standalone
- Claude Code with Superpowers
- Claude Code with `feature-dev`
- Claude Code with Spec Kit
- a generic Agent Skills-compatible harness

For unavailable environments, record `blocked` with the missing executable, plugin, account, or harness. Do not infer compatibility from a manifest validator alone.

- [ ] **Step 4: Verify negative triggers and full impact-loop behavior**

Run all 17 cases at least once in each available client, and run five repetitions for any client whose instructions or adapter wording changed during this task.

Expected:

- all eight positive topics produce evidence-linked impacts;
- all five negative cases stay in the neighboring workflow;
- all four integration cases select exactly one orchestrator;
- after a requirement revision, the output shows resolved, mitigated, unchanged, accepted, deferred, blocked, and new categories where applicable;
- accepted risk remains visible and linked to a decision;
- unknown evidence is never presented as verified.

- [ ] **Step 5: Synchronize compatibility documentation with observed results**

Update all three README compatibility tables from `evals/results/with-skill.md`. Use identical product/version/status rows and translated explanatory notes. Do not add a `supported` claim unless that exact environment completed the documented scenario set.

- [ ] **Step 6: Run final clean-tree verification**

Run:

```bash
python3 -m unittest discover -s tests -v
git diff --check
git status --short
```

Expected: tests pass, `git diff --check` prints nothing, and `git status --short` lists only the Task 7 files before commit.

- [ ] **Step 7: Commit the release-ready repository**

```bash
git add .github/workflows/ci.yml evals/results/with-skill.md README.md README.ko.md README.ja.md
git commit -m "ci: verify cross-client skill compatibility"
```

- [ ] **Step 8: Verify final history and stop before remote publication**

Run:

```bash
git status --short --branch
git log --oneline --decorate -8
```

Expected: a clean `main` branch with the design, RED evaluations, core skill, validator, integrations, packaging, multilingual documentation, and CI commits. Stop here and request explicit repository-owner/organization and publication authorization before creating a GitHub remote, pushing, tagging, or submitting to a marketplace.
