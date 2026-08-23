# Presentation Modes

Every current report includes `Change Impact Summary` immediately after `Report State`. It is a user-facing projection of the canonical `Impact Ledger`, not a second source of facts.

Resolve each setting independently in this order:

1. The user's current request.
2. Repository-root `.requirements-impact-refiner.json`.
3. Its default.

Run `python3 "$SKILL_DIR/scripts/resolve-settings.py" --project-root REPOSITORY_ROOT`. Add `--audience MODE` or `--delivery MODE` only for an explicit current-request override. If configuration is invalid, disclose the error and use `balanced` plus `compact` for that report.

Repository configuration:

```json
{
  "audience": "balanced",
  "delivery": "compact"
}
```

`audience` accepts `simple`, `balanced`, or `technical` and defaults to `balanced`. `delivery` accepts `compact` or `full` and defaults to `compact`. Audience controls wording detail; delivery controls whether the complete canonical report is returned inline.

Use the same fixed table and one row per current `IMP-###` in every mode. Copy `Severity` and `Status` exactly from that impact's ledger row.

| Mode | Wording contract |
| --- | --- |
| `simple` | Everyday language. Explain the user-visible feature and outcome; omit paths and symbols from prose. |
| `balanced` | Default. Everyday explanation plus the most useful component, contract, or evidence pointer. |
| `technical` | Developer detail, including relevant paths, symbols, contracts, data shapes, or tests. |

For each row:

- **Changed feature:** name the behavior the request changes.
- **Possible issue:** state the concrete failure or regression, not an abstract category.
- **Affected feature or user:** name who or what experiences it.
- **Trigger:** state when the issue can occur.
- **Prevention or check:** summarize the linked invariant, decision, or `AC-###` check without claiming a future check already passed.

The summary must not add, omit, merge, or resolve impacts independently. If evidence is unknown, say what remains unknown in plain language.
