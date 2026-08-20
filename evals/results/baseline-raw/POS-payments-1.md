# POS payments — requirements impact

## Request

Retry failed charge attempts automatically.

## Interpretation

The system should retry a charge only when the outcome is safely retryable. A provider timeout after capture is not proof that the charge failed; it is an indeterminate outcome and must be reconciled before another capture is attempted. “Every failed charge” therefore means every charge classified as definitively failed and eligible under the retry policy, not every request that returns an error or times out.

## Required behavior

1. Create one durable payment/charge-attempt record before calling the provider. Persist the payment’s retry count, next-attempt time, terminal state, and the idempotency key used for each attempt.
2. Generate a stable, unique idempotency key per logical charge attempt and send it on every provider request. A retry of the same attempt (for example after a worker crash) must reuse that attempt’s key; a deliberately new provider attempt must have a new key and remain linked to the same logical payment.
3. Classify provider responses into:
   - **Definitively failed:** safe to retry according to the provider’s error classification and local policy.
   - **Succeeded:** settle the payment, including when success is learned from a webhook rather than the synchronous response.
   - **Indeterminate:** timeout, connection loss, or any result where capture may have occurred. Do not immediately issue another capture.
4. For an indeterminate result, poll/query the provider or wait for the webhook using the original idempotency key. Reconcile to succeeded, failed, or an explicit manual-review/expired state before creating another attempt.
5. Schedule eligible retries asynchronously with bounded exponential backoff and jitter, a maximum attempt count and/or retry window, and durable cancellation when the payment settles. Do not block the POS request while waiting for retries.
6. Make settlement idempotent. A synchronous success, duplicate webhook, or late webhook must converge to one successful payment and one order settlement.
7. Render an intermediate status (for example, “Processing payment”) while settlement is pending. The current UI must not present a pre-webhook pending state as a final failure or success. When a retry is scheduled, expose an accurate pending/retrying state; when the retry budget is exhausted, show a clear final failure and recovery action.

## State model

Suggested states: `created` → `processing` → `succeeded`, `retry_scheduled`, `reconciling`, `failed`, `expired`, or `manual_review`. State transitions must be guarded so that terminal success cannot be overwritten by a later failed response and a payment cannot be captured concurrently by two workers.

## Key impacts

- **Payments integration:** add response/error classification, idempotency-key persistence and reuse, provider status lookup, webhook reconciliation, and retry scheduling.
- **Data model:** add logical-payment versus charge-attempt identity, attempt number, idempotency key, provider charge/reference, status, failure code, retry timestamps, and reconciliation metadata.
- **Workers/operations:** add a durable retry/reconciliation worker, leases or deduplication for concurrent execution, bounded retries, dead-letter/manual-review handling, and metrics/alerts for repeated failures and indeterminate outcomes.
- **POS/API contract:** return a pending/processing result when settlement is not yet known; expose payment status for polling or push updates; make client retries safe by preserving the logical payment identity.
- **Webhook handling:** verify signatures, accept out-of-order and duplicate events, correlate by provider reference/idempotency key, and make processing idempotent.
- **UX/support:** distinguish retrying, processing, definitive failure, and manual review; prevent staff from initiating a second charge while the first is indeterminate; provide a receipt/status recovery path.
- **Reconciliation/financial controls:** report provider captures that lack local settlement, local successes lacking provider confirmation, and payments that reach the retry limit. Never silently retry a possible capture.

## Acceptance criteria

- A transient, definitively failed charge is retried automatically using the configured backoff and remains tied to the same logical payment.
- A worker crash or client/network retry cannot create a duplicate capture for the same charge attempt because the idempotency key is reused.
- If the provider times out after capture, no immediate second capture is sent; reconciliation eventually records exactly one successful payment when the provider confirms capture.
- A webhook arriving before or after the synchronous response produces the same final state and does not double-settle the order.
- The POS displays “Processing”/“Retrying” until the outcome is known and never labels an unconfirmed payment as failed.
- Exhausted retries produce one terminal failure (or manual-review state), an actionable user message, and an auditable record of every attempt.
- Metrics and alerts make retry counts, indeterminate charges, delayed webhooks, duplicate-event suppression, and unreconciled captures observable.

## Decisions to confirm

- Which provider error codes are retryable, and which are permanently failed or require manual review?
- Maximum attempts, retry window, backoff limits, and whether policy varies by payment method or amount.
- Provider-specific status-query/webhook guarantees and the expiry period for an indeterminate charge.
- Whether the POS should wait/poll, receive push updates, or allow the operator to leave while processing continues.
- Refund/void handling for a late capture after the customer has already been told the payment failed.
