# Requirement impact refinement: automatic retries for failed charges

## Raw request

> Retry every failed charge automatically.

## Refined requirement

Automatically retry a charge only when the payment attempt is known to be safely retryable. Every retry must reuse a stable idempotency key for the logical charge (or a provider-supported equivalent) so that a provider timeout after capture cannot create a second charge. Retries must be bounded, observable, and reconciled with webhook settlement before the payment is presented as failed or retried.

## Why the raw wording is unsafe

“Failed” is ambiguous. A client-visible timeout or transport error can occur after the provider has captured the payment, and the payment status is rendered before webhook settlement. Retrying immediately with a new key could double-charge the customer; rendering a definitive failure before settlement could also trigger an unsafe retry or duplicate fulfillment.

## Required behavior

1. Create one logical payment attempt with a stable idempotency key and persist its state before issuing the provider request.
2. On a definitive provider decline, mark the attempt failed and apply the configured retry policy only for explicitly retryable decline/error codes. Do not retry permanent declines (for example, invalid payment details, fraud, or customer cancellation).
3. On timeout, connection failure, or an unknown provider response, mark the attempt as `pending_confirmation` and reconcile through the provider status API and/or webhook. Retry with the same idempotency key only where the provider guarantees safe replay; otherwise wait for reconciliation rather than issuing a new capture.
4. Treat webhook settlement as authoritative for final success/failure. Make webhook handling idempotent and safe for duplicate or out-of-order deliveries.
5. Enforce bounded retries with configurable maximum attempts and backoff (including jitter), and stop after the retry window expires. Surface a recoverable/manual-review state when the final outcome remains unknown.
6. Render an intermediate pending state while settlement is unknown; do not show a final failure or initiate a new logical charge solely because the webhook has not arrived.
7. Fulfill the order exactly once after confirmed settlement, regardless of repeated provider responses, retries, or webhooks.
8. Record attempt IDs, idempotency keys, provider response/error classes, retry count, timestamps, and final settlement outcome for support and auditability. Emit metrics and alerts for repeated unknown outcomes and exhausted retries.

## Acceptance criteria

- A provider timeout after capture never results in two captures for one logical charge.
- A retryable, definitively failed attempt retries according to the configured limit and backoff; a permanent decline does not retry.
- Duplicate requests and duplicate webhooks converge on one payment and one fulfillment.
- The UI shows `pending`/`confirming` until settlement is known and never presents a timeout as a confirmed failure.
- Exhausted or unreconciled attempts are visible to operators with enough data to investigate.
- Automated tests cover timeout-after-capture, duplicate webhook, out-of-order webhook, retryable decline, permanent decline, and idempotency-key reuse scenarios.

## Open decisions to resolve before implementation

- Which provider response codes are retryable, and which status/reconciliation APIs are available?
- Does the provider guarantee idempotent replay after an unknown response, and for how long are keys retained?
- What maximum retry count, retry window, backoff, and customer-facing pending timeout are appropriate?
- What operator/manual-review workflow handles an outcome that remains unknown after reconciliation?
