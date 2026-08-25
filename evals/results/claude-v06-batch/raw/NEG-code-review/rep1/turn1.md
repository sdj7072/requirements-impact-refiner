Review of PR #25 "docs(process): develop 통합 브랜치 기준으로 브랜치 전략 갱신" (docs-only, 4 files, base `develop`).

## What I verified as correct

- Git reasoning in 6.9.4 is sound: squash-merging `develop`→`main` would break common ancestry and cause repeat conflicts; with merge commits, `develop`'s head becomes an ancestor of `main`, so a routine back-merge is indeed unnecessary and only `main`-only changes (hotfixes) need one.
- Cross-references all resolve on the PR head: 6.4.2, 6.9.4, 6.13, 6.10.2, and the preserved `BRANCH_STRATEGY 6.5.2` link from AGENTS.md. TOC entry for 6.10 was updated to match the renamed heading. Section numbering (6.4.1/6.4.2/6.9.4/6.15.5/6.16.4) is consistent; the change-history date matches the header 기준일 (2026-08-25).
- The `gh pr create` default-base claim is accurate. Tables are well-formed; code fences pair up.
- No stale "branch from `origin/main`" statements remain in normative docs on the PR branch — remaining `origin/main` mentions (lines 69, 391, 399 of BRANCH_STRATEGY.md) are all legitimate hotfix contexts. There is no CLAUDE.md to update.
- AGENTS.md, POLICY.md, README.md, and BRANCH_STRATEGY.md agree with each other on the core model (develop = integration base, main = release base, squash for work PRs, merge commit for release PRs, hotfix from main + back-merge).

## Findings

**1. Internal contradiction in 6.10.2 (real bug) — `/Users/p042890/workspace/polaris/docs/process/BRANCH_STRATEGY.md`, PR-head lines 327 vs 332.** The section's intro sentence was left unedited and still says "다음 비규범 운영 기록은 … `main` 직접 반영을 허용한다", while the newly added sentence five lines later says "직접 반영 대상 브랜치는 `develop`이다. `main`에는 직접 반영하지 않는다." The intro should say `develop`. The PR body claims a contradiction grep was run, but this leftover slipped through.

**2. The documented back-merge procedure violates the PR's own protection rules (operational flaw).** 6.9.4 (line 309) and 6.13 (line 400) instruct `git switch develop … git merge --no-ff origin/main … git push origin develop` — a direct push of code changes to `develop`. But 6.10.1 says both long-lived branches take no direct pushes of code without a PR, POLICY.md §15 says the same, and the PR body's post-merge checklist asks for `develop` branch protection with "PR 필수" — which would reject exactly this push. The docs need either a back-merge-via-PR procedure or an explicit carve-out (and matching protection config) for back-merges.

**3. The 6.12 deploy-event table contradicts the paragraph two lines below it — line 363.** The table row says `main` 병합 (릴리스 PR) → "자동 배포 없음", while the following paragraph (and README.md and AGENTS.md, which both state "`main`에 병합하면 배포가 발생") says that while the Vercel Git connection is maintained — the current, acknowledged state — a `main` merge does trigger a Production deploy. The table describes only the post-disconnect target state without saying so; a reader of the table alone is misled about current behavior. Relatedly, the 6.4.2 release flow (steps 4–5) omits the "verify the auto-deploy triggered by the merge" step that 6.12 itself mandates.

Finding 1 is a must-fix; 2 and 3 are consistency flaws the team should resolve before relying on the document (2 will actively break the day branch protection is enabled on `develop`). No other correctness issues found.