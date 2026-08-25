Fast Scan result (verbatim):

> Fast impact scan needs more input. Candidate boundaries: no repository-backed candidate. Coverage: needs_input; 3609 ms; cache hit.

**What this means, and what I verified**

The scan found no repository-backed seed for this change, and a direct check confirms why: the polaris repo contains no charge, payment, webhook, or capture code at all. The only related hit is `/Users/p042890/workspace/polaris/submission/1_기획서/09_ERD_데이터모델.md` (line 641), which describes idempotency keys for **policy change items and a Mock Adapter** — not payment charges. So the three supplied evidence bullets (charge requests accept an `idempotency_key`, payment status rendered before webhook settlement, provider may time out after capture) do not correspond to anything in this repository.

**Blocked pending one concrete boundary.** Before any planning or implementation of "retry every failed charge automatically," I need one of:

1. The actual repo/service where the charge code lives (this may be the wrong repository), or
2. A concrete file/module path in polaris that should be treated as the payment boundary, or
3. Confirmation that this is a not-yet-built feature, in which case it needs requirements work, not a retry patch.

**Why the evidence itself argues against blanket auto-retry** (worth surfacing regardless of repo): with a provider that can time out **after capture**, a "failed" charge may actually have succeeded — retrying "every failed charge" without reusing the same `idempotency_key` per logical charge (and without reconciling against webhook settlement, which the UI already races ahead of) is a double-charge generator. Any refined requirement should distinguish (a) definitively-failed charges (safe to retry with a fresh key), (b) ambiguous outcomes like timeouts post-capture (retry only with the same idempotency key, or reconcile first), and (c) non-retryable failures (hard declines, invalid card). No code was changed.
