# Impact Report Templates

Choose exactly one template for the current refinement phase. Do not merge their stage-specific sections.

- Before an explicit choice: [pre-decision template](impact-report-pre-decision-template.md)
- After an explicit choice: [post-decision template](impact-report-post-decision-template.md)

For the first v0.3 report, keep Revision `1`, set `Previous SHA-256` to `none`, place every impact under `new`, and run:

```sh
python3 scripts/validate-impact-report.py --require-summary REPORT.md
```

For every later revision, preserve the Report ID, increment Revision by exactly one, set `Previous SHA-256` from the exact predecessor bytes, and run:

```sh
python3 scripts/validate-impact-report.py --require-summary --previous PREVIOUS.md REPORT.md
```

To render the deterministic Delta without modifying either file:

```sh
python3 scripts/validate-impact-report.py --require-summary --previous PREVIOUS.md --print-expected-delta REPORT.md
```
