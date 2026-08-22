# Impact Taxonomy

Use this checklist to choose inspection targets. It does not justify inventing impacts; record evidence level for every result.

## Functionality

Inspect entry points, user flows, handlers, feature flags, and domain services. Evidence includes route/controller symbols, workflow tests, and feature-flag configuration showing the current path.

## Data

Inspect models, migrations, foreign keys, serializers, retention rules, and background cleanup. Evidence includes schema objects, migration IDs, fixtures, and policy documents naming retention or integrity constraints.

## Interfaces

Inspect public and internal APIs, events, request/response DTOs, webhooks, client decoders, and generated contracts. Evidence includes OpenAPI fields, event schemas, consumer symbols, and compatibility tests.

## Authorization/Privacy

Inspect authentication middleware, role checks, permission defaults, audit trails, data classification, and consent/deletion paths. Evidence includes authorization functions, role tables, audit-event tests, and privacy-policy clauses.

## State/Concurrency

Inspect state machines, transactions, locks, queues, retries, idempotency keys, ordering guarantees, and timeout recovery. Evidence includes transaction boundaries, job handlers, idempotency fields, queue configuration, and race-condition tests.

## Operations

Inspect deployment configuration, feature rollout, metrics, logs, alerts, runbooks, backup/restore, and rollback paths. Evidence includes deployment manifests, dashboards-as-code, alert rules, runbook IDs, and release checks.

## Compatibility

Inspect versioning promises, legacy readers/writers, persisted payloads, client release support, migrations, and downgrade behavior. Evidence includes changelog commitments, compatibility adapters, snapshot fixtures, and old-version tests.

## Legal/Policy

Inspect repository-visible licenses, retention schedules, access policies, regional rules, and approval records. Evidence includes policy section IDs, legal requirements, data inventories, and consent records; mark outside evidence unknown.

## Regression

Inspect tests covering preserved invariants, adjacent flows, fixtures, smoke checks, and explicit gaps. Evidence includes test names, assertions, coverage configuration, and `AC-###`; unavailable tests are a validation gap, never proof of coverage.
