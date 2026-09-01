# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Tenant archive data export through write_tenant_archive | The export change could create, retain, or remove tenant archive data under an unconfirmed policy. | Tenants whose payloads are written to archives, plus operators responsible for storage, expiration, deletion, and policy compliance. | Any planning, implementation, or release of the export change before the retention owner confirms the policy. | medium | Identify the export retention owner, record the confirmed policy, and verify the changed archive writer conforms to it before planning handoff. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for a data export change starting at exports/export_writer.py and write_tenant_archive. The supplied repository evidence is incomplete, so the report remains blocked until the export retention owner confirms the policy. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Define the data export change beginning at exports/export_writer.py::write_tenant_archive while preserving the tenant archive contract. Do not advance the change to planning or implementation until the export retention owner is identified and confirms the retention policy that applies to tenant archives. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | write_tenant_archive continues to produce a tenant archive result associated with the requested tenant and payload. | verified | exports/export_writer.py defines ARCHIVE_TARGET as "tenant archive" and write_tenant_archive returns the supplied tenant_id and payload in the archive result. |
| `INV-002` | The export and retention policy continue to refer to the same tenant archive data class. | verified | exports/export_writer.py names the target "tenant archive" and policy/retention.py sets EXPORT_REF to "tenant archive". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | exports/export_writer.py defines ARCHIVE_TARGET as "tenant archive" and write_tenant_archive returns the supplied tenant_id and payload in the archive result. |
| `INV-002` | `REQ-001` | `IMP-001` | exports/export_writer.py names the target "tenant archive" and policy/retention.py sets EXPORT_REF to "tenant archive". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | legal/policy | medium | blocked | unknown | policy/retention.py sets RETENTION_POLICY to "undocumented" and contains no RETENTION_OWNER declaration. The repository evidence does not identify an accountable owner or a confirmed duration, expiration/deletion rule, or exception policy for tenant archives. | `INV-001`, `INV-002` | the pending decision | `AC-001`, `AC-002` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which retention-policy direction does the export retention owner approve for tenant archives? | Document and retain the existing policy | `IMP-001` | Minimizes export behavior changes, but still requires the owner to state the current retention duration, deletion behavior, and exceptions explicitly. |
| Which retention-policy direction does the export retention owner approve for tenant archives? | Approve a revised retention policy | `IMP-001` | Allows new retention behavior for the export change, but expands implementation, migration, operational, and compliance validation scope. |

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
| `REQ-001` | Define the data export change beginning at exports/export_writer.py::write_tenant_archive while preserving the tenant archive contract. Do not advance the change to planning or implementation until the export retention owner is identified and confirms the retention policy that applies to tenant archives. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | The accountable export retention owner is identified and explicitly confirms the tenant archive retention duration, expiration/deletion behavior, and applicable exceptions or legal holds. | Not satisfied: policy/retention.py has no RETENTION_OWNER declaration and describes RETENTION_POLICY as "undocumented". |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | Repository evidence and tests demonstrate that the proposed write_tenant_archive change preserves the tenant and payload association and conforms to the owner-confirmed retention policy. | Not yet assessable: the proposed export mechanics and governing retention policy have not been confirmed. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The governing tenant archive retention policy and accountable owner are not established by the supplied or inspected repository evidence. | none | Export retention owner (identity unconfirmed) |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Tenant archive creation in exports/export_writer.py::write_tenant_archive | The function is the supplied starting point and currently returns a tenant/payload archive result. | High |
| Tenant archive retention policy and ownership in policy/retention.py | The file references tenant archives, marks the retention policy undocumented, and declares no RETENTION_OWNER. | High for the evidence gap; unknown for the intended policy. |
| Downstream storage, expiration, deletion, legal-hold, and operational behavior | No repository evidence was supplied or discovered that resolves these policy-dependent effects. | Unknown; retained as blocked frontier. |
| Graph paths for IMP-001 | PATH-001: exports/export_writer.py → policy/retention.py | PATH-001: provider builtin; confidence lexical; location exports/export_writer.py + policy/retention.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 971d2b1b01d90a8b682e57fdc62c95bd; sha256 681b318e6646eb542f818cf3af71b5b94dff8688791ef71d24ed15ccf0dcbefb; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `IMP-001` | `IMP-001` | `AC-001`, `AC-002` | Not ready |
