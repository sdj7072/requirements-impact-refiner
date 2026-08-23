# Evidence Model

## IDs and relationships

- `RPT-###`: stable lineage ID; later revisions link the exact predecessor Markdown SHA-256.
- `REQ-###`: original/refined requirement; affected by impacts and optionally refined by a selected decision.
- `INV-###`: observed behavior to preserve; links its requirement and affected impacts.
- `IMP-###`: change, regression, or uncertainty; links requirement, invariants, criteria, and any selected decision.
- `DEC-###`: explicit user/stakeholder choice; refines a requirement and may mitigate or accept impacts.
- `AC-###`: future observable acceptance/regression criterion; never current evidence by itself.

Define IDs before linking them. Keep IDs stable across revisions. Split a compound impact when its claims need different evidence levels. Before selection, never allocate or forward-reference a concrete decision ID; use “the pending decision.” Constraints, evidence, policy, and recommendations are not user selections.

## Evidence

| Level | Use only when | Citation |
| --- | --- | --- |
| `verified` | Directly inspected source, test, schema, config, or authoritative specification supports the claim. | Repository-relative path plus symbol, test, schema object, or specification ID when available. |
| `inferred` | Repository context or call relationships indirectly support the claim. | Name the inspected basis and inference. |
| `unknown` | Support is missing, unavailable, or contradictory. | Name the information gap and inspected boundary. |

Advice and future criteria are not verified evidence. `resolved` requires current evidence explaining why the impact no longer applies. `accepted` requires a linked explicit decision.

## States

`detected` is unaddressed; `refining` is being reduced; `mitigated` is reduced; `resolved` is eliminated with evidence; `accepted` is retained by decision; `deferred` is postponed with rationale; `blocked` needs named information/access; `superseded` is replaced but retained for lineage.

`reopened` is a Delta transition, not a state: use it when `resolved`, `accepted`, or `superseded` becomes active again. Same-state transitions, including `blocked`→`blocked`, are `unchanged`. First-report impacts are `new`; never remove a known impact—retain it or mark it superseded.

## Uncertainty handling

- Repository unavailable: inspect supplied artifacts; mark uninspected code effects unknown.
- Tests unavailable: record the validation gap; do not claim coverage.
- Documentation conflicts with code: preserve observed behavior and record the conflict.
- Reflection/dynamic dispatch or unavailable dependency: inspect local contracts and disclose limits.
- Large repository: inspect likely core paths and record scope.
- Contradictory evidence: use `unknown` or `blocked` until resolved.
