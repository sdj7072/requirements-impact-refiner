# Requirements Impact Refiner 0.6.2-dev Scorecard

## Verdict

- Overall: **79/100 (C+)**
- Release status: **not verified**
- Raw weighted score before critical-gate cap: **83/100 (B)**
- Evaluation-system quality: **96/100 (A)**

The critical-gate cap applies because 14 of 40 positive runs reported modifying product code during a pre-planning refinement task, three of five generic-PRD runs activated refinement, and seven of fifteen lineage runs failed deterministic revision or Delta checks.

## Sealed evidence

| Measure | Result |
| --- | ---: |
| Selected runtime finals | 85/85 pass |
| Deterministic mechanical scores | 78/85 pass |
| Quote-bound adjudications | 366/400 pass |
| Adjudication coverage | 400/400 |
| Adjudication validation errors | 0 |
| Manifest validation errors | 0 |
| Raw manifest rows | 989 |
| Raw manifest aggregate SHA-256 | `9198c3710b497f1758d1c5d4e295eb1a7cc31a53ec31d8b6fa50ecb0f20bc6a6` |

## Dimension scores

| Dimension | Weight | Score | Grade | Evidence |
| --- | ---: | ---: | --- | --- |
| Impact detection and evidence grounding | 25% | 90 | A- | Positive detection 119/120; lineage detection 54/70. |
| Workflow boundary discipline | 20% | 65 | D | Positive forbidden-workflow checks 66/80; 14 runs modified product code. Negative routing 47/50. |
| Canonical report validity | 15% | 92 | A- | 78/85 deterministic scores passed; all seven failures were lineage cases. |
| Lineage and revision semantics | 20% | 70 | C- | Lineage adjudications 114/130; deterministic lineage results 8/15. |
| Superpowers integration | 10% | 100 | A+ | 20/20 entry, exit, and one-orchestrator judgments passed. |
| Reproducibility and evidence integrity | 10% | 96 | A | Complete raw capture, retained retry, exact quote binding, clean manifest, and unchanged raw aggregate digest. |

## Material failures

1. **Implementation leaked past the planning boundary.** Fourteen positive runs changed product files instead of stopping after the impact report.
2. **Generic PRD routing over-triggered.** `NEG-generic-prd` activated the impact scan in repetitions 1, 4, and 5.
3. **Lineage publication was unreliable.** Four runs retained only revision 1; three additional reopened cases omitted the required `reopened` Delta transition.
4. **One impact was missed.** `POS-authorization/02` did not identify invitation/default-member scope.

## Priority improvements

- P0: Enforce a hard stop after canonical impact-report delivery; prohibit product-code edits in the same refinement turn.
- P0: Make generic PRD/ideation classification fail closed before `rir_previous` or `rir_scan`.
- P0: Require a two-turn lineage case to publish revision 2 or return an explicit blocked result; never silently retain revision 1.
- P1: Validate required `unchanged`, `reopened`, and rejected Delta transitions before final delivery.
- P1: Add behavioral canaries for “report only, no implementation” across every positive case family.
- P2: Keep the corrected evaluator behavior that records missing lineage revisions as scoreable failures instead of suppressing the batch report.

