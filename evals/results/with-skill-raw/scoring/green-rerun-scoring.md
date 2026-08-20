# GREEN rerun evaluation scoring — Requirements Impact Refiner

## Scope and recommendation

- **Corpus:** all 15 transcripts in `green-rerun-raw/`: five each for `POS-api-contract`, `POS-payments`, and `NEG-planning`.
- **Contract:** `evals/cases.json`, the current `skills/requirements-impact-refiner/SKILL.md`, and its evidence-model/refinement-loop references.
- **Recommendation: FAIL under the stated strict criteria.** The reruns completely repair the planning-negative control-flow issue: every negative transcript exits the skill without emitting any `REQ`/`INV`/`IMP`/`DEC`/`AC` artifact and then fulfills the normal planning request. All 30 positive must-detect items are explicit and evidence-tied, and no transcript modifies the repository or emits an implementation work breakdown. However, two API runs fabricate a `DEC-001` from a deprecation constraint without a supplied selection; one API run references an uncreated future `DEC-001`; and two whole-set deltas omit material impacts.

## Scoring rules

- A positive must-detect is **D** only when it is tied to a supplied fact or expressly classified `inferred`/`unknown`. **P** is relevant but incomplete; **M** is absent/nonconforming.
- `EC` requires an explicit evidence-confidence label on each material finding. `IDs` requires stable and appropriate identifiers: a `DEC-###` exists only after an explicit supplied or stakeholder selection, and links may reference only existing IDs.
- `UDL` requires the ledger before a needed decision, exactly 2–3 concrete options, and no fabricated recorded choice. `WSR` requires a complete-set delta that accounts for every material `IMP` and includes all categories with `new: none` where applicable.
- `A≠R` requires that accepted impacts have a valid recorded-decision link and resolved impacts have supporting evidence. `Plan` and `Modify` score the two positive must-not-do items.
- For `NEG-planning`, **pass** means the skill emits none of its artifacts and ordinary implementation planning then continues. An implementation plan is therefore required normal-workflow behavior here, not a violation.

## Positive runs

Legend: M = mobile consumer; S = stored payload; B = backward compatibility; K = idempotency key; U = user-visible status; C = duplicate capture.

### POS-api-contract

| Run | M | S | B | Plan | Modify | EC | IDs | UDL | WSR | A≠R | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `POS-api-contract-1.md` | D | D | D | No | No | Yes | **M** | Yes | **M** | Yes | Fail |
| `POS-api-contract-2.md` | D | D | D | No | No | Yes | Yes | Yes | Yes | Yes | Pass |
| `POS-api-contract-3.md` | D | D | D | No | No | Yes | Yes | Yes | Yes | Yes | Pass |
| `POS-api-contract-4.md` | D | D | D | No | No | Yes | **M** | **M** | Yes | Yes | Fail |
| `POS-api-contract-5.md` | D | D | D | No | No | Yes | **M** | **M** | Yes | Yes | Fail |

Case result: **15/15 required detections D; 0/10 positive must-not-do violations.** The failures are decision/traceability or recalculation defects, not missing API impacts.

### POS-payments

| Run | K | U | C | Plan | Modify | EC | IDs | UDL | WSR | A≠R | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `POS-payments-1.md` | D | D | D | No | No | Yes | Yes | Yes | Yes | Yes | Pass |
| `POS-payments-2.md` | D | D | D | No | No | Yes | Yes | Yes | **M** | Yes | Fail |
| `POS-payments-3.md` | D | D | D | No | No | Yes | Yes | Yes | Yes | Yes | Pass |
| `POS-payments-4.md` | D | D | D | No | No | Yes | Yes | Yes | Yes | Yes | Pass |
| `POS-payments-5.md` | D | D | D | No | No | Yes | Yes | Yes | Yes | Yes | Pass |

Case result: **15/15 required detections D; 0/10 positive must-not-do violations.** Each run ties idempotency, pre-settlement status, and post-capture timeout to supplied facts or explicitly labels uncertainty.

## NEG-planning

| Run | Skill exited/no `REQ`/`INV`/`IMP`/`DEC`/`AC` artifacts | Normal implementation-planning workflow continued | Result |
| --- | --- | --- | --- |
| `NEG-planning-1.md` | Yes | Yes | Pass |
| `NEG-planning-2.md` | Yes | Yes | Pass |
| `NEG-planning-3.md` | Yes | Yes | Pass |
| `NEG-planning-4.md` | Yes | Yes | Pass |
| `NEG-planning-5.md` | Yes | Yes | Pass |

Case result: **10/10 negative must-not-do checks pass.** These are ordinary plans with headings such as `Implementation plan`/`Work plan`; that is correct after the skill's early exit. None repeats impact refinement or introduces a skill artifact.

## Confirmed misses and violations

Every excerpt below is exact. Absolute paths identify the source transcript.

| Run / criterion | Result | Exact excerpt | Source path | Why it fails |
| --- | --- | --- | --- | --- |
| API 1 / IDs | M | “Currently blocked pending `DEC-001` (if selected).” | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun-raw/POS-api-contract-1.md:58` | `DEC-001` has not been recorded. The evidence model permits only existing IDs in links, while the skill permits a `DEC-###` only after selection. |
| API 1 / whole-set delta | M | “`unchanged: IMP-004` — possible external consumers remain unverified.”; “`blocked: IMP-005, IMP-006` — cache policy/test evidence is missing.” | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun-raw/POS-api-contract-1.md:44` | `IMP-001`–`IMP-003` are `refining` in the ledger but disappear from the delta. The delta is therefore not a complete recalculation. |
| API 4 / IDs and decision loop | M | “The recorded choice below adopts the compatibility-preserving option implied by the supplied iOS and cache invariants.”; “`DEC-001` — During the one-version deprecation window, responses expose canonical `name` and retain legacy `displayName` as a deprecated alias…” | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun-raw/POS-api-contract-4.md:32` | The supplied facts establish only a deprecation window; they do not select alias emission, two-name reads, cache behavior, or precedence. Creating `DEC-001` fabricates a recorded choice and provides no 2–3 options for that unresolved decision. |
| API 5 / IDs and decision loop | M | “No additional stakeholder choice is required for this contract refinement.”; “`DEC-001` — Adopt the published one-version deprecation policy: add `name` as the canonical field, retain `displayName` as a deprecated compatibility alias…” | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun-raw/POS-api-contract-5.md:27` | A one-version promise does not select the particular dual-alias response/cache policy. This is an unsupported decision artifact rather than a user-supplied choice. |
| Payments 2 / whole-set delta | M | “`unchanged` | none; this is the initial refinement ledger”; “`blocked` | `IMP-006` — provider error/status semantics are missing” | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun-raw/POS-payments-2.md:46` | `IMP-001`–`IMP-005` are material `refining`/`detected` findings in the ledger, but no delta category accounts for them. Calling it an initial ledger does not satisfy the required complete delta. |

### Exact transcript paths

- [API 1](/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun-raw/POS-api-contract-1.md:58)
- [API 4](/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun-raw/POS-api-contract-4.md:32)
- [API 5](/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun-raw/POS-api-contract-5.md:27)
- [Payments 2](/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun-raw/POS-payments-2.md:40)

## Aggregate

| Measure | Count |
| --- | ---: |
| Transcripts scored | 15/15 |
| Positive required detections | 30/30 D |
| Positive implementation-work-breakdown violations | 0/10 |
| Positive repository modifications | 0/10 |
| Positive evidence-confidence passes | 10/10 |
| Positive stable/appropriate-ID passes | 7/10 |
| Positive decision-loop passes | 8/10 |
| Positive complete-delta passes | 8/10 |
| Positive accepted-vs-resolved passes | 10/10 |
| NEG-planning artifact-free early exits | 5/5 |
| NEG-planning normal-planning continuations | 5/5 |
| NEG-planning must-not-do violations | 0/10 |
| Confirmed root defects | 4 |
| Confirmed affected rubric checks | 5 |

## Conclusion

The fresh rerun fixes the prior blocking `NEG-planning` behavior and retains solid, evidence-grounded API and payment impact detection. It should still be rejected under the strict contract until it (1) never allocates or links a `DEC-###` before a real selection, (2) presents 2–3 options instead of synthesizing a compatibility-policy decision, and (3) makes every delta account for all material `IMP-###` entries even before a decision.
