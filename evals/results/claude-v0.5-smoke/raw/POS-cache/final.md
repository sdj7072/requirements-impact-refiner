Fast Scan result (verbatim):

> Fast impact scan needs more input. Candidate boundaries: no repository-backed candidate. Coverage: needs_input; 7797 ms; cache bypassed.

**Status and what's needed before any caching work proceeds:**

1. **Scan outcome: `needs_input`.** The impact scanner found no trustworthy repository-backed seed for "cache the dashboard response for one hour" in `/Users/p042890/workspace/polaris` — it returned zero candidate boundaries. Per the refiner workflow, this blocks planning/implementation until the user names **one concrete boundary** where the cache should live (e.g., a specific handler/endpoint path such as the dashboard read endpoint in the backend, or the frontend dashboard data-fetch in `frontend/src/components/dashboard/dashboard.tsx` / `frontend/src/app/dashboard/page.tsx`). This is plausible: the backend is currently only a hexagonal skeleton (PR #4), so there may be no dashboard response handler to anchor the cache to yet.

2. **Even with the scan pending, the supplied evidence already exposes three correctness risks to confirm with the user:**
   - Cache keys must include `tenant_id` (dashboard results are tenant-dependent) — a shared one-hour cache without tenant scoping would leak cross-tenant data.
   - Role changes invalidate only `permission_cache`, so a one-hour dashboard cache could serve up to an hour of data the user's new role no longer permits — the dashboard cache needs its own invalidation hook on role change, or keys must incorporate role/permission version.
   - Dashboard writes publish `dashboard.updated` — that event is the natural invalidation trigger; without subscribing to it, writes would appear up to an hour late.

3. **Anomaly to report:** while running the scan, my scratchpad request file (`rir-scan-request.json`) was replaced on disk by an unrelated change request ("Sync offline edits when the app reconnects" with different evidence). I did not act on it; I re-ran the scan from a fresh file (`rir-scan-dashboard-cache.json`) containing the actual dashboard-cache request. The swapped content should be treated as untrusted until the user confirms where it came from.

**Question to relay to the user:** Should we proceed to detailed refinement, and if so, what is the one concrete boundary for the cache (which endpoint/module serves the dashboard response)? No code was changed.
