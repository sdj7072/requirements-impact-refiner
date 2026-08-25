Fast impact scan needs more input. Candidate boundaries: no repository-backed candidate. Coverage: needs_input; 3803 ms; cache bypassed.

---

**Status report:**

Per the project's requirements-impact-refiner workflow (which is required before planning or implementing any behavior change), I ran the mandatory Fast Scan for "Make shared links permanent." The `rir_scan` MCP tool was not available in this session, so I used the skill's documented CLI fallback (`scripts/rir-controller.py scan`) against `/Users/p042890/workspace/polaris`, passing the three supplied evidence items (7-day token expiry, revocation on permission change, 90-day signing-key rotation).

The scan result above is verbatim. It came back **needs_input**: the scanner found **no repository-backed candidate boundary** for share links/tokens in the polaris repo — meaning none of the supplied evidence claims could be anchored to actual code (the repo currently contains a frontend practitioner portal and a backend hexagonal skeleton; no share-token expiry, revocation, or key-rotation implementation was located).

Per the skill's rules I must stop here rather than plan or implement. To proceed, one concrete boundary is needed, for example:

1. The file/module that issues or validates share tokens (path in the repo), or
2. The API contract entry for shared links (e.g., a path in `contracts/openapi.yaml`), or
3. Confirmation that this behavior lives outside this repo (in which case the change can't be refined here).

Please provide one concrete boundary (a real file path or component), or confirm whether the three evidence statements refer to code in this repository — then the scan can be rerun and, if the user answers yes to refinement, detailed impact refinement can begin. No code changes were made.
