# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Tenant archive data export in write_tenant_archive | Changing archive creation without an approved retention rule could cause exported tenant data to be retained too long, deleted too early, or handled inconsistently. | Tenant archive payloads, tenants whose data is exported, and operators responsible for retention compliance | Any change to write_tenant_archive or its archive lifecycle before the authoritative retention policy is confirmed | high | Keep the change blocked until the export retention owner identifies the approved policy and confirms its duration or deletion trigger; then revise this report with that evidence. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for a data export change starting at exports/export_writer.py and write_tenant_archive. The supplied repository evidence is incomplete, so the report remains blocked until the export retention owner confirms the policy. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change the tenant archive data-export behavior beginning at exports/export_writer.py::write_tenant_archive only after the export retention owner confirms the authoritative retention policy, including its retention duration or deletion trigger. Until that confirmation is recorded, the change is blocked and must not proceed to planning or implementation. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | write_tenant_archive continues to produce a tenant archive containing the supplied tenant identifier and payload until an approved change defines replacement behavior. | verified | exports/export_writer.py defines write_tenant_archive(tenant_id, payload) and returns a mapping containing tenant and payload. |
| `INV-002` | The repository currently does not declare an owner or an actionable retention rule for tenant archives. | verified | policy/retention.py contains RETENTION_POLICY = "undocumented" and EXPORT_REF = "tenant archive"; repository search found no RETENTION_OWNER declaration. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | exports/export_writer.py defines write_tenant_archive(tenant_id, payload) and returns a mapping containing tenant and payload. |
| `INV-002` | `REQ-001` | `IMP-001` | policy/retention.py contains RETENTION_POLICY = "undocumented" and EXPORT_REF = "tenant archive"; repository search found no RETENTION_OWNER declaration. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | legal/policy | high | blocked | unknown | The export entry point and retention policy file are linked by tenant-archive terminology, but the repository provides neither a RETENTION_OWNER declaration nor an approved duration or deletion trigger. The governing policy therefore cannot be established from current evidence. | `INV-001`, `INV-002` | the pending decision | `AC-001` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which approved retention policy must govern tenant archives produced by write_tenant_archive? | Apply an existing tenant-archive retention policy | `IMP-001` | Reuses an established policy, but the owner must provide an authoritative reference and confirm its duration and deletion trigger. |
| Which approved retention policy must govern tenant archives produced by write_tenant_archive? | Approve an export-specific retention policy | `IMP-001` | Can match export-specific needs, but requires owner approval and explicit lifecycle parameters before the change can proceed. |
| Which approved retention policy must govern tenant archives produced by write_tenant_archive? | Do not proceed with the export change | `IMP-001` | Avoids introducing an ungoverned data lifecycle, but leaves the requested export behavior unchanged. |

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
| new | `IMP-001` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Change the tenant archive data-export behavior beginning at exports/export_writer.py::write_tenant_archive only after the export retention owner confirms the authoritative retention policy, including its retention duration or deletion trigger. Until that confirmation is recorded, the change is blocked and must not proceed to planning or implementation. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | The export retention owner is identified and supplies an authoritative policy reference that states the tenant archive retention duration or deletion trigger before planning or implementation begins. | Not satisfied: policy/retention.py has no RETENTION_OWNER declaration and describes the policy as undocumented. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The applicable retention policy, duration or deletion trigger, and accountable confirmer are not established by the supplied or inspected repository evidence. | none | Export retention owner (identity not declared in the repository) |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Tenant archive export writer | exports/export_writer.py defines ARCHIVE_TARGET = "tenant archive" and write_tenant_archive. | high |
| Tenant archive retention policy and ownership | policy/retention.py marks the policy undocumented and contains no RETENTION_OWNER declaration. | high for the evidence gap; unknown for the governing policy |
| Downstream storage, delivery, deletion jobs, and external compliance obligations | No supplied or discovered evidence identifies these consumers or obligations. | unknown and excluded from confirmed scope pending owner evidence |
| Graph paths for IMP-001 | PATH-001: exports/export_writer.py → policy/retention.py | PATH-001: provider builtin; confidence lexical; location exports/export_writer.py + policy/retention.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 6c125fae823e4788b416167e1441ea96; sha256 13c09eca16476902de1fe1e655b1162e2315a94356cbcb1ec9b9cd4b1807d7d2; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `IMP-001` | `IMP-001` | `AC-001` | Not ready |
