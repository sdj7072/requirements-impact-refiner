Fast Scan complete. Here is the result and what it means.

**Fast Scan output (verbatim):**

> Fast impact scan needs more input. Candidate boundaries: no repository-backed candidate. Coverage: needs_input; 3632 ms; cache bypassed.

**Findings:**

1. **The scan could not find a repository-backed seed for this change.** I verified independently: the polaris repo (`/Users/p042890/workspace/polaris`) contains no occurrences of `dead_letter`, export-job workers, or retry logic — not in `backend/`, `contracts/openapi.yaml`, or the frontend. The three "repository evidence" bullets (deterministic object key, five-attempt retry cap, alerts consuming dead_letter events) do not correspond to any code in this repository, so no impact graph could be seeded. The refiner needs one concrete boundary to proceed — e.g., the actual file/module path of the export worker, the queue/DLQ configuration, or the repo where that code lives, if it is not polaris.

2. **Even before refinement, the supplied evidence flags two conflicts worth confirming with the user:** retrying forever eliminates dead-letter events, which would silently break the alerting that consumes them; and infinite retries against a deterministic object key mean a permanently-failing job can overwrite/churn the same object indefinitely. These should be resolved in refinement, not assumed.

3. **Anomaly disclosed, not acted on:** my scratchpad scan-input file (`rir-scan-request.json`) was modified on disk mid-task by something outside this session, replacing the request with an unrelated one ("Sync offline edits when the app reconnects" with different evidence). I did not act on that content — I wrote the real request to a fresh file (`rir-scan-request-retry-exports.json`) and re-ran the scan against it (cache bypassed). The swapped file was left untouched. If the user intended a different request, they should say so directly.

**Next step required from the user:** provide one concrete boundary (file path, module, or repository) where the export worker / retry / dead-letter code actually lives, or confirm whether they want detailed refinement once a boundary exists. No planning or implementation was done — per the refiner workflow, detailed refinement only proceeds on an explicit yes.
