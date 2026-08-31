# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | a4e7732228f1d9e26476f33eafa5d3be70a327ebef2fcdc436472b92c97b700f | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Tenant archive data export retention behavior in write_tenant_archive. | Implementing the export change without an authoritative retention rule could retain tenant data too long, delete it too early, or make the archive behavior noncompliant with the intended policy. | Tenant archive exports and the tenant data contained in those archives. | Any modification to write_tenant_archive that changes archive creation, storage duration, expiry, or deletion before retention policy confirmation. | high | The export retention owner must confirm and document the applicable policy, after which the export change and its tests must be aligned to that policy. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for a data export change starting at exports/export_writer.py and write_tenant_archive. The supplied repository evidence is incomplete, so the report remains blocked until the export retention owner confirms the policy. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change tenant archive export behavior at exports/export_writer.py::write_tenant_archive only after the export retention owner confirms the applicable retention policy; preserve the existing tenant and payload archive contract unless that confirmed policy explicitly requires a change. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | write_tenant_archive continues to produce a tenant archive that associates the supplied tenant_id with the supplied payload unless an owner-approved retention policy requires otherwise. | verified | exports/export_writer.py currently returns an archive-shaped mapping containing the supplied tenant_id and payload. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | exports/export_writer.py currently returns an archive-shaped mapping containing the supplied tenant_id and payload. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | legal/policy | high | blocked | unknown | policy/retention.py declares RETENTION_POLICY as undocumented and contains no RETENTION_OWNER declaration; no owner-approved retention rule is present in the supplied or inspected repository evidence. | `INV-001` | the pending decision | `AC-001`, `AC-002` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which retention policy does the export retention owner authorize for tenant archives written by write_tenant_archive? | Confirm the existing tenant-archive retention policy and document its duration and deletion semantics. | `IMP-001` | Preserves intended existing behavior, but work cannot proceed until the currently undocumented policy is made explicit. |
| Which retention policy does the export retention owner authorize for tenant archives written by write_tenant_archive? | Approve a new tenant-archive retention period and deletion policy. | `IMP-001` | Provides a clear new rule, but may require archive lifecycle, migration, and compatibility work beyond the writer. |
| Which retention policy does the export retention owner authorize for tenant archives written by write_tenant_archive? | Approve an explicit no-expiry exception for tenant archives. | `IMP-001` | Minimizes deletion changes, but creates the greatest storage, privacy, and compliance exposure and requires explicit owner acceptance. |

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
| `REQ-001` | Change tenant archive export behavior at exports/export_writer.py::write_tenant_archive only after the export retention owner confirms the applicable retention policy; preserve the existing tenant and payload archive contract unless that confirmed policy explicitly requires a change. | the pending decision | none | Controller-created refinement revision. |
| `REQ-001` | Change tenant archive export behavior at exports/export_writer.py::write_tenant_archive only after the export retention owner confirms the applicable retention policy; preserve the existing tenant and payload archive contract unless that confirmed policy explicitly requires a change. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | The export retention owner is identified and provides a documented, authoritative retention duration and deletion semantics for tenant archives. | No RETENTION_OWNER declaration or documented retention policy currently exists in policy/retention.py. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | write_tenant_archive and its verification coverage implement the confirmed policy while preserving tenant_id and payload association unless the approved policy explicitly changes that contract. | exports/export_writer.py currently defines only the tenant_id and payload archive mapping; policy-driven lifecycle behavior is not evidenced. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The applicable retention duration, deletion semantics, and accountable owner are absent from repository evidence, so the export change cannot be safely refined or handed to implementation. | none | Export retention owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| exports/export_writer.py::write_tenant_archive | The function remains the supplied and verified entry point for tenant archive creation. | high |
| policy/retention.py | The file contains RETENTION_POLICY = "undocumented" and no RETENTION_OWNER declaration; no owner confirmation was supplied. | high for the evidence gap; low for the intended retention rule |
| Canonical lineage continuity | The persisted RPT-001 current report selected the exact canonical Markdown predecessor with SHA-256 a4e7732228f1d9e26476f33eafa5d3be70a327ebef2fcdc436472b92c97b700f; first.final.txt is chat output and is not used as canonical lineage evidence. | high |
| Downstream archive lifecycle, deletion, migration, and compliance behavior | The direct receipt path connects exports/export_writer.py to policy/retention.py, but repository evidence does not establish downstream mechanics. | unknown pending owner confirmation and additional evidence |
| Graph coverage limitation | The receipt also contains lexical paths through first.final.txt and an unknown provider frontier; those chat-derived paths are not selected as impact evidence. | provider-limited; the direct PATH-003 is used without upgrading the impact evidence level |
| Graph paths for IMP-001 | PATH-003: write_tenant_archive → RETENTION_OWNER | PATH-003: provider builtin; confidence lexical; location exports/export_writer.py + policy/retention.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 2cc0168862ce09dc8f4eda2f4fa3de40; sha256 9e295b91ed48b8f08b823e6f156b7e3918fc35ef71bca94cdb6111647b3717af; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `IMP-001` | `IMP-001` | `AC-001`, `AC-002` | Not ready |
