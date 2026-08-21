English | [한국어](README.ko.md) | [日本語](README.ja.md)

# Requirements Impact Refiner

Requirements Impact Refiner `0.3.0` is a repository-aware Agent Skill for turning a concrete software change into an evidence-linked impact ledger before implementation planning. English is the semantic authority for [README.md](README.md), [README.ko.md](README.ko.md), and [README.ja.md](README.ja.md).

## 1. Problem

Vibe-coded changes often satisfy the newest request while quietly breaking behavior that already worked: authorization boundaries, stored payloads, mobile clients, retention rules, retry semantics, or observability. A conventional clarification may explain what to build, but it does not necessarily trace the change through repository evidence.

This skill occupies that missing interval. It starts only when the change and inspection scope are concrete, records current behavior as invariants, exposes affected surfaces with confidence, and helps the user reduce, defer, resolve, or explicitly accept impacts. It stops with a report-only `Planning Handoff`; it does not design the product, write an implementation plan, edit code, debug, or review code.

## 2. Core Concepts

The canonical skill is [`skills/requirements-impact-refiner/SKILL.md`](skills/requirements-impact-refiner/SKILL.md). It uses stable IDs so every revision remains traceable:

| ID | Meaning |
| --- | --- |
| `RPT-###` | Stable report identity across consecutive revisions |
| `REQ-###` | Original or refined requirement |
| `INV-###` | Current behavior that may need preservation |
| `IMP-###` | Affected behavior, contract, data path, or risk |
| `DEC-###` | A choice explicitly selected by a user or stakeholder |
| `AC-###` | Observable acceptance or regression criterion |

Evidence levels are exactly `verified`, `inferred`, and `unknown`. Impact states are exactly `detected`, `refining`, `mitigated`, `resolved`, `accepted`, `deferred`, `blocked`, and `superseded`. `reopened` is a Delta transition for a terminal impact returning to active work, not a ledger state. `accepted` requires a linked `DEC-###`; `resolved` requires supporting evidence. Each report records `RPT-###`, Revision, `Previous SHA-256`, and phase. A Revision 1 baseline uses predecessor `none` and classifies every impact as `new`; later revisions preserve IDs and compare against the exact predecessor bytes.

## 3. Quick Start

Install from the GitHub repository with the native marketplace flow when your client supports it. The marketplace and plugin use the same name: `requirements-impact-refiner`.

For Codex CLI:

```sh
codex plugin marketplace add sdj7072/requirements-impact-refiner --ref main
codex plugin add requirements-impact-refiner@requirements-impact-refiner
```

To upgrade an existing Codex installation, refresh the marketplace snapshot and reinstall the plugin so the cached copy is replaced:

```sh
codex plugin marketplace upgrade requirements-impact-refiner
codex plugin remove requirements-impact-refiner@requirements-impact-refiner
codex plugin add requirements-impact-refiner@requirements-impact-refiner
```

The repository marketplace at [`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json) resolves the root [Codex plugin manifest](.codex-plugin/plugin.json), whose `skills` field points to the single canonical `./skills/` tree. It does not add MCP servers, hooks, apps, agents, or dependencies.

For Claude Code, run these commands inside Claude Code:

```text
/plugin marketplace add sdj7072/requirements-impact-refiner
/plugin install requirements-impact-refiner@requirements-impact-refiner
```

To upgrade an existing Claude Code installation, refresh the marketplace, update the installed plugin, and reload it:

```text
/plugin marketplace update requirements-impact-refiner
/plugin update requirements-impact-refiner@requirements-impact-refiner
/reload-plugins
```

Run `/reload-plugins` if the install summary asks for it. [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) publishes the root [Claude plugin manifest](.claude-plugin/plugin.json). For local development loading, clone the repository and run from its root:

```sh
claude --plugin-dir .
```

For another [Agent Skills-compatible client](https://agentskills.io/clients), clone the repository and copy the complete canonical skill into the directory that client documents. The cross-client `.agents/skills/` convention is a useful default, although the Agent Skills specification does not mandate an installation location:

```sh
python3 scripts/install-agent-skill.py --target-dir ~/.agents/skills
```

The installer refuses to overwrite an existing installation. Client-native alternatives include `~/.codex/skills` and `~/.claude/skills`, but the marketplace flows above provide cleaner updates for Codex and Claude Code.

When the plugin is enabled, [`using-requirements-impact-refiner`](skills/using-requirements-impact-refiner/SKILL.md) automatically checks software-development conversations and invokes the core skill for concrete behavior changes at the correct pre-planning boundary. No invocation phrase is required. Disable the plugin in the client's plugin settings to turn this automatic check off.

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

The Revision 1 baseline records both impacts as `new`. On the next report, the recalculated Delta places `IMP-001` under `mitigated`, keeps `IMP-002` under `unchanged` until external-consumer evidence is inspected, and lists no impact twice. If later evidence invalidates a resolved impact, that impact becomes `reopened`. The changelog promise is an invariant, not a fabricated user choice; `DEC-001` exists only after the explicit selection.

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

Compatibility claims below are limited to preserved evaluation evidence. “Behavioral evaluation” means fresh-context model runs with supplied skill/reference files; it is not proof that an external plugin loader or orchestrator executed. Product, version, and status columns are identical across all translations; only the evidence note is translated.

| Environment | Version | Status | Evidence note |
| --- | --- | --- | --- |
| Codex standalone behavioral harness | `codex-cli 0.148.0-alpha.15`; `gpt-5.6-luna`; hosted runtime unavailable | `not verified` | Strict evaluation failed at **7/17** from one repetition per case: positives 0/8, negatives 3/5, integrations 4/4. |
| Codex with Superpowers | executed client/model/version not recorded in selected transcripts | `not verified` | Strict evaluation failed at **10/17** from one repetition per case: one positive passed and seven were partial; negatives 5/5 and integrations 4/4 passed. |
| Codex skill quick validator | local system snapshot | `blocked` | PyYAML is absent. Static audit also found that this validator's allowed-key list omits the Agent Skills `compatibility` key; no executed pass is claimed. |
| Codex plugin validator | local system snapshot | `blocked` | Execution stopped at `ModuleNotFoundError: yaml`; manifest tests are not substituted for this validator. |
| Claude Code standalone | version unavailable | `blocked` | The `claude` executable was absent. |
| Claude Code with Superpowers | version unavailable | `blocked` | The `claude` executable and Claude-side Superpowers runtime were unavailable. |
| Claude Code with `feature-dev` | version unavailable | `blocked` | The `claude` executable and `feature-dev` runtime were unavailable. |
| Claude Code with Spec Kit | version unavailable | `blocked` | The `claude` executable and Spec Kit runtime were unavailable. |
| Generic Agent Skills-compatible harness | client/version unavailable | `blocked` | No named or configured generic harness executable was available. |

Both Codex audits detected all **24/24** positive surface topics and preserved all **4/4** integration ownership boundaries. These are observed behaviors, not compatibility or support. No all-17-times-five rerun was performed: no skill or adapter wording changed in Task 7, and the one-run corpora already failed strict support criteria. Full transcripts, reruns, scorecards, and checksums are in [`evals/results/with-skill.md`](evals/results/with-skill.md).

## 7. Comparison and Non-Goals

Superpowers remains the orchestrator for brainstorming, planning, execution, debugging, and review. Claude Code `feature-dev` remains its phased feature workflow. GitHub Spec Kit remains the specification and planning workflow. Requirements Impact Refiner neither replaces nor vendors them: it contributes the repository-backed impact ledger and iterative impact reduction between their clarification and planning stages.

This project does not provide broad ideation, generic PRD generation, architecture design, task breakdowns, implementation, debugging, or code review. It does not ship an MCP server or custom code-graph engine. It does not automatically install, invoke, or chain another framework, and related-work references do not imply dependency or code reuse.

## 8. Safety and Limitations

Repository access, search, and tests improve confidence, but supplied files may be sufficient and automatic access is not guaranteed. `verified` means direct inspected support, not runtime proof unless runtime evidence was actually inspected. `inferred` and `unknown` must remain visible. An `AC-###` is a future target, never evidence that behavior already passes.

The core evaluation is **24/25**, not 25/25. The single known stochastic failure in `POS-payments-5` embedded reconcile-before-retry mechanics before the user selected a retry policy. The final checklist addresses the pattern, but the allowed correction rounds were exhausted, so the limitation remains disclosed. The separate workflow-integration final composition is **30/30**. These scores come from the recorded Codex harness and must not be generalized to untested clients.

The broader Task 7 release audits supersede any inference of client support: Codex standalone strictly failed at **7/17**, and Codex with Superpowers strictly failed at **10/17**. Each used only one nominated result per case, below the runbook's five-repetition support threshold. Therefore neither environment is verified or supported by this release evidence.

The skill can miss impacts outside the inspected scope. Users should keep unresolved, deferred, blocked, and accepted risks visible through planning and validate critical behavior with appropriate human review and tests.

v0.2 is historical. The manual migration to `0.3.0` treats the first converted artifact as Revision 1 with a new `RPT-###`, `Previous SHA-256` set to `none`, and every retained impact under `new`. Do not fabricate a v0.2 predecessor digest. Subsequent revisions must preserve IDs and use the exact previous file bytes.

## 9. Report Schema and Validation

Start from the [`template chooser`](skills/requirements-impact-refiner/assets/impact-report-template.md). Version `0.3.0` separates `pre-decision` and `post-decision` reports, forbids recorded decisions before selection, and validates a complete, disjoint Impact Delta plus report lineage.

Validate a completed report with the standard-library validator:

```sh
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py path/to/report.md
```

Validate a later revision against its exact predecessor, or print the computed Delta without modifying either file:

```sh
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py --previous previous.md current.md
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py --previous previous.md --print-expected-delta current.md
```

The validator checks required sections, definitions and references, exact evidence/state enums, decision links for `accepted`, evidence for `resolved`, `AC-###` links for critical impacts, consecutive revision numbers, stable report/impact IDs, the exact predecessor digest, and deterministic Delta transitions including `reopened`. It does not verify that cited repository facts are true or locate the predecessor automatically. The optional local skill/plugin platform validators were `blocked` in this environment as described above; no pass is claimed for them.

## 10. Development and Contributing

Run the standard-library suite from the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_documentation -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for RED/GREEN evaluation discipline, five-repetition controls, validator commands, compatibility-claim rules, and the translation policy. English changes are authoritative, but every semantic README change must update `README.ko.md` and `README.ja.md` together or explicitly record a pending translation. This project is available under the [MIT License](LICENSE).
