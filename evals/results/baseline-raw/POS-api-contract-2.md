# API contract impact: rename `displayName` to `name`

## Decision

Rename the profile field exposed by the public API from `displayName` to `name`. Treat `name` as the canonical field for all newly written and newly documented contracts.

## Compatibility and rollout

The public API changelog already promises a one-version deprecation window. During that version, responses should expose `name` and may continue exposing `displayName` as a deprecated compatibility alias, while requests should accept `name` as the preferred input. If request compatibility is required, continue accepting `displayName` for the same window and define deterministic precedence when both fields are supplied: `name` wins. Remove the alias and legacy request support in the next version, following the published deprecation notice.

The changelog, API schema, examples, generated client models, and release notes must all describe the one-version timeline and the eventual removal. Avoid silently changing the meaning of either field; this is a wire-name migration only.

## Required implementation impact

- Update `ios/UserDTO.swift` so decoding reads the canonical `name` key. For the deprecation version, decode `name` first and fall back to `displayName` when `name` is absent; encode `name` as the canonical key.
- Update cached profile JSON handling so new cache entries persist `name`. Read existing cache entries containing `displayName` during the compatibility window, migrate them in memory, and rewrite them using `name` when the cache is next saved. A cache miss or malformed legacy value must not overwrite a valid profile.
- Update API serializers, request/response schemas, fixtures, mocks, documentation, examples, analytics/event payloads, and any generated clients that reference `displayName`.
- Add a deprecation annotation or equivalent contract metadata for `displayName`, with removal scheduled for the next API version.

## Acceptance criteria

1. A response containing `name` decodes correctly on iOS and is written to cache under `name`.
2. A legacy response or cache entry containing only `displayName` remains readable for one API version and is normalized to `name` on write.
3. When both keys are present, `name` is selected consistently.
4. Newly generated requests, responses, schemas, fixtures, and documentation use `name`; no new producer emits `displayName` except an explicitly documented compatibility layer.
5. The changelog states that `displayName` is deprecated for one version and identifies the version in which it will be removed.
6. Tests cover canonical decoding/encoding, legacy fallback, dual-key precedence, cache migration, and post-deprecation rejection or absence of `displayName`.

## Risks and mitigations

The main risks are breaking older cached profiles and creating inconsistent behavior when both keys are supplied. Preserve read compatibility for exactly one version, make precedence explicit, and test cache migration and round trips. Monitor deserialization failures and usage of the deprecated key so removal is evidence-based at the end of the window.
