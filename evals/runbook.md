# Requirements Impact Refiner Evaluation Runbook

1. Use a fresh agent context for every repetition.
2. Run each selected case five times with no skill guidance and five times with the candidate skill.
3. Supply only the case request and `repository_evidence`; do not supply the rubric.
4. Score each `must_detect` item as present only when the output connects it to evidence or explicitly marks it inferred/unknown.
5. Score a `must_not_do` violation when the output performs the forbidden neighboring workflow.
6. Record exact model/client/version, enabled orchestrator, tool access, repetition count, detections, violations, and representative quotations.
7. Treat unavailable repository access or unavailable fresh-context execution as a disclosed blocked evaluation, never as a pass.
8. Require all negative cases to avoid activation and all integration cases to preserve one-orchestrator ownership.
