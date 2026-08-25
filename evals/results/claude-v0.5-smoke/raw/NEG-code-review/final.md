Review complete. I reviewed PR #8 as merged to main (`cd7c3f6`, first-parent diff vs `fc659a1`): the selectable theme system (midnight/aurora/prism) + liquid glass shell, spanning `globals.css`, `layout.tsx`, `portal-shell.tsx`, `dashboard.tsx`, and `next-env.d.ts`.

## Verification run
- `npm run typecheck`: passes
- `npm run lint`: 0 errors (1 pre-existing unused-var warning in `package-editor.tsx`, untouched by this PR)
- `npm run build`: succeeds, all routes compile

## Findings

**1. Bug — dashboard "신청 상세 열기" link 404s for 6 of 10 rows (medium)**
The PR wires the selection notice to `/requests/${selectedRequest.id}`, but the dashboard uses its own local mock `requestRows` with ids REQ-2026-0009 through 0018, while the detail route resolves via `findRequest()` in `requests-mock.ts`, which only contains 0012, 0014, 0016, 0018, 0019, 0021 and calls `notFound()` otherwise. Clicking the link for rows 0009, 0010, 0011, 0013, 0015, or 0017 renders a 404. Fix: derive the dashboard rows from `requests-mock.ts` or align the id sets.

**2. Churn — `next-env.d.ts` committed with dev-generated paths (minor)**
The PR committed the `next dev` variant. I verified locally that `next build` rewrites it back, so this file will flip on every dev/build cycle. Recommend gitignoring `next-env.d.ts` (Next.js's own recommendation) rather than committing either variant. (I restored the file to the committed state after my build.)

**3. Theme system correctness — verified sound**
- The `useSyncExternalStore` pattern in `portal-shell.tsx` is correct: server snapshot `"midnight"` matches SSR output, React re-reads the client snapshot after hydration, and `suppressHydrationWarning` on `<html>` covers the pre-paint script's attribute mutation. The boot script only sets `data-theme` for aurora/prism and wraps localStorage in try/catch — consistent with `applyTheme`, which deletes the attribute for midnight.
- The login screen's Midnight pin is complete: every CSS variable consumed in the login block is re-declared on `.login-screen`, and `body:has(.login-screen)` suppresses the light background layer. Note it depends on `:has()` (fine for modern browsers).
- The `.user-popover button` → `.user-popover > button` scoping change is correct. Light-theme badge overrides appear after the generic badge override, so cascade order is right.

**4. Minor nits (non-blocking)**
- No cross-tab sync: a theme change in one tab won't propagate to another until reload.
- `--chrome` and `--main-background` are still defined in all three theme blocks but no longer consumed anywhere — dead tokens.
- The theme buttons sit inside a `role="menu"` popover without `menuitem` semantics — accessibility nit, consistent with the pre-existing logout button pattern.

Overall: the theme/glass work itself is well-built and hydration-safe; the one real correctness defect is the dashboard-to-detail id mismatch (finding 1), plus the `next-env.d.ts` churn (finding 2).
