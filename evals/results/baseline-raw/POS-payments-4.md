# POS Payments 4 — Requirements Impact Refinement

## Request

Retry every failed charge automatically.

## Refined requirement

When a charge attempt does not reach a confirmed provider outcome, the payment system must retry it automatically using the same logical payment attempt and a stable idempotency key. Retries must be bounded, observable, and safe when the provider may have captured the charge even though the client received a timeout. A payment must not be charged more than once.

“Failed” must be separated into at least these states:

- **Definitively declined/failed:** the provider has returned a terminal failure. Retry only when the provider’s error is explicitly retryable; do not retry permanent declines, invalid payment data, fraud blocks, or rejected authorization.
- **Unknown outcome:** the request timed out, the connection failed, or the provider returned an ambiguous error after capture may have occurred. Reconcile the original request before retrying. The system must not issue an unguarded second charge.
- **Confirmed success:** do not retry, even if the UI has not yet received or rendered webhook settlement.

## Required behavior

1. Create one payment/charge-attempt record with a stable idempotency key before sending the request. Reuse that key for every retry of the same logical charge.
2. Persist an intermediate state such as `pending`/`unknown` immediately when the request is sent. A client timeout must not be presented as a confirmed failure.
3. On timeout or other unknown result, query the provider by idempotency key or provider charge identifier and/or wait for webhook settlement. If the provider confirms success, finalize the payment exactly once. If it confirms a terminal failure, apply retry policy.
4. For retryable failures, retry in a background worker with exponential backoff and jitter. Suggested defaults are a small bounded number of attempts (for example, 3 retries) over a finite window (for example, 15 minutes), configurable by payment method/provider.
5. Enforce a unique logical-payment/idempotency-key constraint and make both charge submission and settlement handling idempotent. Concurrent workers, duplicate webhooks, and client resubmissions must converge on one payment result.
6. Stop retrying on confirmed success, a non-retryable error, expiry/cancellation, fraud/risk rejection, or exhaustion of the retry budget. Record the terminal reason and expose a recoverable/manual-review state for unresolved unknown outcomes.
7. Render status from the server-side payment state, not from the initial charge response alone. Until webhook or reconciliation confirms the result, show “processing” (or equivalent), not “failed” or “paid.”
8. Notify the client/UI after every state transition and provide a stable payment status endpoint. A refresh or repeated submit must return the existing attempt rather than create another charge.
9. Emit structured audit events and metrics for initial attempts, retries, reconciliation, successes, terminal failures, exhausted retries, duplicate suppression, and unknown outcomes. Alert on aged unknown payments and retry-worker failures.

## Acceptance criteria

- A retryable provider failure is retried automatically within the configured policy and eventually settles or terminates with a recorded reason.
- A permanent decline is not retried.
- If capture succeeds but the response times out, reconciliation/webhook processing marks the original payment successful and no second charge is created.
- Reusing the same idempotency key across retries produces at most one provider charge.
- Duplicate jobs, concurrent retries, duplicate webhooks, and repeated client requests are safe and converge to the same payment record.
- The UI shows processing while settlement is unknown and changes to paid/failed only after authoritative confirmation.
- Exhausted or unresolved attempts are visible to operations with enough identifiers to reconcile them safely.

## Impact and decisions to confirm

This changes the payment state machine, persistence model, background-job processing, provider adapter, webhook/reconciliation flow, UI status rendering, and operational monitoring. Product/engineering must confirm the retryable provider error taxonomy, maximum retry window and attempt count, behavior for unresolved unknown outcomes, whether automatic retries may occur after authorization expiry, and customer notification policy. “Retry every failed charge” should not mean blindly retrying every error: doing so can duplicate captures and can repeatedly submit invalid or fraudulent payments.
