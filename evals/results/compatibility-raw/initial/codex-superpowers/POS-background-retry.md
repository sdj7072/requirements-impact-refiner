# Requirements impact refinement — retry failed exports forever

## Initial requirement and preserved behavior

`REQ-001`: Retry failed export jobs forever while preserving deterministic object-key behavior and the existing operational meaning of `dead_letter` alerts. The initial request did not define retryability, pacing, quarantine, or how the five-attempt terminal signal changes.

| ID | Preserved invariant | Evidence | Level |
|---|---|---|---|
| `INV-001` | Export object keys are deterministic for a given export. | Supplied repository fact: exports use a deterministic object key. | `verified` |
| `INV-002` | Export retries currently stop after five attempts. | Supplied repository fact: retries stop after five attempts. | `verified` |
| `INV-003` | Alerts consume `dead_letter` events. | Supplied repository fact: alerts consume `dead_letter` events. | `verified` |

## Initial impact ledger

| ID | Category | Finding | Level | State | Evidence |
|---|---|---|---|---|---|
| `IMP-001` | State / Operations | Replacing the five-attempt limit with forever retries removes the terminal boundary; without defined retryability and pacing, persistent failures can create unbounded work and provider/storage load. | `verified` | `refining` | `INV-002` plus the supplied “forever” request; no failure classification or backoff supplied. |
| `IMP-002` | Data / Compatibility | Deterministic keys target the same logical export object, but write atomicity, overwrite/conditional semantics, and partial-output visibility are unknown; forever retries could overwrite or expose incomplete output. | `inferred` | `refining` | `INV-001`; object-write semantics unavailable. |
| `IMP-003` | Operations / Regression | If jobs no longer become terminal after five attempts, the existing `dead_letter` event may stop being emitted, causing alert consumers to lose notification of permanently unhealthy exports. | `verified` | `refining` | `INV-002` and `INV-003`; event threshold and alert recovery semantics otherwise unavailable. |
| `IMP-004` | State / Operations | Non-retryable errors, poison payloads, and operational safeguards may need termination or quarantine; data-loss, backlog, and operator behavior are unspecified. | `unknown` | `blocked` | No retryability taxonomy, quarantine rule, or override policy supplied. |
| `IMP-005` | Operations | Queue/worker capacity, retry scheduling, and observability for an unbounded retry population are unavailable, so saturation and fairness cannot be assessed. | `unknown` | `blocked` | No queue limits, backoff configuration, metrics, or runbook supplied. |

## Decision needed — `NEEDS_DECISION`

How should “retry forever” interact with persistent failures and the current `dead_letter` alert contract?

1. Forever for classified retryable failures with periodic health signaling: retry transient failures with bounded backoff/jitter without a fixed attempt cap; preserve a periodic alert/health signal; quarantine non-retryable failures.
2. Literal forever for every failure: retry every failure indefinitely and replace or continuously emit `dead_letter` notifications so alert consumers retain an operational signal.
3. Forever with an operational circuit breaker: retry transient failures indefinitely in principle, but allow a circuit breaker or quarantine action to pause unhealthy jobs while preserving `dead_letter` alerts and operator recovery.

No decision was recorded at this stage. The five-attempt limit and `dead_letter` consumer are constraints, not a policy selection.

## Explicit stakeholder revision

> Replace forever with a 20-attempt ceiling and backoff, retain the deterministic object key, and publish the existing `dead_letter` event after the ceiling.

## Refined requirement

`REQ-001` is refined to: Retry failed export jobs for at most 20 attempts using backoff, retain the deterministic object key for each export, and publish the existing `dead_letter` event after the 20th failed attempt. Failure classification and operational capacity validation remain open where not specified.

## Recorded decision

`DEC-001`: The stakeholder selected a 20-attempt ceiling with backoff, retained the deterministic object key, and required publication of the existing `dead_letter` event after the ceiling.

## Whole-set recalculation

| ID | Recalculated impact | Level | State | Evidence | Links |
|---|---|---|---|---|---|
| `IMP-001` | The selected 20-attempt ceiling and backoff remove the unbounded retry loop and replace the prior five-attempt limit. | `verified` | `resolved` | Explicit `DEC-001` plus `INV-002`. | `affects` `REQ-001`, `INV-002`; `resolved by` `DEC-001`; `produces` `AC-001` |
| `IMP-002` | The deterministic object key is retained, but atomicity, overwrite safety, and partial-output behavior remain unverified. | `inferred` | `unchanged` | `DEC-001` retains `INV-001`; object-write semantics were not supplied. | `affects` `REQ-001`, `INV-001`; `produces` `AC-002` |
| `IMP-003` | The existing `dead_letter` event is explicitly published after the 20th failed attempt, preserving the alert-consumer path for jobs reaching the ceiling. | `verified` | `resolved` | Explicit `DEC-001` plus `INV-003`. | `affects` `REQ-001`, `INV-002`, `INV-003`; `resolved by` `DEC-001`; `produces` `AC-003` |
| `IMP-004` | Retryability for non-retryable errors, poison payloads, and operator overrides remains unspecified despite the bounded attempt count. | `unknown` | `blocked` | `DEC-001` specifies ceiling/backoff but no failure taxonomy or quarantine rule. | `affects` `REQ-001`; `produces` `AC-004` |
| `IMP-005` | A finite ceiling and backoff reduce sustained retry pressure, but capacity, fairness, metrics, and recovery behavior remain unverified. | `unknown` | `mitigated` | `DEC-001` bounds attempts and adds backoff; no operational evidence supplied. | `affects` `REQ-001`; `mitigated by` `DEC-001`; `produces` `AC-005` |
| `IMP-006` | Moving `dead_letter` from five attempts to 20 delays the alert and may change operator response timing. | `inferred` | `refining` | Difference between `INV-002` and the explicit 20-attempt threshold in `DEC-001`; alert SLO unavailable. | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-006` |

## Delta

- `resolved`: `IMP-001`, `IMP-003`
- `mitigated`: `IMP-005`
- `unchanged`: `IMP-002`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`
- `new`: `IMP-006`

The categories are disjoint and exhaustive across `IMP-001` through `IMP-006`; every known impact appears exactly once.

## Acceptance and regression criteria

| ID | Future criterion | Evidence / gap |
|---|---|---|
| `AC-001` | An export makes no more than 20 attempts, applies backoff, and stops retrying after the ceiling. | Produced by resolved `IMP-001`; exact backoff parameters remain unspecified. |
| `AC-002` | Every attempt for one export retains its deterministic object key and cannot expose partial or unintended output. | Produced by unchanged `IMP-002`; atomicity and visibility evidence unavailable. |
| `AC-003` | The existing `dead_letter` event is published after the 20th failed attempt and remains consumable by the existing alert path. | Produced by resolved `IMP-003`; implementation evidence not supplied. |
| `AC-004` | Non-retryable or poison failures follow an explicit bounded terminal, quarantine, or operator-override path. | Produced by blocked `IMP-004`; failure taxonomy unspecified. |
| `AC-005` | Queue capacity, fairness, retry metrics, and recovery behavior remain observable and acceptable under bounded retries. | Produced by mitigated `IMP-005`; operational limits unavailable. |
| `AC-006` | The 20-attempt delay before `dead_letter` meets the alerting and response-time expectation for persistently failing exports. | Produced by new `IMP-006`; alert SLO and operator timing unspecified. |

## Stop check and planning handoff

`DEC-001` is recorded and the complete impact set has been recalculated. `IMP-001` and `IMP-003` are resolved; `IMP-005` is mitigated; `IMP-002` is unchanged; `IMP-004` is blocked; and new `IMP-006` requires alert-latency validation. The report is ready for the Superpowers planning workflow. No implementation tasks, work breakdown, or implementation plan is included.
