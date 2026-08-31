# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | 4536f1a5c6d8fca1a918fde020c1a9a9ed3f4607ef9c1f45c8c051075255c630 | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Tenant archive export behavior in write_tenant_archive. | The change could create, retain, or dispose of tenant archive data under an unconfirmed retention policy. | Tenants whose data is included in archives, plus operators responsible for archive storage and deletion. | Any modification to write_tenant_archive that changes archive contents, lifecycle, storage, or deletion behavior. | medium | Keep the change blocked until the export retention owner is identified and confirms the governing policy; then encode that confirmation in implementation requirements and tests. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for a data export change starting at exports/export_writer.py and write_tenant_archive. The supplied repository evidence is incomplete, so the report remains blocked until the export retention owner confirms the policy. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Assess the proposed data export change beginning at exports/export_writer.py::write_tenant_archive, preserving tenant archive behavior and withholding planning or implementation until the export retention owner confirms which retention policy applies. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | write_tenant_archive continues to produce tenant archives for tenants. | verified | Supplied repository evidence states that exports/export_writer.py defines write_tenant_archive for tenant archives. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | Supplied repository evidence states that exports/export_writer.py defines write_tenant_archive for tenant archives. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | legal/policy | medium | blocked | unknown | The supplied evidence links the tenant archive writer to retention concerns and states that policy/retention.py has no RETENTION_OWNER declaration, but it does not identify the accountable owner or confirm the applicable policy. | `INV-001` | the pending decision | `AC-001` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which retention policy does the export retention owner approve for tenant archives affected by this change? | Confirm the existing retention policy applies unchanged. | `IMP-001` | Minimizes change scope, but requires explicit owner confirmation that existing periods and disposal rules cover the modified export. |
| Which retention policy does the export retention owner approve for tenant archives affected by this change? | Approve a revised retention policy for the changed export. | `IMP-001` | Allows lifecycle behavior to change, but adds policy, implementation, migration, and verification work. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | `IMP-001` |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | none |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Assess the proposed data export change beginning at exports/export_writer.py::write_tenant_archive, preserving tenant archive behavior and withholding planning or implementation until the export retention owner confirms which retention policy applies. | the pending decision | none | Controller-created refinement revision. |
| `REQ-001` | Assess the proposed data export change beginning at exports/export_writer.py::write_tenant_archive, preserving tenant archive behavior and withholding planning or implementation until the export retention owner confirms which retention policy applies. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Before planning or implementation proceeds, the identified export retention owner confirms the applicable tenant-archive retention and disposal policy, and that confirmation is recorded as repository evidence. | Completion requires an owner declaration or equivalent accountable-owner record plus explicit policy approval; neither is present in the supplied evidence. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | policy/retention.py has no RETENTION_OWNER declaration, and no other supplied evidence identifies an accountable owner or confirms the policy. | none | Export retention owner (not identified in supplied repository evidence) |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| exports/export_writer.py::write_tenant_archive | Supplied evidence identifies this function as the tenant archive writer and the starting point for the change. | high |
| policy/retention.py and tenant-archive retention ownership | Supplied evidence states that policy/retention.py has no RETENTION_OWNER declaration. | high for the missing declaration; low for the governing policy and accountable owner |
| Downstream archive storage, deletion, scheduling, and consumers | No new repository evidence was supplied for these areas. | unknown |
| Chat-response artifact first.final.txt | The receipt exposes first.final.txt only through lexical paths PATH-001 and PATH-002; it is a chat response and is excluded from canonical predecessor lineage. | excluded from report lineage; graph coverage remains provider-limited |
| Impact graph coverage | The current receipt provides direct PATH-003 from exports/export_writer.py to policy/retention.py and one unknown frontier because ast-grep, codegraph, and scip are unavailable. | provider-limited; direct path confidence lexical |
| Graph paths for IMP-001 | PATH-003: write_tenant_archive → RETENTION_OWNER | PATH-003: provider builtin; confidence lexical; location exports/export_writer.py + policy/retention.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 348f47368bffd0c01fd81245e1ab7580; sha256 37192233064361dae9e2347a46a534c37ea89c11daf0afc5864069531bc9eb22; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `IMP-001` | `IMP-001` | `AC-001` | Not ready |
