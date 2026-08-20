# API Contract Impact: Rename `displayName` to `name`

## Scope

The public profile field is renamed from `displayName` to `name`. This is an API-contract change with client decoding, cached profile persistence, and a one-version deprecation period.

## Required behavior

- New API responses and requests use `name` as the canonical field.
- `ios/UserDTO.swift` must decode `name` into the existing user-name property. During the deprecation window, decoding should accept legacy `displayName` as a compatibility fallback if the server can still return it; when both are present, `name` takes precedence.
- Cached profile JSON must be written using `name`. Existing cached records containing `displayName` must remain readable during the deprecation version and should be migrated or normalized to `name` when loaded and saved.
- The public API changelog must document `displayName` as deprecated for one version, identify `name` as the replacement, and state the removal/version boundary. After that boundary, legacy `displayName` compatibility may be removed.

## Compatibility and rollout

This should be treated as a staged contract migration: introduce and document `name`, support reads of the legacy key for one version, update all writers and examples to emit `name`, then remove the fallback after the promised deprecation period. Avoid emitting both keys by default unless explicitly required for an older consumer, because dual writes can hide migration gaps and create conflicting values.

## Acceptance criteria

1. A payload containing only `name` decodes correctly in `UserDTO`.
2. A legacy payload containing only `displayName` remains readable for the deprecation version.
3. A payload containing both keys resolves to `name`.
4. Newly persisted profile JSON contains `name`, not `displayName`.
5. Existing cached JSON with `displayName` can be loaded without data loss and is normalized on the next persistence operation.
6. The changelog states the one-version deprecation and the planned removal point.
7. Tests cover canonical decoding, legacy fallback, precedence, cache migration, and the post-deprecation removal behavior.

## Risks

The main risks are silent loss of names when old cache data is decoded with a strict new schema, inconsistent precedence when both keys exist, and breaking clients that rely on the old public contract before the promised version elapses. The compatibility fallback and explicit changelog boundary should be removed together only after the deprecation version is complete.
