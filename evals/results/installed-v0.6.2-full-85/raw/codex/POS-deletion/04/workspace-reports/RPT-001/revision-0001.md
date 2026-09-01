# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Immediate account deletion through account.delete_flow | The delete fails for accounts referenced by invoices, or succeeds only after destructive invoice changes. | Accounts with invoices, callers of the deletion flow, and invoice records. | A deletion request targets an account whose id is present in invoice.account_id. | critical | Select an invoice-linked deletion policy and enforce it transactionally before implementing the flow. | blocked |
| `IMP-002` | Immediate deletion of invoice-linked accounts | Financial records or their required account linkage are removed before the 30-day retention period ends. | Finance records, retention controls, audits, and account owners with invoice history. | The deletion flow purges or cascades invoice-linked data before its retention deadline. | critical | Retain the minimum finance-linked record for 30 days, or obtain an explicit policy change before permitting an earlier purge. | blocked |
| `IMP-003` | Account cleanup orchestration | Immediate deletion can leave stale cleanup events, duplicate destructive work, or bypass the existing worker contract. | The account-cleanup queue, its worker, retries, and operational monitoring. | account.delete_flow deletes data before an account-cleanup event is consumed or without defining event behavior. | high | Define emission, idempotency, and missing-account handling for cleanup events as part of the chosen deletion model. | blocked |
| `IMP-004` | account.delete_flow implementation in db/constraints.py | A local edit cannot provide a reliable deletion flow without a defined database API, transaction boundary, and event publisher. | Deletion callers, persistence behavior, and cleanup processing. | Implementation is attempted from the current constant-only module without selecting the lifecycle semantics and integration contract. | high | Specify the flow contract and verify or add its database and event dependencies before coding. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Delete an account immediately through account.delete_flow in db/constraints.py.<br><br>Repository evidence:<br>- db/constraints.py declares invoice.account_id ON DELETE RESTRICT<br>- policy/retention.py sets FINANCE_RETENTION_DAYS to 30<br>- workers/cleanup.py consumes account-cleanup events | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | account.delete_flow must make the requested account unavailable immediately, while the treatment of invoice-linked account data is explicitly selected so the ON DELETE RESTRICT constraint, the 30-day finance-retention rule, and the account-cleanup event consumer remain coherent. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | An account row referenced by invoice.account_id cannot be hard-deleted while the ON DELETE RESTRICT relationship remains in force. | verified | db/constraints.py declares INVOICE_FK = "invoice.account_id ON DELETE RESTRICT". |
| `INV-002` | Finance data governed by the current policy is retained for 30 days. | verified | policy/retention.py sets FINANCE_RETENTION_DAYS = 30 and references account.delete_flow. |
| `INV-003` | Deferred account cleanup is initiated through account-cleanup events carrying an account_id. | verified | workers/cleanup.py names QUEUE = "account-cleanup" and consume(event) reads event["account_id"]. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-004` | db/constraints.py declares INVOICE_FK = "invoice.account_id ON DELETE RESTRICT". |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-004` | policy/retention.py sets FINANCE_RETENTION_DAYS = 30 and references account.delete_flow. |
| `INV-003` | `REQ-001` | `IMP-003`, `IMP-004` | workers/cleanup.py names QUEUE = "account-cleanup" and consume(event) reads event["account_id"]. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | data | critical | blocked | unknown | The requested hard-delete path conflicts directly with invoice.account_id ON DELETE RESTRICT whenever invoices exist. | `INV-001` | the pending decision | `AC-001`, `AC-002` |
| `IMP-002` | `REQ-001` | legal/policy | critical | blocked | unknown | The repository sets FINANCE_RETENTION_DAYS to 30; immediate purging of invoice-linked data would contradict that current rule. | `INV-002` | the pending decision | `AC-003` |
| `IMP-003` | `REQ-001` | operations | high | blocked | unknown | workers/cleanup.py consumes account-cleanup events, but the supplied code does not establish whether immediate deletion emits, bypasses, or invalidates those events. | `INV-003` | the pending decision | `AC-004` |
| `IMP-004` | `REQ-001` | functionality | high | blocked | unknown | db/constraints.py currently contains only INVOICE_FK and FLOW string declarations; it has no callable account.delete_flow implementation or persistence boundary. | `INV-001`, `INV-002`, `INV-003` | the pending decision | `AC-005`, `AC-001` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| For an account referenced by invoices, what must ‘delete immediately’ mean? | Immediately deactivate and anonymize non-financial account data, retain the minimum invoice-linked record for 30 days, then publish/consume account-cleanup to hard-delete it. | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | Preserves retention and gives an immediate user-facing deletion outcome, but physical account deletion is delayed. |
| For an account referenced by invoices, what must ‘delete immediately’ mean? | Hard-delete immediately only when no invoices reference the account; otherwise reject or schedule deletion after the 30-day retention period. | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | Keeps the current constraint and retention policy, but deletion timing differs by invoice history. |
| For an account referenced by invoices, what must ‘delete immediately’ mean? | Hard-delete every account immediately and also purge or detach its invoices, with an approved change to the 30-day finance-retention policy and database constraint. | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | Meets literal immediate physical deletion but is destructive and requires explicit finance-policy and schema authorization. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | none |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | account.delete_flow must make the requested account unavailable immediately, while the treatment of invoice-linked account data is explicitly selected so the ON DELETE RESTRICT constraint, the 30-day finance-retention rule, and the account-cleanup event consumer remain coherent. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | A deletion request produces the selected immediate outcome for both invoice-free and invoice-linked accounts, with no ambiguous partial state. | Test both account classes and verify the selected hard-delete, deactivation, rejection, or scheduling result. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | No deletion path leaves an orphaned invoice.account_id or fails unexpectedly on the RESTRICT constraint. | Integration tests exercise deletion inside the database transaction with an existing invoice reference. |
| `AC-003` | `REQ-001` | `IMP-002` | `INV-002` | Invoice-linked data remains recoverable/auditable for 30 days unless an explicitly approved policy revision is part of the change. | A retention-boundary test verifies behavior before, at, and after 30 days, or cites the approved replacement policy. |
| `AC-004` | `REQ-001` | `IMP-003` | `INV-003` | The deletion flow and worker define one idempotent outcome for emitted, retried, delayed, and missing-account cleanup events. | Worker tests cover duplicate events and events consumed before and after the selected deletion transition. |
| `AC-005` | `REQ-001` | `IMP-004` | `INV-003` | account.delete_flow has a concrete callable contract, transaction boundary, persistence dependency, and event-publication behavior. | Repository code and tests demonstrate the public input/output contract and rollback behavior when database or event publication fails. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The current foreign key makes unconditional immediate hard deletion impossible for invoice-linked accounts. | none | Product and finance-policy owner |
| `IMP-002` | blocked | The requested timing conflicts with the current 30-day retention rule unless deletion is logical or policy is changed. | none | Finance-policy owner |
| `IMP-003` | blocked | Worker event semantics depend on the selected lifecycle and cannot be inferred from the current consumer stub. | none | Account platform owner |
| `IMP-004` | blocked | The target module has no database or event interfaces from which to implement the flow safely. | none | Account platform owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Account deletion semantics and referential integrity in db/constraints.py | Direct inspection found the RESTRICT declaration and flow identifier but no implementation. | High for current file content; database runtime and callers are not present in the supplied repository. |
| Thirty-day finance retention in policy/retention.py | Direct inspection confirmed FINANCE_RETENTION_DAYS = 30. | High for the repository rule; external legal or policy approvals are unknown. |
| account-cleanup consumption in workers/cleanup.py | Direct inspection confirmed the queue name and account_id extraction. | Medium because publishing, retries, scheduling, and actual cleanup side effects are absent. |
| Transitive impact graph coverage | PATH-001 covers the cleanup worker and PATH-002 covers retention; FRONTIER-001 records that ast-grep, codegraph, and scip providers were unavailable and the built-in fallback was used. | Medium; graph links are lexical/structural-inferred and runtime dependencies remain unknown. |
| Graph paths for IMP-001 | This is direct evidence in the requested source file, so no transitive graph path is needed. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-002 | PATH-002: account.delete_flow → account.delete_flow | PATH-002: provider builtin; confidence lexical; location db/constraints.py + policy/retention.py |
| Graph paths for IMP-003 | PATH-001: account.delete_flow → account.delete_flow | PATH-001: provider builtin; confidence lexical; location db/constraints.py + workers/cleanup.py |
| Graph paths for IMP-004 | This is direct inspection of the requested implementation file, not a transitive relationship. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt f509bd2f7ac59994b9777e20e825bebd; sha256 cda3dd9041e2844686ad34d08afa0191910cb9b60c345123cfe35a8487d7c7ca; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005` | Not ready |
