# Requirements Impact Refinement: `displayName` → `name`

## Requirement revision

`REQ-001` — Rename the public profile field from `displayName` to `name`, while honoring the public API changelog’s one-version deprecation promise. During that compatibility window, existing clients and persisted profile data must remain readable; the next-version contract may remove the legacy field after the deprecation window has elapsed.

The compatibility behavior is part of the requirement, not an implementation detail: response compatibility, iOS decoding compatibility, and cached-profile compatibility must be addressed together.

## Current behavior and preserved invariants

`INV-001` — The iOS `UserDTO` currently decodes `displayName` and must continue to decode profiles during the promised one-version compatibility window. **Evidence:** verified, supplied repository fact `ios/UserDTO.swift`.

`INV-002` — Cached profile JSON currently persists the `displayName` key and must remain readable during the compatibility window. **Evidence:** verified, supplied repository fact “cached profile JSON persists `displayName`.”

`INV-003` — The public API currently has a documented one-version deprecation commitment for this rename. **Evidence:** verified, supplied repository fact “the public API changelog promises one-version deprecation.”

`INV-004` — Existing consumers outside the inspected iOS client may rely on `displayName`; their complete inventory and release cadence are not available in the supplied facts. **Evidence:** unknown; external consumer inventory and compatibility tests were not supplied.

## Impact ledger

| ID | Finding | Area | Evidence | State | Links |
|---|---|---|---|---|---|
| `IMP-001` | Removing `displayName` immediately would break the current iOS decoder. | Interfaces / Compatibility | **verified** — `ios/UserDTO.swift` decodes `displayName` | `mitigated` by `DEC-001` | affects `REQ-001`, `INV-001`; produces `AC-001` |
| `IMP-002` | A cache written with the legacy key could fail to hydrate after a write/read migration that only understands `name`. | Data / Compatibility | **verified** — cached profile JSON persists `displayName` | `mitigated` by `DEC-001` | affects `REQ-001`, `INV-002`; produces `AC-002` |
| `IMP-003` | Existing external API consumers may still decode `displayName` during the deprecation version. | Interfaces / Compatibility | **inferred** — public API changelog promises one-version deprecation; external consumer inventory unavailable | `accepted` by `DEC-001` | affects `REQ-001`, `INV-003`; produces `AC-003` |
| `IMP-004` | The response shape and precedence when both `name` and deprecated `displayName` are present are unspecified. | Interfaces | **unknown** — no supplied API schema or compatibility fixture | `deferred` | affects `REQ-001`; produces `AC-004` |
| `IMP-005` | Whether all persisted cache versions can be migrated, including offline/stale data, is not established. | Data / Operations | **unknown** — no migration code, fixture set, or cache-version policy supplied | `blocked` pending cache-version evidence | affects `REQ-001`, `INV-002`; produces `AC-005` |
| `IMP-006` | Existing regression coverage for old and new field names is not established. | Regression | **unknown** — no test inventory or compatibility tests supplied | `blocked` pending test inventory | affects `REQ-001`, `INV-001`, `INV-002`; produces `AC-006` |

## Focused decision

The supplied changelog commitment resolves the key policy choice: should the old field be removed immediately or retained for one compatibility version? The selected refinement is to retain compatibility for exactly one version, then remove the legacy contract in the following version. This is recorded below so the risk is not silently treated as resolved.

## Recorded decision

`DEC-001` — For one public API version, publish/read `name` as the canonical field and retain `displayName` as a deprecated compatibility field. Existing iOS decoding and cached JSON must continue to read `displayName`; writers should establish `name` as canonical while preserving a deliberate legacy-read path. At the end of that one-version window, removal of `displayName` is allowed only as a separately versioned contract change with consumer and cache evidence.

This decision **mitigates** `IMP-001` and `IMP-002`, and **accepts** the residual external-consumer risk in `IMP-003` for the documented deprecation window. It does not resolve the unspecified response precedence, cache-version coverage, or test-coverage gaps.

## Whole-set recalculation

After `DEC-001`, the complete impact set is:

- `IMP-001` — **mitigated**: iOS legacy reads remain required through the compatibility window. Evidence still points to `ios/UserDTO.swift`; `AC-001` verifies it.
- `IMP-002` — **mitigated**: cached legacy JSON remains readable during the compatibility window. `AC-002` verifies it.
- `IMP-003` — **accepted**: external consumers may depend on `displayName`; the one-version promise is the explicit acceptance boundary. Linked decision: `DEC-001`; `AC-003` verifies the boundary.
- `IMP-004` — **deferred**: canonical response shape and dual-field precedence require API schema/fixture confirmation before implementation planning. `AC-004` remains required.
- `IMP-005` — **blocked**: cache migration safety cannot be assessed without cache-version/migration evidence. Named gap: cache schema/version policy and stale/offline fixtures. `AC-005` remains required.
- `IMP-006` — **blocked**: regression confidence cannot be assessed without the test inventory. Named gap: iOS decoding, cache hydration, API compatibility, and downgrade/upgrade test coverage. `AC-006` remains required.

### Delta

| Category | Impacts |
|---|---|
| Mitigated | `IMP-001`, `IMP-002` |
| Accepted | `IMP-003` via `DEC-001` |
| Deferred | `IMP-004` |
| Blocked | `IMP-005`, `IMP-006` |
| Resolved | None; compatibility risks are reduced but require evidence |
| New | None |

## Acceptance and regression criteria

`AC-001` — During the one-version window, an iOS payload containing only `displayName` still decodes successfully; a payload containing canonical `name` also decodes successfully. **Produced by:** `IMP-001`.

`AC-002` — Cached profile JSON written before the rename and containing `displayName` hydrates successfully after the change; newly written cache data uses the canonical `name` representation or an explicitly documented dual-write form. **Produced by:** `IMP-002`.

`AC-003` — The public API contract/changelog marks `displayName` deprecated for exactly one version, documents `name` as canonical, and does not remove legacy reads before that version ends. **Produced by:** `IMP-003`.

`AC-004` — The API contract specifies whether both fields are returned during deprecation and defines deterministic precedence when their values differ. **Produced by:** `IMP-004`.

`AC-005` — Cache migration evidence demonstrates behavior for every supported persisted format, including stale/offline data, and documents the post-window removal behavior. **Produced by:** `IMP-005`.

`AC-006` — Automated or explicitly recorded validation covers legacy iOS decoding, new-field decoding, legacy cache hydration, new cache writes, API compatibility, and the post-deprecation removal boundary. **Produced by:** `IMP-006`.

## Stop check and planning handoff

The requirement is refined enough for a planning workflow, with the one-version compatibility boundary recorded in `DEC-001`. No implementation plan is created here. Planning must first resolve or explicitly carry forward the named gaps for API precedence (`IMP-004`), cache-version/migration evidence (`IMP-005`), and regression coverage (`IMP-006`). The material accepted risk is `IMP-003`, bounded by `DEC-001` and `AC-003`.
