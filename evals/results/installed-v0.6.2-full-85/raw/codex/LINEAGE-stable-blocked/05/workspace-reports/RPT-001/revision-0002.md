# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | e4ab8aeec5b9e66d1314ecba7ce3476993b45f93f7047382a4691580faf96d16 | pre-decision |

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
| `IMP-001` | `REQ-001` | legal/policy | medium | blocked | unknown | No new repository evidence or retention-owner confirmation has been supplied. policy/retention.py remains documented in the prior report as having RETENTION_POLICY set to "undocumented" with no RETENTION_OWNER declaration, so the accountable owner and confirmed duration, expiration/deletion rule, and exception policy remain unknown. | `INV-001`, `INV-002` | the pending decision | `AC-001`, `AC-002` |

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
| `REQ-001` | Define the data export change beginning at exports/export_writer.py::write_tenant_archive while preserving the tenant archive contract. Do not advance the change to planning or implementation until the export retention owner is identified and confirms the retention policy that applies to tenant archives. | the pending decision | none | Controller-created refinement revision. |
| `REQ-001` | Define the data export change beginning at exports/export_writer.py::write_tenant_archive while preserving the tenant archive contract. Do not advance the change to planning or implementation until the export retention owner is identified and confirms the retention policy that applies to tenant archives. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | The accountable export retention owner is identified and explicitly confirms the tenant archive retention duration, expiration/deletion behavior, and applicable exceptions or legal holds. | Not satisfied: no retention-owner confirmation has been supplied, and the prior report records no RETENTION_OWNER declaration. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | Repository evidence and tests demonstrate that the proposed write_tenant_archive change preserves the tenant and payload association and conforms to the owner-confirmed retention policy. | Not yet assessable: no new repository evidence, proposed export mechanics, or confirmed governing retention policy has been supplied. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | No retention owner confirmation or new repository evidence resolves the governing tenant archive retention policy. | none | Export retention owner (identity unconfirmed) |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Canonical report lineage | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md, whose exact SHA-256 is e4ab8aeec5b9e66d1314ecba7ce3476993b45f93f7047382a4691580faf96d16. | High; persisted selector and exact canonical Markdown hash agree. |
| Tenant archive creation in exports/export_writer.py::write_tenant_archive | No new repository evidence was supplied; the prior verified invariant remains the current evidence basis. | High for unchanged prior evidence. |
| Tenant archive retention policy and ownership in policy/retention.py | No retention-owner confirmation exists, so the intended policy remains unresolved. | High for the evidence gap; unknown for the intended policy. |
| Graph path selected for IMP-001 | PATH-003: exports/export_writer.py → policy/retention.py. | Lexical evidence only; impact confidence remains unknown. |
| Noncanonical chat artifact and graph frontier | The trace surfaced first.final.txt, but it is the chat response rather than canonical lineage bytes and is excluded from the selected impact path. Provider fallback leaves one frontier. | Excluded from lineage per supplied continuity evidence; provider-limited impact coverage remains unknown. |
| Graph paths for IMP-001 | PATH-003: write_tenant_archive → RETENTION_OWNER | PATH-003: provider builtin; confidence lexical; location exports/export_writer.py + policy/retention.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt e2d1e08a6fb89a59d114d2fa659d907b; sha256 c4c8384635d200f3ee4040015e821a4d26a709d6cd1a3ad3c4742f7e83ce18fd; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `IMP-001` | `IMP-001` | `AC-001`, `AC-002` | Not ready |
