# POS payments — requirements impact analysis

## Requirement

“Retry every failed charge automatically.”

## Interpretation and required refinement

This requirement is unsafe as written. A charge may be *confirmed failed*, or it may be *indeterminate* because the provider timed out after capture. Those cases must not be handled identically.

The system should automatically retry only charges whose failure is confirmed by the provider as retryable. A timeout or transport error after the capture request has been sent must be recorded as `unknown`/`pending_reconciliation`, not immediately retried. The original request must be resolved through the provider status API and/or webhook processing first. If the provider later confirms that the charge was not captured, the request may enter the retry flow.

## Idempotency and retry identity

Every capture attempt must use a stable idempotency key for the logical payment operation. A network retry of the same operation must reuse that key; generating a new key for each transport retry could create multiple captures when the first request actually succeeded. If a new payment attempt is intentionally created after a confirmed failure, it should have a distinct attempt key while retaining a common payment/order identifier for reconciliation and reporting.

The retry worker must be safe to run more than once. Persist the attempt state and idempotency key before dispatch, enforce uniqueness at the database/provider boundary, and make transitions idempotent when duplicate webhooks or duplicate worker deliveries occur.

## Status and webhook behavior

Payment status is currently rendered before webhook settlement. The UI and downstream consumers therefore need an explicit intermediate state (for example, `processing` or `awaiting_settlement`) rather than displaying a final failure while a capture may still settle. Webhooks are authoritative for settlement and must be able to move a payment from `processing` to `succeeded`, `failed`, or `requires_reconciliation`.

Webhook handling must be authenticated, deduplicated, and order-tolerant. A late success webhook after a timeout must suppress any pending retry. Conversely, a confirmed provider failure should enqueue a retry only once, subject to the retry policy.

## Retry policy to specify

The product requirement must define:

- Which provider error codes are retryable versus permanent (declined, invalid instrument, fraud/risk rejection, and cancelled orders should not be blindly retried).
- Maximum attempts and an overall time window.
- Backoff and jitter, plus rate/concurrency limits.
- Whether retries require a new payment instrument, customer consent, or merchant approval.
- What happens when all attempts are exhausted.
- Customer notifications, merchant/operator alerts, audit records, and reporting semantics.
- How an order is prevented from being fulfilled twice or left unpaid during reconciliation.

## Proposed acceptance criteria

1. A confirmed retryable failure is queued automatically with bounded exponential backoff and no more than the configured maximum attempts.
2. A confirmed permanent failure is not retried automatically and is surfaced with an actionable reason.
3. A provider timeout after capture never creates a new capture attempt until the original attempt is reconciled.
4. Repeating a worker delivery or capture request with the same idempotency key cannot produce more than one provider capture.
5. A success webhook received before or during retry processing marks the logical payment succeeded and cancels/suppresses queued retries.
6. Duplicate and out-of-order webhooks leave the final payment state correct and do not enqueue duplicate retries.
7. The UI shows the intermediate state and does not claim payment failure before webhook/status settlement is known.
8. Exhausted retries produce a durable audit trail, a clear final state, and the required customer/merchant notification.

## Impact

Implementing this safely requires changes to payment state modeling, capture-attempt persistence, idempotency-key handling, webhook reconciliation, retry scheduling, UI status rendering, observability, and tests. The requirement should be approved only after the retryable-error matrix, limits, and reconciliation behavior are explicitly agreed.
