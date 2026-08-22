# Spec Kit Workflow Integration

## Entry

Enter after `speckit.specify` or `speckit.clarify`. Consume the resulting requirement and its current `Planning Handoff` state.

## Ownership

The adapter does not repeat general clarification already completed. The impact refiner asks only evidence-gap or impact-resolution questions. The external workflow is not automatically invoked. If more than one orchestrator is active, ask the user to choose one before continuing.

## Output

Return the canonical impact report, including its `Planning Handoff`; it is not an implementation plan. Preserve the selected Spec Kit artifact as the requirement baseline.

## Exit

Exit before `speckit.plan`. Hand off the report without invoking `speckit.plan` or writing planning tasks.
