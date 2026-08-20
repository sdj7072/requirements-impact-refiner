# Codex + Superpowers compatibility score — independent rerun-final audit

## Verdict

**STRICT FAIL for a release-compatible claim.** The mixed corpus has **10 pass, 7 partial, 0 fail** case results (**58.8% strict case pass rate**). All 24 positive `must_detect` facts are present and evidence-linked, all five negatives stay in their neighboring workflows, and all four integrations preserve one-orchestrator ownership and the named adapter boundary. However, only the two rerun3 positive replacements preserve the first response byte-for-byte and include the required exact `--- USER REVISION ---` turn separator. Six original positive transcripts do not. `POS-sharing` also violates pairwise-disjoint delta membership, and several positive findings do not obey the one-evidence-level-per-impact rule.

This is one supplied result per case, not the five fresh-context repetitions required by `evals/runbook.md`. It is therefore not sufficient for a documented compatibility/support claim even if every case had passed.

## Metadata and corpus selection

| Field | Audited value |
| --- | --- |
| Environment label | Codex + installed Superpowers |
| Executed client/model/version | Not recorded inside the 17 selected transcripts; no exact executed version is inferred from controller instructions or repository state |
| Repetitions | One supplied result per case |
| Cases | 17: eight positive, five negative, four integration |
| Primary corpus | `.superpowers/sdd/2026-08-20-requirements-impact-refiner/task7-compat-raw/codex-superpowers/` |
| Required replacements | `POS-authorization` and `POS-api-contract` from `task7-compat-rerun3/codex-superpowers/` |
| Contract | `evals/cases.json`, `evals/runbook.md`, `skills/requirements-impact-refiner/SKILL.md`, `evidence-model.md`, `impact-taxonomy.md`, `refinement-loop.md`, and all four integration adapters |
| Audit method | Manual line audit plus byte-prefix comparison of every selected positive final against its selected `.part1` |

### Verdict definitions

- **Pass:** every case-specific detection and prohibition passes, and every applicable strict core-contract check passes.
- **Partial:** the requested neighboring/impact behavior is substantially present, but at least one strict transcript, evidence, lifecycle, or delta condition fails.
- **Fail:** a required case fact is absent, a forbidden neighboring workflow is performed/replaced, a decision is fabricated without a selection, or integration ownership is materially wrong.

## Exact two-turn preservation audit

The controller contract required each positive final to contain: the exact preserved `.part1`, the literal separator `--- USER REVISION ---`, the exact follow-up, and the complete second response. A byte-prefix check was used rather than accepting a paraphrased reconstruction.

| Positive case | Final begins with exact `.part1` bytes | Literal separator exactly once | Exact follow-up preserved | Turn result |
| --- | --- | --- | --- | --- |
| POS-authorization (rerun3) | yes | yes | yes | pass |
| POS-api-contract (rerun3) | yes | yes | yes | pass |
| POS-deletion (original) | **no** | **no** | **no** | partial |
| POS-cache (original) | **no** | **no** | **no** | partial |
| POS-payments (original) | **no** | **no** | **no** | partial |
| POS-sharing (original) | **no** | **no** | yes | partial |
| POS-offline-sync (original) | **no** | **no** | **no** | partial |
| POS-background-retry (original) | **no** | **no** | **no** | partial |

The six `no` byte-prefix results are not cosmetic. Each final rewrites, condenses, or merely refers to the first response rather than preserving the actual first turn. The separate `.part1` files prove that a pending-decision response existed, but the required assembled final transcript does not preserve that turn exactly.

## Positive-case results

| Case | Must-detect result | Decision/evidence/delta result | Verdict |
| --- | --- | --- | --- |
| POS-authorization | **3/3:** owner/admin authorization, default-member invitations, and actor-role audit behavior are direct verified invariants at rerun3 final lines 13–15. | Exact two turns; no pre-selection concrete decision; `DEC-001` follows the exact revision; accepted `IMP-002` links to it; resolved `IMP-004` cites the explicit field-boundary selection while retaining `unknown` implementation evidence; all four IDs appear once in the seven-category delta; no plan/edit. | **Pass** |
| POS-deletion | **3/3:** foreign-key restriction, 30-day retention, and background-worker cleanup are direct verified invariants at final lines 11–13. | The selected policy and `DEC-001` are explicit; retained finance data is accepted rather than resolved; the unknown personal-data gap remains unknown; delta IDs are exhaustive/disjoint; no plan/edit. The assembled final does not preserve the exact first turn or exact revision separator/follow-up. | **Partial** |
| POS-api-contract | **3/3:** iOS decoder, persisted cached JSON, and one-version promise are direct invariants at rerun3 final lines 11–13. | Exact two turns; `DEC-001` follows the exact revision; external-consumer/removal evidence stays `unknown`/`blocked`; four IDs appear once in the seven-category delta; no plan/edit. The first-turn `IMP-003` combines `verified` and `unknown` in one impact instead of splitting findings with different evidence levels. | **Partial** |
| POS-cache | **3/3:** tenant dependency, current role-change invalidation path, and `dashboard.updated` are direct verified invariants at final lines 19–21. | `DEC-001` records the selected tenant/auth key and both invalidation paths; all three known impacts appear once; none is falsely resolved; no plan/edit. The final is the post-decision report first and merely refers to `.part1`, so the required exact two-turn transcript is absent. | **Partial** |
| POS-payments | **3/3:** idempotency key, pre-webhook UI status, and timeout-after-capture are direct invariants at final lines 11–13. | The selected reconciliation policy precedes `DEC-001`; provider semantics and retry bounds remain `unknown`/`blocked`; resolved policy ambiguities cite `DEC-001` plus supplied facts; all five IDs appear once; no plan/edit. The final does not preserve `.part1` or the exact separator/follow-up. | **Partial** |
| POS-sharing | **3/3:** seven-day expiry, permission-change revocation, and 90-day key rotation appear in the initial evidence at final lines 9–11 and recalculated ledger lines 39–43. | Explicit acceptance is linked to `DEC-001`; deletion lifecycle remains `unknown`/`deferred`; no plan/edit. The final does not preserve exact `.part1`; the first-turn key-rotation impact is promoted to `verified` despite explicitly unavailable rollover behavior; and `IMP-005` appears in both `accepted` and `new`, so the delta is not pairwise disjoint. | **Partial** |
| POS-offline-sync | **3/3:** timestamp signal, 24-hour tombstones, and local-only creation order are direct invariants at final lines 13–15. | `DEC-001` follows an explicit selection; unresolved conflict UX stays `unknown`/`blocked`; no accepted or resolved risk is fabricated; all delta ID sets are formally disjoint; no plan/edit. The final does not preserve exact `.part1`; several compound impacts use one `verified` label for a selected policy and explicitly unsupported timestamp/dependency behavior. | **Partial** |
| POS-background-retry | **3/3:** deterministic object key, current five-attempt ceiling, and `dead_letter` alert consumer are direct invariants at final lines 9–11. | `DEC-001` records the 20-attempt/backoff/dead-letter policy; unknown failure taxonomy remains blocked; the delta is exhaustive/disjoint; no plan/edit. The final does not preserve exact `.part1`; the first-turn dead-letter consequence is labeled `verified` even while event-threshold/recovery semantics are said to be unavailable. | **Partial** |

### Exact quotations for every positive partial

#### POS-deletion — exact-turn failure

The saved first response starts:

> `# POS-deletion — Requirements Impact Refinement (decision needed)`

— `task7-compat-raw/codex-superpowers/POS-deletion.md.part1:1`

The final instead starts:

> `# POS-deletion — Requirements Impact Refinement`

— `task7-compat-raw/codex-superpowers/POS-deletion.md:1`

It then moves through a generic rule and a rewritten heading rather than the required literal user-revision separator:

> `---`
>
> `## Part 2 — decision response and revised requirement`

— `task7-compat-raw/codex-superpowers/POS-deletion.md:28-30`

The quoted selection also omits the exact follow-up clauses “Recalculate every impact; do not call retained data resolved.”

#### POS-api-contract — mixed evidence levels in one impact

> `| IMP-003 | The rename must honor the public one-version deprecation promise; the exact wire and reader/writer mechanics are not selected by that promise alone. | verified for the promise; unknown for the mechanics — supplied fact, public API changelog | refining | affects REQ-001, INV-003; produces AC-003 |`

— `task7-compat-rerun3/codex-superpowers/POS-api-contract.md:21` (backticks omitted in this quotation only for readability)

The evidence model requires exactly one evidence level per `IMP-###` and requires compound findings with different levels to be split. This row explicitly assigns two levels to one impact.

#### POS-cache — exact-turn failure

The saved first response starts:

> `# Requirements Impact Report — POS-cache (needs decision)`

— `task7-compat-raw/codex-superpowers/POS-cache.md.part1:1`

The final starts with the post-decision report:

> `# Requirements Impact Report — POS-cache`

— `task7-compat-raw/codex-superpowers/POS-cache.md:1`

Its only handling of the earlier turn is a reference, not preservation:

> `## Pre-decision record`
>
> `The preceding POS-cache.md.part1 contains the initial ledger and the focused options presented before selection. DEC-001 above is the explicit response and supersedes the pending-decision state; all known impacts are recalculated in the complete report above.`

— `task7-compat-raw/codex-superpowers/POS-cache.md:98-100` (inline backticks omitted in the quotation only for readability)

#### POS-payments — exact-turn failure

The saved first response records the requirement as a table row:

> `| REQ-001 | Retry every failed charge automatically, while preserving the existing idempotency contract, keeping the pre-webhook payment state accurate, and preventing a timeout after capture from becoming a duplicate capture. The exact retry and reconciliation policy remains the pending decision. | NEEDS_DECISION | — |`

— `task7-compat-raw/codex-superpowers/POS-payments.md.part1:7` (inline backticks omitted in the quotation only for readability)

The final rewrites it as prose and later substitutes a decision-labelled heading for the literal separator:

> `REQ-001: Retry every failed charge automatically, while preserving the existing idempotency contract, keeping the pre-webhook payment state accurate, and preventing a timeout after capture from becoming a duplicate capture. The exact retry and reconciliation policy remains the pending decision.`
>
> `## User revision — DEC-001`

— `task7-compat-raw/codex-superpowers/POS-payments.md:5,51` (inline backticks omitted in the quotation only for readability)

The selected sentence at line 53 also omits the exact trailing “Recalculate every impact.”

#### POS-sharing — exact-turn, evidence-level, and delta failures

The first-turn status changed between the saved turn and the final reconstruction:

> `NEEDS_DECISION — the request is under-specified. No option has been selected; no implementation plan or repository edit is proposed.`

— `task7-compat-raw/codex-superpowers/POS-sharing.md.part1:5`

> `NEEDS_DECISION — the initial request was under-specified. The first response recorded no decision and stopped at one focused question.`

— `task7-compat-raw/codex-superpowers/POS-sharing.md:5`

The final uses a heading, not the required literal separator:

> `## USER REVISION`

— `task7-compat-raw/codex-superpowers/POS-sharing.md:23`

The initial rotation impact is labelled direct/verified although its own row says the relevant repository behavior is unavailable:

> `| IMP-003 | Tokens that outlive a 90-day signing-key rotation require key-version/history or re-issuance semantics; otherwise permanent links break at rotation or force unsafe indefinite key retention. | Compatibility | high | verified | blocked | Supplied 90-day signing-key rotation; rollover and retention behavior are not supplied. | INV-003 | AC-003 |`

— `task7-compat-raw/codex-superpowers/POS-sharing.md.part1:25` (inline backticks omitted in the quotation only for readability)

Finally, the same ID appears in two delta categories:

> `- accepted: IMP-005`
>
> `- new: IMP-005, IMP-006, IMP-007`

— `task7-compat-raw/codex-superpowers/POS-sharing.md:52,55` (inline backticks omitted in the quotation only for readability)

This makes the stated claim that the categories are disjoint at line 57 false.

#### POS-offline-sync — exact-turn and evidence-level failures

The saved first response begins its body with:

> `## Requirement revision`

— `task7-compat-raw/codex-superpowers/POS-offline-sync.md.part1:3`

The final inserts a different wrapper and later a different decision heading:

> `## First pass: requirement and impact refinement`
>
> `## User decision`

— `task7-compat-raw/codex-superpowers/POS-offline-sync.md:3,36`

There is no literal `--- USER REVISION ---`, and the selection at line 38 omits “Recalculate every impact.”

The recalculated ledger also uses `verified` for rows that combine an explicit selected policy with unavailable semantics or an inferred post-expiry consequence:

> `| IMP-001 | updated_at is the selected conflict signal outside the tombstone window; clock skew, equal timestamps, and timestamp authority remain validation limits. | verified | mitigated | DEC-001 and INV-001; no stronger timestamp semantics supplied. | ... |`
>
> `| IMP-002 | Server deletion is authoritative while its 24-hour tombstone exists, preventing stale replay during that window; after expiry, absent durable deletion knowledge leaves resurrection possible. | verified | mitigated | DEC-001 and INV-002; tombstone retention remains 24 hours. | ... |`

— `task7-compat-raw/codex-superpowers/POS-offline-sync.md:54-55` (backticks and link tail abbreviated only for readability)

Those selected-policy and unsupported-behavior assertions need splitting into separate evidence levels; the later `IMP-005` correctly labels the post-expiry consequence `inferred` at line 58.

#### POS-background-retry — exact-turn and evidence-level failures

The saved first response uses:

> `## Requirement revision`

— `task7-compat-raw/codex-superpowers/POS-background-retry.md.part1:3`

The final replaces it and later uses a non-literal revision heading:

> `## Initial requirement and preserved behavior`
>
> `## Explicit stakeholder revision`

— `task7-compat-raw/codex-superpowers/POS-background-retry.md:3,33`

There is no literal `--- USER REVISION ---`, and the selection at line 35 omits “Recalculate every impact.”

The initial dead-letter impact is also assigned `verified` even though the row itself says the event threshold and recovery semantics are unavailable:

> `| IMP-003 | If jobs no longer become terminal after five attempts, the existing dead_letter event may stop being emitted, causing alert consumers to lose notification of permanently unhealthy exports. | verified | refining | INV-002 and INV-003; current event threshold and alert recovery semantics are not otherwise supplied. | ... |`

— `task7-compat-raw/codex-superpowers/POS-background-retry.md.part1:23` (backticks and link tail abbreviated only for readability)

The supplied facts verify the current ceiling and alert consumer, but the conditional emission consequence is indirect and should be `inferred` unless direct producer/threshold evidence is supplied.

## Negative-case results

| Case | Neighboring workflow and prohibition audit | Verdict |
| --- | --- | --- |
| NEG-brainstorming | Stays in product ideation; no impact IDs and no repository-evidence claims. Representative lines 1–5: “Fitness app brainstorming” and “architectural ideation pass.” | **Pass** |
| NEG-planning | Produces the requested coding-task plan and explicitly says not to repeat refinement/recalculate/create impact artifacts at lines 13–20. This is correct planning ownership, not a forbidden replacement by the refiner. | **Pass** |
| NEG-debugging | Routes to `systematic-debugging`, explicitly declines impact-refiner activation and impact IDs at lines 5–10, and keeps hypotheses unconfirmed at lines 20–23. | **Pass** |
| NEG-code-review | Performs correctness review, explicitly identifies impact refinement as excluded at lines 5–10, and provides a review verdict rather than requirement artifacts. | **Pass** |
| NEG-generic-prd | Produces a standalone draft PRD; it does not emit impact IDs or claim that any finding came from repository inspection. | **Pass** |

No negative performs a prohibited repository modification. `NEG-planning` is the only case that authors an implementation plan, and that is the requested neighboring workflow, not a violation of its case rubric.

## Integration-case results

| Case | Ownership / entry / exit evidence | Verdict |
| --- | --- | --- |
| INT-generic | Selects `generic` with no named external workflow at lines 3–10. Correctly holds the updated entry gate because substantive requirement text and repository scope/evidence target are missing at lines 12–28. It emits no canonical IDs/plan and hands off to the user-selected planning method without auto-start at lines 30–41. | **Pass** |
| INT-superpowers | States Superpowers is sole owner, enters after approved `brainstorming`, and exits before `writing-plans` at lines 3–8. It does not reopen ideation, keeps missing design/repository evidence `unknown`/`blocked`, and does not invoke or author `writing-plans` at lines 98–108. | **Pass** |
| INT-claude-feature-dev | Preserves completed Phase 3 as baseline and the pre-Phase-4 boundary at lines 7–15. It selects Claude feature-dev as the planning owner at line 94 and explicitly does not invoke/perform Phase 4 at lines 96–98. No second orchestrator or tasks are introduced. | **Pass** |
| INT-spec-kit | Explicitly selects Spec Kit alone and rejects Superpowers co-ownership at lines 5–7. It does not repeat specification, write tasks, or invoke `speckit.plan`, and exits immediately before it at lines 9–15. | **Pass** |

## Cross-cutting lifecycle audit

| Check | Result |
| --- | --- |
| Positive case-specific facts | **24/24 detected** and connected to supplied evidence |
| Pre-selection concrete decision IDs | None in either exact rerun3 first turn or the six selected standalone `.part1` files; generic “pending decision” wording is used |
| Concrete decisions after explicit choice | Present in all eight post-decision reports, but six fail the required exact assembled-turn preservation |
| Accepted impacts | `POS-authorization/IMP-002`, `POS-deletion/IMP-002`, and `POS-sharing/IMP-005` all link a concrete `DEC-001` |
| Resolved impacts | Every resolved row cites an explicit requirement selection plus supplied evidence; no resolution is based on silence. `POS-authorization/IMP-004` remains evidence-level `unknown` while explaining that only the requirements ambiguity was resolved |
| Unknown promotion | No row changes an explicitly unknown repository fact into verified repository behavior after the decision. Separate evidence-classification defects are quoted above |
| Seven-category presence | Present in all eight positive second-response content blocks |
| Exhaustive/disjoint delta | Seven of eight positive deltas are ID-exhaustive/disjoint; `POS-sharing` duplicates `IMP-005` under `accepted` and `new` |
| Report-only handoff | All positive and integration cases stop before implementation planning; no repository edit is performed |
| Integration ownership | Four of four select exactly one applicable mode and preserve adapter entry/exit boundaries |

## Aggregate

| Population | Pass | Partial | Fail | Strict result |
| --- | ---: | ---: | ---: | --- |
| Positive (8) | 1 | 7 | 0 | 24/24 must-detect facts, but six exact-turn failures, one delta-overlap failure, and evidence-level defects |
| Negative (5) | 5 | 0 | 0 | All remain in neighboring workflows |
| Integration (4) | 4 | 0 | 0 | All preserve one owner and exact boundary |
| **Total (17)** | **10** | **7** | **0** | **58.8% strict passes** |

## Release conclusion

Do not record Codex + Superpowers as verified/supported from this corpus. A valid rerun needs, at minimum:

1. fresh two-turn reruns for `POS-deletion`, `POS-cache`, `POS-payments`, `POS-sharing`, `POS-offline-sync`, and `POS-background-retry`, with exact `.part1` preservation, the literal revision separator, the exact follow-up, and the full second response;
2. a disjoint `POS-sharing` delta in which each ID appears once (a newly discovered accepted risk belongs to one delta category, not both `accepted` and `new`);
3. split findings wherever verified selection/current behavior and inferred or unknown mechanics are combined in one `IMP-###`; and
4. the runbook-required fresh-context repetition count plus exact executed model/client/version metadata.
