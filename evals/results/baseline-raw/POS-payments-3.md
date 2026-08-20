# POS payments — automatic retry requirements and impact

## Requirement

Retry every failed charge automatically, while ensuring that a retry can never
create a second capture for the same customer payment.

## Required behavior

- Generate one durable payment-attempt identity and reuse it as the
  `idempotency_key` for every network retry of that attempt.
- Persist the attempt and its idempotency key before sending the charge
  request. A process restart must resume the same attempt rather than create a
  new one.
- Treat provider timeouts as **unknown**, not as definitive failures. Because a
  provider may time out after capture, do not immediately issue a new charge.
  Reconcile the original attempt using the provider’s idempotency result,
  charge lookup, or webhook before deciding whether another attempt is needed.
- Retry only confirmed, retryable failures (for example transient transport,
  rate-limit, or provider-availability errors). Do not retry declines,
  validation errors, fraud blocks, or already-settled attempts.
- Use bounded retries with exponential backoff and jitter, and persist the
  next retry time, attempt count, and terminal reason. A retry worker must be
  safe to run more than once concurrently.
- Mark an attempt as `pending/unknown`, `succeeded`, `failed`, or
  `requires_action`; do not collapse these states into a generic failure.

## Payment-state and UI impact

Payment status is currently rendered before webhook settlement, so the UI must
support an intermediate `processing` state. It should not display a final
failure while an automatic retry or timeout reconciliation is outstanding.
Webhook handling must be idempotent and authoritative: a late success webhook
must settle the original attempt and stop queued retries, even if the customer
has already been shown `processing`.

If the UI exposes retry progress, show the number of retries only as an
operational detail; never ask the customer to submit the payment again while
the original attempt is unresolved. Provide a clear terminal error and a
manual support/retry path when the retry budget is exhausted.

## Data and operational changes

- Store the payment-attempt id, idempotency key, provider charge/reference,
  status, retry count, last error classification, and next retry timestamp.
- Add an outbox/job record for retry and reconciliation work so webhook
  processing and retry scheduling are durable.
- Enforce uniqueness for the payment-attempt id/idempotency key and guard
  settlement with an atomic state transition.
- Emit structured logs and metrics for retries, unknown outcomes, reconciled
  captures, duplicate webhook deliveries, and terminal failures. Alert on
  unusual retry volume or prolonged unknown states.

## Acceptance criteria

1. A confirmed retryable failure is retried automatically with bounded,
   backoff-based scheduling.
2. A timeout after capture results in at most one capture: reconciliation or
   the provider’s idempotency behavior returns the original result, and no
   second charge is submitted.
3. Repeated worker execution, process restarts, and duplicate webhooks do not
   duplicate charges or settlements.
4. The UI shows `processing` until settlement is known and reflects a late
   webhook success correctly.
5. Non-retryable failures become terminal without automatic resubmission, and
   exhausted retries produce an actionable error.

## Main risks

The highest risk is treating a timeout as a failed capture and issuing a new
idempotency key, which can double-charge the customer. Other risks include
unbounded retry storms, stale pre-webhook status, and racing retry workers or
webhook handlers. These must be covered by fault-injection tests for timeout
before capture, timeout after capture, delayed/duplicate webhooks, restarts,
and concurrent workers.
