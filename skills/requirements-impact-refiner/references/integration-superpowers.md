# Superpowers Workflow Integration

## Entry

Enter after `brainstorming` design approval. Consume the approved design and its current `Planning Handoff` state without reopening ideation. When approval state is known but the design content or repository evidence is unavailable, create a blocked impact report naming those gaps; do not reject entry, restart brainstorming, or proceed to planning.

## Ownership

The adapter does not repeat general clarification already completed. The impact refiner asks only evidence-gap or impact-resolution questions. The external workflow is not automatically invoked. If more than one orchestrator is active, ask the user to choose one before continuing.

## Output

Return the canonical impact report, including its `Planning Handoff`; it is not an implementation plan. Preserve the approved design as the requirement baseline.

In the single `Planning Handoff` row, set `Selected planning workflow` exactly to `superpowers:after-approved-brainstorming;impact-refinement;manual-handoff-before-writing-plans`. Do not decorate, translate, negate, or extend this marker. It records that Superpowers is selected, brainstorming approval precedes impact refinement, the report exits before `writing-plans`, and the handoff is manual rather than automatic. The marker does not claim implementation readiness: record not-ready state and its reason in `Refined requirement` and `Remaining risks`.

## Exit

Exit before `writing-plans`. Hand off the report without invoking `writing-plans` or authoring its work breakdown.
