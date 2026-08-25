Renamed `profile.displayName` to `profile.name` in the public API, honoring the repo's one-version deprecation promise rather than doing a hard break.

What was done, and why not a hard rename:

- **/private/tmp/claude-501/-Users-p042890-workspace-polaris/074a0f85-287f-4435-929b-4948eb69c993/scratchpad/batch-v06/POS-api-contract/rep1/api/profile.py** — `PROFILE_FIELD` is now `"profile.name"`; added `PROFILE_FIELD_DEPRECATED = "profile.displayName"` so the old field stays published as a deprecated alias for one version.
- **.../rep1/mobile/profile_decoder.py** — decoder now targets `"profile.name"` with `DECODES_FALLBACK = "profile.displayName"`. The fallback is required because `IOS_TARGET = "ios-release-decoder"` means shipped clients update slowly, and `profile.cache.payload` cached payloads still carry the old shape.
- **.../rep1/docs/changelog.py** — changelog now records the rename: `FIELD = "profile.name"`, with `DEPRECATED_FIELD = "profile.displayName"` noted as published for one more version then removed, consistent with the existing `"one-version deprecation"` policy.

Key finding: the repository's own evidence (shipped iOS decoder, cached payload shape, one-version deprecation policy) made an immediate hard rename a contract violation — the dual-publish alias for one release cycle is the compliant way to execute this rename. Removal of the alias should happen in the release after next.