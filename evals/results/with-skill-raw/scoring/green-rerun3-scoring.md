# Green rerun 3 — strict transcript scoring

## Result

**8/10 pass; 2/10 fail.**

Scored against `evals/cases.json` and the current `skills/requirements-impact-refiner/SKILL.md` plus its evidence-model and refinement-loop references. A pass requires all supplied detections, evidence-tied `IMP` entries with exactly one level, no implementation-plan behavior, stable IDs, no pre-selection concrete `DEC` ID or decision-derived acceptance, 2–3 options where a decision is needed, no unsupported acceptance claim, and a complete mutually-exclusive delta including `new: none`.

| Transcript | Case | Result | Strict basis |
| --- | --- | --- | --- |
| `green-rerun3-raw/POS-api-contract-1.md` | POS-api-contract | **FAIL** | Records and uses `DEC-001` despite no stakeholder selection; it treats the one-version changelog constraint as the selection of an exact wire policy. |
| `green-rerun3-raw/POS-api-contract-2.md` | POS-api-contract | **PASS** | Detects iOS consumer, persisted cache, and deprecation compatibility; the pending decision has three options and no concrete `DEC`; complete non-overlapping delta. |
| `green-rerun3-raw/POS-api-contract-3.md` | POS-api-contract | **PASS** | Required detections are separately evidence-tied; three options, no pre-selection `DEC`, no accepted/resolved overclaim, and full delta. |
| `green-rerun3-raw/POS-api-contract-4.md` | POS-api-contract | **PASS** | Required contract, cache, and iOS impacts are evidence-tied; decision remains pending; full mutually-exclusive delta. |
| `green-rerun3-raw/POS-api-contract-5.md` | POS-api-contract | **PASS** | Required detections and unknown gaps are explicit; no concrete decision allocation; all delta categories appear and account for the five `IMP`s once. |
| `green-rerun3-raw/POS-payments-1.md` | POS-payments | **PASS** | Detects key reuse/duplicate-capture, provisional status, and timeout risk with levels; offers three options without a `DEC`; complete delta and report-only handoff. |
| `green-rerun3-raw/POS-payments-2.md` | POS-payments | **PASS** | Required idempotency, status, and duplicate-capture impacts are present and evidence-tied; three choices remain pending; all seven `IMP`s occur once in delta categories. |
| `green-rerun3-raw/POS-payments-3.md` | POS-payments | **FAIL** | The delta places the same impacts in both `unchanged` and `blocked`, so categories are not mutually exclusive and the whole-set recalculation is invalid. |
| `green-rerun3-raw/POS-payments-4.md` | POS-payments | **PASS** | Required risks are recorded with one level each; three alternatives remain pending without `DEC`; delta is exhaustive and mutually exclusive. |
| `green-rerun3-raw/POS-payments-5.md` | POS-payments | **PASS** | Required impacts, unknown operational gap, pending three-way choice, no allocated `DEC`, and exhaustive non-overlapping delta are all present. |

## Fail evidence

### `POS-api-contract-1.md`

`green-rerun3-raw/POS-api-contract-1.md:35` says: “`DEC-001` — The supplied public-changelog constraint selects a one-version compatibility period. Refine `REQ-001` with **dual-read / single-write** …”. No explicit stakeholder selection appears before it; the immediately preceding text only offers options at lines 29–31. This violates the rule that a constraint/invariant is not a selected wire policy and that no concrete `DEC-###` may be allocated, linked, or forward-referenced before selection.

The unsupported decision is then operationally linked throughout the recalculation at `green-rerun3-raw/POS-api-contract-1.md:39-43` and planning handoff at `green-rerun3-raw/POS-api-contract-1.md:61`, which says planning may proceed with the selected “dual-read/single-write compatibility.” This is not remedied by the `accepted: none` delta entry.

### `POS-payments-3.md`

`green-rerun3-raw/POS-payments-3.md:47` lists “`unchanged: IMP-001, IMP-003, IMP-004, IMP-005, IMP-006, IMP-007`”, while `green-rerun3-raw/POS-payments-3.md:50` also lists “`blocked: IMP-002, IMP-005, IMP-006`.” `IMP-005` and `IMP-006` therefore occur twice. The refinement loop requires every known impact exactly once across mutually exclusive delta categories; the correct placement for these currently `blocked` ledger entries is `blocked` only.

## Checks applied to passing transcripts

All eight passing transcripts:

- cover the three required case-specific detections (API: mobile consumer, stored payload, compatibility; payments: idempotency key, user-visible pre-settlement status, duplicate capture);
- provide a single `verified`, `inferred`, or `unknown` level for every `IMP`, with stable `REQ`/`INV`/`IMP`/`AC` references;
- present exactly three decision options and state that the decision is pending, without allocating a concrete `DEC-###` or marking any impact `accepted`;
- have no implementation work breakdown or repository modification; and
- include every delta category, `new: none`, and each known `IMP` in exactly one category.
