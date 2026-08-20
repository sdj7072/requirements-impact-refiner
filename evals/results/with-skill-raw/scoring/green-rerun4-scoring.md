# GREEN rerun 4 — strict transcript scoring

## Result and recommendation

**8/10 pass; 2/10 fail. Recommendation: do not mark the rerun green.**

Scored the ten `green-rerun4-raw` transcripts against the two applicable cases in `evals/cases.json` and the current `requirements-impact-refiner` skill, evidence model, taxonomy, and refinement-loop references. A pass requires evidence-tied required detections; one explicit evidence level per `IMP`; stable IDs; no implementation plan or repository modification; a concrete policy/`DEC` only after an exact explicit user or stakeholder selection; two or three options for an unresolved decision; no unsupported acceptance; and an exhaustive, pairwise-disjoint delta with every category and `new: none`.

| Transcript | Case | Result | Strict basis |
| --- | --- | --- | --- |
| `green-rerun4-raw/POS-api-contract-1.md` | POS-api-contract | **PASS** | All three required impacts are evidence-tied; the three-way compatibility choice remains pending; no policy is selected; the five-impact delta is exhaustive and disjoint. |
| `green-rerun4-raw/POS-api-contract-2.md` | POS-api-contract | **PASS** | Detects the iOS reader, cached payload, and deprecation promise; offers three options without a recorded choice; all four impacts occur once in the complete delta. |
| `green-rerun4-raw/POS-api-contract-3.md` | POS-api-contract | **PASS** | Each required finding has one evidence level, the decision is plainly pending, and the delta partitions `IMP-001`–`IMP-004` correctly. |
| `green-rerun4-raw/POS-api-contract-4.md` | POS-api-contract | **PASS** | Required consumer, cache, and compatibility risks are linked to supplied evidence; no policy is chosen; all five impacts are placed once across unchanged/blocked. |
| `green-rerun4-raw/POS-api-contract-5.md` | POS-api-contract | **FAIL** | The requirement revision selects dual-read/single-write cache/contract mechanics before the unresolved choice, and a purportedly verified criterion asserts unsupported new-key iOS decoding. |
| `green-rerun4-raw/POS-payments-1.md` | POS-payments | **PASS** | Idempotency, pre-settlement status, and duplicate-capture risks are evidence-tied; the three policy options remain pending; all six impacts are partitioned once. |
| `green-rerun4-raw/POS-payments-2.md` | POS-payments | **PASS** | All required payment detections are present with levels and supplied evidence; three alternatives are presented without selecting one; the four-impact delta is exhaustive and disjoint. |
| `green-rerun4-raw/POS-payments-3.md` | POS-payments | **PASS** | The ledger ties idempotency, late-settlement status, and duplicate capture to the supplied facts; it keeps the three-way decision pending and has a complete five-impact delta. |
| `green-rerun4-raw/POS-payments-4.md` | POS-payments | **PASS** | Required risks and named information gaps are explicit; no decision or acceptance is fabricated; all five impacts appear once in the delta. |
| `green-rerun4-raw/POS-payments-5.md` | POS-payments | **FAIL** | The revised requirement preselects the reconcile-first/retry-only-confirmed-retryable policy even though the transcript states that no policy was selected. |

## Confirmed failures

### `POS-api-contract-5.md` — unsupported mechanics selection and unsupported verified criterion

The transcript says the transition mechanics have not been selected, but its requirement revision already fixes the mechanics corresponding to dual-read/single-write: new payloads and persisted JSON use `name`, while old data is only read during the compatibility window. This is a concrete transition-policy choice, not merely the supplied one-version constraint.

- Exact excerpt: “`name` is the canonical field for new contract payloads and persisted profile JSON; legacy `displayName` data remains readable only for that compatibility window and is removed at its published boundary.”
- Source: `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun4-raw/POS-api-contract-5.md:5`
- Contradicting exact excerpt: “No `DEC-###` is recorded: the request supplies the deprecation constraint but does not select one of the transition mechanics.”
- Source: `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun4-raw/POS-api-contract-5.md:33`

The criterion also claims as `verified` that a `name` payload decodes in the existing iOS reader, although the only supplied direct evidence says that reader decodes `displayName`. The new-key behavior is a pending transition outcome, not verified current behavior.

- Exact excerpt: “During the compatibility version, an iOS payload containing legacy `displayName` still decodes to the existing user-name value; a payload containing `name` decodes as the canonical value. Evidence: `ios/UserDTO.swift` behavior and `INV-001`.”
- Source: `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun4-raw/POS-api-contract-5.md:51`

### `POS-payments-5.md` — unsupported retry-policy selection

The request and evidence do not select retry eligibility or timeout handling. Nevertheless, the revised requirement commits to retrying only confirmed-retryable failures and reconciling before any retry that could create another capture. That is the substance of its first option, selected without an explicit stakeholder choice.

- Exact excerpt: “Refined requirement: automatically retry only a charge attempt whose failure is confirmed as retryable; preserve the logical charge’s `idempotency_key`; do not treat a pre-webhook status or a provider timeout after possible capture as proof that a new capture is safe; reconcile the original outcome before any retry that could create another capture.”
- Source: `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun4-raw/POS-payments-5.md:7`
- Matching pending option: “**Reconcile before retry (recommended):** retry only explicitly retryable failures; reuse the logical charge’s key; use bounded exponential backoff; reconcile provider status/webhook after an ambiguous timeout before any new capture attempt.”
- Source: `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun4-raw/POS-payments-5.md:32`
- Contradicting exact excerpt: “The request supplies the requirement and three facts but does not select a policy, error taxonomy, retry budget, reconciliation source, or terminal status.”
- Source: `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-rerun4-raw/POS-payments-5.md:36`

## Aggregate checks

| Check | Result |
| --- | --- |
| Required API detections (mobile consumer, stored payload, backward compatibility) | 15/15 evidence-tied |
| Required payments detections (idempotency key, user-visible status, duplicate capture) | 15/15 evidence-tied |
| Must-not-do violations (implementation plan or repository modification) | 0/20 |
| One evidence level per `IMP` | 10/10 transcripts |
| Stable `REQ`/`INV`/`IMP`/`AC` IDs and no concrete recorded decision without selection | 8/10 transcripts |
| Unresolved decision has 2–3 options | 10/10 transcripts |
| Unsupported accepted risk or accepted/resolved conflation | 0/10 transcripts |
| Delta has all categories, `new: none`, exhaustive union, and pairwise-disjoint membership | 10/10 transcripts |

Generic pending-decision wording (including the generic `DEC-###` schema name) was not treated as a concrete decision artifact. No transcript creates a numbered decision ID, links an accepted impact to an unrecorded decision, or claims a risk is resolved without evidence. The two failures are instead the materially equivalent error: selecting policy in the refined requirement while asserting the policy remains pending.

## Required correction

For `POS-api-contract-5`, retain only the supplied rename and one-version compatibility constraint in `REQ-001`; move canonical-write, legacy-read, and new-key iOS-decoding statements into the pending options/acceptance targets with an appropriate unknown or inferred basis until selected.

For `POS-payments-5`, retain the duplicate-capture, pre-settlement-status, and idempotency constraints, but phrase retry eligibility and ambiguous-timeout handling solely as the pending decision. Do not commit the revised requirement to reconcile-first or retry-only-confirmed failures before a stakeholder selects that option.
