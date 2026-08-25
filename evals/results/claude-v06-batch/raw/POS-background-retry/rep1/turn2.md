Detailed refinement is complete (generic adapter, CLI fallback since the `rir_scan`/`rir_begin` MCP tools were unavailable). Report `RPT-001` revision 1 validated and persisted at `/private/tmp/claude-501/-Users-p042890-workspace-polaris/074a0f85-287f-4435-929b-4948eb69c993/scratchpad/batch-v06/POS-background-retry/rep1/.requirements-impact-refiner/reports/RPT-001/revision-0001.md`. Note: the repository's source files (`workers/export.py`, `alerts/dead_letter.py`) were removed from disk between turns, so the analysis carries the supplied repository evidence (plus my earlier in-session reads) as the evidence base, as the skill's empty-workspace rule allows; graph tracing found nodes but zero paths (external providers missing), which is disclosed throughout.

The complete impact report, inline:

---

# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | export.jobs retry policy: the five-attempt cap is removed so failed export jobs retry forever and never dead-letter. | Dead-letter alerting for export.jobs is silently starved: alerts/dead_letter.py will never receive a dead_letter event for export.jobs again, so a permanently failing export (bad credentials, malformed payload, poison job) produces no alert and no human ever learns the export is stuck. | Operators relying on dead-letter alerts to detect stuck exports, and end users waiting on exports that never complete; alerts/dead_letter.py's export.jobs reference becomes dead code. | Any export.jobs job whose failure cause is permanent (non-transient), once the attempt cap is removed. | high | Requires the pending decision (question below): either replace the dead-letter signal with a threshold alert on attempt count/job age fed to the existing alerting pipeline, emit a non-terminal warning event at the old five-attempt threshold while continuing to retry, or explicitly accept silent infinite retry and retire the export.jobs reference in alerts/dead_letter.py. | blocked |
| `IMP-002` | export.jobs failure handling: jobs are re-enqueued indefinitely instead of being dropped after five attempts. | A permanently failing job becomes a poison pill that retries forever: without exponential backoff with a cap and jitter it can hot-loop, waste worker capacity, delay healthy export jobs, and grow the retry queue without bound as more permanent failures accumulate. | Worker throughput and latency for all export.jobs traffic, queue/broker storage, and downstream systems hit by each retried attempt. | Accumulation of jobs with non-transient failure causes under the new never-drop policy, especially during an extended dependency outage. | high | Pace infinite retries with capped exponential backoff plus jitter (e.g. cap at minutes-to-hours per attempt) and keep per-job retry state; the deterministic object key (INV-001) already makes arbitrarily many attempts safe on the storage side. Owner: implementer of the workers/export.py change. | refining |
| `IMP-003` | The dead_letter event contract for export.jobs: the producer side is removed while the consumer reference remains. | alerts/dead_letter.py retains a stale export.jobs reference, misleading future maintainers into believing dead-letter coverage for exports still exists, and any dashboards or runbooks keyed to export.jobs dead-letter alerts silently go dark. | Maintainers of alerts/dead_letter.py and operators using export dead-letter runbooks or dashboards. | The first incident after this change in which someone consults dead-letter alerting to diagnose a stuck export. | low | Whichever decision option is selected, update or remove the export.jobs reference in alerts/dead_letter.py in the same change and note the new (or removed) signal in the alert's runbook. Owner: implementer; evidence gap: other dead_letter consumers are unverified (frontier). | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Retry failures of export.jobs forever. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Failures of the export.jobs worker are retried indefinitely: the five-attempt cap (MAX_ATTEMPTS = 5 in workers/export.py) is removed and no attempt count ever abandons a job. Retries remain idempotent because export.jobs output is written to a deterministic object key, so repeated attempts overwrite the same object. Because export.jobs will consequently never emit dead_letter events, the change must also resolve how permanently failing export jobs stay operationally visible (alerts/dead_letter.py currently consumes dead_letter events and references export.jobs), and unbounded retries must be paced (backoff/jitter) so a permanently failing job cannot hot-loop or monopolize worker capacity. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | export.jobs output is written to a deterministic object key, so any retry of the same job overwrites the same object rather than duplicating output; retries are idempotent at the storage layer. | inferred | Supplied repository evidence: 'workers/export.py writes export.jobs output to a deterministic object key' (OBJECT_KEY = "deterministic" observed in workers/export.py earlier this session; workspace is currently empty, so this is carried as supplied evidence). |
| `INV-002` | The dead-letter alerting pipeline (alerts/dead_letter.py, CONSUMES = "dead_letter") continues to consume dead_letter events for any producer other than export.jobs; this change must not break dead-letter handling for other jobs. | inferred | Supplied repository evidence: 'alerts/dead_letter.py consumes dead_letter events' (JOB_REF = "export.jobs" observed in alerts/dead_letter.py earlier this session; workspace is currently empty, so this is carried as supplied evidence). |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-002` | Supplied repository evidence: workers/export.py deterministic object key. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-003` | Supplied repository evidence: alerts/dead_letter.py consumes dead_letter events (JOB_REF = "export.jobs"). |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | operations | high | blocked | unknown | workers/export.py currently stops retries after five attempts (MAX_ATTEMPTS = 5), which is the point at which a job dead-letters; alerts/dead_letter.py consumes dead_letter events and references export.jobs (JOB_REF). Removing the cap means export.jobs never reaches the dead-letter path. | `INV-002` | `AC-002` |
| `IMP-002` | `REQ-001` | state/concurrency | high | refining | unknown | The request mandates retrying forever; the current implementation bounds work per failing job at five attempts. Supplied evidence gives no backoff/pacing mechanism in workers/export.py, so an unbounded retry loop has no stated ceiling on retry rate or concurrent poison jobs. | `INV-001` | `AC-001` |
| `IMP-003` | `REQ-001` | regression | low | blocked | unknown | alerts/dead_letter.py carries JOB_REF = "export.jobs"; once export.jobs can no longer dead-letter, that reference describes an event that can never occur. | `INV-002` | `AC-002` |

## Decision Needed

**Question: With retries unbounded, export.jobs will never emit dead_letter events again. How should permanent-failure visibility for export.jobs be preserved?**

| Option | Impact IDs | Trade-off |
| --- | --- | --- |
| Threshold alert: keep retrying forever, and emit an operational alert (via the existing alerting pipeline) when a job's attempt count or age crosses a threshold (e.g. the old five-attempt mark or a wall-clock age), updating alerts/dead_letter.py or a sibling consumer to handle the new signal. | `IMP-001`, `IMP-003` | Preserves operator visibility of stuck exports with modest new plumbing (a non-terminal warning event and consumer update); the alert can fire repeatedly for long-stuck jobs unless deduplicated. |
| Accept silent infinite retry: remove the export.jobs reference from alerts/dead_letter.py and rely on the deterministic-object-key idempotency plus eventual success; no failure alerting for exports. | `IMP-001`, `IMP-003` | Simplest change with no new alert plumbing, but permanently failing exports become invisible until users notice missing output; only defensible if all export failures are known to be transient. |
| Warn-then-continue: at the old MAX_ATTEMPTS threshold, emit the existing dead_letter event as a non-terminal warning (job keeps retrying), so alerts/dead_letter.py fires unchanged while the job is never dropped. | `IMP-001`, `IMP-003` | Zero consumer-side changes and visibility preserved, but it redefines dead_letter semantics from 'terminally failed' to 'still retrying', which may mislead other dead_letter consumers (unknown frontier) and runbooks. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| new | `IMP-001`, `IMP-002`, `IMP-003` |
| resolved / mitigated / unchanged / accepted / deferred / blocked / superseded / reopened | none |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-002` | `INV-001` | A job that fails continuously is still being retried well past five attempts (e.g. attempt 100) and is never dropped or dead-lettered; retry intervals follow capped exponential backoff with jitter so steady-state retry rate per stuck job is bounded, and each successful late attempt writes to the same deterministic object key producing exactly one output object. | Target criterion; current evidence: workers/export.py stops retries after five attempts (MAX_ATTEMPTS = 5) and writes to a deterministic object key (supplied repository evidence). |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-002` | After the change, a permanently failing export.jobs job surfaces to operators through the mechanism chosen in the pending decision (threshold alert, warn-then-continue dead_letter warning, or a documented explicit acceptance of no alert), and dead_letter handling for all non-export.jobs producers is unchanged; alerts/dead_letter.py contains no stale export.jobs reference describing an event that can no longer occur. | Target criterion pending decision; current evidence: alerts/dead_letter.py consumes dead_letter events and references export.jobs (supplied repository evidence). |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | Resolution requires the user's choice among the three mutually exclusive visibility options in Decision Needed; no decision has been supplied or selected yet, so no decision ID exists. | none | user (product/operations owner of export alerting) |
| `IMP-003` | blocked | The disposition of the export.jobs reference in alerts/dead_letter.py (update, retire, or keep with new warning semantics) follows directly from the same pending visibility decision; additionally, other consumers of dead_letter events are an unknown graph frontier (FRONTIER-001) with providers unavailable. | none | user decision plus implementer verification of other dead_letter consumers |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| workers/export.py — export.jobs retry loop: remove the MAX_ATTEMPTS = 5 cap, add retry pacing (backoff/jitter), preserve the deterministic object key write. | Supplied repository evidence plus earlier in-session reads (JOB = "export.jobs", OBJECT_KEY = "deterministic", MAX_ATTEMPTS = 5). | High for the seed files; the workspace is currently empty, so contents are carried from earlier in-session reads plus supplied evidence rather than a live re-read. |
| alerts/dead_letter.py — dead_letter consumer whose export.jobs reference (JOB_REF) is affected; disposition depends on the pending decision. | Supplied repository evidence (CONSUMES = "dead_letter", JOB_REF = "export.jobs" observed earlier this session). | High for this file; low beyond it — graph receipt 3f62a40a518a5de41002a6b5dcf1e6a9 found zero paths (external providers missing, workspace emptied), so any additional dead_letter consumers or export.jobs producers/schedulers are an unknown frontier. |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 0 edges · 1 unknown frontier | provider_limited; receipt 3f62a40a518a5de41002a6b5dcf1e6a9; sha256 fae104ef…aedde; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-003` | `AC-001`, `AC-002` | Not ready |

---

Per the generic adapter's exit rule, impact refinement stops here: the Planning Handoff is "Not ready" until the Decision Needed question is answered (threshold alert vs. accept silent retry vs. warn-then-continue), after which a post-decision revision can record the choice and unblock IMP-001/IMP-003 before any planning or implementation begins. Also worth relaying: the repository under test at `/private/tmp/claude-501/-Users-p042890-workspace-polaris/074a0f85-287f-4435-929b-4948eb69c993/scratchpad/batch-v06/POS-background-retry/rep1` was emptied on disk between turns; if that was not intentional, the source files need restoring before implementation.