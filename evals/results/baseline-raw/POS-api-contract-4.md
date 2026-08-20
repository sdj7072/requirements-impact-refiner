# API contract impact: rename `displayName` to `name`

## Decision

The canonical profile field is renamed from `displayName` to `name`. New API responses and request examples must use `name`. The old `displayName` field remains accepted and/or emitted only for the one-version deprecation window promised by the public API changelog; its removal must be called out as a breaking change in the next version transition.

The rename is a contract change, not merely an iOS model-property rename. The iOS DTO decoder and cached profile JSON are both compatibility boundaries and must participate in the transition.

## Affected contract surfaces

- **Wire representation:** Replace `displayName` with `name` in profile payloads, schemas, fixtures, examples, and generated API documentation.
- **iOS client:** Update `ios/UserDTO.swift` so the public/current model reads `name`. During the deprecation window, decoding must remain tolerant of legacy payloads containing only `displayName`; if both keys are present, `name` is authoritative.
- **Cached profile JSON:** Existing on-device/cache entries may contain `displayName`. Cache reads must migrate or normalize that value to `name` without forcing logout or profile loss. Cache writes should use the canonical `name` key. A read-after-migrate/write-back is preferred so legacy data does not persist indefinitely.
- **Changelog/versioning:** Preserve the announced one-version deprecation period. Document the accepted legacy key, the canonical replacement, the version in which compatibility begins, and the first version in which `displayName` is removed.
- **Downstream consumers:** Update any serializers, deserializers, validation rules, analytics/event payloads, mocks, snapshots, and integrations that address the old key. Unknown-field handling must not make a legacy payload fail during the transition.

## Compatibility rules for the deprecation version

| Input/output condition | Required behavior |
| --- | --- |
| Payload contains `name` | Decode/use `name`. |
| Payload contains only `displayName` | Decode/use it as the legacy alias for `name`; do not lose the profile. |
| Payload contains both keys | Use `name`; ignore the legacy value for the effective profile name. If conflict telemetry exists, record it without exposing two competing values to callers. |
| Cache contains only `displayName` | Read it as `name`, normalize the in-memory model, and write canonical cache data on the next safe persistence opportunity. |
| Cache contains `name` | Read and write the canonical form. |
| New serialization | Emit `name`; do not create new `displayName` data. If server response compatibility requires dual emission, keep it explicitly version-gated and remove it with the deprecated contract. |
| Payload contains neither key | Preserve existing required/optional validation semantics; the rename must not silently turn a required profile name into an empty value. |

The precedence rule (`name` over `displayName`) must be consistent across server, iOS, and cache migration code.

## Required implementation behavior

1. Define `name` as the sole canonical application-level property.
2. Add a narrowly scoped legacy decoding/migration path for `displayName`; do not expose two mutable properties to consumers.
3. Ensure cached data written by the new version uses `name`, while old cached data remains readable for at least the announced deprecation version.
4. Avoid destructive cache invalidation, forced re-authentication, or profile reset solely because the key changed.
5. Update the API schema and generated/client-facing documentation so new consumers discover `name`, while the deprecated alias is visibly marked with its removal version.
6. Emit deprecation diagnostics where the legacy alias is actually observed, if the existing telemetry facility supports this. Diagnostics must not include sensitive profile contents.
7. At the end of the deprecation window, remove legacy output and legacy decoding only in the version identified by the changelog. Treat that removal as the documented breaking change.

## Acceptance criteria

- A current payload containing `name` decodes to the expected user name.
- A legacy payload containing only `displayName` still decodes during the deprecation version.
- A payload containing both keys deterministically selects `name`.
- A pre-upgrade cache containing `displayName` loads successfully, is represented as `name`, and is rewritten in canonical form without profile loss.
- Newly persisted profile JSON contains `name` rather than `displayName`.
- Tests cover the three wire-key cases, both cache-key cases, malformed/missing values according to existing validation rules, and migration idempotence.
- Public schema, examples, changelog, and release notes agree on the deprecation and removal versions.
- Tests for the removal version verify that `displayName` is no longer emitted or accepted, if that is the published end-state.

## Risks and rollout notes

The primary risks are data loss from a cache-only rename, inconsistent precedence when both keys are present, and consumers adopting the deprecated field because it remains visible. Keep the compatibility alias localized, make `name` the only documented default, and test upgrade/downgrade or mixed-version interactions where cached profiles can cross app versions.

The changelog should state the migration plainly: “`displayName` is deprecated; use `name`. It remains supported for one version and is removed in `<removal version>`.” The exact version identifiers must match the release plan rather than be inferred independently by each client.
