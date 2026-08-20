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
| Raw corpus | Core: 80 transcripts plus six scoring reports under [`with-skill-raw/`](with-skill-raw/). Integration: 49 transcripts plus three scoring reports under [`integration-raw/`](integration-raw/) |

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

## Workflow Integration Evaluation

This evaluation is separate from the 25-case core composition below. It tests mutually exclusive workflow ownership and does not replace or conceal the core corpus's known payment limitation.

### Integration Environment

| Field | Value |
| --- | --- |
| Evaluator model | `gpt-5.6-luna` |
| Client/runtime | Codex subagent fresh context |
| Local CLI version | `codex-cli 0.148.0-alpha.15` |
| Hosted model/runtime version | Unavailable in supplied evidence; not inferred from the local CLI version |
| Contract | `INT-generic`, `INT-superpowers`, `INT-claude-feature-dev`, `INT-spec-kit`, `NEG-brainstorming`, and `NEG-planning` in `evals/cases.json` |
| Initial adapter commit | `b6b95dd` |
| Generic entry-gate fix | `543e288` |

Strict scoring required exact entry/exit boundaries and counted a prohibition only when the response performed it. Generic mode also had to reject approval-only input before emitting a canonical report or any `REQ/INV/IMP/DEC/AC` artifact. An unselected option or a named next workflow explicitly left unstarted was not scored as automatic invocation.

### Integration Progression

| Corpus | Cases/repetitions | Result | Observed behavior |
| --- | --- | --- | --- |
| `baseline` | Four integration cases; one run each without adapter references | **2/4 exact** | Generic missed its concrete inspection entry; Superpowers had an ambiguous planning exit. Exact exits/entries passed for Claude feature-dev and Spec Kit. There were zero hard-prohibition violations. |
| `initial` | Four integration cases plus two negative controls; five runs each | **25/30** | Superpowers, Claude feature-dev, Spec Kit, brainstorming, and planning passed 25/25. Generic entered from approval alone and emitted reports in 5/5 runs. |
| `rerun-1` | Generic plus both negative controls; five runs each after `543e288` | **15/15** | Generic rejected approval-only input in 5/5 without identifiers/reports; both unchanged negative workflows passed 10/10. |

### Final Integration Composition

| Case | Evidence source | Strict result |
| --- | --- | --- |
| `INT-generic` | `rerun-1` | 5/5 |
| `INT-superpowers` | `initial` | 5/5 |
| `INT-claude-feature-dev` | `initial` | 5/5 |
| `INT-spec-kit` | `initial` | 5/5 |
| `NEG-brainstorming` | `rerun-1` | 5/5 |
| `NEG-planning` | `rerun-1` | 5/5 |
| **Total** | Adjudicated final composition | **30/30** |

The final composition has no repeated broad ideation/clarification, implementation tasks in integration reports, multiple-orchestrator activation, automatic next-workflow invocation, or negative-control workflow replacement. The three unchanged formal adapters use their five-run initial evidence because the fix modified only generic entry gating.

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

The 80 core transcripts are byte-preserved from the controller corpus: `initial` (25), `rerun-1` (15), and `rerun-2` through `rerun-5` (10 each). Six scoring reports are under [`with-skill-raw/scoring/`](with-skill-raw/scoring/). The canonical core inventory is the sorted `relative-path SHA-256` manifest of all 86 Markdown evidence files; its SHA-256 is `6fe00ab7e7ea3c9158c987094c77690efe673a692ab73a3945807b6ae7dde842`. [`tests/test_with_skill_evidence.py`](../../tests/test_with_skill_evidence.py) protects the core directory counts, checksum, and limitation statement.

The integration corpus is independently byte-preserved under [`integration-raw/`](integration-raw/): `baseline` (4 transcripts), `initial` (30), `rerun-1` (15), and `scoring` (3 reports). Its sorted `relative-path SHA-256` manifest covers 52 Markdown files and has SHA-256 `9740064ebd3eb60cae7d95917db99195e765dd84c28d600303c1c6cc0ebbf1fc`. [`tests/test_integration_evidence.py`](../../tests/test_integration_evidence.py) protects its counts, byte checksums, report metadata, and final composition.

Full `git diff --check 3e4476d..366508e` reports exactly four intentional EOF blank-line findings in the byte-preserved controller corpus:

- `evals/results/integration-raw/initial/INT-generic-3.md:67`
- `evals/results/integration-raw/initial/INT-generic-4.md:66`
- `evals/results/integration-raw/initial/INT-spec-kit-2.md:75`
- `evals/results/integration-raw/rerun-1/NEG-brainstorming-2.md:67`

The `integration-raw` subtree is excluded solely to preserve the raw evidence bytes and their audited checksums, not to conceal an implementation whitespace defect. The non-raw portion of that diff check passes.

## Conclusion

The skill materially improves evidence discipline, traceability, focused decisions, whole-set deltas, acceptance-vs-resolution separation, payment grounding, and workflow boundaries. Workflow integration passes its adjudicated final composition at 30/30. The separate core evaluation retains one documented stochastic limitation and must not be represented as a clean 25/25 GREEN result.
