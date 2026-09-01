# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Tenant archive export behavior in write_tenant_archive | A data export change could retain, dispose of, or expose tenant archives contrary to the authoritative retention policy. | Tenant archive data, export operators, and policy/compliance stakeholders | Planning or implementing the export change before the retention policy and accountable owner are confirmed | medium | Require the export retention owner to confirm the authoritative policy, including its reference and enforceable archive-lifecycle rules, before planning or implementation. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for a data export change starting at exports/export_writer.py and write_tenant_archive. The supplied repository evidence is incomplete, so the report remains blocked until the export retention owner confirms the policy. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Assess and define the data export change at exports/export_writer.py::write_tenant_archive only after the export retention owner confirms the authoritative retention policy for tenant archives; do not plan or implement the change while that policy and ownership remain undocumented. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | write_tenant_archive creates a tenant archive result containing the supplied tenant identifier and payload. | verified | exports/export_writer.py defines write_tenant_archive and currently returns a tenant/payload archive result. |
| `INV-002` | Tenant archive creation currently applies no explicit retention rule in write_tenant_archive. | verified | The inspected body of exports/export_writer.py::write_tenant_archive only constructs and returns the archive result; it contains no retention-policy lookup or enforcement. |
| `INV-003` | The repository does not currently identify an owner for the tenant export retention policy. | verified | policy/retention.py declares RETENTION_POLICY = "undocumented" and EXPORT_REF = "tenant archive", and contains no RETENTION_OWNER declaration. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | exports/export_writer.py defines write_tenant_archive and currently returns a tenant/payload archive result. |
| `INV-002` | `REQ-001` | `IMP-001` | The inspected body of exports/export_writer.py::write_tenant_archive only constructs and returns the archive result; it contains no retention-policy lookup or enforcement. |
| `INV-003` | `REQ-001` | `IMP-001` | policy/retention.py declares RETENTION_POLICY = "undocumented" and EXPORT_REF = "tenant archive", and contains no RETENTION_OWNER declaration. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | legal/policy | medium | blocked | unknown | The bounded repository scan links exports/export_writer.py to policy/retention.py through PATH-001, but its provider frontier prevents the graph from establishing authoritative policy mechanics. The writer contains no retention enforcement, while the policy is marked undocumented and has no declared owner. | `INV-001`, `INV-002`, `INV-003` | the pending decision | `AC-001`, `AC-002` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| What authoritative tenant-archive retention policy does the export retention owner confirm for write_tenant_archive? | Confirm an existing policy | `IMP-001` | Provide the authoritative policy reference and the exact retention trigger, duration, and disposal requirements; this minimizes product-policy change but may expose implementation gaps. |
| What authoritative tenant-archive retention policy does the export retention owner confirm for write_tenant_archive? | Define a revised policy | `IMP-001` | The owner specifies new retention, deletion, exception, and audit requirements; this resolves ambiguity but expands policy review and implementation scope. |

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
| `REQ-001` | Assess and define the data export change at exports/export_writer.py::write_tenant_archive only after the export retention owner confirms the authoritative retention policy for tenant archives; do not plan or implement the change while that policy and ownership remain undocumented. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-003` | The accountable export retention owner is identified and confirms an authoritative policy reference plus the exact tenant-archive retention trigger, duration, disposal behavior, exceptions, and audit requirements. | No RETENTION_OWNER declaration or documented retention policy currently exists in policy/retention.py. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-002` | Before implementation, the confirmed retention rules are mapped to explicit expected behavior and verification criteria for write_tenant_archive. | The current writer body contains no retention-policy lookup or enforcement, so alignment cannot be verified without the owner's confirmed rules. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The authoritative retention policy and accountable owner are absent from repository evidence, so the required tenant-archive behavior cannot be safely selected. | none | Export retention owner (identity not yet confirmed) |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| exports/export_writer.py::write_tenant_archive | Defines the tenant archive write entry point and currently returns the tenant identifier and payload without retention enforcement. | high |
| policy/retention.py | Marks RETENTION_POLICY as undocumented, references tenant archives, and has no RETENTION_OWNER declaration. | high |
| Downstream tenant-archive retention behavior | PATH-001 links the writer and retention policy, but the scan provider was unavailable and fallback graph evidence does not establish the missing policy mechanics. | medium |
| Graph paths for IMP-001 | PATH-001: exports/export_writer.py → policy/retention.py | PATH-001: provider builtin; confidence lexical; location exports/export_writer.py + policy/retention.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 066bf8e31a3a78fb4fad6d44912385d4; sha256 ee6a7fe01ac4110532acb660d964969ae3a09031e3a3d51470e37736f2efc74c; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001` | `IMP-001` | `AC-001`, `AC-002` | Not ready |
