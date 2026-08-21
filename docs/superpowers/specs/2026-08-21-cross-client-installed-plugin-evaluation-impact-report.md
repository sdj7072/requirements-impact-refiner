# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 3 | 46d398f6638719089da060a81efa74d847ee72773cd36cbba1cac24c772e957b | post-decision |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Improve Requirements Impact Refiner by validating the actually installed plugin in Codex and Claude-compatible environments. | User request and approved cross-client evaluation design. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Build a client-neutral evaluation harness with Codex and Claude adapters; preserve every execution artifact; run the installed Codex 0.3.0 plugin with Superpowers across 17 applicable cases five times with the user-selected `gpt-5.6-sol` and `high` reasoning; use ephemeral contexts for one-turn cases and isolated persisted session UUIDs for multi-turn resume cases; validate the other adapter contracts structurally; validate Claude CLI and plugin structure without paid authentication; keep the production skill model-neutral; and update compatibility claims only from sealed evidence. | `DEC-002` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The existing runbook requires fresh contexts, five repetitions, hidden rubrics, and explicit blocked states. | `verified` | `evals/runbook.md` — steps 1–8. |
| `INV-002` | The current installed Codex plugin is 0.2.0 while the repository manifest is 0.3.0. | `verified` | Approved design records the local `codex plugin list` probe; `.codex-plugin/plugin.json` — `version`. |
| `INV-003` | Existing evaluation corpora are byte-preserved with checksums and disclosed raw-whitespace exceptions. | `verified` | `.gitattributes`; `tests/test_with_skill_evidence.py`; `tests/test_release_compatibility_evidence.py`. |
| `INV-004` | Current documentation keeps Codex behavior `not verified` and Claude behavior `blocked`. | `verified` | `README.md` — Compatibility table; `evals/results/with-skill.md` — release audit. |
| `INV-005` | The production skill does not select or require a model. | `verified` | `skills/requirements-impact-refiner/SKILL.md`; `skills/using-requirements-impact-refiner/SKILL.md`. |
| `INV-006` | `codex exec --ephemeral` does not persist a resumable session, while `codex exec resume` requires a session ID or `--last`. | `verified` | Local `codex-cli 0.148.0-alpha.21` help for `exec` and `exec resume`. |
| `INV-007` | The installed Codex environment has both Requirements Impact Refiner and Superpowers enabled, and the CLI does not expose a safe per-run override that keeps one installed plugin while disabling only the other. | `verified` | Local `codex plugin list --json`, CLI help, and config-probe errors for `plugins.enabled`. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-004`, `IMP-006`, `IMP-009` | `evals/runbook.md` — repetition, rubric, and blocked-state rules. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-010` | Approved design and `.codex-plugin/plugin.json` — version boundary. |
| `INV-003` | `REQ-001` | `IMP-003`, `IMP-007` | Existing `.gitattributes` and checksum tests. |
| `INV-004` | `REQ-001` | `IMP-005`, `IMP-009` | README compatibility status and preserved audit results. |
| `INV-005` | `REQ-001` | `IMP-002` | Canonical skill instructions contain no model-switching rule. |
| `INV-006` | `REQ-001` | `IMP-012` | Local Codex CLI help establishes the persistence boundary. |
| `INV-007` | `REQ-001` | `IMP-013` | Installed plugin inventory and CLI config probes establish the composition boundary. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | compatibility | critical | refining | verified | Approved design and local probe show installed Codex 0.2.0 versus repository 0.3.0. | `INV-002` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | functionality | high | mitigated | verified | Approved design makes model and reasoning optional run parameters and forbids production-skill model selection. | `INV-005` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | authorization/privacy | critical | mitigated | inferred | Raw prompts and client output could contain a secret; the design prohibits environment capture and requires quarantine before commit. | `INV-003` | `DEC-001` | `AC-003` |
| `IMP-004` | `REQ-001` | operations | high | accepted | verified | The user explicitly selected all 85 applicable Codex-with-Superpowers runs, full raw preservation, `gpt-5.6-sol`, and quality-first evaluation. | `INV-001` | `DEC-002` | `AC-004` |
| `IMP-005` | `REQ-001` | compatibility | high | deferred | verified | Anthropic requires paid authentication for model behavior; the user selected structural validation without purchase or login. | `INV-004` | `DEC-001` | `AC-005` |
| `IMP-006` | `REQ-001` | regression | high | mitigated | verified | The approved rerun policy seals a batch before adjudication and forbids same-batch skill tuning or selective reruns. | `INV-001` | `DEC-001` | `AC-006` |
| `IMP-007` | `REQ-001` | operations | medium | accepted | verified | The user explicitly selected preservation of every raw execution rather than failures or summaries only. | `INV-003` | `DEC-001` | `AC-007` |
| `IMP-008` | `REQ-001` | operations | high | mitigated | verified | The design keeps live clients, network mutation, and paid-model runs outside ordinary CI. | `INV-001` | `DEC-001` | `AC-008` |
| `IMP-009` | `REQ-001` | functionality | high | mitigated | inferred | Substantive impact detection cannot be reduced safely to string checks; the design separates mechanical scores from quoted human adjudication. | `INV-001`, `INV-004` | `DEC-001` | `AC-009` |
| `IMP-010` | `REQ-001` | operations | high | mitigated | verified | Updating the installed Codex plugin changes user-local state; the design requires before/after version probes and an explicit environment gate. | `INV-002` | `DEC-001` | `AC-010` |
| `IMP-011` | `REQ-001` | operations | medium | mitigated | verified | Installing Claude Code changes the user environment; the design requires a separate approval and forbids authentication or purchase. | `INV-004` | `DEC-001` | `AC-011` |
| `IMP-012` | `REQ-001` | operations | medium | mitigated | verified | True multi-turn resume requires non-ephemeral Codex sessions, which remain visible in local session history. | `INV-006` | `DEC-001` | `AC-012` |
| `IMP-013` | `REQ-001` | compatibility | high | mitigated | verified | Installed Superpowers can affect activation and orchestration, so live results cannot be generalized to standalone Codex or the other orchestrator adapters. | `INV-007` | `DEC-002` | `AC-013` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Use a common controller with Codex and Claude adapters, preserve all raw evidence, run a strict 100-execution Codex batch with the user-selected Sol configuration, perform Claude structural checks without paid authentication, and prevent same-batch tuning. | `REQ-001` | `IMP-004`, `IMP-007` | The user approved each architecture, evidence, model, protocol, safety, and scope section; quality and auditability outweigh time and repository-size costs for this batch. |
| `DEC-002` | Restrict live installed-plugin claims to an 85-execution Codex-with-Superpowers matrix; keep generic, Claude feature-dev, and Spec Kit adapters at deterministic structural coverage instead of removing or reconfiguring Superpowers. | `REQ-001` | `IMP-004` | The user chose the non-mutating environment boundary after CLI probes showed no safe per-run override for only one installed plugin. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `IMP-007`, `IMP-008`, `IMP-009`, `IMP-010`, `IMP-011`, `IMP-012` |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | `IMP-013` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Initial installed-plugin evaluation requirement. | `DEC-001` | none | Refined a general improvement request into a client-neutral, evidence-preserving Codex behavior and Claude structural evaluation system with explicit environment gates. |
| `REQ-001` | Revision 2 session-persistence constraint. | `DEC-001` | none | Added the explicit one-turn ephemeral and multi-turn persisted-session boundary after inspecting the Codex CLI resume contract. |
| `REQ-001` | Revision 3 installed-composition boundary. | `DEC-002` | none | Reduced the live matrix from 100 to 85 runs and bounded behavioral claims to Codex with Superpowers rather than mutating the user's plugin composition. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | Every Codex behavior run records installed plugin version 0.3.0 from both client inventory and skill metadata. | Future adapter probe and installed-version integration test. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-005` | The harness passes an explicitly selected model only for that run and leaves the client selection unchanged when the option is omitted. | Future command-construction and model-pass-through tests. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | No committed evidence contains detected credentials or environment dumps; suspicious artifacts are quarantined without being called raw evidence. | Future secret-detection and quarantine tests plus release audit. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-001` | The smoke checkpoint precedes the full sequential 85-execution Codex-with-Superpowers batch, and all time, rate-limit, and usage constraints are reported. | Future run metadata and result report. |
| `AC-005` | `REQ-001` | `IMP-005` | `INV-004` | Claude CLI and package checks are reported separately from model behavior, which remains `blocked` without paid authentication. | Future Claude structural evidence and multilingual compatibility assertions. |
| `AC-006` | `REQ-001` | `IMP-006` | `INV-001` | No valid unfavorable execution is selectively rerun or removed, and every skill change starts a new complete candidate batch. | Future batch-integrity and retry-link tests. |
| `AC-007` | `REQ-001` | `IMP-007` | `INV-003` | Every selected run has a complete raw artifact set covered by a deterministic inventory and SHA-256 manifest. | Future evidence-inventory and checksum tests. |
| `AC-008` | `REQ-001` | `IMP-008` | `INV-001` | Ordinary CI exercises only fake-client deterministic tests and cannot install clients or invoke live models. | Future CI marker and fake-adapter tests. |
| `AC-009` | `REQ-001` | `IMP-009` | `INV-001` | Mechanical and human scores are stored separately, and every human decision contains an exact quotation and rationale. | Future scoring-schema and report-generation tests. |
| `AC-010` | `REQ-001` | `IMP-010` | `INV-002` | Codex installation mutation occurs only after version probes and produces a verified before/after record. | Future installation checkpoint and probe evidence. |
| `AC-011` | `REQ-001` | `IMP-011` | `INV-004` | Claude installation occurs only after a fresh explicit approval and does not initiate login, purchase, or model execution. | Future structural-install checkpoint evidence. |
| `AC-012` | `REQ-001` | `IMP-012` | `INV-006` | One-turn cases use ephemeral contexts; every multi-turn case starts a new persisted session, resumes only its parsed UUID, never uses `--last`, records the session ID, and never reuses it across cases. | Future fake-client resume tests and live smoke metadata. |
| `AC-013` | `REQ-001` | `IMP-013` | `INV-007` | Live reports name the enabled plugin composition and apply behavior scores only to `Codex with Superpowers`; standalone and other orchestrator modes remain structurally tested or not verified. | Future probe metadata, scorer assertions, and multilingual compatibility-table tests. |

## Unresolved, Deferred, and Blocked Items

List only ledger impacts whose state is `deferred` or `blocked`; keep `detected` and `refining` impacts in the ledger only.

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-005` | deferred | Claude model behavior cannot be tested without a paid authenticated account, which the user chose not to purchase for this cycle. | `DEC-001` | Evaluation owner when paid Claude access becomes available. |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Repository scope | Approved design, canonical skills, current runbook, manifests, README compatibility claims, existing result ledgers, and evidence tests were inspected. | Impacts within the evaluation and packaging boundary have high confidence; unrelated product behavior is outside scope. |
| Live clients | Codex CLI inventory was observed, but the new harness, Codex 0.3.0 installed run, and Claude CLI do not exist yet. | All acceptance criteria remain future targets; no new client compatibility pass is claimed. |
| Claude behavior | Official documentation establishes the paid authentication boundary; no paid account is available. | Claude structural support may be assessed, but model behavior remains deferred and must not be inferred. |
| Cost and duration | Exact Sol usage and rate-limit behavior cannot be known before the batch. | The user accepted the quality-first 100-run scope, but the smoke checkpoint must expose practical constraints before full execution. |
| Codex session history | Multi-turn evaluation requires persisted sessions because ephemeral sessions cannot be resumed. | Evaluation sessions will remain in local Codex history; the harness must isolate them by explicit UUID and disclose rather than delete them. |
| Installed plugin composition | Requirements Impact Refiner and Superpowers are both enabled, and no safe per-run single-plugin override was found. | Live evidence supports only the combined environment; other adapter claims remain structurally bounded. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `RPT-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `INV-005`, `INV-006`, `INV-007`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `IMP-007`, `IMP-008`, `IMP-009`, `IMP-010`, `IMP-011`, `IMP-012`, `IMP-013`, `DEC-001`, `DEC-002` | Accepted execution-cost and repository-size risks `IMP-004`, `IMP-007`; deferred Claude behavior `IMP-005`; persisted Codex evaluation sessions `IMP-012`; combined-plugin claim boundary `IMP-013`; environment mutations remain approval-gated. | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005`, `AC-006`, `AC-007`, `AC-008`, `AC-009`, `AC-010`, `AC-011`, `AC-012`, `AC-013` | Superpowers writing-plans after deterministic report validation. |
