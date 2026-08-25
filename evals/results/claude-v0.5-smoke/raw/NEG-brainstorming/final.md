Context check done. The current repo (POLARIS) is an enterprise access-policy portal — unrelated to fitness — so this is a brand-new project with no existing flow to modify. Per the brainstorming skill, I'm classifying this as **architectural** (new project), which means: clarifying questions, then 2–3 approaches, then a design — and nothing gets implemented until you approve. Since this ran as a one-shot task, here is the brainstorming kickoff rather than a finished spec.

## Classification (said out loud)

This looks **architectural** — a new fitness app is a new project, not a bounded change to POLARIS. No code, scaffolding, or spec file has been created. The next step after this message is a dialogue, starting with the first clarifying question below.

## What I verified in the repo

- `/Users/p042890/workspace/polaris/README.md` and `DESIGN.md`: POLARIS is an enterprise AI access-policy portal (Next.js frontend, Spring Boot backend, Supabase). Nothing fitness-related exists here, so the fitness app would be a separate project (or a deliberate reuse of the POLARIS stack — see Direction C).

## Three candidate directions (with trade-offs)

**A. Habit-first micro-workout app (recommended starting point)**
Short daily sessions (5–15 min), streaks, adaptive difficulty, no equipment.
- Pro: smallest viable scope, clearest retention loop, testable MVP in weeks; YAGNI-friendly.
- Con: crowded market — differentiation must come from tone/adaptivity, not features.

**B. Social accountability app**
Small squads (3–6 people), shared weekly goals, check-in photos or auto-verified activity, gentle peer pressure instead of leaderboards.
- Pro: retention driven by people, not gamification; defensible via network effects.
- Con: cold-start problem; needs moderation and privacy design up front.

**C. Practitioner/coach portal + client app**
A trainer manages programs, clients log workouts; sessions sold as packages. Notably, your recent POLARIS commits ("practitioner portal and package ledger") show you already have patterns for exactly this shape — portal shell, package ledger, request/approval flows — that could be reused in a new repo.
- Pro: B2B2C monetizes from day one; your existing Next.js + Spring Boot + Supabase stack and design system transfer directly.
- Con: two user types doubles UX surface; slower to first demo.

**My recommendation:** A if this is a consumer experiment, C if you want to leverage what you've already built. I'd rule out B as a v1 — it's the hardest to bootstrap.

## First clarifying question (one at a time, per the skill)

**Who is this app for — (1) you/consumers building a personal habit, (2) groups keeping each other accountable, or (3) trainers/studios managing clients?** The answer picks the direction and shapes every later question (platform, data model, monetization).

Per the skill's hard gate: no implementation, spec, or scaffolding until the direction is chosen and the design is approved. The user's answer to the question above is what unblocks the next brainstorming step.
