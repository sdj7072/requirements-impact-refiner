# Requirements Impact Refiner v0.3: Report Lineage and Semantic Validation

**Status:** Approved in chat; awaiting written-spec review

**Date:** 2026-08-21

**Target release:** 0.3.0

## Purpose

Requirements Impact Refiner 0.2 validates the internal structure of one impact report. It cannot prove that a later report is the next revision of an earlier report, distinguish a genuinely new impact from an existing one, or reject several semantically empty rows that satisfy the Markdown schema.

Version 0.3 will turn the report into a revisioned impact ledger. It will compare two canonical Markdown reports, calculate the actual transition of every impact, and reject unsupported claims that an impact is new, mitigated, resolved, or otherwise changed. It will also validate that the report contains enough evidence and acceptance detail to support planning.

The release remains a pre-planning requirements skill. It does not execute plans, modify application code, or introduce a database or hidden state file.

## Goals

- Establish verifiable lineage between consecutive Markdown reports.
- Calculate Impact Delta from the previous and current ledgers instead of trusting manually selected categories.
- Reject structurally valid but semantically empty impact reports.
- Preserve deterministic validation when Python can run and a documented conceptual fallback when it cannot.
- Keep reports portable across Codex, Claude Code, and other Agent Skills clients.
- Preserve the existing one-file validation command for v0.3 baseline reports.

## Non-goals

- Automatically convert v0.2 reports into v0.3 reports.
- Maintain permanent dual-schema support.
- Store report history in JSON, a database, client metadata, or an external service.
- Edit a report in place or silently repair an incorrect Delta.
- Claim runtime compatibility for clients or validators that were not actually tested.
- Expand the skill into planning, implementation, debugging, or code review.

## Approved Product Decisions

1. The authoritative history is a chain of human-readable Markdown reports.
2. A report identifies its predecessor with a SHA-256 digest of the predecessor's exact bytes.
3. Revision numbers increase by exactly one and remain within one stable Report ID.
4. Impact Delta represents the transition from the previous report, not a grouping of current lifecycle states.
5. Version 0.3 is an intentional schema break. Existing v0.2 reports remain historical artifacts and are not silently interpreted as v0.3 lineage.
6. A project starts v0.3 history by creating a Revision 1 baseline with `Previous SHA-256` set to `none`.
7. The validator reports errors and can render the expected Delta, but never rewrites the source report.

## Canonical Report Metadata

The `Report State` table will contain exactly these columns:

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | `1` | `none` | `pre-decision` or `post-decision` |

Rules:

- `Report ID` uses `RPT-###` and remains stable through the chain.
- `Revision` is a positive integer.
- Revision 1 requires `Previous SHA-256: none`.
- A later revision requires a lowercase 64-character SHA-256 digest.
- With `--previous`, the current Report ID must equal the previous Report ID.
- With `--previous`, the current revision must equal the previous revision plus one.
- With `--previous`, the digest must equal SHA-256 of the exact previous file bytes.
- A later revision cannot be validated as a lineage-aware report without supplying `--previous`.

The exact-byte rule avoids ambiguous normalization. Documentation will explain that changing an old report intentionally breaks later links and requires regenerating its descendants.

## Impact Identity and Lifecycle

An `IMP-###` identifier represents one stable concern across revisions. Editing wording, evidence, severity, or lifecycle state does not create a new ID. An impact receives a new ID only when it represents a distinct concern.

Every impact present in the previous ledger must do one of the following in the current ledger:

- remain under the same ID;
- remain as `superseded` and identify its replacement or decision context; or
- be rejected as an unexplained deletion.

A resolved impact that becomes active again keeps its ID and produces the `reopened` transition. The ledger lifecycle state becomes `detected`, `refining`, `blocked`, `deferred`, or another current active state as appropriate; `reopened` is a Delta category, not a persistent lifecycle state.

## Transition-based Impact Delta

The canonical Delta categories are:

| Category | Meaning |
| --- | --- |
| `new` | ID exists only in the current report. |
| `unchanged` | ID and material lifecycle meaning did not change. |
| `mitigated` | Current state changed to `mitigated`. |
| `resolved` | Current state changed to `resolved` and resolution evidence is present. |
| `accepted` | Current state changed to `accepted` with a linked recorded decision. |
| `deferred` | Current state changed to `deferred`. |
| `blocked` | Current state changed to `blocked`. |
| `superseded` | Current state changed to `superseded`. |
| `reopened` | Previous state was `resolved`, `accepted`, or `superseded` and the concern is active again. |

Each known current impact appears exactly once. A previous impact may not disappear. Empty categories use the literal `none`; blank cells are invalid.

The comparator derives the expected category from the previous and current rows. Therefore, an impact that is blocked in both reports is `unchanged`, not `blocked`. The validator compares the authored table with the calculated result and reports exact mismatches.

Transitions use this precedence so one impact cannot fit two categories:

1. An ID absent from the previous report is `new`.
2. A previous `resolved`, `accepted`, or `superseded` impact that returns to `detected`, `refining`, `mitigated`, `deferred`, or `blocked` is `reopened`.
3. An impact whose lifecycle state is identical in both reports is `unchanged`.
4. Every other state change uses the current state's matching category: `mitigated`, `resolved`, `accepted`, `deferred`, `blocked`, or `superseded`.

Changes to wording, evidence, category, or severity without a lifecycle-state change remain `unchanged` in Impact Delta. Those changes remain visible in the ledger and revision history; Delta is deliberately a lifecycle transition summary.

For Revision 1, there is no predecessor. Every ledger impact is `new`. This is the only case where the baseline is derived solely from the current file.

## Semantic Completeness Rules

The parser will first enforce the canonical title, section set, phase-specific section, table schemas, and canonical IDs. Semantic validation then applies these rules:

### Evidence

- `verified` requires a nonempty direct evidence citation.
- `inferred` requires a nonempty inference basis.
- `unknown` requires a named information gap.
- `resolved` requires resolution evidence beyond a future acceptance target.
- Future `AC-###` targets never count as verified current behavior.

### Impacts

- `Category` is required and must use the maintained impact taxonomy.
- `Severity` is one of `critical`, `high`, `medium`, or `low`.
- Every impact references a known requirement.
- Every non-superseded impact references at least one acceptance criterion.
- `accepted` requires a recorded decision; `superseded` requires an explicit successor or rationale.
- `deferred` and `blocked` impacts appear exactly once in the unresolved-items table with a gap or rationale and a next owner.

### Requirements, invariants, and decisions

- Requirement descriptions and revision summaries are nonempty.
- Current behavior and preserved-invariant descriptions are nonempty.
- Preserved invariants link to known requirements and affected impacts.
- Pre-decision questions, options, impact links, and trade-offs are nonempty.
- Post-decision choices, rationales, requirement revisions, and applicable impact links are nonempty.

### Acceptance and scope

- Every acceptance criterion has a nonempty observable result and evidence or test method.
- Every acceptance criterion links known requirement, impact, and invariant IDs.
- Analysis Scope and Limitations contains at least one substantive row.
- Each scope row names inspected evidence or explicitly names the information gap and states its confidence consequence.
- Planning Handoff fields are nonempty.
- A pre-decision report remains `Not ready`.
- A post-decision report with any `blocked` impact must keep its selected planning workflow at `Not ready`. Deferred or accepted impacts may proceed only when they are named under Remaining risks and have the required owner or decision link.

## Components and Responsibilities

The current validator is one module. Version 0.3 will retain a small standard-library-only distribution but separate responsibilities through explicit data structures and functions:

### Markdown parser

Parses the canonical title, sections, tables, report metadata, and IDs into an `ImpactReport` model. It reports malformed Markdown without attempting semantic inference.

### Semantic validator

Validates one parsed v0.3 report: required values, enums, evidence rules, relationships, phase rules, unresolved-item reconciliation, and planning readiness.

### Lineage validator

Validates Report ID, consecutive revision, predecessor digest, and preservation of previous impact identities.

### Report comparator

Compares previous and current impact ledgers and returns a deterministic mapping from Delta category to impact IDs. It has no file-writing side effects.

### CLI adapter

Loads exact bytes for digest validation, invokes the parser and validators, prints sorted actionable errors, and optionally renders the expected Delta table.

The implementation may keep these components in one distributable Python file if that best preserves plugin portability. The conceptual boundaries and independently tested functions are required; a multi-file Python package is not.

## Command-line Interface

Baseline or standalone validation:

```bash
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py current.md
```

Lineage-aware comparison:

```bash
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py \
  --previous previous.md \
  current.md
```

Render the canonical expected Delta:

```bash
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py \
  --previous previous.md \
  --print-expected-delta \
  current.md
```

The CLI uses `argparse`, keeps exit code `0` for valid, `1` for report errors, and `2` for invocation or unreadable-file errors. Delta rendering is deterministic and does not mutate either report. When validation fails, the expected Delta may still be printed if both ledgers were parsed far enough to compare safely.

## Skill Behavior and Cross-client Fallback

The core skill will instruct the agent to locate the most recent report for the same change before producing a subsequent revision. If no v0.3 predecessor exists, it creates Revision 1 and clearly labels it as a new baseline. It must not fabricate a digest or lineage.

When repository tools and Python are available, the agent runs the validator. When they are unavailable, the agent applies the same comparison rules conceptually, names the unverified limitation in Analysis Scope and Limitations, and does not claim deterministic validation.

Adapters remain orchestration boundaries only. Superpowers integration runs after approved brainstorming and before writing-plans. Claude feature-dev, Spec Kit, and generic modes do not invoke or imitate external workflows.

## v0.2 Transition Policy

Version 0.2 reports remain valid historical records but are not accepted as v0.3 lineage inputs. The release documentation will include a one-time checklist:

1. Copy the latest known requirement, invariant, impact, decision, and acceptance information into a v0.3 template.
2. Assign a new stable `RPT-###` Report ID.
3. Set Revision to `1` and Previous SHA-256 to `none`.
4. Preserve existing `REQ`, `INV`, `IMP`, `DEC`, and `AC` IDs where their meanings remain stable.
5. Mark all baseline impacts as `new`.
6. Fill newly required semantic fields and validate the baseline.

There will be no automatic migration command in 0.3.0 because missing evidence, identity, and lineage cannot be inferred safely.

## Error Handling

Errors are deterministic, sorted, and identify the report entity whenever possible. Examples:

```text
current revision 4 must follow previous revision 2 exactly
previous SHA-256 does not match previous.md
impact IMP-004 is marked new but existed in revision 2; expected unchanged
impact IMP-007 disappeared; retain it or mark it superseded
impact IMP-009 evidence level unknown requires a named information gap
criterion AC-003 requires a nonempty observable criterion
```

The validator does not guess replacements, normalize an old report, or rewrite lifecycle states. Multiple independent errors may be returned in one run when doing so remains reliable.

## Testing and Evaluation

Implementation follows test-driven development.

### Unit and mutation tests

- Revision 1 metadata and all-impact `new` baseline.
- Consecutive revision, stable Report ID, and exact-byte SHA validation.
- Every supported transition, including unchanged blocked impacts and reopened resolved impacts.
- New IDs, unexplained deletion, explicit supersession, duplicate Delta membership, and blank `none` cells.
- Required category, severity, evidence, descriptions, criteria, scope, ownership, and handoff fields.
- Existing bypass mutations: blank impact category, blank severity, blank observable criterion, blank scope row, and falsely marking all impacts new.
- CLI exit codes and deterministic Delta rendering.

### Regression and packaging tests

- Existing activation and adapter boundaries remain unchanged.
- Templates, core skill, three README languages, plugin manifest, metadata, checksums, and packaging tests agree on version and commands.
- Raw evaluation evidence remains byte-preserved and is not rewritten to fit the new schema.
- Existing v0.2 examples are either clearly historical fixtures or replaced with valid v0.3 examples outside raw evidence corpora.

### Behavioral evaluation

- Fresh multi-turn scenarios create a baseline, accept a decision, and refine the report again.
- The evaluated agent preserves IDs, computes genuine transitions, reports reopened concerns, and refuses unsupported resolution.
- Codex standalone and Codex with Superpowers are measured separately.
- Claude and other clients are marked verified only after an executable run; otherwise documentation says `not verified`.
- Release evidence distinguishes deterministic script results from model-behavior observations and records repetition limits.

## Documentation and Release

The English README remains the semantic authority. Korean and Japanese documents receive equivalent commands, schema rules, migration guidance, and compatibility wording. The release updates plugin and skill versions to `0.3.0`, preserves automatic invocation policy, and documents both explicit invocation and automatic use.

Installation and upgrade documentation must distinguish installing a fresh plugin from updating an existing installation. Publishing to GitHub or installing the release occurs only after implementation, independent review, full verification, and explicit user authorization for the external mutation.

## Acceptance Criteria

The design is complete when an implementation can demonstrate all of the following:

1. A valid Revision 1 report passes standalone validation and lists every impact as `new`.
2. A valid later report passes only when its ID, next revision, and predecessor digest match.
3. The same blocked impact in two revisions is calculated as `unchanged`.
4. A previously resolved impact becoming active is calculated as `reopened`.
5. An unexplained impact deletion fails validation.
6. An authored Delta that differs from the computed Delta fails with an entity-specific error.
7. The CLI renders the computed canonical Delta without modifying source files.
8. Semantically empty evidence, impact, acceptance, scope, or handoff fields fail validation.
9. v0.2 reports are not silently accepted as v0.3 lineage.
10. Core, adapters, templates, multilingual documentation, tests, packaging, and compatibility claims remain synchronized.
