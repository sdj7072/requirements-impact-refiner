# API contract impact: rename `displayName` to `name`

## Decision

Make `name` the canonical public profile field. Treat `displayName` as a deprecated compatibility alias for one release/version, then remove it from the public contract.

## Required behavior

- New API responses and persisted profile JSON must write `name`.
- Request and response documentation, examples, generated models, and changelog entries must use `name` as the canonical field.
- During the deprecation window, readers must accept both `name` and legacy `displayName` so existing cached profiles and clients continue to work.
- If both fields are present, `name` wins. If only `displayName` is present, map it to `name` in memory and mark the data as legacy for migration/telemetry if such instrumentation exists.
- Writers must not emit both fields; emitting `displayName` should be limited to an explicitly documented legacy adapter, if one is required for an older server/client.

## Client and cache impact

`ios/UserDTO.swift` currently decodes `displayName`; update decoding to prefer `name` while retaining a one-version fallback for `displayName`. Update cache serialization and deserialization so newly saved profiles use `name`, while old cached JSON remains readable. A successful read of legacy JSON should either rewrite it in the new shape on the next save or be migrated in place without data loss.

## Compatibility and rollout

The rename is backward-compatible for one version through dual-read/single-write behavior. The public changelog must explicitly state that `displayName` is deprecated, identify the replacement (`name`), and state the removal version/date. Before removal, verify that supported clients, fixtures, cache data, analytics/telemetry payloads, and documentation no longer depend on `displayName`. After the deprecation window, reject or ignore the legacy key according to the API's established unknown-field policy and remove the fallback code.

## Acceptance criteria

1. A profile containing `name` decodes correctly on iOS and serializes with `name`.
2. A profile containing only legacy `displayName` still decodes to the same user-visible value during the compatibility version.
3. When both keys are present, `name` is authoritative.
4. Newly persisted cache JSON contains `name` and does not contain `displayName`.
5. Existing cached JSON containing `displayName` can be loaded and safely rewritten without loss.
6. Contract tests, fixtures, API examples, and changelog coverage document the one-version deprecation and the planned removal.

