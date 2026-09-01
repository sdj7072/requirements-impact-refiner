# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | account.delete_flow would physically remove an account immediately. | The database rejects deletion for accounts that still have invoice rows, or invoice history must be changed first. | Accounts with invoices and the integrity of invoice.account_id. | Immediate hard deletion of an account referenced by invoice.account_id. | critical | Choose whether to defer physical deletion, anonymize or detach retained invoices, or intentionally remove invoice history and the retention rule. | blocked |
| `IMP-002` | Immediate account deletion changes the lifetime of account-linked finance data. | The implementation can violate the configured 30-day finance-retention policy or retain personally identifying account linkage after users believe deletion is complete. | Invoice records, retention enforcement, and account-deletion guarantees. | Deleting an account before FINANCE_RETENTION_DAYS has elapsed. | high | Define whether immediate deletion means access revocation, identity anonymization, or full physical purge, and align the retention policy and schema with that choice. | blocked |
| `IMP-003` | account.delete_flow would complete account deletion immediately while cleanup remains event-driven. | The worker may receive an ID for an already-deleted account, race the transaction, retry destructive work, or lose cleanup work if event publication is not atomic. | The account-cleanup worker, queue retries, and dependent account data. | Publishing or consuming account-cleanup around an immediate physical delete. | high | Specify transaction/outbox ordering and make the cleanup handler idempotent and safe when the account no longer exists. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Delete an account immediately through account.delete_flow in db/constraints.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Make account.delete_flow delete an account immediately, while explicitly defining how invoice rows protected by invoice.account_id ON DELETE RESTRICT, the 30-day finance-retention rule, and queued account-cleanup work remain valid. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | An account referenced by an invoice cannot currently be physically deleted. | verified | db/constraints.py:1 declares invoice.account_id ON DELETE RESTRICT. |
| `INV-002` | Finance data is currently retained for 30 days. | verified | policy/retention.py:1 sets FINANCE_RETENTION_DAYS = 30. |
| `INV-003` | The account-cleanup consumer expects an event containing account_id and is linked to account.delete_flow. | verified | workers/cleanup.py:1-5 names the account-cleanup queue, links account.delete_flow, and reads event["account_id"]. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002` | db/constraints.py:1 declares invoice.account_id ON DELETE RESTRICT. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002` | policy/retention.py:1 sets FINANCE_RETENTION_DAYS = 30. |
| `INV-003` | `REQ-001` | `IMP-003` | workers/cleanup.py:1-5 names the account-cleanup queue, links account.delete_flow, and reads event["account_id"]. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | data | critical | blocked | unknown | PATH-002 identifies db/constraints.py and policy/retention.py only through the scan's lexical/structural fallback; the full runtime deletion behavior is not present in the repository. | `INV-001`, `INV-002` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | legal/policy | high | blocked | unknown | PATH-002 identifies db/constraints.py and policy/retention.py through lexical/structural fallback; no code proving how retention is enforced during deletion is present. | `INV-002`, `INV-001` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | operations | high | blocked | unknown | PATH-001 identifies db/constraints.py and workers/cleanup.py through lexical/structural fallback; event ordering, retries, and missing-account handling are absent from the repository. | `INV-003` | the pending decision | `AC-003` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| What must “delete immediately” mean when the account has retained invoices? | Immediately disable and anonymize the account, retain invoices for 30 days, then physically delete. | `IMP-001`, `IMP-002`, `IMP-003` | Preserves retention and referential integrity, but physical deletion is delayed and the user-facing contract must distinguish immediate deactivation/anonymization from final purge. |
| What must “delete immediately” mean when the account has retained invoices? | Detach or replace invoice.account_id with a non-identifying retention reference, then hard-delete the account immediately. | `IMP-001`, `IMP-002`, `IMP-003` | Allows immediate account removal while retaining finance records, but requires schema/data migration and a defined anonymization standard. |
| What must “delete immediately” mean when the account has retained invoices? | Cascade-delete invoices and the account immediately, and remove or waive the 30-day retention rule. | `IMP-001`, `IMP-002`, `IMP-003` | Provides a full immediate purge, but destroys finance history and changes an explicit retention policy; it may introduce compliance and audit risk. |

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
| `REQ-001` | Make account.delete_flow delete an account immediately, while explicitly defining how invoice rows protected by invoice.account_id ON DELETE RESTRICT, the 30-day finance-retention rule, and queued account-cleanup work remain valid. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | For an account with at least one invoice, account.delete_flow completes according to the selected deletion model without a foreign-key error and without dangling invoice references. | Must be verified with a test covering an invoiced account; current ON DELETE RESTRICT behavior proves the failure case. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | The selected deletion model has an explicit, tested result for finance data before and after the 30-day retention boundary. | Must align with policy/retention.py FINANCE_RETENTION_DAYS = 30 or deliberately revise that policy. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | account-cleanup publication and consumption are idempotent, retry-safe, and succeed when the account has already been deleted or anonymized. | Must be verified with ordering and retry tests around workers/cleanup.py; no such behavior is present in the supplied implementation. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The requested hard-delete behavior cannot coexist with ON DELETE RESTRICT until invoice handling is selected. | none | Product/data-policy owner |
| `IMP-002` | blocked | The meaning of immediate deletion versus the 30-day finance-retention requirement is not specified. | none | Finance retention or compliance owner |
| `IMP-003` | blocked | Cleanup ordering depends on whether the account is physically deleted, anonymized, or deferred. | none | Account deletion implementation owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| db/constraints.py and invoice.account_id deletion semantics | Directly named by the request and verified at db/constraints.py:1-2. | high |
| policy/retention.py finance retention behavior | Direct supplied evidence and verified at policy/retention.py:1-2. | high |
| workers/cleanup.py account-cleanup event contract | Direct supplied evidence and verified at workers/cleanup.py:1-5. | high |
| Unseen schema migrations, event publisher, transaction/outbox logic, and tests | No other implementation files are present in the inspected workspace. | unknown; these are required implementation boundaries but cannot be verified from the repository. |
| Graph paths for IMP-001 | PATH-002: account.delete_flow → account.delete_flow | PATH-002: provider builtin; confidence lexical; location db/constraints.py + policy/retention.py |
| Graph paths for IMP-002 | PATH-002: account.delete_flow → account.delete_flow | PATH-002: provider builtin; confidence lexical; location db/constraints.py + policy/retention.py |
| Graph paths for IMP-003 | PATH-001: account.delete_flow → account.delete_flow | PATH-001: provider builtin; confidence lexical; location db/constraints.py + workers/cleanup.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt af0f1684afa03a17192ea34bd9079ebb; sha256 d482142528c127b87f84494bbdcb309acb184cfc12cf069c9c33bb0ad4272a29; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Not ready |
