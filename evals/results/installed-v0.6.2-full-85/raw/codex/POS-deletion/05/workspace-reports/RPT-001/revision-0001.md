# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | account.delete_flow would delete the account immediately. | Deletion can fail for accounts with invoices or remove finance-linked data before the 30-day retention period. | Accounts with invoices, retained finance records, and callers expecting deletion success. | A deletion request for an account that has invoice references or finance data younger than 30 days. | critical | Choose a compliant retained-record strategy, reject deletion while references exist, or explicitly authorize a retention-policy and schema change. | blocked |
| `IMP-002` | Synchronous account deletion would precede the existing asynchronous cleanup consumer. | Queued or retried cleanup events may act on an already-deleted account or duplicate cleanup work. | The account-cleanup worker and any event publisher or retry mechanism. | An account is deleted synchronously and a cleanup event is later delivered or retried. | high | Define event publication and make cleanup safe for missing or already-cleaned accounts, or remove the event path atomically. | blocked |
| `IMP-003` | account.delete_flow is expected to perform immediate deletion. | Changing a declaration string cannot implement or verify deletion behavior. | Callers of account.delete_flow and maintainers relying on this repository as the behavior source. | The requested change is applied only in db/constraints.py. | high | Identify or add the executable flow boundary and tests before claiming immediate deletion is implemented. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Delete an account immediately through account.delete_flow in db/constraints.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change account.delete_flow so an account deletion request has an immediate, defined outcome while preserving or explicitly superseding the 30-day finance-retention rule, respecting the restrictive invoice foreign key, and defining how existing account-cleanup events behave. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | An account with referencing invoices cannot be physically deleted while invoice.account_id uses ON DELETE RESTRICT. | verified | db/constraints.py declares INVOICE_FK = "invoice.account_id ON DELETE RESTRICT". |
| `INV-002` | Finance data is retained for 30 days. | verified | policy/retention.py declares FINANCE_RETENTION_DAYS = 30 and links it to account.delete_flow. |
| `INV-003` | Account cleanup is integrated through account-cleanup events whose consumer reads event["account_id"]. | verified | workers/cleanup.py declares QUEUE = "account-cleanup", links account.delete_flow, and consume(event) returns event["account_id"]. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003` | db/constraints.py declares INVOICE_FK = "invoice.account_id ON DELETE RESTRICT". |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-003` | policy/retention.py declares FINANCE_RETENTION_DAYS = 30 and links it to account.delete_flow. |
| `INV-003` | `REQ-001` | `IMP-002`, `IMP-003` | workers/cleanup.py declares QUEUE = "account-cleanup", links account.delete_flow, and consume(event) returns event["account_id"]. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | legal/policy | critical | blocked | unknown | The inspected declarations indicate that immediate physical deletion conflicts with both the restrictive invoice foreign key and the 30-day finance-retention setting. | `INV-001`, `INV-002` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | state/concurrency | high | blocked | unknown | workers/cleanup.py consumes account-cleanup events for account.delete_flow, while the inspected repository states no idempotency, cancellation, or already-deleted-account behavior. | `INV-003` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | functionality | high | blocked | unknown | Direct inspection found only INVOICE_FK and FLOW string constants in db/constraints.py; no executable account.delete_flow deletion implementation or test was found in this workspace. | `INV-001`, `INV-002`, `INV-003` | the pending decision | `AC-003` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| What should “delete immediately” mean when invoices must be retained for 30 days and currently restrict physical account deletion? | Immediately deactivate/anonymize the account, retain invoice-linked finance data for 30 days, then physically clean it up. | `IMP-001`, `IMP-002`, `IMP-003` | Meets the immediate user-facing outcome and retention rule, but requires a two-phase state model plus idempotent cleanup. |
| What should “delete immediately” mean when invoices must be retained for 30 days and currently restrict physical account deletion? | Physically delete immediately only when no invoice references exist; otherwise reject with a defined conflict. | `IMP-001`, `IMP-002`, `IMP-003` | Preserves the current foreign key and retained finance data, but deletion is not always successful immediately. |
| What should “delete immediately” mean when invoices must be retained for 30 days and currently restrict physical account deletion? | Physically cascade-delete accounts and invoices immediately and revise the 30-day retention policy. | `IMP-001`, `IMP-002`, `IMP-003` | Provides uniform hard deletion but intentionally removes the current finance-retention guarantee and requires schema, policy, worker, and audit changes. |

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
| `REQ-001` | Change account.delete_flow so an account deletion request has an immediate, defined outcome while preserving or explicitly superseding the 30-day finance-retention rule, respecting the restrictive invoice foreign key, and defining how existing account-cleanup events behave. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | For an account with invoices younger than 30 days, account.delete_flow has a tested outcome that neither violates the selected retention policy nor produces a foreign-key failure. | Required because current ON DELETE RESTRICT and FINANCE_RETENTION_DAYS = 30 conflict with unconditional physical deletion. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | Delivery and retry of an account-cleanup event after the immediate deletion outcome is safe and produces no duplicate destructive effect. | Required because workers/cleanup.py remains linked to account.delete_flow. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-001` | The executable account.delete_flow boundary and tests cover accounts with and without invoice references, including the selected immediate outcome. | Required because db/constraints.py currently contains declarations only and no executable delete flow was found. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The meaning of immediate deletion under the current retention and foreign-key rules is not selected. | none | Product/policy owner |
| `IMP-002` | blocked | Cleanup-event behavior depends on the selected deletion model and an idempotency contract. | none | Account deletion/cleanup maintainer |
| `IMP-003` | blocked | No executable flow or test target is present in the supplied repository scope. | none | Repository maintainer |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| db/constraints.py | Contains only the invoice foreign-key declaration string and account.delete_flow identifier. | High; directly inspected. |
| policy/retention.py | Defines 30-day finance retention and references account.delete_flow. | High; directly inspected. |
| workers/cleanup.py | Defines the account-cleanup queue link and minimal consumer. | High; directly inspected. |
| Executable account.delete_flow implementation, event publisher, schema migration, and tests | Not present among the repository files discovered by rg. | High for this workspace; ownership and intended interfaces remain unknown. |
| Graph paths for IMP-001 | PATH-002: account.delete_flow → account.delete_flow | PATH-002: provider builtin; confidence lexical; location db/constraints.py + policy/retention.py |
| Graph paths for IMP-002 | PATH-001: account.delete_flow → account.delete_flow | PATH-001: provider builtin; confidence lexical; location db/constraints.py + workers/cleanup.py |
| Graph paths for IMP-003 | PATH-001: account.delete_flow → account.delete_flow &#124;&#124; PATH-002: account.delete_flow → account.delete_flow | PATH-001: provider builtin; confidence lexical; location db/constraints.py + workers/cleanup.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location db/constraints.py + policy/retention.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 4f8fbca980a0e6e77b40279d32a2f5b9; sha256 d15805e84e4786f4a9a723cd30b0dc7047967ea4b73fbddee2c297ba722d36eb; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Not ready |
