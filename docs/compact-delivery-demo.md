# Compact Delivery Demo

Request:

> Before planning, add an optional `nickname` field to the profile JSON response while preserving clients that only know `displayName`.

Default `balanced` + `compact` response:

| Impact | Possible issue | Affected | Prevention |
| --- | --- | --- | --- |
| `IMP-001` | An unset nickname has no selected wire representation. | Profile API consumers | Choose omission, `null`, or fallback behavior and test it. |
| `IMP-002` | Strict legacy clients may reject the additive field. | Existing `displayName` clients | Preserve `displayName` and run a representative legacy decoder. |
| `IMP-003` | The additive contract may regress later. | All profile consumers | Add fixtures for profiles with and without nicknames. |

The response then asks one decision question and links the validated artifacts:

```text
State: .requirements-impact-refiner/reports/RPT-001/revision-0001.json
Full report: .requirements-impact-refiner/reports/RPT-001/revision-0001.md
```

Render the complete report when needed:

```sh
python3 skills/requirements-impact-refiner/scripts/render-impact-report.py \
  .requirements-impact-refiner/reports/RPT-001/revision-0001.json \
  --format markdown
```

The compact response and complete report come from the same validated state. Compact delivery changes presentation, not impact coverage or lineage.
