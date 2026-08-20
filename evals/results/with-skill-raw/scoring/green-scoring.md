# GREEN evaluation scoring — Requirements Impact Refiner

## Scope and recommendation

- **Evaluator corpus:** all 25 transcripts in `green-raw/`, scored against the 17-case contract in `evals/cases.json` (the GREEN corpus contains five runs for each of `POS-authorization`, `POS-api-contract`, `POS-payments`, `NEG-brainstorming`, and `NEG-planning`).
- **Recommendation: FAIL the skill’s intended contract as a whole.** All 45 required positive detections are explicit and evidence-grounded, and no response modifies a repository. However, four negative-case responses enter/reforge a workflow they must not enter, one positive response is at least plan-like at the handoff boundary, and six positive responses have a nonconforming or unsupported decision loop. The latter matters because the skill explicitly says silence is never acceptance and defines `DEC-###` as a recorded user choice.

## Scoring rules

- A required detection is **D** only if it is explicitly tied to a supplied fact or is explicitly classified `inferred`/`unknown`. **P** is relevant but ambiguous/partially compliant; **M** is absent or noncompliant.
- `Plan` and `Modify` score must-not-do items. `No` means no violation; **P** means a handoff is materially plan-like but not a full implementation plan; `Yes` is a violation.
- `EC` requires explicit confidence labels on material findings. `IDs` requires stable, internally consistent `REQ`/`INV`/`IMP`/`DEC`/`AC` identifiers where applicable. `UDL` requires the ledger before a needed decision, 2–3 concrete options, no invented user choice, and a correctly pending/recorded choice. `WSR` requires complete-set recalculation plus a delta. `A≠R` requires accepted and resolved states to remain distinct, including an actual decision link for acceptance and evidence for resolution.
- `N/A` is compliant only where the supplied request already fixes the policy and the response correctly says no additional decision is needed. It is not used to excuse an invented `DEC-###` for an otherwise unresolved choice.

## Positive runs

Legend: O = owner/admin distinction; I = invitation scope; A = audit behavior; M = mobile consumer; S = stored payload; B = backward compatibility; K = idempotency key; U = user-visible status; C = duplicate capture.

### POS-authorization

| Run | O | I | A | Plan | Modify | EC | IDs | UDL | WSR | A≠R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `POS-authorization-1.md` | D | D | D | No | No | Yes | Yes | N/A | Yes | Yes |
| `POS-authorization-2.md` | D | D | D | No | No | Yes | Yes | Yes | Yes | Yes |
| `POS-authorization-3.md` | D | D | D | No | No | Yes | Yes | Yes | Yes | Yes |
| `POS-authorization-4.md` | D | D | D | No | No | Yes | Yes | N/A | Yes | Yes |
| `POS-authorization-5.md` | D | D | D | No | No | Yes | Yes | N/A | Yes | Yes |

Case result: **15/15 D; 0 P; 0 M; no must-not-do violation.** The N/A loops correctly recognize that “workspace members edit every project” directly selects the authorization scope. Every run states the three supplied facts as verified evidence, including `POS-authorization-1.md`: “`authorizeProjectEdit` currently permits project edits for owner and admin roles,” “Workspace invitations default the invited user to the member role,” and “Project edits emit an audit event containing the actor role.”

### POS-api-contract

| Run | M | S | B | Plan | Modify | EC | IDs | UDL | WSR | A≠R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `POS-api-contract-1.md` | D | D | D | **P** | No | Yes | Yes | Yes | Yes | Yes |
| `POS-api-contract-2.md` | D | D | D | No | No | Yes | Yes | **P** | Yes | Yes |
| `POS-api-contract-3.md` | D | D | D | No | No | Yes | Yes | **M** | Yes | **P** |
| `POS-api-contract-4.md` | D | D | D | No | No | Yes | Yes | **P** | Yes | Yes |
| `POS-api-contract-5.md` | D | D | D | No | No | Yes | Yes | **P** | Yes | Yes |

Case result: **15/15 D; 0 P; 0 M** for required impacts. All runs make the three evidence links explicit. For example, `POS-api-contract-1.md` identifies that “`ios/UserDTO.swift` decodes `displayName`,” that “Cached profile JSON persists `displayName`,” and that the “Public API changelog promises one-version deprecation.”

### POS-payments

| Run | K | U | C | Plan | Modify | EC | IDs | UDL | WSR | A≠R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `POS-payments-1.md` | D | D | D | No | No | Yes | Yes | Yes | Yes | Yes |
| `POS-payments-2.md` | D | D | D | No | No | Yes | Yes | **P** | Yes | Yes |
| `POS-payments-3.md` | D | D | D | No | No | Yes | Yes | Yes | Yes | Yes |
| `POS-payments-4.md` | D | D | D | No | No | Yes | Yes | **P** | Yes | Yes |
| `POS-payments-5.md` | D | D | D | No | No | Yes | Yes | Yes | **P** | Yes |

Case result: **15/15 D; 0 P; 0 M** for required impacts. This corrects the baseline idempotency defect. A representative explicit connection is `POS-payments-1.md`: “Charge requests accept an `idempotency_key`,” “Payment status can be rendered before webhook settlement,” and “The provider may time out after capture”; the duplicate-capture impact then cites “`INV-001`, `INV-003`.”

## Positive-run exceptions and ambiguities

Every item below is a P, M, or violation from the tables above. Excerpts are exact and paths are absolute.

| Run / criterion | Result | Exact excerpt | Transcript path |
| --- | --- | --- | --- |
| API 1 / implementation-plan boundary | P | “Planning handoff summary: - Implement canonical `name` with one-version legacy read compatibility for `displayName`. - Preserve and migrate cached profile JSON from `displayName` to `name` without data loss. - Update the public API contract/changelog and compatibility fixtures.” | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-raw/POS-api-contract-1.md` |
| API 2 / decision loop | P | “`DEC-001`: The supplied changelog promise is recorded as a compatibility constraint… The exact option above is **not selected by the supplied evidence** and remains a planning decision.” | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-raw/POS-api-contract-2.md` |
| API 3 / decision loop | M | “The supplied changelog commitment resolves the key policy choice…” followed by “`DEC-001` — For one public API version, publish/read `name` as the canonical field and retain `displayName` as a deprecated compatibility field.” No 2–3 options are offered, and the supplied changelog only establishes a deprecation window, not this chosen wire/cache policy. | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-raw/POS-api-contract-3.md` |
| API 3 / accepted vs. resolved | P | “`IMP-003` — **accepted**: external consumers may depend on `displayName`; the one-version promise is the explicit acceptance boundary. Linked decision: `DEC-001`.” The response distinguishes words, but this is not a user acceptance; it is an unsupported synthesized decision. | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-raw/POS-api-contract-3.md` |
| API 4 / decision loop | P | “1. `DEC-001` (selected): emit canonical `name` and retain `displayName` as a deprecated alias for one version…” and “`DEC-001` — Select option 1.” The user supplied a rename and a one-version commitment, not the selected dual-key and precedence policy. | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-raw/POS-api-contract-4.md` |
| API 5 / decision loop | P | “`DEC-001` — Apply the published one-version deprecation promise using option 1…” This treats a recommendation about dual-read/dual-write as a recorded choice despite no stakeholder selection. | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-raw/POS-api-contract-5.md` |
| Payments 2 / decision-ID semantics | P | “No user choice is present in the supplied request, so no `DEC-###` can truthfully be recorded.” Then: “`DEC-001`: **pending user decision**…” This is transparent about the pending state, but a `DEC` is defined as a recorded user choice, so the label is ambiguous. | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-raw/POS-payments-2.md` |
| Payments 4 / decision-ID semantics | P | “`DEC-001` — Proposed baseline, pending product/provider confirmation: choose option 1…” It correctly denies acceptance, but calls a recommendation a `DEC` before a user has decided. | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-raw/POS-payments-4.md` |
| Payments 5 / recalculation and delta | P | “No decision has been recorded, so there is no post-decision recalculation. Current complete set remains:” The following bullets classify the set but do not provide the explicit delta required by the loop (including the category-by-category new-impact outcome). | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-raw/POS-payments-5.md` |

Notes on near-misses not counted as failures:

- `POS-payments-1.md`, `POS-payments-3.md`, and `POS-payments-5.md` correctly retain a pending decision instead of fabricating acceptance. The oddity in run 5 is only its incomplete delta.
- All positive reports use the required identifier families and explicit `verified`/`inferred`/`unknown` labels. `POS-authorization-1.md` deliberately has no `DEC` because it explicitly determines no focused choice is needed; that is compliant, not an identifier failure.

## Negative runs

### NEG-brainstorming

| Run | Activate impact refinement | Invent repository evidence |
| --- | --- | --- |
| `NEG-brainstorming-1.md` | No | No |
| `NEG-brainstorming-2.md` | No | No |
| `NEG-brainstorming-3.md` | No | No |
| `NEG-brainstorming-4.md` | No | No |
| `NEG-brainstorming-5.md` | No | No |

Case result: **0/10 must-not-do violations.** The answers remain ordinary ideation. `NEG-brainstorming-2.md` even correctly confines its repository statement: “This is an early ideation request, so there is no existing behavior or repository evidence to preserve yet.”

### NEG-planning

| Run | Repeat impact refinement | Replace planning workflow |
| --- | --- | --- |
| `NEG-planning-1.md` | No | **Yes** |
| `NEG-planning-2.md` | **Yes** | No |
| `NEG-planning-3.md` | No | **Yes** |
| `NEG-planning-4.md` | No | **Yes** |
| `NEG-planning-5.md` | No | No |

Case result: **4 violations across 10 must-not-do checks.** This is a blocking mode-boundary failure: the request says the impact report is already approved and asks to produce coding tasks, but four runs either produce an implementation plan or reopen the refinement workflow.

## Negative-run violations

| Run / prohibited behavior | Exact excerpt | Transcript path |
| --- | --- | --- |
| Planning 1 / replace planning workflow | “# Implementation Plan: Profile Nickname” and “## Work breakdown” | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-raw/NEG-planning-1.md` |
| Planning 2 / repeat impact refinement | “# Requirements-impact handoff”, “## Current behavior and preserved invariants”, and “## Impact ledger”. The answer creates five new `IMP-###` items after saying “the impact review is complete.” | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-raw/NEG-planning-2.md` |
| Planning 3 / replace planning workflow | “# Implementation plan: profile nickname” and “## Plan” | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-raw/NEG-planning-3.md` |
| Planning 4 / replace planning workflow | “# Implementation plan: profile nickname” and “## Implementation steps” | `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/green-raw/NEG-planning-4.md` |

## Aggregate counts

| Measure | Count |
| --- | ---: |
| Positive required detections | 45/45 D |
| Positive required detections scored P | 0 |
| Positive required detections missed | 0 |
| Positive repository modifications | 0/15 |
| Positive implementation-plan violations | 0/15; 1 plan-like P |
| Positive explicit-evidence-confidence passes | 15/15 |
| Positive stable-ID passes | 15/15 |
| Positive decision loop: pass / P / M / compliant N/A | 6 / 5 / 1 / 3 |
| Positive whole-set recalculation/delta: pass / P | 14 / 1 |
| Positive accepted-vs-resolved: pass / P | 14 / 1 |
| Negative brainstorming must-not-do violations | 0/10 |
| Negative planning must-not-do violations | 4/10 |
| Total confirmed must-not-do violations | 4 |
| Total P/M process or boundary findings (including plan-like handoff) | 9 |

## Contract conclusion

The GREEN change materially improves the core analysis behavior: evidence grounding, uncertainty labels, stable traceability, impact ledgers, acceptance criteria, and complete-set thinking are consistently present. That is not enough for a pass against the stated skill contract. The contract’s most important control-flow boundary fails in 4/5 planning-negative runs, while API compatibility runs repeatedly turn an unselected recommendation into `DEC-001` or an accepted risk. The skill should be revised and the full five-run affected cases rerun before it is treated as GREEN:

1. Add an explicit early exit for an approved impact report / request to produce coding tasks: route to the user’s planning workflow and do not restate a ledger or author tasks.
2. State that a `DEC-###` is created only after the user selects an option. Before then use “Decision needed” without a `DEC` ID (or an explicitly non-decision issue ID), preserve the complete set as pending, and do not mark any impact accepted.
3. Make the planning handoff report-only: refined requirement, linked evidence, open risks, and `AC` criteria; remove imperative implementation work breakdowns.
4. Require an explicit delta even when no decision is made: all categories, including `new: none` where applicable.
