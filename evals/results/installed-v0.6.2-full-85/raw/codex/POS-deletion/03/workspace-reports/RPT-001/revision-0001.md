# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | account.delete_flow would complete physical account deletion immediately. | Deletion will fail for accounts with invoices, or a loosened constraint could orphan or destroy retained finance records. | Accounts with invoice history, their invoices, and finance/audit consumers. | account.delete_flow runs for an account referenced by invoice.account_id. | critical | Choose and implement an explicit retained-invoice strategy before changing the restriction. | blocked |
| `IMP-002` | Immediate account deletion changes the timing and meaning of deletion under account.delete_flow. | Finance data may be erased before the 30-day window or personal account identity may remain longer than promised. | Deleted users, finance records, retention enforcement, and compliance/audit stakeholders. | An account is deleted before its linked finance-retention period expires. | critical | Define deletion semantics that separate immediate account identity removal from required finance-record retention, or approve an explicit policy exception. | blocked |
| `IMP-003` | The account may be absent before asynchronous account-cleanup processing starts. | Cleanup can fail, retry forever, or skip dependent cleanup because its account no longer exists. | The account-cleanup worker, queue operations, and residual account-linked data. | A cleanup event is delivered after immediate account deletion or is redelivered. | high | Specify delete/event ordering and make cleanup tolerate a missing account and duplicate events. | refining |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Delete an account immediately through account.delete_flow in db/constraints.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Make account.delete_flow delete an account immediately, while explicitly resolving the existing invoice foreign-key restriction, the 30-day finance-retention obligation, and the account-cleanup event contract. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | An account referenced by invoice.account_id cannot currently be deleted through the database relationship. | verified | db/constraints.py declares INVOICE_FK as "invoice.account_id ON DELETE RESTRICT". |
| `INV-002` | Finance data associated with account deletion is retained for 30 days. | verified | policy/retention.py sets FINANCE_RETENTION_DAYS = 30 and links the policy to account.delete_flow. |
| `INV-003` | The account-cleanup worker consumes an account-cleanup event and reads event["account_id"]. | verified | workers/cleanup.py declares QUEUE = "account-cleanup", links account.delete_flow, and returns event["account_id"] from consume(event). |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | db/constraints.py declares INVOICE_FK as "invoice.account_id ON DELETE RESTRICT". |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002` | policy/retention.py sets FINANCE_RETENTION_DAYS = 30 and links the policy to account.delete_flow. |
| `INV-003` | `REQ-001` | `IMP-003` | workers/cleanup.py declares QUEUE = "account-cleanup", links account.delete_flow, and returns event["account_id"] from consume(event). |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | data | critical | blocked | unknown | The requested immediate physical account deletion conflicts with the current ON DELETE RESTRICT invoice relationship; no code specifies whether invoices are deleted, detached, anonymized, or retained under another identity. The scan provider was unavailable, so transitive lineage remains a coverage frontier. | `INV-001`, `INV-002` | the pending decision | `AC-001`, `AC-002` |
| `IMP-002` | `REQ-001` | legal/policy | critical | blocked | unknown | The repository sets finance retention to 30 days, while the request requires immediate account deletion; it does not define whether deletion erases personal account data while retaining finance records or erases all related data. The scan provider was unavailable, so transitive lineage remains a coverage frontier. | `INV-002` | the pending decision | `AC-003`, `AC-004` |
| `IMP-003` | `REQ-001` | operations | high | refining | unknown | workers/cleanup.py consumes account-cleanup events using account_id, but the repository does not define ordering, retries, idempotency, or behavior when the account row has already been physically removed. The scan provider was unavailable, so transitive lineage remains a coverage frontier. | `INV-003` | the pending decision | `AC-005`, `AC-006` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| For accounts with invoices still inside the 30-day finance-retention window, what must “delete immediately” do with the retained finance records? | Delete the account identity immediately, but retain invoices for 30 days under a detached or anonymized reference. | `IMP-001`, `IMP-002`, `IMP-003` | Meets immediate identity deletion and finance retention, but requires a schema/reference strategy plus cleanup-worker idempotency. |
| For accounts with invoices still inside the 30-day finance-retention window, what must “delete immediately” do with the retained finance records? | Mark the account pending deletion and physically delete it only after the 30-day retention window. | `IMP-001`, `IMP-002`, `IMP-003` | Preserves the existing restriction and retention behavior, but does not provide immediate physical deletion. |
| For accounts with invoices still inside the 30-day finance-retention window, what must “delete immediately” do with the retained finance records? | Cascade-delete invoices and the account immediately as an approved retention-policy exception. | `IMP-001`, `IMP-002`, `IMP-003` | Provides immediate physical erasure, but intentionally violates the repository’s 30-day finance-retention rule unless policy owners approve and update it. |

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
| `REQ-001` | Make account.delete_flow delete an account immediately, while explicitly resolving the existing invoice foreign-key restriction, the 30-day finance-retention obligation, and the account-cleanup event contract. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | account.delete_flow has a defined, tested result for accounts both with and without invoices, with no foreign-key failure or orphaned invoice reference. | Current db/constraints.py only declares ON DELETE RESTRICT; no future handling is implemented. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-002` | When retention applies, required invoice data remains queryable and referentially valid for the full retention period without preserving unnecessary account identity. | Current retention.py defines 30 days but no separation between account identity and retained finance data. |
| `AC-003` | `REQ-001` | `IMP-002` | `INV-002` | Deletion behavior enforces the selected 30-day retention interpretation, including the boundary at day 30. | FINANCE_RETENTION_DAYS is 30; no enforcement logic is present in the supplied scope. |
| `AC-004` | `REQ-001` | `IMP-002` | `INV-002` | If immediate identity deletion is selected, account credentials and non-retained personal account data become unavailable synchronously when account.delete_flow succeeds. | The repository links the flow to retention but contains no deletion implementation. |
| `AC-005` | `REQ-001` | `IMP-003` | `INV-003` | The cleanup consumer succeeds safely when the account is already absent and when the same event is delivered more than once. | Current consume(event) only reads account_id; missing-account and duplicate-event behavior are unspecified. |
| `AC-006` | `REQ-001` | `IMP-003` | `INV-003` | Tests establish whether account-cleanup is emitted before or after physical deletion and verify that worker processing completes in that order. | workers/cleanup.py declares the queue and flow link, but no ordering contract or tests exist. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | Immediate deletion cannot be implemented safely while ON DELETE RESTRICT remains and invoice disposition is undefined. | none | Product/data owner with finance-policy input |
| `IMP-002` | blocked | The intended meaning of immediate deletion under the 30-day finance-retention rule requires an explicit policy choice. | none | Finance/compliance policy owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| db/constraints.py account.delete_flow and invoice.account_id relationship | The file declares both INVOICE_FK with ON DELETE RESTRICT and FLOW = account.delete_flow. | High; directly inspected. |
| policy/retention.py finance-retention behavior linked to account.delete_flow | The file sets FINANCE_RETENTION_DAYS = 30 and FLOW_REF = account.delete_flow. | High; directly inspected. |
| workers/cleanup.py account-cleanup event consumer | The file names the account-cleanup queue, links account.delete_flow, and consumes account_id. | High for the visible contract; low for ordering/retry semantics because none are present. |
| Tests and additional schema/runtime behavior | Repository inventory contains only the three supplied Python files and no tests or migration definitions. | High for this mounted repository snapshot. |
| Graph paths for IMP-001 | PATH-002: account.delete_flow → account.delete_flow | PATH-002: provider builtin; confidence lexical; location db/constraints.py + policy/retention.py |
| Graph paths for IMP-002 | PATH-002: account.delete_flow → account.delete_flow | PATH-002: provider builtin; confidence lexical; location db/constraints.py + policy/retention.py |
| Graph paths for IMP-003 | PATH-001: account.delete_flow → account.delete_flow | PATH-001: provider builtin; confidence lexical; location db/constraints.py + workers/cleanup.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 088792d00f58327cd26cfa15dcd5586e; sha256 dd2e529f3276c55404e3e116f5409d3763251345093bef0e6bdb2bfeb35498cf; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-002` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005`, `AC-006` | Not ready |
