# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Tenant archive export behavior in write_tenant_archive | Tenant archive data could be retained, deleted, or governed inconsistently because neither the applicable retention rule nor its accountable owner is established. | Tenants whose payloads are written to archives, operators responsible for archive lifecycle, and policy/compliance stakeholders | Implementing or releasing the export change before the retention policy is confirmed | high | Keep the change blocked until the export retention owner is identified and confirms a documented tenant-archive retention policy; then verify the existing archive return contract remains intact unless explicitly changed. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for a data export change starting at exports/export_writer.py and write_tenant_archive. The supplied repository evidence is incomplete, so the report remains blocked until the export retention owner confirms the policy. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change tenant data export behavior beginning at exports/export_writer.py::write_tenant_archive only after the export retention owner confirms and documents the retention policy applicable to tenant archives. Until that confirmation exists, the change remains blocked. Preserve the existing tenant archive return structure unless a separately approved requirement changes it. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | write_tenant_archive continues to produce a tenant archive containing the supplied tenant identifier and payload unless an approved requirement explicitly changes that contract. | verified | exports/export_writer.py defines write_tenant_archive(tenant_id, payload) and returns a mapping with the tenant and payload values. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | exports/export_writer.py defines write_tenant_archive(tenant_id, payload) and returns a mapping with the tenant and payload values. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | legal/policy | high | blocked | unknown | Supplied and inspected evidence shows that exports/export_writer.py writes tenant archives, while policy/retention.py states RETENTION_POLICY = "undocumented" and contains no RETENTION_OWNER declaration. The promoted fallback scan connects exports/export_writer.py to policy/retention.py on PATH-001 but does not establish the governing retention rule or owner. | `INV-001` | the pending decision | `AC-001`, `AC-002` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which retention policy should govern tenant archives produced by write_tenant_archive, and who is the accountable export retention owner? | Apply an existing documented retention policy | `IMP-001` | Reuses an established policy, but the owner must identify the authoritative policy and explicitly confirm that it covers tenant archives. |
| Which retention policy should govern tenant archives produced by write_tenant_archive, and who is the accountable export retention owner? | Define a tenant-archive-specific retention policy | `IMP-001` | Makes archive lifecycle rules explicit, but requires policy definition, ownership assignment, and approval before implementation can proceed. |

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
| `REQ-001` | Change tenant data export behavior beginning at exports/export_writer.py::write_tenant_archive only after the export retention owner confirms and documents the retention policy applicable to tenant archives. Until that confirmation exists, the change remains blocked. Preserve the existing tenant archive return structure unless a separately approved requirement changes it. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Before implementation begins, a named export retention owner confirms the authoritative policy governing tenant archives, including the applicable retention and deletion rule, and the repository or approved policy record documents that confirmation. | Current evidence is insufficient: policy/retention.py marks RETENTION_POLICY as undocumented and has no RETENTION_OWNER declaration. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | The existing write_tenant_archive tenant-and-payload return contract remains unchanged unless the confirmed requirement explicitly authorizes a contract change. | The current function returns both supplied values; no approved requirement in the supplied evidence authorizes changing that structure. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The applicable tenant-archive retention policy and the person accountable for confirming it are not established by the available repository evidence. | none | Export retention owner (not identified in repository evidence) |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| exports/export_writer.py::write_tenant_archive and its tenant archive output behavior | The function is the stated change entry point and returns tenant archive data. | high |
| policy/retention.py retention policy and ownership metadata | RETENTION_POLICY is set to "undocumented" and no RETENTION_OWNER declaration is present. | high |
| Downstream archive storage, deletion jobs, and external policy records | No evidence was supplied or discovered that identifies these consumers or rules; graph provider fallback left an unknown frontier. | unknown |
| Graph paths for IMP-001 | PATH-001: exports/export_writer.py → policy/retention.py | PATH-001: provider builtin; confidence lexical; location exports/export_writer.py + policy/retention.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 24bc50816f35838be02d372dead38aa1; sha256 3fc09ab1feffaca12fe0adf7016afd5789adb84d03a23f3bc0277227b04da636; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `IMP-001` | `IMP-001` | `AC-001`, `AC-002` | Not ready |
