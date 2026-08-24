# Compact Delivery Demo

Request:

> Before planning, add an optional `nickname` field to the profile JSON response while preserving clients that only know `displayName`.

Default `balanced` Fast Scan response after one `rir_scan` call:

| Impact | Possible issue | Affected | Prevention |
| --- | --- | --- | --- |
| `IMP-001` | An unset nickname has no selected wire representation. | Profile API consumers | Choose omission, `null`, or fallback behavior and test it. |
| `IMP-002` | Strict legacy clients may reject the additive field. | Existing `displayName` clients | Preserve `displayName` and run a representative legacy decoder. |
| `IMP-003` | The additive contract may regress later. | All profile consumers | Add fixtures for profiles with and without nicknames. |

**Impact paths:**

- `IMP-001`: `PATH-001`: profile response → mobile DTO → cached profile fixture
- `IMP-002`: `PATH-002`: profile response → legacy decoder
- `IMP-003`: `PATH-003`: profile response → contract fixture

**Coverage:** Impact scan: 8.4 s · 8 nodes / 7 edges · 2 unknown frontiers

The response first asks whether detailed refinement is wanted. Only after yes does promotion create and link validated report artifacts:

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

The compact response and complete report come from the same validated state. Simple output omits path IDs, balanced keeps them, and technical adds receipt-derived provider, confidence, and location. The receipt is detect-only: target `10s`, hard ceiling `30s`, no automatic install or network. It exposes unknown frontiers and fallback/partial-cache limits; Deep broadens bounded discovery but does not prove completeness. Compact delivery changes presentation, not impact coverage or lineage.
