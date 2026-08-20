# No-Guidance Behavioral Baseline

## Evaluation Environment

| Field | Value |
| --- | --- |
| Evaluator model | `gpt-5.6-luna` |
| Client/runtime | Codex subagent fresh context |
| Local CLI version | `codex-cli 0.148.0-alpha.15` |
| Hosted model/runtime version | Not available in the supplied evidence; distinct from the local CLI version |
| Candidate skill guidance | None |
| Enabled orchestrator | None recorded; the control used no skill guidance |
| Tool access | Full Codex agent toolset available; the prompt prohibited workspace reads and subagent dispatch, and the designated output-file write was exercised |
| Contract | `evals/cases.json` |
| Raw corpus | 25 tracked responses in [`evals/results/baseline-raw/`](baseline-raw/) |
| Repetitions | Five per selected case |
| Cases | `POS-authorization`, `POS-api-contract`, `POS-payments`, `NEG-brainstorming`, `NEG-planning` |

The local CLI version is recorded separately from the unavailable hosted model/runtime version. The latter is disclosed rather than inferred or treated as passing evidence.

## Scoring Method

Each `must_detect` item counts as a detection only when its output connects the item to supplied repository evidence or explicitly labels it inferred/unknown. A possible detection discusses the item without that required connection. A violation occurs only when the output performs a forbidden neighboring workflow; an implementation recommendation alone is not a repository modification.

## Results

| Case | Detections / possible detections | Forbidden-workflow violations | Variance notes |
| --- | --- | --- | --- |
| `POS-authorization` | 15 / 0 of 15 | 0 | All repetitions explicitly connected owner/admin distinction, invitation scope, and audit behavior to supplied evidence. Detail level varied; all omitted evidence-confidence labels, stable traceability IDs, a user decision loop, whole-set recalculation, and accepted-versus-resolved separation. |
| `POS-api-contract` | 15 / 0 of 15 | 0 | All repetitions explicitly connected the mobile consumer, stored payload, and compatibility promise to supplied evidence. Presentation varied from brief summaries to transition tables; all omitted the five process/traceability capabilities above. |
| `POS-payments` | 8 / 7 of 15 | 0 | Duplicate-capture risk was explicitly evidenced in every repetition. Idempotency was possible, rather than strict, in all five; user-visible status was strict in repetitions 2, 3, and 5 and possible in 1 and 4. |
| `NEG-brainstorming` | n/a | 0 of 5 | Every repetition stayed in ordinary product brainstorming and did not invent repository evidence. Breadth and MVP specificity varied. |
| `NEG-planning` | n/a | 3 of 5 | No response repeated impact refinement. Repetitions 1, 3, and 4 replaced the planning workflow by authoring a plan or an in-band planning procedure; repetitions 2 and 5 declined safely without the approved specification. |

## Representative Verbatim Evidence

### Correct substantive detection

[`evals/results/baseline-raw/POS-authorization-1.md`](baseline-raw/POS-authorization-1.md) explicitly grounded all three substantive impacts:

> “`authorizeProjectEdit` currently permits only `owner` and `admin` roles”

> “Workspace invitations default to the `member` role”

> “Project edits emit an audit event containing the actor's role.”

[`evals/results/baseline-raw/POS-api-contract-1.md`](baseline-raw/POS-api-contract-1.md) likewise grounded its contract analysis:

> “`ios/UserDTO.swift` currently decodes `displayName`”

> “old cached JSON remains readable”

> “The public changelog must explicitly state that `displayName` is deprecated”

### Payment evidence-discipline failures

The following are possible rather than strict detections because they prescribe the right behavior without connecting it to the supplied evidence that charge requests already accept `idempotency_key`:

> “Generate a stable, unique idempotency key per logical charge attempt and send it on every provider request.” — [`evals/results/baseline-raw/POS-payments-1.md`](baseline-raw/POS-payments-1.md)

> “Every retry must reuse a stable idempotency key for the logical charge (or a provider-supported equivalent).” — [`evals/results/baseline-raw/POS-payments-2.md`](baseline-raw/POS-payments-2.md)

By contrast, duplicate-capture risk was explicitly grounded:

> “Because a provider may time out after capture, do not immediately issue a new charge.” — [`evals/results/baseline-raw/POS-payments-3.md`](baseline-raw/POS-payments-3.md)

The user-visible-status evidence was explicit in some repetitions:

> “the payment status is rendered before webhook settlement.” — [`evals/results/baseline-raw/POS-payments-2.md`](baseline-raw/POS-payments-2.md)

### Planning-boundary violations

The following outputs performed the forbidden replacement planning workflow:

> “# Requirements Impact Refiner Implementation Plan” — [`evals/results/baseline-raw/NEG-planning-1.md`](baseline-raw/NEG-planning-1.md)

> “The implementation plan should then be decomposed into independently testable tasks in this order:” — [`evals/results/baseline-raw/NEG-planning-3.md`](baseline-raw/NEG-planning-3.md)

> “### Task 2: Decompose the requirements into independently testable coding tasks” — [`evals/results/baseline-raw/NEG-planning-4.md`](baseline-raw/NEG-planning-4.md)

## Demonstrated Failures the Skill Must Correct

1. Add explicit evidence-confidence and traceability discipline. Although authorization and API-contract responses detected all substantive case items, no selected response demonstrated explicit evidence-confidence labels or stable output traceability identifiers (except hypothetical identifiers in `NEG-planning-1`, not for the supplied approved report).
2. Establish a user decision loop with a choice, confirmation, and whole-set recalculation; open questions alone did not demonstrate this capability.
3. Separate accepted risks from resolved risks. None of the selected responses showed this distinction.
4. Ground payment idempotency in the supplied repository fact. The payment case achieved 8 strict detections and 7 possible detections, with all five idempotency discussions failing strict evidence connection; this is not a substantive-topic miss.
5. Preserve planning-workflow ownership. The planning negative case had 3 of 5 replacement-workflow violations despite 0 repeat-impact-refinement violations.

The baseline is therefore strong at substantive impact analysis but insufficiently reliable on evidence confidence, traceability, decision/recalculation mechanics, accepted-versus-resolved risk state, payment evidence discipline, and planning-boundary ownership.
