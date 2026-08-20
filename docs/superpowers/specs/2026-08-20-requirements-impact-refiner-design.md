# Requirements Impact Refiner — Design Specification

**Date:** 2026-08-20  
**Status:** Approved
**Distribution:** Public GitHub repository  
**Primary artifact:** Portable Agent Skill with optional platform adapters

## 1. Purpose

`requirements-impact-refiner` helps a user refine a proposed software change before implementation by identifying how it can affect working behavior elsewhere in a repository.

The skill is aimed especially at vibe-coding workflows, where a locally reasonable request can unintentionally break an existing feature, contract, data flow, permission boundary, or operational assumption. It converts those risks into a visible impact ledger, asks the user to make focused decisions, and recalculates the impact set after each refinement.

The intended outcome is not a generic PRD. It is an evidence-backed, reviewable requirements artifact that distinguishes impacts that were removed from impacts that were consciously accepted.

## 2. Product Boundaries

### In scope

- Establish the current behavior relevant to a proposed change.
- Discover repository-backed impact and regression risks.
- Record evidence and uncertainty for every material claim.
- Identify behavior that must remain invariant.
- Present focused refinement choices to the user.
- Recalculate the complete impact set after requirements change.
- Generate regression-oriented acceptance criteria.
- Hand a refined requirement and remaining risks to a planning workflow.

### Out of scope

- Open-ended ideation or product brainstorming.
- Full PRD generation and general requirements elicitation.
- Choosing a product strategy on the user's behalf.
- Writing an implementation plan or breaking work into coding tasks.
- Implementing, debugging, reviewing, or verifying production code.
- Replacing architecture analysis, a code graph engine, an LSP, or tests.
- Installing or automatically invoking an external orchestration framework.

These exclusions intentionally avoid overlap with Superpowers brainstorming, writing-plans, TDD, debugging, code-review, and verification skills.

## 3. Design Principles

1. **Preserve before changing.** Existing working behavior is recorded as explicit invariants before the new requirement is refined.
2. **Evidence over confidence.** A confident inference is not presented as verified evidence.
3. **Whole-set recalculation.** Refining one impact triggers a new scan of the entire known impact set, not only the edited item.
4. **Resolution is not acceptance.** A removed risk and a consciously retained risk remain different states.
5. **One orchestrator at a time.** External evidence sources can be combined, but competing workflow orchestrators are not run simultaneously.
6. **Portable core, optional adapters.** The core skill uses capability language rather than platform-specific tool names.
7. **Graceful degradation.** Missing repository access, tests, LSP, or subagents reduces confidence and is disclosed rather than silently guessed around.

## 4. Core Workflow

### 4.1 Entry conditions

The skill should run after a proposed change is concrete enough to inspect but before implementation planning begins. It may receive a user request, an existing specification, or the output of another clarification workflow.

### 4.2 Refinement loop

1. Capture the proposed requirement as `REQ-###`.
2. Inspect relevant code, tests, schemas, contracts, configuration, and documentation.
3. Describe the current behavior and create preserved invariants as `INV-###`.
4. Create an impact ledger using `IMP-###` entries.
5. Attach evidence, confidence level, affected surfaces, and proposed regression criteria.
6. Show the user the most consequential unresolved impacts and two or three concrete refinement options where a decision is needed.
7. Record the user's selection or edited direction as `DEC-###`.
8. Update the requirement and mark obsolete findings `superseded` when appropriate.
9. Recalculate the complete impact set.
10. Show the delta: resolved, mitigated, unchanged, accepted, deferred, blocked, and newly detected impacts.
11. Repeat until all material impacts are resolved, accepted, deferred with rationale, or blocked with an explicit information gap.
12. Produce regression-oriented acceptance criteria as `AC-###` and a planning handoff summary.

The skill must not claim that refinement has made the change safe merely because the conversation ended.

## 5. Data Model

### 5.1 Stable identifiers

| Prefix | Entity | Purpose |
|---|---|---|
| `REQ-###` | Requirement | Original and refined requested behavior |
| `INV-###` | Invariant | Existing behavior that must be preserved |
| `IMP-###` | Impact | Potential change, regression, or uncertainty |
| `DEC-###` | Decision | User-approved choice or risk acceptance |
| `AC-###` | Acceptance criterion | Testable behavior, including regression coverage |

Relationships include `affects`, `must-preserve`, `refined-by`, `mitigates`, and `produces`. References must point to existing identifiers.

### 5.2 Impact states

- `detected`: identified but not yet discussed or addressed
- `refining`: actively being reduced through requirement changes
- `mitigated`: reduced but not eliminated
- `resolved`: eliminated by a requirement or design constraint
- `accepted`: consciously retained through a recorded user decision
- `deferred`: intentionally postponed with rationale
- `blocked`: cannot be assessed without missing information or access
- `superseded`: replaced by a later requirement revision or finding

`accepted` requires a linked `DEC-###`. `resolved` requires evidence explaining why the impact no longer applies. Neither state may be inferred from silence.

### 5.3 Evidence levels

- `verified`: directly supported by inspected source, test, schema, configuration, or authoritative specification
- `inferred`: supported indirectly by repository context or call relationships
- `unknown`: insufficient or contradictory evidence

Evidence should include repository-relative paths and, where available, symbols, test names, schema objects, or specification identifiers. Tool availability must not alter this semantic model.

### 5.4 Impact taxonomy

The initial taxonomy covers:

- functionality and user flows
- persisted data, migrations, retention, and integrity
- public and internal interfaces
- authentication, authorization, and privacy boundaries
- state, timing, concurrency, idempotency, and retries
- operations, observability, deployment, and rollback
- backward and forward compatibility
- legal, policy, or regulatory constraints visible in project evidence
- regression risk to existing behavior

The taxonomy is a checklist, not a requirement to invent impacts without evidence.

## 6. Output Artifact

The initial release creates one canonical Markdown report:

`docs/requirements/<change-name>/requirements-impact.md`

It contains:

1. Original requirement
2. Current refined requirement
3. Relevant current behavior
4. Preserved invariants
5. Impact ledger
6. Decisions and accepted risks
7. Requirement revision history
8. Acceptance and regression criteria
9. Unresolved, deferred, and blocked items
10. Analysis scope and limitations
11. Handoff summary for the selected planning workflow

The artifact must remain understandable without access to the original chat.

## 7. Repository and Packaging Design

```text
requirements-impact-refiner/
├── skills/requirements-impact-refiner/
│   ├── SKILL.md
│   ├── references/
│   │   ├── evidence-model.md
│   │   ├── impact-taxonomy.md
│   │   ├── refinement-loop.md
│   │   ├── integration-superpowers.md
│   │   ├── integration-claude-feature-dev.md
│   │   ├── integration-spec-kit.md
│   │   └── integration-generic.md
│   ├── assets/
│   │   └── impact-report-template.md
│   └── scripts/
│       └── validate-impact-report.py
├── .claude-plugin/
│   └── plugin.json
├── .codex-plugin/
│   └── plugin.json
├── evals/
│   ├── generic/
│   ├── claude-code/
│   └── codex/
├── tests/
├── README.md
├── README.ko.md
├── README.ja.md
├── LICENSE
└── CONTRIBUTING.md
```

The canonical skill follows the open Agent Skills format with standard frontmatter such as `name`, `description`, `license`, and metadata. The core avoids experimental tool restrictions and platform-specific tool names. Platform manifests package the same canonical skill; they do not fork its behavior.

For clients that follow the cross-client `.agents/skills/` convention, the README provides installation or linking instructions without claiming that the convention is mandated by the Agent Skills specification.

## 8. Compatibility and Integration

### 8.1 Integration policy

Only one workflow orchestrator should own a run. Evidence providers may be combined.

Orchestrators include:

- Superpowers
- Claude Code `feature-dev`
- GitHub Spec Kit
- BMAD and similar lifecycle frameworks

Evidence providers include:

- native repository search and file inspection
- LSP or symbol/reference navigation
- code graph tools
- tests, schemas, configuration, and Git history

If multiple orchestrators are detected, the skill asks the user which one should own the workflow. It does not install, invoke, or chain external frameworks automatically.

### 8.2 Supported v1 adapters

| Environment | Recommended sequence | Support level |
|---|---|---|
| Standalone/generic | clarify request → impact refinement → user's planning method | Formal adapter |
| Superpowers | `brainstorming` → `requirements-impact-refiner` → `writing-plans` | Formal adapter |
| Claude `feature-dev` | after clarification, before architecture design | Formal adapter |
| GitHub Spec Kit | `speckit.specify`/`speckit.clarify` → impact refinement → `speckit.plan` | Formal adapter |
| BMAD | specification → impact refinement → architecture/readiness | Manual guidance in v1 |
| GSD and other workflows | insert between requirement clarification and planning | Manual guidance in v1 |

Claude Code and Codex receive their own packaging metadata and compatibility evaluations while sharing the same core instructions. A plain LLM can use a pasted copy of the skill, but automatic discovery and repository access cannot be guaranteed.

### 8.3 Superpowers overlap controls

The adapter must:

- consume an approved brainstorming result instead of repeating broad ideation;
- ask only questions needed to resolve a discovered impact or evidence gap;
- produce planning inputs without generating an implementation plan;
- leave coding, TDD, debugging, review, and completion verification to their respective skills.

## 9. Failure and Uncertainty Handling

| Condition | Required behavior |
|---|---|
| No repository access | Limit analysis to supplied artifacts and mark code impacts unknown |
| No tests | Record a validation gap and propose regression criteria without claiming coverage exists |
| Documentation conflicts with code | Prefer observed runtime/code behavior for baseline purposes and record the conflict |
| Dynamic dispatch or reflection | Disclose static-analysis limits and mark unsupported conclusions inferred or unknown |
| External dependency unavailable | Analyze local contracts and call sites only; record external behavior as unknown |
| Large repository | Inspect likely core paths first and explicitly record analysis scope |
| Requirement changes substantially | Supersede obsolete impacts and recalculate the whole set |
| Contradictory evidence | Mark the impact blocked or unknown until resolved |
| User accepts a risk | Keep it `accepted`; never convert it to `resolved` |

## 10. Validation

### 10.1 Deterministic report validator

The v1 validator uses Python standard-library modules only. It checks:

- identifier formats and duplicates
- dangling relationships
- allowed impact and evidence states
- `resolved` impacts with no supporting evidence
- `accepted` impacts without a linked decision
- critical impacts without regression acceptance criteria
- missing requirement relationships
- missing analysis-scope and limitations sections

It validates artifact integrity, not the truth of the technical analysis.

### 10.2 Behavioral evaluations

Evaluation fixtures should cover changes involving:

- authorization rules
- record deletion and retention
- API field additions, removals, and renames
- caching and invalidation
- payments and retries
- shared links and access scope
- offline synchronization and conflict resolution
- background jobs and duplicate execution

Each fixture should test whether the skill discovers cross-cutting effects, asks focused questions, preserves stable identifiers, recalculates after decisions, and distinguishes resolved from accepted risk.

### 10.3 Compatibility evaluations

Run equivalent fixtures in:

- Codex standalone
- Codex with Superpowers
- Claude Code standalone
- Claude Code with Superpowers
- Claude Code with `feature-dev`
- Claude Code with Spec Kit
- a generic Agent Skills-compatible harness

Compatibility claims in documentation must identify tested versions and known limitations.

### 10.4 Trigger evaluations

Positive triggers include requests to assess blast radius, preserve existing behavior, identify regression risk, or refine a change using repository evidence.

Negative triggers include pure brainstorming, generic PRD writing, implementation planning, debugging, code review, and implementation. These cases should route to the appropriate external or platform skill instead of activating this skill alone.

## 11. Documentation and Localization

English is the canonical documentation language, with full Korean and Japanese versions in the initial release:

- `README.md` — English source of meaning
- `README.ko.md` — Korean translation
- `README.ja.md` — Japanese translation

All three files use the same section order, examples, compatibility tables, and reciprocal language links. Translations should be natural for developers rather than mechanically literal. When wording conflicts, the English document defines intended meaning.

`CONTRIBUTING.md` and the pull-request checklist require documentation changes to update all maintained languages or explicitly record why a translation is pending. Additional languages are added only when there is demonstrated user demand or a committed maintainer, to avoid stale documentation.

The README family includes:

1. Problem and motivation
2. Core concepts and impact lifecycle
3. Quick starts for generic clients, Codex, and Claude Code
4. A worked before/after refinement example
5. Integration guides and correct sequencing
6. A compatibility matrix with tested versions and limits
7. Comparison with related tools and clear non-goals
8. Safety, evidence, and uncertainty limitations
9. Output schema and validation
10. Development and contribution instructions

It must explicitly document invalid combinations, especially the use of multiple orchestrators in one run.

## 12. Related Work and Differentiation

The project should credit related requirements, specification, and repository-confidence projects as inspiration where appropriate. It must not imply code reuse or a dependency without one.

The differentiator is the combination of:

- repository-evidence-backed impact discovery;
- explicit preservation of existing behavior;
- a stable, stateful impact ledger;
- user-driven iterative requirement refinement;
- whole-set impact recalculation after every material decision; and
- a portable handoff to, rather than replacement of, established planning workflows.

## 13. Initial Release Criteria

The first public release is ready when:

- the canonical skill and four formal v1 adapters are complete;
- the report template and deterministic validator agree on the schema;
- trigger, behavior, and compatibility evaluations pass at the documented level;
- Superpowers overlap tests demonstrate that brainstorming and planning are not duplicated;
- the English, Korean, and Japanese README files are structurally synchronized;
- installation instructions work for the documented Codex, Claude Code, and generic paths;
- limitations and unverified compatibility claims are clearly disclosed.

## 14. Deferred Decisions

- Whether to add a deterministic code graph or MCP service after v1 evidence shows a need.
- Whether BMAD, GSD, or another framework merits a formal adapter.
- Whether to split the single Markdown report into machine-readable and human-readable artifacts.
- Whether additional documentation languages have sufficient demand and maintainership.
