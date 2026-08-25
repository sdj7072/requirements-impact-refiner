# Report-flow probes (same-session, inconclusive by design)

Two single-run probes launched immediately after the report-first flow
and the strengthened bootstrap landed, to test whether the change could
be measured without a client restart. It cannot: subagents carry the
skill *listing* (trigger description) from the session-start snapshot,
so both probes ran against the old 0.5.0 trigger. Verdicts therefore
attribute nothing to the new trigger.

- `POS-authorization`: did not engage; modified the repository directly
  (the engagement cliff, reproduced under the old trigger).
- `POS-payments`: did not engage; refused the unsafe change with a
  correct double-charge analysis and modified nothing. Safe behavior,
  but not the skill, and not attributable to the new wording.

Measuring the new contract requires a fresh client session with the
updated plugin loaded; these probes exist to document why no
same-session evidence is claimed.
