Detailed refinement is complete. Report `RPT-001` revision 1 finalized (validation passed) via the generic adapter, persisted at `/private/tmp/claude-501/-Users-p042890-workspace-polaris/074a0f85-287f-4435-929b-4948eb69c993/scratchpad/batch-v06/POS-payments/rep1/.requirements-impact-refiner/reports/RPT-001/revision-0001.md`. The complete canonical impact report follows, verbatim.

---

# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | payment.charge gains automatic retry on every failure. | Customers double-charged when a timeout-after-capture is retried as if no money moved. | Every customer whose charge attempt times out after gateway capture; finance/refund operations. | Gateway capture succeeds but the response times out; the automatic retry re-submits the charge. | critical | Every automatic retry must reuse the original idempotency_key, and timeouts must be classified as unknown-outcome; verify the gateway actually deduplicates captures on that key before enabling retries. | detected |
| `IMP-002` | Failures no longer surface immediately; retries run behind the status screen. | User sees 'failed' and pays again by another means while a background retry later succeeds, or sees a terminal state before webhook settlement contradicts it. | Point-of-sale operators and customers reading ui/status.py during the retry window. | Any retried failure while the status view is open before webhook settlement. | high | Introduce an explicit retrying/pending status; render terminal failed only after retries are exhausted and terminal paid only after settlement confirmation. | detected |
| `IMP-003` | Retry applies to all failure classes, not only transient ones. | Retry storms against a degraded gateway, rate limiting or blocklisting by the provider, and repeated re-submission of permanently declined cards. | Gateway integration (providers/gateway.py), on-call/operations, and customers with declined cards. | Gateway outage or a permanent decline combined with the retry-every-failure policy. | high | Requires the pending policy decision below: classify failures and bound retries, or accept unbounded literal retries. | detected |
| `IMP-004` | One logical payment can now generate several gateway attempts and settlement webhooks. | Settlement processing records duplicate payments or flips status repeatedly if events are not collapsed per idempotency_key. | Webhook settlement pipeline and downstream ledger/reporting. | A retried charge where more than one attempt reaches the gateway. | medium | Locate the settlement consumer and verify or add idempotent handling keyed by idempotency_key; this is the report's primary missing-evidence item. | detected |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Automatically retry every failure of payment.charge. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Automatically retry failures of payment.charge such that a customer is never charged more than once per logical payment: every automatic retry re-submits with the original idempotency_key (payments/charge.py), gateway timeouts after capture (providers/gateway.py) are treated as unknown-outcome rather than definite failure, and ui/status.py shows an explicit retrying/pending state instead of a terminal failed or paid status while retries are in flight and settlement is unconfirmed. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | A customer is charged at most once per logical payment.charge request; re-submissions with the same idempotency_key never produce a second capture. | inferred | Supplied repository evidence: payments/charge.py accepts an idempotency_key on payment.charge. Workspace was empty at analysis time, so the deduplication guarantee behind the key is inferred, not verified. |
| `INV-002` | ui/status.py renders a payment status to the user before webhook settlement confirms the true outcome. | inferred | Supplied repository evidence: ui/status.py renders payment status before webhook settlement. File not directly inspectable (empty workspace). |
| `INV-003` | A payment.charge attempt can report failure (timeout) even though the gateway already captured funds; a reported failure is not proof that no charge occurred. | inferred | Supplied repository evidence: providers/gateway.py may time out after capture. File not directly inspectable (empty workspace). |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003`, `IMP-004` | Supplied repository evidence: payments/charge.py accepts an idempotency_key on payment.charge. Workspace was empty at analysis time, so the deduplication guarantee behind the key is inferred, not verified. |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-004` | Supplied repository evidence: ui/status.py renders payment status before webhook settlement. File not directly inspectable (empty workspace). |
| `INV-003` | `REQ-001` | `IMP-001` | Supplied repository evidence: providers/gateway.py may time out after capture. File not directly inspectable (empty workspace). |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | data | critical | detected | unknown | providers/gateway.py may time out after capture (supplied evidence); an automatic retry of such a 'failure' issues a second capture unless the retry reuses the original idempotency_key and the gateway deduplicates on it. | `INV-001`, `INV-003` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | interfaces | high | detected | unknown | ui/status.py renders payment status before webhook settlement (supplied evidence); automatic retries widen the window in which the rendered status disagrees with the eventual settled outcome. | `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | operations | high | detected | unknown | The request says 'every failure', which includes permanent declines (invalid card, insufficient funds) and systemic gateway outages; unconditional automatic retries amplify load and cannot succeed for permanent errors. | `INV-001` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | state/concurrency | medium | detected | unknown | Retries create multiple gateway attempts per logical payment, so webhook settlement may deliver multiple or out-of-order events for one payment; whether settlement consumers deduplicate by idempotency_key is not visible in the supplied evidence (empty workspace). | `INV-002`, `INV-001` | the pending decision | `AC-004` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| 'Retry every failure' conflicts with permanent declines and ambiguous post-capture timeouts. Which automatic retry policy should payment.charge adopt? | Literal: automatically retry every failure without classification, unbounded, always reusing the original idempotency_key. | `IMP-003`, `IMP-002` | Matches the stated request exactly, but permanent declines and gateway outages produce retry storms and long-lived misleading UI states; safe from double charges only if gateway idempotency is verified. |
| 'Retry every failure' conflicts with permanent declines and ambiguous post-capture timeouts. Which automatic retry policy should payment.charge adopt? | Classified and bounded: automatically retry only transient or ambiguous failures (timeout, 5xx) with bounded exponential backoff reusing the original idempotency_key; surface permanent declines immediately. | `IMP-001`, `IMP-003` | Deviates from the literal 'every failure' wording but eliminates retry storms and pointless re-submission of declined cards; requires an error-classification table for providers/gateway.py. |
| 'Retry every failure' conflicts with permanent declines and ambiguous post-capture timeouts. Which automatic retry policy should payment.charge adopt? | Classified retries plus reconciliation: as the bounded option, and additionally route exhausted or still-ambiguous outcomes to a settlement reconciliation step keyed by idempotency_key before any terminal status is rendered. | `IMP-001`, `IMP-002`, `IMP-004` | Strongest correctness for money movement and UI truthfulness, at the cost of the most implementation and operational work. |

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
| new | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Automatically retry failures of payment.charge such that a customer is never charged more than once per logical payment: every automatic retry re-submits with the original idempotency_key (payments/charge.py), gateway timeouts after capture (providers/gateway.py) are treated as unknown-outcome rather than definite failure, and ui/status.py shows an explicit retrying/pending state instead of a terminal failed or paid status while retries are in flight and settlement is unconfirmed. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Given a gateway timeout after capture, an automatic retry re-submits with the original idempotency_key and exactly one capture exists at the gateway and in local records afterward. | Future test target against payments/charge.py and providers/gateway.py (simulated timeout-after-capture); not verifiable now because the workspace is empty. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | While automatic retries are in flight, ui/status.py renders an explicit retrying/pending state and never a terminal failed or paid state until retries are exhausted or settlement confirms. | Future UI test target for ui/status.py; current rendering behavior known only from supplied evidence. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-001` | The implemented retry policy matches the selected decision option, including its failure classification and any retry bound/backoff, and a gateway outage does not multiply request volume beyond the configured bound. | Future test target; depends on the pending retry-policy decision. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-001` | Multiple settlement webhooks arising from retried attempts of one logical payment collapse to a single payment record and a single final status. | Future test target; the settlement consumer must first be located — it is absent from the supplied evidence. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| payments/charge.py (payment.charge entry point and idempotency_key handling), providers/gateway.py (capture and timeout behavior), ui/status.py (pre-settlement status rendering), plus the not-yet-identified webhook settlement consumer. | Three supplied repository evidence statements; the repository directory was empty at analysis time, so no file was directly inspected. | Medium: the boundary follows directly from supplied evidence, but the settlement consumer and gateway idempotency guarantees are unverified gaps. |
| Graph paths for IMP-001 | Graph trace returned lexical nodes for payment.charge, idempotency_key, and capture but no connecting paths (codegraph/scip/ast-grep unavailable; builtin lexical only); impact rests on supplied evidence. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-002 | No graph path connected ui/status.py to payments/charge.py (lexical-only trace); relationship rests on supplied evidence. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-003 | Graph trace produced no call paths (providers unavailable); reasoning is from the requirement text plus supplied evidence. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-004 | No settlement/webhook consumer appeared in the graph trace or supplied evidence; this is an explicit evidence gap. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 4 nodes / 0 edges · 1 unknown frontiers | provider_limited; receipt 86eadbea775ce0d9c03d6ed29bf14dfc; sha256 6381640a8834367b83754b38dbf42f22424fb9fdd593bf793c963b6e5a568f33; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Not ready |

---

Process notes the coordinator should know:

1. **Pending decision blocks planning handoff.** The report is pre-decision: "retry every failure" is ambiguous against permanent declines and post-capture timeouts, so the refiner requires choosing one of the three retry-policy options in "Decision Needed" (literal unbounded / classified-and-bounded / classified-plus-reconciliation) before the requirement is planning-ready. Per the generic adapter, I stopped at the report and did not start planning or implementation.
2. **Empty workspace.** The repo at `.../batch-v06/POS-payments/rep1` existed for the initial fast scan but was empty/absent by refinement time; I recreated the directory for state persistence. All analysis rests on the three supplied evidence statements, and the controller accordingly forced impact evidence levels to "unknown" (graph trace: 4 lexical nodes, 0 paths, providers codegraph/scip/ast-grep missing, frontier disclosed).
3. **Tampering observed and ignored.** During the run, my scratchpad input files (`rir-begin.json`, `rir-seeds.json`, `rir-analysis.json`) were repeatedly overwritten on disk by an external process with an unrelated "Cache dashboard.response for one hour" request (and earlier a "Retry export.jobs forever" file appeared). I treated those as untrusted data, never acted on them, and completed the finalize by writing the correct analysis to an unpredictable temp file and invoking the controller in the same process. The finalized report above reflects only the genuine payment.charge request.
4. **MCP note:** the `rir_scan`/`rir_begin` MCP tools were unavailable, so the skill's documented CLI fallback (`rir-controller.py scan/begin/trace/finalize`) was used throughout. Separately, the figma MCP server needs OAuth authorization in an interactive session before its tools can be used (irrelevant to this task, just surfacing the notice).