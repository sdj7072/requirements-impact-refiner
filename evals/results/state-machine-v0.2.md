# State-Machine Behavioral Evaluation

Date: 2026-08-20  
Scope: report-phase selection, decision boundaries, structured delta, and unresolved-item reconciliation.  
Method: fresh-context agents received the named scenario plus only the routed skill files. These are behavioral observations, not client-loader support claims.

## RED — version 0.1.2

Three pre-decision scenarios were run: public share links, payment retry, and object-storage migration.

- Public sharing emitted a forbidden `Decisions and Accepted Risks` section before any choice.
- Payment retry changed canonical section names and omitted the `superseded` delta category.
- Object-storage migration changed the delta schema and omitted `superseded`.

Result: 0/3 satisfied the new phase-and-delta contract.

## GREEN — version 0.2.0

Two fresh pre-decision runs selected `pre-decision`, emitted `Decision Needed`, omitted concrete decision IDs and `Decisions and Accepted Risks`, and included all eight delta categories. Both initially placed `detected`/`refining` rows in the unresolved-items table. The core instructions and both templates were tightened to reserve that table for `deferred`/`blocked`; a focused fresh-context retest then complied.

One fresh post-decision run selected `post-decision`, recorded and linked the explicit choice, omitted `Decision Needed`, included all eight delta categories, and restricted unresolved items to `blocked` rows.

Automated coverage validates both phases, stage-specific required/forbidden sections, focused distinct options, decision linkage, delta completeness/disjointness/state agreement, and unresolved reconciliation.
