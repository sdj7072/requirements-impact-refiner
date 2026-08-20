# Requirements impact refinement — retry failed export jobs forever

## Requirement revision

`REQ-001`: Retry failed export jobs forever, while preserving deterministic object-key behavior and the existing operational meaning of `dead_letter` alerts. The supplied request does not yet define whether every failure remains retryable, how repeated attempts are paced, or what happens to the current dead-letter event after the retry policy changes.

This refines the supplied request, “Retry failed export jobs forever.” No retry, terminal-failure, or alerting policy is selected here.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Relationship |
|---|---|---|---|---|
| `INV-001` | Export object keys are deterministic for a given export. | `verified` | Supplied repository fact: “exports deterministic object key.” | `must-preserve` `REQ-001` |
| `INV-002` | Export retries currently stop after five attempts. | `verified` | Supplied repository fact: “retries stop after five.” | `must-preserve` `REQ-001` |
| `INV-003` | Alerts consume `dead_letter` events. | `verified` | Supplied repository fact: “alerts consume dead_letter events.” | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | State | Evidence | Links |
|---|---|---|---|---|---|
| `IMP-001` | Replacing the five-attempt limit with forever retries removes the current terminal boundary; without a defined retryability and pacing policy, a persistent failure can generate unbounded work and provider/storage load. | `verified` | `refining` | `INV-002` plus the supplied “forever” request; no failure classification or backoff is supplied. | `affects` `REQ-001`, `INV-002`; `produces` `AC-001` |
| `IMP-002` | Deterministic object keys make repeated attempts address the same logical export object, but the supplied facts do not establish whether writes are overwrite-safe, conditional, or partially visible; forever retries could therefore repeatedly overwrite or expose incomplete output. | `inferred` | `refining` | `INV-001`; object-write atomicity, versioning, and partial-output behavior are unavailable. | `affects` `REQ-001`, `INV-001`; `produces` `AC-002` |
| `IMP-003` | If jobs no longer become terminal after five attempts, the existing `dead_letter` event may stop being emitted, so alert consumers could lose notification of exports that remain permanently unhealthy. | `verified` | `refining` | `INV-002` and `INV-003`; current event emission threshold and alert recovery semantics are not otherwise supplied. | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | The request does not specify whether non-retryable errors, poison payloads, or exhausted operational safeguards may still terminate or quarantine a job; this leaves data-loss, backlog, and operator-intervention behavior unknown. | `unknown` | `blocked` | No retryability taxonomy, quarantine rule, or override policy supplied. | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | The queue/worker capacity, retry scheduling, and observability behavior for an unbounded retry population are unavailable, so system-wide saturation and fairness cannot be assessed. | `unknown` | `blocked` | No queue limits, backoff configuration, metrics, or runbook supplied. | `affects` `REQ-001`; `produces` `AC-005` |

## One focused decision

How should “retry forever” interact with persistent failures and the current `dead_letter` alert contract?

1. **Forever for retryable failures with periodic health signaling (recommended):** retry only classified transient failures with bounded backoff/jitter, keep retrying without a fixed attempt cap, and preserve an observable periodic alert/health signal for jobs that remain unhealthy; non-retryable failures remain quarantinable.
2. **Literal forever for every failure:** retry every failed attempt indefinitely and replace or continuously emit `dead_letter` notifications so alert consumers still receive an operational signal. This maximizes eventual retry but risks poison-job amplification and alert storms.
3. **Forever with an operational circuit breaker:** retry transient failures indefinitely in principle, but allow a queue/worker circuit breaker or quarantine action to pause unhealthy jobs while preserving `dead_letter` alerts and operator recovery. This adds an explicit exception to the literal requirement.

**NEEDS_DECISION** — no option is selected. Please choose one policy or specify another, including: which failures are retryable, how repeated retries are paced or paused, and whether/how `dead_letter` alerts continue when there is no terminal attempt.

## Whole-set recalculation (decision pending)

| ID | Result | Reason |
|---|---|---|
| `IMP-001` | `refining` | The forever requirement removes the five-attempt boundary, but retryability and pacing remain unselected. |
| `IMP-002` | `refining` | Deterministic-key safety depends on the unspecified write/partial-output contract. |
| `IMP-003` | `refining` | The alert path must be reconciled with the absence or redesign of a terminal event. |
| `IMP-004` | `blocked` | Failure classes and quarantine/override behavior are unspecified. |
| `IMP-005` | `blocked` | Capacity, scheduling, and observability evidence are unavailable. |

Delta: `resolved` — none; `mitigated` — none; `unchanged` — `IMP-001`, `IMP-002`, `IMP-003`; `accepted` — none; `deferred` — none; `blocked` — `IMP-004`, `IMP-005`; `new` — none.

## Acceptance and regression criteria

| ID | Criterion | Evidence / gap |
|---|---|---|
| `AC-001` | The selected retry policy defines retryable failures, pacing/backoff, and behavior for a persistently failing export without relying on an unbounded hot loop. | Produced by `IMP-001`; policy pending. |
| `AC-002` | Repeated attempts for one export use its deterministic object key without exposing partial or unintended output. | Produced by `IMP-002`; object-write semantics are not supplied. |
| `AC-003` | Operators continue to receive a defined alert/health signal for an unhealthy export even when the selected policy has no fifth-attempt terminal transition. | Produced by `IMP-003`; event semantics are pending. |
| `AC-004` | Non-retryable or poison failures follow an explicit quarantine, terminal, or override path. | Produced by blocked `IMP-004`; failure taxonomy is unspecified. |
| `AC-005` | Queue capacity, retry scheduling, fairness, metrics, and recovery behavior remain bounded and observable under persistent failures. | Produced by blocked `IMP-005`; operational evidence is unavailable. |

## Stop check and planning handoff

Stopped at the pending retry/dead-letter policy decision. No concrete `DEC-###` is recorded, and no implementation tasks, work breakdown, plan, or repository edit is included.

--- USER REVISION ---

Replace forever with a 20-attempt ceiling and backoff, retain the deterministic object key, and publish the existing `dead_letter` event after the ceiling.

# Second response — recalculation after `DEC-001`

## Requirement revision

`REQ-001` is refined to: Retry failed export jobs for at most 20 attempts using backoff, retain the deterministic object key for each export, and publish the existing `dead_letter` event after the 20th failed attempt. The policy replaces the prior request for unbounded retries; failure classification and operational capacity validation remain open where not specified.

## Recorded decision

`DEC-001`: The stakeholder selected: “Replace forever with a 20-attempt ceiling and backoff, retain the deterministic object key, and publish the existing dead_letter event after the ceiling.”

## Whole-set recalculation

| ID | Recalculated impact | Level | State | Evidence | Links |
|---|---|---|---|---|---|
| `IMP-001` | The selected 20-attempt ceiling and backoff remove the unbounded retry loop and explicitly replace the prior five-attempt limit. | `verified` | `resolved` | Explicit `DEC-001` ceiling/backoff selection plus `INV-002`. | `affects` `REQ-001`, `INV-002`; `resolved by` `DEC-001`; `produces` `AC-001` |
| `IMP-002` | The deterministic object key is retained, but whether repeated writes are atomic, overwrite-safe, conditional, or capable of exposing partial output remains unverified. | `inferred` | `unchanged` | `DEC-001` retains `INV-001`; object-write semantics were not supplied. | `affects` `REQ-001`, `INV-001`; `produces` `AC-002` |
| `IMP-003` | The existing `dead_letter` event is explicitly published after the 20th failed attempt, preserving the alert-consumer path for jobs that reach the ceiling. | `verified` | `resolved` | Explicit `DEC-001` event selection plus `INV-003`. | `affects` `REQ-001`, `INV-002`, `INV-003`; `resolved by` `DEC-001`; `produces` `AC-003` |
| `IMP-004` | Retryability for non-retryable errors, poison payloads, and operator overrides remains unspecified even though the total attempt count is bounded. | `unknown` | `blocked` | `DEC-001` specifies ceiling/backoff but no failure taxonomy or quarantine rule. | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | A finite 20-attempt ceiling and backoff reduce sustained retry pressure, but queue capacity, fairness, metrics, and recovery behavior are still unverified. | `unknown` | `mitigated` | `DEC-001` bounds attempts and adds backoff; no capacity or observability evidence was supplied. | `affects` `REQ-001`; `mitigated by` `DEC-001`; `produces` `AC-005` |
| `IMP-006` | Moving the dead-letter transition from five attempts to 20 delays the alert for a persistently failing export and may change operator response timing. | `inferred` | `refining` | Difference between `INV-002` and the explicit 20-attempt event threshold in `DEC-001`; alert latency/SLO is not supplied. | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-006` |

## Delta

- `resolved`: `IMP-001`, `IMP-003`
- `mitigated`: `IMP-005`
- `unchanged`: `IMP-002`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`
- `new`: `IMP-006`

The categories are disjoint and exhaustive across `IMP-001` through `IMP-006`; no impact is listed in more than one category.

## Acceptance criteria targets

| ID | Future criterion | Evidence / gap |
|---|---|---|
| `AC-001` | An export makes no more than 20 attempts, applies the selected backoff between retries, and stops retrying after the ceiling. | Produced by resolved `IMP-001`; exact backoff parameters remain to be specified. |
| `AC-002` | Every attempt for one export retains its deterministic object key and cannot expose partial or unintended output. | Produced by unchanged `IMP-002`; object-write atomicity and visibility are unavailable. |
| `AC-003` | The existing `dead_letter` event is published exactly after the 20th failed attempt and remains consumable by the existing alert path. | Produced by resolved `IMP-003`; event emission implementation is not supplied. |
| `AC-004` | Non-retryable or poison failures follow an explicit bounded terminal, quarantine, or operator-override path. | Produced by blocked `IMP-004`; failure taxonomy is unspecified. |
| `AC-005` | Queue capacity, fairness, retry metrics, and recovery behavior remain observable and acceptable under the bounded retry population. | Produced by mitigated `IMP-005`; operational limits and evidence are unavailable. |
| `AC-006` | The 20-attempt delay before `dead_letter` is documented and meets the alerting/response-time expectation for persistently failing exports. | Produced by new `IMP-006`; alert SLO and operator timing are unspecified. |

## Stop check and planning handoff

The explicit 20-attempt ceiling, backoff, deterministic-key retention, and post-ceiling `dead_letter` event are recorded as `DEC-001`, and the complete impact set has been recalculated. `IMP-001` and `IMP-003` are resolved; `IMP-005` is mitigated; `IMP-002` is unchanged; `IMP-004` is blocked pending failure taxonomy; and new `IMP-006` requires alert-latency validation. The report is ready for the selected planning workflow. No implementation tasks, work breakdown, implementation plan, or repository edit is included.
