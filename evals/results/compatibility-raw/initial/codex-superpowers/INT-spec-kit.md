# Entry

Activate this adapter when the selected orchestrator is GitHub Spec Kit and repository evidence shows that `speckit.clarify` is complete. For this case, the request is “Speckit clarify is complete; refine impacts before planning,” and `speckit.plan` has not started. Consume the clarified requirement and its existing decisions; begin impact refinement after `speckit.clarify`, before any planning work.

# Ownership

Spec Kit is the sole selected orchestrator. Installed Superpowers is not a co-owner and must not add a second workflow. The impact refiner does not repeat general clarification or specification already completed. It asks only evidence-gap or impact-resolution questions, inspects repository evidence, and records decisions and unresolved risk in the canonical impact report. It does not automatically invoke `speckit.plan` or any other external workflow. If more than one orchestrator is active or claimed, stop and ask the user to choose one before continuing.

# Output

Return the canonical requirements-impact report, preserving the clarified requirement and linking each discovered impact to repository evidence or explicitly marking it unknown. Include the report’s planning handoff for Spec Kit: impacts, resolved or accepted decisions, remaining evidence gaps, and constraints that `speckit.plan` must consume. Do not write implementation tasks or a Spec Kit plan, and do not silently change the clarified requirement.

# Exit

Complete when the impact questions are resolved as far as available evidence allows and the canonical report is ready to hand off. End immediately before `speckit.plan`; tell the user that the report is ready for that next step, but do not invoke it automatically. Do not repeat this adapter or re-run broad clarification unless the user supplies a materially revised requirement or explicitly requests another impact pass.
