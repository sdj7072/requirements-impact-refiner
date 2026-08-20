English | [한국어](README.ko.md) | [日本語](README.ja.md)

# Requirements Impact Refiner

Requirements Impact Refiner `0.1.0` is a repository-aware Agent Skill for turning a concrete software change into an evidence-linked impact ledger before implementation planning. English is the semantic authority for [README.md](README.md), [README.ko.md](README.ko.md), and [README.ja.md](README.ja.md).

## 1. Problem

Vibe-coded changes often satisfy the newest request while quietly breaking behavior that already worked: authorization boundaries, stored payloads, mobile clients, retention rules, retry semantics, or observability. A conventional clarification may explain what to build, but it does not necessarily trace the change through repository evidence.

This skill occupies that missing interval. It starts only when the change and inspection scope are concrete, records current behavior as invariants, exposes affected surfaces with confidence, and helps the user reduce, defer, resolve, or explicitly accept impacts. It stops with a report-only `Planning Handoff`; it does not design the product, write an implementation plan, edit code, debug, or review code.

## 2. Core Concepts

The canonical skill is [`skills/requirements-impact-refiner/SKILL.md`](skills/requirements-impact-refiner/SKILL.md). It uses stable IDs so every revision remains traceable:

| ID | Meaning |
| --- | --- |
| `REQ-###` | Original or refined requirement |
| `INV-###` | Current behavior that may need preservation |
| `IMP-###` | Affected behavior, contract, data path, or risk |
| `DEC-###` | A choice explicitly selected by a user or stakeholder |
| `AC-###` | Observable acceptance or regression criterion |

Evidence levels are exactly `verified`, `inferred`, and `unknown`. Impact states are exactly `detected`, `refining`, `mitigated`, `resolved`, `accepted`, `deferred`, `blocked`, and `superseded`. `accepted` requires a linked `DEC-###`; `resolved` requires supporting evidence. Every material requirement revision recalculates the whole known impact set and reports a disjoint delta, including `new: none` when appropriate.

## 3. Quick Start

Clone the repository, then expose the canonical skill to your client. Some cross-client setups use `.agents/skills/`; this is a practical convention, not an installation path mandated by the Agent Skills specification.

```sh
mkdir -p .agents/skills
ln -s ../../skills/requirements-impact-refiner .agents/skills/requirements-impact-refiner
```

For Codex, load this repository as a local plugin using the plugin-loading facility in your Codex client. [`.codex-plugin/plugin.json`](.codex-plugin/plugin.json) points `skills` to `./skills/`; it does not add MCP servers, hooks, apps, agents, or dependencies. No Codex CLI loading command is claimed because none was exercised in this repository's compatibility run.

For Claude Code development loading, run from the repository root:

```sh
claude --plugin-dir .
```

The root [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) uses Claude Code's conventional root-level `skills/` discovery. The command is documented for an environment with Claude Code installed; it was `blocked` here because `claude` was unavailable.

After loading, ask for impact refinement with a concrete change and repository scope, for example: “Before planning, refine the `displayName` API rename against the API, iOS DTO, and cached-profile paths.” If multiple orchestrators are present, select exactly one.

## 4. Worked Example

Request: rename public API field `displayName` to `name`. Repository evidence says `ios/UserDTO.swift` decodes `displayName`, cached profile JSON persists it, and the public changelog promises one-version deprecation.

| Artifact | Example |
| --- | --- |
| `REQ-001` | Rename `displayName` to `name`. |
| `INV-001` | Existing iOS releases decode `displayName`; evidence `verified` from `ios/UserDTO.swift`. |
| `IMP-001` | Mobile decoding can fail; state `refining`, evidence `verified`. |
| `IMP-002` | Uninspected external clients may consume `displayName`; state `detected`, evidence `inferred`. |
| Decision needed | Choose immediate break, dual-field compatibility, or another explicit migration policy. |
| `DEC-001` | User selects dual-field compatibility for one published deprecation version. |
| `REQ-002` | Introduce `name`, preserve deprecated `displayName` for one version, then remove it only after compatibility criteria pass. |
| `AC-001` | The current iOS decoder and cached payload fixtures continue to work during that version. |

The recalculated delta places `IMP-001` under `mitigated`, keeps `IMP-002` under `unchanged` until external-consumer evidence is inspected, lists no impact twice, and states `new: none`. The changelog promise is an invariant, not a fabricated user choice; `DEC-001` exists only after the explicit selection.

## 5. Integrations

Only one formal adapter owns a run. Each sequence inserts impact refinement after clarification and before planning:

| Mode | Formal sequence | Adapter |
| --- | --- | --- |
| `generic` | concrete requirement + repository scope → impact refinement → user's chosen planning method | [`integration-generic.md`](skills/requirements-impact-refiner/references/integration-generic.md) |
| `superpowers` | `brainstorming` design approval → impact refinement → `writing-plans` | [`integration-superpowers.md`](skills/requirements-impact-refiner/references/integration-superpowers.md) |
| `claude-feature-dev` | Phase 3 clarification → impact refinement → Phase 4 architecture design | [`integration-claude-feature-dev.md`](skills/requirements-impact-refiner/references/integration-claude-feature-dev.md) |
| `spec-kit` | `speckit.specify` or `speckit.clarify` → impact refinement → `speckit.plan` | [`integration-spec-kit.md`](skills/requirements-impact-refiner/references/integration-spec-kit.md) |
| BMAD | specification → impact refinement → architecture/readiness | Manual guidance only in v1; no formal adapter |
| GSD and other workflows | requirement clarification → impact refinement → planning | Manual guidance only in v1; no formal adapter |

Adapters do not invoke the upstream or downstream workflow. If more than one orchestrator is active, the skill asks the user to choose one rather than combining them.

## 6. Compatibility

Compatibility claims below are limited to preserved evaluation evidence. “Behavioral evaluation” means fresh-context model runs with supplied skill/reference files; it is not proof that an external plugin loader or orchestrator executed.

| Client or path | Version/environment | Status |
| --- | --- | --- |
| Codex fresh-context behavioral harness | `codex-cli 0.148.0-alpha.15`, evaluator `gpt-5.6-luna`; hosted runtime version unavailable | tested: core final composition 24/25; integration final composition 30/30 |
| Codex local plugin manifest validation | Local Python environment | `blocked`: `ModuleNotFoundError: yaml` |
| Claude Code plugin loading/validation | Claude Code version unavailable | `not tested`; validator/loading command `blocked` because `claude` was not installed |
| Generic `.agents/skills/` discovery | Client and version unspecified | `not tested`; convention documented without a discovery guarantee |
| Superpowers, Claude Code `feature-dev`, Spec Kit runtime execution | External workflows were not invoked | `not tested`; adapter instruction behavior only was evaluated in the Codex harness |
| BMAD and GSD | No v1 adapter | `not tested`; manual guidance only |

## 7. Comparison and Non-Goals

Superpowers remains the orchestrator for brainstorming, planning, execution, debugging, and review. Claude Code `feature-dev` remains its phased feature workflow. GitHub Spec Kit remains the specification and planning workflow. Requirements Impact Refiner neither replaces nor vendors them: it contributes the repository-backed impact ledger and iterative impact reduction between their clarification and planning stages.

This project does not provide broad ideation, generic PRD generation, architecture design, task breakdowns, implementation, debugging, or code review. It does not ship an MCP server or custom code-graph engine. It does not automatically install, invoke, or chain another framework, and related-work references do not imply dependency or code reuse.

## 8. Safety and Limitations

Repository access, search, and tests improve confidence, but supplied files may be sufficient and automatic access is not guaranteed. `verified` means direct inspected support, not runtime proof unless runtime evidence was actually inspected. `inferred` and `unknown` must remain visible. An `AC-###` is a future target, never evidence that behavior already passes.

The core evaluation is **24/25**, not 25/25. The single known stochastic failure in `POS-payments-5` embedded reconcile-before-retry mechanics before the user selected a retry policy. The final checklist addresses the pattern, but the allowed correction rounds were exhausted, so the limitation remains disclosed. The separate workflow-integration final composition is **30/30**. These scores come from the recorded Codex harness and must not be generalized to untested clients.

The skill can miss impacts outside the inspected scope. Users should keep unresolved, deferred, blocked, and accepted risks visible through planning and validate critical behavior with appropriate human review and tests.

## 9. Report Schema and Validation

Start from [`impact-report-template.md`](skills/requirements-impact-refiner/assets/impact-report-template.md). It contains the original/current requirement, current behavior, preserved invariants, impact ledger, decisions, revision history, acceptance criteria, unresolved items, scope limitations, and `Planning Handoff`.

Validate a completed report with the standard-library validator:

```sh
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py path/to/report.md
```

The validator checks required sections, definitions and references, exact evidence/state enums, decision links for `accepted`, evidence for `resolved`, and `AC-###` links for critical impacts. It does not verify that cited repository facts are true. The optional local skill/plugin platform validators were `blocked` in this environment as described above; no pass is claimed for them.

## 10. Development and Contributing

Run the standard-library suite from the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_documentation -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for RED/GREEN evaluation discipline, five-repetition controls, validator commands, compatibility-claim rules, and the translation policy. English changes are authoritative, but every semantic README change must update `README.ko.md` and `README.ja.md` together or explicitly record a pending translation. This project is available under the [MIT License](LICENSE).
