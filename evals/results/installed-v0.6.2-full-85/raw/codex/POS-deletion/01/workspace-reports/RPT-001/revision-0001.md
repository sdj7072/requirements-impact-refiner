# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | account.delete_flow becomes an immediate deletion path. | Deletion will fail on existing invoices, or a constraint change could erase retained finance records. | Accounts with invoices and all retained invoice data. | Deleting an account before its invoice references have been removed or transformed. | critical | Choose and implement an explicit invoice lifecycle—retained/anonymized, immediately deleted under an approved exception, or delayed account removal. | blocked |
| `IMP-002` | Account deletion timing changes from a retention-linked flow to immediate completion. | Finance records may be removed earlier than the configured retention period or may retain personal account linkage after the account is said to be deleted. | Finance retention obligations, invoice auditability, and deletion semantics. | Immediate deletion of an account that has finance data younger than 30 days. | high | Document and test whether finance rows survive in anonymized/detached form, are deleted under an approved policy exception, or keep account deletion pending. | blocked |
| `IMP-003` | Deletion moves to immediate execution while an account-cleanup event consumer remains. | Queued or retried cleanup may act on an already deleted account, fail repeatedly, or duplicate irreversible cleanup. | Cleanup jobs, retries, monitoring, and downstream resources keyed by account_id. | An account-cleanup event is delivered after synchronous deletion or delivered more than once. | high | Define whether the event is retired or retained for downstream cleanup, and make consumption idempotent for missing accounts and duplicate deliveries. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Delete an account immediately through account.delete_flow in db/constraints.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Make account.delete_flow complete account deletion immediately, including when invoices reference the account, while explicitly defining how 30-day finance retention is preserved or intentionally overridden and ensuring account-cleanup event handling remains safe after synchronous deletion. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | An account referenced by invoice.account_id cannot currently be deleted. | verified | db/constraints.py declares INVOICE_FK as "invoice.account_id ON DELETE RESTRICT". |
| `INV-002` | Finance data is retained for 30 days. | verified | policy/retention.py sets FINANCE_RETENTION_DAYS = 30 and links the policy to account.delete_flow. |
| `INV-003` | Account cleanup currently has an asynchronous event consumer that reads event["account_id"]. | verified | workers/cleanup.py declares QUEUE = "account-cleanup", links account.delete_flow, and consume(event) returns event["account_id"]. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | db/constraints.py declares INVOICE_FK as "invoice.account_id ON DELETE RESTRICT". |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002` | policy/retention.py sets FINANCE_RETENTION_DAYS = 30 and links the policy to account.delete_flow. |
| `INV-003` | `REQ-001` | `IMP-003` | workers/cleanup.py declares QUEUE = "account-cleanup", links account.delete_flow, and consume(event) returns event["account_id"]. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | data | critical | blocked | unknown | The restrictive invoice.account_id foreign key directly prevents immediate deletion whenever invoices exist; the repository does not define cascade, detachment, or anonymization behavior. The selected graph path is only lexical and the provider frontier limits transitive verification. | `INV-001`, `INV-002` | the pending decision | `AC-001`, `AC-002` |
| `IMP-002` | `REQ-001` | legal/policy | high | blocked | unknown | The requested immediate deletion is not reconciled with the repository's explicit 30-day finance retention setting. The graph relates the files lexically and cannot verify policy intent beyond the supplied source. | `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | operations | high | blocked | unknown | workers/cleanup.py consumes account-cleanup events by account_id, but no producer, retry, ordering, or idempotency behavior is present in the repository; the graph relation is lexical and optional providers are unavailable. | `INV-003` | the pending decision | `AC-003` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| How should immediate account deletion handle invoices that are still inside the 30-day finance-retention window? | Delete the account immediately but retain finance records for 30 days in a detached or anonymized form. | `IMP-001`, `IMP-002`, `IMP-003` | Preserves the retention window and immediate account removal, but requires a nullable/repointed invoice relationship, a defined retained-data shape, and idempotent cleanup. |
| How should immediate account deletion handle invoices that are still inside the 30-day finance-retention window? | Delete the account and its invoices immediately under an explicit retention-policy exception. | `IMP-001`, `IMP-002`, `IMP-003` | Produces the simplest hard-delete behavior, but overrides the configured 30-day policy and may remove required finance/audit data. |
| How should immediate account deletion handle invoices that are still inside the 30-day finance-retention window? | Keep finance-linked accounts pending until 30 days elapse, then let cleanup hard-delete them. | `IMP-001`, `IMP-002`, `IMP-003` | Preserves current retention and event-driven cleanup, but does not satisfy literal immediate account deletion; only access or personal identifiers could be removed immediately. |

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
| new | `IMP-001`, `IMP-002`, `IMP-003` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Make account.delete_flow complete account deletion immediately, including when invoices reference the account, while explicitly defining how 30-day finance retention is preserved or intentionally overridden and ensuring account-cleanup event handling remains safe after synchronous deletion. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | account.delete_flow completes with a defined successful outcome when the account has one or more invoices. | Must be verified by a test covering an account referenced by invoice.account_id. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | For finance data younger than 30 days, the selected retain, anonymize, delete, or defer behavior is explicit and tested. | Must be verified against policy/retention.py and persistence behavior at deletion time. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | account-cleanup processing succeeds safely for missing accounts, duplicate events, and events delivered after immediate deletion, or the obsolete event path is removed. | Must be verified with worker tests for post-delete and redelivery scenarios. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The required invoice lifecycle is not specified, and the existing foreign key rejects the requested deletion. | none | Product and finance-policy owner |
| `IMP-002` | blocked | No evidence authorizes shortening or bypassing FINANCE_RETENTION_DAYS. | none | Finance-policy or compliance owner |
| `IMP-003` | blocked | Worker behavior depends on whether cleanup remains asynchronous after the account row is deleted. | none | Account deletion implementation owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| db/constraints.py and account.delete_flow deletion semantics | The file contains the restrictive invoice foreign-key declaration and the flow identifier. | verified |
| policy/retention.py finance retention behavior | The file contains a 30-day retention constant linked to account.delete_flow. | verified |
| workers/cleanup.py account-cleanup consumption | The file declares the queue, links the deletion flow, and consumes account_id. | verified |
| Event producer, database migrations, invoice schema details, authorization, and external cleanup side effects | No additional source files are present in the repository. | unknown; must be supplied or added during implementation |
| Graph paths for IMP-001 | PATH-002: account.delete_flow → account.delete_flow | PATH-002: provider builtin; confidence lexical; location db/constraints.py + policy/retention.py |
| Graph paths for IMP-002 | PATH-002: account.delete_flow → account.delete_flow | PATH-002: provider builtin; confidence lexical; location db/constraints.py + policy/retention.py |
| Graph paths for IMP-003 | PATH-001: account.delete_flow → account.delete_flow | PATH-001: provider builtin; confidence lexical; location db/constraints.py + workers/cleanup.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt ddeccde065b030ef1588fb88646952c6; sha256 fd90703df43c446c3bdbc63947cd2b6fd21c9bbe60790577420ba32e14051ed6; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Not ready |
