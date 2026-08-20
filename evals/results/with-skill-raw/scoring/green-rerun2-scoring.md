# GREEN rerun-2 strict scoring

## Scope and rule set

Scored the ten supplied round-2 transcripts against `evals/cases.json`,
`skills/requirements-impact-refiner/SKILL.md`, and its evidence, taxonomy, and
refinement-loop references. The cases are five `POS-api-contract` and five
`POS-payments` runs. A transcript passes only if it satisfies every requested
condition. In particular, before an explicit stakeholder selection it must use
only **Decision needed** / “the pending decision”; it must not allocate,
mention, link, or forward-reference `DEC-###`.

## Aggregate result

| Metric | Result |
| --- | --- |
| Transcripts scored | 10 |
| Passed | 0 |
| Failed | 10 |
| Common fatal violation | 10/10 mention `DEC-###` without an explicit selection |
| Additional whole-set-delta failures | 2 |
| Additional explicit-confidence ambiguity | 1 |
| `must_not_do` failures (implementation plan / repository modification) | 0 |
| Accepted-without-decision findings | 0 |

All ten satisfy the substantive case detection at a high level: API runs
identify the iOS consumer, persisted cache payload, and compatibility promise;
payments runs identify idempotency, the pre-webhook visible status, and
duplicate-capture risk. They also provide 2–3 options, use stable
`REQ`/`INV`/`IMP`/`AC` IDs, do not fabricate an accepted risk, and include all
delta headings with `new: none`. Those strengths do not cure the fatal
pre-selection `DEC-###` references below.

## Per-transcript scorecards

### POS-api-contract-1 — FAIL

- Must-detect evidence links: **pass** — iOS decoder (`INV-001`/`IMP-001`),
  cached JSON (`INV-002`/`IMP-002`), and one-version deprecation
  (`INV-003`/`IMP-003`) are explicitly evidenced.
- Must-not-do: **pass** — report-only handoff; no repository modification or
  implementation plan.
- Decision / accepted / confidence / IDs: **fail** — no selection is supplied,
  yet the transcript says, “No `DEC-###` is recorded”; this is a forbidden
  pre-selection `DEC-###` mention. Evidence levels and IDs are otherwise
  explicit and appropriate.
- Whole-set delta: **pass** — `IMP-001`–`IMP-004` appear exactly once across
  unchanged/blocked; all categories and `new: none` are present.
- Evidence: `green-rerun2-raw/POS-api-contract-1.md:32` — “No `DEC-###` is
  recorded because the supplied request states the deprecation promise but does
  not select one of these exact transition policies.”

### POS-api-contract-2 — FAIL

- Must-detect evidence links: **pass** — each required API concern is tied to
  the supplied decoder, cache, or changelog fact.
- Must-not-do: **pass**.
- Decision / accepted / confidence / IDs: **fail** — “No `DEC-###` is
  recorded” names the prohibited identifier before selection. Confidence
  classifications and IDs are otherwise explicit.
- Whole-set delta: **pass** — `IMP-001`–`IMP-005` occur once, and all required
  categories including `new: none` are shown.
- Evidence: `green-rerun2-raw/POS-api-contract-2.md:45` — “No `DEC-###` is
  recorded because the supplied facts state the deprecation duration, not the
  selected wire policy.”

### POS-api-contract-3 — FAIL

- Must-detect evidence links: **pass** — mobile consumer, stored payload, and
  compatibility promise are correctly identified and linked.
- Must-not-do: **pass**.
- Decision / accepted / confidence / IDs: **fail** — it says “no `DEC-###` is
  allocated” before a stakeholder choice.
- Whole-set delta: **fail** — `IMP-004` and `IMP-005` appear under both
  `unchanged` and `blocked`; each known impact must appear in exactly one delta
  category.
- Evidence: `green-rerun2-raw/POS-api-contract-3.md:35` — “No stakeholder
  selection is recorded in the supplied request, so no `DEC-###` is allocated
  and no impact is marked `accepted`.” `:49` — “- `unchanged: IMP-001,
  IMP-002, IMP-003, IMP-004, IMP-005`”; `:52` — “- `blocked: IMP-004,
  IMP-005`.”

### POS-api-contract-4 — FAIL

- Must-detect evidence links: **pass** — the three case-required concerns are
  present with evidence links.
- Must-not-do: **pass**.
- Decision / accepted / confidence / IDs: **fail** for two reasons: (1) it
  names “`DEC-###`” without a selection; (2) `IMP-003` has the compound level
  “`verified` for the promise; `unknown` for the exact mechanism,” so one impact
  does not have an unambiguous required evidence classification. The exact
  mechanism should be a separately classified unknown impact, or the finding
  should use one defensible level.
- Whole-set delta: **pass** — `IMP-001`–`IMP-004` each occur once.
- Evidence: `green-rerun2-raw/POS-api-contract-4.md:21` — “`verified` for the
  promise; `unknown` for the exact mechanism”; `:32` — “No decision was
  supplied, so no `DEC-###` is recorded and no impact is marked `accepted`.”

### POS-api-contract-5 — FAIL

- Must-detect evidence links: **pass** — all three API case facts are
  explicitly captured.
- Must-not-do: **pass**.
- Decision / accepted / confidence / IDs: **fail** — “no `DEC-###` is
  recorded” is a forbidden mention before selection. Remaining confidence and
  IDs are explicit; no accepted risk is fabricated.
- Whole-set delta: **pass** — `IMP-001`–`IMP-005` occur exactly once, all
  categories are present, and `new: none` is stated.
- Evidence: `green-rerun2-raw/POS-api-contract-5.md:33` — “No stakeholder
  selection was supplied, so no `DEC-###` is recorded and no impact is marked
  `accepted`.”

### POS-payments-1 — FAIL

- Must-detect evidence links: **pass** — idempotency (`INV-001`/`IMP-002`),
  pre-settlement status (`INV-002`/`IMP-003`), and duplicate capture
  (`IMP-001`) are all evidenced.
- Must-not-do: **pass**.
- Decision / accepted / confidence / IDs: **fail** — “no `DEC-###` is created”
  is forbidden before a stakeholder selection. No accepted risk is fabricated;
  levels and IDs are otherwise explicit.
- Whole-set delta: **fail** — it omits `IMP-001` and `IMP-002` from every delta
  category, then expressly rationalizes that omission. Initial `refining`
  impacts belong under `unchanged`, exactly once.
- Evidence: `green-rerun2-raw/POS-payments-1.md:39` — “No stakeholder
  selection is recorded in the supplied request, so no `DEC-###` is created
  and no impact is marked `accepted`.” `:53` — “- `unchanged: IMP-003,
  IMP-004, IMP-006, IMP-007`”; `:56` — “- `blocked: IMP-005` — retry count,
  backoff, retry window, and operational limits are unspecified.” `:59` —
  “`IMP-001` and `IMP-002` remain `refining` rather than being repeated in a
  second delta category.”

### POS-payments-2 — FAIL

- Must-detect evidence links: **pass** — duplicate charge/idempotency,
  pre-webhook status, and retry risk are explicitly present.
- Must-not-do: **pass**.
- Decision / accepted / confidence / IDs: **fail** — both the decision prose and
  recorded-decision section mention `DEC-###` before selection. Evidence levels
  and IDs are otherwise explicit; no risk is marked accepted.
- Whole-set delta: **pass** — all `IMP-001`–`IMP-008` occur once and all delta
  categories, including `new: none`, appear.
- Evidence: `green-rerun2-raw/POS-payments-2.md:40` — “No `DEC-###` is
  recorded because no stakeholder selection was supplied.” `:44` — “None. The
  request supplies a desired behavior but does not select one of the retry
  policies above, so no `DEC-###` is allocated.”

### POS-payments-3 — FAIL

- Must-detect evidence links: **pass** — the supplied idempotency, rendered
  status, and timeout-after-capture facts support the required detection.
- Must-not-do: **pass**.
- Decision / accepted / confidence / IDs: **fail** — it states that no
  `DEC-###` is created before an explicit selection. Its impacts otherwise have
  explicit confidence and stable IDs, and none is improperly accepted.
- Whole-set delta: **pass** — `IMP-001`–`IMP-006` occur once across unchanged
  and blocked, with all headings and `new: none`.
- Evidence: `green-rerun2-raw/POS-payments-3.md:54-55` — “No stakeholder
  selection was supplied in this request, so no `DEC-###` is created and no
  impact is marked `accepted`.”

### POS-payments-4 — FAIL

- Must-detect evidence links: **pass** — the ledger links `IMP-001` to
  idempotency/duplicate-capture facts and `IMP-002` to the pre-webhook status.
- Must-not-do: **pass**.
- Decision / accepted / confidence / IDs: **fail** — it both says no
  `DEC-###` is created and forward-references recording one “as a new
  `DEC-###`,” despite no selection. No fabricated accepted risk; levels and IDs
  are otherwise explicit.
- Whole-set delta: **pass** — `IMP-001`–`IMP-006` occur exactly once, all
  headings appear, and `new: none` is present.
- Evidence: `green-rerun2-raw/POS-payments-4.md:36` — “No option is recorded
  here because the request supplies no selection. Therefore no `DEC-###` is
  created or referenced.” `:52` — “A selected option must be recorded as a new
  `DEC-###`, then the complete impact set must be recalculated.”

### POS-payments-5 — FAIL

- Must-detect evidence links: **pass** — the idempotency, pre-webhook status,
  and duplicate-capture/timeout concerns are all explicitly evidenced.
- Must-not-do: **pass**.
- Decision / accepted / confidence / IDs: **fail** — it says no `DEC-###` is
  recorded before selection. Confidence and IDs are otherwise explicit; there
  is no fabricated accepted risk.
- Whole-set delta: **pass** — `IMP-001`–`IMP-006` occur exactly once and every
  required category plus `new: none` is supplied.
- Evidence: `green-rerun2-raw/POS-payments-5.md:36` — “No stakeholder
  selection was supplied, so no `DEC-###` is recorded and no impact is marked
  `accepted`.”

## Required correction before a GREEN score

For an unselected decision, say only “**Decision needed:** …” and “the pending
decision”; do not print `DEC-###` at all. Move every initial `detected` or
`refining` impact into `unchanged` exactly once, while blocked impacts appear
only in `blocked`. Split mixed-confidence findings into separately classified
impacts when their verified and unknown assertions cannot share one evidence
level.
