The situation is now fully clear — and it changes what I should do. The worktree was clean when I first checked minutes ago, and now shows in-progress Task 1 work (`SecurityConfig.java` modified, `MutationHeaderFilter.java` + tests untracked). An executor is actively working this plan right now, so I must not edit the plan file underneath it. I'll finalize my verification and report.

Final check — confirming the plan's Task 2/5 env names against the properties file already verified, and that the impact-report constraints are honored by the plan's Global Constraints. That's done. Here is my report.

## Report

**The approved specification has already been turned into coding tasks — a complete implementation plan exists and execution has already begun.** I did not create a duplicate plan or modify anything.

### Where the tasks live

- **Plan:** `/Users/p042890/workspace/polaris-worktrees/fix-cross-origin-session/docs/superpowers/plans/2026-08-25-cross-origin-session.md` (commit `99a46dd`, branch `fix/cross-origin-session`)
- **Spec it implements:** `/Users/p042890/workspace/polaris-worktrees/fix-cross-origin-session/docs/superpowers/specs/2026-08-25-cross-origin-session-design.md` (commit `a7d533c`)
- **Approved impact evidence:** `.requirements-impact-refiner/` (RPT-002; latest scan 2026-08-25 20:15 seeds `frontend/src/lib/api.ts` and `SecurityConfig.java`, matching this requirement)

### The 5 coding tasks (each with RED→GREEN→commit steps)

1. **Backend mutation-header guard** — new `MutationHeaderFilter` (`OncePerRequestFilter`) returning contract-JSON 403 for mutations lacking `X-POLARIS-CSRF: 1`; skips GET/HEAD/OPTIONS; MockMvc tests first.
2. **CORS + environment-specific cookie policy** — `SESSION_COOKIE_SAME_SITE`/`SESSION_COOKIE_SECURE` property placeholders (local stays Lax/insecure), add `X-POLARIS-CSRF` to allowed CORS headers; configuration tests first.
3. **Frontend mutation header** — `frontend/src/lib/api.ts` sends `X-POLARIS-CSRF: 1` on POST/PUT/PATCH/DELETE only; static contract check via `frontend/scripts/verify-api-security.mjs` + npm script.
4. **Policy/docs update** — `POLICY.md`, `backend/README.md`, both `.env.example` files; removes the claim that CSRF safety relies only on SameSite=Lax.
5. **Vercel production config + E2E verification** — stable `polaris-backend.vercel.app` alias, disable Vercel Authentication on prod API, set non-secret env values (`NEXT_PUBLIC_API_BASE_URL`, `ALLOWED_ORIGINS`, cookie flags), then health/preflight/browser-login verification.

### Verification I performed

- **Spec coverage:** every spec section (production wiring, cookie policy, CSRF defense, error handling, docs, verification steps) maps to a task. Plan constants match real code: `ErrorResponse.of(code, message)` and `ErrorCode.FORBIDDEN` exist; `app.cors.allowed-origins=${ALLOWED_ORIGINS:...}` and `server.servlet.session.cookie.secure=${SESSION_COOKIE_SECURE:false}` are already in `application.properties` (only `same-site` needs the placeholder); `api.ts` currently sends no CSRF header, so Task 3's RED step is genuinely red.
- **Impact-report alignment:** the plan's Global Constraints encode the accepted decisions (exact-origin credentialed CORS, header-based CSRF replacing Lax-only defense, no secrets read/printed/committed, no schema/workflow/UI changes).

### Live execution warning

Between two of my checks (minutes apart) the worktree went from clean to dirty: `SecurityConfig.java` modified, `MutationHeaderFilter.java` and `MutationHeaderFilterTests.java` created — **Task 1 is being executed right now by another session.** Nothing should rewrite the plan or touch that worktree concurrently.

### Minor residual gaps (for a follow-up, not blocking)

- Task 1 Step 1 and Task 3 Step 1 describe the tests concretely but don't inline the literal test code (strict no-placeholder style).
- The spec's rollback safeguard — "on a failed production deploy, keep the last good deployment; never move the domain alias to a failed deployment" — isn't restated in Task 5.