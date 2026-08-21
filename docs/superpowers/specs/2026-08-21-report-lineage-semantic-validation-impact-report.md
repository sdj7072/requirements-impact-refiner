# Requirements Impact Report

## Report State

| Phase |
| --- |
| post-decision |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Improve the skill so it progressively removes requirement impacts, compare revisions reliably, and prevent changes from breaking working behavior. | User-approved v0.3 design discussion; `docs/superpowers/specs/2026-08-21-report-lineage-semantic-validation-design.md` |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Release version 0.3.0 with Markdown-to-Markdown report lineage, exact predecessor SHA-256 verification, deterministic transition-based Impact Delta calculation, and semantic completeness validation. Preserve automatic activation and orchestration boundaries; keep v0.2 reports as historical records and require a one-time v0.3 baseline rather than implicit migration. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The validator checks one canonical v0.2 report and derives Delta agreement from current lifecycle state only. | `verified` | `skills/requirements-impact-refiner/scripts/validate-impact-report.py` — `validate_report`, `STATE_TO_DELTA`, and `main` |
| `INV-002` | Automatic routing excludes ideation and enters after approved Superpowers brainstorming but before writing-plans. | `verified` | `skills/using-requirements-impact-refiner/SKILL.md`; `skills/requirements-impact-refiner/references/integration-superpowers.md` — Entry and Exit |
| `INV-003` | Raw evaluation evidence is byte-preserved and compatibility claims distinguish observed, verified, and blocked paths. | `verified` | `.gitattributes`; `evals/results/with-skill.md`; `tests/test_release_compatibility_evidence.py` |
| `INV-004` | English documentation is the semantic authority and Korean and Japanese documents are maintained as equivalent translations. | `verified` | `README.md` — Overview; `README.ko.md` — Overview; `README.ja.md` — Overview; `tests/test_documentation.py` |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | Existing one-file command and validator tests define the current public interface. |
| `INV-002` | `REQ-001` | `IMP-007` | Bootstrap and Superpowers adapter tests protect routing ownership and timing. |
| `INV-003` | `REQ-001` | `IMP-004`, `IMP-006` | Git attributes, manifests, and release-evidence tests protect historical evidence integrity. |
| `INV-004` | `REQ-001` | `IMP-005` | Documentation tests enforce shared commands, tokens, and compatibility wording. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Interfaces | high | `refining` | `verified` | `skills/requirements-impact-refiner/scripts/validate-impact-report.py` — `main` currently accepts exactly one positional report. | `INV-001` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | State/Concurrency | critical | `refining` | `verified` | `skills/requirements-impact-refiner/scripts/validate-impact-report.py` — current Delta is mapped from one report's state and has no predecessor model. | `INV-001` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | Regression | high | `refining` | `verified` | Mutation probes against `validate_report` accepted blank category, severity, observable criterion, and scope content under v0.2. | `INV-001` | `DEC-001` | `AC-003` |
| `IMP-004` | `REQ-001` | Compatibility | high | `deferred` | `unknown` | No executable Claude client is available in the current repository environment; conceptual fallback exists but v0.3 behavior is not yet run there. | `INV-003` | `DEC-001` | `AC-004` |
| `IMP-005` | `REQ-001` | Compatibility | high | `detected` | `verified` | Version and command strings occur across `.codex-plugin/plugin.json`, both skill metadata files, three READMEs, templates, and packaging tests. | `INV-004` | `DEC-001` | `AC-005` |
| `IMP-006` | `REQ-001` | Compatibility | medium | `accepted` | `verified` | The approved design explicitly makes v0.3 a schema break and preserves v0.2 reports only as historical records. | `INV-003` | `DEC-001` | `AC-006` |
| `IMP-007` | `REQ-001` | Regression | critical | `detected` | `verified` | `skills/using-requirements-impact-refiner/SKILL.md`, adapter references, `tests/test_integration_adapters.py`, and `tests/test_eval_cases.py` protect automatic activation and exclusions. | `INV-002` | `DEC-001` | `AC-007` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Use a strict v0.3 Markdown lineage with stable Report ID, consecutive revision, exact predecessor SHA-256, computed lifecycle Delta, and semantic validation; start with a manual Revision 1 baseline instead of inferring v0.2 history. | `REQ-001` | `IMP-006` | The user approved this design section by section. Deterministic lineage prevents false new or resolved claims, while refusing automatic migration avoids fabricating evidence and identity. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-005`, `IMP-007` |
| accepted | `IMP-006` |
| deferred | `IMP-004` |
| blocked | none |
| superseded | none |
| new | none |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | 1 | `DEC-001` | none | Refined the general request for progressive impact removal into a strict v0.3 Markdown lineage, transition calculator, semantic validator, compatibility policy, and verified release workflow. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Revision 1 validates with the existing single-report command; later revisions require `--previous`; invocation and unreadable-file errors return exit code 2. | Future CLI tests covering baseline, comparison, usage, and unreadable paths. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-001` | Stable blocked impacts calculate as unchanged, terminal-to-active impacts calculate as reopened, new IDs calculate as new, and unexplained deletion fails. | Future transition-table unit and mutation tests across consecutive Markdown fixtures. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-001` | Empty category, severity, evidence basis, observable criterion, scope, owner, or planning fields fail with entity-specific errors. | Future semantic-validation mutation suite, including all known v0.2 bypasses. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-003` | Documentation labels Claude v0.3 runtime support not verified until an executable fresh-agent run is captured; conceptual fallback discloses the missing deterministic check. | Future Claude evidence when the client exists; until then documentation and release tests assert the limitation. |
| `AC-005` | `REQ-001` | `IMP-005` | `INV-004` | Core metadata, plugin manifest, templates, English, Korean, and Japanese documentation all state 0.3.0 and synchronized commands and transition rules. | Packaging and multilingual documentation parity tests. |
| `AC-006` | `REQ-001` | `IMP-006` | `INV-003` | v0.2 raw evidence remains byte-identical and v0.2 reports are not silently accepted as v0.3 lineage; migration guidance requires a manual Revision 1 baseline. | Checksum, Git attribute, legacy rejection, and documentation tests. |
| `AC-007` | `REQ-001` | `IMP-007` | `INV-002` | Automatic activation still selects concrete behavior changes, excludes ideation and review work, and enters after approved brainstorming before writing-plans. | Existing adapter and activation suites plus fresh behavioral pressure scenarios. |

## Unresolved, Deferred, and Blocked Items

List only ledger impacts whose state is `deferred` or `blocked`; keep `detected` and `refining` impacts in the ledger only.

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-004` | `deferred` | Claude runtime verification cannot be completed without an executable Claude client; the release must retain an explicit not-verified claim. | `DEC-001` | Release evidence owner when a Claude client becomes available. |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Core schema and validator | Current validator, pre/post templates, core skill, evidence model, taxonomy, and Superpowers adapter were inspected. | High confidence in the identified parser, state-machine, and semantic-validation impacts. |
| Packaging and documentation | Plugin manifest, skill metadata, multilingual README references, test inventory, raw-evidence policy, and recent commits were inspected. | High confidence that version and documentation parity require coordinated updates. |
| Cross-client runtime | Current environment exposes Codex skills but no executable Claude client or generic external harness. | Claude behavior remains unknown and is explicitly deferred under `IMP-004`; no compatibility claim may be promoted from conceptual support. |
| Implementation evidence | No v0.3 implementation or future acceptance tests exist yet. | Every listed acceptance criterion is a future target and must not be described as verified current behavior. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `INV-001`, `INV-002`, `INV-003`, `INV-004`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `IMP-007`, `DEC-001` | `IMP-004` remains deferred and `IMP-006` is an explicitly accepted schema-break risk. | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005`, `AC-006`, `AC-007` | Superpowers writing-plans after this report is validated and accepted. |
