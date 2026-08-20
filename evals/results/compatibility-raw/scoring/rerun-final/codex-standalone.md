# Codex standalone final rerun scoring

## Verdict

**FAIL — 7/17 strict case passes.**

| Group | Strict passes |
| --- | ---: |
| Positive | 0/8 |
| Negative | 3/5 |
| Integration | 4/4 |
| Total | **7/17** |

All 24 positive `must_detect` topics are mentioned and tied to the supplied facts. All eight final positive deltas list the seven required categories plus `new` and are pairwise disjoint/exhaustive. Those surface checks are not enough for a strict pass: the evidence set has first/second-turn preservation defects, decision-lifecycle defects, invalid impact states, unsupported evidence promotion, and one decision that reverses part of the explicit user selection.

## Evaluation identity and evidence composition

| Field | Value |
| --- | --- |
| Evaluator model | Fresh independent high-reasoning scorer (this report) |
| Scenario model | Controller-prescribed `gpt-5.6-luna`, medium reasoning; model identity is not embedded in each transcript |
| Client/runtime | Codex standalone fresh-context behavioral harness |
| Local CLI | `codex-cli 0.148.0-alpha.15` (recorded in `task-7-report.md`) |
| Hosted model/runtime version | Unavailable; not inferred from the local CLI version |
| Candidate skill | `skills/requirements-impact-refiner/SKILL.md`, version `0.1.0` |
| Repetitions | One nominated run per case in this 17-case Task 7 corpus |

Scored evidence:

- Original Task 7 standalone positive files except `POS-sharing`, plus `NEG-debugging`, `NEG-code-review`, and `NEG-generic-prd`, under `task7-compat-raw/codex-standalone/`.
- Replacement `POS-sharing`: `task7-compat-rerun2/codex-standalone/POS-sharing.md` and its `.part1`.
- Replacement `NEG-brainstorming`: `task7-compat-rerun1/codex-standalone/NEG-brainstorming.md`.
- Nominated preserved evidence from `task-7-report.md`: `evals/results/integration-raw/rerun-1/NEG-planning-1.md`, `rerun-1/INT-generic-1.md`, and `initial/INT-superpowers-1.md`, `initial/INT-claude-feature-dev-1.md`, `initial/INT-spec-kit-1.md`.

The discarded original `POS-sharing` and earlier brainstorming output were not scored.

## Strict method

A positive passes only if it satisfies the behavioral contract and the Task 7 evidence protocol. In particular:

- `task-7-report.md:109` requires preserving `.part1`, a literal `--- USER REVISION ---` separator, and the exact prescribed revision.
- No concrete decision or **Recorded decision** section may exist before an explicit selection.
- The only impact states are `detected`, `refining`, `mitigated`, `resolved`, `accepted`, `deferred`, `blocked`, and `superseded`; `unchanged` is a delta category, not a state.
- Every no-choice and post-choice delta must classify every known `IMP-###` exactly once across `resolved`, `mitigated`, `unchanged`, `accepted`, `deferred`, `blocked`, and `new`.
- `accepted` requires a selected `DEC-###`; `resolved` requires supporting evidence; insufficient evidence must remain `unknown` rather than being folded into a `verified` compound claim.
- Negative controls must avoid impact refinement and faithfully continue the requested neighboring workflow using only the supplied evaluation input.
- Integration controls must select one orchestrator and honor the exact adapter entry/exit without invoking the next workflow.

## Positive controls

### `POS-authorization` — FAIL

Detections are 3/3: owner/admin authorization, default-member invitations, and actor-role audit behavior are recorded as verified supplied facts (`POS-authorization.md:11-13`). The second delta is disjoint/exhaustive (`:99-107`), the accepted privilege expansion is linked to `DEC-001` (`:92`, `:102`), and no plan/edit is emitted (`:111`).

Failures:

1. The prescribed revision ends with **“Recalculate every impact.”** (`task-7-report.md:113`), but the transcript's user turn ends **“I explicitly accept that default-member invitees gain ordinary edit access immediately.”** (`POS-authorization.md:67`). It is not the exact nominated second turn.
2. Before any selection, it emits **“## Recorded decision”** and **“Decision needed — no `DEC-###` is recorded”** (`:34-36`). The skill expressly forbids a Recorded decision section before selection.
3. `IMP-003` is given state **“`unchanged`”** (`:93`), which is not an allowed impact state.
4. The initial `verified` compound claim says member audit events affect **“any downstream review or alerting that distinguishes roles”** (`:21`), while the recalculation admits **“no consumer behavior was supplied”** (`:93`). The supplied audit-event fact is verified; the downstream-consumer effect is inferred/unknown and needed to be split.

### `POS-deletion` — FAIL (behaviorally acceptable, transcript protocol invalid)

Detections are 3/3 (`POS-deletion.md:9-11`). The actual choice is quoted by `DEC-001` (`:36-40`); resolved retention/worker impacts have stated rationale (`:56-57`); the retained treatment remains accepted rather than falsely resolved and is decision-linked (`:58`, `:65`); the delta is complete (`:62-68`); no plan/edit is emitted (`:72`).

Failure: the exact prescribed turn is **“Disable sign-in immediately, retain finance-linked records for the required 30 days, then let the existing background worker complete deletion. Recalculate every impact; do not call retained data resolved.”** (`task-7-report.md:114`). The transcript contains only **“Disable sign-in immediately, retain finance-linked records for the required 30 days, then let the existing background worker complete deletion.”** after a bare `---` separator (`POS-deletion.md:34-36`). The required literal separator and exact revision were not preserved.

### `POS-api-contract` — FAIL

Detections are 3/3 (`POS-api-contract.md:11-13`). The second-turn choice, decision, evidence-backed resolution, blocked inferred consumer inventory, complete delta, and no-plan handoff are otherwise sound (`:36`, `:46`, `:52-67`, `:80`).

Failures:

1. `.part1` is not a first-response artifact: it itself contains **“--- USER REVISION ---”** and the entire second response (`POS-api-contract.md.part1:34-80`). It is byte-identical to the final `.md`, contradicting the requirement to preserve `.part1` as turn one.
2. The exact prescribed revision ends **“Recalculate every impact.”** (`task-7-report.md:115`); the recorded user line stops at **“compatibility evidence.”** (`POS-api-contract.md:36`).
3. The initial impact table has no evidence-level column—its header is **“Category | Severity | Finding | Evidence | State”**—and `IMP-001` through `IMP-003` have no `verified`/`inferred`/`unknown` level (`:17-21`). Each impact requires exactly one evidence level.

### `POS-cache` — FAIL

Detections are 3/3 (`POS-cache.md:11-13`). The second delta is disjoint/exhaustive (`:91-99`), `IMP-004` remains `unknown`/deferred (`:86`), resolved impacts cite the supplied trigger and explicit decision (`:84-85`), and no plan/edit is emitted (`:113`).

Failures:

1. The exact prescribed revision ends **“Recalculate every impact.”** (`task-7-report.md:116`); the transcript ends **“Defer any broader cache redesign.”** (`POS-cache.md:67`).
2. Before selection it emits **“## Recorded decision”** and **“Decision needed — no `DEC-###` is recorded”** (`:34-36`).
3. `IMP-003` is labeled `verified` while saying the supplied facts **“do not establish whether that event currently invalidates or refreshes dashboard response entries”** (`:21`). The verified event publication and unknown subscriber behavior should be split; the latter cannot be promoted to verified.

### `POS-payments` — FAIL

Detections are 3/3 and correctly calibrated (`verified` invariants at `POS-payments.md:13-15`; inferred duplicate/status impacts and unknown provider/bounds gaps at `:21-25`). The second decision, resolution evidence, blocked unknowns, complete delta, and no-plan handoff are sound (`:79`, `:85-101`, `:105`).

Failures:

1. `.part1` already contains the user revision and complete second response (`POS-payments.md.part1:63-115`) and is byte-identical to the final `.md`; turn one was not separately preserved.
2. The prescribed user line begins directly **“Retry only…”** and ends **“Recalculate every impact.”** (`task-7-report.md:117`). The transcript instead says **“I choose: ‘Retry only … until settlement.’”** and omits the final instruction (`POS-payments.md:65`).
3. The pre-decision delta lists only `IMP-003` under unchanged and `IMP-004`, `IMP-005` under blocked (`:47`), omitting known refining `IMP-001` and `IMP-002` (`:21-22`). It is not exhaustive.

### `POS-sharing` (rerun2) — FAIL

The replacement fixes the transcript shape: the exact revision is present (`POS-sharing.md:64-65`), `.part1` contains only turn one, detections are 3/3 (`:11-13`), the accepted exposure remains visible and linked to `DEC-001` (`:90`, `:94-100`), the delta is disjoint/exhaustive (`:102-110`), `IMP-004` remains unknown/blocked (`:89`), and no plan/edit is emitted (`:114`).

Failure: the explicit user selection says **“preserve revocation on permission changes and key rotation”** (`:65`). The second response changes this to **“continued validity across signing-key rotation”** (`:70`) and records **“signing-key rotation remains compatible with existing links”** in `DEC-001` (`:94`). It then marks the rotation ambiguity `verified`/`resolved` (`:88`). Continued validity across rotation was not selected; this reverses the key-rotation portion of the decision, so the concrete decision and resolved evidence are unsupported.

### `POS-offline-sync` — FAIL

Detections are 3/3 (`POS-offline-sync.md:11-13`). The final decision and delta are otherwise traceable and disjoint/exhaustive (`:83`, `:89-105`); the remaining UX gap stays unknown/blocked (`:92`); no plan/edit is emitted (`:109`).

Failures:

1. The prescribed revision is the direct sentence ending **“Recalculate every impact.”** (`task-7-report.md:119`). The transcript uses a bare `---`, a separate `## USER REVISION` heading, adds **“I choose:”**, and omits the final instruction (`POS-offline-sync.md:65-69`).
2. Before selection it emits **“## Recorded decision”** and **“NEEDS_DECISION — no `DEC-###` is recorded”** (`:34-36`).
3. The initial conflict, resurrection, and global-order consequences are all labeled `verified` even while their key semantics are absent: **“the supplied facts do not define timestamp authority or tie-breaking”** (`:19`), **“offline duration … [is] not bounded”** (`:20`), and **“no global sequence … is supplied”** (`:21`). These are inferred findings, not direct verified behavior.

### `POS-background-retry` — FAIL

Detections are 3/3 (`POS-background-retry.md:13-15`). The final delta is disjoint/exhaustive (`:90-98`); resolved ceiling and alert impacts cite `DEC-001` plus invariants (`:81`, `:83`); unknown gaps remain unknown (`:84-85`); no plan/edit is emitted (`:113`).

Failures:

1. The final transcript does not preserve the first response verbatim. `.part1` ends **“Stopped at the single focused retry/dead-letter policy decision. The refined requirement, preserved invariants, evidence-backed impacts, open information gaps, and provisional `AC-001`–`AC-005` targets are ready for continuation after selection.”** (`POS-background-retry.md.part1:61`), while the final file rewrites that pre-revision line to **“Stopped at the pending retry/dead-letter policy decision.”** (`POS-background-retry.md:61`).
2. The prescribed revision ends **“Recalculate every impact.”** (`task-7-report.md:120`); the transcript's user turn stops at **“publish the existing `dead_letter` event after the ceiling.”** (`POS-background-retry.md:65`).
3. Recalculated `IMP-002` is assigned state **“`unchanged`”** (`:82`). `unchanged` belongs only in the delta; the impact should retain an allowed lifecycle state such as `refining`.
4. Initial `IMP-003` is `verified` despite the hypothetical and unavailable event semantics: **“the existing `dead_letter` event may stop being emitted”** and **“current event emission threshold … [is] not otherwise supplied”** (`:23`). That finding is inferred, not verified.

## Negative controls

### `NEG-brainstorming` (rerun1) — PASS

The replacement faithfully brainstorms a fitness app (**“# Fitness app brainstorming”**, `NEG-brainstorming.md:1`) and supplies six distinct fitness directions (`:5-63`) without any impact-refiner IDs or repository-evidence claims.

### `NEG-planning` (nominated rerun-1) — PASS

It performs the requested neighboring workflow: **“## Implementation plan”** (`NEG-planning-1.md:7`) followed by persistence, API, UI, test, and verification tasks (`:9-42`). It does not repeat impact refinement or replace planning. The plan is allowed and required in this negative control; the positive-case no-plan prohibition does not apply here.

### `NEG-debugging` — PASS

It explicitly says **“This is a debugging task”** and **“requirements-impact-refiner … does not activate”** (`NEG-debugging.md:5-9`), then gives an evidence-first debugging workflow (`:22-42`). It does not rewrite the requirement.

### `NEG-code-review` — FAIL (input/provenance contamination)

The response remains a code review and emits no impact-refiner artifacts, but it does not stay within the supplied evaluation input. The case supplied only the fact that a complete diff exists; the Task 7 prompt prohibited inspecting other workspace files. The response nevertheless claims it **“Reviewed the complete pull-request diff from `main` (`03523bb`) through `7a260ca`”** (`NEG-code-review.md:5-6`) and **“Ran: python3 -m unittest discover -s tests -v … 36 tests passed”** (`:24-30`). Those commit/test observations are not in `cases.json`. This is not a controlled run using only the case request and `repository_evidence`, so it cannot be accepted as fresh standalone neighboring-workflow evidence.

### `NEG-generic-prd` — FAIL (wrong/unsupplied product idea)

The evaluation provides no product-idea text, so the neighboring PRD workflow should request it or clearly remain a template. Instead the response invents a specific subject, **“# Product Requirements Document: Requirements Impact Refiner”** (`NEG-generic-prd.md:1`), and defines **“Requirements Impact Refiner … [as] a planning assistant”** (`:10`). That subject is taken from the skill/workspace rather than the supplied request. As with the earlier meditation-versus-fitness failure, staying in the nominal document genre is insufficient when the neighboring workflow is not faithful to the user's supplied subject.

## Integration controls

### `INT-generic` — PASS

Exactly generic/no named orchestrator is active (`INT-generic-1.md:5`). It enforces the entry gate because the substantive requirement and inspection scope are missing (`:7-10`) and emits no canonical IDs/report (`:12`). It does not invoke an external framework or write tasks.

### `INT-superpowers` — PASS

The sole selected mode is `superpowers`; entry is after approved brainstorming and exit is before `writing-plans` (`INT-superpowers-1.md:5-8`). It reiterates that no ideation, external invocation, work breakdown, or plan is performed (`:126`).

### `INT-claude-feature-dev` — PASS

The sole selected mode is `claude-feature-dev`; entry is after Phase 3 and exit is before Phase 4 architecture, with no repeated clarification, architecture, or tasks (`INT-claude-feature-dev-1.md:5-9`, `:127`).

### `INT-spec-kit` — PASS

The report consumes `speckit.clarify`, exits before `speckit.plan`, and explicitly avoids repeating specification or invoking planning (`INT-spec-kit-1.md:13`, `:86`). Exactly one orchestrator owns the handoff.

## Cross-cutting checks

| Check | Result |
| --- | --- |
| Positive must-detect topics | 24/24 detected and tied to supplied facts |
| Exact positive two-turn evidence | 1/8 (`POS-sharing` only) |
| Final positive seven-category delta | 8/8 structurally disjoint/exhaustive |
| Pre-decision delta | 7/8; `POS-payments` omits `IMP-001` and `IMP-002` |
| Accepted risk with concrete decision link | Present wherever `accepted` is used |
| Resolved evidence | Present except unsupported sharing key-rotation resolution |
| Unknown not promoted | Explicit unknown rows remain unknown, but four positive reports contain compound `verified` claims whose unsupplied portion is inferred/unknown |
| Positive plan/edit prohibition | 8/8; none writes a plan or repository edit |
| Negative neighboring workflow | 3/5 strict; code-review provenance and PRD subject are invalid |
| Integration ownership | 4/4 exact |

## Blocking violations

1. Seven original positive transcripts do not preserve the exact prescribed second user turn; API/payments overwrite `.part1` with both turns, and background-retry also rewrites first-turn content.
2. Authorization, cache, and offline-sync create a Recorded decision section before selection; authorization and background-retry use invalid lifecycle state `unchanged`.
3. Payments' no-choice delta omits two known impacts.
4. Sharing rerun2 invents continued validity across signing-key rotation and resolves it despite the explicit selection preserving revocation on key rotation.
5. Several verified rows combine supplied facts with unsupported consumer, cache-subscriber, timestamp/order, or dead-letter semantics instead of splitting inferred/unknown assertions.
6. The code-review run imports uncontrolled repository/test evidence, and the generic-PRD run invents the Requirements Impact Refiner as the missing product idea.

Because a single strict failure is enough to reject the available-environment corpus, this Codex standalone compatibility corpus does not support a release `supported` claim.
