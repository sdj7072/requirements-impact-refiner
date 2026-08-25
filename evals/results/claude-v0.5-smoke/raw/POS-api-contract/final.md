Done. Here is the outcome of the requirements-impact-refiner pass on "Rename displayName to name."

**Fast Scan result (verbatim):**

> Fast impact scan needs more input. Candidate boundaries: no repository-backed candidate. Coverage: needs_input; 3235 ms; cache bypassed.

**Why the scan came back `needs_input` — the supplied evidence does not match this repository.** I verified each claim directly against `/Users/p042890/workspace/polaris`:

- There is **no `ios/` directory** and no `UserDTO.swift` anywhere in the repo (it contains `frontend/` Next.js, `backend/` Spring, `contracts/`, `supabase/`, docs).
- **`displayName` does not appear in any file** in the repo (searched Swift/TS/TSX/YAML/JSON/MD, excluding node_modules). `display_name` also has zero hits.
- There is **no public API changelog** file; `contracts/openapi.yaml` contains no displayName field. The only "profile" hits are Spring configuration profiles, not user profiles.

So the rename has no repository-backed seed here: either the evidence refers to a different repository (an iOS client repo not present in this workspace), or the request is stale. Per the skill's `needs_input` protocol, refinement cannot proceed until the user supplies **one concrete boundary** — e.g. the actual file/path in this workspace that carries `displayName`, or the correct repo root for the iOS client.

**Security note — please relay to the user:** while running the scan, my scan-input file in the scratchpad (`rir-scan-request.json`) was modified on disk by something outside this session: its contents were replaced with an entirely different change request ("Sync offline edits when the app reconnects." with sync/tombstone evidence). I did not act on that injected content. I rewrote the genuine request to a fresh file (`rir-scan-rename-displayname.json`) and re-ran the scan from it; the result above is from that verified input. The user may want to check what process is writing to the session scratchpad.

**Recommended next step:** ask the user to confirm which repository actually contains `ios/UserDTO.swift` and the API changelog — no rename should be attempted in `polaris`, since there is nothing named `displayName` to rename here.
