English | [한국어](README.ko.md) | [日本語](README.ja.md)

# Requirements Impact Refiner

Requirements Impact Refiner `0.6.0` is a **Public Preview** repository-aware Agent Skill for turning a concrete software change into an evidence-linked impact ledger before implementation planning. English is the semantic authority for [README.md](README.md), [README.ko.md](README.ko.md), and [README.ja.md](README.ja.md).

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

The repository marketplace at [`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json) resolves the root [Codex plugin manifest](.codex-plugin/plugin.json), whose `skills` field points to the single canonical `./skills/` tree. [`.mcp.json`](.mcp.json) also exposes the local, standard-library-only `rir_begin` and `rir_finalize` tools. MCP provides structured enforcement when the host calls those tools; the bundled CLI is the hard-enforcement boundary because an invalid finalize prints no user response. The controller has no network client or third-party runtime dependency, and the plugin adds no hooks, apps, or agents.

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

Every report now starts with a user-facing `Change Impact Summary`: which feature changes, what can go wrong, who or what is affected, when it happens, and how to prevent or check it. Its audience defaults to `balanced`. Set a repository preference in `.requirements-impact-refiner.json`:

```json
{"audience":"balanced","delivery":"compact","flow":"report"}
```

The `flow` setting shapes the answer: the default `report` delivers the complete impact report directly (the scan runs internally to seed it, stopping early only on `needs_input`), while `ask` returns the one-line scan summary plus a confirmation question before detailed refinement.

Allowed audience values are `simple`, `balanced`, and `technical`. Delivery defaults to compact; request `delivery: full` or set `"delivery":"full"` to return the complete canonical report inline. Compact mode persists append-only JSON and Markdown and returns the short summary plus artifact paths. If persistence is unavailable, the skill uses a disclosed `full-inline` fallback. Current-request overrides beat repository settings. These are cross-client skill settings rather than custom Codex or Claude settings-screen controls.

The default path is one `rir_scan` call and a renderer-owned response of at most `180 words`; high-risk results ask before detailed refinement. The graph engine targets `10s` with a `30s` ceiling, but this does not promise total model latency: the first representative canary found the API → decoder → cache → migration path in 17 ms while the model turn took `297.159` seconds and failed strict one-call automation, so v0.4 remains `not verified`.

Detailed graph refinement still supports `rir_begin → rir_trace_impact → inspect compact receipt → rir_finalize → return display_text` for compatibility. A promoted Fast Scan skips trace and reuses its receipt. The receipt adds a short per-impact path and one coverage footer; it never exposes raw provider output. Configure the bounded, local graph pass with the same settings in every client:

```json
{"impact_graph":{"enabled":true,"max_seconds":30,"target_seconds":10,"providers":["auto"],"install_policy":"never","deep":false}}
```

CLI fallback uses the same executable sequence:

```sh
python3 "$SKILL_DIR/scripts/rir-controller.py" begin --repo-root REPO --input REQUEST.json
python3 "$SKILL_DIR/scripts/rir-controller.py" trace --repo-root REPO --draft-id DRAFT_ID --input SEEDS.json
python3 "$SKILL_DIR/scripts/rir-controller.py" finalize --repo-root REPO --draft-id DRAFT_ID --graph-receipt-id RECEIPT_ID --input ANALYSIS.json
```

The target is `10s` with a `30s` hard ceiling. It is detect-only: no automatic install or network. Optional local providers (`builtin`, `codegraph`, `scip`, `joern`, `ast-grep`) retain their own licenses and can be missing, unsafe, unsupported, stale, failed, or timed out. The built-in fallback has limited precision; cache hits reuse only matching receipts, partial cache remains partial, and Deep broadens bounded discovery without proving completeness. Keep unknown frontiers visible. `full-inline` and CLI fallback preserve those limits. Compatibility remains `not verified`/`blocked` where the table says so; transaction correctness and review are not closed because Task 5's parked exclusive-quarantine race still requires Task 7.

![Compact delivery flow](assets/compact-delivery-demo.svg)

See the [compact delivery demo](docs/compact-delivery-demo.md) for a complete request, response, artifact, and full-render example.

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

Compatibility claims below are limited to preserved evaluation evidence. The historical Codex standalone behavioral harness used supplied skill/reference files in a fresh context and is not proof that an external plugin loader or orchestrator executed. By contrast, the sealed v0.3.1 Codex-with-Superpowers batch ran the actual installed-plugin cache whose functional payload is byte-matched to the canonical release. Product, version, and status columns are identical across all translations; only the evidence note is translated.

| Environment | Version | Status | Evidence note |
| --- | --- | --- | --- |
| Codex standalone behavioral harness | `codex-cli 0.148.0-alpha.15`; `gpt-5.6-luna`; hosted runtime unavailable | `not verified` | Strict evaluation failed at **7/17** from one repetition per case: positives 0/8, negatives 3/5, integrations 4/4. |
| Codex with Superpowers | `codex-cli 0.148.0-alpha.21`; `gpt-5.6-sol`; `high`; RIR `0.3.1` | `not verified` | Sealed v0.3.1 batch: 85/85 runtime passes from 85 first-attempt selections with no retries, but the mechanical score is 84/85. `POS-cache` repetition 2 has the sole malformed-ledger/unknown-`IMP-002` failure, so one verification blocker remains. |
| Codex skill quick validator | local system snapshot | `blocked` | PyYAML is absent. Static audit also found that this validator's allowed-key list omits the Agent Skills `compatibility` key; no executed pass is claimed. |
| Codex plugin validator | local system snapshot | `blocked` | Execution stopped at `ModuleNotFoundError: yaml`; manifest tests are not substituted for this validator. |
| Claude Code standalone | `2.1.228 (Claude Code)`; RIR `0.3.1` structural probe | `blocked` | Structural probe only; no authenticated Claude behavioral evaluation ran. |
| Claude Code with Superpowers | `2.1.237 (Claude Code)` subagent smoke; RIR `0.6.0` | `not verified` | Single-repetition behavioral smoke over the 13 claude-code cases: negatives 5/5 mechanical passes (the near-boundary planning case cited the exclusion rule verbatim); positives 0/8 produced a one-turn canonical report because the v0.5 Fast Scan path stops for the confirmation a one-turn harness never sends — 7/8 ran scan → needs_input → ask → stop exactly as documented, 1/8 did not engage the skill. Raw outputs and scorecard in [`evals/results/claude-v0.5-smoke/`](evals/results/claude-v0.5-smoke/scorecard.md). |
| Claude Code with `feature-dev` | `2.1.228 (Claude Code)`; RIR `0.3.1` structural probe | `blocked` | Structural probe only; `feature-dev` behavioral compatibility remains blocked. |
| Claude Code with Spec Kit | `2.1.228 (Claude Code)`; RIR `0.3.1` structural probe | `blocked` | Structural probe only; Spec Kit behavioral compatibility remains blocked. |
| Generic Agent Skills-compatible harness | client/version unavailable | `blocked` | No named or configured generic harness executable was available. |

The historical Codex standalone result remains **7/17** and is not evidence of support. The 7/17 and 84/85 figures are not comparable: they use different case sets (four integration adapters versus three lineage cases), different scoring functions (a narrative model judge versus the deterministic validator), and different skill generations (v0.1 versus v0.3.1). The sealed Codex-with-Superpowers v0.3.1 evidence supersedes the obsolete one-run result: all 85 selected runtime outputs passed, while one deterministic mechanical check prevents verification. The final report, controller, scorecard, manifest, raw transcripts, and quote-bound adjudications are preserved in [`evals/results/installed-v0.3.1/report.md`](evals/results/installed-v0.3.1/report.md) and [`evals/results/installed-v0.3.1/adjudication.json`](evals/results/installed-v0.3.1/adjudication.json).

### Sealed v0.3.1 evaluation evidence

This table records the immutable final evaluation evidence. It does not promote the release to verified status.

| Evidence key | Sealed value |
| --- | --- |
| release | 0.3.1 |
| composition | Codex with Superpowers |
| Codex client | codex-cli 0.148.0-alpha.21 |
| RIR plugin | requirements-impact-refiner@requirements-impact-refiner-v031-eval |
| model / reasoning | gpt-5.6-sol / high |
| runtime outcomes | 85/85 pass; 85 attempt 1 selections; no retries |
| mechanical score | 84/85; one failure: POS-cache repetition 2 |
| adjudication | 400/400 passed; model-scored, quote-bound to sealed outputs, no independent human sign-off |
| release status | not verified; one mechanical verification blocker |
| Claude probe | 2.1.228 (Claude Code) / RIR 0.3.1; structural-only, behavioral compatibility remains blocked |

The exact plugin identifier is `requirements-impact-refiner@requirements-impact-refiner-v031-eval`. It is an isolated local evaluation-only marketplace alias, not a public install ID or support claim; its wrapper marketplace file is intentionally excluded because its top-level name differs, while every functional payload component is byte-matched in the sealed [installed payload](evals/results/installed-v0.3.1/installed-payload.json) inventory. The v0.3.1 manifest digest is `8e195a0cd5584dd56980917ae97ca284e8ef1653570742bdb1838079ec99d88d`; the raw transcript inventory remains byte-preserved and secret-scanned. The lone mechanical failure records exactly a malformed Impact Ledger row and unknown `IMP-002` references in `POS-cache` repetition 2. All 400 adjudications pass; they were scored by a model, every quote is verified as a substring of the selected final output, and no independent human sign-off exists. Claude evidence is structural-only and does not change its blocked behavioral-compatibility status.

## 7. Comparison and Non-Goals

Superpowers remains the orchestrator for brainstorming, planning, execution, debugging, and review. Claude Code `feature-dev` remains its phased feature workflow. GitHub Spec Kit remains the specification and planning workflow. Requirements Impact Refiner neither replaces nor vendors them: it contributes the repository-backed impact ledger and iterative impact reduction between their clarification and planning stages.

This project does not provide broad ideation, generic PRD generation, architecture design, task breakdowns, implementation, debugging, or code review. Its narrow local MCP server and CLI control impact-report creation. The built-in fallback is a bounded lexical co-occurrence scanner, not a code-graph engine: it performs no AST parsing or semantic symbol resolution, and infers only limited import edges from lexical module specifiers. MCP hosts can still skip a tool call, so only the CLI finalize path is hard enforcement. The project does not automatically install, invoke, or chain another framework, and related-work references do not imply dependency or code reuse.

## 8. Safety and Limitations

Repository access, search, and tests improve confidence, but supplied files may be sufficient and automatic access is not guaranteed. `verified` means direct inspected support, not runtime proof unless runtime evidence was actually inspected. `inferred` and `unknown` must remain visible. An `AC-###` is a future target, never evidence that behavior already passes.

The core evaluation is **24/25**, not 25/25. The single known stochastic failure in `POS-payments-5` embedded reconcile-before-retry mechanics before the user selected a retry policy. The final checklist addresses the pattern, but the allowed correction rounds were exhausted, so the limitation remains disclosed. The separate workflow-integration final composition is **30/30**. These scores come from the recorded Codex harness and must not be generalized to untested clients.

The broader release record does not infer client support. Codex standalone strictly failed at **7/17**. Codex with Superpowers completed the full five-repetition, 85-final v0.3.1 batch, but remains `not verified` because the `POS-cache` repetition-2 mechanical failure is a release blocker despite the 85/85 runtime and 400/400 adjudication counts. External provider adapters accept detect-only contracts defined by this project, not the current upstream output formats of those tools, so naming a provider is not a claim of out-of-the-box interoperability.

The skill can miss impacts outside the inspected scope. Users should keep unresolved, deferred, blocked, and accepted risks visible through planning and validate critical behavior with appropriate human review and tests.

v0.2 is historical. The manual migration to `0.3.0` treats the first converted artifact as Revision 1 with a new `RPT-###`, `Previous SHA-256` set to `none`, and every retained impact under `new`. Do not fabricate a v0.2 predecessor digest. Subsequent revisions must preserve IDs and use the exact previous file bytes.

## 9. Report Schema and Validation

Start from the [`template chooser`](skills/requirements-impact-refiner/assets/impact-report-template.md). Version `0.3.0` separates `pre-decision` and `post-decision` reports, forbids recorded decisions before selection, and validates a complete, disjoint Impact Delta plus report lineage.

Validate a completed report with the standard-library validator:

```sh
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py --require-summary path/to/report.md
```

Validate a later revision against its exact predecessor, or print the computed Delta without modifying either file:

```sh
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py --previous previous.md current.md
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py --previous previous.md --print-expected-delta current.md
```

The validator checks required sections, definitions and references, exact evidence/state enums, decision links for `accepted`, evidence for `resolved`, `AC-###` links for critical impacts, consecutive revision numbers, stable report/impact IDs, the exact predecessor digest, and deterministic Delta transitions including `reopened`. With `--require-summary`, it also requires exactly one summary row per impact and checks that its severity and status match the ledger. Reports created before 0.3.2 remain valid without that flag. It does not verify that cited repository facts are true or locate the predecessor automatically. The optional local skill/plugin platform validators were `blocked` in this environment as described above; no pass is claimed for them.

## 10. Development and Contributing

Run the standard-library suite from the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_documentation -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for RED/GREEN evaluation discipline, five-repetition controls, validator commands, compatibility-claim rules, and the translation policy. English changes are authoritative, but every semantic README change must update `README.ko.md` and `README.ja.md` together or explicitly record a pending translation. This project is available under the [MIT License](LICENSE).
