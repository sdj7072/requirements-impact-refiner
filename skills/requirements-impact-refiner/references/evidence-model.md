# Evidence Model

## Identifiers and relationships

| ID | Entity | Required relationships |
| --- | --- | --- |
| `RPT-###` | Stable report lineage | preserves its ID across revisions; points to the exact predecessor SHA-256 |
| `REQ-###` | Original or revised requirement | `refined-by` `DEC-###`; affected by `IMP-###` |
| `INV-###` | Current behavior to preserve | `must-preserve` by `REQ-###`; affected by `IMP-###` |
| `IMP-###` | Potential change, regression, or uncertainty | `affects` `REQ-###`/`INV-###`; may be mitigated by `DEC-###`; produces `AC-###` |
| `DEC-###` | Recorded user choice | refines `REQ-###`; mitigates or accepts `IMP-###` |
| `AC-###` | Testable acceptance or regression criterion | produced by `IMP-###`; verifies a requirement or invariant |

Use only existing IDs in links. Each `IMP-###` has exactly one evidence level; split a compound finding when its assertions need different levels. Create `AC-###` for every critical impact. Create `DEC-###` only after an explicit user/stakeholder selection or a decision explicitly supplied by the request. Before selection, never allocate, link, or forward-reference a concrete `DEC-###` (for example, `DEC-001`); generic “no decision ID is recorded” language is allowed, but operational links and handoffs use only “the pending decision.” A constraint, invariant, recommendation, or policy implied by evidence is not a selection of an exact transition, wire, cache, or retry policy. An `accepted` impact requires that linked recorded decision; a `resolved` impact requires evidence explaining why it no longer applies.

Across report revisions, preserve the `RPT-###` and every still-known `IMP-###`; never renumber an impact because its state changed. A first report has Revision 1 and predecessor `none`. A later report increments by exactly one and records the lowercase SHA-256 of the predecessor's exact bytes. If those bytes are unavailable, disclose missing lineage rather than fabricating a digest.

## Impact states

| State | Meaning |
| --- | --- |
| `detected` | Identified, not yet addressed |
| `refining` | Being reduced through a requirement change |
| `mitigated` | Reduced, not eliminated |
| `resolved` | Eliminated by a requirement or design constraint, with evidence |
| `accepted` | Consciously retained through `DEC-###` |
| `deferred` | Intentionally postponed with rationale |
| `blocked` | Cannot be assessed without named information or access |
| `superseded` | Replaced by a later revision or finding |

`reopened` is a Delta transition, not a ledger state: use it when a previously terminal impact (`resolved`, `accepted`, `deferred`, or `superseded`) returns to `detected`, `refining`, or `blocked`. Stable states are `unchanged`; in particular, `blocked`→`blocked` remains `unchanged`. State changes require a named evidence basis. Resolution needs evidence that the impact no longer applies, and acceptance needs an explicit linked decision.

## Evidence levels and citations

- `verified`: direct inspected support from source, test, schema, configuration, or authoritative specification.
- `inferred`: indirect support from repository context or call relationships.
- `unknown`: insufficient or contradictory support.

For verified and inferred claims, cite a repository-relative path plus a symbol, test name, schema object, or specification ID when available (for example, `ios/UserDTO.swift — UserDTO.init(from:)` or `api/openapi.yaml — User.displayName`). Cite supplied artifacts by their provided identifier. Do not promote advice to verified evidence.

## Example: API field rename

`REQ-001`: rename API field `displayName` to `name`.

| ID | Finding | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `INV-001` | The current iOS decoder reads `displayName`. | `verified` | `ios/UserDTO.swift — UserDTO.init(from:)` | `detected` | `must-preserve` `REQ-001` |
| `IMP-001` | The iOS consumer breaks if the field is removed immediately. | `verified` | `ios/UserDTO.swift — UserDTO.init(from:)` | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | An external consumer may decode the field. | `inferred` | `api/openapi.yaml — User.displayName`; published API contract | `detected` | `affects` `REQ-001` |
| `IMP-003` | The unavailable partner SDK’s handling of the field cannot be assessed. | `unknown` | Partner SDK unavailable; local `api/openapi.yaml — User` inspected | `blocked` | `affects` `REQ-001` |
| `AC-001` | Existing iOS payload decoding continues through the compatibility window. | — | Future observable target; the current decoder is rationale, but no compatibility-window test has been executed (coverage gap). | — | verifies `INV-001`, produced by `IMP-001` |

## Failure and uncertainty handling

| Condition | Required handling |
|---|---|
| repository unavailable | inspect supplied artifacts only and mark code impacts unknown |
| tests unavailable | record a validation gap and propose criteria without claiming coverage |
| documentation conflicts with code | use observed code behavior as the baseline and record the conflict |
| dynamic dispatch or reflection | disclose static-inspection limits and downgrade unsupported claims |
| external dependency unavailable | inspect local contracts/call sites and mark external behavior unknown |
| repository too large for complete inspection | prioritize likely core paths and record the inspected scope |
| requirement changes substantially | mark obsolete impacts superseded and recalculate the whole set |
| evidence contradicts itself | mark the impact blocked or unknown until resolved |
| user accepts a risk | retain accepted state and its decision link |
