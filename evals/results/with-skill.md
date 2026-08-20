# With-Skill Behavioral Evaluation

## Evaluation Environment

| Field | Value |
| --- | --- |
| Evaluator model | `gpt-5.6-luna` |
| Client/runtime | Codex subagent fresh context |
| Local CLI version | `codex-cli 0.148.0-alpha.15` |
| Hosted model/runtime version | Unavailable in supplied evidence; not inferred from the local CLI version |
| Candidate skill | `skills/requirements-impact-refiner/SKILL.md`, version `0.1.0` |
| Contract | `evals/cases.json` |
| Repetitions | Five per evaluated case/run |
| Raw corpus | 80 tracked transcripts under [`with-skill-raw/`](with-skill-raw/) plus six tracked scoring reports |

## Strict Scoring Method

Use the baseline rule: a required detection is strict only when tied to supplied evidence or explicitly marked `inferred`/`unknown`. In addition, each material impact needs exactly one evidence level; a concrete `DEC-###` needs an explicit selection; accepted and resolved remain distinct; and a delta must contain all categories, `new: none`, and a disjoint, exhaustive partition of known impacts. Negative cases must not activate this skill or replace the active workflow.

## RED versus GREEN

| Dimension | RED baseline | GREEN evidence |
| --- | --- | --- |
| Evidence, IDs, and decisions | Strong substantive findings, but no selected response showed explicit confidence labels, stable IDs, or a complete decision/recalculation loop. | All adjudicated final API/payment runs label impacts, use traceability IDs, and present pending options or recorded choices correctly except for the limitation below. |
| Payments | 8 strict and 7 possible detections; idempotency advice was not grounded in the supplied idempotency-key fact. | Rerun 5 has 15/15 strict required payment detections; the evidence link to `idempotency_key`, pre-settlement status, and post-capture timeout is explicit. |
| Accepted vs. resolved | No selected baseline response demonstrated the distinction. | Final runs preserve the distinction; no unrecorded acceptance or unsupported resolution was adjudicated. |
| Planning boundary | The baseline planning control produced 3/5 replacement-workflow violations. | Rerun 1 planning control exits without skill artifacts in 5/5 runs and permits ordinary active-workflow planning. |

## GREEN Progression

| Corpus | Cases/repetitions | Adjudicated result | Purpose |
| --- | --- | --- | --- |
| `initial` | authorization, API, payments, brainstorming, planning; 25 | Initial GREEN exposed decision, recalculation, and planning-boundary defects. | First with-skill pressure run. |
| `rerun-1` | API, payments, planning; 15 | Planning early exit passed 5/5; API/payment defects remained. | Checked the first boundary repair. |
| `rerun-2` | API, payments; 10 | Literal generic-decision-ID flags were later adjudicated false positives; delta/evidence defects were repaired. | Checked identifier and delta wording. |
| `rerun-3` | API, payments; 10 | 8/10 pass; one synthesized decision and one duplicate delta membership remained. | Checked concrete-ID and disjointness gates. |
| `rerun-4` | API, payments; 10 | 8/10 pass; pre-decision mechanics leaked into requirement revisions. | Checked revision/acceptance-target discipline. |
| `rerun-5` | API, payments; 10 | 9/10 pass. API passed 5/5; payments passed 4/5. | Final allowed evaluation round. |

## Final Composition

| Case | Evidence source | Strict result |
| --- | --- | --- |
| `POS-authorization` | `initial` | 5/5 |
| `POS-api-contract` | `rerun-5` | 5/5 |
| `POS-payments` | `rerun-5` | 4/5 |
| `NEG-brainstorming` | `initial` | 5/5 |
| `NEG-planning` | `rerun-1` | 5/5 |
| **Total** | Adjudicated composition | **24/25** |

## Known limitation

`rerun-5/POS-payments-5.md` is the sole known stochastic failure. Its pre-decision requirement revision silently embeds reconcile-before-retry mechanics while also stating that no retry policy has been selected. The final core checklist addresses this pattern, but the maximum five correction rounds is exhausted, so no additional evaluation was run and this result is not claimed as fully GREEN.

## Evidence Inventory

The 80 transcripts are byte-preserved from the controller corpus: `initial` (25), `rerun-1` (15), and `rerun-2` through `rerun-5` (10 each). Six scoring reports are under [`with-skill-raw/scoring/`](with-skill-raw/scoring/). The canonical inventory is the sorted `relative-path SHA-256` manifest of all 86 Markdown evidence files; its SHA-256 is `6fe00ab7e7ea3c9158c987094c77690efe673a692ab73a3945807b6ae7dde842`. [`tests/test_with_skill_evidence.py`](../../tests/test_with_skill_evidence.py) protects the directory counts, manifest checksum, and final-report limitation statement.

## Conclusion

The skill materially improves evidence discipline, traceability, focused decisions, whole-set deltas, acceptance-vs-resolution separation, payment grounding, and workflow boundaries. It has one documented stochastic limitation and must not be represented as a clean 25/25 GREEN result.
