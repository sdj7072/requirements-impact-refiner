# API Contract Impact: Rename `displayName` to `name`

## Decision

Rename the public profile field from `displayName` to `name`.

## Contract changes

- New canonical field: `name`.
- `displayName` is deprecated for one release/version, as promised by the public API changelog.
- The deprecation window applies to both request and response representations where the profile contract is exposed.
- Documentation, generated examples, schemas, and client-facing changelog text must identify `name` as canonical and `displayName` as deprecated.

## Compatibility behavior

During the one-version deprecation window:

1. Responses should emit `name` as the canonical property.
2. Clients sending `displayName` should continue to be accepted, with its value mapped to `name` when `name` is absent.
3. If both properties are supplied, `name` takes precedence; the conflicting legacy value should not overwrite it.
4. If compatibility telemetry or warnings exist, usage of `displayName` should be recorded and/or surfaced as a deprecation warning without breaking the request.
5. After the promised version, remove legacy acceptance and any compatibility-only serialization or decoding paths according to the versioning policy.

## Known implementation surfaces

- `ios/UserDTO.swift` currently decodes `displayName`; it must decode `name` and retain a one-version fallback for `displayName`.
- Cached profile JSON currently persists `displayName`; readers must migrate or read both keys, while writers should persist `name` as the canonical key.
- Existing cached data must remain readable across upgrade. A successful read of legacy data should normalize it to the new in-memory model and, where safe, rewrite the cache using `name`.

## Acceptance criteria

- A profile containing only `name` decodes and round-trips correctly.
- A legacy profile containing only `displayName` remains readable during the deprecation version and normalizes to `name`.
- When both keys are present, `name` wins deterministically.
- Newly written API payloads and cached JSON use `name`.
- No caller-facing contract documentation presents `displayName` as current.
- The changelog explicitly states the one-version deprecation and the removal version/condition.
- Tests cover new-key decoding, legacy fallback, precedence, cache migration, and post-deprecation removal behavior.

## Risk and rollout notes

The primary compatibility risk is data already stored on devices and clients that have not upgraded together. Keep the fallback reader for exactly the published deprecation window, avoid silently emitting both keys unless required by an interoperability contract, and coordinate removal with the next breaking-version release.
