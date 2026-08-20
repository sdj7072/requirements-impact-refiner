# Requirements impact review: API field rename

## Requirement revision

**REQ-001 — Rename `displayName` to `name`.**

Public API payloads should use `name` as the canonical field. The existing `displayName` field must remain compatible for the one-version deprecation window promised by the public API changelog. The requirement is refined here as a compatibility-preserving API contract change; the exact response representation during the window remains a decision point.

## Current behavior and preserved invariants

- **INV-001 — Existing iOS payloads remain readable.** The iOS `UserDTO` currently decodes `displayName`; payloads using the legacy field must continue to decode during the promised compatibility window. **Evidence:** `ios/UserDTO.swift` (supplied repository fact; decoder reads `displayName`). **Level:** `verified`. **Must preserve:** `REQ-001`.
- **INV-002 — Cached profile JSON remains readable.** Already-persisted profile JSON may contain `displayName` and must not become unusable solely because the API field is renamed. **Evidence:** cached profile JSON persists `displayName` (supplied repository fact). **Level:** `verified`. **Must preserve:** `REQ-001`.
- **INV-003 — The published deprecation promise is honored.** The legacy field has a one-version compatibility window rather than an immediate removal. **Evidence:** public API changelog promise of one-version deprecation (supplied repository fact). **Level:** `verified`. **Must preserve:** `REQ-001`.

## Impact ledger

| ID | Impact | Category | Level | Evidence | State | Links / acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| IMP-001 | Removing `displayName` immediately breaks the known iOS decoder. | Interfaces / Regression | verified | `ios/UserDTO.swift` reads `displayName` (supplied repository fact) | refining | affects `REQ-001`, `INV-001`; produces `AC-001` |
| IMP-002 | Removing or rewriting the legacy key without a compatibility reader can make cached profile JSON unreadable. | Data / Compatibility | verified | Cached profile JSON persists `displayName` (supplied repository fact) | refining | affects `REQ-001`, `INV-002`; produces `AC-002` |
| IMP-003 | Immediate removal would violate the public API’s one-version deprecation promise. | Interfaces / Compatibility | verified | Public API changelog (supplied repository fact) | refining | affects `REQ-001`, `INV-003`; produces `AC-003` |
| IMP-004 | Other external or older-version consumers may decode `displayName`. | Interfaces / Compatibility | inferred | Public API contract and the known iOS consumer establish a consumer ecosystem, but no complete consumer inventory was supplied | detected | affects `REQ-001`; produces `AC-004` |
| IMP-005 | The supplied facts do not identify whether the API will dual-write both keys, alias reads, or expose only `name` while accepting the legacy key. | Interfaces / Operations | unknown | Wire-format and rollout details were not supplied | blocked | affects `REQ-001`; decision needed |

## Focused decision

**Decision needed:** During the one-version deprecation window, how should the public response handle the two names?

1. **Dual-write responses (recommended):** emit canonical `name` and legacy `displayName` with identical values; accept legacy input where applicable and document `displayName` as deprecated.
2. **Canonical-only responses with tolerant readers:** emit only `name`, while iOS and other clients accept both response keys; this requires coordinated client rollout before the server response changes.
3. **Compatibility alias at the contract boundary:** keep `displayName` as a documented response alias for one version, then remove it; define precedence and equality if both keys are present.

No `DEC-###` is recorded because no option was selected in the supplied request.

## Whole-set recalculation

No decision was supplied, so the complete delta remains:

- **Resolved:** none.
- **Mitigated:** `IMP-001`, `IMP-002`, and `IMP-003` are mitigated by the explicit one-version compatibility constraint, but not yet resolved because the wire/read policy is unspecified.
- **Unchanged:** `IMP-004` remains an inferred consumer-compatibility risk.
- **Accepted:** none; silence is not acceptance.
- **Deferred:** none.
- **Blocked:** `IMP-005` remains blocked pending the response/read policy and precedence behavior.
- **New:** none.

## Acceptance and regression criteria

- **AC-001:** During the deprecation version, an iOS payload containing legacy `displayName` decodes successfully, and a payload containing canonical `name` also decodes successfully.
- **AC-002:** Cached profile JSON containing `displayName` remains readable after the rename; newly written cache data follows the selected canonical policy.
- **AC-003:** Public API documentation/changelog identifies `name` as canonical, marks `displayName` deprecated, and does not remove the legacy behavior before one version has elapsed.
- **AC-004:** A compatibility test covers both field names and defines behavior when both are present, including deterministic precedence or equality validation.

## Stop check and planning handoff

The refined requirement, preserved invariants, evidence-backed impact ledger, open decision, and testable criteria are ready for the selected planning workflow. Implementation planning should wait for the response/read policy decision; the remaining external-consumer inventory is an explicitly documented uncertainty.
