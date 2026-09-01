# Generic Workflow Integration

## Entry

Enter after the request is concrete enough for repository inspection and the user has not selected a named orchestrator. Approval alone is not sufficient. Before calling `rir_previous`, `rir_scan`, or emitting any `REQ-###`, `INV-###`, `IMP-###`, `DEC-###`, `AC-###`, or canonical report, confirm that both the substantive change request and affected repository scope or evidence target are concrete enough for inspection. Concrete supplied `repository_evidence` is an inspectable evidence target; when it names current behavior, do not demand a mounted repository before reporting its implications and explicit gaps. If either the change or any evidence target is missing, do not start impact refinement or the canonical report; state that the entry gate is not met and ask only for the missing requirement text or scope. A `needs_input` scan is still forbidden activation at this gate. This entry-gate request is not broad product ideation. Once the gate is met, consume the clarified requirement and its current `Planning Handoff` state. When the request states exact mechanics, treat those explicit requested mechanics as already selected rather than asking the user to choose them again.

## Ownership

The adapter does not repeat general clarification already completed. The impact refiner asks only evidence-gap or impact-resolution questions. The external workflow is not automatically invoked. If more than one orchestrator is active, ask the user to choose one before continuing.

## Output

Return the canonical impact report, including its `Planning Handoff`; it is not an implementation plan. Do not add framework-specific commands or conventions.

## Exit

After impact refinement stops, hand the report to the user's chosen planning method. Do not start that method automatically. Return `display_text` verbatim and end the current turn. Do not run commands, use tools, plan, test, or modify files; execution requires a later user turn.
