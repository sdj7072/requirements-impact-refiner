# POS-deletion — Requirements Impact Refinement

## Part 1 — pre-decision analysis

### Original requirement and current behavior

`REQ-001`: Delete an account immediately, subject to the supplied referential-integrity, finance-retention, and cleanup-worker constraints. Exact deletion transition remains the pending decision.

| Invariant ID | Current behavior that must be preserved | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `invoice.account_id` uses `RESTRICT`; an account referenced by an invoice cannot be removed through an unrestricted parent-row deletion. | `verified` | Supplied repository evidence: “invoice.account_id uses RESTRICT” |
| `INV-002` | Finance records are retained for 30 days under the privacy policy. | `verified` | Supplied repository evidence: “privacy.md requires a 30-day finance retention period” |
| `INV-003` | Account cleanup is consumed by a background worker rather than being completed solely in the initiating request. | `verified` | Supplied repository evidence: “account cleanup is consumed by a background worker” |

### Impact ledger before decision

| ID | Requirement | Category | Severity | State | Evidence level | Evidence | Invariants | Decision | Acceptance criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Data / compatibility | high | `refining` | `verified` | `RESTRICT` prevents immediate account-row deletion while invoices reference it. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | Legal/policy / data | high | `refining` | `verified` | Finance retention requires records to remain available for 30 days. | `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | State/concurrency / operations | medium | `detected` | `verified` | Existing cleanup is processed by a background worker, so completion is asynchronous. | `INV-003` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | Privacy / data | high | `detected` | `unknown` | The supplied evidence does not specify whether personal data may be anonymized while finance rows remain linked, or what user-visible state represents “deleted.” | `INV-001`, `INV-002` | the pending decision | `AC-004` |

### Focused decision needed

“Delete an account immediately” conflicts with the `RESTRICT` foreign key and the 30-day finance-retention requirement. Options were: (1) immediate privacy deletion with a retained finance shell, (2) immediate deletion request with deferred physical deletion, or (3) immediate hard deletion requiring a data-model/retention exception. No concrete decision was recorded until the explicit selection below.

---

## Part 2 — decision response and revised requirement

---

## Decision response and revised requirement

> “Disable sign-in immediately, retain finance-linked records for the required
> 30 days, then let the existing background worker complete deletion.”

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-002` | Disable account sign-in immediately. Preserve finance-linked records for the required 30-day retention period, then allow the existing background worker to complete eligible deletion while preserving referential integrity. | `DEC-001` | `REQ-001` |

## Preserved invariants

| Invariant ID | Must preserve | Evidence |
| --- | --- | --- |
| `INV-001` | `invoice.account_id` `RESTRICT` referential integrity remains valid. | Supplied repository evidence: “invoice.account_id uses RESTRICT” |
| `INV-002` | Finance records remain retained for the policy-required 30 days. | Supplied repository evidence: “privacy.md requires a 30-day finance retention period” |
| `INV-003` | Existing account cleanup remains consumed by the background worker. | Supplied repository evidence: “account cleanup is consumed by a background worker” |

## Recorded decision

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Disable sign-in immediately; retain finance-linked records for 30 days; then let the existing worker complete deletion. | `REQ-002` | `IMP-002` | Meets the immediate access-removal request while preserving finance retention and the existing asynchronous cleanup path. |

## Recalculated impact ledger

| ID | Requirement | Category | Severity | State | Evidence level | Evidence | Invariants | Decision | Acceptance criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-002` | Data / compatibility | high | `mitigated` | `verified` | The account/invoice relationship is retained through the finance window, so the `RESTRICT` FK is not bypassed by immediate access removal. | `INV-001` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-002` | Legal/policy / data | high | `accepted` | `verified` | The selected policy deliberately retains finance-linked records for 30 days. Retained data is not treated as resolved. | `INV-002` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-002` | State/concurrency / operations | medium | `unchanged` | `verified` | Cleanup remains asynchronous through the existing background worker after the retention period. | `INV-003` | `DEC-001` | `AC-003` |
| `IMP-004` | `REQ-002` | Privacy / data | high | `mitigated` | `unknown` | Immediate sign-in disable defines the access outcome, but the supplied evidence does not identify every personal field eligible for removal/anonymization while finance-linked records remain. | `INV-001`, `INV-002` | `DEC-001` | `AC-004` |

## Requirement revision history

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Delete an account immediately, subject to supplied constraints. | the pending decision | — | Decision required. |
| `REQ-002` | Disable sign-in immediately; retain finance-linked records for 30 days; worker then completes eligible deletion. | `DEC-001` | none | `IMP-001` mitigated; `IMP-002` accepted; `IMP-003` unchanged; `IMP-004` mitigated. |

## Acceptance and regression criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-002` | `IMP-001` | `INV-001` | After the request, invoices remain referentially valid; no deletion operation violates `invoice.account_id` `RESTRICT`. | Supplied FK evidence; implementation test required. |
| `AC-002` | `REQ-002` | `IMP-002` | `INV-002` | Finance-linked records remain retained for the required 30 days and are not removed early. | Supplied privacy-policy evidence; retention test required. |
| `AC-003` | `REQ-002` | `IMP-003` | `INV-003` | The existing background worker completes eligible deletion only after the retention period, with safe retry behavior. | Supplied worker evidence; worker test required. |
| `AC-004` | `REQ-002` | `IMP-004` | `INV-001`, `INV-002` | Sign-in is rejected immediately after the request; the remaining personal-data treatment is explicitly defined without deleting required finance-linked records. | Immediate-access test required; field-level policy evidence remains a gap. |

## Whole-set delta

- `resolved: none` (retained finance-linked data is not resolved)
- `mitigated: IMP-001, IMP-004`
- `unchanged: IMP-003`
- `accepted: IMP-002`
- `deferred: none`
- `blocked: none`
- `new: none`

Every known impact appears exactly once in the delta. `IMP-002` is accepted through `DEC-001`, but remains a retained-data obligation until the required retention period and cleanup evidence are satisfied.

## Unresolved, deferred, and blocked items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-004` | `mitigated` with evidence gap | Exact field-level anonymization/deletion treatment for non-finance personal data is not supplied. | `DEC-001` | Product/privacy owner |

## Analysis scope and limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Only the three supplied repository facts were available for this focused refinement. | FK restriction, privacy retention statement, and background-worker statement supplied in the request. | Referential, retention, and asynchronous-flow impacts are verified from supplied evidence; field-level privacy behavior and worker retry details remain unverified. |

## Planning handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-002` | `INV-001`–`INV-003`, `IMP-001`–`IMP-004`, `DEC-001` | Field-level personal-data treatment and worker retry/idempotency details require validation; finance retention remains accepted until completion. | `AC-001`–`AC-004` | Superpowers planning handoff; stop before implementation work breakdown. |
