# Compact Impact Delivery Design

## Status

Approved in conversation on 2026-08-23. This design precedes implementation planning and does not authorize a release until its verification gates pass.

## Problem

Requirements Impact Refiner 0.3.2 preserves impact traceability, but its default path is expensive. The bootstrap and core skill total 642 words before supporting resources. The core currently directs the agent to read evidence, taxonomy, refinement, presentation, template, validator, and one integration adapter. A typical selected path therefore exposes roughly 3,500 instruction words before repository evidence. The sealed 0.3.1 corpus contains 100 turn outputs averaging 907 words, with a maximum of 1,596 words.

The cost is mostly repeated context and Markdown boilerplate, not validation CPU time. Small changes receive the same twelve-section inline report as high-risk changes. Revisions also repeat the entire report even when only a few lifecycle transitions changed.

## Goals

- Make `compact` the default delivery without losing any current impact, invariant, decision, acceptance criterion, limitation, or lineage fact.
- Keep the existing canonical Markdown report and SHA-256 predecessor contract.
- Reduce default input guidance by at least 50 percent relative to the measured selected-path baseline.
- Keep median default chat output at or below 450 words in the smoke evaluation.
- Avoid repeating unchanged analysis on later revisions.
- Preserve `simple`, `balanced`, and `technical` audience modes independently of delivery mode.
- Retain a safe full-inline fallback when files cannot be written or the user requests it.

## Non-Goals

- Removing repository inspection, evidence levels, impact lifecycle states, or acceptance criteria.
- Replacing Superpowers, Claude feature-dev, Spec Kit, or another planning workflow.
- Hiding impacts to meet a word target.
- Automatically modifying a user's `.gitignore` or committing generated reports.
- Claiming runtime or cross-client verification from deterministic unit tests alone.

## Configuration

The repository-root `.requirements-impact-refiner.json` accepts two independent settings:

```json
{
  "audience": "balanced",
  "delivery": "compact"
}
```

`audience` remains `simple`, `balanced`, or `technical`. `delivery` is `compact` or `full` and defaults to `compact`. For each setting, the current request overrides repository configuration, which overrides the default. Unknown keys and invalid values are disclosed rather than silently accepted.

`audience` changes wording detail. `delivery` changes where the canonical report appears. It never changes which impacts exist or their state.

## Architecture

The model produces one compact JSON state artifact. Deterministic standard-library tooling validates the state and renders the canonical Markdown report. The chat response is then rendered from the same validated state.

```text
request + repository evidence + predecessor
                    |
                    v
             compact state JSON
                    |
          schema + semantic validation
                    |
          +---------+----------+
          |                    |
          v                    v
canonical Markdown       compact chat view
SHA lineage report       impact summary + choice
```

No Markdown table is authored independently by the model in compact mode. JSON is the authored representation for the current turn; canonical Markdown remains the compatibility and lineage representation.

## Artifact Layout

When the workspace is writable, artifacts are stored under:

```text
.requirements-impact-refiner/
`-- reports/
    `-- RPT-001/
        |-- revision-0001.json
        |-- revision-0001.md
        `-- current.json
```

The skill creates only the report directory and the two report files. It does not edit `.gitignore`. The final response discloses both paths and leaves version-control policy to the user.

Revision artifacts are append-only and never overwritten. `current.json` contains the selected revision number, relative JSON and Markdown paths, and Markdown SHA-256. A new revision writes both uniquely named artifacts, validates them, and then atomically replaces only `current.json`. Exact predecessor Markdown bytes are read through the prior pointer, hashed, and used for the next `Previous SHA-256`. A crash before pointer publication leaves the prior revision current; incomplete candidates cannot impersonate the selected report.

## Compact State Contract

The state schema represents all information currently required by the Markdown validator:

- report metadata: report ID, revision, previous Markdown SHA-256, phase;
- presentation settings: audience and delivery with their resolved sources;
- original and refined requirements;
- current and preserved invariants;
- every impact with category, severity, lifecycle state, evidence, relationships, decision, and acceptance criteria;
- pre-decision question and two or three options, or post-decision records and accepted risks;
- complete Impact Delta;
- requirement revision history;
- acceptance and regression criteria;
- unresolved, deferred, and blocked items;
- analysis scope and limitations;
- planning handoff;
- user-facing summary fields for every impact.

Every current `IMP-###` appears exactly once in the compact summary and exactly once in the ledger. Summary severity and status must equal the ledger. References must resolve to defined IDs. The JSON validator preserves the same decision, evidence, unresolved-state, and lifecycle rules as the Markdown validator.

## Rendering and Lineage

`render-impact-report.py` reads validated state and produces canonical Markdown with deterministic section order, headers, row order, escaping, newline policy, and enum spelling. Rendering the same state twice must produce identical bytes.

The existing Markdown validator remains supported. A new state validator runs before rendering, and the rendered Markdown is then checked by the existing validator. A compact-mode result is successful only if both validations pass.

Existing Markdown-only reports remain valid predecessors. When no JSON predecessor exists, the tool parses the predecessor Markdown into the state needed for comparison. SHA lineage continues to use exact predecessor Markdown bytes; no JSON digest is substituted.

## Default Chat Output

Compact delivery returns, in the user's language:

1. `Change Impact Summary`, with one short row per impact;
2. the highest-severity unresolved, deferred, blocked, or accepted risks;
3. the single pending decision and its two or three options before selection, or the recorded decision after selection;
4. report ID, revision, validation status, and JSON/Markdown paths.

The response does not inline current behavior, preserved invariants, the full ledger, Delta table, history, criteria table, limitations table, or planning handoff. Those remain in the canonical report. Completeness takes precedence over the 450-word target: impacts are compressed, never omitted or merged solely to satisfy the budget.

Full delivery returns the complete canonical Markdown inline and may also save artifacts. Full delivery is selected when the user explicitly requests the full report, repository configuration sets `delivery` to `full`, or file persistence is unavailable.

## Progressive Resource Loading

The core skill stops instructing clients to load every reference. It routes resources by observable conditions:

- always: shortened core skill, compact state contract, selected integration adapter;
- predecessor present: refinement and lineage reference;
- a `verified` claim or ambiguous evidence basis: evidence reference;
- multiple impact domains or uncertain classification: taxonomy reference;
- non-default audience or wording ambiguity: presentation reference;
- full-inline fallback: selected Markdown template;
- normal compact mode: templates are consumed only by the renderer and are not loaded into model context.

The bootstrap remains a routing check and does not load the core references itself.

## Revision Fast Path

When a validated JSON predecessor exists, the agent reads it before repository exploration. It preserves all IDs and unchanged facts, inspects evidence related to the new request, and emits only a revised state artifact. Deterministic tooling calculates and verifies the Delta.

The fast path is forbidden when the predecessor is missing, invalid, refers to different report lineage, or its Markdown digest does not match. In those cases the skill discloses the gap and uses the existing full analysis path.

## Failure Handling

- Invalid JSON, schema errors, dangling IDs, summary mismatches, or lifecycle errors prevent artifact publication and prevent a success handoff.
- Rendering errors do not leave a Markdown report that appears current. Revision files use temporary siblings, and only the current pointer is atomically replaced after both artifacts validate.
- If JSON validates but rendered Markdown fails, both candidate artifacts remain uncommitted and the response names the validation failure.
- If the report directory cannot be created or written, the skill uses full inline delivery and discloses that persistence and revision fast path are unavailable.
- If a report path would escape the repository or resolve through a symlink outside it, persistence is rejected and full inline delivery is used.
- A future acceptance criterion is never promoted to current evidence in either representation.

## Compatibility

- Version 0.3.2 Markdown reports continue to validate without compact artifacts.
- Existing adapters keep their entry and exit boundaries. They receive a compact validated handoff instead of requiring a full inline report.
- Superpowers still owns brainstorming and planning. Compact delivery must not invoke `writing-plans` automatically.
- Codex, Claude Code, and generic Agent Skills clients use the same schema and renderer. Clients lacking file access use the full-inline fallback.
- Plugin-root resource mirrors remain byte-identical to canonical skill resources.

## Performance Measurement

Deterministic tests record word and byte budgets for routed instruction bundles, compact fixtures, and rendered reports. Runtime evaluation records client duration and token usage when the client exposes it; otherwise exact prompt/output bytes and words are retained as proxies.

The first release gate is a six-case, one-repetition installed-plugin smoke run. It must satisfy:

- six successful runtime results with no retry-selected result;
- zero missing, added, merged, or mismatched impacts between JSON, Markdown, and compact output;
- zero schema, semantic, lineage, or renderer failures;
- median compact chat output at or below 450 words;
- routed instruction words at least 50 percent below the measured pre-optimization selected-path baseline;
- no regression in negative activation boundaries or workflow ownership.

Only after this gate passes may the 17-case, five-repetition, 85-run evaluation begin. A failed smoke gate produces no broad compatibility or performance claim.

## Testing Strategy

- Unit tests for configuration defaults, precedence, unknown keys, and invalid values.
- State-schema tests for every required entity, enum, relationship, and failure mode.
- Renderer golden tests proving deterministic Markdown bytes and Markdown-validator acceptance.
- Round-trip tests from existing 0.3.2 Markdown to state and back without semantic loss.
- Lineage tests proving exact predecessor Markdown hashing and revision transitions.
- Atomic-write, traversal, symlink, non-UTF-8, and unwritable-directory tests.
- Compact-output tests proving every impact is represented and linked to the artifact.
- Resource-routing tests proving references are read only under their documented predicates.
- Distribution tests for canonical/root mirror parity and generic installer completeness.
- EN/KO/JA documentation parity tests.
- Installed-plugin smoke evaluation before full evaluation.

## Rollout

1. Implement the compact state, validator, renderer, and compatibility parser behind `delivery: compact`.
2. Keep `delivery: full` as an immediate opt-out.
3. Run deterministic tests and the six-case installed-plugin smoke gate.
4. If the gate passes, update public documentation and run the 85-result evaluation.
5. Only after evidence is sealed, update GitHub metadata, community files, demo, tag, and GitHub Release.

The release remains labeled Public Preview unless the new evidence supports a stronger claim. Existing 0.3.1 evidence remains immutable and separately identified.
