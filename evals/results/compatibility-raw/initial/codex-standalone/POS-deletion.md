# Account deletion — focused refinement

## Requirement revision

`REQ-001`: Delete the account immediately, subject to the existing invoice-integrity constraint, the finance-retention requirement, and the background cleanup path. The exact deletion semantics remain the pending decision; no implementation change is selected here.

## Current behavior and preserved invariants

- `INV-001` — `invoice.account_id` uses `RESTRICT`; deleting an account referenced by an invoice must not silently break invoice referential integrity. **verified** — user-supplied schema fact.
- `INV-002` — Finance-related records must be retained for 30 days. **verified** — user-supplied `privacy.md` retention requirement.
- `INV-003` — Account cleanup is consumed by a background worker, so cleanup is not presently an exclusively synchronous request-path operation. **verified** — user-supplied worker behavior.

## Impact ledger

| ID | Finding | Level | Evidence | State |
| --- | --- | --- | --- | --- |
| `IMP-001` | Immediate physical account deletion can fail when invoices still reference the account because the foreign key is restrictive. | `verified` | User-supplied `invoice.account_id` `RESTRICT` fact | `blocked` |
| `IMP-002` | Immediate erasure of finance-related data would violate the 30-day retention requirement. | `verified` | User-supplied `privacy.md` 30-day finance-retention fact | `blocked` |
| `IMP-003` | A request that reports deletion immediately may diverge from actual cleanup completion because the existing cleanup consumer is a background worker. | `verified` | User-supplied background-worker fact | `refining` |
| `IMP-004` | The required treatment of invoice-linked records during deletion is unspecified; without it, data and legal behavior cannot be assessed completely. | `unknown` | No selected invoice archival, anonymization, detachment, or retention policy supplied | `blocked` |

## Decision needed

Which externally visible deletion contract should apply?

1. **Immediate logical deletion, delayed physical cleanup (recommended)** — mark the account deleted immediately, keep only the finance-required records/account stub for 30 days, then let the background worker remove eligible data while preserving invoice referential integrity.
2. **30-day deletion completion** — accept the deletion request immediately but define the account as fully deleted only after the retention window and worker cleanup complete.
3. **Immediate hard deletion** — require an explicit invoice-record treatment (such as archival or reassignment) that makes the restrictive foreign key safe before physically deleting the account; this may require a contract/schema change.

No decision has been recorded. Please select one option before deletion semantics or acceptance criteria are finalized.

_Stopped at the focused decision; no implementation plan or edit is proposed._

---

Disable sign-in immediately, retain finance-linked records for the required 30 days, then let the existing background worker complete deletion.

## Recorded decision

`DEC-001`: “Disable sign-in immediately, retain finance-linked records for the required 30 days, then let the existing background worker complete deletion.” This explicit user selection refines `REQ-001` and mitigates the deletion impacts; it does not make retained data resolved.

## Revised requirement and acceptance criteria

`REQ-001` is revised to: disable account sign-in immediately; retain finance-linked records for 30 days; and complete eligible deletion through the existing background worker while preserving invoice referential integrity.

- `AC-001` — Sign-in is disabled immediately after the deletion request. **verified support:** explicit user selection; runtime enforcement remains a validation target.
- `AC-002` — Finance-linked records remain available for the required 30-day retention period and are not deleted earlier. **verified support:** explicit user selection plus supplied `privacy.md` requirement; implementation evidence remains required.
- `AC-003` — The background worker completes deletion of eligible non-retained account data after the retention period. **verified support:** explicit user selection and supplied worker fact; execution evidence remains required.
- `AC-004` — Invoice references remain valid while finance-linked records are retained; no restrictive foreign-key violation occurs. **verified support:** supplied `invoice.account_id` `RESTRICT` fact; runtime/test evidence remains required.

## Whole-set recalculation

| ID | Recalculated state | Rationale |
| --- | --- | --- |
| `IMP-001` | `mitigated` | Retaining invoice-linked finance records preserves the restrictive relationship; physical deletion is delayed and constrained, not eliminated as a concern. |
| `IMP-002` | `resolved` | The selected requirement explicitly retains finance-linked records for the required 30 days, matching the supplied retention policy. |
| `IMP-003` | `resolved` | The selected contract explicitly makes the existing background worker the completion mechanism, removing the prior ambiguity about asynchronous completion. |
| `IMP-004` | `accepted` | `DEC-001` explicitly accepts retention of finance-linked records as the treatment; exact cleanup eligibility details still require evidence. |

## Delta

- `resolved`: `IMP-002`, `IMP-003`
- `mitigated`: `IMP-001`
- `unchanged`: none
- `accepted`: `IMP-004` (via `DEC-001`)
- `deferred`: none
- `blocked`: none
- `new`: none

## Stop check and planning handoff

The deletion contract is refined and the full impact set is classified. Retained finance-linked data is not claimed as resolved; its treatment is accepted under `DEC-001`, while `AC-002` and `AC-004` require implementation evidence. Remaining risk is validation of sign-in disablement timing, retention enforcement, worker completion, and foreign-key safety. This is a report-only handoff; no task breakdown, implementation plan, or edit is created.
